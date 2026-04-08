# Root Cause Analysis — Onboarding Issues

## Issue 1: Forgot Password — Cognito doesn't send reset link

### Symptom

User clicks "Forgot Password" but never receives the reset email.

### Root Cause

Cognito has a temporary password expiry (default: 7 days). If a user was created via `admin_create_user` with a temporary password and never logged in to set a permanent password within that window, their account enters `FORCE_CHANGE_PASSWORD` status and eventually expires.

When a user in this state tries "Forgot Password", Cognito may reject the request because the user never completed the initial authentication flow. The `forgot_password` API requires the user to be in `CONFIRMED` status — users stuck in `FORCE_CHANGE_PASSWORD` can't use it.

### How to verify

In AWS Console → Cognito → User Pool → Users, check the user's status:

- `CONFIRMED` → forgot password should work
- `FORCE_CHANGE_PASSWORD` → forgot password won't work
- `RESET_REQUIRED` → user needs admin intervention

### Fix options

**Case A — Confirmed user doesn't receive reset email:**
The root cause is `email_sending_account = "COGNITO_DEFAULT"` in `infrastructure/cognito.tf`. Reset emails are sent from `no-reply@verificationemail.com` which often lands in spam. Fix: switch to SES (see Terraform change below).

**Case B — User stuck in FORCE_CHANGE_PASSWORD (expired temp password):**
A "Resend Invitation" button exists in Tenant Admin → User Management (`UserManagement.tsx` line 751). It calls `/api/tenant-admin/resend-invitation` which:

1. Generates a new temporary password via `invitation_service.resend_invitation()`
2. Calls `admin_set_user_password` in Cognito (with `Permanent=False`)
3. Renders the invitation email template with the new password
4. Sends via SES to the user

Email IS sent. Verified in code (`tenant_admin_email.py` lines 340-355).

Two minor issues found:

- The password is set as temporary (`Permanent=False`), so the user is back in `FORCE_CHANGE_PASSWORD` with a new expiry. If they don't log in in time, they're stuck again. Consider using `Permanent=True` and forcing password change on first login via the app instead.
- If SES fails to send, the endpoint still returns `success: True` to the frontend (line 361). The Tenant Admin thinks it worked but the user got no email. Should return the SES failure to the caller.

The user cannot self-service this — a Tenant Admin must click the button. This is acceptable (admin action by design).

**Quickest fix for Case A — Terraform change (no code changes):**

```hcl
email_configuration {
  email_sending_account  = "DEVELOPER"
  source_arn             = "arn:aws:ses:eu-west-1:344561557829:identity/support@jabaki.nl"
  from_email_address     = "support@jabaki.nl"
}
```

This makes Cognito's built-in emails (password reset, verification codes) come from `support@jabaki.nl` — better deliverability, no spam folder issues, and the 50/day limit is removed.

---

## Issue 2: User deleted from one tenant — loses access to all tenants

### Symptom

A Tenant Admin removes a user from their tenant. The user can no longer access any tenant, even ones they're still subscribed to.

### Root Cause

Found in `tenant_admin_users.py` lines 605-611. The delete logic is:

```python
if len(target_user_tenants) > 1:
    # Remove just this tenant from the list
    updated_tenants = [t for t in target_user_tenants if t != tenant]
    cognito_client.admin_update_user_attributes(...)
else:
    # User only belongs to this tenant, delete completely
    cognito_client.admin_delete_user(...)
```

This logic is correct in principle — it only deletes the Cognito user if they have no remaining tenants. However, there's a potential bug:

The `custom:tenants` attribute parsing could fail. If `get_user_attribute` returns `None` or an empty list (e.g., due to a malformed JSON string in the attribute), then `len(target_user_tenants)` would be 0 or the check would fail, and the code would fall through to the `else` branch — deleting the user entirely.

Also: the `remove_tenant_from_user` method in `cognito_service.py` (line 485) has the same logic but is a separate code path. The tenant admin route uses the direct Cognito client instead of `cognito_service.py`, so the two implementations could diverge.

### How to verify

