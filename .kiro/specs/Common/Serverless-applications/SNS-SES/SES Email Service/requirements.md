# SES Email Service — Requirements

**Status:** Ready for Implementation
**Date:** 2026-03-23
**Related:** `.kiro/Issues and bug fixes/20260323 Onboarding email problems/findings.md` (Issue B)
**Related:** `.kiro/Issues and bug fixes/20260210 1301 SNS Mail service.md`

---

## Problem Statement

User-facing emails (invitations, password resets) are currently sent via AWS SNS, which is a broadcast notification service. SNS delivers to all topic subscribers (peter@pgeers.nl), not to the intended recipient. This means:

- Invited users never receive their invitation email
- The tenant admin (SNS subscriber) receives all invitation emails instead
- Passwords are exposed to the wrong person

## User Stories

### US-1: Direct Email Delivery

As a tenant admin, I want invitation emails to be delivered directly to the invited user's email address, so that they receive their login credentials.

**Acceptance Criteria:**

- Email is delivered to the exact email address specified in the invitation
- Email is NOT broadcast to SNS topic subscribers
- Email contains the correct temporary password, login URL, and tenant name

### US-2: Professional Sender Identity

As a system owner, I want emails to be sent from `support@jabaki.nl`, so that replies go to my support mailbox and the emails look professional.

**Acceptance Criteria:**

- From address is `support@jabaki.nl`
- Reply-to is `support@jabaki.nl`
- Replies are received at jabaki.nl and forwarded to peter@pgeers.nl

### US-3: HTML Email Support

As a user receiving an invitation, I want the email to be well-formatted HTML, so that it's easy to read and looks professional.

**Acceptance Criteria:**

- Email is sent as multipart (HTML + plain text fallback)
- Existing HTML and TXT templates are used
- Email renders correctly in major email clients

### US-4: Admin Notifications Unchanged

As a system admin, I want to keep receiving admin notifications (signup alerts, system alerts) via SNS, so that the existing notification system is not disrupted.

**Acceptance Criteria:**

- SNS continues to work for admin/system notifications
- Only user-facing emails move to SES
- `AWSNotificationService` in `aws_notifications.py` is untouched

### US-5: Graceful Fallback

As a developer, I want the email service to handle failures gracefully, so that user creation doesn't fail if email sending fails.

**Acceptance Criteria:**

- SES failures are logged but don't block user creation
- Invitation status is marked as 'failed' if email fails
- Admin can resend invitation later

## Functional Requirements

### FR-1: SES Email Service

- New `SESEmailService` class in `backend/src/services/ses_email_service.py`
- Sends emails via AWS SES `send_email` or `send_raw_email` API
- Supports HTML + plain text multipart messages
- Configurable sender address via `SES_SENDER_EMAIL` env var (default: `support@jabaki.nl`)

### FR-2: Migration of User-Facing Emails

Replace SNS with SES in these locations:

- `tenant_admin_users.py` — `create_tenant_user()` invitation email
- `tenant_admin_email.py` — `send_email_to_user()` and `resend_invitation()`
- `cognito_service.py` — `send_invitation()` method

### FR-3: Keep SNS for Admin Notifications

These stay on SNS (no changes):

- `aws_notifications.py` — all admin/system alerts
- `signup_service.py` — signup and verification admin notifications

## Non-Functional Requirements

### NFR-1: AWS SES Setup

- Verify `jabaki.nl` domain in AWS SES (or at minimum verify `support@jabaki.nl`)
- Request SES production access if still in sandbox mode
- Region: `eu-west-1` (same as existing AWS services)

### NFR-2: Environment Configuration

- `SES_SENDER_EMAIL` env var (default: `support@jabaki.nl`)
- `SES_REPLY_TO_EMAIL` env var (optional, defaults to sender)
- `AWS_REGION` already exists and is reused

### NFR-3: Security

- No credentials in code — uses existing AWS IAM/boto3 auth
- Email content follows existing template system
- Temporary passwords are only sent to the intended recipient

## Out of Scope

- Email tracking / open rates / click tracking
- Bounce handling / complaint processing (can be added later)
- Custom per-tenant sender addresses
- Email queue / retry mechanism (SES handles retries internally)
- Changes to the email templates themselves (content stays the same)
- Changes to the signup flow (already correct — uses Cognito for verification, SNS for admin alerts)

## Success Criteria

1. Invitation emails arrive in the invited user's inbox (not the SNS subscriber's)
2. Emails come from `support@jabaki.nl`
3. Existing admin notifications via SNS continue to work
4. All existing tests pass
5. New tests cover SES email sending
