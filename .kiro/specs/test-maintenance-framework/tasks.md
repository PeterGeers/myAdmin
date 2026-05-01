# Implementation Plan: Test Maintenance Framework

## Overview

This plan implements the Test Maintenance Framework in 6 phases, prioritized by ROI. Phase 1 delivers immediate value by fixing the root causes of test instability (real DB connections in unit tests, broken fixtures, .env loading). Later phases build detection tooling, drift prevention, tracking, and reporting on top of that foundation.

All tools are Python modules in `backend/scripts/test_maintenance/`. All property-based tests use Hypothesis. All test files go in `backend/tests/unit/test_maintenance/`.

## Tasks

- [x] 1. Phase 1 — Unit test isolation and enhanced fixtures (highest value)
  - [x] 1.1 Create `backend/tests/unit/conftest.py` with `block_real_connections` autouse fixture
    - Implement the connection guard that patches `mysql.connector.connect` with a `RuntimeError` side effect
    - The fixture must be `autouse=True` so every unit test is protected automatically
    - _Requirements: 4.4_

  - [x] 1.2 Write property test for connection guard (Property 8)
    - **Property 8: Unit test connection guard**
    - Verify that for any call parameters to `mysql.connector.connect`, the guard raises `RuntimeError`
    - File: `backend/tests/unit/test_maintenance/test_isolation_layer_props.py`
    - **Validates: Requirements 4.4**

  - [x] 1.3 Fix `backend/tests/conftest.py` to stop loading real `.env` files
    - Remove `from dotenv import load_dotenv` and `load_dotenv(...)` call
    - Keep the `sys.path` setup for imports
    - Preserve all existing fixtures (`temp_dir`, `temp_file`, `mock_database`, `mock_google_drive`, `test_environment`, `production_environment`, `sample_*` fixtures)
    - Preserve `pytest_configure` and `pytest_collection_modifyitems` hooks
    - _Requirements: 4.6_

  - [x] 1.4 Add `mock_db` fixture to `backend/tests/conftest.py`
    - Patch `database.DatabaseManager` class (not `mysql.connector.connect`)
    - Mock `execute_query`, `execute_batch_queries`, `transaction`, `get_cursor` with configurable returns
    - Set up `transaction` and `get_cursor` as proper context managers returning `(mock_cursor, mock_conn)`
    - _Requirements: 4.1, 4.5_

  - [x] 1.5 Write property test for mock_db fixture (Property 9)
    - **Property 9: mock_db fixture method coverage**
    - Verify that for any sequence of DatabaseManager method calls with arbitrary parameters, mock_db handles all without unexpected exceptions
    - File: `backend/tests/unit/test_maintenance/test_isolation_layer_props.py`
    - **Validates: Requirements 4.1**

  - [x] 1.6 Add `mock_env` fixture to `backend/tests/conftest.py`
    - Use `patch.dict(os.environ, test_env, clear=False)` with standard test variables
    - Must NOT call `load_dotenv()` — provides hardcoded test values only
    - Include: `TEST_MODE`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `GOOGLE_DRIVE_FOLDER_ID`, `AWS_REGION`, `FLASK_ENV`
    - _Requirements: 4.6_

  - [x] 1.7 Add `mock_cognito` fixture to `backend/tests/conftest.py`
    - Patch `auth.cognito_utils.boto3.client` to return a mock Cognito client
    - Provide default `admin_get_user` response with test user attributes
    - _Requirements: 4.2_

  - [x] 1.8 Add `mock_google_drive` fixture to `backend/tests/conftest.py`
    - Patch `google_drive_service.build` to return a mock Drive service
    - Provide default `files().list()` and `files().get()` responses
    - Note: existing `mock_google_drive` fixture uses bare `Mock()` without patching — replace it with proper `patch` version
    - _Requirements: 4.3_

  - [x] 1.9 Write unit tests for all new fixtures
    - Test that `mock_db` returns expected defaults and accepts custom return values
    - Test that `mock_env` sets all expected environment variables
    - Test that `mock_cognito` returns expected user attributes
    - Test that `mock_google_drive` returns expected file responses
    - File: `backend/tests/unit/test_maintenance/test_isolation_layer.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.6_

- [x] 2. Checkpoint — Verify Phase 1
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/tests/unit/test_maintenance/ -v` to verify new tests
  - Run a sample of existing unit tests to confirm the connection guard and fixture changes don't break them

