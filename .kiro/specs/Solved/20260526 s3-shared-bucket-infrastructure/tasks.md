# Implementation Plan: S3 Shared Bucket Infrastructure

## Overview

This plan provisions the AWS S3 infrastructure (Terraform), adds environment variable configuration, implements a pre-signed URL download endpoint, a logo upload endpoint, a provider-aware logo resolver, updates the S3 key structure, and wires the frontend to open S3-stored documents via pre-signed URLs.

## Tasks

- [x] 1. Terraform S3 infrastructure
  - [x] 1.1 Create `infrastructure/s3.tf` with S3 bucket, versioning, encryption, public access block, lifecycle, CORS, IAM policy, and outputs
    - Define `aws_s3_bucket.shared` with name `myadmin-shared-${var.environment}` in eu-west-1, `force_destroy = false`
    - Add `aws_s3_bucket_versioning.shared` with `enabled` status
    - Add `aws_s3_bucket_server_side_encryption_configuration.shared` with AES-256 (aws:kms not needed, use sse_algorithm = "AES256")
    - Add `aws_s3_bucket_public_access_block.shared` with all four block settings = true
    - Add `aws_s3_bucket_lifecycle_configuration.shared` transitioning to STANDARD_IA after 90 days
    - Add `aws_s3_bucket_cors_configuration.shared` allowing GET/PUT/HEAD from `https://petergeers.github.io` and `http://localhost:3000`
    - Add `aws_iam_policy.s3_shared_access` with two statements (ListBucket on bucket ARN, PutObject/GetObject/DeleteObject on bucket/\*)
    - Add comment block documenting IAM principal attachment (manual step)
    - Add outputs: `s3_shared_bucket_name`, `s3_shared_bucket_arn`, `s3_shared_access_policy_arn`
    - Apply tags: Name, Environment, Project, ManagedBy, Purpose
    - _Requirements: 1.1–1.9, 2.1–2.5, 4.1–4.4, 5.1–5.5, 11.1–11.4_

  - [x] 1.2 Add validation block to `environment` variable in `infrastructure/variables.tf`
    - Add `validation { condition = contains(["dev", "staging", "production"], var.environment) }` with descriptive error message
    - _Requirements: 4.4_

- [x] 2. Environment variable configuration
  - [x] 2.1 Update `.env.example` with `S3_SHARED_BUCKET` entry
    - Add a new "AWS S3 Storage" section between "AWS SNS (Notifications)" and "Test Environment" sections
    - Include `S3_SHARED_BUCKET=<your-s3-bucket-name>` with a descriptive comment
    - _Requirements: 3.1_

  - [x] 2.2 Update `infrastructure/README.md` with S3 deployment instructions
    - Document that `S3_SHARED_BUCKET` must be set in Railway environment variables for the backend service
    - Include the bucket name pattern and manual IAM attachment step
    - _Requirements: 3.3_

- [x] 3. Checkpoint - Validate Terraform configuration
  - Ensure `terraform validate` passes in the infrastructure directory. Ask the user if questions arise.

- [x] 4. Backend storage blueprint and pre-signed URL endpoint
  - [x] 4.1 Create `backend/src/routes/storage.py` with `storage_bp` blueprint
    - Implement `GET /api/storage/presigned-url` endpoint
    - Use `@cognito_required(required_permissions=[])` and `@tenant_required()` decorators
    - Validate key starts with `{tenant}/` prefix, return 403 if cross-tenant
    - Return 503 if `S3_SHARED_BUCKET` is unset
    - Generate pre-signed URL with 300s expiry and `ResponseContentDisposition: inline`
    - Return `{'success': True, 'url': ..., 'expires_in': 300}`
    - _Requirements: 7.1–7.7_

  - [x] 4.2 Register `storage_bp` in `backend/src/app.py`
    - Import `from routes.storage import storage_bp`
    - Register with `app.register_blueprint(storage_bp)`
    - _Requirements: 7.1_

  - [x] 4.3 Write unit tests for pre-signed URL endpoint
    - Test valid tenant-prefixed key returns 200 with pre-signed URL
    - Test cross-tenant key returns 403
    - Test missing authentication returns 401
    - Test unset `S3_SHARED_BUCKET` returns 503
    - _Requirements: 7.1–7.6_

