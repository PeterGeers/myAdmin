# Backend RBAC Update Plan

## Critical Issue: SysAdmin Permissions

**Current:** `'SysAdmin': ['*']` grants wildcard access to all modules
**Required:** SysAdmin should have NO access to Finance or STR user data

## Required Changes

### 1. Update ROLE_PERMISSIONS in `backend/src/auth/cognito_utils.py`

```python
ROLE_PERMISSIONS = {
    # System Administration - system config ONLY, NO user data access
    'SysAdmin': [
        'system_config', 'system_logs', 'system_audit',
        'cache_manage', 'templates_manage', 'users_manage'
    ],

    # Finance Module - unchanged
    'Finance_CRUD': [...],
    'Finance_Read': [...],
    'Finance_Export': [...],

    # STR Module - unchanged
    'STR_CRUD': [...],
    'STR_Read': [...],
    'STR_Export': [...],
}
```

### 2. Update Routes Using Legacy Roles

**Files with `required_roles=['Administrators']`:**

- `backend/src/scalability_routes.py` - Change to `required_roles=['SysAdmin']`
- `backend/src/duplicate_performance_routes.py` - Change to `required_roles=['SysAdmin']`
- `backend/src/audit_routes.py` - Change to `required_roles=['SysAdmin']`
- `backend/src/debug_routes.py` - Change to `required_roles=['SysAdmin']`

### 3. Verify Module-Specific Routes

**Finance Module Routes (already correct):**

- `/api/upload` - `required_permissions=['invoices_create']` ✅
- `/api/pdf/*` - `required_permissions=['invoices_read/update']` ✅
- `/api/btw/*` - `required_permissions=['btw_process']` ✅
- Banking routes - `required_permissions=['banking_read/process']` ✅

**STR Module Routes (already correct):**

- `/api/str/upload` - `required_permissions=['str_create']` ✅
- `/api/str-invoice/*` - `required_permissions=['str_read/create']` ✅
- `/api/str-channel/*` - `required_permissions=['str_read/bookings_create']` ✅

**Reporting Routes (needs review):**

- Financial reports - `required_permissions=['reports_read']` ⚠️ Too generic
- BNB reports - `required_permissions=['reports_read']` ⚠️ Too generic

Should be:

- Financial reports - Check for Finance module permissions
- BNB reports - Check for STR module permissions

### 4. Remove Legacy Role Mappings

Delete from `ROLE_PERMISSIONS`:

- `'Administrators'`
- `'Accountants'`
- `'Viewers'`
- Any other legacy roles

## Implementation Priority

1. **Critical:** Fix SysAdmin wildcard permission
2. **High:** Update routes using `Administrators` to use `SysAdmin`
3. **Medium:** Split reporting routes by module
4. **Low:** Remove legacy role mappings (after user migration)
