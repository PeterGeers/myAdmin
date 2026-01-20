# Testing Guide

## Test Structure

All tests are now organized in `backend/tests/`:

```
tests/
├── conftest.py           # Shared fixtures and configuration
├── unit/                 # Unit tests (24 tests)
├── api/                  # API endpoint tests (17 tests)
├── database/             # Database tests (10 tests)
├── patterns/             # Pattern analysis tests (12 tests)
└── integration/          # Integration tests (6 tests)
```

Total: **69 test files**

## Running Tests

### All Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest tests/
```

### By Category

```powershell
# Unit tests only
pytest tests/unit/

# API tests only
pytest tests/api/

# Database tests only
pytest tests/database/

# Pattern tests only
pytest tests/patterns/

# Integration tests only
pytest tests/integration/
```

### Specific Test File

```powershell
pytest tests/api/test_duplicate_api.py
```

### Specific Test Function

```powershell
pytest tests/api/test_duplicate_api.py::test_check_duplicate_endpoint
```

### With Verbose Output

```powershell
pytest tests/ -v
```

### With Coverage

```powershell
pytest tests/ --cov=src --cov-report=html
```

## Test Markers

Tests can be marked with custom markers:

```python
@pytest.mark.integration
def test_full_workflow():
    pass

@pytest.mark.slow
def test_performance():
    pass

@pytest.mark.database
def test_database_query():
    pass

@pytest.mark.external
def test_api_call():
    pass
```

Run specific markers:

```powershell
# Run only integration tests
pytest tests/ -m integration

# Skip slow tests
pytest tests/ -m "not slow"

# Run only database tests
pytest tests/ -m database
```

## Available Fixtures

From `conftest.py`:

- `temp_dir` - Temporary directory for test files
- `temp_file` - Temporary file for testing
- `mock_database` - Mock database connection
- `mock_google_drive` - Mock Google Drive service
- `test_environment` - Test environment variables
- `production_environment` - Production environment variables
- `sample_pdf_content` - Sample PDF for testing
- `sample_csv_content` - Sample CSV for banking tests
- `sample_transaction_data` - Sample transaction data
- `sample_str_data` - Sample STR booking data

### Using Fixtures

```python
def test_with_temp_dir(temp_dir):
    # temp_dir is automatically created and cleaned up
    file_path = os.path.join(temp_dir, 'test.txt')
    with open(file_path, 'w') as f:
        f.write('test')
    assert os.path.exists(file_path)

def test_with_mock_db(mock_database):
    # Use mocked database
    cursor = mock_database['cursor']
    cursor.execute.return_value = None
    # Your test code here
```

## Test Utilities

### SNS Notification Test

To test AWS SNS notifications (standalone script):

```powershell
python backend/scripts/test_sns_notification.py
```

This is NOT a pytest test - it's a utility script to verify AWS SNS setup.

## Writing New Tests

### 1. Choose the Right Category

- **Unit tests** (`tests/unit/`) - Test individual functions/classes
- **API tests** (`tests/api/`) - Test Flask endpoints
- **Database tests** (`tests/database/`) - Test database queries
- **Pattern tests** (`tests/patterns/`) - Test pattern analysis logic
- **Integration tests** (`tests/integration/`) - Test complete workflows

### 2. Create Test File

```python
# tests/unit/test_my_feature.py
import pytest
from src.my_module import my_function

def test_my_function():
    result = my_function(input_data)
    assert result == expected_output

def test_my_function_with_fixture(temp_dir):
    # Use fixture
    result = my_function(temp_dir)
    assert result is not None
```

### 3. Run Your Test

```powershell
pytest tests/unit/test_my_feature.py -v
```

## Continuous Integration

Tests should be run before:

- Committing code
- Creating pull requests
- Deploying to production

### Pre-commit Check

```powershell
# Run all tests
pytest tests/

# Run fast tests only
pytest tests/ -m "not slow"

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`, make sure:

1. You're in the backend directory
2. Virtual environment is activated
3. `conftest.py` is in `tests/` root (not subdirectory)

### Database Connection Errors

Tests should use mocked databases. If you see real database errors:

1. Check if test is using `mock_database` fixture
2. Verify test environment variables are set
3. Use `@pytest.mark.database` for tests that need real DB

### Slow Tests

Mark slow tests:

```python
@pytest.mark.slow
def test_performance():
    # Long-running test
    pass
```

Skip them during development:

```powershell
pytest tests/ -m "not slow"
```

## Test Coverage

Generate coverage report:

```powershell
pytest tests/ --cov=src --cov-report=html
```

View report:

```powershell
start htmlcov/index.html
```

## Best Practices

1. **One test, one assertion** - Keep tests focused
2. **Use fixtures** - Don't repeat setup code
3. **Mock external services** - Don't call real APIs in tests
4. **Test edge cases** - Not just happy path
5. **Clear test names** - `test_user_login_with_invalid_password`
6. **Fast tests** - Mark slow tests with `@pytest.mark.slow`
7. **Independent tests** - Tests shouldn't depend on each other

## Example Test

```python
# tests/api/test_my_endpoint.py
import pytest
from flask import json

def test_my_endpoint_success(mock_database):
    """Test successful API call"""
    from app import app

    with app.test_client() as client:
        response = client.post('/api/my-endpoint',
            json={'data': 'test'},
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

def test_my_endpoint_missing_data(mock_database):
    """Test API call with missing data"""
    from app import app

    with app.test_client() as client:
        response = client.post('/api/my-endpoint',
            json={},
            content_type='application/json'
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
```

## Resources

- pytest documentation: https://docs.pytest.org/
- Flask testing: https://flask.palletsprojects.com/en/2.3.x/testing/
- Coverage.py: https://coverage.readthedocs.io/

---

**Last updated**: January 20, 2026  
**Total tests**: 69 test files  
**Test framework**: pytest 8.4.2
