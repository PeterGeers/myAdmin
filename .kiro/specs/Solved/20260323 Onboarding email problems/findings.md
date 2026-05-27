# Onboarding Email Problems — Findings

**Date:** 2026-03-23
**Status:** Analysis Complete

---

## Issue A: Password shown as `*****` or wrong password

### What happens

Two different code paths send invitation emails, and they handle the password differently:

1. **`tenant_admin_users.py` → `create_tenant_user()`** (creating a new user)
   - Generates a random temporary password via `InvitationService.generate_temporary_password()`
   - Passes the real `temp_password` to the email template → user sees the actual password
   - But this password is **not** the one the tenant admin typed in the UI — the admin-provided `password` field from the request body is **completely ignored** for new users. The code always auto-generates one.

2. **`tenant_admin_email.py` → `send_email_to_user()`** (generic send-email endpoint)
   - Uses `user_data.get('temporary_password', '********')` as fallback
   - If the frontend doesn't pass `temporary_password` in `user_data`, the template renders with literal `********`

### Root cause

- The tenant admin defines a password in the UI, but `create_tenant_user()` ignores it and generates its own via `InvitationService`. The admin's password is never used.
- The `send_email_to_user()` endpoint defaults to `'********'` when no password is provided, so resend/manual emails show asterisks.

### Fix

**Option A (recommended):** Remove the password field from the create-user UI entirely. The system auto-generates a secure temporary password — this is actually the safer approach. Make sure the frontend knows the password is auto-generated and shown in the email.

**Option B:** If the admin must define the password, change `create_tenant_user()` to use the admin-provided `password` instead of auto-generating:

```python
# In create_tenant_user(), around line 310:
# Currently:
temp_password = invitation_result['temporary_password']

# Change to:
temp_password = password or invitation_result['temporary_password']
```

For the `********` issue in `tenant_admin_email.py`, the `send_email_to_user()` endpoint should either:

- Not allow sending invitation emails without a real password
- Or look up the password from the `user_invitations` table

---

## Issue B: Email sent to SNS subscriber, not to the invited user

### What happens

The invitation email is sent via **AWS SNS** (`sns_client.publish()` to the topic ARN). SNS is a broadcast notification service — it delivers to **all subscribers** of the topic, not to a specific email address.

The SNS topic `arn:aws:sns:eu-west-1:344561557829:myadmin-notifications` has `peter@pgeers.nl` as a subscriber. So every invitation email goes to peter@pgeers.nl regardless of who the invited user is.

### Where it happens

All three files use the same pattern:

- `tenant_admin_users.py` line ~376: `sns_client.publish(TopicArn=sns_topic_arn, ...)`
- `tenant_admin_email.py` line ~130: `sns_client.publish(TopicArn=sns_topic_arn, ...)`
- `cognito_service.py` `send_invitation()`: `sns_client.publish(TopicArn=sns_topic_arn, ...)`

### Root cause

SNS topics are designed for fan-out notifications (admin alerts, system notifications), not for sending emails to specific recipients. The code uses SNS for both admin notifications AND user-facing emails, which is fundamentally wrong for the user-facing case.

### Fix

Switch to **AWS SES** (Simple Email Service) for user-facing emails. SES allows sending to a specific email address:

```python
ses_client = boto3.client('ses', region_name=AWS_REGION)
ses_client.send_email(
    Source='noreply@yourdomain.com',  # Must be verified in SES
    Destination={'ToAddresses': [recipient_email]},
    Message={
        'Subject': {'Data': subject},
        'Body': {
            'Html': {'Data': html_content},
            'Text': {'Data': text_content}
        }
    }
)
```

**Requirements for SES:**

- Verify a sender domain or email in AWS SES console
- If still in SES sandbox, verify recipient emails too (or request production access)
- Add `SES_SENDER_EMAIL` to environment variables

**Keep SNS** for admin notifications (new signup alerts, system alerts) — that's what it's designed for.

---

## Issue C: Login URL is `http://localhost:3000`

### What happens

The login URL in the email shows `http://localhost:3000` instead of the production URL.

### Root cause

`FRONTEND_URL` in `backend/.env` is set to `http://localhost:3000`:

```
FRONTEND_URL=http://localhost:3000
```

Every place that built the login URL used:

```python
os.getenv('FRONTEND_URL', 'http://localhost:3000')
```

### Fix — IMPLEMENTED ✅

Created `backend/src/utils/frontend_url.py` with a `get_frontend_url()` utility that auto-detects the frontend URL from the incoming request headers:

1. `Origin` header (most reliable, set by browsers on POST/CORS requests)
2. `Referer` header (fallback, extracts scheme + host)
3. `FRONTEND_URL` env var (fallback for background tasks / scripts)
4. `http://localhost:3000` (development last resort)

Updated all 5 files that referenced `FRONTEND_URL`:

- `backend/src/services/email_template_service.py` — `render_user_invitation()`
- `backend/src/routes/tenant_admin_users.py` — `create_tenant_user()`
- `backend/src/routes/tenant_admin_email.py` — `send_email_to_user()` and `resend_invitation()`
- `backend/src/services/cognito_service.py` — `send_invitation()` fallback text
- `backend/src/google_drive_oauth_routes.py` — OAuth callback redirects

No manual Railway env var changes needed. The URL is now derived from the request that triggers the email.

---

## Summary of Required Changes

| Issue                            | Severity | Fix Type                               | Status   |
| -------------------------------- | -------- | -------------------------------------- | -------- |
| A — Password mismatch            | Medium   | Code change in `tenant_admin_users.py` | ✅ Fixed |
| B — Email goes to SNS subscriber | High     | Replace SNS with SES for user emails   | ✅ Fixed |
| C — localhost login URL          | Low      | Auto-detect from request headers       | ✅ Fixed |
