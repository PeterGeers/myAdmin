"""
Preservation Property Tests — Account-Scoped Save-Path Gate (backend)

Spec: banking-import-iban-account-resolution
Property 2: Preservation — Unchanged Behavior for Non-Colliding Inputs

For any input where the bug condition does NOT hold, the fixed
``BankingProcessor.save_approved_transactions`` gate must behave exactly as the
original (unfixed) code. The SECONDARY fix (Task 5) only adds ``Ref1`` to the
authoritative ``Ref2`` duplicate gate; every behavior below sits on the
non-colliding side of that change and must be byte-for-byte preserved.

METHODOLOGY: Observation-first. Each assertion encodes the behavior OBSERVED on
the UNFIXED gate so these tests PASS now (locking in the baseline) and must keep
passing after the fix.

Observed baseline behaviors (bug condition does NOT hold):
  - Same-account duplicate still skipped: a row whose Ref2 matches an existing
    record (same tenant) is skipped — saved_count unchanged, no insert (Req 3.2).
  - Zero-amount lines skipped: amount 0 is skipped before the duplicate gate and
    before any insert (Req 3.5).
  - Closed-period blocking preserved: a non-zero row dated in a closed fiscal year
    raises ClosedPeriodError and no inserts occur (Req 3.6).
  - Wrong-tenant / access-denied rejection preserved: a row with no administration
    is rejected at the tenant-guarded insert (ValueError), so it is NOT saved
    (Req 3.7).

These are run against ``testfinance`` (``test_mode=True``). As with the existing
banking-processor suites (``test_banking_processor.py``,
``test_preservation_closed_period.py``), the ``testfinance`` ``mutaties`` /
``year_closure_status`` state is represented through the mocked DB connection
(the unit-test connection guard forbids real connections); the seeded
``(administration, Ref1, Ref2)`` configuration is encoded in the cursor's
fetch return values.

**Validates: Requirements 3.2, 3.5, 3.6, 3.7**
"""

import sys
import os
import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from banking_processor import BankingProcessor
from db_exceptions import ClosedPeriodError


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Open years: never present in the closed-year configuration below.
open_year_st = st.sampled_from([2024, 2025, 2026])
# Closed years: used only in the closed-period preservation test.
closed_year_st = st.sampled_from([2020, 2021, 2022, 2023])

admin_st = st.sampled_from(['TenantA', 'TenantB', 'GoodwinSolutions'])
month_st = st.integers(min_value=1, max_value=12)
day_st = st.integers(min_value=1, max_value=28)
nonzero_amount_st = st.floats(
    min_value=0.01, max_value=99999.99, allow_nan=False, allow_infinity=False
)
# Ref1 = IBAN (bank account); Ref2 = Volgnr sequence (plain integer string).
iban_st = st.sampled_from([
    'NL98RABO0174003390', 'NL60RABO1101699949', 'NL80RABO0107936917'
])
ref2_st = st.integers(min_value=1, max_value=99).map(str)


def make_bank_txn(trans_date, amount, admin, ref1, ref2):
    """Build a banking transaction dict (lowercase 'administration' key, as the
    frontend/save path uses)."""
    return {
        'row_id': 0,
        'TransactionNumber': f'Rabo {trans_date}',
        'TransactionDate': str(trans_date),
        'TransactionDescription': f'Payment {trans_date}',
        'TransactionAmount': amount,
        'Debet': '',
        'Credit': '1002',
        'ReferenceNumber': '',
        'Ref1': ref1,
        'Ref2': ref2,
        'Ref3': '',
        'Ref4': 'CSV_O.csv',
        'administration': admin,
    }


# ---------------------------------------------------------------------------
# Mock DB builder — represents the testfinance mutaties / year_closure_status
# state through the connection's cursor and execute_query.
# ---------------------------------------------------------------------------

def build_mock_db(ref2_duplicate=False, closed_years_for_admin=None):
    """Build a mock DatabaseManager for BankingProcessor save-path tests.

    Args:
        ref2_duplicate: when True, the authoritative Ref2 gate's SELECT returns a
            matching row (fetchone) → the row is treated as an existing
            same-account duplicate.
        closed_years_for_admin: dict mapping administration -> set of closed years,
            served by the year_closure_status execute_query lookup.
    """
    if closed_years_for_admin is None:
        closed_years_for_admin = {}

    mock_db = MagicMock()

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    if ref2_duplicate:
        # Ref2 gate SELECT ... LIMIT 1 → a matching ID means duplicate.
        mock_cursor.fetchone.return_value = {'ID': 777}
    else:
        mock_cursor.fetchone.return_value = None
    # Fuzzy (amount/date/desc) gate finds nothing.
    mock_cursor.fetchall.return_value = []

    mock_db.get_connection.return_value = mock_conn

    from contextlib import contextmanager

    @contextmanager
    def _get_cursor_cm(*args, **kwargs):
        yield (mock_cursor, mock_conn)
    mock_db.get_cursor = _get_cursor_cm

    def mock_execute_query(query, params=None, **kwargs):
        if 'year_closure_status' in query and params:
            admin = params[0]
            closed = closed_years_for_admin.get(admin, set())
            return [{'year': y} for y in closed]
        return []

    mock_db.execute_query = MagicMock(side_effect=mock_execute_query)
    mock_db.insert_transaction = MagicMock()
    mock_db.normalize_text = None  # unused; BankingProcessor has its own method

    return mock_db, mock_cursor


