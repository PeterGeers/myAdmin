# Tenant Admin Module - Requirements (Missing Features)

**Status**: Draft
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## 1. Overview

This specification defines requirements for the **missing features** of the Tenant Admin Module. Template Management (Phase 2.6) is already complete and serves as a reference implementation.

**Missing Features**:

1. User Management
2. Credentials Management
3. Storage Configuration
4. Tenant Settings

---

## 2. User Stories

### 2.1 User Management

**US-TA-01: Create New User**

- **As a** Tenant Administrator
- **I want to** create a new user in my tenant
- **So that** team members can access myAdmin

**Acceptance Criteria:**

- Tenant Admin can access user creation form
- Form includes: email, first name, last name, role selection
- System creates user in Cognito
- System assigns user to current tenant
- System assigns selected role to user
- System sends invitation email with temporary password
- User appears in user list
- Success confirmation displayed

**US-TA-02: View Tenant Users**

- **As a** Tenant Administrator
- **I want to** view all users in my tenant
- **So that** I can manage team access

**Acceptance Criteria:**

- Tenant Admin can see list of users in their tenant
- List shows: name, email, roles, status (active/inactive), last login
- List is sortable and filterable
- List is paginated (50 per page)
- Cannot see users from other tenants

**US-TA-03: Assign Roles to User**

- **As a** Tenant Administrator
- **I want to** assign roles to users
- **So that** users have appropriate access levels

**Acceptance Criteria:**

- Tenant Admin can select user from list
- Tenant Admin can see available roles (allocated to tenant)
- Tenant Admin can assign multiple roles to user
- Tenant Admin can remove roles from user
- Changes take effect immediately
- User receives email notification of role change
- Action is logged in audit trail

**US-TA-04: Remove User from Tenant**

- **As a** Tenant Administrator
- **I want to** remove users from my tenant
- **So that** I can revoke access when needed

**Acceptance Criteria:**

- Tenant Admin can remove user from tenant
- User loses access to tenant immediately
- User data is preserved (for audit)
- User can be re-added later if needed
- Confirmation dialog before removal
- Action is logged in audit trail

**US-TA-05: Resend Invitation Email**

- **As a** Tenant Administrator
- **I want to** resend invitation emails
- **So that** users who didn't receive the email can access the system

**Acceptance Criteria:**

- Tenant Admin can resend invitation for pending users
- New invitation email sent with new temporary password
- Previous temporary password is invalidated
- Success confirmation displayed

### 2.2 Credentials Management

**US-TA-06: Upload Google Drive Credentials**

- **As a** Tenant Administrator
- **I want to** upload Google Drive credentials
- **So that** myAdmin can access my tenant's Google Drive

**Acceptance Criteria:**

- Tenant Admin can upload credentials.json file
- Tenant Admin can upload token.json file
- System validates file format
- System encrypts credentials before storing
- System stores credentials in MySQL
- System tests connectivity to Google Drive
- Success confirmation displayed
- Previous credentials are archived (not deleted)

**US-TA-07: OAuth Flow for Google Drive**

- **As a** Tenant Administrator
- **I want to** authenticate with Google Drive via OAuth
- **So that** I don't need to manually upload credential files

**Acceptance Criteria:**

- Tenant Admin can click "Connect Google Drive" button
- System redirects to Google OAuth consent screen
- Tenant Admin authorizes myAdmin access
- System receives OAuth tokens
- System encrypts and stores tokens
- System tests connectivity
- Success confirmation displayed

**US-TA-08: Test Google Drive Connection**

- **As a** Tenant Administrator
- **I want to** test Google Drive connectivity
- **So that** I can verify credentials are working

**Acceptance Criteria:**

- Tenant Admin can click "Test Connection" button
- System attempts to list folders in Google Drive
- System displays success or error message
- If error, system provides troubleshooting guidance
- Test results are logged

**US-TA-09: Rotate Google Drive Credentials**

- **As a** Tenant Administrator
- **I want to** rotate Google Drive credentials
- **So that** I can maintain security

**Acceptance Criteria:**

- Tenant Admin can upload new credentials
- System archives old credentials (with timestamp)
- System activates new credentials
- System tests new credentials
- If test fails, system can rollback to old credentials
- Action is logged in audit trail

**US-TA-10: View Credential Status**

- **As a** Tenant Administrator
- **I want to** view credential status
- **So that** I know if credentials are working

**Acceptance Criteria:**

- Tenant Admin can see credential status dashboard
- Dashboard shows: credential type, status (active/expired/invalid), last tested, expires on
- Dashboard shows last successful connection
- Dashboard shows error messages if any
- Dashboard refreshes automatically

### 2.3 Storage Configuration

**US-TA-11: Configure Google Drive Folders**

- **As a** Tenant Administrator
- **I want to** configure Google Drive folder IDs
- **So that** myAdmin knows where to store files

**Acceptance Criteria:**

- Tenant Admin can set folder ID for invoices
- Tenant Admin can set folder ID for reports
- Tenant Admin can set folder ID for templates
- System validates folder IDs (checks if accessible)
- System saves folder configuration
- Success confirmation displayed

