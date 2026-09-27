# Requirements Document

## Introduction

This feature enables tenants to verify their own email address via AWS SES during onboarding, so that invoice emails are sent FROM the tenant's verified email address instead of the generic "myAdmin <support@jabaki.nl>". This improves professionalism and deliverability for tenant communications with their clients.

The system uses SES individual email address verification (Option A — not domain verification) and provides a graceful fallback to the current sender when verification is incomplete.

## Glossary

- **Verification_Service**: The backend service responsible for initiating SES email identity verification, checking verification status, and managing verification state per tenant.
- **Invoice_Email_Service**: The existing service that composes and sends invoice emails with PDF attachments via SES.
- **SES_Email_Service**: The existing low-level service that sends emails through AWS SES.
- **Tenant_Provisioning_Service**: The existing service that handles tenant onboarding (creating tenant records, modules, chart of accounts, admin user).
- **Sender_Settings_UI**: The frontend component in the tenant admin settings page where tenants can view and manage their sender email verification status.
- **Tenant_Email**: The email address a tenant has registered as their business contact email, intended to be used as the From address for outgoing invoice emails.
- **Verification_Status**: One of: `pending`, `verified`, `failed`, `expired`. Tracks the current state of a tenant's email verification with SES.
- **Fallback_Sender**: The default system sender "myAdmin <support@jabaki.nl>" used when a tenant's email is not verified.

## Requirements

### Requirement 1: Trigger Email Verification During Onboarding

**User Story:** As a system administrator, I want the system to automatically initiate SES email verification for the tenant's contact email during onboarding, so that the tenant can start using their own email as the sender address as soon as they confirm.

#### Acceptance Criteria

1. WHEN a new tenant is provisioned, THE Verification_Service SHALL call SES VerifyEmailIdentity with the tenant's contact_email address.
2. WHEN the SES VerifyEmailIdentity API call succeeds, THE Verification_Service SHALL store a verification record with status `pending` for the tenant.
3. IF the SES VerifyEmailIdentity API call fails, THEN THE Verification_Service SHALL log the error and store a verification record with status `failed`, without blocking the overall provisioning process.
4. THE Verification_Service SHALL store the verification record in the database with the tenant's administration identifier, the email address, the verification status, and a timestamp.

### Requirement 2: Check Verification Status

**User Story:** As a tenant administrator, I want to check whether my email has been verified by SES, so that I know when invoice emails will start using my own address.

#### Acceptance Criteria

1. WHEN a tenant administrator requests the verification status, THE Verification_Service SHALL query SES GetIdentityVerificationAttributes for the tenant's email address.
2. WHEN SES reports the email as verified, THE Verification_Service SHALL update the stored verification status to `verified`.
3. WHEN SES reports the email as pending, THE Verification_Service SHALL keep the stored verification status as `pending`.
4. WHEN SES reports the email as failed, THE Verification_Service SHALL update the stored verification status to `failed`.
5. THE Verification_Service SHALL return the current verification status, the email address, and the timestamp of the last status check.

### Requirement 3: Resend Verification Email

**User Story:** As a tenant administrator, I want to resend the SES verification email, so that I can complete verification if the original email was lost or expired.

#### Acceptance Criteria

1. WHEN a tenant administrator requests a verification resend, THE Verification_Service SHALL call SES VerifyEmailIdentity with the tenant's stored email address.
2. WHEN the resend succeeds, THE Verification_Service SHALL update the verification record timestamp and set status to `pending`.
3. IF the resend fails, THEN THE Verification_Service SHALL return an error message describing the failure.
4. THE Verification_Service SHALL enforce a rate limit of one resend request per 60 seconds per tenant to prevent abuse.

### Requirement 4: Use Verified Email as Invoice Sender

**User Story:** As a tenant, I want my invoice emails to be sent from my own verified email address, so that my clients see my business email as the sender.

#### Acceptance Criteria

1. WHEN sending an invoice email AND the tenant's email verification status is `verified`, THE Invoice_Email_Service SHALL use the tenant's verified email as the From address.
2. WHEN sending an invoice email AND the tenant's email verification status is `verified`, THE Invoice_Email_Service SHALL use the tenant's company name as the From display name.
3. WHILE the tenant's email verification status is NOT `verified`, THE Invoice_Email_Service SHALL use the Fallback_Sender as the From address and set the Reply-To header to the tenant's email.
4. THE Invoice_Email_Service SHALL check the verification status from the database before each send operation.

