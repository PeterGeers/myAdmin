# SysAdmin Module - Requirements

**Status**: Updated
**Created**: February 5, 2026
**Last Updated**: February 8, 2026

---

## 1. Overview

The SysAdmin Module provides platform-level administration capabilities for managing the myAdmin system. This specification defines the requirements for implementing SysAdmin functionality, including tenant management, role management, and platform configuration.

**Scope**: This module focuses on platform-level administration. Generic template management has been removed from scope - templates are managed per-tenant by Tenant Admins using the `tenant_template_config` table.

**User Stories**: 15 user stories covering tenant management (9), platform configuration (3), and monitoring & audit (3).

---

## 2. User Stories

### 2.1 Tenant Management

**US-SA-01: Create New Tenant**

- **As a** SysAdmin
- **I want to** create a new tenant in the system
- **So that** new organizations can use myAdmin

**Acceptance Criteria:**

- SysAdmin can access tenant creation form
- Form includes: tenant name, contact email, initial admin email
- System creates tenant in database
- System creates tenant in Cognito
- System sends invitation email to initial admin
- Tenant is created in inactive state (requires activation)
- Success confirmation displayed

**US-SA-02: View All Tenants**

- **As a** SysAdmin
- **I want to** view a list of all tenants
- **So that** I can monitor the platform

**Acceptance Criteria:**

- SysAdmin can see list of all tenants
- List shows: tenant name, status (active/inactive), created date, user count
- List is sortable and filterable
- List is paginated (50 per page)
- Cannot see tenant-specific data (invoices, reports, etc.)

**US-SA-03: Update Tenant Configuration**

- **As a** SysAdmin
- **I want to** update tenant configuration
- **So that** I can manage tenant settings

**Acceptance Criteria:**

- SysAdmin can edit tenant name
- SysAdmin can update contact email
- SysAdmin can enable/disable modules (FIN, STR, BNB)
- SysAdmin can set storage quotas
- Changes are logged in audit trail
- Cannot access tenant data or credentials

**US-SA-04: Activate/Deactivate Tenant**

- **As a** SysAdmin
- **I want to** activate or deactivate a tenant
- **So that** I can control access to the platform

**Acceptance Criteria:**

- SysAdmin can toggle tenant status
- Deactivated tenants cannot log in
- Deactivated tenant data is preserved
- Reactivation restores full access
- Action is logged in audit trail
- Confirmation dialog before deactivation

### 2.2 Role Management

**US-SA-05: Create New Role**

- **As a** SysAdmin
- **I want to** create new roles (Cognito groups)
- **So that** I can define access levels

**Acceptance Criteria:**

- SysAdmin can create new Cognito group
- Form includes: role name, description, permissions
- Role is created in Cognito
- Role is available for tenant assignment
- Success confirmation displayed

**US-SA-06: View All Roles**

- **As a** SysAdmin
- **I want to** view all available roles
- **So that** I can understand the permission structure

**Acceptance Criteria:**

- SysAdmin can see list of all roles
- List shows: role name, description, user count, tenant count
- List includes system roles (SysAdmin, Tenant_Admin) and custom roles
- System roles cannot be deleted

**US-SA-07: Update Role Permissions**

- **As a** SysAdmin
- **I want to** update role permissions
- **So that** I can adjust access levels

**Acceptance Criteria:**

- SysAdmin can edit role description
- SysAdmin can update role permissions
- Changes apply to all users with that role
- System roles (SysAdmin, Tenant_Admin) cannot be modified
- Changes are logged in audit trail

**US-SA-08: Delete Role**

- **As a** SysAdmin
- **I want to** delete unused roles
- **So that** I can keep the system clean

**Acceptance Criteria:**

- SysAdmin can delete custom roles
- Cannot delete system roles (SysAdmin, Tenant_Admin)
- Cannot delete roles assigned to users (must unassign first)
- Confirmation dialog before deletion
- Action is logged in audit trail

**US-SA-09: Define Tenant-Role Allocation**

- **As a** SysAdmin
- **I want to** define which roles are available per tenant
- **So that** tenants can only assign appropriate roles

**Acceptance Criteria:**

- SysAdmin can assign roles to tenants
- Tenant Admins can only assign roles allocated to their tenant
- All tenants have access to basic roles (User, Viewer)
- Changes are logged in audit trail

### 2.3 Platform Configuration

**US-SA-10: Manage Email Templates**

- **As a** SysAdmin
- **I want to** manage email templates
- **So that** system emails are professional

**Acceptance Criteria:**

- SysAdmin can edit email templates (invitation, password reset, etc.)
- Templates support placeholders ({{user_name}}, {{tenant_name}}, etc.)
- SysAdmin can preview emails with sample data
- Changes apply to all tenants
- Templates are versioned