**US-TA-12: Browse Google Drive Folders**

- **As a** Tenant Administrator
- **I want to** browse my Google Drive folders
- **So that** I can select folders without knowing IDs

**Acceptance Criteria:**

- Tenant Admin can click "Browse" button
- System displays folder tree from Google Drive
- Tenant Admin can navigate folders
- Tenant Admin can select folder
- System auto-fills folder ID
- Selected folder is highlighted

**US-TA-13: Test Folder Access**

- **As a** Tenant Administrator
- **I want to** test folder access
- **So that** I can verify myAdmin can write to folders

**Acceptance Criteria:**

- Tenant Admin can click "Test Access" button
- System attempts to create test file in folder
- System deletes test file after verification
- System displays success or error message
- Test results are logged

**US-TA-14: Set Storage Quotas**

- **As a** Tenant Administrator
- **I want to** view storage usage
- **So that** I can monitor my tenant's storage

**Acceptance Criteria:**

- Tenant Admin can see storage usage dashboard
- Dashboard shows: total storage used, storage by type (invoices, reports, templates)
- Dashboard shows storage quota (if set by SysAdmin)
- Dashboard shows percentage used
- Dashboard updates daily

### 2.4 Tenant Settings

**US-TA-15: Update Tenant Information**

- **As a** Tenant Administrator
- **I want to** update tenant information
- **So that** contact details are current

**Acceptance Criteria:**

- Tenant Admin can update tenant name
- Tenant Admin can update contact email
- Tenant Admin can update phone number
- Tenant Admin can update address
- Changes are saved immediately
- Success confirmation displayed

**US-TA-16: Configure Notification Preferences**

- **As a** Tenant Administrator
- **I want to** configure notification preferences
- **So that** I receive relevant alerts

**Acceptance Criteria:**

- Tenant Admin can enable/disable email notifications
- Tenant Admin can set notification frequency (immediate, daily digest, weekly)
- Tenant Admin can select notification types (errors, warnings, info)
- Tenant Admin can add notification recipients
- Changes take effect immediately
- Test notification can be sent

**US-TA-17: Configure Feature Toggles**

- **As a** Tenant Administrator
- **I want to** enable/disable features
- **So that** users only see relevant functionality

**Acceptance Criteria:**

- Tenant Admin can see list of available features
- Tenant Admin can enable/disable features (if allowed by SysAdmin)
- Features include: AI assistance, advanced reports, STR pricing optimizer
- Changes take effect immediately for all tenant users
- Disabled features are hidden from UI

**US-TA-18: View Tenant Activity**

- **As a** Tenant Administrator
- **I want to** view tenant activity logs
- **So that** I can monitor usage

**Acceptance Criteria:**

- Tenant Admin can see activity dashboard
- Dashboard shows: active users, API calls, reports generated, invoices processed
- Dashboard shows activity by date range
- Dashboard is exportable (CSV)
- Dashboard updates in real-time

---

## 3. Functional Requirements

### 3.1 User Management

**FR-TA-01: User Creation**

- System must create users in Cognito
- System must assign users to current tenant
- System must send invitation email via AWS SNS
- System must generate secure temporary password

**FR-TA-02: Role Assignment**

- System must only show roles allocated to tenant
- System must support multiple roles per user
- System must update Cognito groups when roles change
- System must validate role permissions

**FR-TA-03: User Removal**

- System must remove user from tenant (not delete from Cognito)
- System must preserve user data for audit
- System must revoke access immediately
- System must log removal action

### 3.2 Credentials Management

**FR-TA-04: Credential Storage**

- System must encrypt credentials using AES-256
- System must store encrypted credentials in MySQL
- System must use encryption key from environment variable
- System must never expose decrypted credentials to frontend

**FR-TA-05: OAuth Integration**

- System must support Google OAuth 2.0 flow
- System must handle OAuth token refresh
- System must store OAuth tokens securely
- System must handle OAuth errors gracefully

**FR-TA-06: Credential Testing**

- System must test credentials before activation
- System must provide detailed error messages
- System must log test results
- System must support rollback on failure

### 3.3 Storage Configuration

**FR-TA-07: Folder Configuration**

- System must validate folder IDs before saving
- System must check folder accessibility
- System must support folder browsing via Google Drive API
- System must store folder configuration in database

**FR-TA-08: Storage Monitoring**

- System must track storage usage per tenant
- System must calculate storage by file type
- System must respect storage quotas (if set)
- System must alert when approaching quota

### 3.4 Tenant Settings

**FR-TA-09: Settings Storage**

- System must store settings in database
- System must apply settings immediately
- System must validate settings before saving
- System must log settings changes

**FR-TA-10: Notification Configuration**

- System must support email notifications via AWS SNS
- System must support notification preferences per user
- System must support notification batching (digest)
- System must allow test notifications

---

## 4. Non-Functional Requirements

### 4.1 Security

**NFR-TA-01: Authentication**

