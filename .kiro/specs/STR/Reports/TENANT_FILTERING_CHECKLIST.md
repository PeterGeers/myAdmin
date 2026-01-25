# STR Reports - Tenant Filtering Checklist

## Overview

This checklist tracks tenant filtering implementation for STR (Short-Term Rental) reporting endpoints in `bnb_routes.py`.

**Status:** 🔴 Not Started - To be implemented after FIN Reports completion

**Note:** The frontend/backend split has been completed (see REPORTS_MODULE_SPLIT.md). STR reports are now in `STRReports.tsx` using `BnbReportsGroup`, and proper STR endpoints are in `bnb_routes.py` under `/api/bnb/*`.

## Endpoints Requiring Tenant Filtering

### ❌ Missing @tenant_required()

#### BNB/STR Routes (`bnb_routes.py`)

- [ ] 1. `/api/bnb/bnb-listing-data` - ❌ No filtering
  - **Data Source:** `vw_bnb_total` view (has `administration` column)
  - **Frontend Usage:** `BnbActualsReport.tsx`, `myAdminReports.tsx`
  - **Security Risk:** HIGH - Listing data is tenant-specific
  - **Implementation:** Add `@tenant_required()` and filter by user_tenants

- [ ] 2. `/api/bnb/bnb-channel-data` - ❌ No filtering
  - **Data Source:** `vw_bnb_total` view (has `administration` column)
  - **Frontend Usage:** `BnbActualsReport.tsx`, `myAdminReports.tsx`
  - **Security Risk:** HIGH - Channel data is tenant-specific
  - **Implementation:** Add `@tenant_required()` and filter by user_tenants

- [ ] 3. `/api/bnb/bnb-filter-options` - ❌ No filtering
  - **Data Source:** `vw_bnb_total` view (has `administration` column)
  - **Frontend Usage:** `BnbActualsReport.tsx`, `BnbViolinsReport.tsx`, `myAdminReports.tsx`
  - **Security Risk:** MEDIUM - Metadata exposure
  - **Implementation:** Add `@tenant_required()` and filter options by user_tenants

- [ ] 4. `/api/bnb/bnb-actuals` - ❌ No filtering
  - **Data Source:** TBD (needs investigation)
  - **Frontend Usage:** TBD
  - **Security Risk:** HIGH - Actuals data is tenant-specific
  - **Implementation:** Add `@tenant_required()` and filter by user_tenants

- [ ] 5. `/api/bnb/bnb-violin-data` - ❌ No filtering
  - **Data Source:** `vw_bnb_total` view (has `administration` column)
  - **Frontend Usage:** `BnbViolinsReport.tsx`, `myAdminReports.tsx`
  - **Security Risk:** HIGH - Revenue data is tenant-specific
  - **Implementation:** Add `@tenant_required()` and filter by user_tenants

- [ ] 6. `/api/bnb/bnb-returning-guests` - ❌ No filtering
  - **Data Source:** `vw_bnb_total` view (has `administration` column)
  - **Frontend Usage:** `BnbReturningGuestsReport.tsx`, `myAdminReports.tsx`
  - **Security Risk:** HIGH - Guest data is tenant-specific
  - **Implementation:** Add `@tenant_required()` and filter by user_tenants

- [ ] 7. `/api/bnb/bnb-guest-bookings` - ❌ No filtering
  - **Data Source:** `vw_bnb_total` view (has `administration` column)
  - **Frontend Usage:** `BnbReturningGuestsReport.tsx`, `myAdminReports.tsx`
  - **Security Risk:** HIGH - Guest booking data is tenant-specific
  - **Implementation:** Add `@tenant_required()` and filter by user_tenants

### 🗑️ Duplicate Endpoints to Remove

#### These exist in `reporting_routes.py` but are DUPLICATES (should be removed):

- [ ] `/api/reports/bnb-table` - Remove from reporting_routes.py (no equivalent in bnb_routes.py - needs migration)
- [ ] `/api/reports/bnb-filter-options` - Remove from reporting_routes.py (duplicate of `/api/bnb/bnb-filter-options`)
- [ ] `/api/reports/bnb-listing-data` - Remove from reporting_routes.py (duplicate of `/api/bnb/bnb-listing-data`)
- [ ] `/api/reports/bnb-channel-data` - Remove from reporting_routes.py (duplicate of `/api/bnb/bnb-channel-data`)

**Action Required:**

1. Check if `/api/reports/bnb-table` has unique functionality
2. If yes, migrate to `/api/bnb/bnb-table` in bnb_routes.py
3. Update frontend to use `/api/bnb/*` endpoints
4. Remove duplicates from reporting_routes.py

## Implementation Strategy

### For BNB Endpoints:

1. Add `@tenant_required()` decorator
2. Add `tenant` and `user_tenants` parameters to function signature
3. Add `WHERE administration IN (...)` to SQL queries
4. Use `user_tenants` parameter from decorator
5. Ensure no cross-tenant data leakage

### For Filter/Options Endpoints:

1. Add `@tenant_required()` decorator
2. Filter available options by `user_tenants`
3. Ensure no cross-tenant data leakage in dropdown options

## Testing Plan

For each endpoint:

1. Test with GoodwinSolutions tenant
2. Test with PeterPrive tenant
3. Verify no cross-tenant data leakage
4. Verify proper error messages for unauthorized access
5. Test frontend components with tenant context

## Dependencies

- ✅ `@tenant_required()` decorator (already implemented in `auth/tenant_context.py`)
- ✅ `vw_bnb_total` view has `administration` column
- ⏳ Complete FIN Reports tenant filtering first
- ⏳ Clean up duplicate endpoints in reporting_routes.py

## Notes

- All BNB data is tenant-specific (different properties per tenant)
- Priority: Implement after FIN Reports completion
- Frontend/Backend split is complete (see REPORTS_MODULE_SPLIT.md)
- Proper STR endpoints are in `bnb_routes.py` under `/api/bnb/*`
