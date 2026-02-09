# TenantAdmin Module - Complete Architecture

**Date**: February 9, 2026
**Status**: ✅ Complete with Template Management Integration

---

## Overview

The TenantAdmin module provides tenant-level administration capabilities for users with the Tenant_Admin role. It includes **three main features**:

1. **User Management** (NEW - Phase 4.1)
2. **Template Management** (EXISTING - Already implemented)
3. **Tenant Settings & Credentials** (FUTURE - Placeholders)

---

## Architecture

### Frontend Structure

```
frontend/src/components/TenantAdmin/
├── TenantAdminDashboard.tsx          # Main container with tabs
├── UserManagement.tsx                # User CRUD (NEW)
└── TemplateManagement/               # Template management (EXISTING)
    ├── TemplateManagement.tsx        # Main template component
    ├── TemplateUpload.tsx            # Upload functionality
    ├── TemplatePreview.tsx           # Preview with sample data
    ├── ValidationResults.tsx         # Validation display
    ├── TemplateApproval.tsx          # Approve/reject workflow
    ├── AIHelpButton.tsx              # AI-powered fix suggestions
    └── __tests__/                    # Unit tests
```

### Backend Structure

```
backend/src/
├── routes/
│   └── tenant_admin_users.py        # User management endpoints (NEW)
└── tenant_admin_routes.py           # Template + config endpoints (EXISTING)
```

---

## Features by Tab

### Tab 1: User Management (NEW)

**Purpose**: Manage users within the current tenant

**Capabilities**:
- List users in tenant
- Create new users (assigned to tenant)
- Edit user name and roles
- Enable/disable users
- Delete users (tenant-aware)
- Search and filter users
- Role assignment (filtered by enabled modules)

**API Endpoints**:
```
GET    /api/tenant-admin/users
POST   /api/tenant-admin/users
PUT    /api/tenant-admin/users/{username}
DELETE /api/tenant-admin/users/{username}
POST   /api/tenant-admin/users/{username}/groups
DELETE /api/tenant-admin/users/{username}/groups/{group}
GET    /api/tenant-admin/roles
```

**Backend**: `backend/src/routes/tenant_admin_users.py`

### Tab 2: Template Management (EXISTING)

**Purpose**: Customize report templates for the tenant

**Capabilities**:
- Upload custom templates (HTML)
- Preview templates with sample data
- Validate template structure
- AI-powered fix suggestions
- Approve/reject templates
- Version management
- Field mapping configuration

**API Endpoints**:
```
GET    /api/tenant-admin/templates/<template_type>
POST   /api/tenant-admin/templates/preview
POST   /api/tenant-admin/templates/validate
POST   /api/tenant-admin/templates/approve
POST   /api/tenant-admin/templates/reject
POST   /api/tenant-admin/templates/ai-help
POST   /api/tenant-admin/templates/apply-ai-fixes
```

**Backend**: `backend/src/tenant_admin_routes.py` (lines 600+)

**Frontend**: `frontend/src/components/TenantAdmin/TemplateManagement/`

**Template Types**:
- `str_invoice_nl` - STR Invoice (Dutch)
- `str_invoice_en` - STR Invoice (English)
- `btw_aangifte` - VAT Declaration
- `aangifte_ib` - Income Tax Declaration
- `toeristenbelasting` - Tourist Tax
- `financial_report` - Financial Reports

### Tab 3: Tenant Settings (FUTURE)

**Purpose**: Configure tenant-specific settings

**Planned Features**:
- Company information
- Branding settings
- Email templates
- Notification preferences
- Integration settings

**Status**: Placeholder (disabled tab)

### Tab 4: Credentials (FUTURE)

**Purpose**: Manage tenant API credentials and secrets

**Planned Features**:
- Google Drive credentials
- Banking API credentials
- Third-party integrations
- API key management

**Status**: Placeholder (disabled tab)

---

## Integration Points

### TenantAdminDashboard.tsx

The main dashboard component that:
1. Checks Tenant_Admin authorization
2. Loads user's tenants from JWT
3. Provides tenant selector (if multi-tenant)
4. Renders tabs for each feature
5. Passes tenant context to child components

```typescript
<Tabs colorScheme="orange" variant="enclosed">
  <TabList>
    <Tab>User Management</Tab>
    <Tab>Template Management</Tab>
    <Tab isDisabled>Tenant Settings</Tab>
    <Tab isDisabled>Credentials</Tab>
  </TabList>

  <TabPanels>
    <TabPanel>
      <UserManagement tenant={selectedTenant} />
    </TabPanel>
    <TabPanel>
      <TemplateManagement />
    </TabPanel>
    <TabPanel>Coming Soon</TabPanel>
    <TabPanel>Coming Soon</TabPanel>
  </TabPanels>
</Tabs>
```

### Routing (App.tsx)

Already configured:

```typescript
case 'tenant-admin':
  return (
    <ProtectedRoute requiredRoles={['Tenant_Admin']}>
      <Box minH="100vh" bg="gray.900">
        <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
          <HStack justify="space-between">
            <VStack align="start">
              <HStack>
                <Button onClick={() => setCurrentPage('menu')}>← Back</Button>
                <Heading>🏢 Tenant Administration</Heading>
              </HStack>
              <Breadcrumb>
                <BreadcrumbItem>Dashboard</BreadcrumbItem>
                <BreadcrumbItem isCurrentPage>Tenant Administration</BreadcrumbItem>
              </Breadcrumb>
            </VStack>
            <HStack>
              <TenantSelector size="sm" />
              <UserMenu onLogout={logout} mode={status.mode} />
            </HStack>
          </HStack>
        </Box>
        <TenantAdminDashboard />
      </Box>
    </ProtectedRoute>
  );
```

