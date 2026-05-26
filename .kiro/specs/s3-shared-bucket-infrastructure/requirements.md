# Requirements Document

## Introduction

The myAdmin application uses an `S3SharedStorage` class to store invoices and documents in a shared S3 bucket with tenant-prefixed keys. However, no actual S3 bucket exists in AWS — there is no Terraform resource, no IAM permissions, and the `S3_SHARED_BUCKET` environment variable is undefined. This means the provisioning service cannot seed the bucket name into the parameters table, and document storage fails at runtime.

This feature provisions the complete S3 infrastructure: bucket creation via Terraform, IAM permissions for the backend, and environment variable configuration for both local development and Railway production.

## Glossary

- **Terraform**: Infrastructure-as-Code tool used to provision and manage AWS resources declaratively
- **S3_Bucket**: An AWS S3 bucket resource that stores objects (files) with key-based access
- **IAM_Policy**: An AWS Identity and Access Management policy document that grants specific permissions to AWS principals
- **Backend_Service**: The Flask-based Python backend running on Railway in production and Docker locally
- **Provisioning_Service**: The `TenantProvisioningService` that seeds configuration parameters (including the bucket name) into the parameters table during tenant onboarding
- **S3SharedStorage**: The existing storage provider class that uploads/downloads files using tenant-prefixed S3 keys
- **Railway**: The cloud platform hosting the myAdmin production backend
- **Tenant_Key_Prefix**: The S3 key structure `{tenant}/{referenceNumber}/{uuid}_{filename}` used for tenant isolation within the shared bucket

## Requirements

### Requirement 1: S3 Bucket Creation

**User Story:** As a system administrator, I want an S3 bucket provisioned in AWS via Terraform, so that the S3SharedStorage class has a real bucket to store documents in.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL define an S3 bucket resource in `infrastructure/s3.tf` with a name following the pattern `myadmin-shared-{environment}`, where `{environment}` is sourced from the existing `var.environment` variable defined in `variables.tf`
2. THE S3_Bucket SHALL be created in the `eu-west-1` region
3. THE S3_Bucket SHALL have versioning enabled
4. THE S3_Bucket SHALL have server-side encryption enabled using AES-256 (SSE-S3)
5. THE S3_Bucket SHALL block all public access via the `aws_s3_bucket_public_access_block` resource with all four block settings (`block_public_acls`, `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`) set to true
6. THE Terraform_Configuration SHALL define a lifecycle rule that transitions objects to STANDARD_IA storage class after 90 days
7. THE Terraform_Configuration SHALL output the bucket name and ARN as Terraform outputs
8. THE S3_Bucket SHALL have `force_destroy` set to `false` to prevent accidental deletion of stored documents during Terraform destroy operations
9. THE Terraform_Configuration SHALL apply tags to the S3 bucket including `Project` set to the project name, `Environment` set to the environment value, and `ManagedBy` set to `terraform`

### Requirement 2: IAM Permissions for Backend

