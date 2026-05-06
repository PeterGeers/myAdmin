# Requirements Document

## Introduction

This specification covers the addition of missing Python backend tests for 50 source files that currently lack test coverage. The files are classified into three priority tiers based on their business criticality and complexity. The goal is to establish comprehensive test coverage across the backend codebase using pytest with appropriate markers (unit, integration, api) and the existing fixture infrastructure.

## Glossary

- **Test_Suite**: The complete collection of pytest test files under `backend/tests/`
- **Unit_Test**: A fast, isolated test that mocks all external dependencies (database, AWS, APIs)
- **Integration_Test**: A test that verifies interaction between multiple components with mocked external services
- **API_Test**: A test that exercises Flask route endpoints via the test client with mocked authentication
- **Smoke_Test**: A minimal test verifying that a module loads and basic endpoints respond
- **Connection_Guard**: The autouse fixture in `tests/unit/conftest.py` that prevents real database connections in unit tests
- **Mock_DB**: The shared `DatabaseManager` mock fixture providing configurable return values
- **Coverage_Target**: The minimum percentage of lines exercised by tests for a given file
- **Tier_1_File**: A source file containing core business logic (calculations, transformations, security) requiring 80%+ coverage
- **Tier_2_File**: A source file containing service logic or non-trivial route handlers requiring 60%+ coverage
- **Tier_3_File**: A source file primarily delegating to services, requiring 40%+ coverage via API/smoke tests
- **Flask_Test_Client**: The `app.test_client()` instance used for API-level testing without a running server
- **PBT**: Property-Based Testing using the Hypothesis library to generate randomized inputs

## Requirements

### Requirement 1: Tier 1 Unit Tests for Business Logic Files

**User Story:** As a developer, I want comprehensive unit tests for the 11 high-priority business logic files, so that core calculations, transformations, and security checks are verified and regressions are caught early.

#### Acceptance Criteria

1. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `business_pricing_model.py` covering the 7-factor price calculation, each multiplier function, base rate weekday/weekend logic, and BTW adjustment
2. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `hybrid_pricing_optimizer.py` covering pricing strategy generation, seasonal multipliers, event uplifts, and AI insight parsing
3. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `btw_processor.py` covering VAT account resolution, balance calculations, quarter aggregation, and report data preparation
4. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `toeristenbelasting_processor.py` covering tourist tax calculation, report data preparation, and template rendering
5. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `ai_extractor.py` covering date validation, JSON parsing, fallback model logic, and data cleaning
6. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `security_audit.py` covering input validation rules, SQL injection detection, XSS checks, and security scoring
7. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `country_detector.py` covering phone number parsing, country code extraction, and edge cases for malformed input
8. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `bnb_cache.py` covering cache TTL logic, refresh triggers, and data filtering
9. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `database_migrations.py` covering migration tracking, version ordering, and schema state queries
10. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `performance_optimizer.py` covering the profiling decorator, memory tracking, and query analysis
11. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `i18n.py` covering locale detection from Accept-Language header and fallback locale behavior
12. THE Test_Suite SHALL achieve a minimum of 80% line coverage for each Tier_1_File

### Requirement 2: Tier 1 Tests Use Existing Fixture Infrastructure

**User Story:** As a developer, I want Tier 1 tests to use the existing mock fixtures and connection guard, so that tests remain fast, isolated, and consistent with the project's testing patterns.

#### Acceptance Criteria

1. THE Test_Suite SHALL place all Tier 1 test files under `backend/tests/unit/` to activate the Connection_Guard
2. WHEN a Tier 1 test requires database access, THE Test_Suite SHALL use the Mock_DB fixture from `conftest.py`
3. WHEN a Tier 1 test requires environment variables, THE Test_Suite SHALL use the `mock_env` fixture
4. WHEN a Tier 1 test requires AWS Cognito calls, THE Test_Suite SHALL use the `mock_cognito` fixture
5. IF a Tier 1 unit test attempts a real database connection, THEN THE Connection_Guard SHALL raise a RuntimeError

### Requirement 3: Property-Based Tests for Pure Logic Functions

**User Story:** As a developer, I want property-based tests for pure calculation and transformation functions, so that edge cases are discovered through randomized input generation.