**US-SA-11: Configure Platform Branding**

- **As a** SysAdmin
- **I want to** configure platform branding
- **So that** myAdmin has consistent appearance

**Acceptance Criteria:**

- SysAdmin can upload platform logo
- SysAdmin can set primary/secondary colors
- SysAdmin can set platform name/tagline
- Changes apply to login page and system emails
- Tenant-specific branding overrides platform branding

**US-SA-12: Manage System Settings**

- **As a** SysAdmin
- **I want to** manage system-wide settings
- **So that** I can control platform behavior

**Acceptance Criteria:**

- SysAdmin can set session timeout
- SysAdmin can enable/disable features (AI assistance, notifications)
- SysAdmin can set rate limits
- SysAdmin can configure storage quotas
- Changes are logged in audit trail

### 2.4 Monitoring & Audit

**US-SA-13: View System Audit Logs**

- **As a** SysAdmin
- **I want to** view system-wide audit logs
- **So that** I can monitor platform activity

**Acceptance Criteria:**

- SysAdmin can see all platform-level actions
- Logs show: timestamp, user, action, tenant (if applicable)
- Logs are filterable (date range, action type, tenant)
- Logs are exportable (CSV)
- Cannot see tenant-specific data in logs

**US-SA-14: Monitor Platform Health**

- **As a** SysAdmin
- **I want to** monitor platform health
- **So that** I can ensure system reliability

**Acceptance Criteria:**

- SysAdmin can see system status dashboard
- Dashboard shows: active users, API response times, error rates
- Dashboard shows storage usage (aggregated)
- Dashboard shows database connection status
- Alerts for critical issues

**US-SA-15: View Usage Statistics**

- **As a** SysAdmin
- **I want to** view usage statistics
- **So that** I can understand platform usage

**Acceptance Criteria:**

- SysAdmin can see aggregated usage stats
- Stats show: active tenants, total users, API calls per day
- Stats show: storage usage per tenant (aggregated)
- Stats are exportable (CSV)
- Cannot see tenant-specific data

---

## 3. Functional Requirements

### 3.1 Access Control

**FR-SA-01: SysAdmin Role**

- System must have a SysAdmin role in Cognito
- SysAdmin role must have access to myAdmin tenant only
- SysAdmin role must not have access to client tenant data **when acting as SysAdmin in myAdmin tenant**
- **Important**: This restriction applies to the role, not the person. A user with SysAdmin + Tenant_Admin roles can access tenant data when using their Tenant_Admin role in that tenant.

**FR-SA-02: myAdmin Tenant**

- System must have a myAdmin system tenant
- myAdmin tenant must be created in database
- myAdmin tenant must be created in Cognito
- myAdmin tenant must use Railway filesystem (not Google Drive)

**FR-SA-03: Multi-Role Users**

- Users can have multiple roles (e.g., SysAdmin + Tenant_Admin for GoodwinSolutions)
- Users with multiple roles can switch between tenants
- Access is determined by: **current tenant + user's roles for that tenant**
- When in myAdmin tenant → SysAdmin role active → Platform management only
- When in client tenant (e.g., GoodwinSolutions) → Tenant_Admin role active → Full tenant access
- Users with SysAdmin role can access myAdmin tenant
- Users with Tenant_Admin role can access their assigned tenant(s)
- Same user can have both roles and access both types of tenants

### 3.2 Data Isolation

**FR-SA-04: Tenant Data Isolation**

- SysAdmin **role** (when in myAdmin tenant) cannot view tenant-specific data (invoices, reports, transactions)
- SysAdmin **role** (when in myAdmin tenant) cannot access tenant Google Drive credentials
- SysAdmin **role** (when in myAdmin tenant) cannot view tenant templates (tenant-customized)
- **Important**: Same user with Tenant_Admin role CAN access this data when in that tenant
- SysAdmin can only view aggregated, anonymized statistics

**FR-SA-05: Audit Trail**

- All SysAdmin actions must be logged
- Audit logs must include: timestamp, user, action, details
- Audit logs must be immutable (cannot be deleted or modified)
- Audit logs must be retained for 1 year minimum

### 3.3 Storage

**FR-SA-06: Platform Assets Storage**

- Platform assets (logos, branding) must be stored on Railway filesystem
- Assets must be in `backend/static/platform/` directory
- Assets must be publicly accessible (no authentication)

---

## 4. Non-Functional Requirements

### 4.1 Performance

**NFR-SA-01: Response Time**

- Tenant list must load in < 2 seconds
- Role list must load in < 1 second

**NFR-SA-02: Scalability**

- System must support 100+ tenants
- System must support 50+ roles
- System must support 1000+ users

### 4.2 Security

**NFR-SA-03: Authentication**

