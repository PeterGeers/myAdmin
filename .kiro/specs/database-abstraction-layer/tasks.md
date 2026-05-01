# Implementation Plan: Database Abstraction Layer

## Overview

Centralize all database access through `DatabaseManager`, eliminate direct `mysql.connector` imports from application code, and introduce SQL dialect helpers — making the codebase database-agnostic. The implementation follows 5 phases: build the abstraction foundation, refactor production code, refactor script code, refactor test code, and validate/enforce.

**Language:** Python (Flask backend, pytest + Hypothesis for testing)

## Tasks

### Phase 1: Build the Abstraction Layer Foundation

- [x] 1. Create database-agnostic exception hierarchy (`backend/src/db_exceptions.py`)
  - [x] 1.1 Create `db_exceptions.py` with `DatabaseError`, `IntegrityError`, `ConnectionError`, `OperationalError`
    - Each exception stores `message`, `error_code`, `original_error`
    - `__cause__` set automatically when `original_error` is provided
    - _Requirements: 7.1, 7.5_

  - [x] 1.2 Write property test: Error wrapping preserves type, code, and cause (Property 2)
    - **Property 2: Error wrapping preserves type, code, and cause**
    - Generate random MySQL error types/codes/messages, verify correct agnostic exception with preserved cause
    - Test file: `backend/tests/unit/test_database_abstraction.py`
    - **Validates: Requirements 2.5, 7.2, 7.3, 7.5**

  - [x] 1.3 Write unit tests for exception hierarchy (`backend/tests/unit/test_db_exceptions.py`)
    - Verify class inheritance (`IntegrityError` is a `DatabaseError`, etc.)
    - Verify `error_code` attribute, `__cause__` chaining
    - _Requirements: 7.1, 7.5_

- [x] 2. Create SQL dialect helpers (`backend/src/dialect_helpers.py`)
  - [x] 2.1 Implement `MySQLDialect` class with JSON operations
    - `json_extract(column, path)`, `json_unquote_extract(column, path)`, `json_set(column, path, value_placeholder)`, `json_contains(column, value)`
    - Module-level singleton: `dialect = MySQLDialect()`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 2.2 Implement date and utility operations in `MySQLDialect`
    - `year(column)`, `month(column)`, `current_date()`, `current_timestamp()`, `date_subtract(...)`, `date_add(...)`, `date_diff(...)`, `date_format(...)`, `str_to_date(...)`, `ifnull(...)`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 2.3 Implement identifier quoting and introspection in `MySQLDialect`
    - `quote_identifier(name)` — idempotent backtick quoting
    - `get_view_definition(view_name)`, `list_tables()`, `describe_table(table_name)`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 2.4 Write property test: JSON dialect helpers produce valid SQL fragments (Property 3)
    - **Property 3: JSON dialect helpers produce valid SQL fragments**
    - Generate random column names and JSON paths, verify output contains inputs and is structurally valid
    - Test file: `backend/tests/unit/test_dialect_helpers.py`
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 12.1**

  - [x] 2.5 Write property test: Date and utility dialect helpers produce valid SQL fragments (Property 4)
    - **Property 4: Date and utility dialect helpers produce valid SQL fragments**
    - Generate random columns, intervals, units, formats, verify output contains inputs
    - Test file: `backend/tests/unit/test_dialect_helpers.py`
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 12.2**

  - [x] 2.6 Write property test: Identifier quoting is idempotent (Property 5)
    - **Property 5: Identifier quoting is idempotent**
    - Generate random identifier names, verify `quote_identifier(quote_identifier(name)) == quote_identifier(name)`
    - Test file: `backend/tests/unit/test_dialect_helpers.py`
    - **Validates: Requirements 6.1, 12.3**

  - [x] 2.7 Write property test: Introspection query generators produce valid SQL (Property 6)
    - **Property 6: Introspection query generators produce valid SQL containing the target name**
    - Generate random table/view names, verify output contains the name
    - Test file: `backend/tests/unit/test_dialect_helpers.py`
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [x] 3. Enhance DatabaseManager (`backend/src/database.py`)
  - [x] 3.1 Add `transaction()` context manager to DatabaseManager
    - Auto-commits on success, auto-rollbacks on exception
    - Uses existing `get_cursor()` internally
    - _Requirements: 2.2_

  - [x] 3.2 Add exception wrapping to `execute_query()` and `get_cursor()`
    - Catch `mysql.connector.IntegrityError` → `IntegrityError` (preserve existing FK errno 1452 handling)
    - Catch `mysql.connector.OperationalError` → `OperationalError`
    - Catch `mysql.connector.InterfaceError` → `ConnectionError`
    - Catch `mysql.connector.Error` → `DatabaseError`
    - Preserve `error_code` and `__cause__` on all wrapped exceptions
    - _Requirements: 2.5, 7.2, 7.3, 7.4, 7.5_

  - [x] 3.3 Add `execute_ddl()` method and re-export exception types
    - `execute_ddl(statement)` calls `execute_query(fetch=False, commit=True)`
    - Add `from db_exceptions import DatabaseError, IntegrityError, ConnectionError, OperationalError` re-exports
    - _Requirements: 3.4, 9.1_

  - [x] 3.4 Write property test: Transaction context manager commits on success, rolls back on failure (Property 1)
    - **Property 1: Transaction context manager commits on success and rolls back on failure**
    - Mock-based: verify commit on success, rollback on exception for random query sequences
    - Test file: `backend/tests/unit/test_database_abstraction.py`
    - **Validates: Requirements 2.2**

  - [x] 3.5 Write property test: Connection pool resource management (Property 7)
    - **Property 7: Connection pool resource management**
    - Mock-based: verify connection.close() called on both success and exception paths
    - Test file: `backend/tests/unit/test_database_abstraction.py`
    - **Validates: Requirements 8.4**

  - [x] 3.6 Write unit tests for DatabaseManager enhancements
    - Test `execute_ddl()` delegates correctly
    - Test backward compatibility of `execute_query`, `execute_batch_queries`, `get_connection`, `get_cursor` signatures
    - _Requirements: 3.4, 9.1_

