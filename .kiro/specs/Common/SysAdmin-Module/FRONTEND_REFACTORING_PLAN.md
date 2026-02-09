# SysAdmin Frontend Refactoring Plan

**Date**: February 8, 2026
**Status**: Planning

---

## Current State Analysis

### Existing SystemAdmin.tsx (837 lines)

**Location**: `frontend/src/components/SystemAdmin.tsx`

**Current Features**:
1. User Management (Lines ~1-600)
   - List users with search/filter/sort
   - Create users
   - Edit user roles and display name
   - Enable/disable users
   - Delete users
   - API: `/api/admin/users`, `/api/admin/groups`

2. Role Management (Lines ~600-837)
   - List Cognito groups
   - Show user count per group
   - Show group description and precedence
   - API: `/api/admin/groups`

**Issues**:
- ❌ User management should be per-tenant (Tenant_Admin responsibility)
- ❌ Role management uses old `/api/admin/groups` endpoint
- ❌ Missing tenant management functionality
- ❌ Missing module management functionality
- ❌ File is 837 lines (should be under 1000, but could be more modular)

---

## Target Architecture

### 1. SysAdmin Module (Platform-level)

**Purpose**: Platform administration for SysAdmin role only

**Components**:
- `SysAdminDashboard.tsx` - Main container with tabs
- `TenantManagement.tsx` - CRUD for tenants
- `RoleManagement.tsx` - Cognito group management
- `ModuleManagement.tsx` - Enable/disable modules per tenant (nested in tenant details)

**API Endpoints**:
- `/api/sysadmin/tenants` - Tenant CRUD
- `/api/sysadmin/roles` - Role (Cognito group) management
- `/api/sysadmin/tenants/{administration}/modules` - Module management

**Access**: SysAdmin group only

### 2. TenantAdmin Module (Tenant-level)

**Purpose**: Tenant administration for Tenant_Admin role

**Components**:
- `TenantAdminDashboard.tsx` - Main container
- `UserManagement.tsx` - User CRUD for current tenant
- `TenantSettings.tsx` - Tenant configuration
- `CredentialsManagement.tsx` - Tenant credentials

**API Endpoints**:
- `/api/tenant-admin/users` - User management (to be created)
- `/api/tenant-admin/settings` - Tenant settings (to be created)
- `/api/tenant-admin/credentials` - Credentials (existing)

**Access**: Tenant_Admin group, scoped to user's tenants

---

## Refactoring Steps

### Phase 1: Extract User Management to TenantAdmin

**Goal**: Move user management from SystemAdmin to TenantAdmin module

**Tasks**:
1. Create `frontend/src/components/TenantAdmin/` directory
2. Create `TenantAdminDashboard.tsx`
3. Create `UserManagement.tsx` (extract from SystemAdmin.tsx)
4. Update API calls to use tenant-scoped endpoints
5. Add tenant selector (if user has multiple tenants)
6. Test user management in TenantAdmin context

**Estimated Time**: 3-4 hours

### Phase 2: Refactor SysAdmin for Platform Management

**Goal**: Update SystemAdmin to focus on platform-level management

**Tasks**:
1. Rename `SystemAdmin.tsx` to `SysAdminDashboard.tsx`
2. Remove user management code
3. Create `components/SysAdmin/` directory
4. Create `TenantManagement.tsx` component
5. Update `RoleManagement.tsx` to use `/api/sysadmin/roles`
6. Create `ModuleManagement.tsx` component
7. Update routing and navigation

**Estimated Time**: 4-5 hours

### Phase 3: Implement New SysAdmin Features

**Goal**: Add tenant and module management

**Tasks**:
1. Implement tenant list with search/filter/sort
2. Implement tenant create form
3. Implement tenant edit form
4. Implement tenant delete with confirmation
5. Implement module management (nested in tenant details)
6. Add error handling and loading states
7. Test all CRUD operations

**Estimated Time**: 5-6 hours

---

## Detailed Component Breakdown

### SysAdminDashboard.tsx (~150 lines)

```typescript
- Main container with Tabs
- Tab 1: Tenant Management
- Tab 2: Role Management
- Authorization check (SysAdmin group)
- Navigation breadcrumbs
```

