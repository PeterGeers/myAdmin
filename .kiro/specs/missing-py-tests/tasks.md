# Implementation Plan: Missing Python Backend Tests

## Overview

Systematic addition of test coverage for 50 untested Python backend source files across three priority tiers. Tests are delivered in 6 execution batches, starting with small pure-logic files and progressing to complex integration and API tests. Each batch includes compliance verification via the test maintenance scanner.

## Tasks

- [x] 1. Set up shared API test fixtures
  - [x] 1.1 Enhance `backend/tests/api/conftest.py` with shared fixtures
    - Add `app` fixture creating Flask app with `testing=True`
    - Add `client` fixture wrapping `app.test_client()` with application context
    - Add `mock_auth` fixture patching `auth.cognito_utils.extract_user_credentials` returning TenantAdmin credentials
    - Add `mock_auth_sysadmin` fixture returning SysAdmin credentials
    - Add `mock_sns` fixture patching `boto3.client` for SNS publish calls
    - Ensure fixtures do not duplicate existing fixtures in root `conftest.py`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 2. Batch 1 — Tier 1 pure logic tests (no DB dependency)
  - [x] 2.1 Create `backend/tests/unit/test_country_detector.py`
    - Test `extract_country_from_phone` with valid E.164 numbers for multiple countries
    - Test edge cases: malformed input, empty string, None, numbers without country code
    - Test fallback behavior for unrecognized country codes
    - Use naming pattern `test_{function}_{scenario}_{expected}`
    - _Requirements: 1.7, 2.1, 8.1, 8.5_

  - [x] 2.2 Write property test for country extraction
    - Create `backend/tests/unit/test_country_detector_props.py`
    - **Property 2: Phone Number Country Extraction**
    - Use Hypothesis `st.sampled_from(COUNTRY_CODES)` to generate valid E.164 numbers
    - Verify output is always a valid ISO 3166-1 alpha-2 code or None, never an exception
    - Tag: `Feature: missing-py-tests, Property 2: Phone Number Country Extraction`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.2**

  - [x] 2.3 Create `backend/tests/unit/test_i18n.py`
    - Test `get_locale` with valid Accept-Language headers (nl, en, nl-NL, en-US)
    - Test fallback to `'nl'` when header is missing or empty
    - Test malformed headers, multiple quality values, unsupported locales
    - _Requirements: 1.11, 2.1, 8.1, 8.5_

  - [x] 2.4 Write property test for locale detection totality
    - Create `backend/tests/unit/test_i18n_props.py`
    - **Property 4: Locale Detection Totality**
    - Use Hypothesis `st.text()` to generate arbitrary Accept-Language header values
    - Verify output is always in `{'nl', 'en'}`, never None or unsupported
    - Tag: `Feature: missing-py-tests, Property 4: Locale Detection Totality`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.4**

  - [x] 2.5 Run compliance verification for Batch 1
    - Run `python -m backend.scripts.test_maintenance.scanner` and verify zero violations
    - Run `pytest backend/tests/unit/test_country_detector.py backend/tests/unit/test_i18n.py -v` and verify all pass
    - _Requirements: 9.1, 9.6, 9.7_

