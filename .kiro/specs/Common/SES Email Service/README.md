# SES Email Service

Replace AWS SNS with AWS SES for user-facing emails (invitations, password resets). SNS stays for admin notifications.

## Problem

Invitation emails are sent via SNS topic → broadcast to all subscribers (peter@pgeers.nl) instead of the invited user. This has been a known issue since 2026-02-10.

## Solution

New `SESEmailService` that sends emails directly to the recipient via AWS SES, using `support@jabaki.nl` as sender. Replies go to jabaki.nl → forwarded to peter@pgeers.nl.

## Documents

| Document                           | Audience                |
| ---------------------------------- | ----------------------- |
| [requirements.md](requirements.md) | Product / stakeholders  |
| [design.md](design.md)             | Developers              |
| [tasks.md](tasks.md)               | Implementation tracking |

## Key Files

- `backend/src/services/ses_email_service.py` (new)
- `backend/src/routes/tenant_admin_users.py` (modify)
- `backend/src/routes/tenant_admin_email.py` (modify)
- `backend/src/services/cognito_service.py` (modify)

## Prerequisites

- AWS SES: verify `jabaki.nl` domain or `support@jabaki.nl` email
- SES production access (if still in sandbox)
