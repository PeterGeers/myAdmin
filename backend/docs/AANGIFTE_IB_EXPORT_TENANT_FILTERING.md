# Aangifte IB Export - Tenant Filtering Implementation

## Overview

Implemented tenant filtering for the `/api/reports/aangifte-ib-export` endpoint to ensure users can only export data from administrations they have access to.

## Changes Made

### 1. Updated Endpoint (`backend/src/app.py`)

#### Added `@tenant_required()` Decorator

```python
@app.route('/api/reports/aangifte-ib-export', methods=['POST'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()  # ✅ ADDED
def aangifte_ib_export(user_email, user_roles, tenant, user_tenants):  # ✅ ADDED tenant, user_tenants
```

#### Updated Function Signature

- Added `tenant` parameter (injected by `@tenant_required()`)
- Added `user_tenants` parameter (injected by `@tenant_required()`)

#### Added Administration Validation

```python
# Default to current tenant if not specified
administration = data.get('administration', tenant)

# Validate user has access to requested administration
if administration != 'all' and administration not in user_tenants:
    return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
```

#### Updated Cache Query Call

```python
# SECURITY: Pass user_tenants to filter cached data
details = cache.query_aangifte_ib_details(year, administration, parent, aangifte, user_tenants)
```

### 2. Created Tests (`backend/tests/api/test_aangifte_ib_export_tenant.py`)

Created comprehensive tests to verify:

- ✅ Endpoint exists and is registered
- ✅ `@tenant_required()` decorator is applied (checks for `tenant` and `user_tenants` parameters)
- ✅ Administration is validated against `user_tenants`
- ✅ Administration defaults to current tenant
- ✅ `user_tenants` is passed to cache query method

All 5 tests pass successfully.

### 3. Updated Checklist (`.kiro/specs/FIN/Reports/TENANT_FILTERING_CHECKLIST.md`)

Marked task 21 as complete:

```markdown
- [x] 21. `/api/reports/aangifte-ib-export` - ✅ Has @tenant_required() and validates administration
```

## Security Features

### 1. Tenant Context Enforcement

The `@tenant_required()` decorator:

- Extracts tenant from `X-Tenant` header or JWT
- Validates user has access to the tenant
- Injects `tenant` and `user_tenants` into the route function

### 2. Administration Validation

- Validates requested administration against user's accessible tenants
- Returns 403 Forbidden if user tries to access unauthorized administration
- Defaults to current tenant if no administration specified

### 3. Cache Data Filtering

- Passes `user_tenants` to `cache.query_aangifte_ib_details()`
- Cache method filters data by `user_tenants` before processing
- Ensures no cross-tenant data leakage

## Testing

Run the tests with:

```bash
cd backend
python -m pytest tests/api/test_aangifte_ib_export_tenant.py -v
```

Expected output:

```
tests/api/test_aangifte_ib_export_tenant.py::TestAangifteIBExportTenantFiltering::test_aangifte_ib_export_endpoint_exists PASSED
tests/api/test_aangifte_ib_export_tenant.py::TestAangifteIBExportTenantFiltering::test_aangifte_ib_export_has_tenant_decorator PASSED
tests/api/test_aangifte_ib_export_tenant.py::TestAangifteIBExportTenantFiltering::test_aangifte_ib_export_validates_administration PASSED
tests/api/test_aangifte_ib_export_tenant.py::TestAangifteIBExportTenantFiltering::test_aangifte_ib_export_defaults_to_tenant PASSED
tests/api/test_aangifte_ib_export_tenant.py::TestAangifteIBExportTenantFiltering::test_aangifte_ib_export_passes_user_tenants_to_cache PASSED

5 passed
```

## Implementation Pattern

This implementation follows the same pattern as other tenant-filtered endpoints:

1. **Add decorator**: `@tenant_required()`
2. **Update signature**: Add `tenant, user_tenants` parameters
3. **Validate access**: Check `administration in user_tenants`
4. **Filter data**: Pass `user_tenants` to cache/query methods
5. **Test**: Verify decorator, validation, and filtering

## Next Steps

Continue with remaining tasks in the checklist:

- Task 22: `/api/reports/aangifte-ib-xlsx-export`
- Task 23: `/api/reports/aangifte-ib-xlsx-export-stream`

Both follow the same pattern as this implementation.
