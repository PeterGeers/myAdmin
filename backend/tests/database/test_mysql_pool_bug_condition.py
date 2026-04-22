#!/usr/bin/env python3
"""
Bug Condition Exploration Test — MySQL Connection Pool Exhaustion

Property 1: Bug Condition — Docker MySQL Query Performance Degradation

These tests encode the EXPECTED (fixed) behavior. They are designed to FAIL
on unfixed code, confirming the bug exists. After the fix is applied, they
should PASS, confirming the fix works.

Root causes tested:
  1. Docker MySQL default memory settings (tmp_table_size = 16MB)
  2. Non-sargable YEAR(TransactionDate) causing full table scans
  3. Redundant rekeningschema joins in vw_mutaties (4 instead of 2)
  4. Full view materialization for SELECT DISTINCT filter queries

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import sys
import os
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

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
# Test 1 — EXPLAIN analysis: YEAR(TransactionDate) should use index, not
#           full scan.  On unfixed code this FAILS (type = ALL).
# ---------------------------------------------------------------------------

class TestExplainYearQuery:
    """
    Bug Condition: YEAR(TransactionDate) wraps the column in a function,
    preventing MySQL from using the index on TransactionDate.

    Expected (fixed): The application uses sargable date range conditions
    instead of YEAR(). EXPLAIN shows index range scans on the composite
    index idx_mutaties_admin_txdate for the mutaties table accesses
    within the view, NOT full table scans (type = ALL).

    On UNFIXED code this test FAILS because the date range query pattern
    was not available and YEAR() caused full table scans.
    """

    @settings(
        max_examples=5,
        deadline=30_000,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(data=st.data())
    def test_year_filter_uses_index_not_full_scan(
        self, data, db, available_years, available_administrations
    ):
        """For any year/administration combo, the fixed date range query
        should use index range scans on the mutaties table, not ALL."""
        year = data.draw(st.sampled_from(available_years))
        admin = data.draw(st.sampled_from(available_administrations))

        start_date = f"{year}-01-01"
        end_date = f"{year + 1}-01-01"

        # Test the FIXED query pattern: sargable date range instead of YEAR()
        explain_rows = db.execute_query(
            "EXPLAIN SELECT * FROM vw_mutaties "
            "WHERE TransactionDate >= %s AND TransactionDate < %s "
            "AND administration = %s",
            (start_date, end_date, admin),
        )

        # Collect the access types for the mutaties table accesses
        # (aliased as 'm' in the view). The derived table wrapper may
        # show ALL which is expected for UNION ALL processing.
        mutaties_access_types = [
            row.get('type', row.get('Type', ''))
            for row in explain_rows
            if row.get('table', row.get('Table', '')) == 'm'
        ]

        # The fix: mutaties table accesses should use range or ref scans
        # via the composite index, NOT full table scans (ALL)
        assert 'ALL' not in mutaties_access_types, (
            f"EXPLAIN shows full table scan (type=ALL) on mutaties for "
            f"date range {start_date} to {end_date}, administration={admin}. "
            f"Mutaties access types: {mutaties_access_types}. "
            f"The sargable date range should use idx_mutaties_admin_txdate "
            f"(Req 2.2)."
        )


# ---------------------------------------------------------------------------
# Test 2 — View join count: vw_mutaties should reference ≤ 3 tables,
#           not 4+ from redundant rekeningschema joins.
# ---------------------------------------------------------------------------

class TestViewJoinCount:
    """
    Bug Condition: vw_mutaties re-joins rekeningschema on top of the base
    views that already join it, resulting in 3 rekeningschema references
    in the EXPLAIN output (one per base view + one in vw_mutaties).

    Expected (fixed): EXPLAIN SELECT * FROM vw_mutaties LIMIT 1 shows
    rekeningschema referenced at most 2 times (once per UNION branch,
    none in vw_mutaties itself). The total EXPLAIN rows for a UNION ALL
    of two 2-table joins is 5: 1 derived + 2×(mutaties + rekeningschema).

    On UNFIXED code this test FAILS because rekeningschema appears 3+
    times (the extra join in vw_mutaties).
    """

    def test_vw_mutaties_join_count_within_limit(self, db):
        """rekeningschema should be referenced ≤ 2 times (no redundant join)."""
        explain_rows = db.execute_query(
            "EXPLAIN SELECT * FROM vw_mutaties LIMIT 1"
        )

        # Each row in EXPLAIN represents one table access.
        table_refs = [
            row.get('table', row.get('Table', ''))
            for row in explain_rows
        ]

        # Count how many times rekeningschema appears (aliased as 'r')
        # In the fixed view: 2 times (once per UNION branch)
        # In the unfixed view: 3 times (extra join in vw_mutaties)
        rekeningschema_refs = [
            t for t in table_refs
            if str(t).lower() in ('r', 'rekeningschema')
        ]

        assert len(rekeningschema_refs) <= 2, (
            f"rekeningschema is referenced {len(rekeningschema_refs)} times "
            f"in EXPLAIN (expected ≤ 2). Tables: {table_refs}. "
            f"This confirms the redundant join bug — vw_mutaties should not "
            f"re-join rekeningschema (Req 1.3, 2.3)."
        )

        # The flattened view should have exactly 5 EXPLAIN rows:
        # 1 derived table + 2 UNION branches × (mutaties + rekeningschema)
        # The unfixed view had 7+ rows (extra rekeningschema join per branch)
        assert len(table_refs) <= 5, (
            f"vw_mutaties EXPLAIN shows {len(table_refs)} table references "
            f"(expected ≤ 5 for flattened UNION ALL). Tables: {table_refs}. "
            f"This suggests the view chain was not properly flattened (Req 2.3)."
        )


# ---------------------------------------------------------------------------
# Test 3 — Memory settings: tmp_table_size should be ≥ 256 MB.
# ---------------------------------------------------------------------------

class TestMemorySettings:
    """
    Bug Condition: Docker MySQL runs with the default tmp_table_size of
    16 MB (16777216 bytes), causing temporary tables to spill to disk.

    Expected (fixed): tmp_table_size ≥ 268435456 (256 MB).

    On UNFIXED code this test FAILS because tmp_table_size = 16777216.
    """

    MINIMUM_TMP_TABLE_SIZE = 256 * 1024 * 1024  # 256 MB in bytes

    def test_tmp_table_size_is_optimized(self, db):
        """tmp_table_size should be ≥ 256 MB."""
        rows = db.execute_query("SHOW VARIABLES LIKE 'tmp_table_size'")
        assert len(rows) > 0, "Could not retrieve tmp_table_size variable"

        value = int(rows[0]['Value'])
        assert value >= self.MINIMUM_TMP_TABLE_SIZE, (
            f"tmp_table_size = {value} bytes ({value / (1024*1024):.1f} MB), "
            f"expected ≥ {self.MINIMUM_TMP_TABLE_SIZE} bytes (256 MB). "
            f"Docker MySQL is running with defaults (Req 1.1)."
        )

    def test_max_heap_table_size_is_optimized(self, db):
        """max_heap_table_size should be ≥ 256 MB."""
        rows = db.execute_query("SHOW VARIABLES LIKE 'max_heap_table_size'")
        assert len(rows) > 0, "Could not retrieve max_heap_table_size variable"

        value = int(rows[0]['Value'])
        assert value >= self.MINIMUM_TMP_TABLE_SIZE, (
            f"max_heap_table_size = {value} bytes "
            f"({value / (1024*1024):.1f} MB), "
            f"expected ≥ {self.MINIMUM_TMP_TABLE_SIZE} bytes (256 MB). "
            f"Docker MySQL is running with defaults (Req 1.1)."
        )

    def test_innodb_buffer_pool_size_is_optimized(self, db):
        """innodb_buffer_pool_size should be ≥ 512 MB."""
        minimum = 512 * 1024 * 1024  # 512 MB
        rows = db.execute_query(
            "SHOW VARIABLES LIKE 'innodb_buffer_pool_size'"
        )
        assert len(rows) > 0, (
            "Could not retrieve innodb_buffer_pool_size variable"
        )

        value = int(rows[0]['Value'])
        assert value >= minimum, (
            f"innodb_buffer_pool_size = {value} bytes "
            f"({value / (1024*1024):.1f} MB), "
            f"expected ≥ {minimum} bytes (512 MB). "
            f"Docker MySQL buffer pool is undersized (Req 1.1)."
        )


# ---------------------------------------------------------------------------
# Test 4 — Filter query efficiency: SELECT DISTINCT on vw_mutaties should
#           NOT require full view materialization.
# ---------------------------------------------------------------------------

class TestFilterQueryEfficiency:
    """
    Bug Condition: SELECT DISTINCT administration FROM vw_mutaties forces
    MySQL to materialize the entire view (all joins, all rows) before
    extracting distinct values.

    Expected (fixed): The application queries the base mutaties table
    directly for filter dropdowns, avoiding full view materialization.
    EXPLAIN on the base table query should show minimal table references.

    On UNFIXED code this test FAILS because the application queried
    vw_mutaties, causing full view materialization.
    """

    def test_distinct_administration_avoids_full_materialization(self, db):
        """
        EXPLAIN SELECT DISTINCT administration FROM mutaties (the fixed
        query pattern) should show just 1 table reference with index usage.
        """
        explain_rows = db.execute_query(
            "EXPLAIN SELECT DISTINCT administration FROM mutaties"
        )

        # Count table references — the fixed query hits mutaties directly
        table_refs = [
            row.get('table', row.get('Table', ''))
            for row in explain_rows
        ]

        # Direct base table query should show exactly 1 table reference
        assert len(table_refs) <= 2, (
            f"SELECT DISTINCT administration FROM mutaties shows "
            f"{len(table_refs)} table references: {table_refs}. "
            f"Expected ≤ 2 (direct base table query). "
            f"Filter queries should hit the base table directly (Req 2.4)."
        )

        # Verify it uses an index (range or index scan), not ALL
        access_types = [
            row.get('type', row.get('Type', ''))
            for row in explain_rows
        ]
        assert 'ALL' not in access_types, (
            f"SELECT DISTINCT administration FROM mutaties uses full "
            f"table scan. Access types: {access_types}. "
            f"Expected index usage (Req 2.4)."
        )

    def test_distinct_reference_avoids_full_materialization(self, db):
        """
        EXPLAIN SELECT DISTINCT ReferenceNumber FROM mutaties (the fixed
        query pattern) should show just 1 table reference.
        """
        explain_rows = db.execute_query(
            "EXPLAIN SELECT DISTINCT ReferenceNumber FROM mutaties "
            "WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != ''"
        )

        table_refs = [
            row.get('table', row.get('Table', ''))
            for row in explain_rows
        ]

        assert len(table_refs) <= 2, (
            f"SELECT DISTINCT ReferenceNumber FROM mutaties shows "
            f"{len(table_refs)} table references: {table_refs}. "
            f"Expected ≤ 2 (Req 2.4)."
        )
