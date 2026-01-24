# Multi-Tenant Architecture Documentation

This folder contains all documentation for the multi-tenant implementation in myAdmin.

## Overview

myAdmin supports up to 100 tenants using a **shared database with tenant isolation** approach. Users can belong to multiple tenants and switch between them seamlessly.

## Documentation Structure

### Architecture & Requirements

- **[requirements.md](./requirements.md)** - Original requirements and acceptance criteria
- **[architecture.md](./architecture.md)** - Complete multi-tenant architecture design
- **[design-decisions.md](./design-decisions.md)** - Key architectural decisions

### Phase 1: Database Schema

- **[phase1_migration_complete.md](./phase1_migration_complete.md)** - Database schema migration summary
- **[phase1_test_results.md](./phase1_test_results.md)** - Phase 1 testing results

### Phase 2: Cognito Setup

- **[PHASE2_COGNITO_SETUP.md](./PHASE2_COGNITO_SETUP.md)** - Cognito configuration and setup
- **[TENANT_MANAGEMENT_QUICK_REFERENCE.md](./TENANT_MANAGEMENT_QUICK_REFERENCE.md)** - Quick reference for tenant management

### Phase 3: Backend Implementation ✅ COMPLETE

#### Summary & Status
- **[PHASE3_COMPLETE.md](./PHASE3_COMPLETE.md)** - Phase 3 completion summary and overview
- **[PHASE3_IMPLEMENTATION_CHECKLIST.md](./PHASE3_IMPLEMENTATION_CHECKLIST.md)** - Implementation tracking checklist

#### Developer Guides
- **[TENANT_CONTEXT_QUICK_REFERENCE.md](./TENANT_CONTEXT_QUICK_REFERENCE.md)** - Quick reference for developers
- **[tenant_filtering_migration_guide.md](./tenant_filtering_migration_guide.md)** - Step-by-step migration guide
- **[phase3_backend_implementation_summary.md](./phase3_backend_implementation_summary.md)** - Detailed implementation summary

## Quick Start

### For Developers

1. **Start here**: [TENANT_CONTEXT_QUICK_REFERENCE.md](./TENANT_CONTEXT_QUICK_REFERENCE.md)
2. **Migrating routes**: [tenant_filtering_migration_guide.md](./tenant_filtering_migration_guide.md)
3. **Example code**: `../../backend/src/reporting_routes_tenant_example.py`

### For Architects

1. **Architecture overview**: [architecture.md](./architecture.md)
2. **Implementation details**: [phase3_backend_implementation_summary.md](./phase3_backend_implementation_summary.md)
3. **Design decisions**: [design-decisions.md](./design-decisions.md)

### For Project Managers

1. **Phase 3 status**: [PHASE3_COMPLETE.md](./PHASE3_COMPLETE.md)
2. **Implementation checklist**: [PHASE3_IMPLEMENTATION_CHECKLIST.md](./PHASE3_IMPLEMENTATION_CHECKLIST.md)
3. **Requirements**: [requirements.md](./requirements.md)

## Implementation Status

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1: Database Schema | ✅ Complete | 100% |
| Phase 2: Cognito Setup | ✅ Complete | 100% |
| Phase 3: Backend Core | ✅ Complete | 100% |
| Phase 3: Route Migration | 🔄 In Progress | 0% |
| Phase 4: Frontend | ⏳ Pending | 0% |
| Phase 5: Testing & Deployment | ⏳ Pending | 0% |

## Key Features Implemented

### Phase 1 ✅
- Added `administration` field to all tables (lowercase)
- Created `tenant_config` table
- Updated views with tenant filtering
- Added performance indexes

### Phase 2 ✅
- Configured `custom:tenants` attribute in Cognito
- Created Tenant_Admin and module-based groups
- Created tenant management scripts
- Removed legacy groups

### Phase 3 ✅
- Tenant context management (`tenant_context.py`)
- Tenant admin API (6 endpoints)
- SQL query filtering helpers
- Unit tests (23 tests, all passing)
- Comprehensive documentation

## Core Concepts

### Tenant Assignment

Users are assigned to tenants via the `custom:tenants` attribute in their JWT token:

```json
{
  "email": "user@test.com",
  "custom:tenants": ["GoodwinSolutions", "PeterPrive"],
  "cognito:groups": ["Finance_CRUD", "Tenant_Admin"]
}
```

### Tenant Selection

Users select their active tenant via the `X-Tenant` header:

```http
GET /api/invoices
Headers:
  Authorization: Bearer <jwt_token>
  X-Tenant: GoodwinSolutions
```

### Tenant Filtering

All queries are automatically filtered by tenant:

```python
@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
@tenant_required()
def get_invoices(user_email, user_roles, tenant, user_tenants):
    query = "SELECT * FROM mutaties WHERE administration = %s"
    results = db.execute_query(query, [tenant], fetch=True)
    return jsonify({'data': results})
```