- [x] 3. Batch 2 — Tier 1 mocked-DB tests
  - [x] 3.1 Create `backend/tests/unit/test_business_pricing_model.py`
    - Test 7-factor price calculation end-to-end with mocked DB
    - Test each multiplier function in isolation: `_get_historical_multiplier`, `_get_occupancy_multiplier`, `_get_booking_pace_multiplier`, `_get_event_multiplier`
    - Test base rate weekday/weekend logic
    - Test BTW adjustment calculation
    - Test fallback to base rate multiplier of 1.0 when historical data is missing
    - Use `mock_db` fixture for all database interactions
    - _Requirements: 1.1, 2.2, 2.1, 8.5_

  - [x] 3.2 Write property test for pricing multiplier bounds
    - Create `backend/tests/unit/test_business_pricing_model_props.py`
    - **Property 1: Pricing Multiplier Bounds**
    - Use Hypothesis `st.floats(min_value=0.0, max_value=1.0)` for occupancy, `st.dates()` for dates
    - Verify each multiplier output stays within documented bounds (0.5–2.0 standard, 0.0–0.21 BTW)
    - Tag: `Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds`
    - `@settings(max_examples=100, deadline=None)`
    - **Validates: Requirements 3.1**

  - [x] 3.3 Create `backend/tests/unit/test_btw_processor.py`
    - Test VAT account resolution with mocked DB returning account data
    - Test balance calculations for debit/credit totals
    - Test quarter aggregation logic
    - Test report data preparation and formatting
    - Test error case: no VAT accounts found
    - Use `mock_db` fixture for all database interactions
    - _Requirements: 1.3, 2.2, 2.1, 8.5_

  - [x] 3.4 Write property test for BTW balance invariant
    - Create `backend/tests/unit/test_btw_processor_props.py`
    - **Property 5: BTW Debit-Credit Balance Invariant**
    - Use Hypothesis `st.lists(st.fixed_dictionaries({...}))` with balanced debit/credit sets
    - Verify `_calculate_btw_amounts` preserves balance invariant in output
    - Tag: `Feature: missing-py-tests, Property 5: BTW Debit-Credit Balance Invariant`
    - `@settings(max_examples=100, deadline=None)`
    - **Validates: Requirements 3.5**

  - [x] 3.5 Create `backend/tests/unit/test_bnb_cache.py`
    - Test cache TTL logic: fresh data returns cached, expired triggers refresh
    - Test refresh triggers and data filtering
    - Test edge case: expired cache entry returns fresh data after refresh
    - Use `mock_db` fixture and `mock_env` for cache configuration
    - _Requirements: 1.8, 2.2, 2.3, 8.5_

  - [x] 3.6 Run compliance verification for Batch 2
    - Run `python -m backend.scripts.test_maintenance.scanner` and verify zero new violations
    - Run `pytest backend/tests/unit/test_business_pricing_model.py backend/tests/unit/test_btw_processor.py backend/tests/unit/test_bnb_cache.py -v`
    - _Requirements: 9.1, 9.6, 9.7, 9.8_

- [x] 4. Checkpoint — Ensure all Batch 1 and 2 tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Batch 3 — Tier 1 complex tests
  - [x] 5.1 Create `backend/tests/unit/test_security_audit.py`
    - Test input validation rules for various input types
    - Test SQL injection detection with known patterns and edge cases
    - Test XSS check detection
    - Test security scoring calculation
    - Test empty input returns valid result (no injection detected)
    - _Requirements: 1.6, 2.1, 8.5_

  - [x] 5.2 Write property test for SQL injection detection invariance
    - Create `backend/tests/unit/test_security_audit_props.py`
    - **Property 3: SQL Injection Detection Invariance**
    - Use Hypothesis `st.sampled_from(KNOWN_PATTERNS)` combined with `st.text()` for surrounding content
    - Verify detection regardless of surrounding text, casing, or whitespace variations
    - Tag: `Feature: missing-py-tests, Property 3: SQL Injection Detection Invariance`
    - `@settings(max_examples=100)`
    - **Validates: Requirements 3.3**

  - [x] 5.3 Create `backend/tests/unit/test_ai_extractor.py`
    - Test date validation with valid and invalid date formats
    - Test JSON parsing from AI responses (valid JSON, malformed JSON)
    - Test fallback model logic when primary model fails
    - Test data cleaning functions
    - Use `mock_env` for API configuration
    - _Requirements: 1.5, 2.1, 2.3, 8.5_

  - [x] 5.4 Create `backend/tests/unit/test_hybrid_pricing_optimizer.py`
    - Test pricing strategy generation with mocked DB and AI responses
    - Test seasonal multiplier calculations
    - Test event uplift logic
    - Test AI insight parsing (valid and malformed responses)
    - Use `mock_db` and `mock_env` fixtures
    - _Requirements: 1.2, 2.2, 2.3, 8.5_

  - [x] 5.5 Create `backend/tests/unit/test_database_migrations.py`
    - Test migration tracking: recording applied migrations
    - Test version ordering logic
    - Test schema state queries
    - Use `mock_db` fixture for all database interactions
    - _Requirements: 1.9, 2.2, 8.5_

  - [x] 5.6 Create `backend/tests/unit/test_performance_optimizer.py`
    - Test profiling decorator behavior (timing, output)
    - Test memory tracking functionality
    - Test query analysis logic
    - Use `mock_db` fixture where needed
    - _Requirements: 1.10, 2.1, 8.5_

  - [x] 5.7 Create `backend/tests/unit/test_toeristenbelasting_processor.py`
    - Test tourist tax calculation with various rates and periods
    - Test report data preparation
    - Test template rendering output
    - Use `mock_db` fixture for database interactions
    - _Requirements: 1.4, 2.2, 8.5_

  - [x] 5.8 Run compliance verification for Batch 3
    - Run `python -m backend.scripts.test_maintenance.scanner` and verify zero new violations
    - Run all Batch 3 test files with `pytest -v` and verify all pass
    - _Requirements: 9.1, 9.6, 9.7, 9.8_

