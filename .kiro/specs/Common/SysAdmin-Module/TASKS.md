# SysAdmin Module - Implementation Tasks

**Status**: Not Started
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## Overview

This document contains detailed implementation tasks for the SysAdmin Module. Tasks are organized by component and should be completed in order.

**Estimated Time**: 7-8 days

**Phase Breakdown**:

- Phase 1: myAdmin Tenant Setup (0.5 day) ✅ Complete
- Phase 2: Backend - Tenant Management (2 days) 🔄 In Progress
- Phase 3: Backend - Role Management (1 day) 🔄 In Progress
- Phase 4: Frontend UI - Full Refactoring (2-3 days) ⏸️ Not Started
- Phase 5: Testing & Documentation (1 day) ⏸️ Not Started

**Scope Changes**:

- Removed: generic_templates table and endpoints
- Removed: tenant_role_allocation table
- Removed: platform config endpoints
- Future: Audit logging, AI usage monitoring
- **Added**: Full frontend refactoring (extract UserManagement to TenantAdmin)

---

## Prerequisites

- [x] Phase 1 of Railway migration complete (credentials infrastructure) ✅
- [x] Phase 2 of Railway migration complete (template infrastructure) ✅
- [x] AWS Cognito configured with SysAdmin role ✅
- [x] MySQL database accessible ✅

---

## Phase 1: myAdmin Tenant Setup (0.5 day)

### 1.1 Database Setup

- [x] Create myAdmin tenant in database ✅ Done
  ```sql
  INSERT INTO tenants (administration, display_name, status, contact_email, created_at)
  VALUES ('myAdmin', 'myAdmin Platform', 'active', 'admin@myadmin.com', NOW());
  ```
- [x] Verify tenant_modules table exists ✅ Already exists
- [x] Insert myAdmin modules (ADMIN) ✅ Completed 2026-02-08
  ```sql
  -- myAdmin has ADMIN module for platform management (not FIN/STR)
  INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
  VALUES ('myAdmin', 'ADMIN', TRUE, NOW());
  ```
- [x] Test table access locally ✅ Verified with check_myadmin_module.py
- [x] Document schema ✅ Schema documented in check_myadmin_module.py output

### 1.2 Cognito Setup

**Note**: Most Cognito infrastructure is already configured. See `.kiro/specs/Common/Cognito/` for details.

- [x] Verify SysAdmin group exists in Cognito ✅ Verified 2026-02-08
- [x] Verify Tenant_Admin group exists in Cognito ✅ Verified 2026-02-08
- [x] Verify custom:tenants attribute is configured (max 2048 chars) ✅ Verified 2026-02-08
- [x] Check existing test users (peter@pgeers.nl, accountant@test.com, viewer@test.com) ✅ All exist
- [x] Create SysAdmin group if not exists ✅ Already exists
- [x] Create Tenant_Admin group if not exists ✅ Already exists
- [x] Assign SysAdmin group to admin user ✅ peter@pgeers.nl has SysAdmin
- [x] Assign myAdmin tenant to admin user ✅ peter@pgeers.nl has ["myAdmin","GoodwinSolutions","PeterPrive"]
- [x] Test SysAdmin authentication ✅ Verified with test_sysadmin_auth.py
- [x] Update Cognito documentation with SysAdmin-specific configuration ✅ Verified with verify_cognito_setup.py

**Verification Results** (2026-02-08):

- ✅ 8 Cognito groups found (including SysAdmin, Tenant_Admin)
- ✅ custom:tenants attribute configured (max 2048 chars)
- ✅ 5 users found (3 test users confirmed)
- ✅ peter@pgeers.nl has SysAdmin + Tenant_Admin roles
- ✅ peter@pgeers.nl has tenants: ["myAdmin","GoodwinSolutions","PeterPrive"]
- ✅ jose.polman@gmail.com has tenants: ["GoodwinSolutions","PeterPrive"]
- ✅ SysAdmin authentication test passed

**Verification Scripts**:

- `backend/verify_cognito_setup.py` - Verify Cognito configuration
- `backend/test_sysadmin_auth.py` - Test SysAdmin authentication
- `backend/update_admin_tenant.py` - Add myAdmin tenant to SysAdmin user
- `backend/add_tenants_to_user.py` - Add tenants to any user

