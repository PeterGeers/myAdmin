# SysAdmin Module - Implementation Tasks

**Status**: Not Started
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## Overview

This document contains detailed implementation tasks for the SysAdmin Module. Tasks are organized by component and should be completed in order.

**Estimated Time**: 5-7 days

---

## Prerequisites

- [ ] Phase 1 of Railway migration complete (credentials infrastructure)
- [ ] Phase 2 of Railway migration complete (template infrastructure)
- [ ] AWS Cognito configured with SysAdmin role
- [ ] MySQL database accessible

---

## Phase 1: myAdmin Tenant Setup (1 day)

### 1.1 Database Setup

- [ ] Create myAdmin tenant in database
  ```sql
  INSERT INTO tenants (administration, status, created_at) 
  VALUES ('myAdmin', 'active', NOW());
  ```
- [ ] Create tenant_modules table (see design.md)
- [ ] Create generic_templates table (see design.md)
- [ ] Create tenant_role_allocation table (see design.md)
- [ ] Test table creation locally
- [ ] Document schema changes

### 1.2 Cognito Setup

- [ ] Verify SysAdmin group exists in Cognito
- [ ] Create myAdmin tenant in Cognito (if needed)
- [ ] Assign SysAdmin users to myAdmin tenant
- [ ] Test SysAdmin authentication
- [ ] Document Cognito configuration

### 1.3 Filesystem Setup

- [ ] Create `backend/templates/generic/` directory
- [ ] Create `backend/static/platform/` directory
- [ ] Add .gitkeep files to preserve directories
- [ ] Document directory structure

---

## Phase 2: Backend API - Tenant Management (2 days)

### 2.1 Create SysAdmin Routes Blueprint

- [ ] Create `backend/src/sysadmin_routes.py`
- [ ] Setup blueprint with prefix `/api/sysadmin`
- [ ] Import required services and decorators
- [ ] Register blueprint in `app.py`

### 2.2 Implement Tenant Endpoints

- [ ] Implement POST `/api/sysadmin/tenants` (create tenant)
  - [ ] Validate request data
  - [ ] Create tenant in database
  - [ ] Create tenant in Cognito
  - [ ] Send invitation email to initial admin
  - [ ] Return success response
- [ ] Implement GET `/api/sysadmin/tenants` (list tenants)
  - [ ] Query all tenants from database
  - [ ] Add pagination support
  - [ ] Add filtering (status, search)
  - [ ] Add sorting
  - [ ] Return tenant list
- [ ] Implement GET `/api/sysadmin/tenants/:id` (get tenant details)
  - [ ] Query tenant by ID
  - [ ] Return tenant details
  - [ ] Do not include sensitive data
- [ ] Implement PUT `/api/sysadmin/tenants/:id` (update tenant)
  - [ ] Validate request data
  - [ ] Update tenant in database
  - [ ] Log action in audit trail
  - [ ] Return success response
- [ ] Implement PUT `/api/sysadmin/tenants/:id/status` (activate/deactivate)
  - [ ] Update tenant status
  - [ ] Log action in audit trail
  - [ ] Return success response

### 2.3 Authorization & Security

- [ ] Create `@require_sysadmin` decorator
- [ ] Apply decorator to all sysadmin endpoints
- [ ] Verify user has SysAdmin role
- [ ] Log authorization failures
- [ ] Test authorization checks

### 2.4 Testing

- [ ] Write unit tests for tenant endpoints
- [ ] Write integration tests for tenant workflows
- [ ] Test authorization checks
- [ ] Test error handling
- [ ] Achieve 80%+ code coverage

---

## Phase 3: Backend API - Role Management (1 day)

### 3.1 Implement Role Endpoints

- [ ] Implement POST `/api/sysadmin/roles` (create role)
  - [ ] Create Cognito group
  - [ ] Store role metadata in database
  - [ ] Return success response
- [ ] Implement GET `/api/sysadmin/roles` (list roles)
  - [ ] Query all Cognito groups
  - [ ] Return role list with metadata
- [ ] Implement PUT `/api/sysadmin/roles/:id` (update role)
  - [ ] Update Cognito group
  - [ ] Update role metadata
  - [ ] Return success response
- [ ] Implement DELETE `/api/sysadmin/roles/:id` (delete role)
  - [ ] Verify role not assigned to users
  - [ ] Delete Cognito group
  - [ ] Delete role metadata
  - [ ] Return success response

### 3.2 Tenant-Role Allocation

- [ ] Implement POST `/api/sysadmin/tenants/:id/roles` (assign role to tenant)
  - [ ] Insert into tenant_role_allocation table
  - [ ] Return success response
- [ ] Implement DELETE `/api/sysadmin/tenants/:id/roles/:role_id` (remove role from tenant)
  - [ ] Delete from tenant_role_allocation table
  - [ ] Return success response
- [ ] Implement GET `/api/sysadmin/tenants/:id/roles` (list tenant roles)
  - [ ] Query tenant_role_allocation table
  - [ ] Return role list

### 3.3 Testing

- [ ] Write unit tests for role endpoints
- [ ] Write integration tests for role workflows
- [ ] Test Cognito integration
- [ ] Test error handling

---

## Phase 4: Backend API - Generic Templates (1 day)

### 4.1 Create GenericTemplateService