#### Acceptance Criteria

1. WHEN testing `business_pricing_model.py` multiplier functions, THE Test_Suite SHALL include a property test verifying that each multiplier output stays within its documented bounds for all valid inputs
2. WHEN testing `country_detector.py`, THE Test_Suite SHALL include a property test verifying that valid E.164 phone numbers produce a recognized country code or a defined fallback
3. WHEN testing `security_audit.py` input validation, THE Test_Suite SHALL include a property test verifying that known SQL injection patterns are detected regardless of surrounding text
4. WHEN testing `i18n.py` locale detection, THE Test_Suite SHALL include a property test verifying that any well-formed Accept-Language header produces a valid locale from the supported set
5. WHEN testing `btw_processor.py` balance calculations, THE Test_Suite SHALL include a property test verifying that debit and credit totals balance (sum of debits equals sum of credits for a closed period)

### Requirement 4: Tier 2 Integration Tests for Services

**User Story:** As a developer, I want integration tests for the 13 medium-priority service and processor files, so that component interactions and data flows are verified.

#### Acceptance Criteria

1. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `country_report_service.py` covering report data aggregation and HTML rendering
2. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `email_log_service.py` covering email logging, delivery status updates, and query filtering
3. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `tenant_language_service.py` covering language preference CRUD and validation
4. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `tenant_settings_service.py` covering settings JSON management and activity logging
5. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `user_language_service.py` covering Cognito attribute updates and language validation
6. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `aws_notifications.py` covering SNS publish, error handling, and message formatting
7. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `route_validator.py` covering route conflict detection logic
8. WHEN a test run is executed with the `integration` marker, THE Test_Suite SHALL include tests for `migrate_revolut_ref2.py` covering data transformation and reference format migration
9. WHEN a test run is executed with the `unit` marker, THE Test_Suite SHALL include tests for `utils/frontend_url.py` covering URL resolution and environment-based configuration
10. THE Test_Suite SHALL achieve a minimum of 60% line coverage for each Tier_2_File

### Requirement 5: Tier 2 API Tests for Route Handlers with Logic

**User Story:** As a developer, I want API tests for route handlers that contain non-trivial logic beyond simple delegation, so that endpoint behavior, authentication, and error handling are verified.

#### Acceptance Criteria

1. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `admin_routes.py` covering user/role management endpoints and permission checks
2. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `audit_routes.py` covering audit log query, filtering, and report generation
3. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `scalability_routes.py` covering monitoring endpoints and metrics retrieval
4. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `tenant_module_routes.py` covering module access control
5. WHEN an API test sends a request without valid authentication, THE Test_Suite SHALL verify that the endpoint returns a 401 or 403 status code

### Requirement 6: Tier 3 API and Smoke Tests for Route Delegation Files

**User Story:** As a developer, I want API-level and smoke tests for the 26 lower-priority route files, so that endpoint registration, authentication enforcement, and basic request/response flow are verified.

#### Acceptance Criteria

1. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for each Tier_3_File route module verifying that registered endpoints respond with expected status codes for valid requests
2. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL verify that each Tier_3_File route module rejects unauthenticated requests with 401 or 403 status codes
3. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `routes/tax_routes.py` covering BTW and tourist tax endpoint flows
4. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `routes/invoice_routes.py` covering upload flow and duplicate detection
5. WHEN a test run is executed with the `api` marker, THE Test_Suite SHALL include tests for `routes/auth_routes.py` covering forgot-password flow and code validation
6. THE Test_Suite SHALL achieve a minimum of 40% line coverage for each Tier_3_File
7. THE Test_Suite SHALL focus Tier 3 tests on authentication enforcement, input validation, and error handling behavior rather than Flask route wiring or simple delegation to services
8. THE Test_Suite SHALL NOT test third-party library internals or simple getters/setters in Tier 3 files

### Requirement 7: Shared Test Fixtures for New Tests

**User Story:** As a developer, I want shared fixtures for Flask test client and mock authentication, so that API and integration tests have consistent setup without duplication.

#### Acceptance Criteria