**Reference**: See `.kiro/specs/Common/Cognito/` for complete Cognito setup documentation

---

## Phase 2: Backend API - Tenant Management (2 days)

### 2.1 Create SysAdmin Routes Blueprint

- [x] Create `backend/src/routes/sysadmin_routes.py` ✅ Created with module endpoints
- [x] Create `backend/src/routes/sysadmin_tenants.py` ✅ Tenant endpoints separated
- [x] Create `backend/src/routes/sysadmin_roles.py` ✅ Role endpoints separated
- [x] Create `backend/src/routes/sysadmin_helpers.py` ✅ Helper functions extracted
- [x] Setup blueprint with prefix `/api/sysadmin` ✅ Done in sysadmin_routes_new.py
- [x] Import required services and decorators ✅ All imports complete
- [ ] Register blueprint in `app.py` ⚠️ **NEEDS TO BE DONE**

### 2.2 Implement Tenant Endpoints

- [x] Implement POST `/api/sysadmin/tenants` (create tenant) ✅
  - [x] Validate request data (administration, display_name, contact_email, etc.) ✅
  - [x] Create tenant in `tenants` table ✅
  - [x] Insert enabled modules into `tenant_modules` table ✅
  - [x] Add TENADMIN module automatically ✅
  - [x] Return success response ✅
- [x] Implement GET `/api/sysadmin/tenants` (list tenants) ✅
  - [x] Query all tenants from `tenants` table ✅
  - [x] Join with `tenant_modules` to get enabled_modules ✅
  - [x] Query Cognito for user_count per tenant ✅
  - [x] Add pagination support (page, per_page) ✅
  - [x] Add filtering (status, search) ✅
  - [x] Add sorting (administration, display_name, created_at, status) ✅
  - [x] Return tenant list ✅
- [x] Implement GET `/api/sysadmin/tenants/{administration}` (get tenant details) ✅
  - [x] Query tenant by administration ✅
  - [x] Get enabled modules from `tenant_modules` ✅
  - [x] Get users from Cognito (filter by custom:tenants) ✅
  - [x] Return tenant details with users and groups ✅
- [x] Implement PUT `/api/sysadmin/tenants/{administration}` (update tenant) ✅
  - [x] Validate request data ✅
  - [x] Update tenant in `tenants` table (display_name, status, contact info, address) ✅
  - [x] Cannot update `administration` field (immutable) ✅
  - [x] Set `updated_by` to current SysAdmin user email ✅
  - [x] Return success response ✅
- [x] Implement DELETE `/api/sysadmin/tenants/{administration}` (soft delete tenant) ✅
  - [x] Set status='deleted' (soft delete) ✅
  - [x] Check for active users (return 409 if users exist) ✅
  - [x] Return success response ✅

### 2.3 Authorization & Security

- [x] Use existing `@cognito_required` decorator from `auth/cognito_utils.py` ✅
- [x] Add SysAdmin group check in endpoints ✅
- [x] Log authorization failures ✅
- [ ] Test authorization checks ⚠️ **Use pytest TESTS**

### 2.4 Testing

- [ ] Write unit tests for tenant endpoints ⚠️ **TODO**
- [ ] Write integration tests for tenant workflows ⚠️ **TODO**
- [ ] Test authorization checks (SysAdmin only) ⚠️ ** Use pytest withcognito required decorator**
- [ ] Test error handling (400, 401, 403, 404, 409, 500) ⚠️
- [ ] Achieve 80 %+ code coverage ⚠️ **TODO**

---

## Phase 3: Backend API - Role Management (1 day)

### 3.1 Implement Role Endpoints

- [x] Implement GET `/api/sysadmin/roles` (list Cognito groups) ✅
  - [x] Query all Cognito groups ✅
  - [x] Get user count per group from Cognito ✅
  - [x] Categorize groups (platform, tenant, module) ✅
  - [x] Return role list with metadata ✅
- [x] Implement POST `/api/sysadmin/roles` (create Cognito group) ✅
  - [x] Validate group name (no duplicates) ✅
  - [x] Create Cognito group with description ✅
  - [x] Return success response ✅
