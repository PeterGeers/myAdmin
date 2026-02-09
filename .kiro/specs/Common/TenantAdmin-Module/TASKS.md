# Tenant Admin Module - Implementation Tasks

**Status**: Ready for Implementation
**Created**: February 8, 2026
**Estimated Time**: 4-5 days

---

## Overview

This document breaks down the implementation of missing Tenant Admin features into manageable tasks. Template Management (Phase 2.6) is already complete and serves as a reference implementation.

**What's Already Done**:

- ✅ Template Management (Phase 2.6)
- ✅ TenantAdminDashboard (navigation)
- ✅ Backend routes blueprint
- ✅ CredentialService (Phase 1)

**What Needs Implementation**:

- ❌ User Management
- ❌ Credentials Management
- ❌ Storage Configuration
- ❌ Tenant Settings

---

## Phase 4.1: Backend API Endpoints (2 days)

### 4.1.1 CognitoService Implementation

- [x] Create `backend/src/services/cognito_service.py` ✅ Complete
- [x] Implement `__init__(self)` - Initialize boto3 Cognito client ✅ Complete
- [x] Implement `create_user(email, first_name, last_name, tenant, role)` method ✅ Complete
- [x] Implement `list_users(tenant)` method ✅ Complete
- [x] Implement `assign_role(username, role)` method ✅ Complete
- [x] Implement `remove_role(username, role)` method ✅ Complete
- [x] Implement `remove_user_from_tenant(username, tenant)` method ✅ Complete
- [x] Implement `send_invitation(email, temporary_password)` method via SNS ✅ Complete
- [x] Write unit tests for CognitoService (target: 10+ tests) ✅ Complete (30 tests)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days
**Status**: ✅ Complete - All tests passing (30/30)

### 4.1.2 User Management Endpoints

- [ ] Add POST `/api/tenant-admin/users` endpoint
  - [ ] Validate request (email, name, role)
  - [ ] Call CognitoService.create_user()
  - [ ] Send invitation email
  - [ ] Return user data
- [ ] Add GET `/api/tenant-admin/users` endpoint
  - [ ] Call CognitoService.list_users()
  - [ ] Filter by current tenant
  - [ ] Implement pagination
  - [ ] Return user list
- [ ] Add PUT `/api/tenant-admin/users/<username>/roles` endpoint
  - [ ] Validate roles
  - [ ] Call CognitoService.assign_role() / remove_role()
  - [ ] Return updated user
- [ ] Add DELETE `/api/tenant-admin/users/<username>` endpoint
  - [ ] Call CognitoService.remove_user_from_tenant()
  - [ ] Log action in audit trail
  - [ ] Return success
- [ ] Write API tests for user management endpoints (target: 8+ tests)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days

**Reference**: Phase 2.6 template endpoints in `tenant_admin_routes.py`

### 4.1.3 Credentials Management Endpoints

- [ ] Add POST `/api/tenant-admin/credentials` endpoint
  - [ ] Handle multipart/form-data upload
  - [ ] Validate file types (JSON)
  - [ ] Use CredentialService to encrypt and store
  - [ ] Test connectivity
  - [ ] Return credential status
- [ ] Add GET `/api/tenant-admin/credentials` endpoint
  - [ ] Use CredentialService to get credentials
  - [ ] Return status (without decrypted values)
- [ ] Add POST `/api/tenant-admin/credentials/test` endpoint
  - [ ] Use CredentialService to get credentials
  - [ ] Test Google Drive connectivity
  - [ ] Return test results
- [ ] Add POST `/api/tenant-admin/credentials/oauth/start` endpoint
  - [ ] Generate OAuth URL
  - [ ] Store state token
  - [ ] Return auth URL
- [ ] Add POST `/api/tenant-admin/credentials/oauth/callback` endpoint
  - [ ] Validate state token
  - [ ] Exchange code for tokens
  - [ ] Use CredentialService to store tokens
  - [ ] Return success
- [ ] Write API tests for credentials endpoints (target: 6+ tests)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days

**Reference**: Phase 1 CredentialService

### 4.1.4 Storage Configuration Endpoints

- [ ] Add GET `/api/tenant-admin/storage/folders` endpoint
  - [ ] Use GoogleDriveService to list folders
  - [ ] Return folder tree
