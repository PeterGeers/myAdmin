# Implementation Plan: SES Email Verification

## Overview

Implement tenant-level email verification via AWS SES so invoice emails are sent from the tenant's own verified email address. The implementation covers database schema, backend service layer, API routes, invoice email modifications (sender resolution + branded signature), frontend UI, and integration with tenant provisioning.

## Tasks

- [x] 1. Database schema and core service setup
  - [x] 1.1 Create database migration for `email_verifications` table
    - Create SQL migration file with the `email_verifications` table schema
    - Include columns: id, administration, email, status (ENUM), initiated_at, verified_at, last_checked_at, last_resend_at, created_at, updated_at
    - Add indexes: idx_administration, idx_admin_status, idx_email
    - _Requirements: 1.4, 8.5_

  - [x] 1.2 Implement EmailVerificationService class
    - Create `backend/src/services/email_verification_service.py`
    - Implement constructor with db_manager and boto3 SES client initialization
    - Implement `_validate_email()` method with RFC 5322 basic validation
    - Implement `initiate_verification()` — call SES VerifyEmailIdentity, store pending record
    - Implement `check_status()` — query SES GetIdentityVerificationAttributes, sync DB, return state
    - Implement `resend_verification()` — re-call VerifyEmailIdentity with 60s rate limiting
    - Implement `update_email()` — validate, initiate for new email, mark old as replaced
    - Implement `get_verified_sender()` — fast DB lookup returning verified/email/company_name
    - Implement `mark_expired()` — update status to expired
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.5, 6.2_

  - [x] 1.3 Write property tests for EmailVerificationService
    - **Property 3: SES status mapping correctness** — generate random SES states, verify correct mapping to local status
    - **Property 5: Resend rate limiting** — generate random timestamps, verify accept/reject logic against 60s window
    - **Property 9: Email validation** — generate random strings, verify accept/reject matches RFC 5322 rules
    - **Validates: Requirements 2.2, 2.3, 2.4, 3.4, 5.5**

  - [x] 1.4 Write unit tests for EmailVerificationService
    - Test `initiate_verification`: success path, SES failure path
    - Test `check_status`: each SES state mapping, no-record case
    - Test `resend_verification`: success, rate limited, SES failure
    - Test `update_email`: valid email, invalid email, state transitions
    - Test `get_verified_sender`: verified, pending, failed, expired, no-record
    - Test `mark_expired`: status update
    - Test `_validate_email`: valid/invalid email formats
    - _Requirements: 1.1, 1.2, 1.3, 2.1–2.5, 3.1–3.4, 5.1–5.5_

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. API routes and tenant provisioning integration
  - [x] 3.1 Implement verification API routes
    - Create `backend/src/routes/verification_routes.py` with Blueprint
    - Implement GET `/api/tenant-admin/sender-verification` — return current status
    - Implement POST `/api/tenant-admin/sender-verification/resend` — trigger resend
    - Implement PUT `/api/tenant-admin/sender-verification/email` — update email and initiate verification
    - Apply `@cognito_required(required_permissions=['admin_manage'])` and `@tenant_required()` decorators
    - Register blueprint in app.py
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 3.2 Integrate with TenantProvisioningService
    - Modify `backend/src/services/tenant_provisioning_service.py`
    - Add call to `EmailVerificationService.initiate_verification()` after parameter seeding step
    - Ensure verification failure does not block provisioning (try/except with logging)
    - _Requirements: 1.1, 1.3_

  - [x] 3.3 Write unit tests for verification routes
    - Test permission checks (admin_manage required)
    - Test tenant isolation (only own administration)
    - Test request validation (missing/invalid email in PUT)
    - Test rate limit response (429) on resend
    - _Requirements: 8.1–8.5, 3.4_

- [x] 4. Invoice email sender resolution and error recovery
  - [x] 4.1 Modify InvoiceEmailService for verified sender resolution
    - Modify `backend/src/services/invoice_email_service.py`
    - Before sending, call `EmailVerificationService.get_verified_sender(tenant)`
    - If verified: use tenant email as Source, company name as display name
    - If not verified: use fallback sender with Reply-To set to tenant email
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.2 Implement error recovery with fallback
    - On `MessageRejected` or `MailFromDomainNotVerified` error: retry send with fallback sender
    - Call `mark_expired()` to update verification status
    - Log warning with tenant identifier and email
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 4.3 Write property tests for sender resolution
    - **Property 6: Verified sender resolution** — generate random verified tenants, verify correct sender returned
    - **Property 7: Fallback sender for non-verified tenants** — generate random non-verified states, verify fallback used
    - **Property 10: Error recovery with fallback and expiry** — generate SES error scenarios, verify retry + expiry
    - **Validates: Requirements 4.1, 4.2, 4.3, 5.4, 6.1, 6.2**

  - [x] 4.4 Write unit tests for invoice email modifications
    - Test verified tenant uses tenant email as sender
    - Test non-verified tenant uses fallback with Reply-To
    - Test error recovery retries with fallback
    - Test mark_expired called on send failure
    - _Requirements: 4.1–4.4, 6.1–6.3_