- [x] Implement DELETE `/api/sysadmin/roles/{role_name}` (delete Cognito group) ✅
  - [x] Check group has zero users (return 409 if users exist) ✅
  - [x] Delete Cognito group ✅
  - [x] Return success response ✅

### 3.2 Module Management Endpoints

- [x] Implement GET `/api/sysadmin/tenants/{administration}/modules` (get enabled modules) ✅
  - [x] Query `tenant_modules` table ✅
  - [x] Return module list with enabled status ✅
- [x] Implement PUT `/api/sysadmin/tenants/{administration}/modules` (update modules) ✅
  - [x] Update `tenant_modules` table ✅
  - [x] Note: Does NOT remove users from module groups ✅
  - [x] Return success response ✅

### 3.3 Testing

- [x] Write unit tests for role endpoints ✅ Created in test_sysadmin_routes.py
- [x] Write integration tests for role workflows ✅ Created in test_sysadmin_routes.py
- [x] Write tests for module management ✅ Created in test_sysadmin_routes.py
- [x] Write tests for error handling (400, 401, 403, 404, 409) ✅ Created in test_sysadmin_routes.py
- [ ] Fix authentication mocking in tests ⚠️ **BLOCKED - Tests fail with 401**
- [ ] Run tests successfully ⚠️ **BLOCKED - Needs auth mocking fix**

**Test Status**: 12 tests created but failing due to `cognito_required` decorator not being properly mocked.
The decorator is checking for Authorization headers before our mocks can intercept.

**Options to proceed**:

1. Fix the mocking pattern (requires investigation)
2. Test manually with real JWT tokens via Postman
3. Test via frontend integration (Phase 4)
4. Skip automated tests for now, rely on manual testing

---

## Phase 4: Frontend UI - SysAdmin Dashboard (2-3 days)

**Approach**: Full refactoring with component extraction (Option 1)

**Note**: Existing `SystemAdmin.tsx` (837 lines) needs refactoring. See `FRONTEND_REFACTORING_PLAN.md` for complete details.

**Architecture Decision**:

- **SysAdmin Module**: Platform-level management (Tenant CRUD, Role Management, Module Management)
- **TenantAdmin Module**: Tenant-level management (User Management extracted from SystemAdmin.tsx)

### 4.0 Analysis & Planning ✅ COMPLETE

- [x] Analyze existing SystemAdmin.tsx component ✅ 837 lines, has User & Role Management
- [x] Identify what needs to move to TenantAdmin ✅ User Management (tenant-scoped)
- [x] Identify what stays in SysAdmin ✅ Role Management (needs API update)
- [x] Create refactoring plan ✅ FRONTEND_REFACTORING_PLAN.md

**Key Findings**:

- Existing SystemAdmin.tsx uses `/api/admin/*` endpoints
- User Management should move to TenantAdmin module (different spec)
- Role Management stays but needs to use `/api/sysadmin/roles`
- Need to add: Tenant Management, Module Management

---

### 4.1 Extract UserManagement to TenantAdmin (3-4 hours)

**Goal**: Move user management from SystemAdmin to TenantAdmin module

**Prerequisites**:

- [x] Backend `/api/tenant-admin/users` endpoints created ✅ **COMPLETE** (2026-02-08)
- [x] Backend `/api/tenant-admin/roles` endpoint created ✅ **COMPLETE** (2026-02-08)

**Tasks**:

- [x] Create `frontend/src/components/TenantAdmin/` directory ✅
- [x] Create `TenantAdminDashboard.tsx` (~180 lines) ✅
  - [x] Main container with tabs ✅
  - [x] Authorization check (Tenant_Admin group) ✅
  - [x] Uses existing TenantSelector from header (no duplicate) ✅
  - [x] Shows "Managing: [tenant]" indicator ✅
  - [x] Tabs: User Management, Template Management, Settings, Credentials ✅
- [x] Extract `UserManagement.tsx` from SystemAdmin.tsx (~550 lines) ✅
  - [x] Copy user list table from SystemAdmin.tsx ✅
  - [x] Copy user create/edit forms ✅
  - [x] Copy user delete functionality ✅
  - [x] Update API calls to `/api/tenant-admin/users` ✅
  - [x] Add tenant context (filter by current tenant) ✅
  - [x] Filter available roles by tenant's enabled modules ✅
  - [x] Smart user creation (add existing users to tenant) ✅
  - [x] Handle 409 status (user already in tenant) ✅
