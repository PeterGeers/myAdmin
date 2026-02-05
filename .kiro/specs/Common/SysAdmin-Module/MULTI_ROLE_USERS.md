# Multi-Role Users - Clarification

**Date**: February 5, 2026
**Status**: Critical Concept

---

## 🎯 Key Concept

**SysAdmin restrictions apply to the ROLE, not the PERSON.**

A user can have multiple roles and access different tenants based on which tenant they're currently in.

---

## 👤 Example User: Peter

**Email**: peter@example.com

**Roles**:
- SysAdmin (Cognito group)
- Tenant_Admin for GoodwinSolutions (Cognito group)
- Tenant_Admin for PeterPrive (Cognito group)

**Available Tenants**:
1. myAdmin (via SysAdmin role)
2. GoodwinSolutions (via Tenant_Admin role)
3. PeterPrive (via Tenant_Admin role)

---

## 🔄 Tenant Switching Behavior

### Scenario 1: Peter in myAdmin Tenant

**Active Role**: SysAdmin
**Current Tenant**: myAdmin

**Can Do**:
- ✅ Create new tenant "NewCorp"
- ✅ Create new role "Accountant"
- ✅ Upload generic template
- ✅ View list of all tenants
- ✅ Manage platform settings

**Cannot Do**:
- ❌ View GoodwinSolutions invoices (wrong tenant)
- ❌ View PeterPrive reports (wrong tenant)
- ❌ Create users for GoodwinSolutions (wrong tenant)
- ❌ Access tenant Google Drive credentials

**Why**: SysAdmin role is for platform management only, not tenant data access.

---

### Scenario 2: Peter in GoodwinSolutions Tenant

**Active Role**: Tenant_Admin
**Current Tenant**: GoodwinSolutions

**Can Do**:
- ✅ View all GoodwinSolutions invoices
- ✅ View all GoodwinSolutions reports
- ✅ Create users for GoodwinSolutions
- ✅ Upload custom templates for GoodwinSolutions
- ✅ Manage GoodwinSolutions credentials
- ✅ Configure GoodwinSolutions storage

**Cannot Do**:
- ❌ Create new tenants (not in myAdmin tenant)
- ❌ View PeterPrive invoices (different tenant)
- ❌ Manage platform settings (not in myAdmin tenant)

**Why**: Tenant_Admin role has full access to their assigned tenant's data.

---

### Scenario 3: Peter in PeterPrive Tenant

**Active Role**: Tenant_Admin
**Current Tenant**: PeterPrive

**Can Do**:
- ✅ View all PeterPrive invoices
- ✅ View all PeterPrive reports
- ✅ Create users for PeterPrive
- ✅ Upload custom templates for PeterPrive
- ✅ Manage PeterPrive credentials
- ✅ Configure PeterPrive storage

**Cannot Do**:
- ❌ Create new tenants (not in myAdmin tenant)
- ❌ View GoodwinSolutions invoices (different tenant)
- ❌ Manage platform settings (not in myAdmin tenant)

**Why**: Tenant_Admin role has full access to their assigned tenant's data.

---

## 🔐 Access Control Matrix

| Action | myAdmin Tenant (SysAdmin) | GoodwinSolutions (Tenant_Admin) | PeterPrive (Tenant_Admin) |
|--------|---------------------------|----------------------------------|----------------------------|
| Create tenant | ✅ Yes | ❌ No | ❌ No |
| Manage roles | ✅ Yes | ❌ No | ❌ No |
| Upload generic template | ✅ Yes | ❌ No | ❌ No |
| View GoodwinSolutions invoices | ❌ No | ✅ Yes | ❌ No |
| View PeterPrive invoices | ❌ No | ❌ No | ✅ Yes |
| Create GoodwinSolutions users | ❌ No | ✅ Yes | ❌ No |
| Create PeterPrive users | ❌ No | ❌ No | ✅ Yes |
| Manage GoodwinSolutions templates | ❌ No | ✅ Yes | ❌ No |
| Manage PeterPrive templates | ❌ No | ❌ No | ✅ Yes |

---

## 💻 Implementation

### Frontend: Tenant Selector