- [x] 5. S3 key structure update
  - [x] 5.1 Update `S3SharedStorage._make_key` to support `category` parameter
    - Add `category` parameter defaulting to `'invoices'` for backward compatibility
    - Update key pattern to `{tenant}/{category}/{reference}/{uuid}_{filename}`
    - Update `list_files` to accept optional `category` parameter scoping prefix to `{tenant}/{category}/`
    - _Requirements: 10.1–10.6_

  - [x] 5.2 Write unit tests for updated `_make_key` and `list_files`
    - Test default category produces `invoices` in key
    - Test explicit category (branding, templates) produces correct key structure
    - Test `list_files` with category scopes prefix correctly
    - _Requirements: 10.1–10.6_

- [x] 6. Provider-aware logo resolution
  - [x] 6.1 Create `backend/src/services/logo_resolver.py` shared helper
    - Implement `resolve_tenant_logo(tenant, branding_namespace, parameter_service)` function
    - Check `storage.invoice_provider` parameter to determine source
    - For `google_drive`: fetch from `lh3.googleusercontent.com` (existing logic)
    - For `s3_shared` / `s3_tenant`: read from S3 bucket using `company_logo_s3_key` parameter
    - Return base64 data URI string or None
    - _Requirements: 8.1–8.7_

  - [x] 6.2 Update `str_invoice_generator.py` to use `resolve_tenant_logo`
    - Replace inline logo fetch logic with call to `resolve_tenant_logo(tenant, 'str_branding', ps)`
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [x] 6.3 Update `pdf_generator_service.py` to use `resolve_tenant_logo`
    - Replace inline `_get_logo_base64` logic with call to `resolve_tenant_logo(tenant, 'zzp_branding', self.parameter_service)`
    - _Requirements: 8.4, 8.5_

  - [x] 6.4 Write unit tests for `logo_resolver.py`
    - Test Google Drive provider returns base64 data URI (mock requests)
    - Test S3 provider returns base64 data URI (mock boto3)
    - Test missing logo key returns None
    - Test unknown provider returns None
    - _Requirements: 8.1–8.7_

- [x] 7. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Logo upload endpoint
  - [x] 8.1 Add `POST /api/storage/upload-logo` to `backend/src/routes/storage.py`
    - Accept multipart file upload with `@cognito_required` and `@tenant_required()`
    - Validate file type (PNG, JPG, SVG) and max size (2MB)
    - Store at fixed key `{tenant}/branding/company_logo.{ext}` (overwrites previous)
    - Update `company_logo_s3_key` parameter via ParameterService
    - Return `{'success': True, 'key': ...}` on success
    - _Requirements: 9.1–9.3_

  - [x] 8.2 Write unit tests for logo upload endpoint
    - Test valid image upload stores to correct S3 key and updates parameter
    - Test invalid file type returns 400
    - Test file exceeding 2MB returns 400
    - Test missing authentication returns 401
    - _Requirements: 9.1–9.3_

- [x] 9. Frontend pre-signed URL integration
  - [x] 9.1 Update `handleRef3Click` in `frontend/src/components/BankingProcessor.tsx`
    - Detect S3 keys (values not starting with `http`)
    - Call `GET /api/storage/presigned-url?key={encodeURIComponent(ref3)}` via `authenticatedGet`
    - Open resulting URL in new tab on success
    - Fall back to `copyToClipboard` on failure
    - Keep existing Google Drive URL behavior unchanged
    - _Requirements: 7.8, 7.9_

- [x] 10. Frontend branding settings update
  - [x] 10.1 Update branding settings page to show file upload for S3 tenants
    - When `invoice_provider` is `s3_shared` or `s3_tenant`, show file upload control for logo
    - When `invoice_provider` is `google_drive`, keep existing text input for file ID
    - Call `POST /api/storage/upload-logo` with multipart form data on upload
    - _Requirements: 9.4, 9.5_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks are required — no optional tasks
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- No property-based tests needed — this feature is primarily IaC (Terraform) and CRUD endpoints
- Unit tests validate endpoint behavior, logo resolution, and key structure logic
- The Terraform file follows existing conventions from `cognito.tf`, `notifications.tf`, and `ses.tf`
- The `storage_bp` blueprint follows the same pattern as `tenant_admin_storage_bp` and other route files

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "5.1"] },
    { "id": 2, "tasks": ["4.1", "5.2", "6.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "6.2", "6.3"] },
    { "id": 4, "tasks": ["6.4", "8.1"] },
    { "id": 5, "tasks": ["8.2", "9.1"] },
    { "id": 6, "tasks": ["10.1"] }
  ]
}
```