- [x] 6. Checkpoint — Ensure all Tier 1 tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Verify 80%+ coverage target for each Tier 1 file: `pytest --cov=src/{module} tests/unit/test_{module}.py`
  - _Requirements: 1.12, 10.1, 10.2, 10.3_

- [x] 7. Batch 4 — Tier 2 service integration tests
  - [x] 7.1 Create `backend/tests/integration/test_country_report_service.py`
    - Test report data aggregation with mocked DB
    - Test HTML rendering output
    - Use `mock_db` and `mock_env` fixtures
    - _Requirements: 4.1, 8.2, 8.4_

  - [x] 7.2 Create `backend/tests/integration/test_email_log_service.py`
    - Test email logging (create log entry)
    - Test delivery status updates
    - Test query filtering by tenant, date range, status
    - Use `mock_db` fixture
    - _Requirements: 4.2, 8.2, 8.4_

  - [x] 7.3 Create `backend/tests/integration/test_tenant_language_service.py`
    - Test language preference CRUD operations
    - Test validation of supported languages
    - Use `mock_db` and `mock_cognito` fixtures
    - _Requirements: 4.3, 8.2, 8.4_

  - [x] 7.4 Create `backend/tests/integration/test_tenant_settings_service.py`
    - Test settings JSON management (get, update, merge)
    - Test activity logging on settings changes
    - Use `mock_db` fixture
    - _Requirements: 4.4, 8.2, 8.4_

  - [x] 7.5 Create `backend/tests/integration/test_user_language_service.py`
    - Test Cognito attribute updates for language preference
    - Test language validation against supported set
    - Use `mock_db` and `mock_cognito` fixtures
    - _Requirements: 4.5, 8.2, 8.4_

  - [x] 7.6 Create `backend/tests/integration/test_aws_notifications.py`
    - Test SNS publish with valid message
    - Test error handling when SNS fails
    - Test message formatting for different notification types
    - Use `mock_sns` and `mock_env` fixtures
    - _Requirements: 4.6, 8.2, 8.4_

  - [x] 7.7 Create `backend/tests/integration/test_migrate_revolut_ref2.py`
    - Test data transformation logic
    - Test reference format migration from old to new format
    - Use `mock_db` fixture
    - _Requirements: 4.8, 8.2, 8.4_

  - [x] 7.8 Run compliance verification for Batch 4
    - Run `python -m backend.scripts.test_maintenance.scanner` and verify zero new violations
    - Run all Batch 4 test files with `pytest backend/tests/integration/ -v` and verify all pass
    - _Requirements: 9.1, 9.6, 9.8_

