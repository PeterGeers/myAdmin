# Aangifte IB XLSX Export - Tenant Filtering Implementation

## Overview

This document describes the tenant filtering implementation for the `/api/reports/aangifte-ib-xlsx-export` endpoint.

## Changes Made

### 1. Added @tenant_required() Decorator

- Added `@tenant_required()` decorator to the `aangifte_ib_xlsx_export` function
- This decorator automatically extracts and validates tenant context from JWT tokens
- Injects `tenant` and `user_tenants` parameters into the function

### 2. Updated Function Signature

**Before:**

```python
def aangifte_ib_xlsx_export(user_email, user_roles):
```

**After:**

```python
def aangifte_ib_xlsx_export(user_email, user_roles, tenant, user_tenants):
```

### 3. Added Administration Validation

Added validation to ensure users can only export data for administrations they have access to:

```python
# Validate all requested administrations against user_tenants
unauthorized_admins = [admin for admin in administrations if admin not in user_tenants]
if unauthorized_admins:
    return jsonify({
        'success': False,
        'error': f'Access denied to administrations: {", ".join(unauthorized_admins)}'
    }), 403
```

### 4. Filtered Available Administrations

Updated the query to only show administrations the user has access to:

**Before:**

```python
cursor.execute("SELECT DISTINCT Administration FROM vw_mutaties WHERE Administration IS NOT NULL ORDER BY Administration")
```

**After:**

```python
placeholders = ', '.join(['%s'] * len(user_tenants))
query = f"SELECT DISTINCT Administration FROM vw_mutaties WHERE Administration IN ({placeholders}) ORDER BY Administration"
cursor.execute(query, user_tenants)
```

## Security Benefits

1. **Access Control**: Users can only export XLSX files for administrations they have access to
2. **Data Isolation**: Available administrations list is filtered by user's tenant access
3. **Explicit Validation**: Requests for unauthorized administrations return 403 Forbidden
4. **Consistent Pattern**: Follows the same tenant filtering pattern as other endpoints

## Testing

Created comprehensive unit tests in `backend/tests/api/test_aangifte_ib_xlsx_export_tenant.py`:

1. ✅ Endpoint exists
2. ✅ Has @tenant_required decorator
3. ✅ Validates administrations against user_tenants
4. ✅ Filters available administrations by user_tenants
5. ✅ Returns 403 for unauthorized administrations

All tests pass successfully.

## API Behavior

### Request

```json
POST /api/reports/aangifte-ib-xlsx-export
Headers:
  Authorization: Bearer <jwt_token>
  X-Tenant: GoodwinSolutions

Body:
{
  "administrations": ["GoodwinSolutions", "PeterPrive"],
  "years": [2023, 2024]
}
```

### Success Response (200)

```json
{
  "success": true,
  "results": [...],
  "available_administrations": ["GoodwinSolutions"],
  "message": "Generated 2 XLSX files out of 2 requested"
}
```

### Error Response - Unauthorized Administration (403)

```json
{
  "success": false,
  "error": "Access denied to administrations: PeterPrive"
}
```

### Error Response - Missing Parameters (400)

```json
{
  "success": false,
  "error": "Administrations and years are required"
}
```

## Related Files

- **Implementation**: `backend/src/app.py` (lines 2417-2460)
- **Tests**: `backend/tests/api/test_aangifte_ib_xlsx_export_tenant.py`
- **Decorator**: `backend/src/auth/tenant_context.py`
- **Checklist**: `.kiro/specs/FIN/Reports/TENANT_FILTERING_CHECKLIST.md`

## Next Steps

Task 23: `/api/reports/aangifte-ib-xlsx-export-stream` - Similar implementation needed for the streaming version of this endpoint.