### Navigation Menu

Already configured:

```typescript
{(user?.roles?.some(role => ['Tenant_Admin'].includes(role))) && (
  <Button 
    size="lg" 
    w="full" 
    colorScheme="pink" 
    onClick={() => setCurrentPage('tenant-admin')}
  >
    🏢 Tenant Administration
  </Button>
)}
```

---

## Authorization Model

### Tenant_Admin Role

**Scope**: Tenant-level (scoped to user's assigned tenants)

**Capabilities**:
- ✅ Manage users within their tenant(s)
- ✅ Customize templates for their tenant
- ✅ Configure tenant settings
- ✅ Manage tenant credentials
- ❌ Cannot create/delete tenants (SysAdmin only)
- ❌ Cannot enable/disable modules (SysAdmin only)
- ❌ Cannot create/delete Cognito groups (SysAdmin only)
- ❌ Cannot access other tenants' data

**Tenant Context**:
- Extracted from JWT `custom:tenants` attribute
- Passed via `X-Tenant` header in API calls
- Enforced by backend authorization checks

---

## Data Flow

### User Management Flow

```
User Action (Frontend)
    ↓
TenantAdminDashboard (checks auth, gets tenants)
    ↓
UserManagement Component (tenant prop)
    ↓
API Call with X-Tenant header
    ↓
Backend: tenant_admin_users.py
    ↓
Authorization Check (Tenant_Admin + tenant access)
    ↓
Cognito API (user operations)
    ↓
Response to Frontend
    ↓
Update UI + Toast Notification
```

### Template Management Flow

```
User Action (Frontend)
    ↓
TenantAdminDashboard
    ↓
TemplateManagement Component
    ↓
API Call with X-Tenant header
    ↓
Backend: tenant_admin_routes.py
    ↓
Authorization Check (Tenant_Admin + tenant access)
    ↓
Template Service (validation, preview, storage)
    ↓
Google Drive (template storage)
    ↓
Database (metadata storage)
    ↓
Response to Frontend
    ↓
Update UI + Preview Display
```

---

## Comparison: TenantAdmin vs SysAdmin

| Feature | TenantAdmin | SysAdmin |
|---------|-------------|----------|
| **Scope** | Tenant-level | Platform-level |
| **Authorization** | Tenant_Admin role | SysAdmin role |
| **User Management** | Users in assigned tenants | All users (platform-wide) |
| **Tenant Management** | ❌ Cannot manage tenants | ✅ Create/edit/delete tenants |
| **Module Management** | ❌ Cannot enable/disable | ✅ Enable/disable per tenant |
| **Role Management** | ❌ Cannot create groups | ✅ Create/delete Cognito groups |
| **Template Management** | ✅ Customize for tenant | ❌ Not applicable |
| **Tenant Settings** | ✅ Configure tenant | ❌ Not applicable |
| **Credentials** | ✅ Manage tenant secrets | ❌ Not applicable |
| **Multi-Tenant** | ✅ Can manage multiple | ✅ Can see all |

---

## Implementation Status

### Completed ✅

- [x] TenantAdminDashboard component
- [x] User Management (NEW)
- [x] Template Management (EXISTING - integrated)
- [x] Routing and navigation
- [x] Authorization checks
- [x] Multi-tenant support
- [x] Backend endpoints (users + templates)
- [x] TypeScript compilation
- [x] ESLint checks
- [x] Production build

### Future Enhancements 🔮

- [ ] Tenant Settings tab
- [ ] Credentials Management tab
- [ ] User import/export (CSV)
- [ ] Bulk user operations
- [ ] User activity logs
- [ ] Template version history UI
- [ ] Template rollback functionality
- [ ] Advanced template editor

---

## Testing Status

### Static Analysis ✅

- TypeScript: ✅ PASS
- ESLint: ✅ PASS
- Build: ✅ PASS

### Manual Testing (Ready)

- [ ] User Management CRUD
- [ ] Template Management workflow
- [ ] Multi-tenant switching
- [ ] Authorization checks
- [ ] Error handling

---

## File Sizes

| File | Lines | Status |
|------|-------|--------|
| TenantAdminDashboard.tsx | ~190 | ✅ Under 500 |
| UserManagement.tsx | ~550 | ✅ Under 1000 |
| TemplateManagement.tsx | ~400 | ✅ Under 500 |
| tenant_admin_users.py | ~700 | ✅ Under 1000 |
| tenant_admin_routes.py | ~1294 | ⚠️ Over 1000 (existing) |

**Note**: `tenant_admin_routes.py` is over 1000 lines but was already existing. It could be refactored in the future to split template routes into a separate file.

---

## Summary

The TenantAdmin module is **complete and functional** with:

1. ✅ **User Management** - NEW implementation (Phase 4.1)
2. ✅ **Template Management** - EXISTING implementation (already working)
3. 🔮 **Tenant Settings** - FUTURE (placeholder)
4. 🔮 **Credentials** - FUTURE (placeholder)

**Template management was NOT lost** - it was already implemented and has now been integrated into the new TenantAdminDashboard alongside the new User Management feature.

---

## References

- **Dashboard**: `frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`
- **User Management**: `frontend/src/components/TenantAdmin/UserManagement.tsx`
- **Template Management**: `frontend/src/components/TenantAdmin/TemplateManagement/`
- **Backend Users**: `backend/src/routes/tenant_admin_users.py`
- **Backend Templates**: `backend/src/tenant_admin_routes.py`
- **Routing**: `frontend/src/App.tsx` (line ~248)
- **Spec**: `.kiro/specs/Common/template-preview-validation/` (template management spec)

