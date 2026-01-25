# STR/BNB Reports - Tenant Filtering Implementation

## Overview

This directory contains the specification and task list for implementing tenant filtering across all STR (Short-Term Rental) and BNB (Bed & Breakfast) report endpoints in the myAdmin application.

## Purpose

Ensure proper multi-tenant data isolation and security for all STR/BNB reporting endpoints by implementing the `@tenant_required()` decorator and proper SQL filtering.

## Documents

### 1. TENANT_FILTERING_CHECKLIST.md
A comprehensive checklist of all STR/BNB endpoints that require tenant filtering, organized by route file and priority.

**Contents:**
- Complete list of 15 endpoints across 3 route files
- Current implementation status for each endpoint
- Required changes for each endpoint
- Priority classification (HIGH/MEDIUM/LOW)
- Implementation strategy
- Testing plan

### 2. tasks.md
Detailed task breakdown with subtasks for implementing tenant filtering.

**Contents:**
- 15 main tasks organized into 5 phases
- Subtasks for each endpoint implementation
- Testing requirements for each task
- Code patterns and examples
- Success criteria

## Quick Start

### For Implementers

1. Review `TENANT_FILTERING_CHECKLIST.md` to understand scope
2. Follow `tasks.md` for step-by-step implementation
3. Start with Phase 1 (HIGH priority endpoints)
4. Create tests as you implement each endpoint
5. Update checklist as tasks are completed

### For Reviewers

1. Check `TENANT_FILTERING_CHECKLIST.md` for completion status
2. Verify each endpoint has proper tenant filtering
3. Review test coverage in `tasks.md` Phase 5
4. Validate no cross-tenant data leakage

## Endpoint Summary

### Total Endpoints: 15

**By Status:**
- ✅ Already Implemented: 3 endpoints
- ❌ Missing Tenant Filtering: 10 endpoints
- ⚠️ Review Needed: 2 endpoints

**By Priority:**
- HIGH: 5 endpoints (security critical)
- MEDIUM: 6 endpoints (aggregated data)
- LOW: 2 endpoints (administrative)

**By Route File:**
- `bnb_routes.py`: 8 endpoints
- `str_channel_routes.py`: 3 endpoints (2 done, 1 pending)
- `str_invoice_routes.py`: 4 endpoints (1 done, 3 pending)

## Implementation Phases

### Phase 1: BNB Routes - High Priority (Tasks 1-4)
Critical data endpoints that expose raw booking and guest data.
- bnb-listing-data
- bnb-channel-data
- bnb-table
- bnb-guest-bookings

### Phase 2: BNB Routes - Medium Priority (Tasks 5-8)
Aggregated data and filter options.
- bnb-actuals
- bnb-filter-options
- bnb-violin-data
- bnb-returning-guests

### Phase 3: STR Routes - Write Operations (Tasks 9-10)
Endpoints that modify data.
- str-channel/save
- str-invoice/generate-invoice

### Phase 4: Administrative Endpoints (Tasks 11-12)
Review and decision needed.
- str-invoice/upload-template-to-drive
- str-invoice/test

### Phase 5: Testing and Documentation (Tasks 13-15)
Comprehensive testing and documentation updates.

## Key Implementation Patterns

### Pattern 1: Multi-Tenant Filter (BNB Routes)
```python
@bnb_bp.route('/endpoint', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
@tenant_required()
def endpoint_handler(user_email, user_roles, tenant, user_tenants):
    # Build tenant filter
    placeholders = ', '.join(['%s'] * len(user_tenants))
    where_conditions.append(f"administration IN ({placeholders})")
    params.extend(user_tenants)
    
    # Execute query with filter
    query = f"SELECT * FROM bnb WHERE {where_clause}"
    cursor.execute(query, params)
```

### Pattern 2: Single Tenant Validation (STR Routes)
```python
@str_bp.route('/endpoint', methods=['POST'])
@cognito_required(required_permissions=['str_create'])
@tenant_required()
def endpoint_handler(user_email, user_roles, tenant, user_tenants):
    administration = data.get('administration', tenant)
    
    # Validate access
    if administration not in user_tenants:
        return jsonify({
            'success': False, 
            'error': 'Access denied to administration'
        }), 403
    
    # Proceed with operation
```

## Testing Strategy

### Test Scenarios

1. **Single Tenant User**
   - User has access to only one tenant
   - Can only see data for that tenant
   - Gets 403 when requesting other tenant data

2. **Multi-Tenant User**
   - User has access to multiple tenants
   - Sees combined data from all accessible tenants
   - Filter options include data from all tenants

3. **Unauthorized Access**
   - User requests data for tenant they don't have access to
   - Returns 403 with clear error message
   - No data leakage in error response

4. **SysAdmin User** (if applicable)
   - Can access all tenant data
   - Bypasses tenant filtering when `allow_sysadmin=True`

### Test Coverage Goals

- Unit tests: 100% of endpoints
- Integration tests: All critical paths
- Security tests: Cross-tenant access attempts
- Performance tests: Query performance impact

## Database Schema

### BNB Table
- **Table**: `bnb`
- **View**: `vw_bnb_total`
- **Tenant Column**: `administration`
- **Key Fields**: listing, channel, year, guestName, reservationCode

### Mutaties Table
- **Table**: `mutaties`
- **View**: `vw_mutaties`
- **Tenant Column**: `administration`
- **Key Fields**: Reknum, ReferenceNumber, TransactionDate

## Security Considerations

1. **SQL Injection Prevention**
   - Always use parameterized queries
   - Never concatenate user input into SQL
   - Use placeholders for tenant lists

2. **Data Isolation**
   - Every query must filter by tenant
   - No endpoint should expose cross-tenant data
   - Validate tenant access before any operation

3. **Error Messages**
   - Don't leak tenant names in errors
   - Use generic "Access denied" messages
   - Log detailed errors server-side only

4. **Performance**
   - Index `administration` column
   - Monitor query performance
   - Optimize tenant filtering queries

## Related Documentation

- **Main Architecture**: `.kiro/specs/Common/Multitennant/architecture.md`
- **FIN Reports**: `.kiro/specs/FIN/Reports/TENANT_FILTERING_CHECKLIST.md`
- **Tenant Context**: `backend/src/auth/tenant_context.py`
- **Phase 5 Summary**: `.kiro/specs/Common/Multitennant/AA PHASE5_TENANT_MODULES_COMPLETE.md`

## Progress Tracking

Track progress using the checklist in `TENANT_FILTERING_CHECKLIST.md`:
- [ ] = Not started
- [-] = In progress
- [x] = Completed

Update the checklist as each task is completed.

## Questions or Issues

If you encounter issues during implementation:

1. Review the tenant_context.py implementation
2. Check existing implementations in FIN Reports
3. Verify database schema has administration column
4. Test with multiple tenant scenarios
5. Document any edge cases or decisions

## Next Steps

1. Start with Phase 1 HIGH priority endpoints
2. Implement one endpoint at a time
3. Write tests for each endpoint
4. Update checklist as you progress
5. Review and validate before moving to next phase

## Success Metrics

- ✅ All endpoints have tenant filtering
- ✅ No cross-tenant data leakage
- ✅ Test coverage > 80%
- ✅ Performance impact < 10%
- ✅ Documentation complete
- ✅ Code review passed
