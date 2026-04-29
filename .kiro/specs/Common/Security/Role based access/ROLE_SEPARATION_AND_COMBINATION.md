# Role Separation and Combination Behavior

**Last Updated**: February 8, 2026  
**Status**: ✅ Verified and Tested

---

## Overview

myAdmin implements a role-based access control (RBAC) system with clear separation between platform management and tenant data access. This document explains how roles work individually and in combination.

---

## Role Types

### 1. SysAdmin Role

**Purpose**: Platform management functions only

**Permissions**:
- User management (create, update, delete users)
- Role assignment (add/remove users from groups)
- System configuration
- Performance monitoring
- Scalability management
- Audit log viewing

**Restrictions**:
- ❌ **NO access to any tenant data** (including myAdmin tenant)
- ❌ Cannot query financial transactions
- ❌ Cannot access Google Drive files
- ❌ Cannot view reports
- ❌ Cannot access invoices or bookings

**Protected Routes**:
- `/api/admin/users` - User management
- `/api/admin/groups` - Role management
- `/api/scalability/dashboard` - System monitoring
- `/api/duplicate-detection/performance/status` - Performance monitoring

**Code Reference**: `backend/src/admin_routes.py`, `backend/src/scalability_routes.py`

---

### 2. Tenant_Admin Role

**Purpose**: Tenant-level administration

**Permissions** (for assigned tenant only):
- Credential management (Google Drive OAuth)
- Template management (upload, validate, approve)
- User invitation and management
- Storage configuration
- Module access control

**Restrictions**:
- ✅ Full access to assigned tenant's data
- ❌ No access to other tenants' data
- ❌ No platform management functions

**Protected Routes**:
- `/api/tenant-admin/credentials` - Credential management
- `/api/tenant-admin/templates/*` - Template management
- `/api/tenant-admin/users` - User management for tenant

**Code Reference**: `backend/src/tenant_admin_routes.py`

---

### 3. Module Roles (Finance, STR)

**Purpose**: Data access control within a tenant

**Finance Roles**:
- `Finance_Read` - View financial data
- `Finance_CRUD` - Create, read, update, delete financial data
- `Finance_Export` - Export financial reports

**STR Roles**:
- `STR_Read` - View short-term rental data
- `STR_CRUD` - Create, read, update, delete STR data
- `STR_Export` - Export STR reports

**Restrictions**:
- ✅ Access to assigned tenant's data only
- ❌ No access to other tenants' data
- ❌ No platform management functions
- ❌ No tenant administration functions

---

## Role Combinations

### Scenario 1: SysAdmin Only

**Roles**: `SysAdmin`  
**Tenant Assignments**: None

**Access**:
- ✅ Platform management functions (user management, system monitoring)
- ❌ **NO tenant data access** (GoodwinSolutions, PeterPrive, myAdmin)

**Use Case**: Platform administrator who manages users and system health but doesn't need to see any business data.

**Test Result**: ✅ Verified - SysAdmin correctly denied access to all tenants

---

### Scenario 2: TenantAdmin Only

**Roles**: `Tenant_Admin`  
**Tenant Assignments**: `GoodwinSolutions`

**Access**:
- ✅ Full administration of GoodwinSolutions tenant
- ✅ Access to GoodwinSolutions data
- ❌ No access to other tenants (PeterPrive, myAdmin)
- ❌ No platform management functions

**Use Case**: Tenant administrator who manages their own tenant's configuration and users.

---

### Scenario 3: TenantAdmin + SysAdmin (Combined Roles)

**Roles**: `Tenant_Admin`, `SysAdmin`  
**Tenant Assignments**: `GoodwinSolutions`

**Access**:
- ✅ Platform management functions (via SysAdmin role)
- ✅ Full administration of GoodwinSolutions tenant (via Tenant_Admin role)
- ✅ Access to GoodwinSolutions data (via tenant assignment)
- ❌ No access to other tenants (PeterPrive, myAdmin)

**Use Case**: Developer or power user who needs both platform management and access to their own tenant's data.

**Important**: The SysAdmin role does NOT grant access to tenant data. Access comes from the tenant assignment, not the SysAdmin role.

**Test Result**: ✅ Verified - Combined roles work correctly with proper isolation

---

### Scenario 4: Multiple Tenant Assignments

**Roles**: `Tenant_Admin`, `Finance_CRUD`  
**Tenant Assignments**: `GoodwinSolutions`, `PeterPrive`

**Access**:
- ✅ Full administration of both GoodwinSolutions and PeterPrive
- ✅ Access to data for both tenants
- ❌ No access to myAdmin tenant
- ❌ No platform management functions

**Use Case**: Accountant or consultant who manages multiple clients.

---

### Scenario 5: myAdmin Tenant Access

**Roles**: `Tenant_Admin`  
**Tenant Assignments**: `myAdmin`

**Access**:
- ✅ Full administration of myAdmin tenant
- ✅ Access to generic templates stored in myAdmin
- ❌ No access to other tenants (GoodwinSolutions, PeterPrive)
- ❌ No platform management functions

**Use Case**: Template manager who maintains generic templates shared across all tenants.

**Important**: myAdmin is a regular tenant, not a special system tenant. Access requires Tenant_Admin role with myAdmin tenant assignment, NOT SysAdmin role.

---

## Technical Implementation

### Tenant Access Validation

**Function**: `validate_tenant_access(user_tenants, requested_tenant)`  
**Location**: `backend/src/auth/tenant_context.py`

