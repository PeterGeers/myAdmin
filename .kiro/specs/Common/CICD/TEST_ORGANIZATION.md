# Test Organization Strategy

## Overview

Clear separation of test types ensures:
- Fast feedback loops for developers
- Reliable CI/CD pipelines
- Easy test maintenance
- Appropriate test coverage at each level

## Test Categories

### 1. Unit Tests
**Purpose**: Test individual functions/classes in isolation
**Speed**: Fast (< 1 second per test)
**Dependencies**: None (mocked)
**Run**: On every commit, pre-commit hooks

**Characteristics**:
- No database connections
- No external API calls
- No file system operations (except temp files)
- All dependencies mocked
- Deterministic (same input = same output)

**Location**: `backend/tests/unit/`

**Examples**:
- `test_auth.py` - Auth logic without real Cognito
- `test_validators.py` - Input validation functions
- `test_utils.py` - Utility functions
- `test_models.py` - Data model logic

### 2. Integration Tests
**Purpose**: Test component interactions with real dependencies
**Speed**: Medium (1-10 seconds per test)
**Dependencies**: Database, file system, internal services
**Run**: On PR, before merge

**Characteristics**:
- Real database connections (test database)
- Real file system operations
- Internal service calls
- May require test data setup
- Should be idempotent (can run multiple times)

**Location**: `backend/tests/integration/`

**Examples**:
- `test_database_operations.py` - Real DB queries
- `test_file_processing.py` - PDF parsing with real files
- `test_pattern_analysis.py` - Pattern detection with test data
- `test_tenant_filtering.py` - Multi-tenant data isolation

### 3. API Tests
**Purpose**: Test HTTP endpoints with authentication
**Speed**: Medium-Slow (2-15 seconds per test)
**Dependencies**: Running Flask app, database, auth service
**Run**: On PR, in CI pipeline

**Characteristics**:
- Requires running Flask application
- Real HTTP requests
- Authentication/authorization testing
- May require mock external services (Cognito, S3)

**Location**: `backend/tests/api/`

**Examples**:
- `test_reporting_routes.py` - Report endpoints
- `test_duplicate_api.py` - Duplicate detection API
- `test_str_routes.py` - STR booking endpoints

### 4. End-to-End (E2E) Tests
**Purpose**: Test complete user workflows
**Speed**: Slow (10-60 seconds per test)
**Dependencies**: Full stack (frontend + backend + database)
**Run**: Nightly, before release

**Characteristics**:
- Browser automation (Selenium/Playwright)
- Full application stack running
- Real user scenarios
- Tests critical business flows

**Location**: `backend/tests/e2e/` or `frontend/tests/e2e/`

**Examples**:
- User login → upload invoice → approve transaction
- Generate report → export CSV → verify data
- Multi-tenant user switching workflows

### 5. Performance Tests
**Purpose**: Measure and validate performance metrics
**Speed**: Variable (depends on test)
**Dependencies**: Production-like environment
**Run**: On-demand, before release

**Characteristics**:
- Load testing
- Stress testing
- Benchmark comparisons
- Should not block CI pipeline (too flaky)

**Location**: `backend/tests/performance/`

**Examples**:
- `test_scalability_10x.py` - 10x load testing
- `test_query_performance.py` - Database query benchmarks
- `test_cache_performance.py` - Cache hit rate testing

## Pytest Markers

Use pytest markers to categorize tests:

```python
# Unit test (default - no marker needed)
def test_calculate_total():
    assert calculate_total([1, 2, 3]) == 6

# Integration test
@pytest.mark.integration
def test_database_query():
    db = DatabaseManager()
    result = db.execute_query("SELECT * FROM users")
    assert len(result) > 0

# API test
@pytest.mark.api
def test_login_endpoint(client):
    response = client.post('/api/login', json={'email': 'test@example.com'})
    assert response.status_code == 200

# E2E test
@pytest.mark.e2e
def test_invoice_workflow(browser):
    browser.login('user@example.com')
    browser.upload_invoice('test.pdf')
    assert browser.find_element('.success-message')

# Performance test
@pytest.mark.performance
@pytest.mark.skip(reason="Run manually or in nightly builds")
def test_load_handling():
    # Load test code
    pass

# Slow test
@pytest.mark.slow
def test_large_dataset_processing():
    # Takes > 30 seconds
    pass
```

