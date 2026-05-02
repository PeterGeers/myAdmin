# Requirements Document

## Introduction

This specification defines the requirements for introducing a database abstraction layer into the myAdmin codebase. Currently, ~45 Python files import `mysql.connector` directly, and 30% of database calls (367 out of ~1,224) bypass the existing `DatabaseManager.execute_query()` abstraction by using raw `cursor.execute()` or creating standalone `mysql.connector.connect()` connections. This tight coupling to MySQL makes the codebase fragile and blocks any future database migration.

The goal is to centralize all database access through `DatabaseManager`, eliminate direct MySQL driver imports from application code, and introduce SQL dialect helpers — making the codebase database-agnostic without changing the underlying MySQL 8.0/9.4 database.

This is **not** a PostgreSQL migration. It is a refactoring effort that improves code quality now and reduces a future migration from a codebase-wide rewrite to a configuration change + schema conversion.

## Glossary

- **DatabaseManager**: The central database access class in `backend/src/database.py` that provides `execute_query()`, `execute_batch_queries()`, `get_connection()`, and `get_cursor()` methods
- **ScalabilityManager**: The advanced connection pooling system in `backend/src/scalability_manager.py` managing up to 50 connections
- **Legacy_Pool**: The fallback `MySQLConnectionPool` with 20 connections used when ScalabilityManager is unavailable
- **Direct_Import**: Any Python file outside `database.py` and `scalability_manager.py` that contains `import mysql.connector`
- **Direct_Cursor_Call**: A `cursor.execute()` call that bypasses `DatabaseManager.execute_query()` by obtaining a raw connection
- **Standalone_Connection**: A `mysql.connector.connect()` call made entirely outside DatabaseManager, creating its own connection configuration
- **Dialect_Helper**: A module that translates database-agnostic function calls into database-specific SQL fragments (e.g., JSON operations, date functions, identifier quoting)
- **Abstraction_Layer**: The combination of DatabaseManager, Dialect_Helper, and connection pooling that isolates all MySQL-specific code from the rest of the application
- **Production_Code**: Python files in `backend/src/` that serve live application requests (routes, services, business logic)
- **Script_Code**: Python files in `backend/scripts/` and root `scripts/` used for migrations, utilities, and maintenance
- **Test_Code**: Python files in `backend/tests/` used for automated testing

## Requirements

### Requirement 1: Centralize Database Driver Imports

**User Story:** As a developer, I want all MySQL driver imports centralized in the database module, so that changing the database driver requires modifying only one file instead of ~45 files.

#### Acceptance Criteria

1. THE Abstraction_Layer SHALL expose all necessary database functionality (connections, cursors, error types, pooling) through `database.py` and `scalability_manager.py` only
2. WHEN a Production_Code file needs database access, THE Production_Code file SHALL import from `database.py` instead of importing `mysql.connector` directly
3. WHEN a Script_Code file needs database access, THE Script_Code file SHALL import from `database.py` or a shared script helper instead of importing `mysql.connector` directly
4. WHEN a Test_Code file needs to mock database errors, THE Test_Code file SHALL import error types from `database.py` instead of importing `mysql.connector.Error` directly
5. IF a file outside the Abstraction_Layer contains `import mysql.connector`, THEN THE build validation SHALL flag the import as a violation

### Requirement 2: Eliminate Direct Cursor Calls in Production Code

**User Story:** As a developer, I want all production database queries routed through DatabaseManager, so that connection management, error handling, and pooling are applied consistently.

#### Acceptance Criteria

1. WHEN Production_Code needs to execute a SQL query, THE Production_Code SHALL use `DatabaseManager.execute_query()` or `DatabaseManager.get_cursor()` context manager
2. WHEN Production_Code needs to execute multiple related queries in a transaction, THE DatabaseManager SHALL provide a transaction context manager that handles commit and rollback
3. THE DatabaseManager SHALL support all query patterns currently used by direct cursor calls: single queries, batch inserts via `executemany`, multi-statement transactions, and queries returning `lastrowid`
4. WHEN Production_Code currently creates a Standalone_Connection via `mysql.connector.connect()`, THE Production_Code SHALL be refactored to use `DatabaseManager.get_connection()` instead
5. IF a Production_Code query fails, THEN THE DatabaseManager SHALL raise a database-agnostic exception that wraps the driver-specific error

### Requirement 3: Eliminate Direct Cursor Calls in Script and Test Code

**User Story:** As a developer, I want migration scripts and tests to use the same database abstraction as production code, so that all database access is consistent and portable.

#### Acceptance Criteria

1. WHEN Script_Code needs database access, THE Script_Code SHALL instantiate DatabaseManager or use a script-oriented helper that delegates to DatabaseManager
2. WHEN Script_Code needs to execute DDL statements (CREATE TABLE, ALTER TABLE, DROP), THE DatabaseManager SHALL support DDL execution with appropriate commit handling
3. WHEN Test_Code needs to set up or tear down test data, THE Test_Code SHALL use DatabaseManager or test fixtures that delegate to DatabaseManager
4. THE DatabaseManager SHALL provide a method for executing raw SQL strings for migration scripts that require database-specific DDL