- [x] Update routing ✅
  - [x] Add route `/tenant-admin` in React Router ✅ (Already configured in App.tsx)
  - [x] Add sub-route `/tenant-admin/users` ✅ (Handled by tabs in dashboard)
  - [x] Add navigation menu item (visible to Tenant_Admin group) ✅ (Already in menu)
- [x] Fix Docker backend startup ✅ **COMPLETE** (2026-02-09)
  - [x] Updated validate_env.py to skip validation in Docker ✅
  - [x] Backend container now starts successfully ✅
- [x] Test user management in TenantAdmin context ✅ **COMPLETE** (2026-02-09)
  - [x] Test with single tenant user ✅
  - [x] Test with multi-tenant user ✅
  - [x] Test smart user creation (existing users) ✅
  - [x] Test role assignment (filtered by modules) ✅
  - [x] Test authorization (Tenant_Admin only) ✅

**Estimated Time**: 3-4 hours

---

### 4.2 Refactor SysAdmin Structure (4-5 hours)

**Goal**: Update SystemAdmin to focus on platform-level management

**Tasks**:

- [x] Backup existing component ✅
  - [x] Rename `SystemAdmin.tsx` to `SystemAdmin.old.tsx` ✅
  - [x] Keep as reference during refactoring ✅
- [x] Create new directory structure ✅
  - [x] Create `frontend/src/components/SysAdmin/` directory ✅
  - [x] Create `frontend/src/services/sysadminService.ts` for API calls ✅
- [x] Create `SysAdminDashboard.tsx` (~100 lines) ✅
  - [x] Authorization check (SysAdmin group only) ✅
  - [x] Error boundary ✅
  - [x] Loading states ✅
  - [x] Shows RoleManagement directly (no tabs until Tenant Management added) ✅
- [x] Extract and update `RoleManagement.tsx` (~400 lines) ✅
  - [x] Extract role management code from SystemAdmin.old.tsx ✅
  - [x] Update API calls to use `/api/sysadmin/roles` ✅
  - [x] Update data structure to match new API response ✅
  - [x] Keep existing UI (role list, create, delete) ✅
  - [x] Add role categorization (platform, module, other) ✅
  - [x] Disable delete for SysAdmin and Tenant_Admin roles ✅
- [x] Update routing ✅
  - [x] Update App.tsx to use SysAdminDashboard ✅
  - [x] Keep route as `/system-admin` (no change needed) ✅
  - [x] Navigation menu item already exists ✅
- [x] Test refactored structure ✅
  - [x] TypeScript compilation passes ✅
  - [x] ESLint passes (only pre-existing warnings) ✅
  - [x] No new errors introduced ✅

**Estimated Time**: 4-5 hours

---

### 4.3 Implement Tenant Management (5-6 hours)

**Goal**: Add tenant CRUD functionality to SysAdmin

**Tasks**:

- [ ] Create `TenantManagement.tsx` component (~300 lines)
  - [ ] Import Chakra UI components (Table, Modal, Form, etc.)
  - [ ] Setup state management (tenants list, loading, errors)
  - [ ] Setup pagination state (page, perPage, total)
  - [ ] Setup filter state (status, search)
  - [ ] Setup sort state (field, direction)
- [ ] Implement tenant list view
  - [ ] Create Table component with columns:
    - [ ] administration (sortable, searchable)
    - [ ] display_name (sortable, searchable)
    - [ ] status (filterable, sortable)
    - [ ] enabled_modules (badge display)
    - [ ] user_count (from API)
    - [ ] created_at (sortable, formatted)
    - [ ] actions (view, edit, delete buttons)
  - [ ] Add search input (debounced)
  - [ ] Add status filter dropdown (all, active, suspended, inactive, deleted)
  - [ ] Add sort controls (click column headers)
  - [ ] Add pagination controls (page size, prev/next)
  - [ ] Add "Create Tenant" button
  - [ ] Add loading spinner
  - [ ] Add empty state message
