---
inclusion: fileMatch
fileMatchPattern: "**/test_*.py,**/*.test.ts,**/*.test.tsx"
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
- `tests/integration/` — integration tests
- `tests/api/` — API endpoint tests
- `tests/e2e/` — end-to-end tests

### Fixtures

Use shared fixtures from `conftest.py`:

- `mock_database` — mocked MySQL connection + cursor
- `mock_google_drive` — mocked Drive service
- `test_environment` — sets TEST_MODE=true with test env vars
- `production_environment` — sets TEST_MODE=false
- `sample_transaction_data` — sample transaction records
- `sample_str_data` — sample STR booking records
- `sample_csv_content` — sample banking CSV
- `temp_dir` / `temp_file` — temporary filesystem

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

## Frontend (Jest + React Testing Library)

### Naming

Format: `describe('ComponentName') > it('should do X when Y')`

### Approach

- Test behavior, not implementation details
- Use `screen.getByRole`, `screen.getByText` over `getByTestId`
- Avoid testing internal state — test what the user sees
- Use MSW for API mocking

### Coverage

- Target: 80% for new components
- Run: `npm test -- --coverage`
