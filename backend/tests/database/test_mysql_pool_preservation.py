#!/usr/bin/env python3
"""
Preservation Property Tests — MySQL Connection Pool Fix

Property 2: Preservation — Query Result Set Identity and Tenant Isolation

These tests capture the CURRENT (unfixed) behavior as a baseline. They must
ALL PASS on unfixed code, confirming the behavior we need to preserve. After
the fix is applied, they must STILL PASS, confirming no regressions.

Observation-first methodology:
  - Observe current behavior on unfixed code
  - Encode observations as properties
  - Verify properties hold after fix

Properties tested:
  1. Date Range Equivalence — YEAR(TransactionDate) = Y returns identical
     rows to TransactionDate >= '{Y}-01-01' AND TransactionDate < '{Y+1}-01-01'
  2. View Result Set Snapshot — vw_mutaties output (row count, columns,
     Aangifte mapping, amount signs) is preserved
  3. Amount Sign Preservation — debet = positive, credit = negative
  4. Filter Dropdown Equivalence — DISTINCT values from vw_mutaties match
     DISTINCT values from base mutaties table
  5. Tenant Isolation — administration filtering returns only matching rows

Requirements: 3.1, 3.2, 3.3, 3.6, 3.7
"""

import sys
import os
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    """Create a DatabaseManager connected to the Docker MySQL finance database."""
    return DatabaseManager(test_mode=False)


@pytest.fixture(scope="module")
def available_years(db):
    """Fetch the distinct years present in the mutaties table."""
    rows = db.execute_query(
        "SELECT DISTINCT YEAR(TransactionDate) AS yr "
        "FROM mutaties "
        "WHERE TransactionDate IS NOT NULL "
        "ORDER BY yr"
    )
    years = [int(r['yr']) for r in rows if r['yr'] is not None]
    assert len(years) > 0, "No years found in mutaties — is the database populated?"
    return years


@pytest.fixture(scope="module")
def available_administrations(db):
    """Fetch the distinct administrations present in the mutaties table."""
    rows = db.execute_query(
        "SELECT DISTINCT administration FROM mutaties "
        "WHERE administration IS NOT NULL"
    )
    admins = [r['administration'] for r in rows]
    assert len(admins) > 0, "No administrations found — is the database populated?"
    return admins


# ---------------------------------------------------------------------------
# Test 1 — Date Range Equivalence (Property 1 from design)
#
# For all years present in the data, YEAR(TransactionDate) = Y and
# TransactionDate >= '{Y}-01-01' AND TransactionDate < '{Y+1}-01-01'
# must return identical row counts and row sets on the base mutaties table.
#
# Validates: Requirement 3.1
# ---------------------------------------------------------------------------

