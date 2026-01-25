# FIN Reports - Tenant Filtering Checklist

## Endpoints Requiring Tenant Filtering

### ✅ Already Has @tenant_required()

1. `/api/reports/filter-options` - ✅ Has @tenant_required()
2. `/api/reports/check-reference` - ✅ Has @tenant_required()
3. `/api/reports/aangifte-ib` - ✅ Has @tenant_required()

### ❌ Missing @tenant_required()

#### Actuals Routes (`actuals_routes.py`)

Ebnsure proper tennanthandling
Add @tenant_required() decorator
Add tenant and user_tenants parameters to the function signature
Validate the administration parameter against user_tenants
Filter cached data by user_tenants for security

- [x] 4. `/api/reports/actuals-balance` - ✅ Has @tenant_required()
- [x] 5. `/api/reports/actuals-profitloss` - ✅ Has @tenant_required()

#### Reporting Routes (`reporting_routes.py`)

- [x] 6. `/api/reports/financial-summary` - ✅ Filters by `administration` parameter
- [x] 7. `/api/reports/str-revenue` - ✅ Has @tenant_required() and filters by user_tenants
- [x] 8. `/api/reports/account-summary` - ✅ Has @tenant_required() and filters by administration
- [x] 9. `/api/reports/mutaties-table` - ✅ Has @tenant_required() and filters by user_tenants

- [x] 10. `/api/reports/<table>-fields` - ✅ REMOVED (dead code - no usage found)

- [x] 11. `/api/reports/balance-data` - ✅ Has @tenant_required() and filters by user_tenants
- [x] 12. `/api/reports/bnb-table` - ✅ MOVED to `/api/bnb/bnb-table` in bnb_routes.py (STR module)
- [x] 13. `/api/reports/trends-data` - ✅ Has @tenant_required() and validates administration
- [x] 14. `/api/reports/available-<data_type>` - ✅ Has @tenant_required() and filters by user_tenants

- [x] 15. `/api/reports/reference-analysis` - ✅ Has @tenant_required() and validates administration
- [x] 16. `/api/reports/bnb-filter-options` - 🗑️ DUPLICATE/DEAD CODE REMOVED - Migrated to `/api/bnb/bnb-filter-options`

- [x] 17. `/api/reports/bnb-listing-data` - ✅ MIGRATED to `/api/bnb/bnb-listing-data` (frontend updated)

- [x] 18. `/api/reports/bnb-channel-data` - ✅ MIGRATED to `/api/bnb/bnb-channel-data` (frontend updated)
- [x] 19. `/api/reports/available-years` - ✅ Has @tenant_required() and filters by user_tenants

#### Aangifte IB Routes (`app.py`)

- [x] 20. `/api/reports/aangifte-ib-details` - ✅ Has @tenant_required() and filters by user_tenants
- [x] 21. `/api/reports/aangifte-ib-export` - ✅ Has @tenant_required() and validates administration
- [x] 22. `/api/reports/aangifte-ib-xlsx-export` - ✅ Has @tenant_required() and validates administrations
- [x] 23. `/api/reports/aangifte-ib-xlsx-export-stream` - ✅ Has @tenant_required() and validates administrations

**Note:**

- Frontend/Backend split was completed (see REPORTS_MODULE_SPLIT.md)
- FINReports.tsx uses FinancialReportsGroup (FIN only)
- STRReports.tsx uses BnbReportsGroup (STR only)
- Proper STR endpoints are in bnb_routes.py under `/api/bnb/*`
- These duplicates in reporting_routes.py are legacy code from before the split
- str-revenue endpoint was already completed in FIN Reports as it was used there

## Implementation Strategy

### For Cache-Based Endpoints:

1. Add `@tenant_required()` decorator
2. Filter cached data by `user_tenants` before processing
3. Validate `administration` parameter against `user_tenants`

### For Direct Query Endpoints:

1. Add `@tenant_required()` decorator
2. Add `WHERE administration = %s` to SQL queries
3. Use `tenant` parameter from decorator

### For Export Endpoints:

1. Add `@tenant_required()` decorator
2. Validate requested administration against `user_tenants`
3. Filter data before export

## Testing Plan

For each endpoint:

1. Test with GoodwinSolutions tenant
2. Test with PeterPrive tenant
3. Verify no cross-tenant data leakage
4. Verify proper error messages for unauthorized access
