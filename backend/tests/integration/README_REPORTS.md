# Integration Test Reports - Scope Guide

**⚠️ IMPORTANT**: Each report in this directory covers **SPECIFIC** tests, not all integration tests.

## Report Inventory

### Phase 1: Credentials Infrastructure

1. **test_tenant_credentials_table_results.md**
   - **Scope**: ONLY `test_tenant_credentials_table.py` (8 tests)
   - **Purpose**: Validates tenant_credentials table structure and operations
   - **Phase**: Phase 1.1 - Database Schema

2. **CREDENTIAL_ROTATION_TEST_SUMMARY.md**
   - **Scope**: ONLY `test_credential_rotation.py` (7 tests)
   - **Purpose**: Validates credential rotation functionality
   - **Phase**: Phase 1.6 - Testing credential rotation

3. **CREDENTIAL_ROTATION_QUICK_REFERENCE.md**
   - **Scope**: Quick reference for credential rotation tests
   - **Purpose**: Condensed version of CREDENTIAL_ROTATION_TEST_SUMMARY.md

4. **GOOGLE_DRIVE_TENANT_ACCESS_TEST_SUMMARY.md**
   - **Scope**: ONLY `test_google_drive_real_access.py`
   - **Purpose**: Validates Google Drive access with real credentials
   - **Phase**: Phase 1.6 - Testing Google Drive access

5. **GOOGLE_DRIVE_TENANT_TESTING_SUMMARY.md**
   - **Scope**: ONLY `test_google_drive_service_tenants.py`
   - **Purpose**: Validates GoogleDriveService tenant isolation
   - **Phase**: Phase 1.6 - Testing tenant isolation

### Phase 2: Template Management

6. **TEMPLATE_SERVICE_FETCH_TEST_SUMMARY.md**
   - **Scope**: ONLY template fetching tests from `test_template_service_integration.py`
   - **Purpose**: Validates template fetching from Google Drive
   - **Phase**: Phase 2 - Template Management

### Other Tests (No Reports Yet)

The following integration test files **DO NOT** have dedicated reports:

- test_aangifte_ib_generator_integration.py
- test_account_summary_tenant_filtering.py
- test_duplicate_integration_e2e.py
- test_duplicate_system_comprehensive.py
- test_invoice_upload_tenant.py
- test_multi_tenant_scenarios.py
- test_multitenant_phase5.py
- test_payout_real_file.py
- test_payout_upload_manual.py
- test_reference_requirement_validation.py
- test_scalability_10x.py
- test_str_invoice_generation.py
- test_str_invoice_simple.py
- test_str_invoice_template_integration.py
- test_str_invoice_tenant_filtering.py
- test_tenant_filtering_comprehensive.py
- test_tenant_filtering_performance.py
- test_toeristenbelasting_template_integration.py
- test_tourist_tax_rates.py

## How to Read Reports

Each report documents:

1. **Specific test file(s)** it covers
2. **Number of tests** validated
3. **Test results** (pass/fail)
4. **Compliance** with test organization standards
5. **Phase/task** in Railway migration

## Creating New Reports

When creating a new test report:

1. Use a descriptive name that indicates the specific test(s) covered
2. Add a **⚠️ SCOPE NOTICE** section at the top
3. Clearly state which test file(s) are covered
4. Update this README with the new report

## Running All Integration Tests

To run ALL integration tests (not just those with reports):

```bash
pytest backend/tests/integration/ -v -m integration
```

To run a specific test file:

```bash
pytest backend/tests/integration/test_<name>.py -v -m integration
```
