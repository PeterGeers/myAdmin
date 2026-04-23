# Initial Admin User Creation During Tenant Provisioning — Bugfix Design

## Overview

All three tenant provisioning entry points (SysAdmin UI, `provision_tenant.py` script, SysAdmin provisioning API) successfully create tenant infrastructure (tenant record, modules, chart of accounts) but never create an initial admin user. This leaves every newly provisioned tenant with 0 users and no way to log in.

The fix extracts the existing user creation logic from `tenant_admin_users.py` into a reusable service method on `TenantProvisioningService` and calls it from each entry point after the tenant infrastructure is created. The new method must be idempotent (safe to rerun), handle both new and existing Cognito users, and create the `user_tenant_roles` row with `Tenant_Admin` role, an invitation record in `user_invitations`, and send the appropriate email.

## Glossary

- **Bug_Condition (C)**: A tenant provisioning operation completes without creating an initial admin user — no `user_tenant_roles` row, no `user_invitations` record, no invitation email sent
- **Property (P)**: After provisioning, the tenant has at least one user with `Tenant_Admin` role in `user_tenant_roles`, an invitation record in `user_invitations`, and an invitation email was sent (or a tenant-added notification for existing Cognito users)
- **Preservation**: Existing tenant infrastructure creation (tenant record, modules, chart of accounts), Cognito `custom:tenants` updates, signup status marking, SNS admin notifications, welcome emails, and the manual user creation flow via `tenant_admin_users.py` must all remain unchanged
- **`TenantProvisioningService`**: The service in `backend/src/services/tenant_provisioning_service.py` that handles shared provisioning logic (tenant record, modules, chart of accounts)
- **`InvitationService`**: The service in `backend/src/services/invitation_service.py` that manages invitation records and temporary password generation
- **`CognitoService`**: The service in `backend/src/services/cognito_service.py` that handles Cognito user operations (create, get, update tenants)
- **`EmailTemplateService`**: The service in `backend/src/services/email_template_service.py` that renders email templates with locale detection
- **`SESEmailService`**: The service in `backend/src/services/ses_email_service.py` that sends emails via AWS SES
- **Entry Point**: One of the three code paths that trigger tenant provisioning: SysAdmin UI (`sysadmin_tenants.py`), provisioning script (`provision_tenant.py`), or provisioning API (`sysadmin_provisioning.py`)

## Bug Details

### Bug Condition

The bug manifests when any of the three provisioning entry points creates a new tenant. The `TenantProvisioningService.create_and_provision_tenant()` method handles tenant record, modules, and chart of accounts — but has no step for creating an initial admin user. None of the three callers add this step either.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type ProvisioningRequest
         { entry_point: 'sysadmin_ui' | 'provision_script' | 'provisioning_api',
           email: string,
           administration: string,
           initial_admin_email: optional string }
  OUTPUT: boolean

  // For SysAdmin UI: bug triggers when initial_admin_email is provided
  IF input.entry_point == 'sysadmin_ui' THEN
    RETURN input.initial_admin_email IS NOT NULL
           AND input.initial_admin_email IS NOT EMPTY
           AND NOT userTenantRoleExists(input.initial_admin_email, input.administration, 'Tenant_Admin')

  // For script and API: bug always triggers (email comes from signup record)
  IF input.entry_point IN ['provision_script', 'provisioning_api'] THEN
    RETURN input.email IS NOT NULL
           AND input.email IS NOT EMPTY
           AND NOT userTenantRoleExists(input.email, input.administration, 'Tenant_Admin')

  RETURN FALSE
