# RBAC Frontend Menu Implementation

## Module Structure

```
├── Finance Module
│   ├── Finance_Read (view only)
│   ├── Finance_CRUD (create, update, delete)
│   └── Finance_Export (export data)
├── STR Module
│   ├── STR_Read (view only)
│   ├── STR_CRUD (create, update, delete)
│   └── STR_Export (export data)
└── System Module
    └── SysAdmin (system configuration, NO user data access)
```

## Role Access Matrix

| Feature               | Finance_CRUD | Finance_Read | Finance_Export | STR_CRUD | STR_Read | STR_Export | SysAdmin |
| --------------------- | ------------ | ------------ | -------------- | -------- | -------- | ---------- | -------- |
| Import Invoices       | ✅           | ❌           | ❌             | ❌       | ❌       | ❌         | ❌       |
| Import Banking        | ✅           | ❌           | ❌             | ❌       | ❌       | ❌         | ❌       |
| Import STR Bookings   | ❌           | ❌           | ❌             | ✅       | ❌       | ❌         | ❌       |
| STR Invoice Generator | ❌           | ❌           | ❌             | ✅       | ✅       | ✅         | ❌       |
| STR Pricing Model     | ❌           | ❌           | ❌             | ✅       | ❌       | ❌         | ❌       |
| Financial Reports     | ✅           | ✅           | ✅             | ❌       | ❌       | ❌         | ❌       |
| BNB Reports           | ❌           | ❌           | ❌             | ✅       | ✅       | ✅         | ❌       |
| System Admin Features | ❌           | ❌           | ❌             | ❌       | ❌       | ❌         | ✅       |

## Key Principles

1. **Roles are additive**: Users can have multiple roles
2. **SysAdmin has NO access to Finance or STR modules**
3. **Module isolation**: Finance roles cannot access STR data and vice versa
4. **Backend enforces all permissions** - frontend only hides UI elements

## Current Implementation Status

### ❌ Issues Found

**Frontend incorrectly includes SysAdmin in Finance/STR checks:**

- ✅ Fixed in `App.tsx`
- ✅ Fixed in `MyAdminReportsNew.tsx`

**Backend uses mixed permission system:**

- Some routes use legacy roles (`Administrators`, `Accountants`)
- Some routes use generic permissions (`reports_read`, `banking_read`)
- Module-specific roles defined in `ROLE_PERMISSIONS` but not consistently used

### ✅ Completed Fixes

- [x] 1. Remove `'SysAdmin'` from all Finance/STR module checks in frontend
- [x] 2. Update SysAdmin permissions in backend (removed wildcard `['*']`, added specific system permissions)
- [x] 3. Update routes using legacy `'Administrators'` role to use `'SysAdmin'`
- [x] 4. Add System Administration menu with User & Role Management

## Files Updated

- [x] `frontend/src/App.tsx` - Removed SysAdmin from Finance/STR checks, added System Admin menu
- [x] `frontend/src/components/MyAdminReportsNew.tsx` - Removed SysAdmin from report checks
- [x] `frontend/src/components/SystemAdmin.tsx` - New component for user/role management
- [x] `backend/src/auth/cognito_utils.py` - Changed SysAdmin from wildcard to specific permissions
- [x] `backend/src/admin_routes.py` - New routes for user/role management
- [x] `backend/src/app.py` - Registered admin_bp blueprint
- [x] `backend/src/scalability_routes.py` - Changed Administrators to SysAdmin
- [x] `backend/src/duplicate_performance_routes.py` - Changed Administrators to SysAdmin
- [x] `backend/src/audit_routes.py` - Changed Administrators to SysAdmin

## System Administration Features

**Menu:** ⚙️ System Administration (SysAdmin role only)

**Features:**

- User & Role Management
  - List all users with their roles and status
  - Add/remove roles from users
  - Enable/disable user accounts
  - Delete user accounts
  - View all available roles (groups)

Tennant structuur ontbreekt nog!!!!!
tennants  PeterPrive, GoodwinSolutions
Gebruik veld administration in sql
Voeg nog toe aan bnb tabellen and views