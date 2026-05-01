# Requirements Document

## Introduction

The myAdmin project suffers from chronic test instability: unit tests connect to real databases instead of using mocks, code changes break tests that are never updated, pre-existing failures accumulate and get ignored, and the AI assistant runs the full test suite repeatedly instead of scoping to relevant changes. This spec defines a Test Maintenance Framework — a systematic approach to classify, fix, and prevent broken tests, plus tooling and processes to keep tests healthy as the codebase evolves.

## Glossary

- **Test_Health_Scanner**: A Python script that analyzes backend test files to detect common anti-patterns (real database connections in unit tests, missing mocks, outdated assertions, missing test markers)
- **Test_Dependency_Mapper**: A utility that maps source files to their corresponding test files, enabling scoped test execution when code changes
- **Mock_Violation_Detector**: A component of the Test_Health_Scanner that identifies unit tests importing or connecting to real external resources (database, APIs, file systems) without proper mocking
- **Test_Classification_Registry**: A configuration file that categorizes every test file by type (unit, integration, api, e2e, manual) and tracks its health status (passing, failing, skipped, flaky)
- **Scoped_Test_Runner**: A script or configuration that determines which tests to run based on which source files changed, using the Test_Dependency_Mapper
- **Test_Isolation_Layer**: Shared pytest fixtures and conftest patterns that enforce proper mocking of database connections, external APIs, and environment variables for unit tests
- **Flaky_Test_Quarantine**: A mechanism to tag and isolate tests that fail intermittently due to environment dependencies, preventing them from blocking other test runs
- **Frontend_Test_Runner**: The Vitest-based test execution system for React/TypeScript tests, including React Testing Library and MSW for API mocking
- **E2E_Test_Runner**: The Playwright-based end-to-end test execution system

## Requirements

### Requirement 1: Test Health Scanning and Classification

**User Story:** As a developer, I want to automatically scan all test files for common anti-patterns, so that I can identify and prioritize which tests need fixing.

#### Acceptance Criteria

1. WHEN the Test_Health_Scanner is executed against the backend test directory, THE Test_Health_Scanner SHALL analyze each test file and produce a report listing detected anti-patterns per file
2. WHEN a unit test file contains a direct import of `mysql.connector` or calls `mysql.connector.connect` without a mock context, THE Mock_Violation_Detector SHALL flag that file as having a database mock violation
3. WHEN a unit test file references environment variables that point to real databases (e.g., `testfinance`) without using `patch.dict`, THE Mock_Violation_Detector SHALL flag that file as having an environment isolation violation
4. WHEN the Test_Health_Scanner completes analysis, THE Test_Health_Scanner SHALL categorize each detected issue by severity: critical (test hits real resources), high (test broken by code change), medium (flaky/environment-dependent), low (style or marker issues)
5. WHEN the Test_Health_Scanner is executed, THE Test_Health_Scanner SHALL output a machine-readable JSON report and a human-readable summary to the console

### Requirement 2: Source-to-Test Dependency Mapping

**User Story:** As a developer, I want to know which tests correspond to which source files, so that I can run only the relevant tests after making a code change.

#### Acceptance Criteria

1. WHEN the Test_Dependency_Mapper is executed, THE Test_Dependency_Mapper SHALL scan all backend source files in `backend/src/` and map each to its corresponding test files in `backend/tests/`
2. WHEN a source file has no corresponding test file, THE Test_Dependency_Mapper SHALL flag that source file as untested in the mapping output
3. WHEN the Test*Dependency_Mapper generates a mapping, THE Test_Dependency_Mapper SHALL use import analysis and naming conventions (`test*{module_name}.py`) to establish source-to-test relationships
4. WHEN the Test_Dependency_Mapper is executed for frontend files, THE Test_Dependency_Mapper SHALL map React components in `frontend/src/` to their corresponding test files using co-located test patterns (`*.test.tsx`, `*.test.ts`) and the `__tests__/` directory convention
5. THE Test_Dependency_Mapper SHALL produce a JSON mapping file that can be consumed by the Scoped_Test_Runner

### Requirement 3: Scoped Test Execution

**User Story:** As a developer, I want to run only the tests affected by my code changes, so that I get fast feedback without running the entire test suite.

#### Acceptance Criteria

