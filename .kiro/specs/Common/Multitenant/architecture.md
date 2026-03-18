# Multi-Tenant Architecture for myAdmin

## Overview

myAdmin will support up to 100 tenants using a **shared database with tenant isolation** approach.

**Important Design Decision:** All database identifiers (tables, columns, views) use **lowercase** for PostgreSQL compatibility and future migration.

## Current State

- **Existing Tenants:** PeterPrive, InterimManagement, GoodwinSolutions
- **Database Field:** `Administration` field exists in some tables (mutaties, rekeningschema)
- **Issue:** Inconsistent implementation - some tables missing the field, some use lowercase `administration`

## Proposed Architecture

### 1. Tenant Definition (Cognito)

**Approach:** Use Cognito Custom Attributes + Single Tenant_Admin Role

```
User Attributes:
- custom:tenants = ["GoodwinSolutions", "PeterPrive"]  // JSON array of allowed tenants

Cognito Groups (Roles) - Tenant-agnostic:
- Tenant_Admin           // Admin role (tenant determined by custom:tenants)
- Finance_CRUD           // Module access (works with tenant assignment)
- STR_CRUD               // Module access (works with tenant assignment)
- Finance_Read           // Read-only module access
- STR_Read               // Read-only module access
- Finance_Export         // Export permission
- STR_Export             // Export permission
- SysAdmin               // System administration (no tenant data access)

Example Users:
1. Tenant Admin for GoodwinSolutions:
   - Roles: [Tenant_Admin]
   - custom:tenants: ["GoodwinSolutions"]
   - Can manage: GoodwinSolutions config, users, secrets

2. Accountant for multiple tenants:
   - Roles: [Finance_CRUD]
   - custom:tenants: ["GoodwinSolutions", "PeterPrive"]
   - Can access: Finance data for both tenants

3. Tenant Admin for multiple tenants:
   - Roles: [Tenant_Admin]
   - custom:tenants: ["GoodwinSolutions", "PeterPrive"]
   - Can manage: Both tenants' configs, users, secrets
```

**Tenant_Admin Permissions:**

- Configure tenant-specific integrations (Google Drive, S3, OneDrive, email) for their assigned tenants
- Manage tenant secrets (API keys, credentials) - encrypted per tenant
- Add/remove users to their assigned tenants
- Assign module roles (Finance_CRUD, STR_CRUD) to users within their tenants
- View tenant-specific audit logs for their tenants
- Cannot access tenants not in their custom:tenants list

**Benefits:**

- Single Tenant_Admin role (scalable to 100+ tenants)
- Tenant assignment via custom:tenants attribute
- Users can be admin for multiple tenants
- No need to create new Cognito groups per tenant
- Easy to add/remove tenant access
- Integrates with existing Cognito RBAC
- Tenant-specific configuration management

### 2. Database Schema Standardization

**Action:** Add `administration` field (VARCHAR(50), lowercase) to all tables

**Rationale:**

- Lowercase is standard for PostgreSQL migration
- More portable across databases
- Consistent with modern database practices

**Tables requiring update:**

```sql
-- Add administration field (lowercase)
ALTER TABLE bnb ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE bnbfuture ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE bnblookup ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE bnbplanned ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE listings ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE pricing_events ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE pricing_recommendations ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';

-- Rename uppercase to lowercase (for consistency)
ALTER TABLE mutaties CHANGE Administration administration VARCHAR(50);
ALTER TABLE rekeningschema CHANGE Administration administration VARCHAR(50);
-- pattern_analysis_metadata and pattern_verb_patterns already use lowercase ✓
```

**Views requiring update:**

```sql
-- Update all views to use lowercase 'administration'
-- vw_bnb_total - add administration field
-- vw_readreferences - already uses lowercase ✓
```

**Generic Tables (No tenant field needed):**

- countries
- database_migrations (SysAdmin only)
- duplicate_decision_log (SysAdmin only)

**New Table: Tenant Configuration**

```sql
CREATE TABLE tenant_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    config_key VARCHAR(100) NOT NULL,
    config_value TEXT,  -- Encrypted for secrets
    is_secret BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    UNIQUE KEY unique_tenant_config (administration, config_key),
    INDEX idx_administration (administration)
);

-- Example tenant configurations:
-- administration='GoodwinSolutions', config_key='google_drive_folder_id', config_value='encrypted_value', is_secret=true
-- administration='GoodwinSolutions', config_key='email_from', config_value='admin@goodwin.com', is_secret=false
-- administration='PeterPrive', config_key='s3_bucket', config_value='encrypted_value', is_secret=true
```