1. THE Test_Suite SHALL provide a `client` fixture that creates a Flask test client with application context
2. THE Test_Suite SHALL provide a `mock_auth` fixture that generates valid authentication headers for API tests
3. THE Test_Suite SHALL provide a `mock_sns` fixture that mocks AWS SNS publish calls for notification tests
4. WHEN a new fixture is added, THE Test_Suite SHALL place the fixture in the appropriate `conftest.py` file based on test directory scope
5. THE Test_Suite SHALL reuse existing fixtures (`mock_db`, `mock_env`, `mock_cognito`, `mock_google_drive`) where applicable rather than creating duplicates

### Requirement 8: Test Organization and Naming Conventions

**User Story:** As a developer, I want tests organized by type in the correct directories with consistent naming, so that test discovery, filtering by marker, and maintenance are straightforward.

#### Acceptance Criteria

1. THE Test*Suite SHALL place unit tests in `backend/tests/unit/` with filenames matching `test*{source_module}.py`
2. THE Test*Suite SHALL place integration tests in `backend/tests/integration/` with filenames matching `test*{source_module}.py`
3. THE Test*Suite SHALL place API tests in `backend/tests/api/` with filenames matching `test*{source_module}.py`
4. WHEN a test file is created, THE Test_Suite SHALL include the appropriate `@pytest.mark` decorator matching its directory location
5. THE Test*Suite SHALL use descriptive test function names following the pattern `test*{function}_{scenario}_{expected}`(e.g.,`test_process_transaction_valid_csv_returns_success`)
6. THE Test_Suite SHALL use the modern fixture set (`mock_db`, `mock_env`, `mock_cognito`, `mock_google_drive`) and SHALL NOT use legacy fixtures (`mock_database`, `test_environment`, `production_environment`) in new test files

### Requirement 9: Test Execution, CI Compatibility, and Compliance

**User Story:** As a developer, I want all new tests to pass in isolation and in the full test suite, and to comply with the project's test compliance rules, so that CI pipelines remain green and tests follow established conventions.

#### Acceptance Criteria

1. WHEN the full test suite is executed with `pytest backend/tests/unit/`, THE Test_Suite SHALL complete without failures for all new unit tests
2. WHEN tests are executed in parallel, THE Test_Suite SHALL not produce shared state conflicts between test modules
3. IF a test requires specific environment state, THEN THE Test_Suite SHALL set up and tear down that state within the test or fixture scope
4. THE Test_Suite SHALL not introduce dependencies on test execution order
5. WHEN a new test file is added, THE Test_Suite SHALL ensure it does not import from other test files (only from conftest fixtures and source modules)
6. WHEN the compliance checker is run against new test files, THE Test_Suite SHALL produce zero violations against the rules defined in `backend/tests/test-compliance-rules.json`
7. THE Test_Suite SHALL NOT contain direct `mysql.connector` imports, direct `os.environ` access without `patch.dict`, `DatabaseManager(test_mode=True)` without mocking, `load_dotenv()` calls, or `sys.path` manipulation in unit test files
8. WHEN the test maintenance scanner is run after test creation, THE Test_Suite SHALL not introduce new mock violations or compliance failures

### Requirement 10: Incremental Delivery by Execution Order

**User Story:** As a developer, I want tests delivered in a specific execution order starting with small pure-logic files, so that I can review and merge incrementally without blocking on the full scope.

#### Acceptance Criteria

1. THE Test_Suite SHALL deliver Tier 1 pure logic tests first: `country_detector.py`, `i18n.py` (small files, no database dependency)
2. WHEN Tier 1 pure logic tests are complete, THE Test_Suite SHALL deliver Tier 1 mocked-DB tests: `business_pricing_model.py`, `btw_processor.py`, `bnb_cache.py`
3. WHEN Tier 1 mocked-DB tests are complete, THE Test_Suite SHALL deliver Tier 1 complex tests: `security_audit.py`, `ai_extractor.py`, `hybrid_pricing_optimizer.py`, `database_migrations.py`, `performance_optimizer.py`, `toeristenbelasting_processor.py`
4. WHEN Tier 1 tests are complete, THE Test_Suite SHALL deliver Tier 2 service tests followed by Tier 2 utility and route tests
5. WHEN Tier 2 tests are complete, THE Test_Suite SHALL deliver Tier 3 route tests batched by module (tax, invoices, auth, sysadmin, tenant_admin)