1. WHEN a list of changed source files is provided, THE Scoped_Test_Runner SHALL use the Test_Dependency_Mapper output to determine which test files to execute
2. WHEN the Scoped_Test_Runner identifies affected tests, THE Scoped_Test_Runner SHALL execute only those tests using the appropriate test runner (pytest for backend, vitest for frontend)
3. WHEN no test files map to a changed source file, THE Scoped_Test_Runner SHALL report that the changed file has no test coverage and skip test execution for that file
4. WHEN the Scoped_Test_Runner is invoked with a `--full` flag, THE Scoped_Test_Runner SHALL execute the complete test suite instead of scoped tests
5. IF the Scoped_Test_Runner encounters an error resolving dependencies, THEN THE Scoped_Test_Runner SHALL fall back to running all tests in the same directory as the changed file and log a warning

### Requirement 4: Unit Test Isolation Enforcement

**User Story:** As a developer, I want unit tests to be properly isolated from external resources, so that they run fast and reliably without database or network access.

#### Acceptance Criteria

1. THE Test_Isolation_Layer SHALL provide a `mock_db` pytest fixture that patches `DatabaseManager` methods (`execute_query`, `execute_batch_queries`, `transaction`, `get_cursor`) with configurable return values
2. THE Test_Isolation_Layer SHALL provide a `mock_cognito` pytest fixture that patches AWS Cognito authentication calls with configurable mock responses
3. THE Test_Isolation_Layer SHALL provide a `mock_google_drive` pytest fixture that patches Google Drive API calls with configurable mock responses
4. WHEN a unit test (in `backend/tests/unit/`) attempts to create a real database connection, THE Test_Isolation_Layer SHALL raise an error indicating that unit tests must use mock fixtures
5. WHEN a unit test uses the `mock_db` fixture, THE Test_Isolation_Layer SHALL ensure no real network calls are made during test execution
6. THE Test_Isolation_Layer SHALL provide a `mock_env` fixture that sets standard test environment variables without loading from `.env` files

### Requirement 5: Flaky Test Detection and Quarantine

**User Story:** As a developer, I want flaky tests to be identified and quarantined, so that they do not block reliable test results or waste CI time.

#### Acceptance Criteria

1. WHEN a test passes on some runs and fails on others within the same code state, THE Flaky_Test_Quarantine SHALL mark that test as flaky in the Test_Classification_Registry
2. WHEN a test is marked as flaky, THE Flaky_Test_Quarantine SHALL add a `@pytest.mark.flaky` marker (backend) or `.skip` annotation with reason (frontend) to prevent it from blocking test runs
3. WHEN the Flaky_Test_Quarantine quarantines a test, THE Flaky_Test_Quarantine SHALL log the quarantine reason, the date, and the last observed failure message
4. WHEN a quarantined test is fixed and passes consistently for 3 consecutive full test runs, THE Flaky_Test_Quarantine SHALL remove the flaky marker and restore the test to normal execution
5. THE Flaky_Test_Quarantine SHALL maintain a quarantine report listing all currently quarantined tests with their reasons and quarantine dates

### Requirement 6: Test-Code Drift Detection

**User Story:** As a developer, I want to be alerted when source code changes make existing tests outdated, so that I can update tests before they accumulate as broken.

#### Acceptance Criteria

1. WHEN a source file is modified, THE Test_Dependency_Mapper SHALL identify all test files that depend on the modified source file
2. WHEN a function signature changes (parameters added, removed, or renamed) in a source file, THE Test_Health_Scanner SHALL flag dependent test files as potentially outdated
3. WHEN a data structure or dictionary key changes in a source file (e.g., renaming `'Account'` to `'account_number'`), THE Test_Health_Scanner SHALL flag tests that reference the old key names
4. WHEN drift is detected between source and test files, THE Test_Health_Scanner SHALL generate a drift report listing each affected test with the specific change that caused the drift
5. IF a source file is modified and has no corresponding test file, THEN THE Test_Health_Scanner SHALL flag the source file as requiring new test coverage

### Requirement 7: Test Execution Reporting and Dashboard

**User Story:** As a developer, I want a clear overview of test health across the project, so that I can track progress on fixing broken tests and preventing regressions.

#### Acceptance Criteria

1. WHEN the test suite is executed, THE Test_Health_Scanner SHALL generate a summary report showing: total tests, passing, failing, skipped, flaky, and quarantined counts per category (unit, integration, api, e2e)
2. WHEN the summary report is generated, THE Test_Health_Scanner SHALL include a trend comparison with the previous report showing tests fixed, tests newly broken, and tests newly quarantined
3. THE Test_Health_Scanner SHALL store historical test health reports in a `backend/tests/reports/` directory with timestamped filenames
4. WHEN a test transitions from passing to failing, THE Test_Health_Scanner SHALL highlight that test in the report as a regression
5. THE Test_Health_Scanner SHALL generate a markdown summary suitable for inclusion in pull request descriptions

### Requirement 8: Pre-existing Failure Triage