**Logic**:
1. Extract user's tenant assignments from JWT token
2. Check if requested tenant is in user's tenant list
3. Return authorization result

**Key Point**: SysAdmin role is NOT checked in this function. Tenant access is purely based on tenant assignments.

### SysAdmin Bypass (Special Cases)

**Decorator**: `@tenant_required(allow_sysadmin=True)`

**Usage**: Only for system-wide operations where SysAdmin needs to see aggregated data across all tenants (e.g., system health dashboard).

**Example**:
```python
@reporting_bp.route('/admin/all-tenants-summary', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
@tenant_required(allow_sysadmin=True)
def get_all_tenants_summary(user_email, user_roles, tenant, user_tenants):
    # SysAdmin can see aggregated data across all tenants
    if 'SysAdmin' in user_roles:
        # Return system-wide summary
        pass
```

**Important**: This is an exception, not the rule. Most routes should NOT use `allow_sysadmin=True`.

---

## Security Principles

### 1. Principle of Least Privilege

Users should only have the minimum permissions needed for their role.

### 2. Separation of Concerns

- Platform management (SysAdmin) is separate from data access (Tenant_Admin, module roles)
- Tenant data is isolated - users can only access their assigned tenants

### 3. Explicit Tenant Assignment

- Tenant access is granted through explicit tenant assignments in JWT token
- Roles alone do not grant tenant access (except with `allow_sysadmin=True`)

### 4. Defense in Depth

- Multiple layers of authorization checks:
  1. JWT token validation
  2. Role verification (`@cognito_required`)
  3. Tenant access validation (`@tenant_required`)
  4. SQL-level tenant filtering (`add_tenant_filter`)

---

## Testing

### Automated Tests

**Location**: `backend/tests/test_sysadmin_role_config.py`

**Tests**:
1. ✅ SysAdmin role exists in Cognito
2. ✅ SysAdmin cannot access tenant data (GoodwinSolutions, PeterPrive, myAdmin)
3. ✅ Combined roles (TenantAdmin + SysAdmin) can access tenant data
4. ✅ Combined roles cannot access other tenants
5. ✅ SysAdmin has platform management functions
6. ✅ All expected roles exist

**Run Tests**:
```bash
python backend/tests/test_sysadmin_role_config.py
```

### Integration Tests

**Location**: `backend/tests/integration/test_multitenant_phase5.py`

**Tests**:
- SysAdmin only (no tenant access)
- Finance_CRUD with tenant (has access)
- SysAdmin + Finance_CRUD + tenant (development mode)
- Tenant_Admin with tenant (can manage tenant)

---

## Common Scenarios

### Q: Can SysAdmin access myAdmin tenant data?

**A**: No. myAdmin is a regular tenant. SysAdmin role does NOT grant access to any tenant data, including myAdmin. To access myAdmin tenant, a user needs Tenant_Admin role with myAdmin tenant assignment.

### Q: Can a user have multiple roles?

**A**: Yes. A user can have multiple roles (e.g., Tenant_Admin + SysAdmin + Finance_CRUD). Each role grants specific permissions.

### Q: Can a user access multiple tenants?

**A**: Yes. A user can be assigned to multiple tenants (e.g., GoodwinSolutions and PeterPrive). They can access data for all assigned tenants.

### Q: How does a user switch between tenants?

**A**: The frontend sends the `X-Tenant` header with each request. The backend validates that the user has access to the requested tenant.

### Q: What happens if SysAdmin tries to access tenant data?

**A**: The request is denied with a 403 Forbidden error. The `validate_tenant_access` function checks tenant assignments, not roles.

---

## Configuration

### Cognito Groups

**Location**: `infrastructure/cognito.tf`

**Groups**:
- `SysAdmin` - Precedence 5
- `Tenant_Admin` - Precedence 4
- `Finance_CRUD` - Precedence 9
- `Finance_Read` - Precedence 10
- `Finance_Export` - Precedence 11
- `STR_CRUD` - Precedence 19
- `STR_Read` - Precedence 20
- `STR_Export` - Precedence 21

**Precedence**: Lower number = higher priority (used for default role selection)

### JWT Token Structure

**Custom Attributes**:
- `custom:tenants` - JSON array of tenant names (e.g., `["GoodwinSolutions", "PeterPrive"]`)
- `custom:role` - Primary role (deprecated, use groups instead)
- `custom:tenant_id` - Primary tenant ID (deprecated, use tenants array)

**Groups**: Array of group names (e.g., `["SysAdmin", "Tenant_Admin", "Finance_CRUD"]`)

---

## Maintenance

### Adding a New Role

1. Add Cognito group in `infrastructure/cognito.tf`
2. Deploy with Terraform: `terraform apply`
3. Update role checks in backend code
4. Update this documentation
5. Add tests for new role

### Modifying Role Permissions

1. Update route decorators (`@cognito_required(required_roles=[...])`)
2. Update this documentation
3. Update tests
4. Notify users of permission changes

---

## References

- **Cognito Configuration**: `infrastructure/cognito.tf`
- **Authentication Decorators**: `backend/src/auth/cognito_utils.py`
- **Tenant Context**: `backend/src/auth/tenant_context.py`
- **Admin Routes**: `backend/src/admin_routes.py`
- **Tenant Admin Routes**: `backend/src/tenant_admin_routes.py`
- **Integration Tests**: `backend/tests/integration/test_multitenant_phase5.py`

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-02-08 | Initial documentation - Phase 3.2 complete | System |
| 2026-02-08 | Verified all tests passing | System |

