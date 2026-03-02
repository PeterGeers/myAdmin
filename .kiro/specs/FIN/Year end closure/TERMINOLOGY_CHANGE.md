# Terminology Change: "Role" → "Purpose"

**Date**: 2026-03-02  
**Status**: ✅ Complete  
**Reason**: Avoid confusion with user roles/permissions

## Problem

The original implementation used "role" to describe the function an account serves in year-end closure:

- `parameters: {"role": "equity_result"}`
- UI labels: "Account Role", "Role" column

This was confusing because "role" is also used for user permissions (Tenant_Admin, Finance_CRUD, etc.).

## Solution

Changed terminology from "role" to "purpose" throughout the codebase:

- `parameters: {"purpose": "equity_result"}`
- UI labels: "Account Purpose", "Purpose" column

## Why "Purpose"?

"Purpose" is the clearest English term because:

- Immediately understandable: "What is this account's purpose?"
- No confusion with user roles/permissions
- Natural fit in UI: "Account Purpose" column
- Accounting-appropriate terminology

## Changes Made

### Backend

**Files Modified**:

- `backend/src/services/year_end_config.py`
  - `REQUIRED_ROLES` → `REQUIRED_PURPOSES`
  - `get_account_by_role()` → `get_account_by_purpose()`
  - `set_account_role()` → `set_account_purpose()`
  - `remove_account_role()` → `remove_account_purpose()`
  - `get_all_configured_roles()` → `get_all_configured_purposes()`
  - All JSON queries: `'$.role'` → `'$.purpose'`

- `backend/src/routes/year_end_config_routes.py`
  - `/api/tenant-admin/year-end-config/roles` → `/api/tenant-admin/year-end-config/purposes`
  - Request/response fields: `role` → `purpose`
  - `configured_roles` → `configured_purposes`
  - `required_roles` → `required_purposes`

- `backend/src/routes/chart_of_accounts_routes.py`
  - Query: `JSON_EXTRACT(parameters, '$.role')` → `JSON_EXTRACT(parameters, '$.purpose')`

### Frontend

**Files Modified**:

- `frontend/src/types/chartOfAccounts.ts`
  - `role?: string` → `purpose?: string`

- `frontend/src/services/yearEndConfigService.ts`
  - `YearEndRole` → `YearEndPurpose`
  - `RequiredRole` → `RequiredPurpose`
  - `configured_roles` → `configured_purposes`
  - `required_roles` → `required_purposes`
  - `getConfiguredRoles()` → `getConfiguredPurposes()`
  - `setAccountRole()` → `setAccountPurpose()`
  - `current_role` → `current_purpose`

- `frontend/src/components/TenantAdmin/ChartOfAccounts.tsx`
  - State: `role: ''` → `purpose: ''`
  - Column header: "Role" → "Purpose"
  - Filter label: "Role" → "Purpose"
  - Badge display: `account.role` → `account.purpose`

- `frontend/src/components/TenantAdmin/YearEndSettings.tsx`
  - `requiredRoles` → `requiredPurposes`
  - `getRoleDisplayName()` → `getPurposeDisplayName()`
  - `getConfiguredRoles()` → `getConfiguredPurposes()`
  - `setAccountRole()` → `setAccountPurpose()`
  - All variable names and comments updated

### Database

**No migration needed** - The `parameters` column was empty, so we changed the JSON key before any data was stored:

- Before: `{"role": "equity_result"}`
- After: `{"purpose": "equity_result"}`

## API Changes

### Old Endpoints (removed):

```
GET  /api/tenant-admin/year-end-config/roles
POST /api/tenant-admin/year-end-config/accounts (with "role" field)
```

### New Endpoints:

```
GET  /api/tenant-admin/year-end-config/purposes
POST /api/tenant-admin/year-end-config/accounts (with "purpose" field)
```

### Request/Response Format Change:

**Old**:

```json
{
  "account_code": "3080",
  "role": "equity_result"
}
```

**New**:

```json
{
  "account_code": "3080",
  "purpose": "equity_result"
}
```

## UI Changes

### Chart of Accounts

**Before**:

```
┌─────────┬──────────────────┬─────┬──────────────┐
│ Account │ Name             │ VW  │ Role         │
├─────────┼──────────────────┼─────┼──────────────┤
│ 3080    │ Equity           │ N   │ equity_result│
└─────────┴──────────────────┴─────┴──────────────┘
```

**After**:

```
┌─────────┬──────────────────┬─────┬──────────────┐
│ Account │ Name             │ VW  │ Purpose      │
├─────────┼──────────────────┼─────┼──────────────┤
│ 3080    │ Equity           │ N   │ equity_result│
└─────────┴──────────────────┴─────┴──────────────┘
```

### Year-End Settings

**Before**: "Configure accounts for year-end closure process. All three roles must be assigned."

**After**: "Configure accounts for year-end closure process. All three purposes must be assigned."

## Documentation Updates Needed

The following documentation files should be updated to reflect the terminology change:

- [ ] `backend/docs/guides/YEAR_END_CONFIGURATION.md`
- [ ] `.kiro/specs/FIN/Year end closure/PHASE1_COMPLETE.md`
- [ ] `.kiro/specs/FIN/Year end closure/PHASE1_UI_COMPLETE.md`
- [ ] `.kiro/specs/FIN/Year end closure/design-closure.md`
- [ ] `.kiro/specs/FIN/Year end closure/requirements.md`

## Testing Checklist

- [ ] Backend API endpoints respond correctly
- [ ] Frontend displays "Purpose" instead of "Role"
- [ ] Configuration can be saved and loaded
- [ ] Validation works correctly
- [ ] Chart of Accounts shows purpose column
- [ ] Filter by purpose works

## Summary

Successfully changed terminology from "role" to "purpose" throughout the year-end closure feature. This change:

- ✅ Eliminates confusion with user roles/permissions
- ✅ Uses clearer, more intuitive terminology
- ✅ Made before any data was stored (no migration needed)
- ✅ Consistent across backend, frontend, and database
- ✅ Improves code readability and maintainability

The term "purpose" better describes what the parameter represents: the function or purpose that an account serves in the year-end closure process.
