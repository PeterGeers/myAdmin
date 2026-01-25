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

- [ ] 6. `/api/reports/financial-summary` - ❌ Filters by `administration` parameter
- [ ] 7. `/api/reports/str-revenue` - ❌ No filtering (STR data)
- [ ] 8. `/api/reports/account-summary` - ❌ No tenant filtering
- [ ] 9. `/api/reports/mutaties-table` - ❌ Filters by `administration` parameter

- [ ] 10. `/api/reports/<table>-fields` - ❌ No filtering
- [ ] 11. `/api/reports/balance-data` - ❌ Filters by `administration` parameter
- [ ] 12. `/api/reports/bnb-table` - ❌ No filtering (STR data)
- [ ] 13. `/api/reports/trends-data` - ❌ Filters by `administration` parameter
- [ ] 14. `/api/reports/available-<data_type>` - ❌ No filtering

15. `/api/reports/reference-analysis` - ❌ Filters by `administration` parameter
16. `/api/reports/bnb-filter-options` - ❌ No filtering (STR data)
17. `/api/reports/bnb-listing-data` - ❌ No filtering (STR data)
18. `/api/reports/bnb-channel-data` - ❌ No filtering (STR data)
19. `/api/reports/available-years` - ❌ No filtering

#### Aangifte IB Routes (`app.py`)

20. `/api/reports/aangifte-ib-details` - ❌ Uses cache
21. `/api/reports/aangifte-ib-export` - ❌ Uses cache
22. `/api/reports/aangifte-ib-xlsx-export` - ❌ Uses cache
23. `/api/reports/aangifte-ib-xlsx-export-stream` - ❌ Uses cache

## Priority Fixes

### HIGH PRIORITY (FIN Reports - Direct Data Access)

- actuals-balance
- actuals-profitloss
- mutaties-table
- balance-data
- trends-data
- reference-analysis
- aangifte-ib-details
- aangifte-ib-export

### MEDIUM PRIORITY (Metadata/Options)

- filter-options (already done)
- available-<data_type>
- <table>-fields

### LOW PRIORITY (STR Reports - Should be in STR module)

- str-revenue
- bnb-table
- bnb-filter-options
- bnb-listing-data
- bnb-channel-data

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
