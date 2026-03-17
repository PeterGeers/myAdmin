### ⚠️ Backend Dependency: Trial Signup API (myAdmin App)

This is a parallel workstream in the myAdmin app repo (Flask backend). The website signup form cannot function without these endpoints.

**Phase 1 — Launch MVP (manual onboarding):**

1. Build `POST /api/signup` endpoint:
   - Validate input (see wireframe for field specs)
   - Create user in AWS Cognito user pool
   - Store signup request in `pending_signups` table (Railway DB)
   - Send verification email via AWS SES/SNS
   - Return 201 with userId
2. Build `POST /api/signup/verify` endpoint:
   - Validate email verification token from Cognito
   - Mark signup as verified in `pending_signups`
   - Notify admin (email to peter@jabaki.nl) that a new signup needs provisioning
   - Return redirect URL
3. Build `POST /api/signup/resend` endpoint:
   - Resend Cognito verification email
   - Rate limit: 1 per 60 seconds

At this stage, tenant provisioning is manual — you receive the notification and run a script or manually set up the tenant.
What has to be done after sign-up. 
- User has to be given access to 
-- Cognito has to be filled with admistration
-- MySQL
--- tenant_config
--- tenant_credentials
--- tenant_modules
--- tenant_template_config

-- User manual
-- basic setup data
--- General ledger template  
--- Purpose definitions
--- Templatefiles as examples
--- 


**Phase 2 — Automated provisioning (post-launch):**

1. Build a tenant provisioning service/script that:
   - Creates tenant schema/records in Railway DB
   - Sets up default configuration (trial plan, 2-month expiry)
   - Optionally creates Google Drive folder structure or S3 bucket
   - Sends welcome/onboarding email
2. Trigger provisioning automatically after email verification (background job or Cognito post-confirmation Lambda)
3. Build `pending_signups` → `tenants` promotion flow

**API contract**: See `.kiro/specs/Website/wireframes/trial-signup.md` for full request/response specs.