### TenantManagement.tsx (~300 lines)

```typescript
- Tenant list table
  - Columns: administration, display_name, status, modules, user_count, created_at
  - Search: administration, display_name, contact_email
  - Filter: status (active, suspended, inactive, deleted)
  - Sort: administration, display_name, created_at, status
  - Pagination
- Create tenant modal
  - Form: administration, display_name, contact_email, phone, address
  - Module selection: FIN, STR
  - Validation
- Edit tenant modal
  - Update fields (administration immutable)
  - Status change
  - Module management button
- Delete tenant
  - Confirmation dialog
  - Check for active users
```

### RoleManagement.tsx (~200 lines)

```typescript
- Role list
  - Columns: name, description, user_count, category, created_date
  - Categorization: platform, module, other
- Create role modal
  - Form: name, description
  - Validation
- Delete role
  - Confirmation dialog
  - Check for users in group
```

### ModuleManagement.tsx (~150 lines)

```typescript
- Module list for tenant
  - Toggle switches: FIN, STR, TENADMIN
  - Show is_active status
- Update modules
  - Save button
  - Warning: doesn't remove users from groups
```

### UserManagement.tsx (TenantAdmin) (~400 lines)

```typescript
- Extracted from SystemAdmin.tsx
- Scoped to current tenant
- User list with search/filter/sort
- Create/edit/delete users
- Assign roles (filtered by tenant modules)
```

---

## API Endpoint Mapping

### SysAdmin Endpoints (New)

| Component | Method | Endpoint | Purpose |
|-----------|--------|----------|---------|
| TenantManagement | POST | `/api/sysadmin/tenants` | Create tenant |
| TenantManagement | GET | `/api/sysadmin/tenants` | List tenants |
| TenantManagement | GET | `/api/sysadmin/tenants/{id}` | Get tenant |
| TenantManagement | PUT | `/api/sysadmin/tenants/{id}` | Update tenant |
| TenantManagement | DELETE | `/api/sysadmin/tenants/{id}` | Delete tenant |
| RoleManagement | GET | `/api/sysadmin/roles` | List roles |
| RoleManagement | POST | `/api/sysadmin/roles` | Create role |
| RoleManagement | DELETE | `/api/sysadmin/roles/{name}` | Delete role |
| ModuleManagement | GET | `/api/sysadmin/tenants/{id}/modules` | Get modules |
| ModuleManagement | PUT | `/api/sysadmin/tenants/{id}/modules` | Update modules |

### TenantAdmin Endpoints (To Be Created)

| Component | Method | Endpoint | Purpose |
|-----------|--------|----------|---------|
| UserManagement | GET | `/api/tenant-admin/users` | List users (tenant-scoped) |
| UserManagement | POST | `/api/tenant-admin/users` | Create user |
| UserManagement | PUT | `/api/tenant-admin/users/{id}` | Update user |
| UserManagement | DELETE | `/api/tenant-admin/users/{id}` | Delete user |
| UserManagement | GET | `/api/tenant-admin/roles` | List available roles |

**Note**: Current `/api/admin/*` endpoints will be deprecated in favor of tenant-scoped endpoints.

---

## File Structure

### Before Refactoring

```
frontend/src/components/
└── SystemAdmin.tsx (837 lines)
```

### After Refactoring

```
frontend/src/components/
├── SysAdmin/
│   ├── SysAdminDashboard.tsx (~150 lines)
│   ├── TenantManagement.tsx (~300 lines)
│   ├── RoleManagement.tsx (~200 lines)
│   └── ModuleManagement.tsx (~150 lines)
└── TenantAdmin/
    ├── TenantAdminDashboard.tsx (~100 lines)
    ├── UserManagement.tsx (~400 lines)
    ├── TenantSettings.tsx (~150 lines)
    └── CredentialsManagement.tsx (~200 lines)
```

**Total Lines**:
- SysAdmin: ~800 lines across 4 files
- TenantAdmin: ~850 lines across 4 files
- All files under 500 lines ✅

---

## Navigation Changes

### Current Navigation