END FUNCTION
```

### Examples

- **SysAdmin UI with `initial_admin_email`**: SysAdmin creates tenant "AcmeCorp" with `initial_admin_email: "admin@acme.com"`. Tenant record, modules, and chart are created. But `admin@acme.com` has no `user_tenant_roles` row, no Cognito user linked to "AcmeCorp", no invitation record, and no invitation email. Expected: `admin@acme.com` should have `Tenant_Admin` role and receive an invitation email.

- **`provision_tenant.py` script**: Operator runs `python provision_tenant.py user@example.com`. Tenant is created, Cognito `custom:tenants` is updated, signup is marked provisioned, SNS notification is sent. But `user@example.com` has no `user_tenant_roles` entry with `Tenant_Admin` and no invitation email. Expected: `user@example.com` should have `Tenant_Admin` role and receive an invitation email with temporary password.

- **SysAdmin provisioning API**: SysAdmin provisions `user@example.com` via POST `/api/sysadmin/provisioning/provision`. Tenant is created, Cognito updated, signup marked provisioned, welcome email sent. But `user@example.com` has no `user_tenant_roles` entry and no invitation record. Expected: `user@example.com` should have `Tenant_Admin` role and receive an invitation email.

- **SysAdmin UI without `initial_admin_email`**: SysAdmin creates tenant "TestCorp" without providing `initial_admin_email`. Tenant infrastructure is created. No admin user should be created — this is correct behavior and must be preserved.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Tenant record insertion into `tenants` table with correct details and `active` status must continue to work exactly as before
- Tenant module insertion into `tenant_modules` (always including `TENADMIN`) must remain unchanged
- Chart of accounts loading from locale-appropriate JSON template into `rekeningschema` must remain unchanged
- `provision_tenant.py`: Cognito `custom:tenants` update, `pending_signups` status marking to `provisioned`, and SNS admin notification must continue to work
- SysAdmin provisioning API: Cognito `custom:tenants` update, signup status marking, trial plan setting, and welcome email must continue to work
- Manual user creation via POST `/api/tenant-admin/users` must continue to work exactly as today
- Idempotent reruns must continue to skip already-completed steps without error
- SysAdmin UI tenant creation without `initial_admin_email` must succeed without creating an admin user

**Scope:**
All provisioning inputs that do NOT involve initial admin user creation should be completely unaffected by this fix. This includes:

- Tenant record creation logic
- Module insertion logic
- Chart of accounts loading logic
- Cognito `custom:tenants` attribute updates (handled by callers, not the shared service)
- SNS admin notifications
- Welcome emails (distinct from invitation emails)
- The existing `tenant_admin_users.py` POST endpoint

## Hypothesized Root Cause

Based on the code analysis, the root cause is clear and confirmed:

1. **Missing Step in `TenantProvisioningService`**: The `create_and_provision_tenant()` method only handles three steps: (1) insert tenant record, (2) insert modules, (3) load chart of accounts. There is no Step 4 for creating an initial admin user. The method does not accept an `initial_admin_email` parameter.

2. **No Caller-Side User Creation**: None of the three entry points add user creation after calling `create_and_provision_tenant()`:
   - `sysadmin_tenants.py` (`create_tenant`): Accepts `initial_admin_email` in the request schema (documented in docstring) but never reads it from `data` or acts on it
   - `provision_tenant.py` (`provision`): Updates Cognito `custom:tenants` but never creates a `user_tenant_roles` row or invitation
   - `sysadmin_provisioning.py` (`provision_signup`): Updates Cognito `custom:tenants` and sends a welcome email but never creates a `user_tenant_roles` row or invitation

3. **Working Logic Exists But Is Isolated**: The complete user creation flow (Cognito user creation/lookup, `user_tenant_roles` insertion, invitation record creation, email sending) already works in `tenant_admin_users.py` POST `/api/tenant-admin/users`. This logic needs to be extracted into a reusable service method.

## Correctness Properties

Property 1: Bug Condition — Initial Admin User Created During Provisioning

_For any_ provisioning request where an admin email is available (either `initial_admin_email` for SysAdmin UI, or the signup email for script/API entry points), the fixed provisioning flow SHALL create a `user_tenant_roles` row with the admin email, the tenant's administration name, and the `Tenant_Admin` role, AND create an invitation record in `user_invitations`, AND attempt to send an invitation email (for new Cognito users) or a tenant-added notification (for existing Cognito users).

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — Existing Provisioning Infrastructure Unchanged

_For any_ provisioning request (with or without initial admin email), the fixed provisioning flow SHALL produce the same tenant record, modules, and chart of accounts as the original flow, preserving all existing infrastructure creation behavior including idempotent skip logic.

**Validates: Requirements 3.1, 3.2, 3.3, 3.7**

Property 3: Preservation — Entry-Point-Specific Behavior Unchanged

_For any_ provisioning request through the script or API entry points, the fixed flow SHALL continue to perform Cognito `custom:tenants` updates, signup status marking, SNS notifications, trial plan setting, and welcome emails exactly as the original flow, preserving all entry-point-specific behavior.

**Validates: Requirements 3.4, 3.5**

Property 4: Edge Case — SysAdmin UI Without initial_admin_email

_For any_ SysAdmin UI tenant creation request where `initial_admin_email` is NOT provided or is empty, the fixed flow SHALL create the tenant infrastructure successfully and SHALL NOT attempt to create an initial admin user, preserving the current behavior of allowing tenant creation without an initial admin.

**Validates: Requirements 3.8**

Property 5: Preservation — Manual User Creation Unchanged

_For any_ user creation request via POST `/api/tenant-admin/users`, the fixed code SHALL produce exactly the same behavior as the original code, preserving the existing manual user creation flow for Tenant_Admin users.

**Validates: Requirements 3.6**

## Fix Implementation

### Changes Required

**File**: `backend/src/services/tenant_provisioning_service.py`

**New Method**: `create_initial_admin_user()`

**Specific Changes**:

1. **Add `create_initial_admin_user()` method to `TenantProvisioningService`**: Extract the user creation logic from `tenant_admin_users.py` into a reusable method. This method will:
   - Accept `administration`, `email`, `created_by`, and `locale` parameters
   - Check if a `user_tenant_roles` row already exists for this email + administration (idempotent guard)
   - Check if the Cognito user already exists
   - For new users: create Cognito user with `custom:tenants`, then immediately call `admin_set_user_password(Permanent=True)` to move the user from `FORCE_CHANGE_PASSWORD` to `CONFIRMED` status, create invitation record with temp password, insert `user_tenant_roles` with `Tenant_Admin`, send invitation email
   - For existing users (already `CONFIRMED` from signup flow): update Cognito `custom:tenants`, insert `user_tenant_roles` with `Tenant_Admin`, send tenant-added notification email
   - Return a result dict with status (`created`, `skipped`, `existing_user`) and any warnings

### Cognito User Status Handling

**Critical**: When Cognito creates a user via `admin_create_user()`, the user status is set to `FORCE_CHANGE_PASSWORD`. This blocks normal login — the user would need to complete a password challenge flow. To avoid this:

- **New users** (SysAdmin UI path): After `admin_create_user()`, immediately call `admin_set_user_password(Username=email, Password=temp_password, Permanent=True)` to move the user to `CONFIRMED` status. The user logs in with the temporary password from the invitation email and can then change it via the normal password reset flow.
- **Existing users** (provisioning script/API path): The user already went through `sign_up` + `confirm_sign_up` during the promo signup flow, so their status is already `CONFIRMED`. No password change needed — just add the tenant and role.

This pattern is already used in `tenant_admin_email.py` (resend invitation) where `admin_set_user_password(Permanent=True)` moves users from `FORCE_CHANGE_PASSWORD` to `CONFIRMED`.

2. **Add optional `initial_admin_email` parameter to `create_and_provision_tenant()`**: After the existing three steps (tenant, modules, chart), add a Step 4 that calls `create_initial_admin_user()` if `initial_admin_email` is provided. Add the result to the returned `results` dict under key `initial_admin`.

3. **Update `sysadmin_tenants.py` (`create_tenant`)**: Extract `initial_admin_email` from `data` and pass it to `create_and_provision_tenant()`. Include the `initial_admin` result in the response.

4. **Update `provision_tenant.py` (`provision`)**: Pass the signup email as `initial_admin_email` to `service.create_and_provision_tenant()`. The locale from the signup record is already available.

5. **Update `sysadmin_provisioning.py` (`provision_signup`)**: Pass the signup email as `initial_admin_email` to `service.create_and_provision_tenant()`. The locale is already available from the signup record.

6. **Add SysAdmin resend invitation endpoint**: Create `POST /api/sysadmin/tenants/<administration>/resend-invitation` in `sysadmin_tenants.py`. This endpoint allows SysAdmin to resend the initial admin invitation email for a tenant. It:
   - Accepts `{ "email": "admin@example.com" }` in the request body
   - Looks up the existing invitation in `user_invitations` for this email + administration
   - If no invitation exists, creates one (handles the case where provisioning was done before this fix)
   - Generates a new temporary password, updates the Cognito user password via `admin_set_user_password(Permanent=True)` to keep status `CONFIRMED`
   - Sends the invitation email via SES
   - Returns success with invitation details
   - Authorization: SysAdmin role required
   - Reuses `InvitationService`, `EmailTemplateService`, and `SESEmailService`

7. **Add "Resend Invitation" button to SysAdmin Tenant Management modal**: In the edit modal for existing tenants, add a "Resend Invitation" button that:
   - Is visible only in edit mode for existing tenants
   - Calls the new `POST /api/sysadmin/tenants/<administration>/resend-invitation` endpoint with the tenant's `contact_email`
   - Shows a success/error toast with the result
   - Is disabled while the request is in progress

### Idempotency Design

The `create_initial_admin_user()` method must be idempotent:

- If `user_tenant_roles` row already exists for this email + administration → skip (return `'skipped'`)
- If Cognito user already exists but doesn't have this tenant → add tenant, insert role, send tenant-added email
- If Cognito user already exists and already has this tenant → skip Cognito update, still ensure `user_tenant_roles` exists

### Error Handling

- Initial admin user creation failures should be logged as warnings but should NOT fail the overall provisioning operation
- The `results` dict should include an `initial_admin` key with status and any error details
- This matches the existing pattern where chart of accounts failures produce warnings rather than hard failures

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause analysis that `create_and_provision_tenant()` has no user creation step and no caller adds one.

**Test Plan**: Write tests that call each entry point's provisioning logic and assert that a `user_tenant_roles` row with `Tenant_Admin` exists afterward. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:

1. **SysAdmin UI Test**: Call `create_tenant` endpoint with `initial_admin_email` in request body, verify `user_tenant_roles` has a `Tenant_Admin` row for that email (will fail on unfixed code)
2. **Provisioning Script Test**: Call `provision()` function with a valid signup email, verify `user_tenant_roles` has a `Tenant_Admin` row (will fail on unfixed code)
3. **Provisioning API Test**: Call `provision_signup` endpoint with a valid signup email, verify `user_tenant_roles` has a `Tenant_Admin` row (will fail on unfixed code)
4. **Invitation Record Test**: After any provisioning, verify `user_invitations` has a record for the admin email (will fail on unfixed code)

**Expected Counterexamples**:

- `user_tenant_roles` table has 0 rows for the provisioned tenant after provisioning completes
- `user_invitations` table has 0 records for the admin email after provisioning completes
- Root cause confirmed: `create_and_provision_tenant()` returns results with no `initial_admin` key

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := create_and_provision_tenant_fixed(input)
  ASSERT result['initial_admin'] IS NOT NULL
  ASSERT result['initial_admin']['status'] IN ['created', 'existing_user']
  ASSERT userTenantRoleExists(input.email, input.administration, 'Tenant_Admin')
  ASSERT invitationRecordExists(input.email, input.administration)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT create_and_provision_tenant_original(input).tenant == create_and_provision_tenant_fixed(input).tenant
  ASSERT create_and_provision_tenant_original(input).modules == create_and_provision_tenant_fixed(input).modules
  ASSERT create_and_provision_tenant_original(input).chart == create_and_provision_tenant_fixed(input).chart
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many combinations of administration names, emails, module lists, and locales
- It catches edge cases in the idempotent logic (rerun scenarios, existing users)
- It provides strong guarantees that the existing three provisioning steps are unchanged

**Test Plan**: Observe behavior on UNFIXED code first for tenant/module/chart creation, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Tenant Record Preservation**: Verify that for any valid provisioning input, the tenant record in `tenants` table is identical before and after the fix
2. **Module Insertion Preservation**: Verify that for any valid module list, `tenant_modules` rows are identical before and after the fix
3. **Chart of Accounts Preservation**: Verify that for any valid locale, `rekeningschema` rows are identical before and after the fix
4. **SysAdmin UI Without Email Preservation**: Verify that creating a tenant without `initial_admin_email` produces no `user_tenant_roles` rows (same as before)
5. **Idempotent Rerun Preservation**: Verify that running provisioning twice produces the same final state (no duplicates, no errors)

### Unit Tests

- Test `create_initial_admin_user()` with a new Cognito user (mocked): verify Cognito create, `admin_set_user_password(Permanent=True)` called to set status to `CONFIRMED`, `user_tenant_roles` insert, invitation creation, email send
- Test `create_initial_admin_user()` with an existing Cognito user (mocked): verify Cognito tenant update, `user_tenant_roles` insert, tenant-added email, NO `admin_set_user_password` call (user already `CONFIRMED`)
- Test `create_initial_admin_user()` idempotent skip: verify that if `user_tenant_roles` already exists, method returns `'skipped'`
- Test `create_and_provision_tenant()` with `initial_admin_email=None`: verify no user creation step is attempted
- Test `create_and_provision_tenant()` with `initial_admin_email` provided: verify user creation step is called
- Test error handling: verify that user creation failure does not fail overall provisioning
- Test new user status: verify that after `create_initial_admin_user()` for a new user, the Cognito user status is `CONFIRMED` (not `FORCE_CHANGE_PASSWORD`)

### Property-Based Tests

- Generate random valid (administration, email, modules, locale) tuples and verify that after `create_and_provision_tenant()`, the tenant record, modules, and chart are correctly created regardless of whether `initial_admin_email` is provided
- Generate random valid emails and administration names and verify that `create_initial_admin_user()` always produces a `user_tenant_roles` row with `Tenant_Admin` role
- Generate random provisioning inputs and verify idempotency: running twice produces the same final state

### Integration Tests

- Test full SysAdmin UI flow: create tenant with `initial_admin_email`, verify tenant + admin user + invitation + email
- Test full provisioning script flow: provision a signup, verify tenant + admin user + invitation + email + Cognito update + SNS notification
- Test full provisioning API flow: provision a signup, verify tenant + admin user + invitation + email + Cognito update + welcome email + trial plan
- Test SysAdmin UI flow without `initial_admin_email`: verify tenant created, no admin user
- Test rerun scenario: provision twice, verify no duplicate users or errors