- [x] 3. Phase 1.5 — Fix broken unit tests using new isolation layer
  - [x] 3.1 Fix `test_audit_logger.py` — replace real DB with mock_db
    - Remove `setup_test_table` fixture that creates real database tables
    - Replace `DatabaseManager(test_mode=True)` with `mock_db` fixture
    - Update all 11 failing tests to use mocked `execute_query` return values instead of real queries
    - Fix `AuditLogger` instantiation to accept a mocked DatabaseManager
    - Failures: `test_log_continue_decision`, `test_log_cancel_decision`, `test_log_decision_minimal_data`, `test_query_by_reference_number`, `test_query_by_date_range`, `test_query_by_decision_type`, `test_get_decision_count`, `test_generate_compliance_report`, `test_get_user_activity_report`, `test_cleanup_old_logs`, `test_get_audit_trail_for_transaction`

  - [x] 3.2 Fix `test_banking_processor.py` — replace ad-hoc mocks with shared fixtures
    - Replace local `mock_connection` fixture with `mock_db` from conftest
    - Fix `test_save_approved_transactions_success` and `test_save_approved_transactions_error` — currently hit real DB (`Access denied for user 'peter'`)
    - Fix `test_check_banking_accounts` and `test_check_banking_accounts_with_end_date` — `KeyError: 'Account'` indicates mock return values don't match current code; update mock data to match actual column names
    - Fix `test_check_sequence_numbers_invalid_sequence` — assertion `0 == 1` indicates mock setup doesn't return expected data
    - Failures: 6 tests total

  - [x] 3.3 Fix `test_year_end_service.py` — update mock return values to match current signatures
    - All 8 failures are `KeyError: 'first_date'` — the service now returns different keys than what mocks provide
    - Read current `year_end_service.py` to identify actual return value structure
    - Update mock `execute_query` return values in all fixtures to match current dict keys
    - Fix `test_close_year_rollback_on_error` — regex pattern mismatch in expected exception message
    - Failures: `test_validate_year_previous_not_closed`, `test_validate_year_missing_configuration`, `test_validate_year_success`, `test_validate_year_zero_result_warning`, `test_get_first_year`, `test_get_first_year_no_data`, `test_close_year_success`, `test_close_year_rollback_on_error`

  - [x] 3.4 Fix `test_create_initial_admin_user.py` — fix route registration
    - All 3 failures return `404` instead of `200` — the route endpoint has been moved or renamed
    - Read current route registration to find correct URL path
    - Update test client calls to use the correct endpoint
    - Failures: `test_happy_path_resend`, `test_creates_cognito_user_if_not_exists`, `test_creates_tenant_admin_role_if_not_exists`

  - [x] 3.5 Fix `test_toeristenbelasting_generator.py` — update expected values
    - `test_get_tourist_tax_from_account` and `test_get_financial_data` both assert `25.47 < 0.01` — the calculation logic or test data has changed
    - Read current `toeristenbelasting_generator.py` to understand actual calculation
    - Update mock data or expected values to match current business logic
    - Failures: 2 tests

  - [x] 3.6 Fix `test_pivot_service.py` — update expected return format
    - `test_get_available_columns_no_tenant_restriction` and `test_get_available_columns_with_tenant_restriction` — service now returns `[{'label': ..., 'type': ...}]` dicts instead of plain string lists
    - Update test assertions to expect the new dict format
    - Failures: 2 tests

  - [x] 3.7 Fix `test_storage_provider.py` — mock S3 configuration
    - `test_defaults_to_google_drive` fails with `ValueError: S3 shared bucket not configured`
    - The factory now requires S3 config even when defaulting to Google Drive — use `mock_env` to provide S3 config or mock the config check
    - Failures: 1 test

  - [x] 3.8 Fix `test_xlsx_export.py` — fix path comparison
    - `test_init` has path string comparison issue (Windows path normalization)
    - Use `os.path.normpath()` or `pathlib.Path` for platform-independent comparison
    - Failures: 1 test

  - [x] 3.9 Fix `test_module_registry.py` — update mock return value
    - `test_seeds_str_params_skips_none_defaults` — `assert 0 is None` indicates the function now returns `0` instead of `None`
    - Read current `module_registry.py` to verify expected behavior and update assertion
    - Failures: 1 test

  - [x] 3.10 Fix `test_duplicate_load.py` — mock caching layer
    - `test_optimized_query_performance` — "No cache hits detected" means the caching layer isn't mocked
    - `test_sustained_load` — "No successful requests" means the test setup doesn't provide working mocks
    - These are load/performance tests that need proper mock infrastructure; consider re-marking as `@pytest.mark.integration` if they require real infrastructure
    - Failures: 2 tests

  - [x] 3.11 Fix `test_parameter_service_props.py` — resolve Hypothesis flakiness
    - `test_delete_user_falls_back_to_role` — `hypothesis.errors.Flaky` indicates non-deterministic behavior
    - Investigate whether the test or the service has side effects causing flakiness
    - Fix the underlying non-determinism or add `@settings(derandomize=True)` as a temporary measure
    - Failures: 1 test