1. Check the audit log for the exact delete operation
2. In Cognito console, search for the user — if they're gone, they were fully deleted
3. Check if the user's `custom:tenants` attribute was properly formatted JSON before deletion

### Fix options

1. Add a safety check: Before deleting, log the current tenants list and verify it's truly empty/single
2. Use cognito_service.py consistently: The `remove_tenant_from_user` method has the same logic — consolidate to one code path
3. Never delete Cognito users from tenant admin: Only remove the tenant from the attribute. Let a SysAdmin handle full user deletion
4. Add a confirmation step: Show the user's other tenants before deletion and warn accordingly

---

## Issue 3: Existing Cognito user — new tenant created but no email received

### Symptom

An existing user in the Cognito user pool gets a new tenant assigned. They say they didn't receive an email notification.

### Root Cause

Found in `tenant_admin_users.py` lines 265-297. When a user already exists in Cognito and a new tenant is added:

```python
if user_exists:
    # Add tenant to their list
    cognito_client.admin_update_user_attributes(...)
    # Add to groups
    # ...
    return jsonify({
        'success': True,
        'message': f'User {email} added to tenant {tenant}',
        'existing_user': True
    })
```

No email is sent. The invitation email logic (SES send) only runs in the `else` branch (new user creation, lines 380-440). When an existing user gets a new tenant, the code silently adds the tenant and returns success — but the user is never notified.

### Fix

Add an email notification in the `user_exists` branch. It doesn't need to include a temporary password (user already has credentials), but should inform them:

- They've been added to a new tenant
- Which tenant
- A link to log in

This could use a different email template (e.g., `tenant_added` instead of `user_invitation`).

---

## Cross-Cutting Issues

### No email delivery tracking

There's no way to see which emails were sent to a user. The SES send result is logged to stdout (`print(f"AUDIT: ...")`) but not stored in a queryable table.

Recommendation: Store email send events in a table:

```
email_log:
  id, recipient, email_type (invitation/password_reset/tenant_added),
  tenant, status (sent/failed/bounced), ses_message_id,
  created_at, error_message
```

This would answer "how can we see which emails have been sent to a user" directly.

### Cognito vs SES email confusion

The system uses `MessageAction='SUPPRESS'` when creating users (line 342 in tenant_admin_users.py), which tells Cognito NOT to send its built-in welcome email. Instead, the app sends its own email via SES. This is intentional (custom branded emails), but it means:

- Cognito's email delivery logs won't show anything
- Only SES delivery logs (in AWS Console → SES → Sending Statistics) will show email activity
- If SES fails silently, the user gets no email and there's no retry

### Password reset flow

The "Forgot Password" flow uses Cognito's built-in `forgot_password` → `confirm_forgot_password` flow, which sends emails through Cognito (not SES). This means:

- Invitation emails go through SES (custom templates)
- Password reset emails go through Cognito (default templates)
- Two different email delivery systems with different monitoring

---

## Action Plan

### What to fix (3 concrete actions)

- [x] **Issue 3 — Add email for existing user + new tenant** (done)
      Added email notification in the `user_exists` branch of `tenant_admin_users.py`. Sends via SES with subject "You've been added to {tenant} in myAdmin". Uses `tenant_added` template if available, falls back to plain text. No password included (user already has credentials). Email failure doesn't block the tenant assignment.

  File changed: `backend/src/routes/tenant_admin_users.py`

- [x] **Issue 1 — Resend invitation SES failure handling** (done during RCA)
      The "Resend Invitation" button already exists in Tenant Admin. During analysis, two bugs were found and fixed:
  1. `tenant_admin_email.py`: If SES failed to send the email, the endpoint returned `success: true` — admin thought it worked but user got nothing. Fixed: now returns `success: false` with `email_failed: true` and the `temporary_password` in the response.
  2. `UserManagement.tsx`: Added handling for the `email_failed` response — copies temp password to clipboard and opens the admin's email client via `mailto:` link with the password pre-filled, so the admin can send it manually.