### Requirement 4: SQL Dialect Helpers for JSON Operations

**User Story:** As a developer, I want database-agnostic helper functions for JSON operations, so that queries using JSON_EXTRACT, JSON_SET, JSON_UNQUOTE, and JSON_CONTAINS work through a portable interface.

#### Acceptance Criteria

1. THE Dialect_Helper SHALL provide a `json_extract(column, path)` function that generates the correct SQL fragment for the configured database (e.g., `JSON_EXTRACT(column, '$.path')` for MySQL)
2. THE Dialect_Helper SHALL provide a `json_unquote_extract(column, path)` function that generates the correct SQL fragment for extracting a JSON value as unquoted text
3. THE Dialect_Helper SHALL provide a `json_set(column, path, value_placeholder)` function that generates the correct SQL fragment for setting a JSON value
4. THE Dialect_Helper SHALL provide a `json_contains(column, value)` function that generates the correct SQL fragment for checking JSON containment
5. WHEN a query in Production_Code uses MySQL-specific JSON functions, THE query SHALL be refactored to use Dialect_Helper functions instead

### Requirement 5: SQL Dialect Helpers for Date and Utility Functions

**User Story:** As a developer, I want database-agnostic helper functions for date operations and common SQL utilities, so that queries using YEAR(), CURDATE(), DATE_SUB(), IFNULL(), and DATE_FORMAT() work through a portable interface.

#### Acceptance Criteria

1. THE Dialect_Helper SHALL provide a `year(column)` function that generates the correct SQL fragment for extracting the year from a date column
2. THE Dialect_Helper SHALL provide a `current_date()` function that generates the correct SQL fragment for the current date
3. THE Dialect_Helper SHALL provide a `date_subtract(date_expr, interval_value, interval_unit)` function that generates the correct SQL fragment for date subtraction
4. THE Dialect_Helper SHALL provide an `ifnull(expr, default)` function that generates the correct SQL fragment for null coalescing
5. THE Dialect_Helper SHALL provide a `date_format(column, format_string)` function that generates the correct SQL fragment for date formatting
6. THE Dialect_Helper SHALL provide a `str_to_date(string_expr, format_string)` function that generates the correct SQL fragment for parsing date strings

### Requirement 6: SQL Dialect Helpers for Identifier Quoting and Introspection

**User Story:** As a developer, I want database-agnostic identifier quoting and schema introspection helpers, so that queries using backtick quoting, SHOW CREATE VIEW, SHOW FULL TABLES, and DESCRIBE work through a portable interface.

#### Acceptance Criteria

1. THE Dialect_Helper SHALL provide a `quote_identifier(name)` function that applies the correct quoting for the configured database (backticks for MySQL, double quotes for PostgreSQL)
2. THE Dialect_Helper SHALL provide a `get_view_definition(view_name)` query generator that returns the SQL to retrieve a view's definition
3. THE Dialect_Helper SHALL provide a `list_tables()` query generator that returns the SQL to list all tables and views in the current database
4. THE Dialect_Helper SHALL provide a `describe_table(table_name)` query generator that returns the SQL to describe a table's columns
5. WHEN Production_Code or Script_Code uses MySQL-specific introspection commands (SHOW CREATE VIEW, SHOW FULL TABLES, DESCRIBE), THE code SHALL be refactored to use Dialect_Helper query generators instead

### Requirement 7: Database-Agnostic Error Handling

**User Story:** As a developer, I want database errors wrapped in a common exception hierarchy, so that error handling code does not depend on MySQL-specific exception classes.

#### Acceptance Criteria

1. THE Abstraction_Layer SHALL define a set of database-agnostic exception classes: `DatabaseError`, `IntegrityError`, `ConnectionError`, and `OperationalError`
2. WHEN the MySQL driver raises `mysql.connector.Error`, THEN THE DatabaseManager SHALL catch the error and re-raise it as the corresponding database-agnostic exception
3. WHEN the MySQL driver raises `mysql.connector.IntegrityError`, THEN THE DatabaseManager SHALL catch the error and re-raise it as `IntegrityError` with the original error code and message preserved
4. WHEN Production_Code catches database exceptions, THE Production_Code SHALL catch the database-agnostic exception classes instead of `mysql.connector.Error`
5. THE database-agnostic exceptions SHALL preserve the original driver exception as a `__cause__` attribute for debugging

### Requirement 8: Connection Pooling Abstraction

**User Story:** As a developer, I want connection pooling managed entirely within the abstraction layer, so that application code does not need to know about ScalabilityManager or MySQLConnectionPool.

#### Acceptance Criteria

