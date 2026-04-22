# Bugfix Requirements Document

## Introduction

MySQL connection pool exhaustion occurs in the local Docker environment, causing external database clients (HeidiSQL, MySQL Workbench) to be unable to connect. The backend executes slow queries against a 3-level nested view chain (`vw_mutaties` → `vw_debetmutaties`/`vw_creditmutaties` → `mutaties`) that get stuck in "converting HEAP to ondisk" state, holding connections for 400+ seconds and exhausting all 151 available MySQL connections.

The root cause is a combination of:

1. Docker MySQL running with all defaults (16MB `tmp_table_size`, 128MB buffer pool) while Railway has optimized settings (256MB buffer pool, `table_open_cache=2000`)
2. `YEAR(TransactionDate)` used in 20+ queries across the codebase, preventing index usage on `TransactionDate`
3. The view chain performing redundant double joins — `vw_debetmutaties`/`vw_creditmutaties` already join `rekeningschema`, then `vw_mutaties` joins `rekeningschema` again (4 joins instead of 2)
4. `SELECT DISTINCT` queries on `vw_mutaties` for filter dropdowns triggering full view materialization every time

The issue does NOT occur on Railway (production) due to its optimized MySQL configuration and better hardware resources.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the backend executes queries against `vw_mutaties` in the Docker environment THEN the system exhausts all 151 MySQL connections because queries get stuck in "converting HEAP to ondisk" state for 400+ seconds due to Docker MySQL's default 16MB `tmp_table_size` and `max_heap_table_size`

1.2 WHEN queries use `YEAR(TransactionDate)` for filtering (e.g., `WHERE YEAR(TransactionDate) = 2025`) THEN the system performs full table scans on `mutaties` (~62,000 rows) because the `YEAR()` function wrapper prevents MySQL from using the existing `idx_transaction_date_range` index on `TransactionDate`

1.3 WHEN the `vw_mutaties` view is queried THEN the system performs 4 joins with `rekeningschema` instead of 2, because `vw_debetmutaties`/`vw_creditmutaties` each join `rekeningschema` on `Debet`/`Credit`, and then `vw_mutaties` joins `rekeningschema` again on `Reknum` to get `Belastingaangifte`

1.4 WHEN filter dropdown endpoints (`/api/reporting/filters`, `/api/banking/filters`) execute `SELECT DISTINCT` queries on `vw_mutaties` for administrations, years, ledgers, and references THEN the system materializes the entire view for each distinct query, multiplying the performance impact

1.5 WHEN all MySQL connections are exhausted by slow queries THEN external database clients (HeidiSQL, MySQL Workbench) cannot connect and the system becomes unresponsive to new client queries

### Expected Behavior (Correct)

2.1 WHEN the backend executes queries against `vw_mutaties` in the Docker environment THEN the system SHALL complete queries within reasonable time (under 5 seconds) because Docker MySQL SHALL be configured with optimized settings matching Railway's configuration (`tmp_table_size=256M`, `max_heap_table_size=256M`, `innodb_buffer_pool_size=512M`, `table_open_cache=2000`)

2.2 WHEN queries filter by year on `TransactionDate` THEN the system SHALL use sargable date range conditions (`TransactionDate >= '2025-01-01' AND TransactionDate < '2026-01-01'`) instead of `YEAR(TransactionDate)`, allowing MySQL to use the existing `idx_transaction_date_range` index

2.3 WHEN the `vw_mutaties` view is queried THEN the system SHALL perform only 2 joins with `rekeningschema` instead of 4, by including `Belastingaangifte` in the base views (`vw_debetmutaties`/`vw_creditmutaties`) so `vw_mutaties` does not need to re-join `rekeningschema`

2.4 WHEN filter dropdown endpoints execute queries for distinct values THEN the system SHALL query the base `mutaties` table directly (or use cached results) instead of materializing the entire `vw_mutaties` view for each filter query

2.5 WHEN the Docker environment is running with the optimized MySQL configuration THEN the system SHALL maintain available connections for external database clients, preventing connection pool exhaustion under normal backend query load

### Unchanged Behavior (Regression Prevention)

3.1 WHEN queries filter by year using the new date range syntax THEN the system SHALL CONTINUE TO return the same result sets as the original `YEAR(TransactionDate)` queries for all years present in the data

3.2 WHEN the `vw_mutaties` view is queried after flattening the view chain THEN the system SHALL CONTINUE TO return the same columns with the same values, including the correct `Aangifte` (`Belastingaangifte`) column for each row

3.3 WHEN the `vw_mutaties` view calculates amounts THEN the system SHALL CONTINUE TO return positive amounts for debet mutations and negative amounts (`-TransactionAmount`) for credit mutations

3.4 WHEN the Railway (production) environment runs THEN the system SHALL CONTINUE TO operate with its existing optimized MySQL configuration without any changes to production infrastructure

3.5 WHEN the backend connection pooling logic operates THEN the system SHALL CONTINUE TO use the existing `DatabaseManager` class with its scalability manager and legacy pool fallback chain without changes to the connection management code

3.6 WHEN tenant-filtered queries execute THEN the system SHALL CONTINUE TO enforce tenant isolation through `administration` filtering on all queries that touch tenant data

3.7 WHEN filter dropdown endpoints return results THEN the system SHALL CONTINUE TO return the same set of distinct administrations, years, ledgers, and references as before the optimization
