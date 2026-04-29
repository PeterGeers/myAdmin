# Role-Based Access Control (RBAC) - Frontend Implementation

## Overview

The frontend menu and reports now implement role-based access control to show only the features that each user role is authorized to access.

**Implementation Date**: January 23, 2026  
**Status**: ✅ Complete

## What Accountants Can See

When logged in as **accountant@test.com**:

### Dashboard Menu (3 items):

- ✅ 📄 Import Invoices
- ✅ 🏦 Import Banking Accounts
- ✅ 📈 myAdmin Reports

### Reports Section:

- ✅ **Financial Reports ONLY** (no tabs, direct access)
  - 💰 Mutaties (P&L)
  - 📊 Actuals
  - 🧾 Aangifte BTW
  - 📈 Trend by ReferenceNumber
  - 📋 Aangifte IB
- ❌ **BNB Reports** (Hidden - these are STR/Short-Term Rental reports)

## Complete Role Matrix

### Administrators (Full Access)

- ✅ All dashboard menu items (6 items)
- ✅ Both report tabs: BNB Reports + Financial Reports

### Accountants (Financial Operations)

- ✅ Dashboard: Import Invoices, Banking, Reports (3 items)
- ✅ Reports: Financial Reports only (no BNB tab)

### Finance_CRUD / Finance_Read

- ✅ Dashboard: Import Invoices, Reports (2 items)
- ✅ Reports: Financial Reports only

### STR_CRUD (STR Management)

- ✅ Dashboard: STR Bookings, STR Invoice, STR Pricing (3 items)
- ✅ Reports: BNB Reports only (no Financial tab)

### STR_Read (STR Read-Only)

- ✅ Dashboard: STR Bookings, STR Invoice (2 items)
- ✅ Reports: BNB Reports only

### Viewers (Read-Only)

- ✅ Dashboard: Import Invoices, Reports (2 items)
- ✅ Reports: Financial Reports only

## Implementation Details

### Smart Report Display

The reports component automatically adapts based on user permissions:

- **Both permissions** → Show tabs for BNB and Financial
- **Only Financial** → Show Financial Reports directly (no tabs)
- **Only BNB** → Show BNB Reports directly (no tabs)
- **No permissions** → Show warning message

### Files Modified

1. `frontend/src/App.tsx` - Dashboard menu filtering
2. `frontend/src/components/MyAdminReportsNew.tsx` - Report category filtering

## Security

- **Frontend**: Hides unauthorized items (better UX)
- **Backend**: Enforces permissions on all API calls (security)
- Users cannot bypass restrictions by URL manipulation
