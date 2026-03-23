# SES Email Service — Tasks

**Status:** In Progress (Phases 1-3 complete, 4-5 remaining)
**Date:** 2026-03-23

---

## Phase 1: AWS SES Setup (Manual)

- [x] Verify `jabaki.nl` domain in AWS SES Console (eu-west-1)
- [x] Add DNS records — TXT (`_amazonses`) + 3 DKIM CNAMEs at Squarespace
- [x] Domain verification: Success, DKIM verification: Success
- [x] Test email sent from `support@jabaki.nl` via SES — delivered successfully

## Phase 2: SES Email Service Implementation

- [x] Create `backend/src/services/ses_email_service.py` with `SESEmailService` class
- [x] Add `SES_SENDER_EMAIL` and `SES_REPLY_TO_EMAIL` to `backend/.env.example`
- [x] Add `SES_SENDER_EMAIL=support@jabaki.nl` to `backend/.env`

## Phase 3: Migrate User-Facing Emails from SNS to SES

- [x] `tenant_admin_users.py` — `create_tenant_user()`: replaced SNS with SES
- [x] `tenant_admin_email.py` — `send_email_to_user()`: replaced SNS with SES
- [x] `tenant_admin_email.py` — `resend_invitation()`: replaced SNS with SES
- [x] `cognito_service.py` — `send_invitation()`: replaced SNS with SES
- [x] Verified SNS code in `aws_notifications.py` and `signup_service.py` is NOT touched

## Phase 4: Testing

- [x] Create `backend/tests/unit/test_ses_email_service.py` — 14 tests, all passing
- [x] Run existing tests to confirm nothing is broken — 44 signup tests pass
- [x] Manual test: create a user via tenant admin UI and verify email arrives at the invited user's address

## Phase 5: Environment & Deployment

- [x] Add `SES_SENDER_EMAIL=support@jabaki.nl` to Railway backend service env vars
- [x] Deploy to Railway
- [ ] Send test invitation email from production
- [ ] Verify email arrives at invited user's address (not SNS subscriber)
- [ ] Verify admin SNS notifications still work

## Phase 6: Documentation & Cleanup

- [x] Update `findings.md` — mark Issue B as fixed
- [x] Update `backend/.env.example` with SES variables
- [ ] Optional: add `infrastructure/ses.tf` for Terraform management
