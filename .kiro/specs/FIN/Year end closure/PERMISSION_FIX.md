# Year-End Closure Permission Fix

**Date**: March 2, 2026  
**Issue**: "Insufficient permissions" error when trying to close year 2025  
**Status**: ✅ Fixed

## Problem

User with `Finance_CRUD` role was getting "Insufficient permissions" error when attempting to close fiscal year 2025.

**User's Roles**:

- Tenant_Admin
- Finance_Read
- STR_Read
- Finance_Export
- STR_Export
- SysAdmin
- Finance_CRUD ← Should have permission
- STR_CRUD

## Root Cause

The year-end closure API endpoint (`POST /api/year-end/close`) requires `finance_write` permission:

```python
@year_end_bp.route('/api/year-end/close', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
@tenant_required()
def close_year(user_email, user_roles, tenant, user_tenants):
```

However, the `Finance_CRUD` role in `backend/src/auth/cognito_utils.py` did NOT include `finance_write` permission.

**Before** (Finance_CRUD permissions):

```python
'Finance_CRUD': [
    'finance_create', 'finance_read', 'finance_update', 'finance_delete',
    'finance_list', 'finance_export',
    # Missing: 'finance_write'
    ...
]
```

## Solution

Added `finance_write` permission to the `Finance_CRUD` role.

**After** (Finance_CRUD permissions):

```python
'Finance_CRUD': [
    'finance_create', 'finance_read', 'finance_update', 'finance_delete',
    'finance_list', 'finance_export', 'finance_write',  # ← ADDED
    ...
]
```

## File Changed

- `backend/src/auth/cognito_utils.py` (line 41)

## Required Action

**Backend must be restarted** for the permission change to take effect:

```bash
# Stop backend if running
# Then restart:
cd backend
.\.venv\Scripts\Activate.ps1
python src/app.py

# Or use PowerShell script:
.\powershell\start_backend.ps1
```

## Verification

After restarting backend:

1. Navigate to FIN Reports → Year-End Closure tab
2. Click "Boekjaar Afsluiten" (Close Fiscal Year)
3. Select year 2025
4. Click "Volgende" (Next)
5. Should see validation results (no permission error)
6. Click "Sluit Jaar 2025" (Close Year 2025)
7. Should successfully close the year

## Why This Permission?

The `finance_write` permission is used for operations that modify financial data in significant ways:

- Closing fiscal years (creates closure and opening balance transactions)
- Other write operations that go beyond simple CRUD

The `Finance_CRUD` role should have this permission because:

- It's the primary role for financial data management
- Users with this role need to perform year-end closures
- It's consistent with other write permissions in the role

## Related Documentation

- `.kiro/specs/FIN/Year end closure/TASKS-closure.md` - Phase 3 notes about permissions
- `.kiro/specs/FIN/Year end closure/design-closure.md` - Permission requirements
- `backend/src/routes/year_end_routes.py` - API endpoint documentation

## Testing

After fix, verify:

- [x] Finance_CRUD role can close years
- [ ] Finance_Read role CANNOT close years (read-only)
- [ ] Finance_Export role CANNOT close years (export-only)
- [ ] Users without Finance_CRUD get proper error message

## Notes

- This is a one-time fix - no database changes needed
- Only affects backend code
- Frontend already handles permission errors correctly
- No migration script required
