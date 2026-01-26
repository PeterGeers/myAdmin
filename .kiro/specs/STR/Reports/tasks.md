# STR/BNB Reports - Tenant Filtering Implementation Tasks

## Overview

This task list provides a structured approach to implementing tenant filtering for all STR/BNB report endpoints.

## Task List

### Phase 1: BNB Routes - High Priority Data Endpoints

- [x] 1. Implement tenant filtering for `/api/bnb/bnb-listing-data`
  - [x] 1.1 Import tenant_required decorator in bnb_routes.py
  - [x] 1.2 Add @tenant_required() decorator to get_bnb_listing_data
  - [x] 1.3 Add tenant and user_tenants parameters to function signature
  - [x] 1.4 Build tenant filter with placeholders for user_tenants
  - [x] 1.5 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 1.6 Test with single tenant user
  - [x] 1.7 Test with multi-tenant user
  - [x] 1.8 Test unauthorized access returns 403

- [x] 2. Implement tenant filtering for `/api/bnb/bnb-channel-data`
  - [x] 2.1 Add @tenant_required() decorator to get_bnb_channel_data
  - [x] 2.2 Add tenant and user_tenants parameters to function signature
  - [x] 2.3 Build tenant filter with placeholders for user_tenants
  - [x] 2.4 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 2.5 Test with single tenant user
  - [x] 2.6 Test with multi-tenant user
  - [x] 2.7 Test unauthorized access returns 403

- [x] 3. Implement tenant filtering for `/api/bnb/bnb-table`
  - [x] 3.1 Add @tenant_required() decorator to get_bnb_table
  - [x] 3.2 Add tenant and user_tenants parameters to function signature
  - [x] 3.3 Build tenant filter with placeholders for user_tenants
  - [x] 3.4 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 3.5 Note: Uses vw_bnb_total view
  - [x] 3.6 Test with single tenant user
  - [x] 3.7 Test with multi-tenant user
  - [x] 3.8 Test unauthorized access returns 403

- [x] 4. Implement tenant filtering for `/api/bnb/bnb-guest-bookings`
  - [x] 4.1 Add @tenant_required() decorator to get_bnb_guest_bookings
  - [x] 4.2 Add tenant and user_tenants parameters to function signature
  - [x] 4.3 Build tenant filter with placeholders for user_tenants
  - [x] 4.4 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 4.5 Ensure guest data is isolated by tenant
  - [x] 4.6 Test with single tenant user
  - [x] 4.7 Test with multi-tenant user
  - [x] 4.8 Test cross-tenant guest data access is blocked

### Phase 2: BNB Routes - Medium Priority Endpoints

- [x] 5. Implement tenant filtering for `/api/bnb/bnb-actuals`
  - [x] 5.1 Add @tenant_required() decorator to get_bnb_actuals
  - [x] 5.2 Add tenant and user_tenants parameters to function signature
  - [x] 5.3 Build tenant filter with placeholders for user_tenants
  - [x] 5.4 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 5.5 Remove or validate unused administration parameter
  - [x] 5.6 Test with single tenant user
  - [x] 5.7 Test with multi-tenant user

- [x] 6. Implement tenant filtering for `/api/bnb/bnb-filter-options`
  - [x] 6.1 Add @tenant_required() decorator to get_bnb_filter_options
  - [x] 6.2 Add tenant and user_tenants parameters to function signature
  - [x] 6.3 Build tenant filter with placeholders for user_tenants
  - [x] 6.4 Add WHERE administration IN (user_tenants) to years query
  - [x] 6.5 Add WHERE administration IN (user_tenants) to listings query
  - [x] 6.6 Add WHERE administration IN (user_tenants) to channels query
  - [x] 6.7 Test filter options only show data for user's tenants
  - [x] 6.8 Test with multi-tenant user sees combined options

- [x] 7. Implement tenant filtering for `/api/bnb/bnb-violin-data`
  - [x] 7.1 Add @tenant_required() decorator to get_bnb_violin_data
  - [x] 7.2 Add tenant and user_tenants parameters to function signature
  - [x] 7.3 Build tenant filter with placeholders for user_tenants
  - [x] 7.4 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 7.5 Test violin plot data is filtered by tenant
  - [x] 7.6 Test with multi-tenant user

- [x] 8. Implement tenant filtering for `/api/bnb/bnb-returning-guests`
  - [x] 8.1 Add @tenant_required() decorator to get_bnb_returning_guests
  - [x] 8.2 Add tenant and user_tenants parameters to function signature
  - [x] 8.3 Build tenant filter with placeholders for user_tenants
  - [x] 8.4 Add WHERE administration IN (user_tenants) to SQL query
  - [x] 8.5 Ensure guest data is isolated by tenant
  - [x] 8.6 Test returning guests only from user's tenants
  - [x] 8.7 Test with multi-tenant user

### Phase 3: STR Routes - Write Operations