- [ ] Add PUT `/api/tenant-admin/storage/config` endpoint
  - [ ] Validate folder IDs
  - [ ] Store in database (tenants table settings column)
  - [ ] Return success
- [ ] Add POST `/api/tenant-admin/storage/test` endpoint
  - [ ] Test folder accessibility
  - [ ] Test write permissions
  - [ ] Return test results
- [ ] Add GET `/api/tenant-admin/storage/usage` endpoint
  - [ ] Calculate storage usage by type
  - [ ] Return usage statistics
- [ ] Write API tests for storage endpoints (target: 5+ tests)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

### 4.1.5 Tenant Settings Endpoints

- [ ] Create `backend/src/services/tenant_settings_service.py`
- [ ] Implement `get_settings(administration)` method
- [ ] Implement `update_settings(administration, settings)` method
- [ ] Implement `get_activity(administration, date_range)` method
- [ ] Add GET `/api/tenant-admin/settings` endpoint
- [ ] Add PUT `/api/tenant-admin/settings` endpoint
- [ ] Add GET `/api/tenant-admin/activity` endpoint
- [ ] Write unit tests for TenantSettingsService (target: 5+ tests)
- [ ] Write API tests for settings endpoints (target: 4+ tests)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

---

## Phase 4.2: Frontend Components (2 days)

### 4.2.1 API Service Layer

- [ ] Create `frontend/src/services/tenantAdminApi.ts`
- [ ] Implement user management API functions
  - [ ] `createUser(userData)`
  - [ ] `listUsers(filters)`
  - [ ] `assignRole(username, role)`
  - [ ] `removeUser(username)`
- [ ] Implement credentials management API functions
  - [ ] `uploadCredentials(files)`
  - [ ] `listCredentials()`
  - [ ] `testCredentials()`
  - [ ] `startOAuth()`
  - [ ] `handleOAuthCallback(code)`
- [ ] Implement storage configuration API functions
  - [ ] `browseFolders()`
  - [ ] `updateStorageConfig(config)`
  - [ ] `testFolder(folderId)`
  - [ ] `getStorageUsage()`
- [ ] Implement tenant settings API functions
  - [ ] `getSettings()`
  - [ ] `updateSettings(settings)`
  - [ ] `getActivity(dateRange)`
- [ ] Add TypeScript types for all requests/responses
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

**Reference**: `frontend/src/services/templateApi.ts` from Phase 2.6

### 4.2.2 UserManagement Component

- [ ] Create `frontend/src/components/TenantAdmin/UserManagement/` directory
- [ ] Create `UserManagement.tsx` (main container)
  - [ ] Setup state management
  - [ ] Implement `handleCreateUser()` function
  - [ ] Implement `handleAssignRole()` function
  - [ ] Implement `handleRemoveUser()` function
  - [ ] Implement `handleResendInvitation()` function
- [ ] Create `UserList.tsx` component
  - [ ] Display user table
  - [ ] Implement sorting and filtering
  - [ ] Implement pagination
- [ ] Create `UserCreateForm.tsx` component
  - [ ] Email input with validation
  - [ ] Name inputs
  - [ ] Role selector
  - [ ] Submit button with loading state
- [ ] Create `UserRoleEditor.tsx` component
  - [ ] Display current roles
  - [ ] Add/remove role buttons
  - [ ] Confirmation dialogs
- [ ] Add routing to TenantAdminDashboard
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days

**Reference**: Phase 2.6 TemplateManagement component structure

### 4.2.3 CredentialsManagement Component

- [ ] Create `frontend/src/components/TenantAdmin/CredentialsManagement/` directory
- [ ] Create `CredentialsManagement.tsx` (main container)
  - [ ] Setup state management
  - [ ] Implement `handleUploadCredentials()` function
  - [ ] Implement `handleTestConnection()` function
  - [ ] Implement `handleOAuthStart()` function
- [ ] Create `CredentialUpload.tsx` component
  - [ ] File input for credentials.json
  - [ ] File input for token.json
  - [ ] Upload button with progress
  - [ ] File validation
- [ ] Create `CredentialStatus.tsx` component
  - [ ] Display credential status
  - [ ] Display last tested timestamp
  - [ ] Display test results