- [x] 5. Email signature builder
  - [x] 5.1 Implement `_build_signature_block` method
    - Add private method to `InvoiceEmailService`
    - Retrieve `zzp_branding.company_name` and `zzp_branding.contact_email` from ParameterService
    - Call `resolve_tenant_logo()` for base64 logo data URI
    - Build HTML signature template with conditional logo inclusion
    - Implement locale-aware greeting ("Met vriendelijke groet," for nl_NL, "Kind regards," for others)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 5.2 Integrate signature block into email composition
    - Modify `_build_locale_body()` to append signature after email body
    - Modify `_build_body()` to append signature after body content
    - Remove existing inline greeting from `_build_nl_body()` and `_build_en_body()` (moved to signature)
    - Handle graceful degradation when ParameterService unavailable
    - _Requirements: 9.1, 9.6_

  - [x] 5.3 Write property tests for signature builder
    - **Property 12: Signature block contains required branding fields** — generate random branding params, verify presence in output HTML
    - **Property 13: Conditional logo inclusion** — generate random logo/no-logo configs, verify img tag presence/absence
    - **Property 14: Locale-aware signature greeting** — generate random locales, verify correct greeting text
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.7**

  - [x] 5.4 Write unit tests for signature builder
    - Test signature with logo and all branding fields
    - Test signature without logo (no broken img tag)
    - Test signature with missing company_name (falls back to tenant identifier)
    - Test signature with missing contact_email (email line omitted)
    - Test Dutch locale greeting
    - Test English/other locale greeting
    - _Requirements: 9.1–9.7_

- [x] 6. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Frontend verification API service and types
  - [x] 7.1 Create TypeScript types and API service
    - Create `frontend/src/types/VerificationTypes.ts` with VerificationStatus and response interfaces
    - Create `frontend/src/services/verificationApi.ts`
    - Implement `getVerificationStatus()` — GET /api/tenant-admin/sender-verification
    - Implement `resendVerification()` — POST /api/tenant-admin/sender-verification/resend
    - Implement `updateSenderEmail(email)` — PUT /api/tenant-admin/sender-verification/email
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 8. Frontend SenderSettingsTab component
  - [x] 8.1 Implement SenderSettingsTab component
    - Create `frontend/src/components/TenantAdmin/SenderSettingsTab.tsx`
    - Display current sender email and verification status badge (pending=yellow, verified=green, failed=red, expired=orange)
    - Implement "Resend Verification" button with 60s cooldown timer
    - Display informational message when status is pending
    - Display fallback sender info when not verified
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.7_

  - [x] 8.2 Implement email update form
    - Add Formik form with Yup email validation schema
    - Submit calls `updateSenderEmail()` and refreshes status display
    - Show inline validation errors and API error toasts
    - _Requirements: 7.5, 7.6_

  - [x] 8.3 Integrate SenderSettingsTab into TenantAdminDashboard
    - Add new tab between "Tenant Info" and "Pivot Views" in the dashboard
    - Wire up tab navigation and lazy loading
    - _Requirements: 7.1_

  - [x] 8.4 Write frontend unit tests for SenderSettingsTab
    - Test component rendering for each status state (pending, verified, failed, expired)
    - Test resend button disabled during cooldown
    - Test email update form validation
    - Test API error handling and toast display
    - _Requirements: 7.1–7.7_

  - [x] 8.5 Write frontend property tests
    - **Property 9 (frontend): Email validation** — generate random strings with fast-check, verify Yup schema matches backend validation rules
    - **Property 14 (frontend): Locale greeting** — generate random locale strings, verify correct greeting selection logic
    - **Validates: Requirements 5.5, 9.7**

- [x] 9. Integration wiring and provisioning hook
  - [x] 9.1 Wire EmailVerificationService into application context
    - Register service in app.py or service registry
    - Ensure proper dependency injection of db_manager
    - Verify SES client configuration uses correct region from environment
    - _Requirements: 1.1, 4.4_

  - [x] 9.2 Write integration tests
    - Test full provisioning flow triggers verification initiation
    - Test API endpoint authentication and authorization
    - Test end-to-end status check flow (API → Service → SES mock → DB → response)
    - _Requirements: 1.1, 8.4, 8.5_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python (Flask, pytest, hypothesis); Frontend uses TypeScript (React, Vitest, fast-check)
- The signature builder reuses existing `resolve_tenant_logo()` — no new logo infrastructure needed
- Verification failure during provisioning is non-blocking by design

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "7.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3"] },
    { "id": 9, "tasks": ["8.4", "8.5", "9.1"] },
    { "id": 10, "tasks": ["9.2"] }
  ]
}
```