- [x] 9. Implement tenant filtering for `/api/str-channel/save`
  - [x] 9.1 Add @tenant_required() decorator to save_str_channel_transactions
  - [x] 9.2 Add tenant and user_tenants parameters to function signature
  - [x] 9.3 Validate all transactions Administration field is in user_tenants
  - [x] 9.4 Return 403 if any transaction has unauthorized administration
  - [x] 9.5 Test saving transactions for authorized tenant succeeds
  - [x] 9.6 Test saving transactions for unauthorized tenant fails with 403
  - [x] 9.7 Test mixed authorized/unauthorized transactions are rejected

- [x] 10. Implement tenant filtering for `/api/str-invoice/generate-invoice`
  - [x] 10.1 Add @tenant_required() decorator to generate_invoice
  - [x] 10.2 Add tenant and user_tenants parameters to function signature
  - [x] 10.3 Add WHERE administration IN (user_tenants) to booking query
  - [x] 10.4 Validate booking exists and user has access before generating invoice
  - [x] 10.5 Return 403 if booking belongs to unauthorized tenant
  - [x] 10.6 Test invoice generation for authorized booking succeeds
  - [x] 10.7 Test invoice generation for unauthorized booking fails with 403

### Phase 4: Administrative Endpoints - Review and Decision

- [x] 11. Review `/api/str-invoice/upload-template-to-drive`
  - [x] 11.1 Determine if invoice templates are tenant-specific or global
  - [x] 11.2 If tenant-specific: Add @tenant_required() and tenant validation
  - [x] 11.3 If global: Document decision and keep current implementation
  - [x] 11.4 Update endpoint documentation

- [x] 12. Review `/api/str-invoice/test`
  - [x] 12.1 Determine if endpoint should remain in production
  - [O] 12.2 If keeping: Restrict to SysAdmin role only DOES NOT APPLY see 12.3
  - [x] 12.3 If removing: Remove endpoint and update documentation
  - [x] 12.4 Update endpoint documentation

### Phase 5: Testing and Documentation

- [x] 13. Create comprehensive test suite
  - [x] 13.1 Create test file for BNB routes tenant filtering
  - [x] 13.2 Create test file for STR channel routes tenant filtering
  - [x] 13.3 Create test file for STR invoice routes tenant filtering
  - [x] 13.4 Implement integration tests with real database
  - [x] 13.5 Test with multiple tenant scenarios
  - [x] 13.6 Test performance impact of tenant filtering

- [x] 14. Update documentation
  - [x] 14.1 Update API documentation with tenant filtering requirements
  - [x] 14.2 Document tenant filtering patterns for future endpoints
  - [x] 14.3 Update frontend documentation if API changes affect frontend
  - [x] 14.4 Create migration guide for existing API consumers
  - [x] 14.5 Review, update, validate and consolidate all diocumentation in .kiro\specs\STR\Reports

- [x] 15. Code review and validation
  - [x] 15.1 Review all SQL queries for proper parameterization
  - [x] 15.2 Verify no SQL injection vulnerabilities
  - [x] 15.3 Check error messages don't leak sensitive information
  - [x] 15.4 Validate consistent error handling across all endpoints
  - [x] 15.5 Performance review of tenant filtering queries

  - [x] 16. Rebuild the backend container and see if it works
  - [x] 17. Rebuild the frontend and see if it works

## Implementation Notes

### Import Statement for BNB Routes

Add to top of `backend/src/bnb_routes.py`:

```python
from auth.tenant_context import tenant_required
```

### Tenant Filter Pattern

Use this pattern for building tenant filters:

```python
placeholders = ', '.join(['%s'] * len(user_tenants))
where_conditions.append(f"administration IN ({placeholders})")
params.extend(user_tenants)
```

### Validation Pattern

Use this pattern for validating single administration:

```python
if administration not in user_tenants:
    return jsonify({
        'success': False,
        'error': f'Access denied to administration: {administration}'
    }), 403
```

### Testing Pattern

Each endpoint should be tested with:

1. Single tenant user (e.g., PeterPrive only)
2. Multi-tenant user (e.g., PeterPrive + GoodwinSolutions)
3. Unauthorized access attempt
4. SysAdmin user (if allow_sysadmin=True)

## Success Criteria

- [ ] All HIGH priority endpoints have tenant filtering
- [ ] All MEDIUM priority endpoints have tenant filtering
- [ ] All write operations validate tenant access
- [ ] Comprehensive test coverage (>80%)
- [ ] No cross-tenant data leakage in any endpoint
- [ ] Performance impact < 10% for tenant filtering
- [ ] Documentation updated and complete

## Related Files

- Implementation: `backend/src/bnb_routes.py`
- Implementation: `backend/src/str_channel_routes.py`
- Implementation: `backend/src/str_invoice_routes.py`
- Decorator: `backend/src/auth/tenant_context.py`
- Tests: `backend/tests/api/test_bnb_routes_tenant.py` (to be created)
- Tests: `backend/tests/api/test_str_channel_routes_tenant.py` (to be created)
- Tests: `backend/tests/api/test_str_invoice_routes_tenant.py` (to be created)