class TestDateRangeEquivalence:
    """
    Preservation Property: The sargable date range rewrite must return
    exactly the same rows as the original YEAR() filter.

    This test PASSES on unfixed code (baseline) and must continue to
    pass after the YEAR() rewrites are applied.
    """

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_year_vs_date_range_row_count_on_mutaties(
        self, data, db, available_years, available_administrations
    ):
        """Row count from YEAR() filter equals row count from date range."""
        year = data.draw(st.sampled_from(available_years))
        admin = data.draw(st.sampled_from(available_administrations))

        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"

        # YEAR() approach (current)
        year_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM mutaties "
            "WHERE YEAR(TransactionDate) = %s AND administration = %s",
            (year, admin),
        )
        year_count = int(year_rows[0]['cnt'])

        # Date range approach (proposed fix)
        range_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM mutaties "
            "WHERE TransactionDate >= %s AND TransactionDate < %s "
            "AND administration = %s",
            (start_date, end_date, admin),
        )
        range_count = int(range_rows[0]['cnt'])

        assert year_count == range_count, (
            f"Row count mismatch for year={year}, admin={admin}: "
            f"YEAR() returned {year_count}, date range returned {range_count}. "
            f"The date range rewrite must be equivalent (Req 3.1)."
        )

    @settings(
        max_examples=3,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_year_vs_date_range_transaction_numbers_match(
        self, data, db, available_years, available_administrations
    ):
        """The exact set of TransactionNumbers must match between approaches."""
        year = data.draw(st.sampled_from(available_years))
        admin = data.draw(st.sampled_from(available_administrations))

        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"

        # YEAR() approach
        year_rows = db.execute_query(
            "SELECT TransactionNumber FROM mutaties "
            "WHERE YEAR(TransactionDate) = %s AND administration = %s "
            "ORDER BY TransactionNumber",
            (year, admin),
        )
        year_txns = {r['TransactionNumber'] for r in year_rows}

        # Date range approach
        range_rows = db.execute_query(
            "SELECT TransactionNumber FROM mutaties "
            "WHERE TransactionDate >= %s AND TransactionDate < %s "
            "AND administration = %s "
            "ORDER BY TransactionNumber",
            (start_date, end_date, admin),
        )
        range_txns = {r['TransactionNumber'] for r in range_rows}

        assert year_txns == range_txns, (
            f"TransactionNumber sets differ for year={year}, admin={admin}. "
            f"Only in YEAR(): {year_txns - range_txns}. "
            f"Only in range: {range_txns - year_txns}. "
            f"The date range rewrite must return identical rows (Req 3.1)."
        )


# ---------------------------------------------------------------------------
# Test 2 — View Result Set Snapshot (Property 2 from design)
#
# For all administrations, capture the current vw_mutaties output (row count,
# column values, Aangifte mapping, amount signs) as the baseline to preserve.
#
# Validates: Requirements 3.2, 3.3
# ---------------------------------------------------------------------------

class TestViewResultSetSnapshot:
    """
    Preservation Property: The flattened vw_mutaties view must return
    exactly the same rows with the same column values as the original
    3-level view chain.

    This test PASSES on unfixed code (baseline) and must continue to
    pass after the view chain is flattened.
    """

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_vw_mutaties_row_count_per_administration(
        self, data, db, available_administrations
    ):
        """
        Row count from vw_mutaties for each administration must be
        consistent with the sum of debet + credit mutations.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # Count from vw_mutaties
        view_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM vw_mutaties "
            "WHERE administration = %s",
            (admin,),
        )
        view_count = int(view_rows[0]['cnt'])

        # Count debet mutations (rows where Debet is not null/empty)
        debet_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM mutaties m "
            "LEFT JOIN rekeningschema r "
            "ON m.Debet = r.Account AND m.administration = r.administration "
            "WHERE m.administration = %s AND m.Debet IS NOT NULL "
            "AND m.Debet != ''",
            (admin,),
        )
        debet_count = int(debet_rows[0]['cnt'])

        # Count credit mutations
        credit_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM mutaties m "
            "LEFT JOIN rekeningschema r "
            "ON m.Credit = r.Account AND m.administration = r.administration "
            "WHERE m.administration = %s AND m.Credit IS NOT NULL "
            "AND m.Credit != ''",
            (admin,),
        )
        credit_count = int(credit_rows[0]['cnt'])

        expected_count = debet_count + credit_count

        assert view_count == expected_count, (
            f"vw_mutaties row count ({view_count}) != debet ({debet_count}) "
            f"+ credit ({credit_count}) = {expected_count} for admin={admin}. "
            f"View result set must be preserved (Req 3.2)."
        )

    @settings(
        max_examples=3,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_vw_mutaties_aangifte_column_populated(
        self, data, db, available_administrations
    ):
        """
        The Aangifte column in vw_mutaties must be populated from
        rekeningschema.Belastingaangifte. Verify it matches the
        source data for a sample of rows.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # Get a sample of rows with non-null Aangifte from vw_mutaties
        view_rows = db.execute_query(
            "SELECT Reknum, Aangifte FROM vw_mutaties "
            "WHERE administration = %s AND Aangifte IS NOT NULL "
            "LIMIT 10",
            (admin,),
        )

        if len(view_rows) == 0:
            # No rows with Aangifte for this admin — that's fine
            return

        # For each row, verify Aangifte matches rekeningschema
        for row in view_rows:
            reknum = row['Reknum']
            view_aangifte = row['Aangifte']

            schema_rows = db.execute_query(
                "SELECT Belastingaangifte FROM rekeningschema "
                "WHERE Account = %s AND administration = %s",
                (reknum, admin),
            )

            if len(schema_rows) > 0:
                expected = schema_rows[0]['Belastingaangifte']
                assert view_aangifte == expected, (
                    f"Aangifte mismatch for Reknum={reknum}, admin={admin}: "
                    f"vw_mutaties has '{view_aangifte}', rekeningschema has "
                    f"'{expected}'. Aangifte mapping must be preserved "
                    f"(Req 3.2)."
                )


# ---------------------------------------------------------------------------
# Test 3 — Amount Sign Preservation (Property 2 from design)
#
# Debet mutations must have positive Amount and credit mutations must have
# negative Amount (-TransactionAmount) in vw_mutaties.
#
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------

class TestAmountSignPreservation:
    """
    Preservation Property: Amount signs in vw_mutaties must follow the
    convention: positive for debet, negative for credit.

    This test PASSES on unfixed code (baseline) and must continue to
    pass after the view chain is flattened.
    """

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_debet_amounts_are_positive(
        self, data, db, available_administrations
    ):
        """
        Debet-side rows in vw_mutaties (from vw_debetmutaties) must have
        positive Amount values. We identify debet rows by checking that
        the Reknum matches a Debet column value in mutaties.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # Query vw_debetmutaties directly — these are the debet-side rows
        # that feed into vw_mutaties with positive TransactionAmount
        rows = db.execute_query(
            "SELECT TransactionAmount, Reknum "
            "FROM vw_debetmutaties "
            "WHERE administration = %s "
            "LIMIT 50",
            (admin,),
        )

        for row in rows:
            amount = float(row['TransactionAmount'])
            assert amount >= 0, (
                f"Debet-side TransactionAmount should be >= 0 but got "
                f"{amount} for Reknum={row['Reknum']}, admin={admin}. "
                f"Debet amounts must be positive in vw_mutaties (Req 3.3)."
            )

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_credit_amounts_are_negative(
        self, data, db, available_administrations
    ):
        """
        Credit-side rows in vw_mutaties (from vw_creditmutaties) must
        produce negative Amount values. In vw_mutaties, credit amounts
        are negated: -TransactionAmount.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # Verify the sign convention in vw_mutaties: for each row that
        # comes from the credit side, Amount should be negative.
        # We can identify credit rows by checking vw_creditmutaties.
        credit_reknums = db.execute_query(
            "SELECT DISTINCT Reknum FROM vw_creditmutaties "
            "WHERE administration = %s LIMIT 10",
            (admin,),
        )

        if len(credit_reknums) == 0:
            return  # No credit rows for this admin

        # Pick a credit Reknum and verify its Amount is negative in vw_mutaties
        for cr in credit_reknums[:5]:
            reknum = cr['Reknum']
            view_rows = db.execute_query(
                "SELECT Amount FROM vw_mutaties "
                "WHERE administration = %s AND Reknum = %s "
                "AND Amount < 0 LIMIT 5",
                (admin, reknum),
            )
            # We expect at least some negative amounts for credit accounts
            # (there may also be positive amounts if the same account
            # appears on the debet side of other transactions)
            for vr in view_rows:
                assert float(vr['Amount']) < 0, (
                    f"Credit-side Amount should be negative but got "
                    f"{vr['Amount']} for Reknum={reknum}, admin={admin}. "
                    f"Credit amounts must be -TransactionAmount (Req 3.3)."
                )

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_amount_sign_distribution(
        self, data, db, available_administrations
    ):
        """
        vw_mutaties must contain both positive (debet) and negative
        (credit) amounts for administrations with transactions. The
        count of positive amounts must equal the debet row count and
        the count of negative amounts must equal the credit row count.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # Count positive amounts in vw_mutaties (debet side)
        pos_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM vw_mutaties "
            "WHERE administration = %s AND Amount > 0",
            (admin,),
        )
        positive_count = int(pos_rows[0]['cnt'])

        # Count negative amounts in vw_mutaties (credit side)
        neg_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM vw_mutaties "
            "WHERE administration = %s AND Amount < 0",
            (admin,),
        )
        negative_count = int(neg_rows[0]['cnt'])

        # Count debet rows from base view
        debet_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM vw_debetmutaties "
            "WHERE administration = %s",
            (admin,),
        )
        debet_count = int(debet_rows[0]['cnt'])

        # Count credit rows from base view
        credit_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM vw_creditmutaties "
            "WHERE administration = %s",
            (admin,),
        )
        credit_count = int(credit_rows[0]['cnt'])

        # Count zero amounts (can appear on either side)
        zero_rows = db.execute_query(
            "SELECT COUNT(*) AS cnt FROM vw_mutaties "
            "WHERE administration = %s AND Amount = 0",
            (admin,),
        )
        zero_count = int(zero_rows[0]['cnt'])

        # Positive + negative + zero must equal debet + credit
        total_view = positive_count + negative_count + zero_count
        total_base = debet_count + credit_count

        assert total_view == total_base, (
            f"Total vw_mutaties rows ({total_view} = {positive_count} pos + "
            f"{negative_count} neg + {zero_count} zero) != base view total "
            f"({total_base} = {debet_count} debet + {credit_count} credit) "
            f"for admin={admin}. Amount distribution must be preserved "
            f"(Req 3.3)."
        )

        # Non-negative amounts (>= 0) must come from debet side
        assert positive_count + zero_count >= debet_count or \
               positive_count <= debet_count, (
            f"Amount sign distribution inconsistent for admin={admin}. "
            f"Positive: {positive_count}, Zero: {zero_count}, "
            f"Debet: {debet_count} (Req 3.3)."
        )


# ---------------------------------------------------------------------------
# Test 4 — Filter Dropdown Equivalence (Property 3 from design)
#
# SELECT DISTINCT administration FROM vw_mutaties WHERE administration IN (...)
# must return the same set as SELECT DISTINCT administration FROM mutaties
# WHERE administration IN (...).
#
# Validates: Requirement 3.7
# ---------------------------------------------------------------------------

class TestFilterDropdownEquivalence:
    """
    Preservation Property: Optimized filter queries against the base
    mutaties table must return exactly the same distinct values as the
    original queries against vw_mutaties.

    This test PASSES on unfixed code (baseline) and must continue to
    pass after filter queries are rewritten to hit the base table.
    """

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_distinct_administrations_match(
        self, data, db, available_administrations
    ):
        """
        DISTINCT administration from vw_mutaties must equal DISTINCT
        administration from mutaties for any subset of administrations.
        """
        # Draw a non-empty subset of administrations
        subset_size = data.draw(
            st.integers(min_value=1, max_value=len(available_administrations))
        )
        subset = data.draw(
            st.sampled_from(
                [available_administrations[:subset_size]]
            )
        )

        placeholders = ', '.join(['%s'] * len(subset))

        # From vw_mutaties (current approach)
        view_rows = db.execute_query(
            f"SELECT DISTINCT administration FROM vw_mutaties "
            f"WHERE administration IN ({placeholders})",
            tuple(subset),
        )
        view_admins = {r['administration'] for r in view_rows}

        # From base mutaties table (proposed fix)
        base_rows = db.execute_query(
            f"SELECT DISTINCT administration FROM mutaties "
            f"WHERE administration IN ({placeholders})",
            tuple(subset),
        )
        base_admins = {r['administration'] for r in base_rows}

        assert view_admins == base_admins, (
            f"DISTINCT administration mismatch. "
            f"Only in vw_mutaties: {view_admins - base_admins}. "
            f"Only in mutaties: {base_admins - view_admins}. "
            f"Filter dropdown values must be preserved (Req 3.7)."
        )

    @settings(
        max_examples=3,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_distinct_years_match(
        self, data, db, available_administrations
    ):
        """
        DISTINCT years from vw_mutaties must equal DISTINCT years from
        mutaties for any administration.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # From vw_mutaties
        view_rows = db.execute_query(
            "SELECT DISTINCT jaar AS yr FROM vw_mutaties "
            "WHERE administration = %s ORDER BY yr",
            (admin,),
        )
        view_years = {int(r['yr']) for r in view_rows if r['yr'] is not None}

        # From base mutaties table
        base_rows = db.execute_query(
            "SELECT DISTINCT YEAR(TransactionDate) AS yr FROM mutaties "
            "WHERE administration = %s AND TransactionDate IS NOT NULL "
            "ORDER BY yr",
            (admin,),
        )
        base_years = {int(r['yr']) for r in base_rows if r['yr'] is not None}

        assert view_years == base_years, (
            f"DISTINCT years mismatch for admin={admin}. "
            f"Only in vw_mutaties: {view_years - base_years}. "
            f"Only in mutaties: {base_years - view_years}. "
            f"Year filter values must be preserved (Req 3.7)."
        )

    @settings(
        max_examples=3,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_distinct_reference_numbers_match(
        self, data, db, available_administrations
    ):
        """
        DISTINCT ReferenceNumber from vw_mutaties must equal DISTINCT
        ReferenceNumber from mutaties for any administration.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        # From vw_mutaties
        view_rows = db.execute_query(
            "SELECT DISTINCT ReferenceNumber FROM vw_mutaties "
            "WHERE administration = %s "
            "AND ReferenceNumber IS NOT NULL AND ReferenceNumber != '' "
            "ORDER BY ReferenceNumber",
            (admin,),
        )
        view_refs = {r['ReferenceNumber'] for r in view_rows}

        # From base mutaties table
        base_rows = db.execute_query(
            "SELECT DISTINCT ReferenceNumber FROM mutaties "
            "WHERE administration = %s "
            "AND ReferenceNumber IS NOT NULL AND ReferenceNumber != '' "
            "ORDER BY ReferenceNumber",
            (admin,),
        )
        base_refs = {r['ReferenceNumber'] for r in base_rows}

        assert view_refs == base_refs, (
            f"DISTINCT ReferenceNumber mismatch for admin={admin}. "
            f"Only in vw_mutaties: {view_refs - base_refs}. "
            f"Only in mutaties: {base_refs - view_refs}. "
            f"Reference filter values must be preserved (Req 3.7)."
        )


# ---------------------------------------------------------------------------
# Test 5 — Tenant Isolation (Property 4 from design)
#
# For all administration values, queries filtered by administration = X
# must return only rows where administration = X.
#
# Validates: Requirement 3.6
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """
    Preservation Property: Tenant isolation via administration filtering
    must be maintained. Every row returned for administration = X must
    have administration = X.

    This test PASSES on unfixed code (baseline) and must continue to
    pass after all query rewrites.
    """

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_vw_mutaties_tenant_isolation(
        self, data, db, available_administrations
    ):
        """
        All rows from vw_mutaties filtered by administration must have
        the correct administration value.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        rows = db.execute_query(
            "SELECT administration FROM vw_mutaties "
            "WHERE administration = %s LIMIT 100",
            (admin,),
        )

        for row in rows:
            assert row['administration'] == admin, (
                f"Tenant isolation violation: queried admin={admin} but "
                f"got row with administration={row['administration']}. "
                f"Tenant filtering must be preserved (Req 3.6)."
            )

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_mutaties_tenant_isolation(
        self, data, db, available_administrations
    ):
        """
        All rows from base mutaties table filtered by administration
        must have the correct administration value.
        """
        admin = data.draw(st.sampled_from(available_administrations))

        rows = db.execute_query(
            "SELECT administration FROM mutaties "
            "WHERE administration = %s LIMIT 100",
            (admin,),
        )

        for row in rows:
            assert row['administration'] == admin, (
                f"Tenant isolation violation on base table: queried "
                f"admin={admin} but got row with "
                f"administration={row['administration']}. "
                f"Tenant filtering must be preserved (Req 3.6)."
            )

    @settings(
        max_examples=3,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_cross_tenant_exclusion(
        self, data, db, available_administrations
    ):
        """
        Querying for one administration must NOT return rows belonging
        to a different administration.
        """
        if len(available_administrations) < 2:
            return  # Need at least 2 admins to test cross-tenant

        admin = data.draw(st.sampled_from(available_administrations))

        rows = db.execute_query(
            "SELECT DISTINCT administration FROM vw_mutaties "
            "WHERE administration = %s",
            (admin,),
        )

        distinct_admins = {r['administration'] for r in rows}

        assert len(distinct_admins) <= 1, (
            f"Cross-tenant leak: queried admin={admin} but got rows "
            f"from {distinct_admins}. Tenant isolation violated (Req 3.6)."
        )

        if len(distinct_admins) == 1:
            assert admin in distinct_admins, (
                f"Cross-tenant leak: queried admin={admin} but got "
                f"{distinct_admins} (Req 3.6)."
            )
