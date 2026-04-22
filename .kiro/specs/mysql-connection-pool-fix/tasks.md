# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Docker MySQL Query Performance Degradation
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists in Docker MySQL
  - **Scoped PBT Approach**: Scope the property to concrete failing cases that demonstrate the root causes
  - Write a property-based test in `backend/tests/database/test_mysql_pool_bug_condition.py` using Hypothesis
  - Test 1 — EXPLAIN analysis: For representative queries using `YEAR(TransactionDate)` on `vw_mutaties`, run `EXPLAIN` and assert the plan uses an index range scan (not `type: ALL` full scan)
  - Test 2 — View join count: Run `EXPLAIN SELECT * FROM vw_mutaties LIMIT 1` and assert the number of table references is ≤ 3 (not 4+ from redundant `rekeningschema` joins)
  - Test 3 — Memory settings: Run `SHOW VARIABLES LIKE 'tmp_table_size'` and assert the value is ≥ 256MB (not the 16MB default)
  - Test 4 — Filter query efficiency: Run `EXPLAIN SELECT DISTINCT administration FROM vw_mutaties` and assert it does NOT require full view materialization
  - The test assertions match the Expected Behavior Properties from design (queries < 5s, index usage, no redundant joins)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists: full scans, 4 joins, 16MB tmp_table_size, full materialization)
  - Document counterexamples found (e.g., "EXPLAIN shows type: ALL for YEAR()-filtered query", "tmp_table_size = 16777216 bytes")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Query Result Set Identity and Tenant Isolation
  - **IMPORTANT**: Follow observation-first methodology
  - Write property-based tests in `backend/tests/database/test_mysql_pool_preservation.py` using Hypothesis
  - **Date Range Equivalence** (Property 1 from design): For all years present in the data, observe that `YEAR(TransactionDate) = Y` and `TransactionDate >= '{Y}-01-01' AND TransactionDate < '{Y+1}-01-01'` return identical row counts and row sets on the base `mutaties` table
  - **View Result Set Snapshot** (Property 2 from design): For all administrations, capture the current `vw_mutaties` output (row count, column values, `Aangifte` mapping, amount signs) as the baseline to preserve
  - **Amount Sign Preservation** (Property 2 from design): Observe that debet mutations have positive `Amount` and credit mutations have negative `Amount` (`-TransactionAmount`) in `vw_mutaties`
  - **Filter Dropdown Equivalence** (Property 3 from design): Observe that `SELECT DISTINCT administration FROM vw_mutaties WHERE administration IN (...)` returns the same set as `SELECT DISTINCT administration FROM mutaties WHERE administration IN (...)`
  - **Tenant Isolation** (Property 4 from design): For all administration values, observe that queries filtered by `administration = X` return only rows where `administration = X`
  - Use Hypothesis `@given` with strategies drawing from actual years and administrations in the database
  - Verify all tests PASS on UNFIXED code (confirms baseline behavior to preserve)
  - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7_

- [x] 3. Docker MySQL Configuration (quickest win)
  - [x] 3.1 Create `docker/mysql/my.cnf` with optimized settings
    - Create file with `[mysqld]` section containing: `tmp_table_size=256M`, `max_heap_table_size=256M`, `innodb_buffer_pool_size=512M`, `table_open_cache=2000`, `max_connections=100`, `lower-case-table-names=2`
    - These settings match Railway's production configuration to eliminate the HEAP-to-ondisk conversion bottleneck
    - _Bug_Condition: isBugCondition(query, 'docker') where mysqlConfig.tmp_table_size <= 16MB_
    - _Expected_Behavior: Docker MySQL configured with tmp_table_size=256M, max_heap_table_size=256M, innodb_buffer_pool_size=512M per design_
    - _Preservation: Railway production config unchanged (Req 3.4), DatabaseManager unchanged (Req 3.5)_
    - _Requirements: 1.1, 2.1, 2.5, 3.4, 3.5_

  - [x] 3.2 Update `docker-compose.yml` to mount `my.cnf` and remove inline command
    - Add volume mount: `./docker/mysql/my.cnf:/etc/mysql/conf.d/custom.cnf`
    - Remove the `command: --lower-case-table-names=2` line (now in `my.cnf`)
    - Verify Docker MySQL starts with the new configuration by checking `SHOW VARIABLES`
    - _Requirements: 2.1, 2.5_