- More portable across databases
- Consistent with modern database practices

**Tables requiring update:**

```sql
-- Add administration field (lowercase)
ALTER TABLE bnb ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE bnbfuture ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE bnblookup ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE bnbplanned ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE listings ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE pricing_events ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';
ALTER TABLE pricing_recommendations ADD COLUMN administration VARCHAR(50) DEFAULT 'GoodwinSolutions';

-- Rename uppercase to lowercase (for consistency)
ALTER TABLE mutaties CHANGE Administration administration VARCHAR(50);
ALTER TABLE rekeningschema CHANGE Administration administration VARCHAR(50);
-- pattern_analysis_metadata and pattern_verb_patterns already use lowercase ✓
```

**Views requiring update:**

```sql
-- Update all views to use lowercase 'administration'
-- vw_bnb_total - add administration field
-- vw_readreferences - already uses lowercase ✓
```

**Generic Tables (No tenant field needed):**

- countries
- database_migrations (SysAdmin only)
- duplicate_decision_log (SysAdmin only)

### 3. Backend Implementation

**Tenant Context Middleware:**

```python
# Extract tenant from JWT token
def get_user_tenants(jwt_token):
    """Extract custom:tenants from JWT"""
    payload = decode_jwt(jwt_token)
    return payload.get('custom:tenants', [])

def get_tenant_admin_role(tenant):
    """Get tenant admin role name - single role for all tenants"""
    return "Tenant_Admin"

def is_tenant_admin(user_roles, tenant, user_tenants):
    """Check if user is admin for specific tenant"""
    has_admin_role = "Tenant_Admin" in user_roles
    has_tenant_access = tenant in user_tenants
    return has_admin_role and has_tenant_access

def get_current_tenant(request):
    """Get tenant from request header or use default"""
    # Option 1: From header (user selected)
    tenant = request.headers.get('X-Tenant')

    # Option 2: From JWT default
    if not tenant:
        tenant = get_default_tenant(jwt_token)

    return tenant

# Apply to all queries
@cognito_required(required_permissions=['invoices_read'])
def get_invoices(user_email, user_roles):
    tenant = get_current_tenant(request)
    user_tenants = get_user_tenants(request)

    # Verify user has access to requested tenant
    if tenant not in user_tenants:
        return jsonify({'error': 'Access denied to tenant'}), 403

    # Filter by tenant
    query = "SELECT * FROM mutaties WHERE Administration = %s"
    results = db.execute(query, [tenant])
    return jsonify(results)
```

**SysAdmin Access:**

```python
# SysAdmin role does NOT grant tenant data access (separation of duties)
# SysAdmin needs explicit tenant assignment + module role to access tenant data

# Example 1: SysAdmin only (no tenant access)
if 'SysAdmin' in user_roles and not user_tenants:
    # Can only access system tables, no tenant data
    return jsonify({'error': 'No tenant access'}), 403

# Example 2: SysAdmin + Finance_CRUD + tenant assignment (development/testing)
if 'SysAdmin' in user_roles and 'Finance_CRUD' in user_roles and user_tenants:
    # Has both system admin AND tenant data access
    # This is allowed during development but should be avoided in production
    query = "SELECT * FROM mutaties WHERE administration = %s"
    results = db.execute(query, [tenant])

# Production best practice: Separate users
# - SysAdmin user: System management only, no tenant assignments
# - Finance user: Tenant data access only, no SysAdmin role
```

**Tenant_Admin API Endpoints:**