- [ ] Implement tenant creation modal
  - [ ] Create Modal with Form
  - [ ] Add form fields:
    - [ ] administration (text input, required, unique, lowercase)
    - [ ] display_name (text input, required)
    - [ ] contact_email (email input, required, validated)
    - [ ] phone_number (text input, optional)
    - [ ] street_address (text input, optional)
    - [ ] city (text input, optional)
    - [ ] zipcode (text input, optional)
    - [ ] country (text input, optional)
    - [ ] Module selection (checkboxes: FIN, STR)
    - [ ] initial_admin_email (email input, optional)
  - [ ] Add form validation (Formik + Yup)
  - [ ] Add submit button with loading state
  - [ ] Add cancel button
  - [ ] Handle API errors (display error messages)
  - [ ] Refresh list on success
- [ ] Implement tenant edit modal
  - [ ] Create Modal with Form (similar to create)
  - [ ] Pre-populate form with tenant data
  - [ ] Disable administration field (immutable)
  - [ ] Add status dropdown (active, suspended, inactive)
  - [ ] Add "View Modules" button (opens module management)
  - [ ] Add form validation
  - [ ] Add submit button with loading state
  - [ ] Add cancel button
  - [ ] Handle API errors
  - [ ] Refresh list on success
- [ ] Implement tenant details view
  - [ ] Create Modal or Drawer
  - [ ] Display all tenant fields (read-only)
  - [ ] Display enabled modules with badges
  - [ ] Display users list (from API)
  - [ ] Add "Edit" button (opens edit modal)
  - [ ] Add "Delete" button (opens delete confirmation)
  - [ ] Add "Manage Modules" button (opens module management)
  - [ ] Add close button
- [ ] Implement tenant deletion
  - [ ] Create confirmation dialog
  - [ ] Show warning message
  - [ ] Check for active users (API returns 409 if users exist)
  - [ ] Display error if users exist
  - [ ] Add "Confirm Delete" button
  - [ ] Add "Cancel" button
  - [ ] Handle API errors
  - [ ] Refresh list on success
- [ ] Add error handling
  - [ ] Display API errors in toast notifications
  - [ ] Handle 400 (validation errors)
  - [ ] Handle 401 (unauthorized)
  - [ ] Handle 403 (forbidden)
  - [ ] Handle 404 (not found)
  - [ ] Handle 409 (conflict - duplicate or has users)
  - [ ] Handle 500 (server error)
- [ ] Add loading states
  - [ ] Skeleton loader for table
  - [ ] Spinner for modals
  - [ ] Disabled buttons during API calls

**Estimated Time**: 5-6 hours

---

### 4.4 Implement Module Management (2-3 hours)

**Goal**: Add module enable/disable functionality per tenant

**Tasks**:

- [ ] Create `ModuleManagement.tsx` component (~150 lines)
  - [ ] Import Chakra UI components (Modal, Switch, etc.)
  - [ ] Setup state management (modules list, loading, errors)
  - [ ] Accept tenant administration as prop
- [ ] Implement module list view
  - [ ] Fetch modules from `/api/sysadmin/tenants/{administration}/modules`
  - [ ] Display module list:
    - [ ] TENADMIN (always enabled, read-only)
    - [ ] FIN (toggle switch)
    - [ ] STR (toggle switch)
  - [ ] Show module descriptions
  - [ ] Show is_active status
  - [ ] Add loading spinner
- [ ] Implement module toggle
  - [ ] Handle switch onChange
  - [ ] Update local state immediately (optimistic update)
  - [ ] Show "Save Changes" button when modified
  - [ ] Add "Reset" button to revert changes
- [ ] Implement save functionality
  - [ ] Call PUT `/api/sysadmin/tenants/{administration}/modules`
  - [ ] Send updated module list
  - [ ] Show loading state on save button
  - [ ] Display success toast
  - [ ] Handle API errors
  - [ ] Refresh module list on success
- [ ] Add warning message
  - [ ] Display warning: "Disabling a module does not remove users from module groups"
  - [ ] Add info icon with tooltip
- [ ] Add error handling
  - [ ] Display API errors in toast notifications
  - [ ] Handle validation errors
  - [ ] Handle authorization errors
- [ ] Integration with TenantManagement
  - [ ] Open ModuleManagement from tenant details view
  - [ ] Pass tenant administration as prop
  - [ ] Close modal on save
  - [ ] Refresh tenant list on close

**Estimated Time**: 2-3 hours

---

