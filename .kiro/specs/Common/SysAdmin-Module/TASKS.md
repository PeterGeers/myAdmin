# SysAdmin Module - Implementation Tasks

**Status**: Not Started
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## Overview

This document contains detailed implementation tasks for the SysAdmin Module. Tasks are organized by component and should be completed in order.

**Estimated Time**: 5.5 days

**Scope Changes**:

- Removed: generic_templates table and endpoints
- Removed: tenant_role_allocation table
- Removed: platform config endpoints
- Future: Audit logging, AI usage monitoring

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

- [ ] Verify SysAdmin group exists in Cognito (check if created)
- [ ] Verify Tenant_Admin group exists in Cognito (check if created)
- [ ] Verify custom:tenants attribute is configured (max 2048 chars)
- [ ] Check existing test users (peter@pgeers.nl, accountant@test.com, viewer@test.com)
- [ ] Create SysAdmin group if not exists
- [ ] Create Tenant_Admin group if not exists
- [ ] Assign SysAdmin group to admin user
- [ ] Assign myAdmin tenant to admin user (custom:tenants = ["myAdmin"])
- [ ] Test SysAdmin authentication
- [ ] Update Cognito documentation with SysAdmin-specific configuration (if needed)

**Verification Commands**:

```powershell
# List all groups
aws cognito-idp list-groups --user-pool-id <USER_POOL_ID> --region eu-west-1

# Check user pool schema for custom:tenants attribute
aws cognito-idp describe-user-pool --user-pool-id <USER_POOL_ID> --region eu-west-1

# List users
aws cognito-idp list-users --user-pool-id <USER_POOL_ID> --region eu-west-1
```

**Reference**: See `.kiro/specs/Common/Cognito/` for complete Cognito setup documentation

---

## Phase 2: Backend API - Tenant Management (2 days)

### 2.1 Create SysAdmin Routes Blueprint

- [ ] Create `backend/src/routes/sysadmin_routes.py`
- [ ] Setup blueprint with prefix `/api/sysadmin`
- [ ] Import required services and decorators
- [ ] Register blueprint in `app.py`

### 2.2 Implement Tenant Endpoints

- [ ] Implement POST `/api/sysadmin/tenants` (create tenant)
  - [ ] Validate request data (administration, display_name, contact_email, etc.)
  - [ ] Create tenant in `tenants` table
  - [ ] Insert enabled modules into `tenant_modules` table
  - [ ] Create initial Tenant_Admin user in Cognito (optional)
  - [ ] Send invitation email to initial admin (optional)
  - [ ] Return success response
- [ ] Implement GET `/api/sysadmin/tenants` (list tenants)
  - [ ] Query all tenants from `tenants` table
  - [ ] Join with `tenant_modules` to get enabled_modules
  - [ ] Query Cognito for user_count per tenant
  - [ ] Add pagination support (page, per_page)
  - [ ] Add filtering (status, search)
  - [ ] Add sorting (administration, display_name, created_at, status)
  - [ ] Return tenant list
- [ ] Implement GET `/api/sysadmin/tenants/{administration}` (get tenant details)
  - [ ] Query tenant by administration
  - [ ] Get enabled modules from `tenant_modules`
  - [ ] Get users from Cognito (filter by custom:tenants)
  - [ ] Return tenant details with users and groups
- [ ] Implement PUT `/api/sysadmin/tenants/{administration}` (update tenant)
  - [ ] Validate request data
  - [ ] Update tenant in `tenants` table (display_name, status, contact info, address)
  - [ ] Cannot update `administration` field (immutable)
  - [ ] Set `updated_by` to current SysAdmin user email
  - [ ] Return success response
- [ ] Implement DELETE `/api/sysadmin/tenants/{administration}` (soft delete tenant)
  - [ ] Set status='deleted' (soft delete)
  - [ ] Check for active users (return 409 if users exist)
  - [ ] Return success response

### 2.3 Authorization & Security

- [ ] Use existing `@cognito_required` decorator from `auth/cognito_utils.py`
- [ ] Add SysAdmin group check in endpoints
- [ ] Log authorization failures
- [ ] Test authorization checks

### 2.4 Testing

- [ ] Write unit tests for tenant endpoints
- [ ] Write integration tests for tenant workflows
- [ ] Test authorization checks (SysAdmin only)
- [ ] Test error handling (400, 401, 403, 404, 409, 500)
- [ ] Achieve 80%+ code coverage

---

## Phase 3: Backend API - Role Management (1 day)

### 3.1 Implement Role Endpoints

- [ ] Implement GET `/api/sysadmin/roles` (list Cognito groups)
  - [ ] Query all Cognito groups
  - [ ] Get user count per group from Cognito
  - [ ] Categorize groups (platform, tenant, module)
  - [ ] Return role list with metadata