```python
# Tenant Configuration Management
@app.route('/api/tenant/config', methods=['GET'])
@cognito_required(required_permissions=[])
def get_tenant_config(user_email, user_roles):
    """Get tenant configuration (Tenant_Admin only)"""
    tenant = get_current_tenant(request)

    # Check if user is tenant admin
    if not is_tenant_admin(user_roles, tenant):
        return jsonify({'error': 'Tenant admin access required'}), 403

    # Get non-secret configs
    query = "SELECT config_key, config_value FROM tenant_config WHERE administration = %s AND is_secret = FALSE"
    configs = db.execute(query, [tenant])

    # Get secret keys (but not values)
    secret_query = "SELECT config_key FROM tenant_config WHERE administration = %s AND is_secret = TRUE"
    secrets = db.execute(secret_query, [tenant])

    return jsonify({
        'configs': configs,
        'secrets': [s['config_key'] for s in secrets]
    })

@app.route('/api/tenant/config', methods=['POST'])
@cognito_required(required_permissions=[])
def set_tenant_config(user_email, user_roles):
    """Set tenant configuration (Tenant_Admin only)"""
    tenant = get_current_tenant(request)

    if not is_tenant_admin(user_roles, tenant):
        return jsonify({'error': 'Tenant admin access required'}), 403

    data = request.get_json()
    config_key = data.get('config_key')
    config_value = data.get('config_value')
    is_secret = data.get('is_secret', False)

    # Encrypt if secret
    if is_secret:
        config_value = encrypt_value(config_value, tenant)

    query = """
        INSERT INTO tenant_config (administration, config_key, config_value, is_secret, created_by)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE config_value = %s, updated_at = NOW()
    """
    db.execute(query, [tenant, config_key, config_value, is_secret, user_email, config_value])

    # Audit log
    audit_log.info(f"Tenant config updated: {tenant}.{config_key} by {user_email}")

    return jsonify({'success': True})

@app.route('/api/tenant/users', methods=['GET'])
@cognito_required(required_permissions=[])
def get_tenant_users(user_email, user_roles):
    """Get users in tenant (Tenant_Admin only)"""
    tenant = get_current_tenant(request)

    if not is_tenant_admin(user_roles, tenant):
        return jsonify({'error': 'Tenant admin access required'}), 403

    # Get all users with this tenant assignment
    users = cognito_client.list_users(UserPoolId=USER_POOL_ID)
    tenant_users = []

    for user in users['Users']:
        user_tenants = get_user_attribute(user, 'custom:tenants')
        if tenant in user_tenants:
            tenant_users.append({
                'email': get_user_attribute(user, 'email'),
                'roles': get_user_groups(user['Username'])
            })

    return jsonify({'users': tenant_users})

@app.route('/api/tenant/users/<username>/roles', methods=['POST'])
@cognito_required(required_permissions=[])
def assign_tenant_role(username, user_email, user_roles):
    """Assign role to user within tenant (Tenant_Admin only)"""
    tenant = get_current_tenant(request)

    if not is_tenant_admin(user_roles, tenant):
        return jsonify({'error': 'Tenant admin access required'}), 403

    data = request.get_json()
    role = data.get('role')

    # Verify user belongs to this tenant
    user_tenants = get_user_tenants_from_cognito(username)
    if tenant not in user_tenants:
        return jsonify({'error': 'User not in this tenant'}), 403

    # Only allow assigning module roles (not SysAdmin or other Tenant_Admin roles)
    allowed_roles = ['Finance_CRUD', 'Finance_Read', 'Finance_Export', 'STR_CRUD', 'STR_Read', 'STR_Export']
    if role not in allowed_roles:
        return jsonify({'error': 'Cannot assign this role'}), 403

    # Assign role
    cognito_client.admin_add_user_to_group(
        UserPoolId=USER_POOL_ID,
        Username=username,
        GroupName=role
    )

    # Audit log
    audit_log.info(f"Tenant admin {user_email} assigned {role} to {username} in {tenant}")

    return jsonify({'success': True})
```

### 4. Frontend Implementation

**Tenant Selector Component:**

```typescript
// Show tenant selector if user has multiple tenants
const TenantSelector = () => {
  const { user } = useAuth();
  const [currentTenant, setCurrentTenant] = useState<string>();

  // Get tenants from JWT
  const tenants = user?.tenants || [];

  // Initialize default tenant on mount
  useEffect(() => {
    if (tenants.length > 0 && !currentTenant) {
      // Option 1: Use localStorage preference
      const savedTenant = localStorage.getItem('selectedTenant');
      if (savedTenant && tenants.includes(savedTenant)) {
        setCurrentTenant(savedTenant);
      } else {
        // Option 2: Use first tenant in array
        setCurrentTenant(tenants[0]);
      }
    }
  }, [tenants]);

  // Save preference when changed
  const handleTenantChange = (tenant: string) => {
    setCurrentTenant(tenant);
    localStorage.setItem('selectedTenant', tenant);
    // Trigger API refresh with new tenant
  };

  if (tenants.length <= 1) return null;

  return (
    <Select value={currentTenant} onChange={(e) => handleTenantChange(e.target.value)}>
      {tenants.map(t => <option key={t} value={t}>{t}</option>)}
    </Select>
  );
};
```