```
System Administration → User & Role Management
```

### New Navigation

```
System Administration (SysAdmin only)
├── Tenant Management
└── Role Management

Tenant Administration (Tenant_Admin)
├── User Management
├── Tenant Settings
└── Credentials
```

---

## Authorization

### SysAdmin Module

- **Required Group**: `SysAdmin`
- **Tenant Access**: All tenants (platform-wide)
- **Capabilities**:
  - Create/edit/delete tenants
  - Create/delete Cognito groups
  - Enable/disable modules per tenant
  - View all users across all tenants (read-only)

### TenantAdmin Module

- **Required Group**: `Tenant_Admin`
- **Tenant Access**: User's assigned tenants only (from `custom:tenants`)
- **Capabilities**:
  - Create/edit/delete users in their tenant(s)
  - Assign roles to users (limited to tenant's enabled modules)
  - Update tenant settings
  - Manage tenant credentials

---

## Testing Strategy

### Unit Tests

- Component rendering
- Form validation
- State management
- API call mocking

### Integration Tests

- Full CRUD workflows
- Authorization checks
- Error handling
- Multi-tenant scenarios

### Manual Testing

- SysAdmin creates tenant
- SysAdmin enables modules
- SysAdmin creates roles
- Tenant_Admin creates users
- Tenant_Admin assigns roles
- User logs in and sees correct permissions

---

## Migration Path

### Step 1: Backward Compatibility

- Keep existing `/api/admin/*` endpoints working
- Add new `/api/sysadmin/*` and `/api/tenant-admin/*` endpoints
- Both UIs work simultaneously

### Step 2: Gradual Migration

- Deploy new SysAdmin UI
- Test thoroughly
- Deploy new TenantAdmin UI
- Test thoroughly

### Step 3: Deprecation

- Mark `/api/admin/*` endpoints as deprecated
- Update documentation
- Remove old endpoints after grace period

---

## Risks and Mitigation

### Risk 1: Breaking Existing Functionality

**Mitigation**:
- Keep old SystemAdmin.tsx as backup
- Deploy new components alongside old ones
- Gradual rollout with feature flags

### Risk 2: Authorization Confusion

**Mitigation**:
- Clear documentation of SysAdmin vs Tenant_Admin
- UI shows current role and tenant context
- Error messages explain permission requirements

### Risk 3: Data Inconsistency

**Mitigation**:
- Backend enforces tenant isolation
- Frontend validates tenant access
- Audit logging tracks all changes

---

## Success Criteria

- ✅ SysAdmin can manage all tenants
- ✅ SysAdmin can manage Cognito groups
- ✅ SysAdmin can enable/disable modules per tenant
- ✅ Tenant_Admin can manage users in their tenant(s)
- ✅ Tenant_Admin cannot access other tenants' data
- ✅ All components under 500 lines
- ✅ Comprehensive error handling
- ✅ Responsive design
- ✅ Accessibility compliant

---

## Timeline

| Phase | Tasks | Estimated Time | Dependencies |
|-------|-------|----------------|--------------|
| Phase 1 | Extract UserManagement to TenantAdmin | 3-4 hours | Backend tenant-admin endpoints |
| Phase 2 | Refactor SysAdmin structure | 4-5 hours | Phase 1 complete |
| Phase 3 | Implement new SysAdmin features | 5-6 hours | Backend sysadmin endpoints ✅ |
| Testing | Manual and automated testing | 2-3 hours | All phases complete |
| **Total** | | **14-18 hours** | **~2-3 days** |

---

## Next Steps

1. **Immediate**: Review this plan with stakeholders
2. **Backend**: Create `/api/tenant-admin/*` endpoints (Phase 1 dependency)
3. **Frontend**: Start Phase 1 (extract UserManagement)
4. **Testing**: Set up test environment with multiple tenants and users

---

## References

- Backend API: `backend/src/routes/sysadmin_*.py`
- Existing Component: `frontend/src/components/SystemAdmin.tsx`
- Design Spec: `.kiro/specs/Common/SysAdmin-Module/design.md`
- Requirements: `.kiro/specs/Common/SysAdmin-Module/requirements.md`
