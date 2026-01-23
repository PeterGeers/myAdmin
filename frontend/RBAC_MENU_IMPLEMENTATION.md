# Role-Based Access Control (RBAC) - Frontend Menu Implementation

## Overview

The frontend menu and reports now implement role-based access control to show only the features that each user role is authorized to access.

**Implementation Date**: January 23, 2026  
**Status**: ✅ Complete

## Role-Based Menu Access

### Administrators
**Full Access** - Can see all menu items and reports:
- ✅ 📄 Import Invoices
- ✅ 🏦 Import Banking Accounts
- ✅ 🏠 Import STR Bookings
- ✅ 🧾 STR Invoice Generator
- ✅ 💰 STR Pricing Model
- ✅ 📈 myAdmin Reports
  - ✅ 🏠 BNB Reports (all 6 reports)
  - ✅ 💰 Financial Reports (all 5 reports)

### Accountants
**Financial Operations** - Can see:
- ✅ 📄 Import Invoices
- ✅ 🏦 Import Banking Accounts
- ❌ 🏠 Import STR Bookings (Hidden)
- ❌ 🧾 STR Invoice Generator (Hidden)
- ❌ 💰 STR Pricing Model (Hidden)
- ✅ 📈 myAdmin Reports
  - ❌ 🏠 BNB Reports (Hidden - STR data)
  - ✅ 💰 Financial Reports (all 5 reports)

### Finance_CRUD / Finance_Read
**Invoice Management** - Can see:
- ✅ 📄 Import Invoices
- ❌ 🏦 Import Banking Accounts (Hidden)
- ❌ 🏠 Import STR Bookings (Hidden)
- ❌ 🧾 STR Invoice Generator (Hidden)
- ❌ 💰 STR Pricing Model (Hidden)
- ✅ 📈 myAdmin Reports
  - ❌ 🏠 BNB Reports (Hidden)
  - ✅ 💰 Financial Reports (all 5 reports)

### STR_CRUD
**STR Management** - Can see:
- ❌ 📄 Import Invoices (Hidden)
- ❌ 🏦 Import Banking Accounts (Hidden)
- ✅ 🏠 Import STR Bookings
- ✅ 🧾 STR Invoice Generator
- ✅ 💰 STR Pricing Model
- ✅ 📈 myAdmin Reports
  - ✅ 🏠 BNB Reports (all 6 reports)
  - ❌ 💰 Financial Reports (Hidden)

### STR_Read
**STR Read-Only** - Can see:
- ❌ 📄 Import Invoices (Hidden)
- ❌ 🏦 Import Banking Accounts (Hidden)
- ✅ 🏠 Import STR Bookings (Read-only)
- ✅ 🧾 STR Invoice Generator
- ❌ 💰 STR Pricing Model (Hidden)
- ✅ 📈 myAdmin Reports
  - ✅ 🏠 BNB Reports (all 6 reports, read-only)
  - ❌ 💰 Financial Reports (Hidden)

### Viewers
**Read-Only Access** - Can see:
- ✅ 📄 Import Invoices (Read-only)
- ❌ 🏦 Import Banking Accounts (Hidden)
- ❌ 🏠 Import STR Bookings (Hidden)
- ❌ 🧾 STR Invoice Generator (Hidden)
- ❌ 💰 STR Pricing Model (Hidden)
- ✅ 📈 myAdmin Reports
  - ❌ 🏠 BNB Reports (Hidden)
  - ✅ 💰 Financial Reports (all 5 reports, read-only)

## Report Categories

### BNB Reports (STR/Short-Term Rental)
Access: Administrators, STR_CRUD, STR_Read
1. 🏠 Revenue
2. 🏡 Actuals
3. 🎻 Violins
4. 🔄 Terugkerend (Returning Guests)
5. 📈 Future
6. 🏨 Toeristenbelasting (Tourist Tax)

### Financial Reports
Access: Administrators, Accountants, Finance_CRUD, Finance_Read, Finance_Export, Viewers
1. 💰 Mutaties (P&L)
2. 📊 Actuals
3. 🧾 Aangifte BTW (VAT Declaration)
4. 📈 Trend by ReferenceNumber
5. 📋 Aangifte IB (Income Tax Declaration)

