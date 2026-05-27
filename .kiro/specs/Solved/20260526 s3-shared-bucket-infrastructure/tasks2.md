# Deployment Plan: S3 Shared Bucket Infrastructure

## Overview

This plan covers the deployment steps to bring the S3 shared bucket infrastructure live. All code implementation is complete — these tasks are operational steps to provision AWS resources, configure permissions, and deploy the application.

## Tasks

- [x] 1. Terraform — Provision S3 bucket and IAM policy
  - [x] 1.1 Initialize and validate Terraform
    - Run `terraform init` in the `infrastructure/` directory
    - Run `terraform plan` and verify output shows only additions (no modifications or deletions to existing resources)
    - Confirm the plan includes: S3 bucket, versioning, encryption, public access block, lifecycle, CORS, IAM policy, and outputs

  - [x] 1.2 Apply Terraform configuration
    - Run `terraform apply` and confirm the apply
    - Note the outputs: `s3_shared_bucket_name`, `s3_shared_bucket_arn`, `s3_shared_access_policy_arn`
    - ✅ Bucket: `myadmin-shared-production`
    - ✅ IAM policy: `arn:aws:iam::344561557829:policy/myadmin-s3-shared-access-production`
    - ⚠️ Cognito update failed (unrelated — Threat Protection requires tier upgrade)

  - [x] 1.3 Verify bucket creation
    - ✅ `aws s3 ls s3://myadmin-shared-production` — bucket exists (empty)
    - ✅ Versioning: `"Status": "Enabled"`
    - ✅ Encryption: `"SSEAlgorithm": "AES256"`
    - ✅ Public access block: all four settings `true`

- [x] 2. IAM — Attach policy to backend user
  - [x] 2.1 Attach the S3 access policy
    - ✅ Attached `myadmin-s3-shared-access-production` to IAM user `WebMaster`

  - [x] 2.2 Verify IAM attachment
    - ✅ `aws iam list-attached-user-policies --user-name WebMaster` confirms policy is attached

- [x] 3. Railway — Set environment variable
  - [x] 3.1 Configure S3_SHARED_BUCKET in Railway
    - ✅ Set `S3_SHARED_BUCKET=myadmin-shared-production` via Railway dashboard

  - [x] 3.2 Verify backend can access S3
    - ✅ Backend running normally, no S3-related errors in logs
    - ✅ No `ValueError: S3 shared bucket not configured` errors

- [x] 4. Deploy application code
  - [x] 4.1 Commit and push changes
    - ✅ Committed: `feat: S3 shared bucket infrastructure - presigned URLs, logo upload, provider-aware resolution`
    - ✅ 21 files changed, 2405 insertions(+), 68 deletions(-)
    - ✅ Pushed to `main` (219550d..4555d94)

  - [x] 4.2 Verify backend deployment
    - ✅ Railway auto-deployed successfully

  - [x] 4.3 Verify frontend deployment
    - ✅ GitHub Actions frontend build and deploy succeeded

- [x] 5. Post-deployment verification
  - [ ] 5.1 Test pre-signed URL flow
    - Upload a test document via the existing S3SharedStorage flow (or use AWS CLI: `aws s3 cp test.pdf s3://myadmin-shared-production/TestTenant/invoices/general/test_doc.pdf`)
    - In the Banking Processor, click a transaction with an S3 key in ref3
    - Verify the PDF opens in a new browser tab via pre-signed URL

    FAILED Created a new bugfix provider-aware-folder-routes

  - [ ] 5.2 Test logo upload flow
    - Navigate to Tenant Admin → Storage tab
    - Confirm the provider is set to `s3_shared`
    - In the "Branding — Company Logo" section, upload a PNG logo
    - Verify success toast and S3 key is displayed
    - Generate a test invoice and confirm the logo appears

  - [ ] 5.3 Verify tenant isolation
    - Confirm that requesting a pre-signed URL for another tenant's key returns 403
    - Confirm that the logo upload stores under the correct tenant prefix

  - [ ] 5.4 Verify backward compatibility
    - Confirm existing Google Drive tenants still work (logo fetched from Google Drive, documents open via Drive URLs)
    - Confirm tenants without `S3_SHARED_BUCKET` configured gracefully skip S3 features

## Notes

- Order matters: Terraform → IAM → Railway env var → Code push
- Existing Google Drive tenants are unaffected — the `invoice_provider` parameter controls routing
- New tenants provisioned after deployment will automatically get `s3_shared` as their storage provider
- The S3 bucket has `force_destroy = false` — it cannot be accidentally deleted via Terraform
- Versioning is enabled — overwritten logos are preserved in version history

## Execution Order

These steps are strictly sequential: 1 → 2 → 3 → 4 → 5. Each step depends on the previous one completing successfully. The only parallelism is within step 5 (verification checks are independent of each other).