### Tenant Admin

Tenant_Admin role can manage their assigned tenants:
- Configure tenant settings (Google Drive, S3, email)
- Manage tenant secrets (API keys, credentials)
- Assign/remove module roles to users
- View tenant-specific audit logs

## API Endpoints

### Tenant Admin API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/tenant/config` | GET | Get tenant configuration |
| `/api/tenant/config` | POST | Set tenant configuration |
| `/api/tenant/config/<key>` | DELETE | Delete configuration |
| `/api/tenant/users` | GET | List tenant users |
| `/api/tenant/users/<user>/roles` | POST | Assign role |
| `/api/tenant/users/<user>/roles/<role>` | DELETE | Remove role |

## Code Examples

### Basic Tenant Filtering

```python
from auth import tenant_required

@app.route('/api/data', methods=['GET'])
@cognito_required(required_permissions=['data_read'])
@tenant_required()
def get_data(user_email, user_roles, tenant, user_tenants):
    query = "SELECT * FROM table WHERE administration = %s"
    results = db.execute_query(query, [tenant], fetch=True)
    return jsonify({'data': results})
```

### Using Helper Function

```python
from auth import tenant_required, add_tenant_filter

@app.route('/api/data', methods=['GET'])
@cognito_required(required_permissions=['data_read'])
@tenant_required()
def get_data(user_email, user_roles, tenant, user_tenants):
    query = "SELECT * FROM table WHERE date > %s"
    params = ['2024-01-01']
    
    # Add tenant filter automatically
    query, params = add_tenant_filter(query, params, tenant)
    
    results = db.execute_query(query, params, fetch=True)
    return jsonify({'data': results})
```

### Tenant Admin Check

```python
from auth import tenant_required, is_tenant_admin

@app.route('/api/tenant/settings', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def update_settings(user_email, user_roles, tenant, user_tenants):
    if not is_tenant_admin(user_roles, tenant, user_tenants):
        return jsonify({'error': 'Tenant admin required'}), 403
    
    # Update settings...
    return jsonify({'success': True})
```

## Testing

### Unit Tests

Run tenant context tests:

```bash
cd backend
python -m pytest tests/test_tenant_context.py -v
```

All 23 tests should pass.

### Manual Testing

Test with cURL:

```bash
# Get data for GoodwinSolutions
curl -H "Authorization: Bearer <token>" \
     -H "X-Tenant: GoodwinSolutions" \
     http://localhost:5000/api/invoices

# Try unauthorized tenant (should fail with 403)
curl -H "Authorization: Bearer <token_goodwin_only>" \
     -H "X-Tenant: PeterPrive" \
     http://localhost:5000/api/invoices
```

## Next Steps

### Immediate Actions

1. **Migrate Existing Routes** (2-3 days)
   - Start with reporting routes
   - Update financial routes
   - Update STR routes

2. **Integration Testing** (1 day)
   - Test tenant isolation
   - Test unauthorized access
   - Test Tenant_Admin operations

3. **Secret Encryption** (1 day)
   - Implement AWS KMS encryption
   - Update config functions

### Phase 4: Frontend Integration

1. Add tenant selector component
2. Store selected tenant in context
3. Include X-Tenant header in API calls
4. Display current tenant to user
5. Test tenant switching

### Phase 5: Testing & Deployment

1. Test with each tenant
2. Test role combinations
3. Performance testing
4. Deploy to staging
5. Deploy to production

## Support

For questions or issues:

1. Check the [Quick Reference](./TENANT_CONTEXT_QUICK_REFERENCE.md)
2. Review the [Migration Guide](./tenant_filtering_migration_guide.md)
3. See [Example Routes](../../backend/src/reporting_routes_tenant_example.py)
4. Review the [Implementation Checklist](./PHASE3_IMPLEMENTATION_CHECKLIST.md)

## Files Reference

### Implementation Files

- `backend/src/auth/tenant_context.py` - Tenant context management
- `backend/src/tenant_admin_routes.py` - Tenant admin API
- `backend/src/reporting_routes_tenant_example.py` - Example routes
- `backend/tests/test_tenant_context.py` - Unit tests

### Database Files

- `backend/sql/phase1_multitenant_schema.sql` - Database migration script
- `backend/scripts/run_phase1_migration.py` - Migration runner

### Infrastructure Files

- `infrastructure/cognito.tf` - Cognito configuration
- `infrastructure/assign-user-tenants.ps1` - Tenant assignment script
- `infrastructure/create-cognito-user.ps1` - User creation script

## Version History

- **2026-01-24**: Phase 3 core infrastructure complete
- **2026-01-24**: Phase 2 Cognito setup complete
- **2026-01-24**: Phase 1 database schema complete

---

**Current Status**: Phase 3 Core Complete ✅  
**Next Phase**: Route Migration → Frontend Integration → Testing → Deployment
