# Aangifte IB Details Tenant Filtering Implementation

## Overview

Implemented tenant filtering for the `/api/reports/aangifte-ib-details` endpoint to ensure users can only access data from administrations they have permission to view.

## Changes Made

### 1. Updated Endpoint (`backend/src/app.py`)

- Added `@tenant_required()` decorator to the `aangifte_ib_details` function
- Added `tenant` and `user_tenants` parameters to function signature
- Changed default administration from `'all'` to `tenant` (current tenant)
- Added validation to ensure user has access to requested administration
- Added security filtering of cached data by `user_tenants` before processing
- Updated cache method call to pass `user_tenants` parameter

### 2. Updated Cache Method (`backend/src/mutaties_cache.py`)

- Modified `query_aangifte_ib_details` method to accept optional `user_tenants` parameter
- Added security filtering at the beginning of the method to filter by `user_tenants`
- Updated docstring to document the new parameter

### 3. Added Tests (`backend/tests/api/test_aangifte_ib_details_tenant.py`)

Created comprehensive tests to verify:

- Endpoint exists and is properly registered
- `@tenant_required()` decorator is applied (checks for `tenant` and `user_tenants` parameters)
- Administration validation is implemented
- Cache method accepts and uses `user_tenants` parameter
- Data is filtered by user's accessible tenants

## Security Implementation

### Endpoint Level

```python
# Validate user has access to requested administration
if administration not in user_tenants:
    return jsonify({'success': False, 'error': 'Access denied to administration'}), 403

# SECURITY: Filter by user's accessible tenants
df = df[df['Administration'].isin(user_tenants)]
```

### Cache Level

```python
# SECURITY: Filter by user's accessible tenants first
if user_tenants is not None:
    df = df[df['Administration'].isin(user_tenants)]
```

## Testing Results

All 5 tests passed successfully:

- ✅ Endpoint exists
- ✅ Has @tenant_required decorator
- ✅ Validates administration access
- ✅ Cache method accepts user_tenants parameter
- ✅ Cache method filters by user_tenants

## API Behavior

### Before

- No tenant filtering
- Users could access any administration's data
- Default administration was 'all'

### After

- Strict tenant filtering enforced
- Users can only access administrations in their `user_tenants` list
- Default administration is the current tenant
- Returns 403 error if user tries to access unauthorized administration
- Data is filtered at both endpoint and cache levels for defense in depth

## Usage Example

### Authorized Request

```
GET /api/reports/aangifte-ib-details?year=2023&parent=Assets&aangifte=Balance
Headers:
  Authorization: Bearer <token>
  X-Tenant: GoodwinSolutions

Response: 200 OK (if user has access to GoodwinSolutions)
```

### Unauthorized Request

```
GET /api/reports/aangifte-ib-details?year=2023&administration=PeterPrive&parent=Assets&aangifte=Balance
Headers:
  Authorization: Bearer <token>
  X-Tenant: GoodwinSolutions

Response: 403 Forbidden (if user doesn't have access to PeterPrive)
{
  "success": false,
  "error": "Access denied to administration"
}
```

## Checklist Status

Updated `.kiro/specs/FIN/Reports/TENANT_FILTERING_CHECKLIST.md`:

- Changed status from `[-]` (in progress) to `[x]` (completed)
- Updated description to reflect implementation
