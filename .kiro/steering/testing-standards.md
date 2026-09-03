---
inclusion: fileMatch
fileMatchPattern: "**/test_*.py"
---

# Testing Standards

## Backend (pytest)

### Markers

Tests are auto-marked by directory, but you can also add explicit markers:

- `@pytest.mark.unit` — fast, isolated, no external dependencies
- `@pytest.mark.integration` — database, file system, external services
- `@pytest.mark.api` — requires running Flask app with authentication
- `@pytest.mark.e2e` — full stack testing
- `@pytest.mark.slow` — tests that take > 10 seconds

### Test Naming

Format: `test_{function}_{scenario}_{expected}` — e.g.:

```python
def test_process_transaction_valid_csv_returns_success():
def test_process_transaction_missing_iban_raises_error():
def test_check_duplicate_existing_record_returns_true():
```

### Directory Structure

Place tests in the matching directory — markers are auto-applied:

- `tests/unit/` — unit tests
- `tests/unit/test_maintenance/` — test maintenance framework tests (382 tests)
- `tests/integration/` — integration tests
- `tests/api/` — API endpoint tests
- `tests/e2e/` — end-to-end tests

### Test Isolation Layer

Unit tests are protected by an isolation layer that prevents accidental real connections. This is enforced automatically — no opt-in required.

**Connection guard** (`tests/unit/conftest.py`): An `autouse` fixture patches `mysql.connector.connect` to raise `RuntimeError`. Any unit test that accidentally tries a real DB connection fails immediately.

**Required fixtures** — use these instead of creating ad-hoc mocks:

| Fixture             | What it mocks                     | Key methods                                                           |
| ------------------- | --------------------------------- | --------------------------------------------------------------------- |
| `mock_db`           | `database.DatabaseManager`        | `execute_query`, `execute_batch_queries`, `transaction`, `get_cursor` |
| `mock_env`          | `os.environ` via `patch.dict`     | All standard env vars (DB*HOST, COGNITO*\*, etc.)                     |
| `mock_cognito`      | `auth.cognito_utils.boto3.client` | `admin_get_user` with test user attributes                            |
| `mock_google_drive` | `google_drive_service.build`      | `files().list()`, `files().get()`                                     |

**Usage example:**

```python
def test_my_service(mock_db, mock_env):
    mock_db.execute_query.return_value = [{"id": 1, "name": "test"}]
    result = my_service.get_items()
    assert len(result) == 1
```

**Legacy fixtures** (still available in `tests/conftest.py`):

- `mock_database` — older mocked MySQL connection + cursor
- `test_environment` / `production_environment` — sets TEST_MODE
- `sample_transaction_data`, `sample_str_data`, `sample_csv_content`
- `temp_dir` / `temp_file` — temporary filesystem

### Anti-Patterns (enforced by compliance checker)

- **No direct `mysql.connector` imports** in unit tests — use `mock_db`
- **No `os.environ` access** to real DB names without `patch.dict` — use `mock_env`
- **No `DatabaseManager(test_mode=True)`** without mocking — use `mock_db`
- **No `load_dotenv()`** in test files — hardcode test values or use `mock_env`
- **No `sys.path` manipulation** in test files — conftest handles it

### Compliance Rules

Rules are defined in `backend/tests/test-compliance-rules.json` and checked by the compliance checker. Categories: `required`, `recommended`, `forbidden`.

### Coverage

- Target: 80% for new code
- Run: `pytest --cov=src tests/`
- Focus on business logic in services, not boilerplate routes

### What to Test

- Service layer business logic
- Data validation and edge cases
- Error handling paths
- Tenant isolation (verify queries include tenant_id)

### What NOT to Test

- Flask route wiring (covered by API tests)
- Third-party library internals
- Simple getters/setters

## Test Maintenance Framework

The project includes a test maintenance framework in `backend/scripts/test_maintenance/` that provides automated test health analysis.

### Tools

| Tool                        | Purpose                                      | CLI                                                        |
| --------------------------- | -------------------------------------------- | ---------------------------------------------------------- |
| **Scanner**                 | Orchestrates all analysis, produces reports  | `python -m backend.scripts.test_maintenance.scanner`       |
| **Scoped Runner**           | Runs only tests affected by code changes     | `python -m backend.scripts.test_maintenance.scoped_runner` |
| **Dependency Mapper**       | Maps source files to their test files        | Used by scanner and scoped runner                          |
| **Mock Violation Detector** | Finds direct DB/env access in unit tests     | Used by scanner                                            |
| **Compliance Checker**      | Checks tests against coding conventions      | Used by scanner                                            |
| **Drift Detector**          | Finds source-test signature/key mismatches   | Used by scanner                                            |
| **Frontend Scanner**        | Finds missing MSW, provider, stale imports   | Used by scanner                                            |
| **Flaky Quarantine**        | Tracks and quarantines intermittent failures | Used by scanner                                            |
| **Report Generator**        | JSON + Markdown reports with trend tracking  | Used by scanner                                            |

### Common Commands

```bash
# Full health scan
python -m backend.scripts.test_maintenance.scanner

# Maintenance session (prioritised fix list)
python -m backend.scripts.test_maintenance.scanner --maintenance-session

# Generate baseline snapshot
python -m backend.scripts.test_maintenance.scanner --baseline

# Frontend-only scan
python -m backend.scripts.test_maintenance.scanner --frontend-only

# Run tests for changed files only
python -m backend.scripts.test_maintenance.scoped_runner --git-diff

# Run tests for specific files
python -m backend.scripts.test_maintenance.scoped_runner backend/src/services/my_service.py

# Run full suite via scoped runner
python -m backend.scripts.test_maintenance.scoped_runner --full
```

### Reports

Reports are stored in `backend/tests/reports/` with timestamped filenames. The scanner automatically compares against the latest previous report to show trends (fixed, newly broken, newly quarantined).

### Classification Registry

`backend/tests/test-classification-registry.json` tracks test status, triage decisions, and failure reasons. Failing tests require a `triage_decision` before being added. Tests failing > 14 days without a fix are flagged as stale.

### Full Spec

#[[file:.kiro/specs/test-maintenance-framework/design.md]]
