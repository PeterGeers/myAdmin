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
# CloudFront Function — URL Rewrite (/p/{slug} → {slug}/index.html)
# ============================================================================

resource "aws_cloudfront_function" "public_pages_url_rewrite" {
  name    = "myadmin-public-pages-url-rewrite-${var.environment}"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrites landing page URLs to {slug}/index.html"
  publish = true
  code    = <<-EOF
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

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
    cloudfront_default_certificate = true
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
resource "aws_iam_policy" "s3_public_pages_write" {
  name        = "myadmin-s3-public-pages-write-${var.environment}"
  description = "S3 write access for myAdmin landing page publishing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPublicPagesWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.public_pages.arn}/*"
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
resource "aws_iam_policy" "cloudfront_invalidation" {
  name        = "myadmin-cloudfront-invalidation-${var.environment}"
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
        Resource = aws_cloudfront_distribution.public_pages.arn
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