1. THE DatabaseManager SHALL manage all connection pooling internally, selecting between ScalabilityManager, Legacy_Pool, and direct connections based on availability
2. WHEN application code needs a database connection, THE application code SHALL call `DatabaseManager.get_connection()` without specifying pool implementation details
3. THE DatabaseManager SHALL continue to support the `pool_type` parameter ('primary', 'readonly', 'analytics') for routing queries to appropriate connection pools
4. WHEN a connection is obtained via `DatabaseManager.get_connection()`, THE connection SHALL be returned to the pool when the context manager exits or when explicitly closed
5. THE Abstraction_Layer SHALL not expose `mysql.connector.pooling` imports to any file outside `database.py` and `scalability_manager.py`

### Requirement 9: Backward Compatibility and Zero Downtime

**User Story:** As a developer, I want the abstraction layer introduced incrementally without breaking existing functionality, so that the application remains fully operational throughout the refactoring.

#### Acceptance Criteria

1. THE Abstraction_Layer SHALL maintain the existing `DatabaseManager` public API (`execute_query`, `execute_batch_queries`, `get_connection`, `get_cursor`) without breaking changes
2. WHEN a file is refactored to use the Abstraction_Layer, THE file's external behavior (API responses, data written, errors raised) SHALL remain identical
3. THE Abstraction_Layer SHALL work with both MySQL 8.0 (local Docker) and MySQL 9.4 (Railway production) without configuration changes
4. WHEN the Abstraction_Layer is deployed, THE existing database schema, data, and views SHALL remain unchanged
5. THE refactoring SHALL be deployable incrementally — each refactored file SHALL be independently deployable without requiring all files to be refactored simultaneously

### Requirement 10: Validation and Enforcement

**User Story:** As a developer, I want automated checks that prevent new direct MySQL imports from being introduced, so that the abstraction layer remains the single point of database access.

#### Acceptance Criteria

1. THE project SHALL include a lint rule or CI check that flags any `import mysql.connector` statement outside the allowed files (`database.py`, `scalability_manager.py`)
2. WHEN a developer adds a new `import mysql.connector` outside the allowed files, THEN THE CI check SHALL fail with a descriptive error message indicating the violation and the correct import path
3. THE allowed files list SHALL be configurable to accommodate future changes to the abstraction layer structure

### Requirement 11: Codebase-Wide Refactoring to Use Abstraction Layer

**User Story:** As a developer, I want all existing code that bypasses the abstraction layer to be identified, validated, and refactored, so that every database call in the codebase goes through DatabaseManager and the dialect helpers.

#### Acceptance Criteria

1. ALL ~45 Python files that currently contain `import mysql.connector` outside `database.py` and `scalability_manager.py` SHALL be refactored to import from the Abstraction_Layer instead
2. ALL 134 direct `cursor.execute()` calls in Production_Code (`backend/src/`) SHALL be refactored to use `DatabaseManager.execute_query()`, `DatabaseManager.get_cursor()` context manager, or the transaction context manager
3. ALL ~145 direct `cursor.execute()` calls in Script_Code (`backend/scripts/` and root `scripts/`) SHALL be refactored to use DatabaseManager or a script-oriented helper
4. ALL ~21 direct `cursor.execute()` calls in Test_Code (`backend/tests/`) SHALL be refactored to use DatabaseManager or test fixtures that delegate to DatabaseManager
5. ALL 44 Standalone_Connection calls (`mysql.connector.connect()` outside DatabaseManager) SHALL be removed and replaced with `DatabaseManager.get_connection()`
6. ALL MySQL-specific SQL functions (JSON_EXTRACT, IFNULL, YEAR, DATE_SUB, CURDATE, DATE_FORMAT, STR_TO_DATE, SHOW CREATE VIEW, DESCRIBE, SHOW FULL TABLES) in Production_Code and Script_Code SHALL be replaced with Dialect_Helper equivalents
7. AFTER refactoring, THE project SHALL pass all existing tests with zero regressions
8. THE design document SHALL include a file-by-file inventory of all files requiring refactoring, grouped by priority (Production_Code first, then Script_Code, then Test_Code)
9. THE tasks document SHALL include explicit refactoring tasks for each file or logical group of files, not a generic "refactor remaining files" task

### Requirement 12: Dialect Helper Round-Trip Consistency

**User Story:** As a developer, I want to verify that dialect helpers produce SQL that is functionally equivalent across supported dialects, so that switching dialects does not change query semantics.

#### Acceptance Criteria

1. FOR ALL valid column names and JSON paths, THE Dialect_Helper `json_extract` output SHALL produce a valid SQL fragment that can be parsed and re-serialized without loss of meaning (round-trip property)
2. FOR ALL valid date format strings, THE Dialect_Helper `date_format` output SHALL produce a valid SQL fragment for the configured dialect
3. FOR ALL valid identifier names, THE Dialect_Helper `quote_identifier` function applied twice SHALL produce the same result as applying it once (idempotence property)