### 4.5 Integration & Polish (2-3 hours)

**Goal**: Connect all components and ensure smooth UX

**Tasks**:

- [ ] Update navigation
  - [ ] Add "System Administration" menu item
  - [ ] Show only to SysAdmin group
  - [ ] Add icon (e.g., Settings or Shield)
  - [ ] Add "Tenant Administration" menu item
  - [ ] Show only to Tenant_Admin group
  - [ ] Add icon (e.g., Users or Building)
- [ ] Update routing in `App.tsx`
  - [ ] Add route `/sysadmin` → SysAdminDashboard
  - [ ] Add route `/tenant-admin` → TenantAdminDashboard
  - [ ] Add protected route wrapper (check group membership)
  - [ ] Add redirect to home if unauthorized
- [ ] Add breadcrumbs
  - [ ] Home > System Administration > Tenants
  - [ ] Home > System Administration > Roles
  - [ ] Home > Tenant Administration > Users
- [ ] Implement API service layer
  - [ ] Create `frontend/src/services/sysadminService.ts`
  - [ ] Create functions for all SysAdmin endpoints
  - [ ] Add error handling and response parsing
  - [ ] Add TypeScript types for requests/responses
  - [ ] Create `frontend/src/services/tenantAdminService.ts`
  - [ ] Create functions for all TenantAdmin endpoints
- [ ] Add TypeScript types
  - [ ] Create `frontend/src/types/sysadmin.ts`
  - [ ] Define Tenant interface
  - [ ] Define Role interface
  - [ ] Define Module interface
  - [ ] Define API response types
- [ ] Styling and responsiveness
  - [ ] Use existing Chakra UI theme
  - [ ] Ensure responsive design (mobile, tablet, desktop)
  - [ ] Test on different screen sizes
  - [ ] Add loading skeletons
  - [ ] Add empty states
  - [ ] Add error states
- [ ] Accessibility
  - [ ] Add ARIA labels to all interactive elements
  - [ ] Add keyboard navigation (Tab, Enter, Escape)
  - [ ] Add focus indicators
  - [ ] Test with screen reader
  - [ ] Ensure color contrast meets WCAG AA
- [ ] Error handling
  - [ ] Add error boundaries
  - [ ] Add toast notifications for errors
  - [ ] Add inline error messages in forms
  - [ ] Add retry buttons for failed API calls
- [ ] Loading states
  - [ ] Add skeleton loaders for tables
  - [ ] Add spinners for modals
  - [ ] Disable buttons during API calls
  - [ ] Show progress indicators

**Estimated Time**: 2-3 hours

---

### 4.6 Testing (2-3 hours)

**Goal**: Ensure all functionality works correctly

**Tasks**:

- [ ] Manual testing - SysAdmin workflows
  - [ ] Test tenant creation (valid data)
  - [ ] Test tenant creation (invalid data - validation errors)
  - [ ] Test tenant creation (duplicate administration - 409 error)
  - [ ] Test tenant list (pagination, search, filter, sort)
  - [ ] Test tenant details view
  - [ ] Test tenant edit (update fields)
  - [ ] Test tenant edit (change status)
  - [ ] Test tenant deletion (no users)
  - [ ] Test tenant deletion (has users - 409 error)
  - [ ] Test module management (enable/disable)
  - [ ] Test role creation (valid data)
  - [ ] Test role creation (duplicate name - 409 error)
  - [ ] Test role list (search, categorization)
  - [ ] Test role deletion (no users)
  - [ ] Test role deletion (has users - 409 error)