def make_processor(mock_db):
    with patch('banking_processor.DatabaseManager', return_value=mock_db):
        bp = BankingProcessor(test_mode=True)
    bp.db = mock_db
    return bp


# ===========================================================================
# 3.2 — Same-account duplicate still skipped
# ===========================================================================

class TestSameAccountDuplicatePreserved:
    """A row whose (administration, Ref1, Ref2) already exists is still skipped by
    the Ref2 gate — unchanged by the fix."""

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st, month=month_st, day=day_st,
        amount=nonzero_amount_st, admin=admin_st, ref1=iban_st, ref2=ref2_st,
    )
    def test_existing_same_account_ref2_is_skipped(
        self, year, month, day, amount, admin, ref1, ref2
    ):
        """
        **Validates: Requirements 3.2**

        When the authoritative Ref2 gate finds a matching record, the row is a
        duplicate: saved_count == 0 and insert_transaction is never called.
        """
        trans_date = date(year, month, day)
        txn = make_bank_txn(trans_date, amount, admin, ref1, ref2)

        mock_db, _cursor = build_mock_db(ref2_duplicate=True)
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([txn])

        assert saved_count == 0, (
            f"Expected 0 saved for an existing same-account Ref2={ref2}, "
            f"got {saved_count}"
        )
        assert mock_db.insert_transaction.call_count == 0

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st, month=month_st, day=day_st,
        amount=nonzero_amount_st, admin=admin_st, ref1=iban_st, ref2=ref2_st,
    )
    def test_non_existing_row_is_saved(
        self, year, month, day, amount, admin, ref1, ref2
    ):
        """
        **Validates: Requirements 3.2**

        A row with no matching existing record saves normally — baseline for the
        'skip only true duplicates' behavior.
        """
        trans_date = date(year, month, day)
        txn = make_bank_txn(trans_date, amount, admin, ref1, ref2)

        mock_db, _cursor = build_mock_db(ref2_duplicate=False)
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([txn])

        assert saved_count == 1, (
            f"Expected 1 saved for a genuinely new Ref2={ref2}, got {saved_count}"
        )
        assert mock_db.insert_transaction.call_count == 1


# ===========================================================================
# 3.5 — Zero-amount lines skipped
# ===========================================================================

class TestZeroAmountSkippedPreserved:
    """Zero-amount rows are skipped before the duplicate gate and before insert —
    unchanged by the fix."""

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st, month=month_st, day=day_st,
        admin=admin_st, ref1=iban_st, ref2=ref2_st,
    )
    def test_zero_amount_is_skipped(self, year, month, day, admin, ref1, ref2):
        """
        **Validates: Requirements 3.5**

        A zero-amount row is skipped: saved_count == 0, no insert, even when the
        Ref2 gate would otherwise find no duplicate.
        """
        trans_date = date(year, month, day)
        txn = make_bank_txn(trans_date, 0.0, admin, ref1, ref2)

        mock_db, _cursor = build_mock_db(ref2_duplicate=False)
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([txn])

        assert saved_count == 0, (
            f"Expected 0 saved for a zero-amount row, got {saved_count}"
        )
        assert mock_db.insert_transaction.call_count == 0

    @settings(max_examples=25, deadline=None)
    @given(
        year=open_year_st, month=month_st, day=day_st,
        amount=nonzero_amount_st, admin=admin_st, ref1=iban_st,
    )
    def test_mixed_zero_and_nonzero_only_nonzero_saved(
        self, year, month, day, amount, admin, ref1
    ):
        """
        **Validates: Requirements 3.5**

        In a batch with a zero-amount row and a non-zero row, only the non-zero
        row is saved.
        """
        trans_date = date(year, month, day)
        zero_txn = make_bank_txn(trans_date, 0.0, admin, ref1, '1')
        nonzero_txn = make_bank_txn(trans_date, amount, admin, ref1, '2')

        mock_db, _cursor = build_mock_db(ref2_duplicate=False)
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([zero_txn, nonzero_txn])

        assert saved_count == 1, (
            f"Expected only the non-zero row saved, got {saved_count}"
        )
        assert mock_db.insert_transaction.call_count == 1


# ===========================================================================
# 3.6 — Closed-period blocking preserved
# ===========================================================================