```typescript
// User's available tenants (from Cognito token)
const user = {
  email: 'peter@example.com',
  roles: ['SysAdmin', 'Tenant_Admin'],
  tenants: [
    { name: 'myAdmin', role: 'SysAdmin' },
    { name: 'GoodwinSolutions', role: 'Tenant_Admin' },
    { name: 'PeterPrive', role: 'Tenant_Admin' }
  ]
};

// Tenant selector dropdown
<Select value={currentTenant} onChange={switchTenant}>
  <option value="myAdmin">🏢 myAdmin (Platform)</option>
  <option value="GoodwinSolutions">🏢 GoodwinSolutions</option>
  <option value="PeterPrive">🏢 PeterPrive</option>
</Select>

// When user switches tenant
function switchTenant(tenantName) {
  setCurrentTenant(tenantName);
  // Backend validates access based on tenant + user's roles
  // UI updates to show appropriate menu items
}
```

### Backend: Authorization Middleware

```python
from functools import wraps
from flask import request, g

def get_current_tenant():
    """Get current tenant from X-Tenant header"""
    return request.headers.get('X-Tenant')

def get_user_roles():
    """Get user's roles from Cognito token"""
    # Extract from JWT token
    return g.user.roles

def get_user_tenants():
    """Get user's accessible tenants from Cognito"""
    # Extract from JWT token or database
    return g.user.tenants

def require_sysadmin(f):
    """Require SysAdmin role AND myAdmin tenant"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_tenant = get_current_tenant()
        user_roles = get_user_roles()
        
        # Check 1: User must have SysAdmin role
        if 'SysAdmin' not in user_roles:
            return {'error': 'SysAdmin role required'}, 403
        
        # Check 2: User must be in myAdmin tenant
        if current_tenant != 'myAdmin':
            return {'error': 'Must be in myAdmin tenant'}, 403
        
        # Both checks passed
        return f(*args, **kwargs)
    
    return decorated_function

def require_tenant_admin(f):
    """Require Tenant_Admin role for current tenant"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_tenant = get_current_tenant()
        user_tenants = get_user_tenants()
        
        # Check: User must have access to current tenant
        if current_tenant not in [t['name'] for t in user_tenants]:
            return {'error': 'No access to this tenant'}, 403
        
        # Check passed
        return f(*args, **kwargs)
    
    return decorated_function

# Example endpoints
@app.route('/api/sysadmin/tenants')
@cognito_required
@require_sysadmin  # Requires SysAdmin role + myAdmin tenant
def list_tenants():
    return list_all_tenants()

@app.route('/api/invoices')
@cognito_required
@require_tenant_admin  # Requires access to current tenant
def list_invoices():
    current_tenant = get_current_tenant()
    return list_invoices_for_tenant(current_tenant)
```

---

## 🎯 Key Takeaways

1. **Role-based, not person-based**: Restrictions apply to the role being used, not the person.

2. **Tenant-based access**: Access is determined by current tenant + user's roles for that tenant.

3. **SysAdmin role**: Platform management only (when in myAdmin tenant).

4. **Tenant_Admin role**: Full tenant access (when in that tenant).

5. **Multi-role users**: Can switch between tenants and use different roles.

6. **No cross-tenant access**: Cannot access Tenant A's data while in Tenant B.

---

## 📝 Documentation Updates

This clarification has been added to:
- ✅ README.md - New section "Multi-Role Users (Important!)"
- ✅ requirements.md - Updated FR-SA-01, FR-SA-03, FR-SA-04
- ✅ This document (MULTI_ROLE_USERS.md) - Comprehensive explanation

---

## ❓ Common Questions

**Q: Can a SysAdmin view tenant invoices?**
A: No, not when acting as SysAdmin in myAdmin tenant. But if the same user has Tenant_Admin role for that tenant, they can view invoices when they switch to that tenant.

**Q: Why can't SysAdmin access tenant data?**
A: Security and data isolation. SysAdmin is for platform management, not tenant data access. This prevents accidental or unauthorized access to tenant data.

**Q: How does a user with multiple roles access tenant data?**
A: They switch to that tenant using the tenant selector. The system then uses their Tenant_Admin role for that tenant.

**Q: Can a user be Tenant_Admin for multiple tenants?**
A: Yes! A user can be Tenant_Admin for GoodwinSolutions, PeterPrive, and any other tenants they're assigned to.

**Q: What if a user only has SysAdmin role?**
A: They can only access myAdmin tenant for platform management. They cannot access any client tenant data.

---

## ✅ Approval

This clarification is critical for correct implementation.

| Role | Name | Approved | Date |
|------|------|----------|------|
| Product Owner | | ✅ | 2026-02-05 |
| Technical Lead | | ✅ | 2026-02-05 |
| Security Lead | | ✅ | 2026-02-05 |
