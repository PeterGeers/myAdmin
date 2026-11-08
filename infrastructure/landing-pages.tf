# Landing Page Infrastructure
# DynamoDB table, S3 public bucket, CloudFront distribution, and IAM policies
# for the tenant landing page feature.

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
# S3 Bucket — Published Landing Pages (served via CloudFront)
# ============================================================================

resource "aws_s3_bucket" "public_pages" {
  bucket        = "myadmin-public-pages-${var.environment}"
  force_destroy = false

  tags = {
    Name        = "myAdmin-Public-Pages"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "landing-page-delivery"
  }
}

# Server-Side Encryption (AES-256)
resource "aws_s3_bucket_server_side_encryption_configuration" "public_pages" {
  bucket = aws_s3_bucket.public_pages.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block All Public Access (CloudFront OAC provides read access)
resource "aws_s3_bucket_public_access_block" "public_pages" {
  bucket = aws_s3_bucket.public_pages.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================================
# CloudFront Function — URL Rewrite (host-based + path-based routing)
# ============================================================================

resource "aws_cloudfront_function" "public_pages_url_rewrite" {
  name    = "myadmin-public-pages-url-rewrite-${var.environment}"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrites landing page URLs: host-based (*.jabaki.nl, custom domains) and path-based (/p/{slug})"
  publish = true

  key_value_store_associations = [aws_cloudfront_key_value_store.domain_mapping.arn]

  code = <<-EOF
    import cf from 'cloudfront';

    // KVS binding — associated via Terraform key_value_store_associations
    var kvsId = '${aws_cloudfront_key_value_store.domain_mapping.id}';
    var kvs;
    try {
      kvs = cf.kvs(kvsId);
    } catch (err) {
      // KVS not available — custom domain lookup disabled
    }

    async function handler(event) {
      var request = event.request;
      var uri = request.uri;
      var host = request.headers.host ? request.headers.host.value : '';

      // --- Static subdomain redirects (Squarespace migration) ---
      var redirects = {
        'gscheckin.jabaki.nl':  'https://sites.google.com/pgeers.nl/jabaki/checkingreenstudio',
        'rscheckin.jabaki.nl':  'https://sites.google.com/pgeers.nl/jabaki/checkinredstudio',
        'gascheckin.jabaki.nl': 'https://sites.google.com/pgeers.nl/jabaki/checkingardenstudio',
      };
      if (redirects[host]) {
        return {
          statusCode: 302,
          statusDescription: 'Found',
          headers: { location: { value: redirects[host] } },
        };
      }

      // --- Host-based routing: Jabaki subdomain (slug.jabaki.nl) ---
      if (host.endsWith('.jabaki.nl')) {
        var slug = host.replace('.jabaki.nl', '');
        if (slug && slug.length > 0 && slug !== 'www') {
          if (uri === '/' || uri === '') {
            request.uri = '/' + slug + '/index.html';
          } else if (!uri.includes('.')) {
            // Non-file path → serve index.html
            request.uri = '/' + slug + '/index.html';
          } else {
            // File request (images, json, etc.) → prefix with slug
            request.uri = '/' + slug + uri;
          }
          return request;
        }
      }

      // --- Host-based routing: Custom domain (e.g. www.acme-rentals.nl) ---
      // Custom domain → slug mapping is stored in CloudFront KeyValueStore
      if (kvs && host && !host.endsWith('.cloudfront.net') && !host.endsWith('.jabaki.nl')) {
        try {
          var slug = await kvs.get(host);
          if (slug) {
            if (uri === '/' || uri === '') {
              request.uri = '/' + slug + '/index.html';
            } else if (!uri.includes('.')) {
              request.uri = '/' + slug + '/index.html';
            } else {
              request.uri = '/' + slug + uri;
            }
            return request;
          }
        } catch (e) {
          // KVS lookup failed or key not found — fall through to 404
        }
      }

      // --- Unknown host fallback: prevent content leak from unconfigured domains ---
      if (host && !host.endsWith('.cloudfront.net') && !host.endsWith('.jabaki.nl')) {
        // Host didn't match KVS — return 404
        return {
          statusCode: 404,
          statusDescription: 'Not Found',
          body: {
            encoding: 'text',
            data: '<html><body><h1>404 - Domain Not Found</h1><p>This domain is not configured.</p></body></html>'
          }
        };
      }

      // --- Existing path-based routing (fallback: /p/{slug}) ---

      // Match /p/{slug} or /p/{slug}/ → /{slug}/index.html
      if (uri.startsWith('/p/')) {
        var slug = uri.replace(/^\/p\//, '').replace(/\/$/, '');
        if (slug && slug.length > 0) {
          request.uri = '/' + slug + '/index.html';
        }
        return request;
      }

      // Match /{slug}/ (trailing slash, no file extension) → /{slug}/index.html
      if (uri.match(/^\/[a-z0-9-]+\/?$/) && !uri.includes('.')) {
        var path = uri.replace(/\/$/, '');
        request.uri = path + '/index.html';
        return request;
      }

      return request;
    }
  EOF
}

# ============================================================================
# CloudFront Distribution — Public Landing Page Delivery
# ============================================================================

# Origin Access Control for S3
resource "aws_cloudfront_origin_access_control" "public_pages" {
  name                              = "myadmin-public-pages-oac-${var.environment}"
  description                       = "OAC for landing page S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "public_pages" {
  enabled             = true
  comment             = "myAdmin public landing pages (${var.environment})"
  default_root_object = "index.html"
  aliases             = ["*.jabaki.nl"]

  origin {
    domain_name              = aws_s3_bucket.public_pages.bucket_regional_domain_name
    origin_id                = "S3-public-pages"
    origin_access_control_id = aws_cloudfront_origin_access_control.public_pages.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-public-pages"
    viewer_protocol_policy = "redirect-to-https"

    min_ttl     = 0
    default_ttl = 300
    max_ttl     = 3600

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.public_pages_url_rewrite.arn
    }

    # viewer-response: set CSP frame-ancestors on the application form from the
    # tenant's application_embed_origins (KVS). Defined in application-form.tf.
    # No-op for landing pages whose host has no embed-origins KVS entry (the
    # function omits the header when the host is not configured).
    function_association {
      event_type   = "viewer-response"
      function_arn = aws_cloudfront_function.application_form_frame_ancestors.arn
    }
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.jabaki_wildcard.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name        = "myAdmin-Public-Pages-CDN"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "landing-page-delivery"
  }
}

# S3 Bucket Policy — Allow CloudFront OAC to read objects
resource "aws_s3_bucket_policy" "public_pages" {
  bucket = aws_s3_bucket.public_pages.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontOAC"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.public_pages.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.public_pages.arn
          }
        }
      }
    ]
  })
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