- All endpoints must require authentication
- All endpoints must verify Tenant_Admin role
- All endpoints must verify tenant context

**NFR-TA-02: Authorization**

- Tenant Admin can only access their tenant
- Tenant Admin cannot access other tenants
- Tenant Admin cannot access platform settings

**NFR-TA-03: Data Protection**

- Credentials must be encrypted at rest
- Credentials must be encrypted in transit
- Credentials must never be logged
- Audit logs must not contain sensitive data

### 4.2 Performance

**NFR-TA-04: Response Time**

- User list must load in < 2 seconds
- Credential upload must complete in < 5 seconds
- Folder browsing must load in < 3 seconds

**NFR-TA-05: Scalability**

- System must support 100+ users per tenant
- System must support 1000+ folders per tenant
- System must handle concurrent credential tests

### 4.3 Usability

**NFR-TA-06: User Interface**

- UI must be intuitive and easy to use
- UI must be responsive (mobile, tablet, desktop)
- UI must follow existing myAdmin design patterns
- UI must provide clear error messages

**NFR-TA-07: Help & Documentation**

- Each feature must have inline help
- Each feature must have tooltips
- Each feature must link to documentation
- Error messages must provide troubleshooting guidance

---

## 5. Success Criteria

### 5.1 User Management Success

- ✅ Tenant Admin can create users
- ✅ Tenant Admin can assign roles
- ✅ Tenant Admin can remove users
- ✅ Users receive invitation emails
- ✅ All tests passing

### 5.2 Credentials Management Success

- ✅ Tenant Admin can upload credentials
- ✅ Tenant Admin can use OAuth flow
- ✅ Credentials are encrypted and secure
- ✅ Connection testing works
- ✅ All tests passing

### 5.3 Storage Configuration Success

- ✅ Tenant Admin can configure folders
- ✅ Tenant Admin can browse folders
- ✅ Folder access testing works
- ✅ Storage monitoring works
- ✅ All tests passing

### 5.4 Tenant Settings Success

- ✅ Tenant Admin can update settings
- ✅ Notifications work correctly
- ✅ Feature toggles work
- ✅ Activity dashboard works
- ✅ All tests passing

---

## 6. Out of Scope

The following are explicitly out of scope:

- ❌ Template Management (already implemented in Phase 2.6)
- ❌ Platform-level administration (handled by SysAdmin)
- ❌ Tenant creation (handled by SysAdmin)
- ❌ Role creation (handled by SysAdmin)
- ❌ Generic template management (handled by SysAdmin)

---

## 7. Dependencies

### 7.1 Technical Dependencies

- AWS Cognito (user management)
- MySQL database (metadata storage)
- Google Drive API (storage integration)
- AWS SNS (email notifications)
- CredentialService (from Phase 1)

### 7.2 Specification Dependencies

- Railway Migration Phase 1 (credentials infrastructure)
- Railway Migration Phase 2 (template infrastructure)
- SysAdmin Module (tenant and role allocation)

---

## 8. Acceptance Testing Scenarios

### Scenario 1: Create User and Assign Role

**Given** I am logged in as Tenant Administrator
**When** I navigate to User Management
**And** I click "Create User"
**And** I fill in email "john@example.com"
**And** I fill in name "John Doe"
**And** I select role "Finance_User"
**And** I click "Create User"
**Then** I see success message "User created and invitation sent"
**And** John appears in user list
**And** John receives invitation email

### Scenario 2: Upload Google Drive Credentials

**Given** I am logged in as Tenant Administrator
**When** I navigate to Credentials Management
**And** I click "Upload Credentials"
**And** I upload "credentials.json"
**And** I upload "token.json"
**And** I click "Save and Test"
**Then** I see success message "Credentials saved and tested successfully"
**And** Connection status shows "Active"
**And** Last tested timestamp is updated

### Scenario 3: Configure Storage Folders

**Given** I am logged in as Tenant Administrator
**When** I navigate to Storage Configuration
**And** I click "Browse" for Invoices folder
**And** I select folder "Invoices/2026"
**And** I click "Test Access"
**Then** I see success message "Folder is accessible"
**And** Folder ID is saved
**And** Test file is created and deleted

### Scenario 4: Update Notification Settings

**Given** I am logged in as Tenant Administrator
**When** I navigate to Tenant Settings
**And** I select "Notifications" tab
**And** I enable "Email Notifications"
**And** I select frequency "Daily Digest"
**And** I add recipient "admin@example.com"
**And** I click "Send Test Notification"
**Then** I see success message "Test notification sent"
**And** admin@example.com receives test email

---

## 9. Revision History

| Version | Date       | Author       | Changes       |
| ------- | ---------- | ------------ | ------------- |
| 0.1     | 2026-02-05 | AI Assistant | Initial draft |

---

## 10. Approval

| Role                | Name | Signature | Date |
| ------------------- | ---- | --------- | ---- |
| Product Owner       |      |           |      |
| Technical Lead      |      |           |      |
| Tenant Admin (User) |      |           |      |