- [ ] Implement POST `/api/sysadmin/roles` (create Cognito group)
  - [ ] Validate group name (no duplicates)
  - [ ] Create Cognito group with description
  - [ ] Return success response
- [ ] Implement DELETE `/api/sysadmin/roles/{role_name}` (delete Cognito group)
  - [ ] Check group has zero users (return 409 if users exist)
  - [ ] Delete Cognito group
  - [ ] Return success response

### 3.2 Module Management Endpoints

- [ ] Implement GET `/api/sysadmin/tenants/{administration}/modules` (get enabled modules)
  - [ ] Query `tenant_modules` table
  - [ ] Return module list with enabled status
- [ ] Implement PUT `/api/sysadmin/tenants/{administration}/modules` (update modules)
  - [ ] Update `tenant_modules` table
  - [ ] Note: Does NOT remove users from module groups
  - [ ] Return success response

### 3.3 Testing

- [ ] Write unit tests for role endpoints
- [ ] Write integration tests for role workflows
- [ ] Test Cognito integration
- [ ] Test module management
- [ ] Test error handling (400, 401, 403, 404, 409)

---

## Phase 4: Frontend UI - SysAdmin Dashboard (2 days)

### 4.1 Create Component Structure

- [ ] Create `frontend/src/components/SysAdmin/` directory
- [ ] Create `SysAdminDashboard.tsx` (main container)
- [ ] Create `TenantManagement.tsx` component
- [ ] Create `RoleManagement.tsx` component
- [ ] Create `ModuleManagement.tsx` component

### 4.2 Implement Tenant Management UI

- [ ] Create tenant list view
  - [ ] Display tenant table (administration, display_name, status, enabled_modules, user_count, created_at)
  - [ ] Add pagination
  - [ ] Add filtering (status, search)
  - [ ] Add sorting (administration, display_name, created_at, status)
- [ ] Create tenant creation form
  - [ ] Input: administration (unique identifier)
  - [ ] Input: display_name
  - [ ] Input: contact_email, phone_number
  - [ ] Input: address fields (street, city, zipcode, country)
  - [ ] Module selection checkboxes (FIN, STR)
  - [ ] Input: initial_admin_email (optional)
  - [ ] Submit button
- [ ] Create tenant edit form
  - [ ] Update display_name, contact info, address
  - [ ] Update status (active, suspended, inactive)
  - [ ] Cannot update administration (immutable)
  - [ ] Save button
- [ ] Create tenant details view
  - [ ] Show all tenant fields
  - [ ] Show enabled modules
  - [ ] Show users with their groups
  - [ ] Edit and delete buttons
- [ ] Add error handling and loading states

### 4.3 Implement Role Management UI

- [ ] Create role list view
  - [ ] Display role table (name, description, user_count, category)
  - [ ] Add search/filter
  - [ ] Group by category (platform, tenant, module)
- [ ] Create role creation form
  - [ ] Input: name (group name)
  - [ ] Input: description
  - [ ] Select: category (platform, tenant, module)
  - [ ] Select: module (if category=module)
  - [ ] Submit button
- [ ] Create role deletion
  - [ ] Delete button
  - [ ] Confirmation dialog
  - [ ] Show error if group has users
- [ ] Add error handling and loading states

### 4.4 Implement Module Management UI

- [ ] Create module management view (per tenant)
  - [ ] Display enabled modules (FIN, STR)
  - [ ] Toggle switches to enable/disable
  - [ ] Save button
  - [ ] Warning: Disabling module doesn't remove users from groups
- [ ] Add error handling and loading states

### 4.5 Navigation & Routing

- [ ] Add SysAdmin menu item (visible to SysAdmin group only)
- [ ] Add route `/sysadmin` in React Router
- [ ] Add sub-routes: `/sysadmin/tenants`, `/sysadmin/roles`
- [ ] Add breadcrumbs
- [ ] Add back navigation

### 4.6 Styling

- [ ] Use existing Chakra UI theme
- [ ] Ensure responsive design
- [ ] Add accessibility (ARIA labels, keyboard navigation)
- [ ] Test on multiple browsers

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

| Phase                                | Status         | Start Date | End Date | Notes             |
| ------------------------------------ | -------------- | ---------- | -------- | ----------------- |
| Phase 1: myAdmin Tenant Setup        | 🔄 In Progress | 2026-02-05 | -        | Tenant created ✅ |
| Phase 2: Backend - Tenant Management | ⏸️ Not Started | -          | -        | -                 |
| Phase 3: Backend - Role Management   | ⏸️ Not Started | -          | -        | -                 |
| Phase 4: Frontend UI                 | ⏸️ Not Started | -          | -        | -                 |
| Phase 5: Testing & Documentation     | ⏸️ Not Started | -          | -        | -                 |

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