- [x] 8. Batch 5 — Tier 2 route + utility tests
  - [x] 8.1 Create `backend/tests/unit/test_route_validator.py`
    - Test route conflict detection logic
    - Test with overlapping and non-overlapping route patterns
    - _Requirements: 4.7, 8.1, 8.5_

  - [x] 8.2 Create `backend/tests/unit/test_frontend_url.py`
    - Test URL resolution for different environments (dev, staging, production)
    - Test environment-based configuration switching
    - Use `mock_env` fixture
    - _Requirements: 4.9, 8.1, 8.5_

  - [x] 8.3 Create `backend/tests/api/test_admin_routes.py`
    - Test user management endpoints (list, create, update, delete)
    - Test role management endpoints
    - Test permission checks: verify 401/403 for unauthenticated/unauthorized requests
    - Use `client`, `mock_auth`, `mock_auth_sysadmin`, `mock_db` fixtures
    - _Requirements: 5.1, 5.5, 8.3, 8.4_

  - [x] 8.4 Create `backend/tests/api/test_audit_routes.py`
    - Test audit log query endpoint with filters
    - Test report generation endpoint
    - Test authentication enforcement (401/403)
    - Use `client`, `mock_auth`, `mock_db` fixtures
    - _Requirements: 5.2, 5.5, 8.3, 8.4_

  - [x] 8.5 Create `backend/tests/api/test_scalability_routes.py`
    - Test monitoring endpoints return expected metrics
    - Test authentication enforcement
    - Use `client`, `mock_auth_sysadmin`, `mock_db` fixtures
    - _Requirements: 5.3, 5.5, 8.3, 8.4_

  - [x] 8.6 Create `backend/tests/api/test_tenant_module_routes.py`
    - Test module access control endpoints
    - Test that unauthorized tenants cannot access restricted modules
    - Use `client`, `mock_auth`, `mock_db` fixtures
    - _Requirements: 5.4, 5.5, 8.3, 8.4_

  - [x] 8.7 Run compliance verification for Batch 5
    - Run `python -m backend.scripts.test_maintenance.scanner` and verify zero new violations
    - Run Batch 5 test files and verify all pass
    - _Requirements: 9.1, 9.6, 9.8_

- [x] 9. Checkpoint — Ensure all Tier 2 tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Verify 60%+ coverage target for each Tier 2 file
  - _Requirements: 4.10, 10.4_

