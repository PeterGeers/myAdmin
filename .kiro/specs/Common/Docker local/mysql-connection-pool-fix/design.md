# MySQL Connection Pool Exhaustion Bugfix Design

## Overview

The Docker MySQL environment exhausts all 151 connections because queries against the 3-level view chain `vw_mutaties` get stuck in "converting HEAP to ondisk" state for 400+ seconds. The fix addresses four root causes without changing the connection pooling code or Railway production:

1. **Docker MySQL defaults** — configure `tmp_table_size`, `max_heap_table_size`, `innodb_buffer_pool_size` to match Railway
2. **Non-sargable YEAR() calls** — rewrite 20+ `YEAR(TransactionDate)` usages to date range conditions
3. **Redundant view joins** — flatten the view chain from 4 joins to 2
4. **Full view materialization for filters** — query base `mutaties` table directly for `SELECT DISTINCT` dropdowns

## Glossary

- **Bug_Condition (C)**: Queries against `vw_mutaties` in Docker that trigger "converting HEAP to ondisk" due to default MySQL settings, non-sargable `YEAR()` filters, redundant joins, and full view materialization for filter dropdowns
- **Property (P)**: All queries complete within reasonable time (<5s), connections remain available for external clients, and all result sets are identical to pre-fix behavior
- **Preservation**: Existing query results, amount signs (positive debet / negative credit), tenant isolation, Railway production config, and `DatabaseManager` connection pooling code must remain unchanged
- **vw_mutaties**: Top-level view that unions `vw_debetmutaties` and `vw_creditmutaties`, currently re-joining `rekeningschema` to get `Belastingaangifte`
- **vw_debetmutaties / vw_creditmutaties**: Base views that join `mutaties` with `rekeningschema` on `Debet`/`Credit` columns to get `AccountName`, `Parent`, `VW`, etc.
- **Sargable**: "Search ARGument ABLE" — a query condition that allows the optimizer to use an index. `YEAR(TransactionDate) = 2025` is non-sargable; `TransactionDate >= '2025-01-01' AND TransactionDate < '2026-01-01'` is sargable.
- **rekeningschema**: Chart of accounts table (~270 rows) with columns `Account`, `AccountName`, `Parent`, `VW`, `Belastingaangifte`, `ledger`, `administration`

## Bug Details

### Bug Condition

The bug manifests when the backend executes queries against `vw_mutaties` in the Docker environment. The combination of default MySQL memory settings, non-sargable `YEAR()` function calls, a 3-level view chain with redundant joins, and full view materialization for filter dropdowns causes queries to get stuck in "converting HEAP to ondisk" state, holding connections for 400+ seconds and exhausting all 151 available connections.

**Formal Specification:**

```
FUNCTION isBugCondition(query, environment)
  INPUT: query of type SQLQuery, environment of type {docker, railway}
  OUTPUT: boolean

  RETURN environment = 'docker'
         AND query.targetsView('vw_mutaties')
         AND (
           query.usesFunction('YEAR', 'TransactionDate')
           OR query.isSelectDistinctOnView()
           OR mysqlConfig.tmp_table_size <= 16MB
         )
         AND query.executionTime > 5_SECONDS
END FUNCTION
```

### Examples

- **YEAR() filter on vw_mutaties**: `SELECT * FROM vw_mutaties WHERE YEAR(TransactionDate) = 2025 AND administration = 'GoodwinSolutions'` — full table scan on ~62,000 rows instead of index range scan, takes 400+ seconds in Docker
- **Filter dropdown materialization**: `SELECT DISTINCT administration FROM vw_mutaties WHERE administration IN (...)` — materializes entire view (4 joins, 62K rows) just to get ~3 distinct administration values
- **Trends query with double YEAR()**: `SELECT Parent, ledger, YEAR(TransactionDate) as year, SUM(Amount) ... GROUP BY Parent, ledger, YEAR(TransactionDate)` — uses YEAR() in both SELECT and GROUP BY, preventing any index usage
- **Year-end closure on vw_mutaties**: `SELECT ... FROM vw_mutaties WHERE administration = %s AND YEAR(TransactionDate) = %s AND VW = 'Y'` — combines non-sargable YEAR() with view materialization

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- All query result sets must return identical rows and values after optimization
- Amount signs in `vw_mutaties`: positive for debet mutations (`TransactionAmount`), negative for credit mutations (`-TransactionAmount`)
- The `Aangifte` column must correctly map `rekeningschema.Belastingaangifte` for each row
- Tenant isolation via `administration` filtering on all tenant-scoped queries
- Railway production MySQL configuration and infrastructure — zero changes
- `DatabaseManager` class in `backend/src/database.py` — no modifications to connection pooling logic
- Mouse clicks, UI interactions, and all non-query behavior unaffected