## Running Tests

### Local Development
```bash
# Run only unit tests (fast feedback)
pytest tests/unit/

# Run unit + integration tests
pytest tests/unit/ tests/integration/

# Run specific marker
pytest -m "not slow"
pytest -m integration
pytest -m api
```

### CI Pipeline
```bash
# Stage 1: Unit tests (must pass)
pytest tests/unit/ -v --tb=short

# Stage 2: Integration tests (must pass)
pytest tests/integration/ -v --tb=short

# Stage 3: API tests (must pass)
pytest tests/api/ -m "not slow" -v --tb=short

# Stage 4: E2E tests (optional, can warn)
pytest tests/e2e/ -v --tb=short || echo "E2E tests failed (non-blocking)"
```

### Pre-commit Hook
```bash
# Only run fast unit tests
pytest tests/unit/ -x --tb=short
```

## Directory Structure

```
backend/
├── tests/
│   ├── unit/                    # Unit tests (fast, isolated)
│   │   ├── test_auth.py
│   │   ├── test_validators.py
│   │   ├── test_utils.py
│   │   └── test_models.py
│   │
│   ├── integration/             # Integration tests (medium speed)
│   │   ├── test_database_operations.py
│   │   ├── test_file_processing.py
│   │   ├── test_pattern_analysis.py
│   │   └── test_tenant_filtering.py
│   │
│   ├── api/                     # API tests (requires running app)
│   │   ├── test_reporting_routes.py
│   │   ├── test_duplicate_api.py
│   │   ├── test_str_routes.py
│   │   └── test_auth_endpoints.py
│   │
│   ├── e2e/                     # End-to-end tests (full stack)
│   │   ├── test_invoice_workflow.py
│   │   ├── test_report_generation.py
│   │   └── test_user_management.py
│   │
│   ├── performance/             # Performance tests (manual/nightly)
│   │   ├── test_scalability.py
│   │   ├── test_query_performance.py
│   │   └── test_cache_performance.py
│   │
│   ├── fixtures/                # Shared test fixtures
│   │   ├── conftest.py
│   │   ├── database_fixtures.py
│   │   └── auth_fixtures.py
│   │
│   └── conftest.py              # Root conftest with markers
```

## pytest.ini Configuration

```ini
[pytest]
# Test discovery
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, isolated, no external dependencies)
    integration: Integration tests (database, file system)
    api: API tests (requires running Flask app)
    e2e: End-to-end tests (full stack, browser automation)
    performance: Performance tests (load, stress, benchmarks)
    slow: Tests that take > 10 seconds
    skip_ci: Skip in CI pipeline (manual testing only)

# Test output
addopts = 
    -v
    --strict-markers
    --tb=short
    --disable-warnings
    
# Coverage
testpaths = tests
```

## CI Pipeline Configuration

### Stage 1: Unit Tests (Required)
- **Run**: On every commit
- **Timeout**: 2 minutes
- **Pass Rate**: 100% required
- **Command**: `pytest tests/unit/ -v`

### Stage 2: Integration Tests (Required)
- **Run**: On PR
- **Timeout**: 10 minutes
- **Pass Rate**: 95% required
- **Command**: `pytest tests/integration/ -v`

### Stage 3: API Tests (Required)
- **Run**: On PR
- **Timeout**: 15 minutes
- **Pass Rate**: 95% required
- **Command**: `pytest tests/api/ -m "not slow" -v`

### Stage 4: E2E Tests (Optional)
- **Run**: Nightly or pre-release
- **Timeout**: 30 minutes
- **Pass Rate**: 90% required (can warn)
- **Command**: `pytest tests/e2e/ -v`

### Stage 5: Performance Tests (Manual)
- **Run**: On-demand or weekly
- **Timeout**: 60 minutes
- **Pass Rate**: N/A (informational)
- **Command**: `pytest tests/performance/ -v`

## Migration Plan

### Phase 1: Reorganize Existing Tests
1. Create new directory structure
2. Move tests to appropriate directories
3. Add pytest markers to all tests
4. Update imports

### Phase 2: Fix Test Issues
1. Fix unit tests to not require external dependencies
2. Add proper mocking to unit tests
3. Ensure integration tests use test database
4. Add authentication fixtures for API tests