- [x] 10. Batch 6 — Tier 3 route tests (batched by module)
  - [x] 10.1 Create `backend/tests/api/test_tax_routes.py`
    - Test BTW report generation endpoint (POST with valid payload)
    - Test tourist tax endpoint flows
    - Test authentication enforcement (401/403 without valid auth)
    - Test input validation (missing required fields)
    - Use `client`, `mock_auth`, `mock_db` fixtures
    - _Requirements: 6.1, 6.2, 6.3, 8.3_

  - [x] 10.2 Create `backend/tests/api/test_invoice_routes.py`
    - Test upload flow endpoint
    - Test duplicate detection endpoint
    - Test authentication enforcement
    - Use `client`, `mock_auth`, `mock_db`, `mock_google_drive` fixtures
    - _Requirements: 6.1, 6.2, 6.4, 8.3_

  - [x] 10.3 Create `backend/tests/api/test_auth_routes.py`
    - Test forgot-password flow endpoint
    - Test code validation endpoint
    - Test authentication enforcement where applicable
    - Use `client`, `mock_cognito`, `mock_env` fixtures
    - _Requirements: 6.1, 6.2, 6.5, 8.3_

  - [x] 10.4 Create Tier 3 sysadmin route tests
    - Create `backend/tests/api/test_sysadmin_health.py` — health check endpoints, auth enforcement
    - Create `backend/tests/api/test_sysadmin_roles.py` — role management, auth enforcement
    - Create `backend/tests/api/test_system_health_routes.py` — health/monitoring endpoints
    - Use `client`, `mock_auth_sysadmin`, `mock_db` fixtures
    - _Requirements: 6.1, 6.2, 8.3_

  - [x] 10.5 Create Tier 3 tenant admin route tests
    - Create `backend/tests/api/test_tenant_admin_config.py` — config CRUD, auth enforcement
    - Create `backend/tests/api/test_tenant_admin_credentials.py` — credential operations, auth enforcement
    - Create `backend/tests/api/test_tenant_admin_details.py` — tenant details CRUD, auth enforcement
    - Create `backend/tests/api/test_tenant_admin_email.py` — email sending, auth enforcement
    - Create `backend/tests/api/test_tenant_admin_settings.py` — settings CRUD, auth enforcement
    - Create `backend/tests/api/test_tenant_admin_storage.py` — storage config, auth enforcement
    - Use `client`, `mock_auth`, `mock_db` fixtures
    - _Requirements: 6.1, 6.2, 8.3_

  - [x] 10.6 Create remaining Tier 3 route tests
    - Create `backend/tests/api/test_chart_of_accounts_routes.py` — CRUD endpoints, auth enforcement
    - Create `backend/tests/api/test_duplicate_detection_routes.py` — detection endpoints, auth enforcement
    - Create `backend/tests/api/test_email_log_routes.py` — query endpoints, webhook, auth enforcement
    - Create `backend/tests/api/test_folder_routes.py` — Google Drive folder operations, auth enforcement
    - Create `backend/tests/api/test_missing_invoices_routes.py` — transaction retrieval, auth enforcement
    - Create `backend/tests/api/test_pdf_validation_routes.py` — validation endpoints, auth enforcement
    - Create `backend/tests/api/test_user_routes.py` — user preferences, auth enforcement
    - Create `backend/tests/api/test_year_end_config_routes.py` — year-end config, auth enforcement
    - Create `backend/tests/api/test_asset_routes.py` — asset CRUD, auth enforcement
    - Use `client`, `mock_auth`, `mock_db` fixtures
    - _Requirements: 6.1, 6.2, 8.3_

  - [x] 10.7 Create Tier 3 smoke tests
    - Create `backend/tests/api/test_config_routes.py` — config loads and serves
    - Create `backend/tests/api/test_migration_routes.py` — endpoints register and respond
    - Create `backend/tests/api/test_static_routes.py` — static files serve
    - Create `backend/tests/api/test_api_schemas.py` — schema validation works
    - Create `backend/tests/api/test_sysadmin_helpers.py` — helper functions (unit-level in api dir or unit dir as appropriate)
    - Use `client`, `mock_auth` fixtures
    - _Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 8.3_

  - [x] 10.8 Run compliance verification for Batch 6
    - Run `python -m backend.scripts.test_maintenance.scanner` and verify zero new violations
    - Run all Batch 6 test files with `pytest backend/tests/api/ -v` and verify all pass
    - _Requirements: 9.1, 9.6, 9.8_

- [x] 11. Final checkpoint — Full suite verification
  - Run full test suite: `pytest backend/tests/unit/ backend/tests/integration/ backend/tests/api/ -v`
  - Verify no shared state conflicts between test modules
  - Verify no test execution order dependencies
  - Run final compliance scan: `python -m backend.scripts.test_maintenance.scanner`
  - Verify coverage targets: Tier 1 ≥ 80%, Tier 2 ≥ 60%, Tier 3 ≥ 40%
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 9.1, 9.2, 9.4, 9.6, 9.8, 10.5_

## Notes

- All tasks are required (no optional tasks)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each tier
- Property tests validate the 5 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All test files must comply with anti-patterns: no direct `mysql.connector` imports, no `os.environ` without `patch.dict`, no `load_dotenv()`, no `sys.path` manipulation, no imports from other test files
- Test naming convention: `test_{function}_{scenario}_{expected}`
- Compliance verification after each batch using `python -m backend.scripts.test_maintenance.scanner`

- **Pre-existing issue**: `services/signup_service.py` imports `mysql.connector` directly instead of using `DatabaseManager`. This causes `test_signup_routes.py` to fail because it patches `services.signup_service.mysql.connector` which no longer resolves correctly. The signup service should be refactored to use the database abstraction layer (`DatabaseManager`), and its tests updated accordingly. This is out of scope for this spec.