class TestClosedPeriodBlockingPreserved:
    """A non-zero row dated in a closed fiscal year still raises ClosedPeriodError
    and performs no inserts — unchanged by the fix."""

    @settings(max_examples=30, deadline=None)
    @given(
        closed_year=closed_year_st, month=month_st, day=day_st,
        amount=nonzero_amount_st, admin=admin_st, ref1=iban_st, ref2=ref2_st,
    )
    def test_closed_year_raises_and_no_insert(
        self, closed_year, month, day, amount, admin, ref1, ref2
    ):
        """
        **Validates: Requirements 3.6**

        A row targeting a closed fiscal year raises ClosedPeriodError before any
        insert occurs.
        """
        trans_date = date(closed_year, month, day)
        txn = make_bank_txn(trans_date, amount, admin, ref1, ref2)

        mock_db, _cursor = build_mock_db(
            ref2_duplicate=False,
            closed_years_for_admin={admin: {closed_year}},
        )
        bp = make_processor(mock_db)

        with pytest.raises(ClosedPeriodError):
            bp.save_approved_transactions([txn])

        # Closed-period guard runs before the save loop → no inserts.
        assert mock_db.insert_transaction.call_count == 0

    @settings(max_examples=25, deadline=None)
    @given(
        open_year=open_year_st, closed_year=closed_year_st,
        month=month_st, day=day_st,
        amount=nonzero_amount_st, admin=admin_st, ref1=iban_st,
    )
    def test_open_year_not_blocked_when_other_year_closed(
        self, open_year, closed_year, month, day, amount, admin, ref1
    ):
        """
        **Validates: Requirements 3.6**

        An open-year row is NOT blocked merely because a DIFFERENT year is closed
        for the tenant — the closed-period guard is year-specific.
        """
        trans_date = date(open_year, month, day)
        txn = make_bank_txn(trans_date, amount, admin, ref1, '1')

        mock_db, _cursor = build_mock_db(
            ref2_duplicate=False,
            closed_years_for_admin={admin: {closed_year}},
        )
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([txn])

        assert saved_count == 1, (
            f"Expected the open-year row to save (closed year {closed_year} "
            f"differs from {open_year}), got {saved_count}"
        )


# ===========================================================================
# 3.7 — Wrong-tenant / access-denied rejection preserved
# ===========================================================================

class TestWrongTenantRejectionPreserved:
    """A row with no administration is rejected at the tenant-guarded insert, so it
    is not saved — unchanged by the fix. The save loop swallows the per-row error
    and simply does not count the row."""

    @settings(max_examples=30, deadline=None)
    @given(
        year=open_year_st, month=month_st, day=day_st,
        amount=nonzero_amount_st, ref1=iban_st, ref2=ref2_st,
    )
    def test_missing_administration_row_not_saved(
        self, year, month, day, amount, ref1, ref2
    ):
        """
        **Validates: Requirements 3.7**

        A row whose administration is missing/empty is rejected by the tenant
        guard in insert_transaction (ValueError). The save loop catches the error,
        so the row is NOT saved (saved_count == 0).
        """
        trans_date = date(year, month, day)
        txn = make_bank_txn(trans_date, amount, '', ref1, ref2)
        # Represent a missing tenant: no administration value at all.
        del txn['administration']

        mock_db, _cursor = build_mock_db(ref2_duplicate=False)

        # The real tenant guard: insert_transaction rejects a missing tenant.
        def guarded_insert(transaction, table_name='mutaties'):
            administration = transaction.get('Administration') or transaction.get('administration')
            if not administration:
                raise ValueError(
                    'Administration is required for tenant-scoped insert into mutaties'
                )
            return True

        mock_db.insert_transaction = MagicMock(side_effect=guarded_insert)
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([txn])

        assert saved_count == 0, (
            f"Expected a row with no tenant to be rejected (not saved), "
            f"got saved_count={saved_count}"
        )

    @settings(max_examples=25, deadline=None)
    @given(
        year=open_year_st, month=month_st, day=day_st,
        amount=nonzero_amount_st, admin=admin_st, ref1=iban_st,
    )
    def test_valid_tenant_row_saved_against_same_guard(
        self, year, month, day, amount, admin, ref1
    ):
        """
        **Validates: Requirements 3.7**

        With the SAME tenant guard installed, a row carrying a valid administration
        passes the guard and is saved — baseline confirming the guard rejects only
        the missing-tenant case.
        """
        trans_date = date(year, month, day)
        txn = make_bank_txn(trans_date, amount, admin, ref1, '1')

        mock_db, _cursor = build_mock_db(ref2_duplicate=False)

        def guarded_insert(transaction, table_name='mutaties'):
            administration = transaction.get('Administration') or transaction.get('administration')
            if not administration:
                raise ValueError('Administration is required')
            return True

        mock_db.insert_transaction = MagicMock(side_effect=guarded_insert)
        bp = make_processor(mock_db)

        saved_count = bp.save_approved_transactions([txn])

        assert saved_count == 1, (
            f"Expected a valid-tenant row to save, got {saved_count}"
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
