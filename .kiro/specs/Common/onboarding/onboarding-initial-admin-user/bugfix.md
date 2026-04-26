# Bugfix Requirements Document

## Introduction

When a new tenant is created through any of the three provisioning entry points (SysAdmin UI, `provision_tenant.py` script, or SysAdmin provisioning API endpoint), no initial admin user is created for the tenant. The tenant ends up with 0 users in `user_tenant_roles`, no Cognito user linked to the tenant with the `Tenant_Admin` role, no invitation record in `user_invitations`, and no invitation email sent. This makes the tenant unusable because nobody can log in and manage it.

The working user creation logic already exists in `tenant_admin_users.py` (POST `/api/tenant-admin/users`) but is never called during provisioning. The fix must ensure that every tenant provisioning flow creates an initial admin user with the `Tenant_Admin` role.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a new tenant is created via the SysAdmin UI (POST `/api/sysadmin/tenants`) with an `initial_admin_email` in the request body THEN the system inserts the tenant record, modules, and chart of accounts but never extracts `initial_admin_email` from the request and never creates a user in `user_tenant_roles` or Cognito for that tenant

1.2 WHEN a new tenant is created via the `provision_tenant.py` script THEN the system inserts the tenant record, modules, and chart of accounts, and updates the Cognito user's `custom:tenants` attribute, but never creates a `user_tenant_roles` entry with `Tenant_Admin` role and never sends an invitation email

1.3 WHEN a new tenant is created via the SysAdmin provisioning API endpoint (POST `/api/sysadmin/provisioning/provision`) THEN the system inserts the tenant record, modules, and chart of accounts, updates Cognito `custom:tenants`, and sends a welcome email, but never creates a `user_tenant_roles` entry with `Tenant_Admin` role and never creates an invitation record in `user_invitations`

1.4 WHEN a tenant is created through any entry point THEN the tenant's user count shows 0 in the SysAdmin tenant list, and no user can operate within the tenant as `Tenant_Admin`

### Expected Behavior (Correct)

2.1 WHEN a new tenant is created via the SysAdmin UI with an `initial_admin_email` provided THEN the system SHALL extract the `initial_admin_email` from the request, create or link the Cognito user, insert a `user_tenant_roles` row with email, administration, and `Tenant_Admin` role, create an invitation record in `user_invitations`, and send an invitation email (with temporary password for new users) or a tenant-added notification email (for existing Cognito users)

2.2 WHEN a new tenant is created via the `provision_tenant.py` script THEN the system SHALL create a `user_tenant_roles` entry with the signup email, the new administration name, and `Tenant_Admin` role, create an invitation record in `user_invitations`, and send an invitation email to the user

2.3 WHEN a new tenant is created via the SysAdmin provisioning API endpoint THEN the system SHALL create a `user_tenant_roles` entry with the signup email, the new administration name, and `Tenant_Admin` role, create an invitation record in `user_invitations`, and send an invitation email to the user

2.4 WHEN a tenant is created through any entry point and the initial admin user step completes successfully THEN the system SHALL show a user count of at least 1 for that tenant in the SysAdmin tenant list, and the initial admin user SHALL be able to log in and operate within the tenant as `Tenant_Admin`

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a tenant is created through any entry point THEN the system SHALL CONTINUE TO insert the tenant record into the `tenants` table with correct details and `active` status

3.2 WHEN a tenant is created through any entry point THEN the system SHALL CONTINUE TO insert the correct modules into `tenant_modules` (always including `TENADMIN`)

3.3 WHEN a tenant is created through any entry point THEN the system SHALL CONTINUE TO load the chart of accounts from the locale-appropriate JSON template into `rekeningschema`

3.4 WHEN a tenant is created via `provision_tenant.py` THEN the system SHALL CONTINUE TO update the Cognito user's `custom:tenants` attribute, mark the signup as provisioned, and send the SNS admin notification

3.5 WHEN a tenant is created via the SysAdmin provisioning API THEN the system SHALL CONTINUE TO update the Cognito user's `custom:tenants` attribute, mark the signup as provisioned, set the trial plan, and send the welcome email

3.6 WHEN a Tenant_Admin manually creates a user via POST `/api/tenant-admin/users` THEN the system SHALL CONTINUE TO create the user in Cognito, add `user_tenant_roles`, create an invitation, and send the invitation email exactly as it does today

3.7 WHEN the provisioning service is rerun for an existing tenant (idempotent rerun) THEN the system SHALL CONTINUE TO skip already-completed steps (tenant insert, modules, chart of accounts) without error

3.8 WHEN the SysAdmin UI creates a tenant without providing `initial_admin_email` THEN the system SHALL CONTINUE TO create the tenant successfully (tenant record, modules, chart) and SHALL skip the initial admin user creation step without error

### Resend Invitation (SysAdmin)

2.5 WHEN a SysAdmin clicks "Resend Invitation" in the Tenant Management edit modal THEN the system SHALL generate a new temporary password, update the Cognito user password to keep status `CONFIRMED`, create or update the invitation record in `user_invitations`, and send a new invitation email to the tenant's contact email

2.6 WHEN a SysAdmin attempts to resend an invitation for a tenant that has no initial admin user yet THEN the system SHALL create the initial admin user (Cognito user, `user_tenant_roles` with `Tenant_Admin`, invitation record) and send the invitation email