**Note**: Default tenant selection is handled by frontend (localStorage + first tenant fallback), not by Cognito attribute.

**API Calls:**

```typescript
// Include tenant in all API calls
fetch("/api/invoices", {
  headers: {
    Authorization: `Bearer ${token}`,
    "X-Tenant": currentTenant,
  },
});
```

### 5. Migration Strategy

- [x] **Phase 1: Database Schema (1-2 hours)** ✅ COMPLETE

**Reference**: See section "2. Database Schema Standardization" above for detailed SQL scripts

**Status**: Completed on 2026-01-24

**What was done**:

1. ✅ Added `administration` field (lowercase) to all tables (see SQL ALTER TABLE statements)
2. ✅ Renamed existing `Administration` to `administration` (lowercase) in mutaties and rekeningschema
3. ✅ Updated views to include `administration` (lowercase)
4. ✅ Created `tenant_config` table for tenant-specific settings
5. ✅ Set default values for existing data (e.g., 'GoodwinSolutions')
6. ✅ Added performance indexes on all `administration` columns

**Files created**:

- `backend/sql/phase1_multitenant_schema.sql` - SQL migration script
- `backend/scripts/run_phase1_migration.py` - Python migration runner
- `backend/docs/phase1_migration_complete.md` - Complete documentation

**Verification**: 21 tables now have `administration` field, 10 tables have indexes, `tenant_config` table created

- [x] **Phase 2: Cognito Setup (1 hour)** ✅ COMPLETE

**Reference**: See section "1. Tenant Definition (Cognito)" above for detailed configuration

**Status**: Completed on 2026-01-24

**What was done**:

1. ✅ Added `custom:tenants` attribute to User Pool (already existed as "tenants" schema)
2. ✅ Created Tenant_Admin Cognito group in Terraform
3. ✅ Created module-based groups (Finance*\*, STR*\*, SysAdmin) in Terraform
4. ✅ Updated user creation scripts to support tenant assignment
5. ✅ Created `assign-user-tenants.ps1` script for managing tenant assignments
6. ✅ Updated `create-cognito-user.ps1` to support multiple groups and tenants
7. ✅ Updated `create-module-groups.ps1` to include Tenant_Admin group
8. ✅ Updated `assign-user-groups.ps1` with Tenant_Admin information
9. ✅ Created comprehensive documentation in `.kiro/specs/Common/Multitennant/PHASE2_COGNITO_SETUP.md`
10. ✅ Removed legacy groups (Administrators, Accountants, Viewers)

**Files created/updated**:

- `infrastructure/cognito.tf` - Added Tenant_Admin and module groups, removed legacy groups
- `infrastructure/assign-user-tenants.ps1` - New script for tenant management
- `infrastructure/create-cognito-user.ps1` - Updated for multi-tenant support
- `infrastructure/create-module-groups.ps1` - Added Tenant_Admin group
- `infrastructure/assign-user-groups.ps1` - Updated documentation
- `.kiro/specs/Common/Multitennant/PHASE2_COGNITO_SETUP.md` - Complete Phase 2 documentation
- `.kiro/specs/Common/Multitennant/TENANT_MANAGEMENT_QUICK_REFERENCE.md` - Quick reference guide

**Deployment steps**:

1. Apply Terraform changes: `cd infrastructure && terraform apply`
2. Assign tenants to users: `.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "GoodwinSolutions" -Action set`
3. Verify JWT tokens contain `custom:tenants` attribute

**Verification**: All Cognito groups created, scripts functional, documentation complete

- [x] **Phase 3: Backend (4-6 hours)**

**Reference**: See section "3. Backend Implementation" above for detailed code examples

1. Create tenant context middleware (see `get_user_tenants()`, `get_current_tenant()` functions)
2. Implement Tenant_Admin validation (see `is_tenant_admin()` function)
3. Update all queries to filter by `administration` field
4. Add tenant validation to all endpoints (verify user has tenant access)
5. Create Tenant_Admin API endpoints (see tenant config/user management endpoints)
6. Implement tenant secret encryption for `tenant_config` table
7. Test with multiple tenants and role combinations