- [ ] Create `backend/src/services/generic_template_service.py`
- [ ] Implement `upload_template(file, template_type, template_name)` method
- [ ] Implement `get_template(template_name, version)` method
- [ ] Implement `list_templates()` method
- [ ] Implement `get_template_versions(template_name)` method
- [ ] Write unit tests

### 4.2 Implement Template Endpoints

- [ ] Implement POST `/api/sysadmin/templates` (upload template)
  - [ ] Validate file type (HTML, XLSX)
  - [ ] Save file to Railway filesystem
  - [ ] Store metadata in database
  - [ ] Return success response
- [ ] Implement GET `/api/sysadmin/templates` (list templates)
  - [ ] Query generic_templates table
  - [ ] Return template list
- [ ] Implement GET `/api/sysadmin/templates/:id` (get template)
  - [ ] Read file from filesystem
  - [ ] Return file content
- [ ] Implement GET `/api/sysadmin/templates/:id/versions` (list versions)
  - [ ] Query template versions
  - [ ] Return version list

### 4.3 Testing

- [ ] Write unit tests for template service
- [ ] Write integration tests for template endpoints
- [ ] Test file upload and retrieval
- [ ] Test version management

---

## Phase 5: Frontend UI - SysAdmin Dashboard (2 days)

### 5.1 Create Component Structure

- [ ] Create `frontend/src/components/SysAdmin/` directory
- [ ] Create `SysAdminDashboard.tsx` (main container)
- [ ] Create `TenantManagement.tsx` component
- [ ] Create `RoleManagement.tsx` component
- [ ] Create `GenericTemplateManagement.tsx` component
- [ ] Create `PlatformConfig.tsx` component
- [ ] Create `AuditLogs.tsx` component

### 5.2 Implement Tenant Management UI

- [ ] Create tenant list view
  - [ ] Display tenant table (name, status, users, created date)
  - [ ] Add pagination
  - [ ] Add filtering (status, search)
  - [ ] Add sorting
- [ ] Create tenant creation form
  - [ ] Input: tenant name
  - [ ] Input: contact email
  - [ ] Input: initial admin email
  - [ ] Module selection checkboxes
  - [ ] Submit button
- [ ] Create tenant edit form
  - [ ] Update tenant name
  - [ ] Update contact email
  - [ ] Enable/disable modules
  - [ ] Save button
- [ ] Create tenant status toggle
  - [ ] Activate/deactivate button
  - [ ] Confirmation dialog
- [ ] Add error handling and loading states

### 5.3 Implement Role Management UI

- [ ] Create role list view
  - [ ] Display role table (name, description, users, tenants)
  - [ ] Add search/filter
- [ ] Create role creation form
  - [ ] Input: role name
  - [ ] Input: description
  - [ ] Permission checkboxes
  - [ ] Submit button
- [ ] Create role edit form
  - [ ] Update description
  - [ ] Update permissions
  - [ ] Save button
- [ ] Create role deletion
  - [ ] Delete button
  - [ ] Confirmation dialog
- [ ] Add error handling and loading states

### 5.4 Implement Generic Template Management UI

- [ ] Create template list view
  - [ ] Display template table (name, type, version, updated)
  - [ ] Add search/filter
- [ ] Create template upload form
  - [ ] File input
  - [ ] Template type selector
  - [ ] Template name input
  - [ ] Upload button
- [ ] Create template preview
  - [ ] Display template content
  - [ ] Version selector
- [ ] Add error handling and loading states

### 5.5 Navigation & Routing

- [ ] Add SysAdmin menu item (visible to SysAdmin role only)
- [ ] Add route `/sysadmin` in React Router
- [ ] Add breadcrumbs
- [ ] Add back navigation

### 5.6 Styling

- [ ] Use existing Chakra UI theme
- [ ] Ensure responsive design
- [ ] Add accessibility (ARIA labels, keyboard navigation)
- [ ] Test on multiple browsers

---

## Phase 6: Testing & Documentation (1 day)

### 6.1 End-to-End Testing

- [ ] Test complete tenant creation workflow
- [ ] Test complete role management workflow
- [ ] Test complete template upload workflow
- [ ] Test authorization (SysAdmin only)
- [ ] Test data isolation (cannot access tenant data)

### 6.2 Documentation

- [ ] Update API documentation (OpenAPI/Swagger)
- [ ] Create user guide for SysAdmin
- [ ] Document all environment variables
- [ ] Update Railway migration README

### 6.3 Code Review

- [ ] Review all code for quality
- [ ] Review all tests for coverage
- [ ] Review all documentation for completeness
- [ ] Address any issues

---

## Progress Tracking

| Phase | Status | Start Date | End Date | Notes |
|-------|--------|------------|----------|-------|
| Phase 1: myAdmin Tenant Setup | ⏸️ Not Started | - | - | - |
| Phase 2: Backend - Tenant Management | ⏸️ Not Started | - | - | - |
| Phase 3: Backend - Role Management | ⏸️ Not Started | - | - | - |
| Phase 4: Backend - Generic Templates | ⏸️ Not Started | - | - | - |
| Phase 5: Frontend UI | ⏸️ Not Started | - | - | - |
| Phase 6: Testing & Documentation | ⏸️ Not Started | - | - | - |

**Legend:**
- ⏸️ Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked

---

## Notes

- This spec focuses on core SysAdmin functionality
- Additional features (audit logs, monitoring) can be added later
- Coordinate with Railway migration Phase 3 and Phase 5
- Test thoroughly before deploying to production