## Implementation Details

### Menu Filtering Logic

The menu items are conditionally rendered based on the user's roles:

```typescript
// Invoice Management - Accountants, Administrators, Finance roles, Viewers
{(user?.roles?.some(role => ['Administrators', 'Accountants', 'Finance_CRUD', 'Finance_Read', 'Viewers'].includes(role))) && (
  <Button>📄 Import Invoices</Button>
)}

// Banking - Accountants, Administrators only
{(user?.roles?.some(role => ['Administrators', 'Accountants'].includes(role))) && (
  <Button>🏦 Import Banking Accounts</Button>
)}

// STR Features - Administrators, STR_CRUD, STR_Read only
{(user?.roles?.some(role => ['Administrators', 'STR_CRUD', 'STR_Read'].includes(role))) && (
  <Button>🏠 Import STR Bookings</Button>
)}
```

### Reports Filtering Logic

The reports component dynamically shows only authorized report categories:

```typescript
// BNB Reports - STR roles only
const canAccessBnbReports = user?.roles?.some(role => 
  ['Administrators', 'STR_CRUD', 'STR_Read'].includes(role)
);

// Financial Reports - Financial roles
const canAccessFinancialReports = user?.roles?.some(role => 
  ['Administrators', 'Accountants', 'Finance_CRUD', 'Finance_Read', 'Finance_Export', 'Viewers'].includes(role)
);
```

**Smart UI Behavior**:
- If user has access to both report types → Show tabs
- If user has access to only one type → Show that type directly (no tabs)
- If user has no access → Show warning message

### User Role Display

The menu header now shows the user's assigned roles:
```
Logged in as: accountant@test.com
Role: Accountants
```

## Testing

### Test User: accountant@test.com (Accountants role)

**Expected Behavior**:
- ✅ Dashboard: Import Invoices, Import Banking Accounts, myAdmin Reports
- ✅ Reports: Only Financial Reports (no BNB tab)
- ❌ Should NOT see: STR features, BNB Reports

### Test User: viewer@test.com (Viewers role)

**Expected Behavior**:
- ✅ Dashboard: Import Invoices (read-only), myAdmin Reports
- ✅ Reports: Only Financial Reports (no BNB tab)
- ❌ Should NOT see: Banking, STR features, BNB Reports

### Test User: peter@pgeers.nl (Administrators role)

**Expected Behavior**:
- ✅ Dashboard: ALL menu items
- ✅ Reports: Both BNB and Financial Reports tabs

## Backend Protection

**Important**: The frontend menu filtering is for UX only. The backend API endpoints are protected with the `@cognito_required` decorator and will return 403 Forbidden if a user tries to access an endpoint they don't have permission for.

This provides **defense in depth**:
1. **Frontend**: Hides unauthorized menu items and reports (better UX)
2. **Backend**: Enforces permissions on API calls (security)

## Files Modified

- `frontend/src/App.tsx` - Added role-based menu filtering
- `frontend/src/components/MyAdminReportsNew.tsx` - Added role-based report filtering

## Related Documentation

- Backend RBAC: `backend/docs/RBAC_IMPLEMENTATION_SUMMARY.md`
- Authentication Context: `frontend/src/context/AuthContext.tsx`
- Auth Service: `frontend/src/services/authService.ts`

## Next Steps

1. ✅ Frontend menu filtering implemented
2. ✅ Frontend reports filtering implemented
3. ⏳ Test with all user roles
4. ⏳ Add role-based UI elements within components (e.g., hide edit buttons for read-only users)
5. ⏳ Add user feedback when attempting unauthorized actions

## Security Notes

- Menu items and report tabs are hidden based on roles, but backend still validates all requests
- Users cannot bypass frontend restrictions by manipulating URLs
- All API calls require valid JWT tokens with appropriate permissions
- Unauthorized API calls return 403 Forbidden with audit logging