# S3 public pages write access for publish/unpublish
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
#   - `arn:…:{bucket}/*/*`   — any object nested under a top-level `{slug}/` prefix
#                              (served artifacts live at `{slug}/index.html` etc.).
#   - `arn:…:{bucket}/_slugs/*` — the reserved control-plane marker prefix.
# Top-level bucket-root objects (e.g. a stray `foo.html` with no `{slug}/`) are NOT
# writable — PutObject there is denied, which is the intended least-privilege boundary.
# `_slugs/` is a strict subset of `*/*` (it has one path separator) but is listed
# explicitly for intent + in case the marker prefix is ever flattened.
#
# Buckets covered — BOTH, to RECONCILE the hosting-migration drift:
#   - the legacy personal bucket (`aws_s3_bucket.public_pages`, this account), and
#   - the NONPROFIT bucket (`var.nonprofit_public_pages_bucket_name`, acct 506221081911)
#     the publish identity was granted on via a LIVE CLI edit (identity-policy v2 in the
#     hosting-migration findings). Reflecting it here means a future `terraform apply`
#     will NOT revert the working cross-account publish. The matching BUCKET-POLICY grant
#     (principal = this user) lives on the NONPROFIT side and must be reconciled in the
#     hosting-migration spec's `hosting.tf` (see that spec's findings DRIFT NOTE) — it is
#     NOT this personal-account module's resource to author.
resource "aws_iam_policy" "s3_public_pages_write" {
  name        = "myadmin-s3-public-pages-write-${var.environment}"
  description = "Least-privilege, prefix-scoped S3 write for public-pages publishing (SEC-8): {slug}/* artifacts + _slugs/* markers only, never bucket-wide. Covers legacy + nonprofit buckets."

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
          # Legacy personal bucket — served `{slug}/*` artifacts + `_slugs/*` markers.
          "${aws_s3_bucket.public_pages.arn}/*/*",
          "${aws_s3_bucket.public_pages.arn}/_slugs/*",
          # Nonprofit bucket (hosting migration) — same two prefix scopes.
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
          aws_s3_bucket.public_pages.arn,
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

# CloudFront invalidation access for instant publish/unpublish visibility
#
# SEC-8 (spec 14 Task 9.2) — grants `cloudfront:CreateInvalidation` on BOTH:
#   - the legacy personal distribution (`aws_cloudfront_distribution.public_pages`), and
#   - the NONPROFIT `*.jabaki.nl` distribution (`var.nonprofit_public_pages_distribution_arn`,
#     acct 506221081911) the hosting migration cut over to.
#
# CROSS-ACCOUNT NOTE (hosting-migration finding): the publish identity
# `myadmin-railway-backend` is in the PERSONAL account (344561557829) but the
# live `*.jabaki.nl` distribution (E3GLUX3TWBIJG) is in NONPROFIT (506221081911).
# `cloudfront:CreateInvalidation` is NOT currently cross-account grantable to an
# IAM user by a resource policy the way S3 is (CloudFront distributions have no
# resource policy), so an IDENTITY grant naming a foreign-account distribution
# ARN alone does NOT authorise the call — the request still evaluates in the
# RESOURCE owner's (nonprofit) account, which has no matching grant for this
# principal. The identity statement below is the identity-side HALF of the grant
# (removes the "unpermitted in the principal's own account" half of the failure).
#
# To actually CLOSE the invalidation gap, the correct minimal mechanism is a
# CROSS-ACCOUNT ROLE in NONPROFIT that this personal user assumes:
#   - nonprofit defines `role/myadmin-publish-invalidation` whose trust policy allows
#     `arn:aws:iam::344561557829:user/service-accounts/myadmin-railway-backend` to
#     `sts:AssumeRole`, and whose permissions policy allows
#     `cloudfront:CreateInvalidation` on the nonprofit distribution;
#   - that ROLE + trust belong to the HOSTING-MIGRATION spec's `hosting.tf`
#     (nonprofit-owned), NOT this personal-account module — so it is FLAGGED there,
#     not authored here (do not silently author another spec's nonprofit infra).
# The `sts:AssumeRole` permission for THIS user (the personal-account half of the
# assume-role mechanism) is NOT added yet — it needs the nonprofit role ARN, which
# the hosting-migration tf must define first. It is a FOLLOW-UP in THIS module once
# that role exists; until then the identity grant below is the identity-side half.
#
# CODE FOLLOW-UP (flagged, not closed by IAM alone): the backend currently BUILDS
# the invalidation ARN with the PERSONAL account id (344561557829) while the
# distribution is in NONPROFIT (506221081911) — see hosting-migration findings and
# `sam/members/repository/public_page_artifact_store.py`. Even with the grant/role
# in place, the backend must (a) target the nonprofit distribution id and (b) assume
# the cross-account role before calling `CreateInvalidation`. That is a CODE change
# tracked as a follow-up to this IAM task — the invalidation is already best-effort /
# non-fatal in the publish path, so publishing is NOT blocked by it.
resource "aws_iam_policy" "cloudfront_invalidation" {
  name        = "myadmin-cloudfront-invalidation-${var.environment}"
  description = "CloudFront invalidation access for public-pages publish/unpublish (SEC-8). Identity-side grant for the legacy + nonprofit distributions; cross-account close-out via an assume-role in the hosting-migration tf."

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
          aws_cloudfront_distribution.public_pages.arn,
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

# Custom Domains management — ACM, CloudFront, and KVS access
resource "aws_iam_policy" "custom_domains_management" {
  name        = "myadmin-custom-domains-${var.environment}"
  description = "Permissions for managing custom domain certificates and routing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ACMCertificateManagement"
        Effect = "Allow"
        Action = [
          "acm:RequestCertificate",
          "acm:DescribeCertificate",
          "acm:DeleteCertificate",
          "acm:ListCertificates",
          "acm:AddTagsToCertificate"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudFrontDistributionUpdate"
        Effect = "Allow"
        Action = [
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:UpdateDistribution"
        ]
        Resource = aws_cloudfront_distribution.public_pages.arn
      },
      {
        Sid    = "CloudFrontKeyValueStore"
        Effect = "Allow"
        Action = [
          "cloudfront-keyvaluestore:GetKey",
          "cloudfront-keyvaluestore:PutKey",
          "cloudfront-keyvaluestore:DeleteKey",
          "cloudfront-keyvaluestore:ListKeys",
          "cloudfront-keyvaluestore:DescribeKeyValueStore"
        ]
        Resource = aws_cloudfront_key_value_store.domain_mapping.arn
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
# CloudFront KeyValueStore — Custom Domain → Slug Mapping
# ============================================================================

resource "aws_cloudfront_key_value_store" "domain_mapping" {
  name    = "myadmin-domain-slug-mapping"
  comment = "Maps custom domains to tenant slugs for landing page routing"
}

# ============================================================================
# Outputs
# ============================================================================

output "dynamodb_landing_pages_table_name" {
  description = "Name of the DynamoDB table for landing pages"
  value       = aws_dynamodb_table.landing_pages.name
}

output "dynamodb_landing_pages_table_arn" {
  description = "ARN of the DynamoDB table for landing pages"
  value       = aws_dynamodb_table.landing_pages.arn
}

output "s3_public_pages_bucket_name" {
  description = "Name of the S3 bucket for published landing pages"
  value       = aws_s3_bucket.public_pages.bucket
}

output "s3_public_pages_bucket_arn" {
  description = "ARN of the S3 bucket for published landing pages"
  value       = aws_s3_bucket.public_pages.arn
}

output "cloudfront_public_pages_domain_name" {
  description = "Domain name of the CloudFront distribution for landing pages"
  value       = aws_cloudfront_distribution.public_pages.domain_name
}

output "cloudfront_public_pages_distribution_id" {
  description = "ID of the CloudFront distribution for landing pages"
  value       = aws_cloudfront_distribution.public_pages.id
}

output "dynamodb_landing_pages_policy_arn" {
  description = "ARN of the IAM policy for DynamoDB landing page access"
  value       = aws_iam_policy.dynamodb_landing_pages.arn
}

output "s3_public_pages_write_policy_arn" {
  description = "ARN of the IAM policy for S3 public pages write access"
  value       = aws_iam_policy.s3_public_pages_write.arn
}

output "cloudfront_kvs_domain_mapping_arn" {
  description = "ARN of the CloudFront KeyValueStore for custom domain→slug mapping"
  value       = aws_cloudfront_key_value_store.domain_mapping.arn
}

output "custom_domains_management_policy_arn" {
  description = "ARN of the IAM policy for custom domain management (ACM, CloudFront, KVS)"
  value       = aws_iam_policy.custom_domains_management.arn
}