**Scope:**
All inputs that do NOT involve Docker MySQL query execution are completely unaffected. This includes:

- Railway (production) environment operation
- Frontend code and UI behavior
- Authentication and authorization flows
- File processing (CSV, PDF, banking)
- Google Drive integration
- Cache invalidation logic

## Hypothesized Root Cause

Based on the bug description and codebase analysis, the root causes are:

1. **Docker MySQL Default Memory Settings**: Docker MySQL runs with `tmp_table_size=16MB` and `max_heap_table_size=16MB` (defaults), while Railway has `innodb_buffer_pool_size=256MB` and `table_open_cache=2000`. When temporary tables from view materialization exceed 16MB, MySQL converts them from in-memory HEAP to on-disk MyISAM, causing 400+ second query times.

2. **Non-Sargable YEAR() Function**: 20+ locations use `YEAR(TransactionDate)` which wraps the column in a function, preventing MySQL from using the existing `idx_transaction_date_range` index on `TransactionDate`. This forces full table scans on ~62,000 rows.

3. **Redundant Double Join in View Chain**: `vw_debetmutaties`/`vw_creditmutaties` already join `rekeningschema` (on `Debet`/`Credit` → `Account`) to get `AccountName`, `Parent`, `VW`. Then `vw_mutaties` joins `rekeningschema` again (on `Reknum` → `Account`) solely to get `Belastingaangifte`. This doubles the join work (4 joins instead of 2).

4. **Full View Materialization for Filter Dropdowns**: `SELECT DISTINCT` queries on `vw_mutaties` for filter options (administrations, ledgers, references) force MySQL to materialize the entire view before extracting distinct values. These values exist directly in the base `mutaties` table or `rekeningschema`.

## Correctness Properties

Property 1: Bug Condition - Sargable Date Range Equivalence

_For any_ year Y present in the `mutaties` table, the sargable date range condition `TransactionDate >= '{Y}-01-01' AND TransactionDate < '{Y+1}-01-01'` SHALL return exactly the same set of rows as `YEAR(TransactionDate) = Y`, preserving row count and all column values.

**Validates: Requirements 2.2, 3.1**

Property 2: Preservation - View Result Set Identity

_For any_ administration and date range, the flattened `vw_mutaties` view (with `Belastingaangifte` included in base views) SHALL return exactly the same rows with the same column values as the original 3-level view chain, including correct `Aangifte` mapping, amount signs (positive debet, negative credit), and all other columns.

**Validates: Requirements 2.3, 3.2, 3.3**

Property 3: Preservation - Filter Dropdown Equivalence

_For any_ set of tenant-accessible administrations, the optimized filter queries against the base `mutaties` table SHALL return exactly the same distinct values (administrations, ledgers/Reknum, references, years) as the original `SELECT DISTINCT` queries against `vw_mutaties`.

**Validates: Requirements 2.4, 3.7**

Property 4: Preservation - Tenant Isolation

_For any_ query rewritten as part of this fix, the query SHALL continue to include `administration` filtering that restricts results to the authenticated user's accessible tenants, maintaining the same tenant isolation guarantees as the original queries.

**Validates: Requirements 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

### 1. Docker MySQL Configuration

**New File**: `docker/mysql/my.cnf`

Create a custom MySQL configuration file with optimized settings:

```ini
[mysqld]
tmp_table_size=256M
max_heap_table_size=256M
innodb_buffer_pool_size=512M
table_open_cache=2000
max_connections=100
lower-case-table-names=2
```

**File**: `docker-compose.yml`

**Specific Changes**:

- Add volume mount for `my.cnf`: `./docker/mysql/my.cnf:/etc/mysql/conf.d/custom.cnf`
- Remove the `command: --lower-case-table-names=2` line (moved into `my.cnf`)

### 2. YEAR(TransactionDate) Query Rewrites