### Requirement 5: Handle Email Address Changes

**User Story:** As a tenant administrator, I want to update my sender email address, so that I can use a different business email for invoice communications.

#### Acceptance Criteria

1. WHEN a tenant administrator updates their sender email address, THE Verification_Service SHALL call SES VerifyEmailIdentity with the new email address.
2. WHEN a new email address is submitted, THE Verification_Service SHALL set the verification status to `pending` for the new address.
3. WHEN a new email address is verified, THE Verification_Service SHALL mark the previous email address record as `replaced`.
4. WHILE the new email address is not yet verified, THE Invoice_Email_Service SHALL continue using the Fallback_Sender.
5. THE Verification_Service SHALL validate that the new email address is a well-formed email address before initiating verification.

### Requirement 6: Handle Verification Expiry

**User Story:** As a system, I want to detect when a previously verified email is no longer valid in SES, so that the system falls back gracefully and notifies the tenant.

#### Acceptance Criteria

1. WHEN the Invoice_Email_Service attempts to send from a verified tenant email AND SES returns a "MessageRejected" or "MailFromDomainNotVerified" error, THE Invoice_Email_Service SHALL retry the send using the Fallback_Sender.
2. WHEN a send failure indicates the tenant's email is no longer verified, THE Verification_Service SHALL update the verification status to `expired`.
3. WHEN the verification status changes to `expired`, THE Verification_Service SHALL log a warning with the tenant identifier and email address.

### Requirement 7: Tenant Admin Sender Settings UI

**User Story:** As a tenant administrator, I want a settings page where I can see my sender email verification status and manage it, so that I have full visibility and control over my invoice sender identity.

#### Acceptance Criteria

1. THE Sender_Settings_UI SHALL display the current sender email address and its verification status.
2. THE Sender_Settings_UI SHALL display a visual indicator showing whether the status is `pending`, `verified`, `failed`, or `expired`.
3. WHEN the status is `pending` or `failed` or `expired`, THE Sender_Settings_UI SHALL display a "Resend Verification" button.
4. WHEN the status is `pending`, THE Sender_Settings_UI SHALL display an informational message explaining that the tenant should check their inbox for the SES verification email.
5. THE Sender_Settings_UI SHALL provide a form to update the sender email address.
6. WHEN the tenant submits a new email address, THE Sender_Settings_UI SHALL display the updated status after the verification request completes.
7. THE Sender_Settings_UI SHALL display the Fallback_Sender information when the tenant's email is not verified, explaining that invoice emails are currently sent from the system address.

### Requirement 8: API Endpoints for Email Verification Management

**User Story:** As a frontend application, I want API endpoints to manage email verification, so that the Sender_Settings_UI can interact with the backend.

#### Acceptance Criteria

1. THE Verification_Service SHALL expose a GET endpoint that returns the current verification status for the authenticated tenant.
2. THE Verification_Service SHALL expose a POST endpoint that triggers a verification resend for the authenticated tenant.
3. THE Verification_Service SHALL expose a PUT endpoint that updates the sender email address and initiates verification for the authenticated tenant.
4. THE Verification_Service SHALL require `admin_manage` permission for all verification management endpoints.
5. THE Verification_Service SHALL enforce tenant isolation so that a tenant can only view and manage verification for their own administration.

### Requirement 9: Branded Email Signature

**User Story:** As a ZZP freelancer, I want my invoice emails to include a professional signature with my company name, email address, and logo, so that my clients receive a branded and trustworthy communication.

#### Acceptance Criteria

1. WHEN composing an invoice email, THE Invoice_Email_Service SHALL append a signature block at the bottom of the HTML email body.
2. THE signature block SHALL include the tenant's company name as retrieved from the `zzp_branding.company_name` parameter.
3. THE signature block SHALL include the tenant's contact email address as retrieved from the `zzp_branding.contact_email` parameter.
4. WHEN the tenant has a branding logo configured (stored in S3 via the logo resolver), THE signature block SHALL include the logo as an inline base64-encoded image.
5. IF the tenant does not have a branding logo configured, THEN THE signature block SHALL render without a logo image, displaying only the company name and email.
6. THE signature block SHALL be visually separated from the email body by a horizontal rule or spacing, following a consistent HTML template.
7. THE signature block SHALL be locale-aware: using "Met vriendelijke groet," for Dutch (nl_NL) and "Kind regards," for English and other locales.