- [x] 4. Create CI lint rule (`backend/scripts/check_db_imports.py`)
  - [x] 4.1 Implement AST-based lint script
    - Scan all `.py` files for `import mysql.connector` and `from mysql.connector`
    - Configurable `ALLOWED_FILES` set (initially `database.py`, `scalability_manager.py`)
    - Exit code 0 = clean, 1 = violations found with descriptive error messages
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 4.2 Write unit tests for CI lint rule
    - Test it catches violations in sample files
    - Test it passes for allowed files
    - Test configurable allowed files list
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 5. Checkpoint — Phase 1 Foundation
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python backend/scripts/check_db_imports.py` to establish baseline violation count

### Phase 2: Refactor Production Code (`backend/src/`) — HIGHEST PRIORITY

- [x] 6. Refactor core database files with direct imports and standalone connections
  - [x] 6.1 Refactor `backend/src/transaction_logic.py` (Inventory #1)
    - Remove `import mysql.connector`
    - Replace `self.get_connection()` / standalone `mysql.connector.connect()` with `DatabaseManager.get_connection()`
    - Route all queries through `DatabaseManager`
    - _Requirements: 1.2, 2.1, 2.4, 11.1, 11.2, 11.5_

  - [x] 6.2 Refactor `backend/src/str_database.py` (Inventory #2)
    - Remove `import mysql.connector`
    - Replace 8× `mysql.connector.Error` catches with `DatabaseError`
    - Replace `DESCRIBE bnb` with `dialect.describe_table('bnb')`
    - _Requirements: 1.2, 6.5, 7.4, 11.1, 11.2, 11.6_

  - [x] 6.3 Refactor `backend/src/routes/missing_invoices_routes.py` (Inventory #3)
    - Remove `import mysql.connector`
    - Delete `get_db_connection()` helper
    - Replace standalone `mysql.connector.connect()` and direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 1.2, 2.1, 2.4, 11.1, 11.2, 11.5_

  - [x] 6.4 Refactor `backend/src/business_pricing_model.py` (Inventory #4)
    - Remove unused `import mysql.connector` (already uses `DatabaseManager`)
    - _Requirements: 1.2, 11.1_

  - [x] 6.5 Refactor `backend/src/services/signup_service.py` (Inventory #5)
    - Remove `import mysql.connector`
    - Replace `_get_connection()` / standalone `mysql.connector.connect()` with `DatabaseManager.get_connection()` or a second `DatabaseManager` instance for the promo database
    - _Requirements: 1.2, 2.4, 11.1, 11.5_

  - [x] 6.6 Remove duplicate `backend/src/validate_pattern/database.py` (Inventory #6)
    - Delete this file entirely (it is a full copy of `database.py`)
    - Update all imports in `validate_pattern/` to use the main `DatabaseManager` from `backend/src/database.py`
    - _Requirements: 1.2, 11.1, 11.5_

  - [x] 6.7 Refactor `backend/src/migrate_revolut_ref2.py` (Inventory #9)
    - Remove `import mysql.connector`
    - Replace standalone `mysql.connector.connect()` with `DatabaseManager`
    - _Requirements: 1.2, 2.4, 11.1, 11.5_

- [x] 7. Checkpoint — Core database files refactored
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python backend/scripts/check_db_imports.py` to verify reduced violation count