- [ ] Create `CredentialTest.tsx` component
  - [ ] Test button
  - [ ] Test results display
  - [ ] Error messages
- [ ] Create `OAuthFlow.tsx` component
  - [ ] "Connect Google Drive" button
  - [ ] OAuth redirect handling
  - [ ] Success/error display
- [ ] Add routing to TenantAdminDashboard
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days

### 4.2.4 StorageConfiguration Component

- [ ] Create `frontend/src/components/TenantAdmin/StorageConfiguration/` directory
- [ ] Create `StorageConfiguration.tsx` (main container)
  - [ ] Setup state management
  - [ ] Implement `handleBrowseFolders()` function
  - [ ] Implement `handleSelectFolder()` function
  - [ ] Implement `handleTestFolder()` function
  - [ ] Implement `handleSaveConfig()` function
- [ ] Create `FolderBrowser.tsx` component
  - [ ] Display folder tree
  - [ ] Implement folder navigation
  - [ ] Implement folder selection
- [ ] Create `FolderConfig.tsx` component
  - [ ] Folder ID inputs for each type
  - [ ] Browse buttons
  - [ ] Test buttons
  - [ ] Save button
- [ ] Create `StorageUsage.tsx` component
  - [ ] Display total usage
  - [ ] Display usage by type (chart)
  - [ ] Display quota information
- [ ] Add routing to TenantAdminDashboard
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days

### 4.2.5 TenantSettings Component

- [ ] Create `frontend/src/components/TenantAdmin/TenantSettings/` directory
- [ ] Create `TenantSettings.tsx` (main container)
  - [ ] Setup state management with tabs
  - [ ] Implement `handleUpdateSettings()` function
  - [ ] Implement `handleTestNotification()` function
  - [ ] Implement `handleToggleFeature()` function
- [ ] Create `GeneralSettings.tsx` component
  - [ ] Tenant name input
  - [ ] Contact email input
  - [ ] Phone input
  - [ ] Address input
- [ ] Create `NotificationSettings.tsx` component
  - [ ] Enable/disable toggle
  - [ ] Frequency selector
  - [ ] Type checkboxes
  - [ ] Recipients list
  - [ ] Test notification button
- [ ] Create `FeatureToggles.tsx` component
  - [ ] Feature list with toggles
  - [ ] Feature descriptions
  - [ ] Confirmation for disabling
- [ ] Create `ActivityDashboard.tsx` component
  - [ ] Display activity metrics
  - [ ] Display charts (Recharts)
  - [ ] Date range selector
  - [ ] Export button
- [ ] Add routing to TenantAdminDashboard
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

---

## Phase 4.3: User Invitation System (1 day)

### 4.3.1 Email Templates

- [ ] Create invitation email template (HTML)
- [ ] Create invitation email template (plain text)
- [ ] Include temporary password
- [ ] Include login link
- [ ] Include instructions
- [ ] Test email rendering
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

### 4.3.2 SNS Integration

- [ ] Configure SNS topic for invitations
- [ ] Add SNS_INVITATION_TOPIC_ARN to environment
- [ ] Implement `send_invitation_email()` function
- [ ] Test email delivery
- [ ] Handle SNS errors gracefully
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

### 4.3.3 Invitation Flow

- [ ] Implement temporary password generation
- [ ] Implement invitation status tracking
- [ ] Implement resend invitation functionality
- [ ] Add invitation expiry (7 days)
- [ ] Test complete invitation flow
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.5 days

---

## Phase 4.4: Access Control (0.5 days)

### 4.4.1 Verify Tenant Isolation

- [ ] Test Tenant Admin can only see their tenant's users
- [ ] Test Tenant Admin cannot access other tenant's credentials
- [ ] Test Tenant Admin cannot access other tenant's storage
- [ ] Test Tenant Admin cannot access other tenant's settings
- [ ] Verify `@tenant_required()` decorator works correctly
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

**Reference**: Phase 3.3 test results

### 4.4.2 Test Role Checks