- [x] 4. Checkpoint — Verify Phase 1.5
  - Run `pytest backend/tests/unit/ -v` to verify all previously broken tests now pass
  - Confirm total failure count is reduced from 40+ to 0 (or near-zero with documented exceptions)
  - Any tests that cannot be fixed should be documented with a reason and marked with `@pytest.mark.skip(reason="...")`

- [x] 5. Phase 2 — Dependency mapper and scoped test runner (high value)
  - [x] 5.1 Create `backend/scripts/test_maintenance/__init__.py` package
    - Create the package directory and `__init__.py`
    - _Requirements: 1.1_

  - [x] 5.2 Implement `import_analyzer.py` — Python import parsing via AST
    - Parse Python files using `ast` module to extract all `import` and `from ... import` statements
    - Resolve relative imports to absolute module paths
    - Return structured list of imported modules per file
    - _Requirements: 2.3_

  - [x] 5.3 Implement `dependency_mapper.py` — source-to-test mapping
    - Implement `DependencyMapper` class with `build_backend_map()` and `build_frontend_map()`
    - Use naming convention matching (`test_{module}.py`) as primary strategy
    - Use import analysis (via `import_analyzer.py`) as secondary strategy
    - Support frontend co-location patterns (`Component.test.tsx`, `__tests__/Component.test.tsx`)
    - Implement `get_tests_for_files()` for scoped test selection
    - Implement `get_untested_sources()` to find source files with no tests
    - Implement `save_map()` to persist as JSON
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 5.4 Write property test for dependency mapping completeness (Property 4)
    - **Property 4: Dependency mapping completeness**
    - For any file layout, every source file appears in either the mapped set or the untested set, never both, never neither
    - File: `backend/tests/unit/test_maintenance/test_dependency_mapper_props.py`
    - **Validates: Requirements 2.1, 2.2, 6.5**

  - [x] 5.5 Write property test for import-based mapping (Property 5)
    - **Property 5: Import-based dependency mapping**
    - For any test file with an import referencing a source module, the mapper includes that test in the mapping
    - File: `backend/tests/unit/test_maintenance/test_dependency_mapper_props.py`
    - **Validates: Requirements 2.3**

  - [x] 5.6 Write property test for frontend co-location mapping (Property 6)
    - **Property 6: Frontend co-location mapping**
    - For any frontend source file with a co-located test, the mapper maps source to test
    - File: `backend/tests/unit/test_maintenance/test_dependency_mapper_props.py`
    - **Validates: Requirements 2.4**

  - [x] 5.7 Implement `scoped_runner.py` — change-based test selection
    - Implement `ScopedTestRunner` class that loads dependency map JSON
    - Implement `run()` method that selects tests for changed files and executes via subprocess
    - Support `--full` flag for complete suite execution
    - Support `--git-diff` flag to auto-detect changes from git
    - Implement fallback: if dependency map missing, run all tests in changed file's directory
    - Backend: invoke `pytest` with specific test file paths
    - Frontend: invoke `vitest --related` with changed source files
    - Add CLI interface via `__main__` block
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.8 Write property test for scoped test selection (Property 7)
    - **Property 7: Scoped test selection correctness**
    - For any dependency map and changed files, selected tests equal the union of mapped tests, and unmapped changes appear in untested_changes
    - File: `backend/tests/unit/test_maintenance/test_scoped_runner_props.py`
    - **Validates: Requirements 3.1, 3.3, 6.1**

  - [x] 5.9 Write unit tests for dependency mapper and scoped runner
    - Test naming convention matching with real project file patterns
    - Test import analysis with sample Python files
    - Test frontend co-location with sample TypeScript files
    - Test CLI argument parsing for scoped runner
    - Test fallback behavior when dependency map is missing
    - Files: `backend/tests/unit/test_maintenance/test_dependency_mapper.py`, `backend/tests/unit/test_maintenance/test_scoped_runner.py`
    - _Requirements: 2.1, 2.3, 2.4, 3.1, 3.5_

