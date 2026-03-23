# SES Email Service — Technical Design

**Status:** Ready for Implementation
**Date:** 2026-03-23

---

## Architecture Overview

```
Current (broken):
  Tenant Admin UI → create_tenant_user() → SNS Topic → All subscribers (peter@pgeers.nl)
                                                        ❌ Invited user never gets email

Target:
  Tenant Admin UI → create_tenant_user() → SES → Invited user's email
                                                  ✅ Direct delivery

  Admin alerts (signup, system) → SNS Topic → Admin subscribers (unchanged)
```

## New Component: SESEmailService

**File:** `backend/src/services/ses_email_service.py`

```python
class SESEmailService:
    """Sends user-facing emails via AWS SES"""

    def __init__(self, region='eu-west-1'):
        self.client = boto3.client('ses', region_name=region)
        self.sender = os.getenv('SES_SENDER_EMAIL', 'support@jabaki.nl')
        self.reply_to = os.getenv('SES_REPLY_TO_EMAIL', self.sender)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str
    ) -> dict:
        """Send email to a specific recipient via SES"""

    def send_invitation(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str
    ) -> dict:
        """Send invitation email (wrapper with invitation-specific logging)"""
```

### SES API Call

```python
response = self.client.send_email(
    Source=f'myAdmin <{self.sender}>',
    Destination={
        'ToAddresses': [to_email]
    },
    Message={
        'Subject': {'Data': subject, 'Charset': 'UTF-8'},
        'Body': {
            'Html': {'Data': html_body, 'Charset': 'UTF-8'},
            'Text': {'Data': text_body, 'Charset': 'UTF-8'}
        }
    },
    ReplyToAddresses=[self.reply_to]
)
```

## Files to Modify

### 1. `tenant_admin_users.py` — `create_tenant_user()`

Replace SNS publish block (~lines 396-420) with:

```python
from services.ses_email_service import SESEmailService
ses = SESEmailService()
ses.send_invitation(
    to_email=email,
    subject=subject,
    html_body=html_content,
    text_body=text_content
)
```

### 2. `tenant_admin_email.py` — `send_email_to_user()` and `resend_invitation()`

Replace both `sns_client.publish()` calls with `SESEmailService.send_email()`.

### 3. `cognito_service.py` — `send_invitation()`

Replace `sns_client.publish()` with `SESEmailService.send_invitation()`.

### 4. Files NOT modified (stay on SNS)

- `aws_notifications.py` — admin/system alerts
- `signup_service.py` — signup admin notifications
- `signup_routes.py` — verification admin notifications

## Environment Variables

| Variable             | Default             | Description                  |
| -------------------- | ------------------- | ---------------------------- |
| `SES_SENDER_EMAIL`   | `support@jabaki.nl` | From address for user emails |
| `SES_REPLY_TO_EMAIL` | (same as sender)    | Reply-to address             |
| `AWS_REGION`         | `eu-west-1`         | Already exists, reused       |

Add to `backend/.env` and `backend/.env.example`.

## AWS SES Setup (Manual Steps)

### Option A: Domain Verification (recommended)

1. Go to AWS SES Console → Verified identities → Create identity
2. Choose "Domain" → enter `jabaki.nl`
3. Add the DNS records (DKIM, SPF) to jabaki.nl's DNS
4. Wait for verification (usually minutes, up to 72h)

### Option B: Email Verification (quick start)

1. Go to AWS SES Console → Verified identities → Create identity
2. Choose "Email address" → enter `support@jabaki.nl`
3. Click verification link in email
4. Note: In sandbox mode, recipient emails must also be verified

### Production Access

- If SES is in sandbox mode, request production access via AWS Console
- Sandbox limits: can only send to verified email addresses
- Production: can send to any email address

## Terraform (Optional)

Add to `infrastructure/ses.tf`:

```hcl
resource "aws_ses_domain_identity" "jabaki" {
  domain = "jabaki.nl"
}

resource "aws_ses_domain_dkim" "jabaki" {
  domain = aws_ses_domain_identity.jabaki.domain
}
```

This is optional — can be done manually via console first, Terraform later.

## Error Handling

```python
try:
    ses.send_invitation(to_email=email, ...)
    invitation_service.mark_invitation_sent(administration=tenant, email=email)
except ClientError as e:
    error_code = e.response['Error']['Code']
    if error_code == 'MessageRejected':
        logger.error(f"SES rejected email to {email}: {e}")
    elif error_code == 'MailFromDomainNotVerifiedException':
        logger.error(f"Sender domain not verified: {e}")
    # Don't fail user creation
    invitation_service.mark_invitation_failed(
        administration=tenant, email=email, error_message=str(e)
    )
```

## Security Considerations

- SES uses existing AWS IAM credentials (same as SNS) — no new credentials needed
- Temporary passwords are sent only to the intended recipient (not broadcast)
- `Source` address is fixed to `support@jabaki.nl` — cannot be spoofed by API callers
- Rate limiting: SES has built-in sending limits (start at 200/day in sandbox, 50k+/day in production)

## Testing Strategy

- Unit tests: mock `boto3.client('ses')` and verify correct parameters
- Integration test: send test email to verified address in sandbox
- Verify existing SNS admin notifications still work after changes