- [x] **Issue 1 — Switch Cognito to SES email sender** (Quick, Terraform only)
      Changed `email_sending_account` from `COGNITO_DEFAULT` to `DEVELOPER` in `infrastructure/cognito.tf`. Password reset emails now come from `myAdmin <support@jabaki.nl>` instead of `no-reply@verificationemail.com`. Run `terraform apply` in the `infrastructure/` folder to deploy.

- [x] **Issue 2 — Safety check + consolidate delete logic** (Medium, 2 hours)
      Two things done together:
  1. Added safety guard in `cognito_service.py`'s `remove_tenant_from_user()` — validates `custom:tenants` is a proper list before deciding to delete vs remove-tenant. If malformed, raises `ValueError` and refuses to delete. Logs current tenants before and after removal.
  2. Refactored `tenant_admin_users.py`'s `delete_tenant_user()` to delegate to `cognito_service.remove_tenant_from_user()` instead of duplicating the logic. One code path, not two. Route now catches `ValueError` (safety guard) separately from `ClientError` (AWS).

  Files changed: `backend/src/services/cognito_service.py`, `backend/src/routes/tenant_admin_users.py`

### Code changes already made (during RCA — to be reviewed and pushed)

| File                                                     | Change                                                               |
| -------------------------------------------------------- | -------------------------------------------------------------------- |
| `backend/src/routes/tenant_admin_email.py`               | Resend invitation: return SES failure to frontend with temp password |
| `frontend/src/components/TenantAdmin/UserManagement.tsx` | Handle `email_failed` response: clipboard + mailto fallback          |

These changes are local only, not pushed to production yet.

### Nice to have (separate improvements, not blocking)

- [x] **Email delivery tracking via SES → SNS** (Medium, 3-4 hours) — Implemented email logging for all SES emails. Every `send_email` / `send_invitation` call now logs to an `email_log` table with recipient, type, tenant, SES message ID, and status. SNS webhook at `/api/webhooks/ses` receives delivery/bounce/complaint notifications and updates the status. Query endpoint at `GET /api/email-log` (SysAdmin: all tenants, Tenant Admin: own tenant only).

  Deployment steps:
  1. Run `backend/src/migrations/create_email_log_table.sql` against both prod and test databases
  2. In AWS Console → SES → Configuration Sets → create `myadmin-emails` → add SNS event destination for Sends, Deliveries, Bounces, Complaints
  3. Subscribe the backend webhook URL (`https://your-backend/api/webhooks/ses`) to the SNS topic
  4. Deploy backend

  Files created: `email_log_service.py`, `email_log_routes.py`, `create_email_log_table.sql`
  Files changed: `ses_email_service.py`, `tenant_admin_email.py`, `tenant_admin_users.py`, `cognito_service.py`, `sysadmin_provisioning.py`, `app.py`

- [x] **Consistent email system** (Low, 4-6 hours) — Moved password reset emails from Cognito to our own SES flow. The frontend now calls `POST /api/auth/forgot-password` and `POST /api/auth/confirm-reset` instead of Amplify's `resetPassword`/`confirmResetPassword`. The backend generates a 6-digit code, stores it in `password_reset_codes` table (10-min expiry, max 3 attempts), sends it via SES (tracked in `email_log`), and on confirmation uses `admin_set_user_password` to set the new password. All emails now go through one system (SES) and one log table (`email_log`).

  Deployment steps:
  1. Run `backend/src/migrations/create_password_reset_codes_table.sql` against both databases
  2. Deploy backend (new `auth_routes.py` blueprint)
  3. Deploy frontend (Login.tsx now calls backend instead of Amplify)

  Files created: `auth_routes.py`, `create_password_reset_codes_table.sql`
  Files changed: `Login.tsx` (removed Amplify resetPassword/confirmResetPassword), `app.py` (registered auth_bp)

### Moved to separate spec

- **Issue 4 — Per-tenant roles**: Architecture change, tracked at `.kiro/specs/Common/per-tenant-roles/ideas.md`


A question 
MessageRejected: Email address is not verified. The following identities failed the check in region EU-WEST-1: jose.polman@gmail.com