- [x] 6. Checkpoint — Verify Phase 2
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/tests/unit/test_maintenance/ -v` to verify all tests

- [x] 7. Phase 3 — Mock violation detector, compliance checker, and scanner orchestrator (detection tooling)
  - [x] 7.1 Implement `mock_violation_detector.py` — AST-based scanning
    - Implement `MockViolationDetector` class with `analyze_file()` method
    - Implement `detect_db_imports()` — flag direct `mysql.connector` imports in unit tests
    - Implement `detect_env_leaks()` — flag `os.environ` access to real DB names without `patch.dict`
    - Implement `detect_real_connections()` — flag `DatabaseManager(test_mode=True)` without mock
    - Return `MockViolation` dataclass with `file_path`, `line_number`, `violation_type`, `severity`, `description`, `suggested_fix`
    - Use Python `ast` module for import detection, regex for string pattern matching
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 7.2 Write property test for mock violation detection (Property 1)
    - **Property 1: Mock violation detection accuracy**
    - For any test file content with zero or more violations, the detector correctly identifies all violations and produces no false positives for properly mocked code
    - File: `backend/tests/unit/test_maintenance/test_mock_violation_detector_props.py`
    - **Validates: Requirements 1.2, 1.3, 11.1**

  - [x] 7.3 Write property test for issue completeness (Property 2)
    - **Property 2: Issue completeness invariant**
    - For any detected issue, it has a valid severity and all required fields
    - File: `backend/tests/unit/test_maintenance/test_mock_violation_detector_props.py`
    - **Validates: Requirements 1.4, 11.6**

  - [x] 7.4 Create `backend/tests/test-compliance-rules.json`
    - Define backend_unit rules: `use_shared_mock_db`, `pytest_marker_required`, `no_sys_path_manipulation`, `use_mock_env`, `no_real_db_in_unit`
    - Define frontend_unit rules: `use_test_utils_render`, `use_msw_for_api`
    - Define backend_route rules: `blueprint_naming`
    - Categorize as required, recommended, or forbidden
    - _Requirements: 11.7_

  - [x] 7.5 Implement `compliance_checker.py` — configurable rule engine
    - Implement `ComplianceChecker` class that loads rules from JSON
    - Implement `check_backend_test()` — check against backend_unit rules
    - Implement `check_frontend_test()` — check against frontend_unit rules
    - Return `ComplianceViolation` dataclass with `file_path`, `line_number`, `rule_id`, `severity`, `expected_pattern`, `actual_pattern`, `convention_reference`
    - Support required, recommended, and forbidden rule categories
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 7.6 Write property test for pytest marker detection (Property 25)
    - **Property 25: Pytest marker detection**
    - For any backend test file lacking explicit markers and not in an auto-marking directory, the checker flags it as non-compliant
    - File: `backend/tests/unit/test_maintenance/test_compliance_checker_props.py`
    - **Validates: Requirements 11.2**

  - [x] 7.7 Write property test for blueprint pattern detection (Property 26)
    - **Property 26: Blueprint pattern detection**
    - For any route file in `backend/src/routes/`, verify Blueprint with `_bp` suffix is detected
    - File: `backend/tests/unit/test_maintenance/test_compliance_checker_props.py`
    - **Validates: Requirements 11.5**

  - [x] 7.8 Write property test for configurable compliance rules (Property 27)
    - **Property 27: Configurable compliance rules**
    - For any valid rules JSON, the checker loads and applies all rules; changing rules changes detected violations
    - File: `backend/tests/unit/test_maintenance/test_compliance_checker_props.py`
    - **Validates: Requirements 11.7**

  - [x] 7.9 Implement `scanner.py` — main Test Health Scanner orchestrator
    - Implement `TestHealthScanner` class that coordinates all analysis components
    - Implement `scan()` method that runs MockViolationDetector, ComplianceChecker, and DependencyMapper
    - Implement `generate_baseline()` for initial snapshot of failing tests
    - Produce `ScanReport` dataclass with summary, violations, drift issues, compliance violations, untested sources
    - Add CLI interface: `--maintenance-session`, `--baseline`, `--frontend-only` flags
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 7.10 Write unit tests for mock violation detector, compliance checker, and scanner
    - Test detector against real anti-patterns from existing test files (e.g., `test_audit_logger.py` patterns)
    - Test compliance checker rule loading and matching
    - Test scanner orchestration and report assembly
    - Files: `backend/tests/unit/test_maintenance/test_mock_violation_detector.py`, `backend/tests/unit/test_maintenance/test_compliance_checker.py`
    - _Requirements: 1.2, 1.3, 11.1, 11.7_

- [x] 8. Checkpoint — Verify Phase 3
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Phase 4 — Drift detector and frontend scanner (drift prevention)
  - [x] 9.1 Implement `drift_detector.py` — signature and key change detection
    - Implement `DriftDetector` class that takes a `DependencyMap`
    - Implement `detect_signature_drift()` — compare function signatures in source vs mock setup in tests using AST
    - Implement `detect_key_drift()` — compare dictionary keys/data structures between source and test mocks
    - Return `DriftIssue` dataclass with `source_file`, `test_file`, `line_number`, `drift_type`, `severity`, `old_value`, `new_value`, `description`
    - Implement `generate_drift_report()` for structured output
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

  - [x] 9.2 Write property test for source-test drift detection (Property 12)
    - **Property 12: Source-test drift detection**
    - For any source file change modifying a function signature or dictionary key, and any dependent test file, the detector flags the test with a DriftIssue
    - File: `backend/tests/unit/test_maintenance/test_drift_detector_props.py`
    - **Validates: Requirements 6.2, 6.3, 6.4**

  - [x] 9.3 Implement `frontend_scanner.py` — React test analysis
    - Implement frontend scanner that analyzes TypeScript test files using regex patterns
    - Detect missing MSW handlers for API calls (`fetch(`, `axios.get(` without `setupServer`)
    - Detect missing provider wrappers (direct `@testing-library/react` `render` instead of `test-utils`)
    - Detect stale imports (imports from paths that don't exist in the source tree)
    - _Requirements: 9.1, 9.2, 9.4_

  - [x] 9.4 Write property test for frontend MSW detection (Property 19)
    - **Property 19: Frontend MSW detection**
    - For any TypeScript test file with HTTP calls without MSW setup, the scanner flags it
    - File: `backend/tests/unit/test_maintenance/test_frontend_scanner_props.py`
    - **Validates: Requirements 9.1, 11.4**

  - [x] 9.5 Write property test for frontend provider detection (Property 20)
    - **Property 20: Frontend provider detection**
    - For any test file importing `render` from `@testing-library/react` instead of `test-utils`, the scanner flags it
    - File: `backend/tests/unit/test_maintenance/test_frontend_scanner_props.py`
    - **Validates: Requirements 9.2, 11.3**

  - [x] 9.6 Write property test for frontend stale import detection (Property 21)
    - **Property 21: Frontend stale import detection**
    - For any test file importing from a non-existent path, the scanner flags it
    - File: `backend/tests/unit/test_maintenance/test_frontend_scanner_props.py`
    - **Validates: Requirements 9.4**

  - [x] 9.7 Wire drift detector and frontend scanner into `scanner.py`
    - Integrate `DriftDetector` into the scanner's `scan()` method
    - Integrate `FrontendScanner` into the scanner's `scan()` method
    - Add drift issues and frontend violations to `ScanReport`
    - _Requirements: 1.1, 6.4, 9.1_

  - [x] 9.8 Write unit tests for drift detector and frontend scanner
    - Test signature drift with real function signature changes
    - Test key drift with dictionary key renames
    - Test frontend patterns against real TypeScript test file examples
    - Files: `backend/tests/unit/test_maintenance/test_drift_detector.py`, `backend/tests/unit/test_maintenance/test_frontend_scanner.py`
    - _Requirements: 6.2, 6.3, 9.1, 9.2_

- [x] 10. Checkpoint — Verify Phase 4
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Phase 5 — Flaky test quarantine, classification registry, and baseline triage (tracking)
  - [x] 11.1 Create `backend/tests/test-classification-registry.json` with initial schema
    - Define the JSON schema with `version`, `last_updated`, `tests` (keyed by test ID), and `metadata`
    - Each test entry: `category`, `status`, `failure_reason`, `triage_decision`, `triage_date`, `target_fix_date`, `root_cause`, `notes`
    - Implement validation: reject entries without `triage_decision` for failing tests
    - _Requirements: 8.3, 8.4_

  - [x] 11.2 Implement `flaky_quarantine.py` — flaky test detection and tracking
    - Implement `FlakyQuarantine` class with `record_result()`, `detect_flaky()`, `quarantine()`, `check_restoration()`
    - Track test results per test ID with pass/fail history
    - Detect flakiness: same test has both pass and fail within same code state
    - Quarantine lifecycle: quarantine with reason → track consecutive passes → restore after 3 consecutive passes
    - Implement `get_quarantine_report()` returning all quarantined tests
    - Create `backend/tests/quarantine-log.json` for persistence
    - Use atomic writes (write to temp file, then rename) for data integrity
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 11.3 Write property test for flaky test detection (Property 10)
    - **Property 10: Flaky test detection**
    - For any sequence of results where a test has both pass and fail in the same code state, the system marks it flaky
    - File: `backend/tests/unit/test_maintenance/test_flaky_quarantine_props.py`
    - **Validates: Requirements 5.1**

  - [x] 11.4 Write property test for quarantine lifecycle integrity (Property 11)
    - **Property 11: Quarantine lifecycle integrity**
    - For any sequence of quarantine/restore operations, the report lists exactly the quarantined tests with valid fields; restoration only after 3+ consecutive passes
    - File: `backend/tests/unit/test_maintenance/test_flaky_quarantine_props.py`
    - **Validates: Requirements 5.3, 5.4, 5.5**

  - [x] 11.5 Implement baseline snapshot and stale failure detection in `scanner.py`
    - Implement `generate_baseline()` to snapshot all currently failing tests with failure reasons
    - Implement stale failure detection: flag tests failing > 14 days without a fix
    - Implement untriaged warning: warn when > 10 failing tests lack triage decisions
    - Wire classification registry validation into scanner
    - _Requirements: 8.1, 8.2, 8.5_

  - [x] 11.6 Write property test for stale failure escalation (Property 16)
    - **Property 16: Stale failure escalation**
    - For any registry entry with failure date > 14 days before scan date, the scanner includes it in stale_failures
    - File: `backend/tests/unit/test_maintenance/test_classification_registry_props.py`
    - **Validates: Requirements 8.2**

  - [x] 11.7 Write property test for triage enforcement (Property 17)
    - **Property 17: Triage enforcement**
    - For any attempt to add a failing test without a triage_decision, the registry rejects it
    - File: `backend/tests/unit/test_maintenance/test_classification_registry_props.py`
    - **Validates: Requirements 8.4**

  - [x] 11.8 Write property test for untriaged warning threshold (Property 18)
    - **Property 18: Untriaged warning threshold**
    - For any report where untriaged failing tests > 10, the summary includes a warning
    - File: `backend/tests/unit/test_maintenance/test_classification_registry_props.py`
    - **Validates: Requirements 8.5**

  - [x] 11.9 Write unit tests for flaky quarantine and classification registry
    - Test quarantine lifecycle with specific examples
    - Test registry validation rejecting entries without triage decisions
    - Test stale failure detection with date arithmetic
    - Files: `backend/tests/unit/test_maintenance/test_flaky_quarantine.py`
    - _Requirements: 5.1, 5.3, 8.2, 8.4_

- [x] 12. Checkpoint — Verify Phase 5
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Phase 6 — Report generator, historical tracking, and maintenance sessions (reporting)
  - [x] 13.1 Implement `report_generator.py` — JSON and Markdown output
    - Implement `ReportGenerator` class with `to_json()` and `to_markdown()` methods
    - JSON output: full `ScanReport` serialized with all fields
    - Markdown output: summary table, regressions section, improvements section, quarantine section
    - Implement report serialization round-trip (JSON → object → JSON preserves all fields)
    - Store reports in `backend/tests/reports/` with timestamped filenames
    - Create `backend/tests/reports/.gitkeep`
    - _Requirements: 1.5, 7.3, 7.5_

  - [x] 13.2 Write property test for report serialization round-trip (Property 3)
    - **Property 3: Report serialization round-trip**
    - For any ScanReport or DependencyMap, serializing to JSON and back produces an equivalent object
    - File: `backend/tests/unit/test_maintenance/test_report_generator_props.py`
    - **Validates: Requirements 1.5, 2.5**

  - [x] 13.3 Implement trend comparison and historical reporting
    - Implement `compute_trend()` that compares two ScanReports
    - Compute: tests_fixed, tests_newly_broken, tests_newly_quarantined
    - Detect regressions (passing → failing) and highlight in report
    - Load previous report from `backend/tests/reports/` for automatic comparison
    - _Requirements: 7.2, 7.4_

  - [x] 13.4 Write property test for report trend computation (Property 13)
    - **Property 13: Report trend computation**
    - For any two reports, trend correctly computes fixed = (failing before ∩ passing after), newly_broken = (passing before ∩ failing after)
    - File: `backend/tests/unit/test_maintenance/test_report_generator_props.py`
    - **Validates: Requirements 7.2, 7.4, 10.3**

  - [x] 13.5 Write property test for summary category completeness (Property 14)
    - **Property 14: Summary category completeness**
    - For any test results across categories, the summary has a CategorySummary per category where total = passing + failing + skipped + flaky + quarantined
    - File: `backend/tests/unit/test_maintenance/test_report_generator_props.py`
    - **Validates: Requirements 7.1**

  - [x] 13.6 Write property test for markdown report structure (Property 15)
    - **Property 15: Markdown report structure**
    - For any ScanReport, the markdown contains summary table, regressions section (if any), improvements section (if any), quarantine section (if any)
    - File: `backend/tests/unit/test_maintenance/test_report_generator_props.py`
    - **Validates: Requirements 7.5**

  - [x] 13.7 Implement maintenance session workflow in `scanner.py`
    - Implement `--maintenance-session` mode that generates prioritized work list
    - Group fixes by root cause: database_mocking, key_mismatch, signature_change, environment_dependency
    - Order within groups by severity (critical → high → medium → low)
    - Include effort estimates per fix category
    - Implement `generate_session_summary()` comparing before/after reports
    - Track session history in `backend/tests/reports/` for trend tracking
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 13.8 Write property test for maintenance work list ordering (Property 22)
    - **Property 22: Maintenance work list ordering**
    - For any set of issues, the work list groups by root cause and orders by severity within groups
    - File: `backend/tests/unit/test_maintenance/test_maintenance_session_props.py`
    - **Validates: Requirements 10.1, 10.5**

  - [x] 13.9 Write property test for effort estimation completeness (Property 23)
    - **Property 23: Effort estimation completeness**
    - For any set of issues grouped by category, the output includes a non-negative effort estimate per category
    - File: `backend/tests/unit/test_maintenance/test_maintenance_session_props.py`
    - **Validates: Requirements 10.2**

  - [x] 13.10 Write property test for session history ordering (Property 24) - **Property 24: Session history ordering** - For any sequence of sessions, history is in chronological order with no gaps or duplicates - File: `backend/tests/unit/test_maintenance/test_maintenance_session_props.py` - **Validates: Requirements 10.4**
        c

- [x] 14. Final checkpoint — Verify all phases
  - Ensure all tests pass, ask the user if questions arise.
  - Run full test maintenance test suite: `pytest backend/tests/unit/test_maintenance/ -v`
  - Verify scanner CLI works: `python -m backend.scripts.test_maintenance.scanner --help`
  - Verify scoped runner CLI works: `python -m backend.scripts.test_maintenance.scoped_runner --help`

## Notes

- All tasks are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between phases
- Property tests validate universal correctness properties (27 total across all phases)
- Unit tests validate specific examples and edge cases
- Phase 1 delivers immediate ROI by fixing the root cause of most test failures
- All tools produce JSON output for machine consumption and console/markdown for humans
