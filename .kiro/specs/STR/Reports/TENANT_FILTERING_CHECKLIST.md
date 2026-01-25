# STR/BNB Reports - Tenant Filtering Checklist

## Overview

This checklist tracks the implementation of tenant filtering for all STR (Short-Term Rental) and BNB (Bed & Breakfast) report endpoints. The goal is to ensure proper multi-tenant data isolation and security.

## Endpoints Requiring Tenant Filtering

### BNB Routes (`bnb_routes.py`)

All BNB endpoints query the `bnb` table which contains an `administration` column for tenant filtering.

#### Data Retrieval Endpoints

- [ ] 1. `/api/bnb/bnb-listing-data` - Missing tenant filtering
- [ ] 2. `/api/bnb/bnb-channel-data` - Missing tenant filtering
- [ ] 3. `/api/bnb/bnb-actuals` - Missing tenant filtering
- [ ] 4. `/api/bnb/bnb-filter-options` - Missing tenant filtering
- [ ] 5. `/api/bnb/bnb-violin-data` - Missing tenant filtering
- [ ] 6. `/api/bnb/bnb-returning-guests` - Missing tenant filtering
- [ ] 7. `/api/bnb/bnb-guest-bookings` - Missing tenant filtering
- [ ] 8. `/api/bnb/bnb-table` - Missing tenant filtering

### STR Channel Routes (`str_channel_routes.py`)

#### Already Implemented

- [x] 9. `/api/str-channel/calculate` - Has tenant filtering
- [x] 10. `/api/str-channel/preview` - Has tenant filtering

#### Missing Tenant Filtering

- [ ] 11. `/api/str-channel/save` - Missing tenant filtering

### STR Invoice Routes (`str_invoice_routes.py`)

#### Already Implemented

- [x] 12. `/api/str-invoice/search-booking` - Has tenant filtering

#### Missing Tenant Filtering

- [ ] 13. `/api/str-invoice/generate-invoice` - Missing tenant filtering
- [ ] 14. `/api/str-invoice/upload-template-to-drive` - Review needed
- [ ] 15. `/api/str-invoice/test` - Diagnostic endpoint

## Implementation Details

### Task 1: `/api/bnb/bnb-listing-data`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 2: `/api/bnb/bnb-channel-data`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 3: `/api/bnb/bnb-actuals`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 4: `/api/bnb/bnb-filter-options`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Filter years, listings, and channels by user_tenants

### Task 5: `/api/bnb/bnb-violin-data`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 6: `/api/bnb/bnb-returning-guests`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 7: `/api/bnb/bnb-guest-bookings`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 8: `/api/bnb/bnb-table`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Add WHERE administration IN (user_tenants) to SQL query

### Task 11: `/api/str-channel/save`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Validate all transactions Administration field is in user_tenants

### Task 13: `/api/str-invoice/generate-invoice`
**Current Status**: Has @cognito_required but no tenant filtering
**Required Changes**:
- Add @tenant_required() decorator
- Add tenant and user_tenants parameters
- Validate booking administration against user_tenants

### Task 14: `/api/str-invoice/upload-template-to-drive`
**Current Status**: Has @cognito_required but no tenant filtering
**Decision Needed**: Are invoice templates tenant-specific or global?

### Task 15: `/api/str-invoice/test`
**Current Status**: Diagnostic endpoint with no required permissions
**Review Needed**: Should be restricted to SysAdmin or removed in production

## Priority Classification

### HIGH PRIORITY (Security Critical)
- Task 1: bnb-listing-data
- Task 2: bnb-channel-data
- Task 7: bnb-guest-bookings
- Task 8: bnb-table
- Task 13: generate-invoice

### MEDIUM PRIORITY
- Task 3: bnb-actuals
- Task 4: bnb-filter-options
- Task 5: bnb-violin-data
- Task 6: bnb-returning-guests
- Task 11: str-channel save

### LOW PRIORITY
- Task 14: upload-template-to-drive
- Task 15: test endpoint

## Implementation Strategy

### For BNB Routes:
1. Import tenant_required from auth.tenant_context
2. Add @tenant_required() decorator after @cognito_required()
3. Add tenant and user_tenants parameters
4. Build tenant filter with placeholders
5. Apply filter to all SQL queries

### For STR Routes:
1. Add @tenant_required() decorator
2. Validate administration parameter against user_tenants
3. Return 403 for unauthorized access

## Testing Plan

Test each endpoint with:
1. Single tenant user
2. Multi-tenant user
3. Unauthorized tenant access
4. SysAdmin user (if applicable)

## Notes

- tenant_required decorator needs to be imported in bnb_routes.py
- All BNB endpoints use bnb table or vw_bnb_total view
- STR endpoints use vw_mutaties and vw_bnb_total views
