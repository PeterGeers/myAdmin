# AWS S3 Shared Bucket for myAdmin
# Provisions the shared document storage bucket used by S3SharedStorage
# for tenant-prefixed invoice, branding, and template storage.

# S3 Bucket
resource "aws_s3_bucket" "shared" {
  bucket        = "myadmin-shared-${var.environment}"
  force_destroy = false

  tags = {
    Name        = "myAdmin-Shared-Storage"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "document-storage"
  }
}

# Versioning
resource "aws_s3_bucket_versioning" "shared" {
  bucket = aws_s3_bucket.shared.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-Side Encryption (AES-256)
resource "aws_s3_bucket_server_side_encryption_configuration" "shared" {
  bucket = aws_s3_bucket.shared.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block All Public Access
resource "aws_s3_bucket_public_access_block" "shared" {
  bucket = aws_s3_bucket.shared.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle Rule — transition to STANDARD_IA after 90 days
resource "aws_s3_bucket_lifecycle_configuration" "shared" {
  bucket = aws_s3_bucket.shared.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

# CORS Configuration — allow browser uploads from frontend origins
resource "aws_s3_bucket_cors_configuration" "shared" {
  bucket = aws_s3_bucket.shared.id

  cors_rule {
    allowed_headers = ["Content-Type", "x-amz-acl", "x-amz-meta-*"]
    allowed_methods = ["GET", "PUT", "HEAD"]
    allowed_origins = [
      "https://petergeers.github.io",
      "http://localhost:3000"
    ]
    expose_headers  = ["ETag", "Content-Length"]
    max_age_seconds = 3600
  }
}

# IAM Policy — least-privilege S3 access for the backend service
resource "aws_iam_policy" "s3_shared_access" {
  name        = "myadmin-s3-shared-access-${var.environment}"
  description = "Least-privilege S3 access for myAdmin backend to the shared document bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowBucketListing"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.shared.arn
      },
      {
        Sid    = "AllowObjectOperations"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.shared.arn}/*"
      }
    ]
  })

  tags = {
    Name        = "myAdmin-S3-Shared-Access"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# ============================================================================
# IAM Policy Attachment
# ============================================================================
# The policy above must be attached to the IAM user or role used by the
# backend service (Railway production uses AWS access keys).
#
# To attach manually via AWS CLI:
#
#   aws iam attach-user-policy \
#     --user-name <backend-iam-user> \
#     --policy-arn <output: s3_shared_access_policy_arn>
#
# Or for a role:
#
#   aws iam attach-role-policy \
#     --role-name <backend-iam-role> \
#     --policy-arn <output: s3_shared_access_policy_arn>
#
# ============================================================================

# Outputs
output "s3_shared_bucket_name" {
  description = "Name of the shared S3 bucket for document storage"
  value       = aws_s3_bucket.shared.bucket
}

output "s3_shared_bucket_arn" {
  description = "ARN of the shared S3 bucket"
  value       = aws_s3_bucket.shared.arn
}

output "s3_shared_access_policy_arn" {
  description = "ARN of the IAM policy for S3 shared bucket access"
  value       = aws_iam_policy.s3_shared_access.arn
}