- SysAdmin must authenticate via AWS Cognito
- SysAdmin session must expire after 8 hours
- SysAdmin must use MFA (optional but recommended)

**NFR-SA-04: Authorization**

- All SysAdmin endpoints must require SysAdmin role
- All actions must be authorized before execution
- Failed authorization attempts must be logged

**NFR-SA-05: Data Protection**

- Tenant credentials must remain encrypted
- SysAdmin cannot decrypt tenant credentials
- Audit logs must not contain sensitive data

### 4.3 Usability

**NFR-SA-06: User Interface**

- SysAdmin UI must be intuitive and easy to use
- SysAdmin UI must be responsive (mobile, tablet, desktop)
- SysAdmin UI must follow existing myAdmin design patterns

**NFR-SA-07: Error Handling**

- All errors must be displayed clearly to SysAdmin
- All errors must be logged for troubleshooting
- System must recover gracefully from errors

### 4.4 Maintainability

**NFR-SA-08: Code Quality**

- All code must follow project coding standards
- All code must have unit tests (80%+ coverage)
- All code must have integration tests

**NFR-SA-09: Documentation**

- All APIs must be documented in OpenAPI/Swagger
- All features must have user documentation
- All code must have inline comments

---

## 5. Success Criteria

### 5.1 Functional Success

- ✅ SysAdmin can create and manage tenants
- ✅ SysAdmin can create and manage roles
- ✅ SysAdmin can configure platform settings
- ✅ SysAdmin can view audit logs and statistics
- ✅ SysAdmin cannot access tenant-specific data

### 5.2 Technical Success

- ✅ All unit tests passing (80%+ coverage)
- ✅ All integration tests passing
- ✅ All API endpoints documented
- ✅ All security requirements met
- ✅ Performance requirements met

### 5.3 User Acceptance

- ✅ SysAdmin can complete all tasks without assistance
- ✅ SysAdmin UI is intuitive and easy to use
- ✅ SysAdmin can troubleshoot issues using audit logs
- ✅ No security vulnerabilities identified

---

## 6. Out of Scope

The following are explicitly out of scope for this specification:

- ❌ Tenant-specific user management (handled by Tenant Admin)
- ❌ Tenant-specific template customization (handled by Tenant Admin)
- ❌ Tenant-specific credential management (handled by Tenant Admin)
- ❌ Financial reporting and analytics (handled by FIN module)
- ❌ STR-specific features (handled by STR module)
- ❌ Invoice processing (handled by Invoice module)

---

## 7. Dependencies

### 7.1 Technical Dependencies

- AWS Cognito (user authentication and role management)
- MySQL database (tenant and role metadata)
- Flask backend (API endpoints)
- React frontend (SysAdmin UI)

### 7.2 Specification Dependencies

- Railway Migration (Phase 3 creates myAdmin tenant)
- Tenant Admin Module (defines tenant-level administration)
- Authentication (Cognito integration and RBAC)

---

## 8. Acceptance Testing Scenarios

### Scenario 1: Create New Tenant

**Given** I am logged in as SysAdmin
**When** I navigate to Tenant Management
**And** I click "Create New Tenant"
**And** I fill in tenant name "NewCorp"
**And** I fill in contact email "admin@newcorp.com"
**And** I fill in initial admin email "john@newcorp.com"
**And** I click "Create Tenant"
**Then** I see success message "Tenant created successfully"
**And** NewCorp appears in tenant list with status "Inactive"
**And** John receives invitation email

### Scenario 2: View Audit Logs

**Given** I am logged in as SysAdmin
**When** I navigate to Audit Logs
**And** I filter by date range "Last 7 days"
**And** I filter by action type "Tenant Created"
**Then** I see list of tenant creation events
**And** Each event shows timestamp, user, tenant name
**And** I cannot see tenant-specific data

### Scenario 3: Cannot Access Tenant Data

**Given** I am logged in as SysAdmin
**When** I try to access tenant "GoodwinSolutions"
**Then** I see error "Access denied"
**And** I cannot view invoices, reports, or transactions
**And** I cannot view tenant Google Drive credentials
**And** Action is logged in audit trail

---

## 9. Revision History

| Version | Date       | Author       | Changes                                                                                     |
| ------- | ---------- | ------------ | ------------------------------------------------------------------------------------------- |
| 0.1     | 2026-02-05 | AI Assistant | Initial draft                                                                               |
| 0.2     | 2026-02-08 | AI Assistant | Removed generic template management (US-SA-10 to US-SA-13) - aligned with simplified design |

---

## 10. Approval

| Role            | Name | Signature | Date |
| --------------- | ---- | --------- | ---- |
| Product Owner   |      |           |      |
| Technical Lead  |      |           |      |
| SysAdmin (User) |      |           |      |