**User Story:** As a backend service, I want IAM permissions to read and write objects in the S3 bucket, so that the S3SharedStorage class can upload, download, list, and delete documents.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL define an IAM policy granting `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, and `s3:ListBucket` permissions
2. THE IAM_Policy SHALL define separate statements scoping `s3:ListBucket` to the bucket ARN (`arn:aws:s3:::bucket-name`) and `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` to the bucket objects ARN (`arn:aws:s3:::bucket-name/*`), where the bucket ARN is referenced from the Terraform S3 bucket resource defined in Requirement 1
3. THE IAM_Policy SHALL contain no wildcard actions (`s3:*`), no wildcard resources (`*`), and no permissions beyond the four actions listed in criterion 1
4. THE Terraform_Configuration SHALL attach the IAM policy to the backend service's IAM user or role
5. IF the IAM user or role does not yet exist in Terraform, THEN THE Terraform_Configuration SHALL include a comment block in `infrastructure/s3.tf` documenting the IAM principal ARN to which the policy must be manually attached and the AWS CLI command to perform the attachment

### Requirement 3: Environment Variable Configuration

**User Story:** As a developer, I want the `S3_SHARED_BUCKET` environment variable defined in all environments, so that the Provisioning_Service can seed the bucket name and S3SharedStorage can resolve its target bucket.

#### Acceptance Criteria

1. THE `.env.example` file SHALL include an `S3_SHARED_BUCKET` entry with a placeholder value (e.g., `<your-s3-bucket-name>`) and a descriptive comment, placed in a new "AWS S3 Storage" section between the existing "AWS SNS (Notifications)" and "Test Environment" sections
2. WHEN the Backend_Service starts in production, THE `S3_SHARED_BUCKET` environment variable SHALL contain a non-empty string matching a valid AWS S3 bucket name (3–63 lowercase characters, digits, or hyphens) provisioned by Terraform
3. THE project documentation in the deployment or infrastructure README SHALL specify that the `S3_SHARED_BUCKET` variable must be set in Railway's environment variables for the backend service
4. WHEN `S3_SHARED_BUCKET` is configured with a non-empty value, THE Provisioning_Service SHALL seed two parameters at tenant scope during tenant onboarding: `storage.invoice_provider` set to `s3_shared` and `storage.s3_shared_bucket` set to the environment variable value
5. IF `S3_SHARED_BUCKET` is unset or empty at service start, THEN THE Provisioning_Service SHALL skip S3 storage parameter seeding during tenant onboarding and the tenant SHALL retain the default storage provider configuration

### Requirement 4: Bucket Naming and Tagging

**User Story:** As a system administrator, I want consistent naming and tagging on the S3 bucket, so that it is identifiable and manageable within the AWS account.

#### Acceptance Criteria

1. THE S3_Bucket SHALL use the naming pattern `myadmin-shared-{environment}` where environment is derived from the Terraform `environment` variable, which accepts one of the values: `dev`, `staging`, or `production`
2. THE S3_Bucket SHALL be tagged with all of the following tags: `Project = myAdmin`, `Environment = {environment}`, and `ManagedBy = terraform`
3. THE S3_Bucket SHALL be tagged with `Purpose = document-storage` to identify its function
4. IF the Terraform `environment` variable is set to a value other than `dev`, `staging`, or `production`, THEN THE Terraform configuration SHALL fail validation with an error message indicating the allowed values

### Requirement 5: CORS Configuration

**User Story:** As a frontend developer, I want CORS configured on the S3 bucket, so that future direct-upload functionality from the browser is not blocked.

#### Acceptance Criteria

1. THE S3_Bucket SHALL have a CORS configuration allowing `GET`, `PUT`, and `HEAD` methods
2. THE CORS configuration SHALL allow the production origin `https://petergeers.github.io` and the local development origin `http://localhost:3000`
3. THE CORS configuration SHALL allow request headers `Content-Type`, `x-amz-acl`, and any header matching the prefix `x-amz-meta-`
4. THE CORS configuration SHALL expose the `ETag` and `Content-Length` headers in responses
5. THE CORS configuration SHALL set a max age of 3600 seconds for preflight caching

### Requirement 6: Terraform State Consistency

**User Story:** As a system administrator, I want the new S3 resources to integrate cleanly with the existing Terraform state, so that applying the configuration does not disrupt other managed resources.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL use variables already defined in `main.tf` and `variables.tf` (specifically `aws_region`, `project_name`, and `environment`) without redefining them or any other existing variables or resource identifiers
2. THE Terraform_Configuration SHALL be contained in a single new file `infrastructure/s3.tf` following the existing resource-per-file convention, including a file header comment, resource tags (Name, Environment, Project, ManagedBy), and output blocks for resource identifiers
3. WHEN `terraform validate` is run against the infrastructure directory, THE Terraform_Configuration SHALL pass with no errors
4. WHEN `terraform plan` is run, THE new resources SHALL show as additions only, with zero modifications or deletions to existing resources
