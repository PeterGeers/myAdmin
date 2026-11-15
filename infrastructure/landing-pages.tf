# Landing Page Infrastructure (personal account 344561557829)
#
# What is left here: the DynamoDB drafts/versions table and the IAM policies for
# the Railway backend user `myadmin-railway-backend`.
#
# The public-pages HOSTING (S3 bucket, CloudFront distribution, url-rewrite
# function, OAC, domain->slug KVS) moved to the nonprofit account (506221081911)
# and lives in infrastructure/nonprofit-public-pages/. The personal copies were
# retired on 2026-11-15 (spec .kiro/specs/myBacklog/jabaki-hosting-migration-to-nonprofit,
# task 7.2; bucket backup in /home/peter/backups/jabaki-old-public-pages-2026-11-15).

# ============================================================================
# DynamoDB Table — Landing Page Drafts & Versions
# ============================================================================

resource "aws_dynamodb_table" "landing_pages" {
  name         = "myadmin-landing-pages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  tags = {
    Name        = "myAdmin-Landing-Pages"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "landing-page-storage"
  }
}

# ============================================================================
# Retired personal hosting — drop from state, do NOT destroy (already deleted)
# ============================================================================
# The objects were deleted by hand after a backup. These `removed` blocks make the
# next plan forget them instead of trying to recreate or destroy them. Delete the
# blocks once an apply has run with them.

removed {
  from = aws_s3_bucket.public_pages
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_s3_bucket_server_side_encryption_configuration.public_pages
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_s3_bucket_public_access_block.public_pages
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_s3_bucket_policy.public_pages
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cloudfront_function.public_pages_url_rewrite
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cloudfront_origin_access_control.public_pages
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cloudfront_distribution.public_pages
  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_cloudfront_key_value_store.domain_mapping
  lifecycle {
    destroy = false
  }
}

# ============================================================================
# IAM Policies — Backend Access (Railway)
# ============================================================================

# DynamoDB access for landing page CRUD
resource "aws_iam_policy" "dynamodb_landing_pages" {
  name        = "myadmin-dynamodb-landing-pages-${var.environment}"
  description = "DynamoDB access for myAdmin landing page operations"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLandingPageTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.landing_pages.arn
      }
    ]
  })

  tags = {
    Name        = "myAdmin-DynamoDB-Landing-Pages"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# S3 public pages write access for publish/unpublish (nonprofit bucket)
#
# SEC-8 (spec 14 Task 9.2) — LEAST-PRIVILEGE, PREFIX-SCOPED publish IAM.
# A publisher may write ONLY:
#   - the served artifacts it owns under `{slug}/*` (e.g. `{slug}/index.html`,
#     `{slug}/form.json`, and the landing plane's `{slug}/landing-pages/*.json`), and
#   - the control-plane owner markers under `_slugs/*` (`_slugs/{slug}`, design D6).
# It must NEVER have bucket-wide `s3:PutObject` — over-broad write would let one
# producer overwrite another producer's marker or served artifact (SEC-8 hijack).
#
# Per-slug Resource ARNs are impractical in ONE shared identity policy (the slugs are
# runtime data, not known at apply time), so we scope to the two PREFIX patterns the
# producers actually use instead of `bucket/*`:
#   - `arn:…:{bucket}/*/*`      — any object nested under a top-level `{slug}/` prefix.
#   - `arn:…:{bucket}/_slugs/*` — the reserved control-plane marker prefix.
# Top-level bucket-root objects are NOT writable — the intended boundary.
#
# The bucket is in the NONPROFIT account; the matching bucket-policy grant (principal
# = this user) lives in infrastructure/nonprofit-public-pages/hosting.tf.
resource "aws_iam_policy" "s3_public_pages_write" {
  name = "myadmin-s3-public-pages-write-${var.environment}"
  # Description kept identical to the live policy: changing it forces a
  # destroy/re-create of the attached policy (a short permission gap).
  description = "S3 write access for myAdmin landing page publishing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPrefixScopedPublicPagesWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.nonprofit_public_pages_bucket_name}/*/*",
          "arn:aws:s3:::${var.nonprofit_public_pages_bucket_name}/_slugs/*"
        ]
      },
      {
        # ListBucket is needed by the publish/marker-resolve path (the slug-marker
        # store reverse-reads `_slugs/{slug}`; an unpublish may list a slug's prefix).
        # Scoped with a prefix condition so the grant cannot enumerate the whole bucket.
        Sid    = "AllowPrefixScopedList"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.nonprofit_public_pages_bucket_name}"
        ]
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "_slugs/*",
              "*/*"
            ]
          }
        }
      }
    ]
  })

  tags = {
    Name        = "myAdmin-S3-Public-Pages-Write"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# CloudFront invalidation — identity-side grant on the NONPROFIT distribution.
#
# CloudFront distributions have no resource policy, so this identity grant alone
# does not authorise a cross-account call. The backend actually invalidates by
# assuming `var.nonprofit_public_pages_backend_role_arn` (see the
# AssumeNonprofitPublicPagesRole statement below and
# landing_page_publish_service._public_pages_credentials). This statement is kept
# as the identity half; it grants nothing in this account.
resource "aws_iam_policy" "cloudfront_invalidation" {
  name = "myadmin-cloudfront-invalidation-${var.environment}"
  # Description kept identical to the live policy (a change forces replacement).
  description = "CloudFront invalidation access for landing page publish/unpublish"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowInvalidation"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation"
        ]
        Resource = [
          var.nonprofit_public_pages_distribution_arn
        ]
      }
    ]
  })

  tags = {
    Name        = "myAdmin-CloudFront-Invalidation"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# Custom Domains management — cross-account role only.
#
# The custom-domain tenants (CloudFront multi-tenant distribution), their
# certificates and the KVS are all in NONPROFIT. The backend assumes this role
# there (env PUBLIC_PAGES_AWS_ROLE_ARN); the role + trust live in
# infrastructure/nonprofit-public-pages/hosting.tf. The former personal ACM,
# CloudFront and KVS statements pointed at retired resources and were dropped.
resource "aws_iam_policy" "custom_domains_management" {
  name = "myadmin-custom-domains-${var.environment}"
  # Description kept identical to the live policy (a change forces replacement).
  description = "Permissions for managing custom domain certificates and routing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AssumeNonprofitPublicPagesRole"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = var.nonprofit_public_pages_backend_role_arn
      }
    ]
  })

  tags = {
    Name        = "myAdmin-Custom-Domains"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# ============================================================================
# Outputs
# ============================================================================
# Hosting outputs (bucket, distribution, KVS) come from
# `terraform -chdir=infrastructure/nonprofit-public-pages output`.

output "dynamodb_landing_pages_table_name" {
  description = "Name of the DynamoDB table for landing pages"
  value       = aws_dynamodb_table.landing_pages.name
}

output "dynamodb_landing_pages_table_arn" {
  description = "ARN of the DynamoDB table for landing pages"
  value       = aws_dynamodb_table.landing_pages.arn
}

output "dynamodb_landing_pages_policy_arn" {
  description = "ARN of the IAM policy for DynamoDB landing page access"
  value       = aws_iam_policy.dynamodb_landing_pages.arn
}

output "s3_public_pages_write_policy_arn" {
  description = "ARN of the IAM policy for S3 public pages write access"
  value       = aws_iam_policy.s3_public_pages_write.arn
}

output "custom_domains_management_policy_arn" {
  description = "ARN of the IAM policy that lets the backend assume the nonprofit public-pages role"
  value       = aws_iam_policy.custom_domains_management.arn
}
