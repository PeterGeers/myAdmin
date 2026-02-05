# SysAdmin Module Specification

**Status**: Draft
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## 📖 Overview

The SysAdmin Module provides platform-level administration capabilities for managing the myAdmin system. SysAdmins have access to the myAdmin system tenant and can manage platform-wide resources, but cannot access tenant-specific data.

---

## 📚 Reading Order

### 1. **README.md** (You are here)

- Overview and navigation
- Quick reference

### 2. **requirements.md** ⭐ START HERE

- User stories and acceptance criteria
- Functional requirements
- Non-functional requirements
- Success criteria

### 3. **design.md**

- Technical architecture
- API specifications
- Database schema
- Security model
- Implementation details

### 4. **TASKS.md**

- Detailed implementation tasks
- Phase breakdown
- Progress tracking

---

## 🎯 Key Concepts

### SysAdmin Role

- Platform administrator role (exists in Cognito)
- Access to myAdmin system tenant only
- Cannot access client tenant data
- Manages platform-wide resources

### myAdmin System Tenant

- Special tenant for platform management
- Stores generic templates (Railway filesystem)
- Stores platform assets and configurations
- No Google Drive (uses Railway storage)

### Separation of Concerns

**Important**: Users can have multiple roles. The restrictions below apply to the **role**, not the person.

- **SysAdmin role**: Platform management (tenants, roles, generic templates) in myAdmin tenant
- **Tenant_Admin role**: Tenant-specific management (users, credentials, templates) in assigned tenant(s)
- **User roles**: Access to assigned tenant features based on roles

**Multi-Role Example**:

- User: peter@example.com
- Roles: SysAdmin, Tenant_Admin (GoodwinSolutions), Tenant_Admin (PeterPrive)
- Can switch between tenants:
  - myAdmin → SysAdmin role → Platform management
  - GoodwinSolutions → Tenant_Admin role → Full tenant access
  - PeterPrive → Tenant_Admin role → Full tenant access

---

## 🎭 Multi-Role Users (Important!)

**Key Concept**: Users can have multiple roles. The access restrictions apply to the **role being used**, not the person.

### How It Works

**User**: peter@example.com
**Roles**:

- SysAdmin (for myAdmin tenant)
- Tenant_Admin (for GoodwinSolutions)
- Tenant_Admin (for PeterPrive)

**When Peter switches tenants**:

| Tenant           | Active Role  | Can Do                                        | Cannot Do                      |
| ---------------- | ------------ | --------------------------------------------- | ------------------------------ |
| myAdmin          | SysAdmin     | Manage tenants, roles, generic templates      | View GoodwinSolutions invoices |
| GoodwinSolutions | Tenant_Admin | View invoices, create users, manage templates | Manage other tenants           |
| PeterPrive       | Tenant_Admin | View invoices, create users, manage templates | Manage other tenants           |

### Access Control Rules

**Rule 1**: Role-based access is determined by **current tenant**

- In myAdmin tenant → SysAdmin role active → Platform management only
- In GoodwinSolutions tenant → Tenant_Admin role active → Full tenant access

**Rule 2**: SysAdmin role restrictions apply **only in myAdmin tenant**

- SysAdmin role cannot view tenant data **when in myAdmin tenant**
- Same user can view tenant data **when in that tenant** (using Tenant_Admin role)

**Rule 3**: Users switch tenants via tenant selector

- Frontend shows available tenants based on user's roles
- Backend validates access based on current tenant + user's roles for that tenant

### Example Scenarios

**Scenario 1: Platform Management**

- Peter logs in → Selects myAdmin tenant
- SysAdmin role active
- Can create new tenant "NewCorp"
- Cannot view GoodwinSolutions invoices (wrong tenant)

**Scenario 2: Tenant Administration**

- Peter switches to GoodwinSolutions tenant
- Tenant_Admin role active
- Can view all GoodwinSolutions invoices
- Can create users for GoodwinSolutions
- Cannot create new tenants (not in myAdmin tenant)

**Scenario 3: Multi-Tenant User**

- Peter switches to PeterPrive tenant
- Tenant_Admin role active
- Can view all PeterPrive invoices
- Cannot view GoodwinSolutions invoices (different tenant)

### Implementation

**Frontend** (Tenant Selector):