**User Story:** As a developer, I want to systematically triage and track pre-existing test failures, so that they are fixed rather than permanently ignored.

#### Acceptance Criteria

1. WHEN the Test_Health_Scanner is first executed, THE Test_Health_Scanner SHALL create a baseline snapshot of all currently failing tests with their failure reasons
2. WHEN a test has been failing for more than 14 days without a fix, THE Test_Health_Scanner SHALL escalate that test in the report as a stale failure requiring attention
3. WHEN a pre-existing failure is triaged, THE Test_Classification_Registry SHALL record the triage decision: fix (with target date), quarantine (with reason), or delete (with justification)
4. THE Test_Classification_Registry SHALL prevent new pre-existing failures from being added without a triage decision
5. WHEN the number of untriaged failing tests exceeds 10, THE Test_Health_Scanner SHALL include a warning in the summary report

### Requirement 9: Frontend Test Maintenance

**User Story:** As a frontend developer, I want the same test health scanning and isolation patterns applied to frontend tests, so that React component tests remain reliable.

#### Acceptance Criteria

1. WHEN the Test_Health_Scanner is executed for frontend tests, THE Test_Health_Scanner SHALL detect tests that make real API calls without MSW (Mock Service Worker) handlers
2. WHEN a frontend component test fails due to missing mock providers (e.g., ChakraProvider, AuthContext), THE Test_Health_Scanner SHALL flag the test as having a missing provider dependency
3. THE Frontend_Test_Runner SHALL provide a shared test utility (`test-utils.tsx`) that wraps components with all required providers (ChakraProvider, I18nextProvider, AuthContext, Router)
4. WHEN a frontend test file imports a component that has been moved or renamed, THE Test_Health_Scanner SHALL flag the test as having a stale import
5. THE Frontend_Test_Runner SHALL support scoped test execution using vitest's `--related` flag to run only tests affected by changed files

### Requirement 10: Test Maintenance Session Workflow

**User Story:** As a developer, I want a structured workflow for periodic test maintenance sessions, so that test health improves consistently over time.

#### Acceptance Criteria

1. THE Test_Health_Scanner SHALL provide a `--maintenance-session` mode that generates a prioritized work list of tests to fix, ordered by severity and impact
2. WHEN a maintenance session is started, THE Test_Health_Scanner SHALL estimate the effort for each fix category: mock violations (per test), code drift (per test), flaky tests (per test), missing tests (per source file)
3. WHEN a maintenance session is completed, THE Test_Health_Scanner SHALL generate a session summary showing: tests fixed, tests quarantined, tests deleted, and remaining backlog
4. THE Test_Health_Scanner SHALL track maintenance session history to show test health improvement over time
5. WHEN the maintenance session work list is generated, THE Test_Health_Scanner SHALL group fixes by root cause (database mocking, key mismatches, signature changes, environment dependencies) to enable batch fixing

### Requirement 11: Framework and Pattern Compliance Checking

**User Story:** As a developer, I want to verify that tests and source code follow the project's established frameworks and patterns, so that new code stays consistent and tests don't break due to convention violations.

#### Acceptance Criteria

1. WHEN the Test_Health_Scanner analyzes a backend unit test file, THE Test_Health_Scanner SHALL verify that the test uses shared `conftest.py` fixtures (e.g., `mock_db`, `mock_env`) instead of creating ad-hoc mocks for database connections, Cognito, or Google Drive
2. WHEN the Test_Health_Scanner analyzes a backend test file, THE Test_Health_Scanner SHALL verify that the test has a proper pytest marker (`@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.api`, or `@pytest.mark.e2e`) and flag unmarked tests as non-compliant
3. WHEN the Test_Health_Scanner analyzes a frontend test file, THE Test_Health_Scanner SHALL verify that the test uses the shared `test-utils.tsx` render wrapper (with ChakraProvider, I18nextProvider, AuthContext, Router) instead of bare `render()` calls
4. WHEN the Test_Health_Scanner analyzes a frontend test file that tests API interactions, THE Test_Health_Scanner SHALL verify that the test uses MSW (Mock Service Worker) handlers instead of manual `fetch` or `axios` mocks
5. WHEN the Test_Health_Scanner analyzes a backend route file, THE Test_Health_Scanner SHALL verify that the route uses the Blueprint pattern with `_bp` suffix naming convention
6. WHEN the Test_Health_Scanner detects a framework compliance violation, THE Test_Health_Scanner SHALL include the violation in the report with the expected pattern, the actual pattern found, and a reference to the project convention documentation
7. THE Test_Health_Scanner SHALL support a configurable compliance rules file (`test-compliance-rules.json`) that defines which patterns are required, recommended, or forbidden for each test category
