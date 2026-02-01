# Integration Tests Guide

## Template Management Integration Tests

**Purpose:** Test end-to-end workflows with real database and Google Drive integration

---

## Overview

Integration tests verify that all components work together correctly in a real environment:

- ✅ Full preview generation flow (upload → validate → preview)
- ✅ Approval workflow (approve → save to Drive → update DB)
- ✅ AI help flow (request → sanitize → call API → parse response)
- ✅ Tenant isolation (cannot access other tenant's data)
- ✅ Real database and Google Drive integration

---

## Prerequisites

### 1. Test Database

```bash
# Ensure test database is running
# Connection details in .env file:
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=testfinance  # Use test database, not production!
```

### 2. Google Drive Credentials

```bash
# Ensure Google Drive credentials are configured
# credentials.json should be in backend/ directory
GOOGLE_DRIVE_CREDENTIALS=path/to/credentials.json
```

### 3. OpenRouter API Key (for AI tests)

```bash
# Set in .env file:
OPENROUTER_API_KEY=your_api_key_here
```

### 4. Test Tenant Configuration

```bash
# Set test tenant in .env file:
TEST_ADMINISTRATION=TestTenant
TEST_USER_EMAIL=test@example.com
```

---

## Running Integration Tests

### Run All Integration Tests

```bash
cd backend
python -m pytest tests/integration/test_template_management_integration.py -v -s
```

### Run Specific Test Class

```bash
# Test preview generation flow
python -m pytest tests/integration/test_template_management_integration.py::TestPreviewGenerationFlow -v -s

# Test approval workflow
python -m pytest tests/integration/test_template_management_integration.py::TestApprovalWorkflow -v -s

# Test AI help flow
python -m pytest tests/integration/test_template_management_integration.py::TestAIHelpFlow -v -s

# Test tenant isolation
python -m pytest tests/integration/test_template_management_integration.py::TestTenantIsolation -v -s

# Test database integration
python -m pytest tests/integration/test_template_management_integration.py::TestRealDatabaseIntegration -v -s
```

### Run Specific Test Method

```bash
python -m pytest tests/integration/test_template_management_integration.py::TestPreviewGenerationFlow::test_preview_generation_with_valid_template -v -s
```

### Skip Tests Requiring External Services

```bash
# Skip tests that require Google Drive
python -m pytest tests/integration/test_template_management_integration.py -v -s -m "not google_drive"

# Skip tests that require OpenRouter API
python -m pytest tests/integration/test_template_management_integration.py -v -s -k "not ai_help"
```

---

## Test Classes

### 1. TestPreviewGenerationFlow

**Tests:** Full preview generation workflow

**Test Methods:**

- `test_preview_generation_with_valid_template` - Valid template preview
- `test_preview_generation_with_invalid_template` - Invalid template rejection
- `test_preview_generation_with_security_issues` - Security validation
- `test_preview_generation_all_template_types` - All 5 template types

**Requirements:**

- ✅ Database connection
- ❌ Google Drive (not required)
- ❌ OpenRouter API (not required)

**Expected Output:**

```
✅ Preview generated successfully
   Data source: database
   Validation: 0 errors, 1 warnings
```

### 2. TestApprovalWorkflow

**Tests:** Template approval and Google Drive integration

**Test Methods:**

- `test_approval_workflow_complete` - Full approval flow
- `test_approval_workflow_validation_failure` - Rejection of invalid templates
- `test_approval_workflow_version_management` - Version management

**Requirements:**

- ✅ Database connection
- ✅ Google Drive credentials
- ❌ OpenRouter API (not required)

**Expected Output:**

```
✅ Template approved and saved to Google Drive
   File ID: 1abc...xyz
   Filename: str_invoice_nl_v1.html
   Created: 2026-02-01T10:30:00.000Z
   ✓ Test file cleaned up
```

**Note:** Tests automatically clean up created files

### 3. TestAIHelpFlow

**Tests:** AI-powered template assistance

**Test Methods:**

- `test_ai_help_flow_complete` - Full AI help workflow
- `test_ai_help_sanitization` - PII sanitization
- `test_ai_help_without_api_key` - Graceful API key handling

**Requirements:**

- ✅ Database connection (for usage tracking)
- ❌ Google Drive (not required)
- ✅ OpenRouter API key

**Expected Output:**

```
✅ AI help flow completed successfully
   Tokens used: 1250
   Model used: google/gemini-flash-1.5
   Analysis: The template is missing several required placeholders...
   Fixes suggested: 6
   Fix 1: Missing placeholder 'invoice_number'
          (auto-fixable)
```

### 4. TestTenantIsolation

**Tests:** Multi-tenant data isolation

**Test Methods:**

- `test_tenant_isolation_sample_data` - Sample data isolation
- `test_tenant_isolation_google_drive` - Google Drive folder separation
- `test_tenant_isolation_validation_logging` - Logging isolation

**Requirements:**

- ✅ Database connection
- ✅ Google Drive credentials (for some tests)
- ❌ OpenRouter API (not required)

**Expected Output:**

```
✅ Tenant isolation verified for sample data
   Tenant1 data source: database
   Tenant2 data source: database
```

### 5. TestRealDatabaseIntegration

**Tests:** Database connectivity and data fetching

**Test Methods:**

- `test_database_connection` - Basic database connectivity
- `test_sample_data_from_database` - Real data fetching

**Requirements:**

- ✅ Database connection
- ❌ Google Drive (not required)
- ❌ OpenRouter API (not required)

**Expected Output:**

```
✅ Database connection verified
✅ Sample data fetched from: database
   Using real database data
   Record ID: RES-2026-001
```

---

## Test Fixtures

### Database Fixtures

- `db_manager` - DatabaseManager instance (module scope)
- `template_service` - TemplatePreviewService instance (module scope)
- `ai_assistant` - AITemplateAssistant instance (module scope)

### Template Fixtures

- `valid_str_invoice_template` - Valid STR invoice template
- `invalid_template_missing_placeholders` - Invalid template (missing placeholders)
- `invalid_template_with_script` - Invalid template (security issues)

---

## Environment Variables

### Required

```bash
# Database
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=testfinance

# Test Configuration
TEST_ADMINISTRATION=TestTenant
TEST_USER_EMAIL=test@example.com
```

### Optional (for specific tests)

```bash
# Google Drive (required for approval workflow tests)
GOOGLE_DRIVE_CREDENTIALS=path/to/credentials.json

# OpenRouter API (required for AI help tests)
OPENROUTER_API_KEY=your_api_key_here
```

---

## Test Markers

Tests use pytest markers to indicate requirements:

```python
@pytest.mark.skipif(
    not os.getenv('GOOGLE_DRIVE_CREDENTIALS'),
    reason="Google Drive credentials not configured"
)
def test_approval_workflow_complete(...):
    # Test code
```

**Available Markers:**

- Tests requiring Google Drive are automatically skipped if credentials not configured
- Tests requiring OpenRouter API are automatically skipped if API key not set

---

## Troubleshooting

### Database Connection Errors

```
Error: Can't connect to MySQL server
```

**Solution:**

1. Verify database is running: `docker ps` or check MySQL service
2. Check connection details in `.env` file
3. Ensure test database exists: `CREATE DATABASE IF NOT EXISTS testfinance;`
4. Verify user has permissions: `GRANT ALL ON testfinance.* TO 'user'@'localhost';`

### Google Drive Errors

```
Error: Invalid credentials
```

**Solution:**

1. Verify `credentials.json` exists in `backend/` directory
2. Ensure credentials are valid and not expired
3. Check Google Drive API is enabled in Google Cloud Console
4. Verify service account has access to tenant folders

### OpenRouter API Errors

```
Error: AI service not configured
```

**Solution:**

1. Set `OPENROUTER_API_KEY` in `.env` file
2. Verify API key is valid
3. Check API quota/limits
4. Ensure network connectivity to OpenRouter API

### Tenant Isolation Errors

```
Error: Tenant data not found
```

**Solution:**

1. Verify `TEST_ADMINISTRATION` is set correctly
2. Ensure test tenant exists in database
3. Check tenant has sample data (or tests will use placeholders)
4. Verify tenant folder exists in Google Drive

---

## Best Practices

### 1. Use Test Database

**Always use a separate test database, never production!**

```bash
# Good
DB_NAME=testfinance

# Bad - DO NOT USE
DB_NAME=finance  # Production database!
```

### 2. Clean Up Test Data

Tests automatically clean up created files, but verify:

```bash
# Check for orphaned test files in Google Drive
# Look for files with "Integration test" in notes
```

### 3. Run Tests in Isolation

Run integration tests separately from unit tests:

```bash
# Unit tests (fast, no external dependencies)
pytest tests/unit/ -v

# Integration tests (slower, requires external services)
pytest tests/integration/ -v -s
```

### 4. Monitor API Usage

AI help tests consume API tokens:

```bash
# Check token usage after tests
# Look for log entries with token counts
```

### 5. Verify Test Environment

Before running tests, verify environment:

```bash
# Check database connection
python -c "from database import DatabaseManager; db = DatabaseManager(); print('✅ Database OK')"

# Check Google Drive credentials
python -c "from google_drive_service import GoogleDriveService; g = GoogleDriveService('TestTenant'); print('✅ Google Drive OK')"

# Check OpenRouter API
python -c "import os; print('✅ API Key OK' if os.getenv('OPENROUTER_API_KEY') else '❌ API Key Missing')"
```

---

## Expected Test Results

### All Tests Passing

```
tests/integration/test_template_management_integration.py::TestPreviewGenerationFlow::test_preview_generation_with_valid_template PASSED
tests/integration/test_template_management_integration.py::TestPreviewGenerationFlow::test_preview_generation_with_invalid_template PASSED
tests/integration/test_template_management_integration.py::TestPreviewGenerationFlow::test_preview_generation_with_security_issues PASSED
tests/integration/test_template_management_integration.py::TestPreviewGenerationFlow::test_preview_generation_all_template_types PASSED
tests/integration/test_template_management_integration.py::TestApprovalWorkflow::test_approval_workflow_complete PASSED
tests/integration/test_template_management_integration.py::TestApprovalWorkflow::test_approval_workflow_validation_failure PASSED
tests/integration/test_template_management_integration.py::TestApprovalWorkflow::test_approval_workflow_version_management PASSED
tests/integration/test_template_management_integration.py::TestAIHelpFlow::test_ai_help_flow_complete PASSED
tests/integration/test_template_management_integration.py::TestAIHelpFlow::test_ai_help_sanitization PASSED
tests/integration/test_template_management_integration.py::TestAIHelpFlow::test_ai_help_without_api_key PASSED
tests/integration/test_template_management_integration.py::TestTenantIsolation::test_tenant_isolation_sample_data PASSED
tests/integration/test_template_management_integration.py::TestTenantIsolation::test_tenant_isolation_google_drive PASSED
tests/integration/test_template_management_integration.py::TestTenantIsolation::test_tenant_isolation_validation_logging PASSED
tests/integration/test_template_management_integration.py::TestRealDatabaseIntegration::test_database_connection PASSED
tests/integration/test_template_management_integration.py::TestRealDatabaseIntegration::test_sample_data_from_database PASSED

======================== 15 passed in 12.34s ========================
```

### Some Tests Skipped (Missing Credentials)

```
tests/integration/test_template_management_integration.py::TestApprovalWorkflow::test_approval_workflow_complete SKIPPED (Google Drive credentials not configured)
tests/integration/test_template_management_integration.py::TestAIHelpFlow::test_ai_help_flow_complete SKIPPED (OpenRouter API key not configured)

======================== 10 passed, 5 skipped in 5.67s ========================
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest

    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: testpass
          MYSQL_DATABASE: testfinance
        ports:
          - 3306:3306

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run integration tests
        env:
          DB_HOST: 127.0.0.1
          DB_USER: root
          DB_PASSWORD: testpass
          DB_NAME: testfinance
          TEST_ADMINISTRATION: TestTenant
          TEST_USER_EMAIL: test@example.com
        run: |
          cd backend
          pytest tests/integration/test_template_management_integration.py -v -s
```

---

## Summary

Integration tests provide confidence that:

- ✅ All components work together correctly
- ✅ Database operations are successful
- ✅ Google Drive integration works
- ✅ AI assistance functions properly
- ✅ Tenant isolation is maintained
- ✅ End-to-end workflows complete successfully

**Total Tests:** 15 integration tests  
**Execution Time:** ~10-15 seconds (depending on external services)  
**Coverage:** End-to-end workflows and real service integration

---

**Created:** February 1, 2026  
**Author:** Kiro AI Assistant  
**Project:** Template Management Integration Tests