```typescript
// User's available tenants based on their roles
const availableTenants = [
  { name: "myAdmin", role: "SysAdmin" },
  { name: "GoodwinSolutions", role: "Tenant_Admin" },
  { name: "PeterPrive", role: "Tenant_Admin" },
];

// When user switches tenant
function switchTenant(tenantName) {
  setCurrentTenant(tenantName);
  // Backend validates access based on tenant + user's roles
}
```

**Backend** (Authorization):

```python
@app.route('/api/sysadmin/tenants')
@cognito_required
def list_tenants():
    # Check if user has SysAdmin role
    if 'SysAdmin' not in user.roles:
        return {'error': 'SysAdmin role required'}, 403

    # Check if user is in myAdmin tenant
    if current_tenant != 'myAdmin':
        return {'error': 'Must be in myAdmin tenant'}, 403

    # User has SysAdmin role AND is in myAdmin tenant
    return list_all_tenants()

@app.route('/api/invoices')
@cognito_required
def list_invoices():
    # Check if user has access to current tenant
    if current_tenant not in user.tenants:
        return {'error': 'No access to this tenant'}, 403

    # User has access to this tenant
    return list_invoices_for_tenant(current_tenant)
```

---

## 🔑 Core Capabilities

### Tenant Management

- Create new tenants
- View all tenants
- Update tenant configuration
- Deactivate/reactivate tenants
- Cannot view tenant data (invoices, reports, transactions)

### Role Management (Cognito Groups)

- Create new roles (Cognito groups)
- View all roles
- Update role permissions
- Delete roles
- Define which roles are available per tenant

### Generic Template Management

- Upload generic templates to Railway filesystem
- Update generic templates
- Version control for templates
- Templates available to all tenants as fallback

**Scope for Railway Migration (Phase 3-5)**:

- Templates are Dutch only
- Basic template management
- Stored on Railway filesystem

**Future Enhancement (Phase 6 - Post-Railway)**:

- Multi-language templates (NL, EN)
- Comprehensive Starter Packages:
  - Chart of accounts (per country)
  - VAT rules (per country/year)
  - Account mapping patterns
  - Email templates (localized)
  - Default settings (per country/language)
- See: `.kiro/specs/Common/Starter-Packages/` (to be created)

### Platform Configuration

- System-wide settings
- Feature flags
- Basic platform configuration

**Note**: Advanced features (email templates, branding, full localization) are planned for Phase 6.

### Monitoring & Audit

- View system-wide audit logs
- Monitor platform health
- View usage statistics (aggregated, no tenant data)
- Error tracking

---

## 🚫 What SysAdmin CANNOT Do

**Important**: These restrictions apply to the **SysAdmin role** when accessing the myAdmin tenant. A user with multiple roles (e.g., SysAdmin + Tenant_Admin for GoodwinSolutions) can access tenant data when using their Tenant_Admin role.

**When acting as SysAdmin (in myAdmin tenant)**:

- ❌ View tenant-specific data (invoices, reports, transactions)
- ❌ Access tenant Google Drive credentials
- ❌ Create users (Tenant Admins do this)
- ❌ Assign users to tenants (Tenant Admins do this)
- ❌ View tenant templates (tenant-customized)
- ❌ Access tenant financial data

**When acting as Tenant_Admin (in their assigned tenant)**:

- ✅ Full access to their tenant's data
- ✅ Can create users for their tenant
- ✅ Can manage their tenant's templates
- ✅ Can view their tenant's financial data

**Example**:

- User: john@example.com
- Roles: SysAdmin, Tenant_Admin (GoodwinSolutions)
- When in myAdmin tenant → SysAdmin role → Platform management only
- When in GoodwinSolutions tenant → Tenant_Admin role → Full tenant access

---

## 📊 Current Status

### Implemented

- ✅ SysAdmin role exists in Cognito
- ✅ Role-based access control (RBAC) framework

### Not Implemented

- ❌ myAdmin system tenant (database + Cognito)
- ❌ SysAdmin UI/page
- ❌ Tenant management endpoints
- ❌ Role management endpoints
- ❌ Generic template management
- ❌ Platform configuration UI

---

## 🔗 Related Specifications