**New Helper Function**: Create `year_to_date_range(year)` in a shared utility module (e.g., `backend/src/utils/query_helpers.py`):

```python
def year_to_date_range(year):
    """Convert a year to sargable date range conditions.

    Returns (start_date, end_date) where:
      start_date = '{year}-01-01'
      end_date = '{year+1}-01-01'

    Usage: WHERE TransactionDate >= %s AND TransactionDate < %s
    """
    return (f"{int(year)}-01-01", f"{int(year) + 1}-01-01")
```

**Locations to update (source files only — scripts are excluded from this fix):**

| #   | File                  | Function/Location                                   | Current Pattern                                                                        | New Pattern                                                                                                                                  |
| --- | --------------------- | --------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `reporting_routes.py` | `get_trends_data` SELECT                            | `YEAR(TransactionDate) as year`                                                        | `jaar as year` (use existing `jaar` column from view)                                                                                        |
| 2   | `reporting_routes.py` | `get_trends_data` GROUP BY                          | `GROUP BY Parent, ledger, YEAR(TransactionDate)`                                       | `GROUP BY Parent, ledger, jaar`                                                                                                              |
| 3   | `reporting_routes.py` | `get_available_years`                               | `YEAR(TransactionDate) as value`                                                       | `DISTINCT jaar as value` from base table or use `YEAR()` on indexed range                                                                    |
| 4   | `banking_routes.py`   | `get_filters` years query                           | `SELECT DISTINCT YEAR(TransactionDate) as year FROM {table_name}`                      | Use `year_to_date_range` or query distinct `jaar`                                                                                            |
| 5   | `banking_service.py`  | `get_mutaties` years filter                         | `YEAR(TransactionDate) IN (...)`                                                       | Convert each year to date range with OR conditions or use `year_to_date_range`                                                               |
| 6   | `pdf_validation.py`   | `validate_pdf_urls_with_progress`                   | `YEAR(TransactionDate) = %s`                                                           | `TransactionDate >= %s AND TransactionDate < %s`                                                                                             |
| 7   | `pdf_validation.py`   | `get_administrations_for_year`                      | `YEAR(TransactionDate) = %s`                                                           | `TransactionDate >= %s AND TransactionDate < %s`                                                                                             |
| 8   | `mutaties_cache.py`   | `get_available_years`                               | `SELECT DISTINCT YEAR(TransactionDate) as year FROM mutaties`                          | `SELECT DISTINCT YEAR(TransactionDate) as year FROM mutaties` (keep — runs once for cache, not performance-critical) OR rewrite to use index |
| 9   | `year_end_service.py` | `get_available_years`                               | `SELECT DISTINCT YEAR(TransactionDate) as year` + `YEAR(TransactionDate) NOT IN (...)` | Rewrite with date range subquery                                                                                                             |
| 10  | `year_end_service.py` | `_get_first_year`                                   | `MIN(YEAR(TransactionDate))`                                                           | `MIN(TransactionDate)` then extract year in Python                                                                                           |
| 11  | `year_end_service.py` | `_calculate_net_pl_result`                          | `YEAR(TransactionDate) = %s`                                                           | `TransactionDate >= %s AND TransactionDate < %s`                                                                                             |
| 12  | `year_end_service.py` | `_count_balance_sheet_accounts`                     | `YEAR(TransactionDate) = %s`                                                           | `TransactionDate >= %s AND TransactionDate < %s`                                                                                             |
| 13  | `year_end_service.py` | `_get_ending_balances` (has_opening_balance branch) | `YEAR(TransactionDate) = %s`                                                           | `TransactionDate >= %s AND TransactionDate < %s`                                                                                             |
| 14  | `migration_routes.py` | `get_years_needing_migration`                       | `YEAR(TransactionDate) as year`                                                        | Extract year in Python from `MIN(TransactionDate)` per admin, or keep (admin tool, not performance-critical)                                 |
| 15  | `migration_routes.py` | `get_first_year_with_transactions`                  | `MIN(YEAR(TransactionDate))`                                                           | `MIN(TransactionDate)` then extract year in Python                                                                                           |

**Strategy for `YEAR(TransactionDate) IN (year1, year2, ...)`** (banking_service.py):
Convert to: `(TransactionDate >= %s AND TransactionDate < %s) OR (TransactionDate >= %s AND TransactionDate < %s) ...`
Or use: `TransactionDate >= %s AND TransactionDate < %s` with min/max year range when years are contiguous.