- [ ] Test only Tenant_Admin role can access endpoints
- [ ] Test other roles (Finance_CRUD, STR_CRUD) are denied
- [ ] Test SysAdmin role alone is denied (no tenant access)
- [ ] Test combined roles (TenantAdmin + SysAdmin) work correctly
- [ ] Verify `@cognito_required()` decorator works correctly
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

**Reference**: Phase 3.2 test results

---

## Phase 4.5: Testing (1 day)

### 4.5.1 Backend Unit Tests

- [ ] Test CognitoService methods (10+ tests)
- [ ] Test TenantSettingsService methods (5+ tests)
- [ ] Test user management endpoints (8+ tests)
- [ ] Test credentials endpoints (6+ tests)
- [ ] Test storage endpoints (5+ tests)
- [ ] Test settings endpoints (4+ tests)
- [ ] Achieve 80%+ code coverage
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

**Target**: 38+ tests total

### 4.5.2 Backend Integration Tests

- [ ] Test create user → assign role → verify access flow
- [ ] Test upload credentials → test connection → verify storage flow
- [ ] Test configure folders → test access → verify writes flow
- [ ] Test update settings → verify applied flow
- [ ] Test tenant isolation (cannot access other tenant data)
- [ ] Test with real Cognito (test environment)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

**Target**: 5+ integration tests

### 4.5.3 Frontend Unit Tests

- [ ] Test UserManagement component (20+ tests)
- [ ] Test CredentialsManagement component (15+ tests)
- [ ] Test StorageConfiguration component (15+ tests)
- [ ] Test TenantSettings component (15+ tests)
- [ ] Test API service functions (15+ tests)
- [ ] Mock API calls
- [ ] Achieve 80%+ code coverage
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.25 days

**Target**: 80+ tests total

**Reference**: Phase 2.6 created 148 unit tests

### 4.5.4 Frontend Integration Tests

- [ ] Test complete user creation flow
- [ ] Test complete credential upload flow
- [ ] Test complete storage configuration flow
- [ ] Test complete settings update flow
- [ ] Test error handling
- [ ] Test loading states
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.125 days

**Target**: 5+ integration tests

**Reference**: Phase 2.6 created 11 integration tests

### 4.5.5 E2E Tests

- [ ] Test end-to-end user management workflow
- [ ] Test end-to-end credential management workflow
- [ ] Test end-to-end storage configuration workflow
- [ ] Test on different browsers (Chrome, Firefox)
- [ ] Test responsive design (mobile, tablet, desktop)
- [ ] Check if tsc and lint pass correctly and minimize warnings
- [ ] add to github using scripts\git\git-upload.ps1

**Time Estimate**: 0.125 days

**Target**: 3+ E2E tests

**Tool**: Playwright (already configured)

---

## Progress Tracking

| Phase                        | Status         | Duration | Start Date | End Date | Notes |
| ---------------------------- | -------------- | -------- | ---------- | -------- | ----- |
| Phase 4.1: Backend API       | ⏸️ Not Started | 2 days   | -          | -        | -     |
| Phase 4.2: Frontend          | ⏸️ Not Started | 2 days   | -          | -        | -     |
| Phase 4.3: Invitation System | ⏸️ Not Started | 1 day    | -          | -        | -     |
| Phase 4.4: Access Control    | ⏸️ Not Started | 0.5 days | -          | -        | -     |
| Phase 4.5: Testing           | ⏸️ Not Started | 1 day    | -          | -        | -     |

**Legend**:

- ⏸️ Not Started
- 🔄 In Progress
- ✅ Completed
- ⚠️ Blocked

---

## Notes

- Each phase should be completed and tested before moving to the next
- Reference Phase 2.6 template management for implementation patterns
- Reuse CredentialService from Phase 1
- Follow Phase 3 role separation and tenant isolation patterns
- Update this file as tasks are completed
- Git uploads after each major section

---

## Summary

**Total Tasks**: ~120 tasks
**Total Time**: 4-5 days
**Test Coverage Target**: 80%+
**Total Tests Target**: 130+ tests (38 backend unit, 5 backend integration, 80 frontend unit, 5 frontend integration, 3 E2E)

**Reference Implementations**:

- Phase 2.6 Template Management (component structure, testing)
- Phase 1 Credentials Infrastructure (CredentialService)
- Phase 3 Role Separation (authentication, authorization)