- [x] 4. YEAR(TransactionDate) Query Rewrites
  - [x] 4.1 Create `year_to_date_range()` helper in `backend/src/utils/query_helpers.py`
    - Implement `year_to_date_range(year)` returning `(start_date, end_date)` tuple
    - `start_date = '{year}-01-01'`, `end_date = '{year+1}-01-01'`
    - Add unit tests for edge cases: years 2020-2030, boundary years, type coercion from string input
    - _Bug_Condition: isBugCondition(query) where query.usesFunction('YEAR', 'TransactionDate')_
    - _Expected_Behavior: Sargable date range conditions allow index usage per design_
    - _Requirements: 2.2, 3.1_

  - [x] 4.2 Rewrite `reporting_routes.py` — `get_trends_data` (locations #1, #2 from design)
    - Replace `YEAR(TransactionDate) as year` with `jaar as year` in SELECT
    - Replace `GROUP BY Parent, ledger, YEAR(TransactionDate)` with `GROUP BY Parent, ledger, jaar`
    - The `jaar` column already exists in `vw_mutaties` from the base views
    - _Preservation: Same result set, same grouping (Req 3.1)_
    - _Requirements: 1.2, 2.2, 3.1_

  - [x] 4.3 Rewrite `reporting_routes.py` — `get_available_years` (location #3)
    - Already uses `jaar` column: verify query uses `DISTINCT jaar as value` from `vw_mutaties`
    - If using `YEAR(TransactionDate)`, replace with `jaar`
    - _Requirements: 2.2, 3.1_

  - [x] 4.4 Rewrite `banking_routes.py` — `get_filters` years query (location #4)
    - Replace `SELECT DISTINCT YEAR(TransactionDate) as year FROM {table_name}` with sargable alternative
    - Use `year_to_date_range` helper or query `DISTINCT YEAR(TransactionDate)` on the base `mutaties` table (acceptable since it's filtered by administration via index)
    - Maintain tenant filtering with `administration` parameter
    - _Preservation: Same distinct years returned (Req 3.7), tenant isolation maintained (Req 3.6)_
    - _Requirements: 1.2, 2.2, 3.1, 3.6, 3.7_

  - [x] 4.5 Rewrite `banking_service.py` — `get_mutaties` years filter (location #5)
    - Replace `YEAR(TransactionDate) IN (year1, year2, ...)` with date range OR conditions
    - Use `year_to_date_range` for each year: `(TransactionDate >= %s AND TransactionDate < %s) OR ...`
    - For contiguous years, optimize to single range: `TransactionDate >= %s AND TransactionDate < %s`
    - _Preservation: Same rows returned for any year combination (Req 3.1), tenant isolation (Req 3.6)_
    - _Requirements: 1.2, 2.2, 3.1, 3.6_

  - [x] 4.6 Rewrite `pdf_validation.py` — both locations (locations #6, #7)
    - `validate_pdf_urls_with_progress`: Replace `YEAR(TransactionDate) = %s` with `TransactionDate >= %s AND TransactionDate < %s` using `year_to_date_range`
    - `get_administrations_for_year`: Same replacement pattern
    - Update parameter lists to pass `(start_date, end_date)` instead of `(year,)`
    - _Requirements: 1.2, 2.2, 3.1_

  - [x] 4.7 Rewrite `year_end_service.py` — 5 locations (locations #9-#13)
    - `get_available_years` (#9): Rewrite `YEAR(TransactionDate) NOT IN (...)` subquery with date range logic
    - `_get_first_year` (#10): Replace `MIN(YEAR(TransactionDate))` with `MIN(TransactionDate)` and extract year in Python
    - `_calculate_net_pl_result` (#11): Replace `YEAR(TransactionDate) = %s` with date range using `year_to_date_range`
    - `_count_balance_sheet_accounts` (#12): Same date range replacement
    - `_get_ending_balances` (#13): Replace `YEAR(TransactionDate) = %s` in the `has_opening_balance` branch with date range
    - _Bug_Condition: These queries run on vw_mutaties with YEAR() causing full scans_
    - _Expected_Behavior: Sargable date ranges allow index usage_
    - _Preservation: Same result sets for all year/administration combinations (Req 3.1)_
    - _Requirements: 1.2, 2.2, 3.1, 3.6_

  - [x] 4.8 Rewrite `migration_routes.py` — 2 locations (locations #14, #15)
    - `get_years_needing_migration` (#14): Replace `YEAR(TransactionDate) as year` — keep as-is (admin tool, not performance-critical) or rewrite to extract year in Python
    - `get_first_year_with_transactions` (#15): Replace `MIN(YEAR(TransactionDate))` with `MIN(TransactionDate)` then extract year in Python
    - _Requirements: 1.2, 2.2, 3.1_

  - [x] 4.9 Review `mutaties_cache.py` — location #8 (optional optimization)
    - `get_available_years`: Currently `SELECT DISTINCT YEAR(TransactionDate) as year FROM mutaties` — runs once for cache, not performance-critical
    - Optionally rewrite to use index, or keep as-is per design note
    - _Requirements: 2.2_

- [x] 5. View Chain Flattening
  - [x] 5.1 Create migration script `backend/scripts/database/flatten_view_chain.py`
    - Capture current `vw_mutaties` row count and checksums per administration as baseline
    - Alter `vw_debetmutaties` to include `r.Belastingaangifte` in SELECT list (already joins `rekeningschema`)
    - Alter `vw_creditmutaties` to include `r.Belastingaangifte` in SELECT list (already joins `rekeningschema`)
    - Recreate `vw_mutaties` as simple UNION ALL of `vw_debetmutaties` and `vw_creditmutaties` WITHOUT re-joining `rekeningschema`
    - Debet side: `d.TransactionAmount AS Amount` (positive), Credit side: `-c.TransactionAmount AS Amount` (negative)
    - Map `Belastingaangifte AS Aangifte` from base views instead of re-joining
    - Verify row count and checksums match after recreation
    - _Bug_Condition: isBugCondition(query) where vw_mutaties performs 4 joins instead of 2_
    - _Expected_Behavior: vw_mutaties performs only 2 joins (Req 2.3)_
    - _Preservation: Same rows, same columns, same Aangifte mapping, same amount signs (Req 3.2, 3.3)_
    - _Requirements: 1.3, 2.3, 3.2, 3.3_

  - [x] 5.2 Run migration script and verify view output matches baseline
    - Execute `flatten_view_chain.py` against Docker MySQL
    - Compare row counts per administration before and after
    - Spot-check `Aangifte` values for known accounts
    - Verify amount signs: positive for debet, negative for credit
    - _Requirements: 3.2, 3.3_

- [x] 6. Composite Index
  - [x] 6.1 Add `idx_mutaties_admin_txdate` composite index
    - Execute: `CREATE INDEX idx_mutaties_admin_txdate ON mutaties(administration, TransactionDate)`
    - This covers the most common query pattern: filter by `administration` then range scan on `TransactionDate`
    - Verify index exists with `SHOW INDEX FROM mutaties`
    - Run `EXPLAIN` on a representative query to confirm index usage
    - _Expected_Behavior: Index supports sargable date range queries and filter dropdowns_
    - _Requirements: 2.1, 2.2_

- [x] 7. Filter Query Optimization
  - [x] 7.1 Rewrite `reporting_routes.py` — `get_filter_options` endpoint
    - Replace `SELECT DISTINCT administration FROM vw_mutaties` with `SELECT DISTINCT administration FROM mutaties`
    - Replace `SELECT DISTINCT Reknum FROM vw_mutaties` with a direct join: `SELECT DISTINCT r.Account as Reknum FROM mutaties m JOIN rekeningschema r ON (m.Debet = r.Account OR m.Credit = r.Account) AND m.administration = r.administration WHERE m.administration = %s`
    - Replace `SELECT DISTINCT ReferenceNumber FROM vw_mutaties` with `SELECT DISTINCT ReferenceNumber FROM mutaties WHERE administration = %s`
    - Maintain all existing `administration` filtering for tenant isolation
    - _Bug_Condition: isBugCondition(query) where query.isSelectDistinctOnView()_
    - _Expected_Behavior: Filter queries hit base table directly, no view materialization (Req 2.4)_
    - _Preservation: Same distinct values returned (Req 3.7), tenant isolation maintained (Req 3.6)_
    - _Requirements: 1.4, 2.4, 3.6, 3.7_

  - [x] 7.2 Rewrite `reporting_routes.py` — available accounts query
    - Replace `SELECT DISTINCT Reknum, AccountName FROM vw_mutaties` with direct query on `mutaties` joined with `rekeningschema`
    - Maintain tenant filtering
    - _Requirements: 2.4, 3.6, 3.7_

- [x] 8. Verify bug condition exploration test now passes
  - [x] 8.1 Re-run bug condition exploration test after all fixes
    - **Property 1: Expected Behavior** - Docker MySQL Query Performance After Fix
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (index usage, ≤3 joins, ≥256MB tmp_table_size, no full materialization)
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms all four root causes are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 8.2 Verify preservation tests still pass
    - **Property 2: Preservation** - Query Result Set Identity After Fix
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm date range equivalence, view result set identity, amount signs, filter dropdown equivalence, and tenant isolation are all preserved
    - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7_

- [x] 9. Checkpoint — Ensure all tests pass
  - Run full test suite to confirm no regressions
  - Verify Docker MySQL starts correctly with new `my.cnf` configuration
  - Verify external database clients (HeidiSQL, MySQL Workbench) can connect while backend is running queries
  - Ensure all property-based tests (bug condition + preservation) pass
  - Ask the user if questions arise