### Phase 3: Update CI Pipeline
1. Update build.ps1 to run tests by category
2. Set appropriate pass rate thresholds
3. Add stage-specific timeouts
4. Configure parallel test execution

### Phase 4: Documentation
1. Document test writing guidelines
2. Create test templates
3. Add examples for each test type
4. Update contributing guide

## Best Practices

### Unit Tests
- ✅ Test one thing at a time
- ✅ Use descriptive test names
- ✅ Mock all external dependencies
- ✅ Keep tests under 1 second
- ❌ Don't access database
- ❌ Don't make HTTP requests
- ❌ Don't read/write files (except temp)

### Integration Tests
- ✅ Test component interactions
- ✅ Use test database
- ✅ Clean up after each test
- ✅ Make tests idempotent
- ❌ Don't test external APIs (mock them)
- ❌ Don't rely on specific data (create test data)

### API Tests
- ✅ Test complete request/response cycle
- ✅ Test authentication/authorization
- ✅ Test error handling
- ✅ Use test client fixtures
- ❌ Don't test business logic (that's unit tests)
- ❌ Don't make real external API calls

### Performance Tests
- ✅ Establish baseline metrics
- ✅ Test with realistic data volumes
- ✅ Measure and log results
- ✅ Make tests repeatable
- ❌ Don't block CI pipeline
- ❌ Don't use production data

## Example Test Files

### Unit Test Example
```python
# tests/unit/test_validators.py
import pytest
from src.validators import validate_email, validate_amount

class TestEmailValidator:
    """Unit tests for email validation"""
    
    def test_valid_email(self):
        assert validate_email("user@example.com") is True
    
    def test_invalid_email_no_at(self):
        assert validate_email("userexample.com") is False
    
    def test_invalid_email_no_domain(self):
        assert validate_email("user@") is False
    
    @pytest.mark.parametrize("email", [
        "user@example.com",
        "user.name@example.co.uk",
        "user+tag@example.com"
    ])
    def test_valid_email_formats(self, email):
        assert validate_email(email) is True
```

### Integration Test Example
```python
# tests/integration/test_database_operations.py
import pytest
from src.database import DatabaseManager

@pytest.mark.integration
class TestDatabaseOperations:
    """Integration tests for database operations"""
    
    @pytest.fixture
    def db(self):
        """Create test database connection"""
        db = DatabaseManager(test_mode=True)
        yield db
        db.close()
    
    def test_insert_and_retrieve_user(self, db):
        # Insert test user
        user_id = db.execute_query(
            "INSERT INTO users (email, name) VALUES (%s, %s)",
            ("test@example.com", "Test User"),
            fetch=False,
            commit=True
        )
        
        # Retrieve user
        result = db.execute_query(
            "SELECT * FROM users WHERE email = %s",
            ("test@example.com",)
        )
        
        assert len(result) == 1
        assert result[0]['email'] == "test@example.com"
```

### API Test Example
```python
# tests/api/test_auth_endpoints.py
import pytest
from flask import Flask

@pytest.mark.api
class TestAuthEndpoints:
    """API tests for authentication endpoints"""
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    def test_login_success(self, client, mock_cognito):
        """Test successful login"""
        response = client.post('/api/login', json={
            'email': 'user@example.com',
            'password': 'password123'
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'token' in data
        assert data['success'] is True
    
    def test_login_invalid_credentials(self, client, mock_cognito):
        """Test login with invalid credentials"""
        response = client.post('/api/login', json={
            'email': 'user@example.com',
            'password': 'wrongpassword'
        })
        
        assert response.status_code == 401
        data = response.get_json()
        assert data['success'] is False
```

## Summary

This organization provides:
1. **Clear separation** of test types
2. **Fast feedback** for developers (unit tests)
3. **Reliable CI** (appropriate tests at each stage)
4. **Easy maintenance** (tests in logical locations)
5. **Flexible execution** (run what you need, when you need it)

The key is to run the right tests at the right time:
- **Unit tests**: Every commit (< 2 min)
- **Integration tests**: Every PR (< 10 min)
- **API tests**: Every PR (< 15 min)
- **E2E tests**: Nightly/pre-release (< 30 min)
- **Performance tests**: On-demand (informational)