**Strategy for `SELECT DISTINCT YEAR(TransactionDate)`** (banking_routes.py, reporting_routes.py):
For the base `mutaties` table, rewrite as:

```sql
SELECT DISTINCT YEAR(TransactionDate) as year
FROM mutaties
WHERE TransactionDate IS NOT NULL AND administration IN (...)
ORDER BY year DESC
```

This still uses `YEAR()` but on a much smaller result set after index-filtered rows. Alternatively, if a composite index `(administration, TransactionDate)` exists, MySQL can do an index-only scan.

### 3. View Chain Flattening

**Step 1**: Alter `vw_debetmutaties` to include `Belastingaangifte` from `rekeningschema`:

```sql
-- vw_debetmutaties already joins rekeningschema on Debet = Account
-- Add r.Belastingaangifte to the SELECT list
ALTER VIEW vw_debetmutaties AS
SELECT
    m.TransactionNumber,
    m.TransactionDate,
    m.TransactionDescription,
    m.TransactionAmount,
    r.Account AS Reknum,
    r.AccountName,
    r.Parent,
    r.VW,
    r.Belastingaangifte,          -- NEW: added here
    YEAR(m.TransactionDate) AS jaar,
    QUARTER(m.TransactionDate) AS kwartaal,
    MONTH(m.TransactionDate) AS maand,
    WEEK(m.TransactionDate) AS week,
    m.ReferenceNumber,
    m.administration,
    m.Ref3,
    m.Ref4
FROM mutaties m
LEFT JOIN rekeningschema r ON m.Debet = r.Account
    AND m.administration = r.administration;
```

**Step 2**: Same for `vw_creditmutaties` — add `r.Belastingaangifte`.

**Step 3**: Simplify `vw_mutaties` to a simple UNION ALL without re-joining:

```sql
CREATE OR REPLACE VIEW vw_mutaties AS
SELECT
    d.Belastingaangifte AS Aangifte,
    d.TransactionNumber,
    d.TransactionDate,
    d.TransactionDescription,
    d.TransactionAmount AS Amount,
    d.Reknum,
    d.AccountName,
    d.Parent,
    d.VW,
    d.jaar,
    d.kwartaal,
    d.maand,
    d.week,
    d.ReferenceNumber,
    d.administration,
    d.Ref3,
    d.Ref4
FROM vw_debetmutaties d

UNION ALL

SELECT
    c.Belastingaangifte AS Aangifte,
    c.TransactionNumber,
    c.TransactionDate,
    c.TransactionDescription,
    -c.TransactionAmount AS Amount,
    c.Reknum,
    c.AccountName,
    c.Parent,
    c.VW,
    c.jaar,
    c.kwartaal,
    c.maand,
    c.week,
    c.ReferenceNumber,
    c.administration,
    c.Ref3,
    c.Ref4
FROM vw_creditmutaties c;
```

This eliminates 2 of the 4 `rekeningschema` joins.

**Implementation**: Create a migration script `backend/scripts/database/flatten_view_chain.py` that:

1. Captures current `vw_mutaties` row count and checksums per administration
2. Drops and recreates views in dependency order
3. Verifies row count and checksums match after recreation

### 4. Composite Index

**File**: New migration or script

```sql
CREATE INDEX idx_mutaties_admin_txdate
ON mutaties(administration, TransactionDate);
```

This composite index covers the most common query pattern: filter by `administration` then range scan on `TransactionDate`. It benefits both the sargable date range rewrites and the filter dropdown queries.

### 5. Filter Query Optimization

**File**: `backend/src/reporting_routes.py` — `get_filter_options` endpoint

Replace `SELECT DISTINCT` queries on `vw_mutaties` with queries on the base `mutaties` table:

```python
# Before (materializes entire view):
cursor.execute("SELECT DISTINCT administration FROM vw_mutaties WHERE ...")

# After (queries base table directly):
cursor.execute("SELECT DISTINCT administration FROM mutaties WHERE ...")
```

For `Reknum` (ledger) values, join `mutaties` with `rekeningschema` directly:

```python
cursor.execute("""
    SELECT DISTINCT r.Account as Reknum
    FROM mutaties m
    JOIN rekeningschema r ON m.Debet = r.Account AND m.administration = r.administration
    WHERE m.administration = %s
    UNION
    SELECT DISTINCT r.Account as Reknum
    FROM mutaties m
    JOIN rekeningschema r ON m.Credit = r.Account AND m.administration = r.administration
    WHERE m.administration = %s
    ORDER BY Reknum
""", [administration, administration])
```

For `ReferenceNumber` values:

```python
cursor.execute("""
    SELECT DISTINCT ReferenceNumber
    FROM mutaties
    WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != ''
    AND administration = %s
    ORDER BY ReferenceNumber
""", [administration])
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Run EXPLAIN on representative queries against the Docker MySQL to confirm non-sargable behavior and full table scans. Measure query execution times and check MySQL process list for "converting HEAP to ondisk" states.

**Test Cases**:

1. **YEAR() Full Table Scan**: Run `EXPLAIN SELECT * FROM vw_mutaties WHERE YEAR(TransactionDate) = 2025 AND administration = 'GoodwinSolutions'` — expect `type: ALL` (full scan) on unfixed code
2. **Filter Dropdown Materialization**: Run `EXPLAIN SELECT DISTINCT administration FROM vw_mutaties` — expect full view materialization on unfixed code
3. **View Chain Join Count**: Run `EXPLAIN SELECT * FROM vw_mutaties LIMIT 1` — expect 4 table references (mutaties + rekeningschema × 2 in base views + rekeningschema × 1 in vw_mutaties)
4. **Memory Settings Check**: Run `SHOW VARIABLES LIKE 'tmp_table_size'` — expect 16MB default on unfixed Docker

**Expected Counterexamples**:

- EXPLAIN shows `type: ALL` for YEAR()-filtered queries
- `SHOW PROCESSLIST` shows queries in "converting HEAP to ondisk" state
- Possible causes: default tmp_table_size (16MB), non-sargable YEAR(), redundant joins

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed queries complete within reasonable time and use indexes.

**Pseudocode:**

```
FOR ALL query WHERE isBugCondition(query, 'docker') DO
  result := executeOptimizedQuery(query)
  ASSERT result.executionTime < 5_SECONDS
  ASSERT result.explainPlan.usesIndex('idx_mutaties_admin_txdate')
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed code produces the same result as the original code.

**Pseudocode:**

```
FOR ALL year IN availableYears DO
  FOR ALL administration IN availableAdministrations DO
    original := executeQuery("SELECT * FROM vw_mutaties WHERE YEAR(TransactionDate) = year AND administration = admin")
    fixed := executeQuery("SELECT * FROM vw_mutaties WHERE TransactionDate >= start AND TransactionDate < end AND administration = admin")
    ASSERT original.rowCount = fixed.rowCount
    ASSERT original.rows = fixed.rows (order-independent)
  END FOR
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many year/administration combinations automatically
- It catches edge cases (year boundaries, NULL dates, leap years)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for all query patterns, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Date Range Equivalence**: For each year in the data, verify `YEAR(TransactionDate) = Y` returns identical rows to `TransactionDate >= 'Y-01-01' AND TransactionDate < '(Y+1)-01-01'`
2. **View Flattening Preservation**: Compare full `vw_mutaties` output before and after view chain flattening — same row count, same column values, same `Aangifte` mapping
3. **Amount Sign Preservation**: Verify debet mutations have positive Amount and credit mutations have negative Amount after view changes
4. **Filter Dropdown Preservation**: Compare distinct administrations, ledgers, references from optimized queries vs original vw_mutaties queries

### Unit Tests

- Test `year_to_date_range()` helper for various years (2020-2030, edge cases like year 0, negative years)
- Test that each rewritten query location uses the helper correctly
- Test Docker MySQL config file contains expected settings
- Test view recreation script handles dependency order correctly

### Property-Based Tests

- Generate random years from the available data range and verify date range equivalence against `YEAR()` results
- Generate random administration + year combinations and verify `vw_mutaties` returns identical results before/after view flattening
- Generate random filter parameter combinations and verify optimized filter queries return same distinct values as original

### Integration Tests

- Test full reporting flow with optimized queries returns same data as before
- Test year-end closure process works correctly with sargable date ranges
- Test banking mutaties listing with date range filters returns correct paginated results
- Test PDF validation with year filter returns same records
- Test that Docker MySQL starts with correct configuration values
- Test that concurrent query load does not exhaust connections