- [x] 8. Refactor route files with MySQL-specific SQL (JSON, date, introspection)
  - [x] 8.1 Refactor `backend/src/routes/chart_of_accounts_routes.py` (Inventory #10)
    - Replace `JSON_UNQUOTE(JSON_EXTRACT(...))` with `dialect.json_unquote_extract()`
    - Replace `IFNULL(JSON_EXTRACT(...))` with `dialect.ifnull(dialect.json_extract(...))`
    - 3 query locations
    - _Requirements: 4.5, 5.4, 11.6_

  - [x] 8.2 Refactor `backend/src/routes/str_routes.py` (Inventory #11)
    - Replace `DATE_SUB(CURDATE(), ...)` with `dialect.date_subtract(dialect.current_date(), ...)`
    - Replace `YEAR()`, `MONTH()` with `dialect.year()`, `dialect.month()`
    - Multiple queries
    - _Requirements: 5.1, 5.2, 5.3, 11.6_

  - [x] 8.3 Refactor `backend/src/routes/zzp_routes.py` (Inventory #12)
    - Replace `JSON_EXTRACT(parameters, ...)` with `dialect.json_extract()`
    - Replace `DATEDIFF(CURDATE(), ...)` with `dialect.date_diff(dialect.current_date(), ...)`
    - _Requirements: 4.5, 5.2, 11.6_

  - [x] 8.4 Refactor `backend/src/routes/sysadmin_provisioning.py` (Inventory #13)
    - Replace `DATE_ADD(NOW(), INTERVAL ...)` with `dialect.date_add(dialect.current_timestamp(), ...)`
    - _Requirements: 5.3, 11.6_

  - [x] 8.5 Refactor `backend/src/str_channel_routes.py` (Inventory #14)
    - Replace `JSON_EXTRACT(parameters, '$.str_revenue_account')` with `dialect.json_extract()`
    - _Requirements: 4.5, 11.6_

- [x] 9. Refactor service files with MySQL-specific SQL
  - [x] 9.1 Refactor `backend/src/hybrid_pricing_optimizer.py` (Inventory #15)
    - Replace `DATE_SUB(CURDATE(), ...)`, `DATE_ADD(...)`, `YEAR()`, `MONTH()` in 6+ queries with dialect helpers
    - _Requirements: 5.1, 5.2, 5.3, 11.6_

  - [x] 9.2 Refactor `backend/src/services/ai_usage_tracker.py` (Inventory #16)
    - Replace `DATE_SUB(NOW(), INTERVAL ...)` in 2 queries with `dialect.date_subtract(dialect.current_timestamp(), ...)`
    - _Requirements: 5.3, 11.6_

  - [x] 9.3 Refactor `backend/src/services/pivot_service.py` (Inventory #17)
    - Replace `DESCRIBE {data_source}` with `dialect.describe_table(data_source)`
    - _Requirements: 6.4, 6.5, 11.6_

  - [x] 9.4 Refactor `backend/src/services/year_end_config.py` (Inventory #18)
    - Replace `JSON_SET(COALESCE(parameters, '{}'), ...)` in 2 queries with `dialect.json_set()`
    - _Requirements: 4.3, 11.6_

  - [x] 9.5 Refactor `backend/src/services/invoice_service.py` (Inventory #19)
    - Replace `CURDATE()` with `dialect.current_date()`
    - _Requirements: 5.2, 11.6_

  - [x] 9.6 Refactor `backend/src/services/zzp_invoice_service.py` (Inventory #20)
    - Replace `CURDATE()` with `dialect.current_date()`
    - _Requirements: 5.2, 11.6_

  - [x] 9.7 Refactor `backend/src/services/time_tracking_service.py` (Inventory #21)
    - Replace `DATE_FORMAT(entry_date, ...)` with `dialect.date_format('entry_date', ...)`
    - _Requirements: 5.5, 11.6_

  - [x] 9.8 Refactor `backend/src/services/pdf_generator_service.py` (Inventory #22)
    - Replace `JSON_UNQUOTE(JSON_EXTRACT(parameters, ...))` with `dialect.json_unquote_extract()`
    - _Requirements: 4.2, 11.6_

- [x] 10. Refactor remaining production code files
  - [x] 10.1 Refactor `backend/src/migrations/backfill_rekeningschema_flags.py` (Inventory #23)
    - Replace `JSON_EXTRACT(...)`, `JSON_SET(COALESCE(...))` in 10+ locations with dialect helpers
    - _Requirements: 4.1, 4.3, 11.6_

  - [x] 10.2 Refactor `backend/src/pattern_analyzer.py` (Inventory #24)
    - Replace `DATE_SUB(CURDATE(), ...)` in 2 queries with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

  - [x] 10.3 Refactor `backend/src/validate_pattern/pattern_analyzer_test.py` (Inventory #25)
    - Replace `DATE_SUB(CURDATE(), ...)` in 2 queries with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

  - [x] 10.4 Refactor `backend/src/duplicate_checker.py` (Inventory #26)
    - Replace `CURDATE()` with `dialect.current_date()`
    - _Requirements: 5.2, 11.6_

  - [x] 10.5 Refactor `backend/src/duplicate_query_optimizer.py` (Inventory #27)
    - Replace `CURDATE()` with `dialect.current_date()`
    - _Requirements: 5.2, 11.6_

  - [x] 10.6 Refactor `backend/src/database_migrations.py` (Inventory #28)
    - Replace `CURDATE()` in cleanup query with `dialect.current_date()`
    - _Requirements: 5.2, 11.6_

  - [x] 10.7 Refactor `backend/src/bnb_cache.py` (Inventory #29)
    - Replace `YEAR()`, `MONTH()`, `QUARTER()` with dialect helpers
    - _Requirements: 5.1, 11.6_

  - [x] 10.8 Refactor `backend/src/app.py` (Inventory #30)
    - Replace `CURDATE()` with `dialect.current_date()`
    - _Requirements: 5.2, 11.6_

  - [x] 10.9 Refactor `backend/src/error_handlers.py` (Inventory #31)
    - Update string references to `mysql.connector.errors.DatabaseError` and `mysql.connector.errors.InterfaceError` to use agnostic exception class names
    - _Requirements: 7.4, 11.1_

  - [x] 10.10 Verify `backend/src/reporting_routes.py` (Inventory #32)
    - Verify no raw MySQL SQL exists (the `date_format` key is Python-level, not SQL)
    - No changes expected — confirm and document
    - _Requirements: 11.6_

- [x] 11. Checkpoint — All production code refactored
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python backend/scripts/check_db_imports.py` to verify zero violations in `backend/src/`

### Phase 3: Refactor Script Code (`backend/scripts/` and root `scripts/`)

- [x] 12. Refactor provisioning and migration scripts with direct imports
  - [x] 12.1 Refactor `backend/scripts/provision_tenant.py` (Inventory #33)
    - Remove `import mysql.connector`
    - Replace 8× standalone `mysql.connector.connect()` calls with `DatabaseManager` instances (one for finance DB, one for promo DB)
    - Replace all direct `cursor.execute()` calls
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 12.2 Refactor `backend/scripts/migrate_roles_to_db.py` (Inventory #34)
    - Remove `import mysql.connector`
    - Replace standalone `mysql.connector.connect()` and direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 12.3 Refactor `backend/scripts/setup_test_database.py` (Inventory #35)
    - Remove `import mysql.connector`
    - Replace standalone `mysql.connector.connect()` with `DatabaseManager`
    - Replace `SHOW CREATE VIEW` with `dialect.get_view_definition()`
    - Replace `mysql.connector.Error` catch with `DatabaseError`
    - _Requirements: 1.3, 3.1, 6.5, 11.1, 11.3, 11.5, 11.6_

  - [x] 12.4 Refactor `backend/scripts/run_phase1_migration.py` (Inventory #36)
    - Remove `import mysql.connector`
    - Replace `mysql.connector.Error` catch with `DatabaseError`
    - _Requirements: 1.3, 11.1, 11.3_

  - [x] 12.5 Refactor `backend/scripts/migrate_revolut_ref2.py` (Inventory #37)
    - Remove `import mysql.connector`
    - Replace standalone `mysql.connector.connect()` with `DatabaseManager`
    - Replace `mysql.connector.Error` catch with `DatabaseError`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

- [x] 13. Refactor country-related scripts
  - [x] 13.1 Refactor `backend/scripts/backfill_country.py` (Inventory #38)
    - Remove `import mysql.connector`; replace standalone connection, `executemany`, and error catch with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 13.2 Refactor `backend/scripts/populate_all_countries.py` (Inventory #39)
    - Remove `import mysql.connector`; replace standalone connection, `executemany`, and error catch with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 13.3 Refactor `backend/scripts/create_countries_lookup.py` (Inventory #40)
    - Remove `import mysql.connector`; replace standalone connection, `executemany`, `DESCRIBE`, and error catch with `DatabaseManager` and dialect helpers
    - _Requirements: 1.3, 3.1, 6.4, 6.5, 11.1, 11.3, 11.5, 11.6_

  - [x] 13.4 Refactor `backend/scripts/migrate_add_country.py` (Inventory #41)
    - Remove `import mysql.connector`; replace standalone connection, `DESCRIBE`, and error catch with `DatabaseManager` and dialect helpers
    - _Requirements: 1.3, 3.1, 6.4, 6.5, 11.1, 11.3, 11.5, 11.6_

  - [x] 13.5 Refactor `backend/scripts/migrate_add_country_name.py` (Inventory #42)
    - Remove `import mysql.connector`; replace standalone connection, `DESCRIBE`, and error catch with `DatabaseManager` and dialect helpers
    - _Requirements: 1.3, 3.1, 6.4, 6.5, 11.1, 11.3, 11.5, 11.6_

  - [x] 13.6 Refactor `backend/scripts/generate_country_report.py` (Inventory #43)
    - Remove `import mysql.connector`; replace standalone connection and error catch with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 13.7 Refactor `backend/scripts/fix_country_12.py` (Inventory #44)
    - Remove `import mysql.connector`; replace standalone connection and `executemany` with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 13.8 Refactor `backend/scripts/debug_country.py` (Inventory #45)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 13.9 Refactor `backend/scripts/verify_country.py` (Inventory #46)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 13.10 Refactor `backend/scripts/test_country_lookup.py` (Inventory #47)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

- [x] 14. Checkpoint — Provisioning, migration, and country scripts refactored
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Refactor maintenance, database, and encoding scripts
  - [x] 15.1 Refactor `backend/scripts/maintenance/query_templates.py` (Inventory #48)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - Remove hardcoded credentials
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 15.2 Refactor `backend/scripts/database/fix_encoding_duplicate.py` (Inventory #49)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 15.3 Refactor `backend/scripts/database/configure_vat_netting.py` (Inventory #50)
    - Replace `JSON_EXTRACT(...)`, `JSON_SET(...)` with dialect helpers
    - _Requirements: 4.1, 4.3, 11.6_

  - [x] 15.4 Refactor `backend/scripts/database/test_parameters_column.py` (Inventory #51)
    - Replace `JSON_EXTRACT(...)`, `JSON_CONTAINS(...)` with dialect helpers
    - Replace direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 4.1, 4.4, 11.3, 11.6_

  - [x] 15.5 Refactor `backend/scripts/database/create_year_closure_tables.py` (Inventory #52)
    - Replace `JSON_EXTRACT(...)` in index creation with dialect helper
    - _Requirements: 4.1, 11.6_

  - [x] 15.6 Refactor `backend/scripts/database/apply_schema_migration.py` (Inventory #53)
    - Replace `JSON_EXTRACT(...)` in index creation with dialect helper
    - _Requirements: 4.1, 11.6_

  - [x] 15.7 Refactor `backend/scripts/database/migrate_opening_balances.py` (Inventory #54)
    - Replace `JSON_CONTAINS(...)` with `dialect.json_contains()`
    - _Requirements: 4.4, 11.6_

- [x] 16. Refactor view introspection scripts
  - [x] 16.1 Refactor `backend/scripts/fix_lookupbankaccounts_view.py` (Inventory #55)
    - Replace `SHOW CREATE VIEW` in 2 locations with `dialect.get_view_definition()`
    - _Requirements: 6.2, 6.5, 11.6_

  - [x] 16.2 Refactor `backend/scripts/verify_all_views_lowercase.py` (Inventory #56)
    - Replace `SHOW CREATE VIEW` with `dialect.get_view_definition()`
    - _Requirements: 6.2, 6.5, 11.6_

  - [x] 16.3 Refactor `backend/scripts/diagnose_mysql_workbench_issue.py` (Inventory #57)
    - Replace `SHOW CREATE VIEW` with `dialect.get_view_definition()`
    - _Requirements: 6.2, 6.5, 11.6_

  - [x] 16.4 Refactor `backend/scripts/diagnostics/check_account_1022.py` (Inventory #58)
    - Replace `SHOW CREATE VIEW` with `dialect.get_view_definition()`
    - _Requirements: 6.2, 6.5, 11.6_

  - [x] 16.5 Refactor `backend/scripts/analysis/investigate_account_1022_root_cause.py` (Inventory #59)
    - Replace `SHOW CREATE VIEW` with `dialect.get_view_definition()`
    - _Requirements: 6.2, 6.5, 11.6_

- [x] 17. Refactor analysis scripts with direct imports
  - [x] 17.1 Refactor `backend/scripts/analysis/analyze_goodwin.py` (Inventory #60)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 17.2 Refactor `backend/scripts/analysis/analyze_mutaties_table.py` (Inventory #61)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 17.3 Refactor `backend/scripts/analysis/check_columns.py` (Inventory #62)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 17.4 Refactor `backend/scripts/analysis/debug_account_names.py` (Inventory #63)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 17.5 Refactor `backend/scripts/analysis/debug_check_accounts.py` (Inventory #64)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 17.6 Refactor `backend/scripts/analysis/debug_ref4.py` (Inventory #65)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 17.7 Refactor `backend/scripts/analysis/show_duplicates.py` (Inventory #66)
    - Remove `import mysql.connector`; replace standalone connection with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

- [x] 18. Refactor data optimization and pattern scripts
  - [x] 18.1 Refactor `backend/scripts/data/optimize_pattern_storage.py` (Inventory #67)
    - Replace `DATE_SUB(CURDATE(), ...)` in 4+ queries with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

  - [x] 18.2 Refactor `backend/scripts/data/pattern_storage_value_analysis.py` (Inventory #68)
    - Replace `DATE_SUB(CURDATE(), ...)` with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

  - [x] 18.3 Refactor `backend/scripts/data/aggressive_pattern_optimization.py` (Inventory #69)
    - Replace `DATE_SUB(CURDATE(), ...)` in 5+ queries with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

  - [x] 18.4 Refactor `backend/scripts/database/consolidate_database_views.py` (Inventory #70)
    - Replace `DATE_SUB(CURDATE(), ...)` with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

- [x] 19. Refactor remaining backend scripts
  - [x] 19.1 Refactor `backend/scripts/check_str_invoice_tenant_filtering.py` (Inventory #71)
    - Replace `DATE_SUB(CURDATE(), ...)`, `CURDATE()` with dialect helpers
    - _Requirements: 5.2, 5.3, 11.6_

  - [x] 19.2 Refactor `backend/scripts/maintenance/fix_checkout_dates.py` (Inventory #72)
    - Replace `DATE_ADD(checkinDate, INTERVAL ...)` with `dialect.date_add()`
    - _Requirements: 5.3, 11.6_

  - [x] 19.3 Refactor `backend/scripts/database/check_view_names.py` (Inventory #73)
    - Replace `SHOW FULL TABLES WHERE Table_type = "VIEW"` with `dialect.list_tables()`
    - _Requirements: 6.3, 6.5, 11.6_

  - [x] 19.4 Refactor `backend/scripts/check_year_end_setup.py` (Inventory #74)
    - Replace `DESCRIBE year_closure_status` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.6_

  - [x] 19.5 Refactor `backend/scripts/verify_ai_usage_log_table.py` (Inventory #75)
    - Replace `DESCRIBE ai_usage_log` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.6_

  - [x] 19.6 Refactor `backend/scripts/verify_template_validation_log_table.py` (Inventory #76)
    - Replace `DESCRIBE template_validation_log` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.6_

  - [x] 19.7 Refactor `backend/scripts/database/apply_pattern_migrations.py` (Inventory #77)
    - Replace `DESCRIBE pattern_analysis_metadata`, `DESCRIBE pattern_verb_patterns` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.6_

  - [x] 19.8 Refactor `backend/scripts/diagnostics/check_myadmin_module.py` (Inventory #78)
    - Replace `DESCRIBE tenant_modules` with `dialect.describe_table()`
    - Replace direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 3.1, 6.4, 6.5, 11.3, 11.6_

  - [x] 19.9 Refactor `backend/scripts/create_ai_usage_log_table.py` (Inventory #79)
    - Update string references to `SHOW`/`DESCRIBE` if needed
    - _Requirements: 11.6_

- [x] 20. Refactor root `scripts/` directory files
  - [x] 20.1 Refactor `scripts/deployment/update_ref3_from_csv.py` (Inventory #80)
    - Remove `import mysql.connector`; replace standalone connection and direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 20.2 Refactor `scripts/deployment/update_database_with_urls.py` (Inventory #81)
    - Remove `import mysql.connector`; replace standalone connection and direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 1.3, 3.1, 11.1, 11.3, 11.5_

  - [x] 20.3 Refactor `scripts/deployment/fix_duplicate_rows.py` (Inventory #82)
    - Remove `import mysql.connector`; replace standalone connection and 7× direct `cursor.execute()` with `DatabaseManager` using `transaction()`
    - _Requirements: 1.3, 2.2, 3.1, 11.1, 11.3, 11.5_

  - [x] 20.4 Refactor `scripts/templates/migrate_template_versioning.py` (Inventory #83)
    - Replace `DESCRIBE tenant_template_config` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.6_

  - [x] 20.5 Refactor `scripts/check_template_schema.py` (Inventory #84)
    - Replace `DESCRIBE tenant_template_config` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.6_

- [x] 21. Checkpoint — All script code refactored
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python backend/scripts/check_db_imports.py` to verify zero violations in `backend/scripts/` and `scripts/`

### Phase 4: Refactor Test Code (`backend/tests/`)

- [x] 22. Refactor test configuration and unit test files
  - [x] 22.1 Refactor `backend/tests/conftest.py` (Inventory #85)
    - Remove `import mysql.connector`
    - Import error types from `db_exceptions` instead
    - _Requirements: 1.4, 11.1, 11.4_

  - [x] 22.2 Refactor `backend/tests/unit/test_error_handling_robustness.py` (Inventory #86)
    - Remove `import mysql.connector` and `from mysql.connector import Error as MySQLError`
    - Replace with `from db_exceptions import DatabaseError`
    - _Requirements: 1.4, 7.4, 11.1, 11.4_

  - [x] 22.3 Refactor `backend/tests/unit/test_transaction_logic.py` (Inventory #87)
    - Remove `import mysql.connector`
    - Replace `mysql.connector.Error` in assertions and `side_effect` with `DatabaseError`
    - _Requirements: 1.4, 7.4, 11.1, 11.4_

  - [x] 22.4 Refactor `backend/tests/database/test_database.py` (Inventory #88)
    - Remove `import mysql.connector`
    - Replace `mysql.connector.Error` in assertions and `side_effect` with `DatabaseError`
    - _Requirements: 1.4, 7.4, 11.1, 11.4_

- [x] 23. Refactor database check and integration test files
  - [x] 23.1 Refactor `backend/tests/database/check_mutaties_structure.py` (Inventory #89)
    - Remove `import mysql.connector`; replace standalone `mysql.connector.connect()` with `DatabaseManager`
    - Replace `DESCRIBE mutaties` with `dialect.describe_table('mutaties')`
    - _Requirements: 1.4, 3.3, 6.4, 6.5, 11.1, 11.4, 11.5, 11.6_

  - [x] 23.2 Refactor `backend/tests/database/check_databases.py` (Inventory #90)
    - Remove `import mysql.connector`; replace standalone `mysql.connector.connect()` with `DatabaseManager`
    - _Requirements: 1.4, 3.3, 11.1, 11.4, 11.5_

  - [x] 23.3 Refactor `backend/tests/database/test_vw_bnb_total.py` (Inventory #91)
    - Replace `SHOW FULL TABLES`, `DESCRIBE vw_bnb_total` with dialect helpers
    - Replace direct `cursor.execute()` with `DatabaseManager`
    - _Requirements: 3.3, 6.3, 6.4, 6.5, 11.4, 11.6_

  - [x] 23.4 Refactor `backend/tests/api/test_payout_api.py` (Inventory #92)
    - Replace direct `cursor.execute()` for test setup/teardown with `DatabaseManager`
    - _Requirements: 3.3, 11.4_

  - [x] 23.5 Refactor `backend/tests/integration/test_migration_integration.py` (Inventory #93)
    - Replace 10+ direct `cursor.execute()` calls with `DatabaseManager` using `transaction()`
    - _Requirements: 2.2, 3.3, 11.4_

  - [x] 23.6 Refactor `backend/tests/integration/test_tenant_credentials_table.py` (Inventory #94)
    - Replace `DESCRIBE tenant_credentials` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.4, 11.6_

  - [x] 23.7 Refactor `backend/tests/patterns/test_pattern_storage_complete.py` (Inventory #95)
    - Replace `DESCRIBE {table}` with `dialect.describe_table()`
    - _Requirements: 6.4, 6.5, 11.4, 11.6_

  - [x] 23.8 Refactor `backend/tests/manual/test_railway_connection.py` (Inventory #96)
    - Replace `SHOW FULL TABLES` with `dialect.list_tables()`
    - _Requirements: 6.3, 6.5, 11.4, 11.6_

- [x] 24. Checkpoint — All test code refactored
  - Ensure all tests pass, ask the user if questions arise.
  - Run `python backend/scripts/check_db_imports.py` to verify zero violations in `backend/tests/`

### Phase 5: Validation and Enforcement

- [x] 25. Final validation
  - [x] 25.1 Run CI lint rule to verify zero violations across entire codebase
    - Execute `python backend/scripts/check_db_imports.py`
    - Verify exit code 0 and "No direct mysql.connector imports found outside allowed files" message
    - _Requirements: 1.5, 10.1, 10.2, 11.7_

  - [x] 25.2 Run full test suite for regression verification
    - Execute `pytest backend/tests/ -v` to run all existing tests
    - Verify zero test failures — all existing behavior preserved
    - _Requirements: 9.2, 11.7_

  - [x] 25.3 Verify MySQL 8.0 and 9.4 compatibility
    - Confirm all dialect helpers generate valid MySQL 8.0+ SQL
    - Confirm no MySQL version-specific syntax was introduced
    - _Requirements: 9.3_

- [x] 26. Final checkpoint — Database abstraction layer complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: zero `import mysql.connector` outside allowed files, all 96 files refactored, all property tests passing

## Notes

- All tasks are required — property tests and unit tests are mandatory for this spec
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each phase
- Property tests validate universal correctness properties (7 properties total)
- Unit tests validate specific examples and edge cases
- Every refactored file is independently deployable (Requirement 9.5)
- The inventory numbers (#1-96) map directly to the design document's file-by-file inventory
- Files #7 (`scalability_manager.py`) and #8 (`database.py`) are part of the abstraction layer and are enhanced, not refactored away