- **Railway Migration**: `.kiro/specs/Common/Railway migration/`
  - Overall migration plan and phases
  - Phase 3 creates myAdmin tenant
  - Phase 5 deploys to Railway

- **Tenant Admin Module**: `.kiro/specs/Common/TenantAdmin-Module/`
  - Tenant-specific administration
  - User management within tenant
  - Template customization

- **Authentication**: AWS Cognito integration
  - User pools and groups
  - Role-based access control
  - Multi-tenant authentication

---

## 🆘 Quick Reference

**Who is SysAdmin?**
→ Platform administrator with access to myAdmin tenant only

**What can SysAdmin do?**
→ Manage tenants, roles, generic templates, platform config

**What can't SysAdmin do?**
→ Access tenant data, create users, view tenant credentials

**Where is SysAdmin data stored?**
→ Railway filesystem (not Google Drive)

**When to implement?**
→ Phase 3 of Railway migration (after credentials & templates)

---

## 📝 Document Status

| Document        | Status         | Completion |
| --------------- | -------------- | ---------- |
| README.md       | ✅ Complete    | 100%       |
| requirements.md | 🔄 In Progress | 0%         |
| design.md       | ⏸️ Not Started | 0%         |
| TASKS.md        | ⏸️ Not Started | 0%         |

---

## Next Steps

1. Read `requirements.md` to understand user stories and acceptance criteria
2. Review `design.md` for technical architecture
3. Follow `TASKS.md` for implementation
4. Reference Railway migration spec for context

---

## 🚀 Future Enhancements (Phase 6 - Post-Railway)

After successful Railway deployment, the following enhancements are planned:

### 1. Starter Packages System

**Specification**: `.kiro/specs/Common/Starter-Packages/` (to be created)

**Features**:

- Comprehensive tenant onboarding packages
- Chart of accounts (per country: NL, UK, etc.)
- VAT rules (per country/year)
- Account mapping patterns (transaction categorization)
- Email templates (localized: NL, EN)
- Default settings (per country/language)
- Sample data (optional, for training)

**Benefits**:

- New tenants can start immediately
- Country-specific configurations
- Best practices built-in
- Faster onboarding

### 2. Internationalization (i18n)

**Specification**: `.kiro/specs/Common/Internationalization/` (to be created)

**Features**:

- Multi-language UI (NL, EN initially)
- Language selector
- Localized date/number formats
- Currency support
- Translated UI strings (react-i18next)

**Benefits**:

- Support international tenants
- Professional localization
- Scalable to more languages

### 3. Generic Filter Framework

**Specification**: `.kiro/specs/Common/Filters a generic approach/` (exists)

**Features**:

- Unified filter component architecture
- Consistent filter behavior across all reports
- Reusable filter components
- Better maintainability

**Benefits**:

- Consistent user experience
- Easier to maintain
- Faster development of new reports

### 4. Advanced Platform Features

**Email Template Management**:

- Visual email template editor
- Template preview with sample data
- Multi-language email templates

**Platform Branding**:

- Custom logo upload
- Color scheme configuration
- White-label options

**Advanced Monitoring**:

- Real-time platform health dashboard
- Performance metrics
- Usage analytics
- Cost tracking

---

## 📅 Implementation Roadmap

| Phase     | Focus                       | Timeline     |
| --------- | --------------------------- | ------------ |
| Phase 3-5 | Railway Migration           | Current      |
| Phase 6.1 | Starter Packages            | Post-Railway |
| Phase 6.2 | Internationalization (i18n) | Post-Railway |
| Phase 6.3 | Generic Filter Framework    | Post-Railway |
| Phase 6.4 | Advanced Platform Features  | Post-Railway |

**Priority**: Get to Railway first, then enhance!

---

## 📝 Related Specifications

- **Railway Migration**: `.kiro/specs/Common/Railway migration/` (current focus)
- **Tenant Admin Module**: `.kiro/specs/Common/TenantAdmin-Module/` (Phase 4)
- **Generic Filters**: `.kiro/specs/Common/Filters a generic approach/` (Phase 6.3)
- **Starter Packages**: `.kiro/specs/Common/Starter-Packages/` (Phase 6.1 - to be created)
- **Internationalization**: `.kiro/specs/Common/Internationalization/` (Phase 6.2 - to be created)