- [x] **Phase 4: Frontend (2-3 hours)**

**Reference**: See section "4. Frontend Implementation" above for detailed component code

1. Add tenant selector component (see `TenantSelector` component with localStorage)
2. Store selected tenant in context
3. Include tenant in API headers (`X-Tenant` header)
4. Display current tenant to user (REQ11)
5. Test tenant switching without re-authentication (REQ7)

- [x] **Phase 5: Testing (2-3 hours)** ✅ COMPLETE

**Reference**: See section "3. Backend Implementation" for SysAdmin access patterns and role combinations

**Status**: Completed on 2026-01-25

**What was done**:

1. ✅ Created comprehensive integration test suite (`backend/tests/integration/test_multitenant_phase5.py`)
2. ✅ Tested with each tenant (PeterPrive, InterimManagement, GoodwinSolutions)
3. ✅ Tested tenant switching without re-authentication (REQ7)
4. ✅ Tested role combinations:
   - SysAdmin only (should NOT access tenant data - REQ12)
   - Finance_CRUD + tenant (should access tenant data)
   - SysAdmin + Finance_CRUD + tenant (development mode - REQ12a)
   - Tenant_Admin + tenant (can manage tenant config and users - REQ16-REQ20)
5. ✅ Tested user with multiple tenants (REQ4)
6. ✅ Tested Tenant_Admin functions (config management, user management, secrets)
7. ✅ Verified database query level filtering (REQ6, REQ13)
8. ✅ Verified no cross-tenant data leakage (REQ15)
9. ✅ Verified lowercase administration field (REQ8)

**Test Results**: 20/20 tests passing

**Files created**:

- `backend/tests/integration/test_multitenant_phase5.py` - Comprehensive integration tests (20 tests)
- `backend/scripts/setup_test_database.py` - Test database setup script (fixed to handle views)
- `backend/sql/create_testfinance_database.sql` - SQL script for test database
- `backend/scripts/create_testfinance_db.ps1` - PowerShell setup script
- `backend/scripts/create_testfinance_db.bat` - Batch file for Windows
- `backend/CREATE_TESTDB_COMMANDS.md` - Manual setup instructions
- `.kiro/specs/Common/Multitennant/PHASE5_TESTING_COMPLETE.md` - Complete documentation

**Test Coverage**:

- Tenant Isolation: 4 tests ✅
- Tenant Switching: 2 tests ✅
- Role Combinations: 5 tests ✅
- Multi-Tenant Users: 2 tests ✅
- Tenant_Admin Functions: 3 tests ✅
- Database Filtering: 3 tests ✅
- Integration: 1 test ✅

**Requirements Validated**: REQ1, REQ4, REQ6, REQ7, REQ8, REQ10, REQ12, REQ12a, REQ13, REQ15, REQ16, REQ17, REQ19, REQ20

**Verification**: All tests passing, multi-tenant architecture fully validated

## Data Isolation

**Row-Level Security:**

- Every query filtered by `Administration = ?`
- Backend enforces tenant access
- SysAdmin can bypass filter

**User Access Control:**

- Users assigned to tenants via Cognito
- JWT contains tenant list
- Backend validates tenant access

## Scalability

**Current Approach Supports:**

- ✅ Up to 100 tenants (shared database)
- ✅ Easy to add new tenants
- ✅ Users can belong to multiple tenants
- ✅ SysAdmin can manage all tenants

**Future Considerations (if > 100 tenants):**

- Database sharding by tenant
- Separate databases per tenant
- Tenant-specific connection pools

## Security

**Tenant Isolation:**

1. JWT contains allowed tenants
2. Backend validates tenant access on every request
3. Database queries filtered by tenant
4. SysAdmin has no access to all tenants

**Audit Trail:**

- Log all tenant switches
- Log cross-tenant access attempts
- Track SysAdmin has no access to tenant data

## Summary

**Best Approach:** Shared database with row-level tenant filtering

**Key Components:**

1. Cognito custom attributes for tenant assignment
2. `Administration` field in all tables
3. Backend middleware for tenant context
4. Frontend tenant selector
5. Query filtering by tenant

**Advantages:**

- Simple to implement
- Cost-effective
- Easy to manage
- Supports up to 100 tenants
- Users can have multiple tenants
- SysAdmin cannot access all tenants