- [ ] Manual testing - TenantAdmin workflows
  - [ ] Test user creation (valid data)
  - [ ] Test user creation (invalid data - validation errors)
  - [ ] Test user list (search, filter, sort)
  - [ ] Test user edit (update fields)
  - [ ] Test user edit (assign roles - filtered by modules)
  - [ ] Test user deletion
  - [ ] Test tenant selector (multi-tenant user)
  - [ ] Test tenant isolation (cannot see other tenants' users)
- [ ] Manual testing - Authorization
  - [ ] Test SysAdmin access (should see System Administration)
  - [ ] Test Tenant_Admin access (should see Tenant Administration)
  - [ ] Test regular user access (should not see either)
  - [ ] Test unauthorized access (redirect to home)
- [ ] Manual testing - Error handling
  - [ ] Test network errors (disconnect network)
  - [ ] Test 401 errors (expired token)
  - [ ] Test 403 errors (insufficient permissions)
  - [ ] Test 404 errors (tenant not found)
  - [ ] Test 409 errors (conflicts)
  - [ ] Test 500 errors (server errors)
- [ ] Manual testing - UI/UX
  - [ ] Test responsive design (mobile, tablet, desktop)
  - [ ] Test keyboard navigation
  - [ ] Test screen reader compatibility
  - [ ] Test loading states
  - [ ] Test empty states
  - [ ] Test error states
- [ ] Browser compatibility testing
  - [ ] Test on Chrome
  - [ ] Test on Firefox
  - [ ] Test on Safari
  - [ ] Test on Edge
- [ ] Automated testing (optional)
  - [ ] Write unit tests for components
  - [ ] Write integration tests for workflows
  - [ ] Write E2E tests with Playwright
- [ ] Performance testing
  - [ ] Test with large tenant list (100+ tenants)
  - [ ] Test with large user list (100+ users)
  - [ ] Test pagination performance
  - [ ] Test search performance
- [ ] Document test results
  - [ ] Create test report
  - [ ] Document any issues found
  - [ ] Document workarounds or fixes

**Estimated Time**: 2-3 hours

---

## Phase 5: Testing & Documentation (1 day)

### 5.1 End-to-End Testing

- [ ] Test complete tenant creation workflow
- [ ] Test complete role management workflow
- [ ] Test module management workflow
- [ ] Test authorization (SysAdmin group only)
- [ ] Test data isolation (SysAdmin cannot access tenant business data)

### 5.2 Documentation

- [ ] Update API documentation (OpenAPI/Swagger)
- [ ] Create user guide for SysAdmin
- [ ] Document Cognito group management
- [ ] Update README with SysAdmin module info

### 5.3 Code Review

- [ ] Review all code for quality
- [ ] Review all tests for coverage
- [ ] Review all documentation for completeness
- [ ] Address any issues

---

## Progress Tracking

| Phase                                | Status         | Start Date | End Date   | Notes                                               |
| ------------------------------------ | -------------- | ---------- | ---------- | --------------------------------------------------- |
| Phase 1: myAdmin Tenant Setup        | ✅ Completed   | 2026-02-05 | 2026-02-08 | ADMIN + TENADMIN modules added                      |
| Phase 2: Backend - Tenant Management | 🔄 In Progress | 2026-02-08 | -          | Code complete, needs blueprint registration & tests |
| Phase 3: Backend - Role Management   | 🔄 In Progress | 2026-02-08 | -          | Code complete, needs blueprint registration & tests |
| Phase 4.0: Analysis & Planning       | ✅ Completed   | 2026-02-08 | 2026-02-08 | Refactoring plan created                            |
| Phase 4.1: Extract UserManagement    | ✅ Completed   | 2026-02-08 | 2026-02-09 | Backend + Frontend complete, Docker fixed, tested   |
| Phase 4.2: Refactor SysAdmin         | ✅ Completed   | 2026-02-09 | 2026-02-09 | RoleManagement extracted, service layer created     |
| Phase 4.3: Tenant Management UI      | ⏸️ Not Started | -          | -          | -                                                   |
| Phase 4.4: Module Management UI      | ⏸️ Not Started | -          | -          | -                                                   |
| Phase 4.5: Integration & Polish      | ⏸️ Not Started | -          | -          | -                                                   |
| Phase 4.6: Testing                   | ⏸️ Not Started | -          | -          | -                                                   |
| Phase 5: Testing & Documentation     | ⏸️ Not Started | -          | -          | -                                                   |

**Legend:**

- ⏸️ Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked

---

## Notes

- **Removed from scope**: generic_templates table, tenant_role_allocation table, platform config endpoints
- **Design decisions**:
  - Use `tenant_template_config` with `administration='myAdmin'` for myAdmin templates
  - Derive available roles from `tenant_modules` + Cognito groups
  - Roles stored in Cognito, not database
  - Audit logging and AI usage monitoring marked as future enhancements
- Coordinate with Railway migration Phase 3 and Phase 5
- Test thoroughly before deploying to production
