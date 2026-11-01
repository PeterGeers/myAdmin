# ============================================================================
# S3 bucket — published landing pages (served via CloudFront OAC)
# ============================================================================
resource "aws_s3_bucket" "public_pages" {
  bucket        = var.public_pages_bucket_name
  force_destroy = false
  tags = {
    Name        = "myAdmin-Public-Pages-Nonprofit"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "landing-page-delivery"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "public_pages" {
  bucket = aws_s3_bucket.public_pages.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "public_pages" {
  bucket                  = aws_s3_bucket.public_pages.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================================
# CloudFront KeyValueStores
#   - domain_mapping: custom-domain -> slug (used by url-rewrite function)
#   - application_embed_origins: created so the Phase 6 backend re-seed has a
#     target. NOT associated to any function here (CSP function deferred, D4).
# ============================================================================
resource "aws_cloudfront_key_value_store" "domain_mapping" {
  name    = "myadmin-domain-slug-mapping"
  comment = "Maps custom domains to tenant slugs for landing page routing"
}

resource "aws_cloudfront_key_value_store" "application_embed_origins" {
  name    = "myadmin-application-embed-origins"
  comment = "Form host -> allowed embed origins (reserved; CSP function deferred, D4)"
}

# ============================================================================
# CloudFront Function — url-rewrite (viewer-request). Copied verbatim from the
# personal landing-pages.tf so routing is byte-for-byte identical.
# ============================================================================
resource "aws_cloudfront_function" "public_pages_url_rewrite" {
  name    = "myadmin-public-pages-url-rewrite-${var.environment}"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrites landing page URLs: host-based (*.jabaki.nl, custom domains) and path-based (/p/{slug})"
  publish = true

  key_value_store_associations = [aws_cloudfront_key_value_store.domain_mapping.arn]

  code = <<-EOF
    import cf from 'cloudfront';

    var kvsId = '${aws_cloudfront_key_value_store.domain_mapping.id}';
    var kvs;
    try {
      kvs = cf.kvs(kvsId);
    } catch (err) {}

    async function handler(event) {
      var request = event.request;
      var uri = request.uri;
      var host = request.headers.host ? request.headers.host.value : '';

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

      if (host.endsWith('.jabaki.nl')) {
        var slug = host.replace('.jabaki.nl', '');
        if (slug && slug.length > 0 && slug !== 'www') {
          if (uri === '/' || uri === '') {
            request.uri = '/' + slug + '/index.html';
          } else if (!uri.includes('.')) {
            request.uri = '/' + slug + '/index.html';
          } else {
            request.uri = '/' + slug + uri;
          }
          return request;
        }
      }

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
        } catch (e) {}
      }

      if (host && !host.endsWith('.cloudfront.net') && !host.endsWith('.jabaki.nl')) {
        return {
          statusCode: 404,
          statusDescription: 'Not Found',
          body: {
            encoding: 'text',
            data: '<html><body><h1>404 - Domain Not Found</h1><p>This domain is not configured.</p></body></html>'
          }
        };
      }

      if (uri.startsWith('/p/')) {
        var slug = uri.replace(/^\/p\//, '').replace(/\/$/, '');
        if (slug && slug.length > 0) {
          request.uri = '/' + slug + '/index.html';
        }
        return request;
      }

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
# ACM certificate — *.jabaki.nl (us-east-1).
# The DNS-validation CNAME it needs is written into the PERSONAL jabaki.nl zone
# as a separate, deliberate step (Phase 2.3) using the personal profile — it is
# intentionally NOT a resource here, because this state must not touch that zone.
# So we use aws_acm_certificate (request only) and let Phase 2.3 add the record;
# issuance is confirmed out-of-band before the distribution references the cert.
# ============================================================================
resource "aws_acm_certificate" "jabaki_wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.jabaki.nl"
  validation_method = "DNS"

  tags = {
    Name        = "jabaki-wildcard-cert-nonprofit"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================================================
# Origin Access Control + Distribution
# ============================================================================
resource "aws_cloudfront_origin_access_control" "public_pages" {
  name                              = "myadmin-public-pages-oac-nonprofit-${var.environment}"
  description                       = "OAC for nonprofit landing page S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "public_pages" {
  enabled             = true
  comment             = "myAdmin public landing pages (nonprofit ${var.environment})"
  default_root_object = "index.html"
  aliases             = var.distribution_aliases

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
    min_ttl                = 0
    default_ttl            = 300
    max_ttl                = 3600

    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }

    # ONLY the viewer-request url-rewrite function (parity, D4). The personal
    # stack also had a viewer-response CSP function — deliberately omitted here.
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
    geo_restriction { restriction_type = "none" }
  }

  # References the cert ARN directly. Apply ordering: request cert (above) ->
  # Phase 2.3 add validation CNAME in personal zone -> cert ISSUED ->
  # then apply the distribution. See README.md for the two-step apply.
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.jabaki_wildcard.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name        = "myAdmin-Public-Pages-CDN-Nonprofit"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "landing-page-delivery"
  }
}

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
          StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.public_pages.arn }
        }
      },
      {
        # Cross-account publish: the Railway backend IAM user (personal account)
        # writes published landing pages into this nonprofit bucket. Both this
        # resource policy AND the user's identity policy
        # (myadmin-s3-public-pages-write-production, personal account) must allow it.
        Sid       = "AllowRailwayBackendPublishCrossAccount"
        Effect    = "Allow"
        Principal = { AWS = var.railway_backend_user_arn }
        Action    = ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetObject"]
        Resource = [
          aws_s3_bucket.public_pages.arn,
          "${aws_s3_bucket.public_pages.arn}/*"
        ]
      }
    ]
  })
}

# ============================================================================
# Backend IAM policies (Railway) — mirror the personal stack
# ============================================================================
resource "aws_iam_policy" "s3_public_pages_write" {
  name        = "myadmin-s3-public-pages-write-nonprofit-${var.environment}"
  description = "S3 write access for myAdmin landing page publishing (nonprofit)"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AllowPublicPagesWrite"
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:DeleteObject"]
      Resource = "${aws_s3_bucket.public_pages.arn}/*"
    }]
  })
}

resource "aws_iam_policy" "cloudfront_invalidation" {
  name        = "myadmin-cloudfront-invalidation-nonprofit-${var.environment}"
  description = "CloudFront invalidation access for publish/unpublish (nonprofit)"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AllowInvalidation"
      Effect   = "Allow"
      Action   = ["cloudfront:CreateInvalidation"]
      Resource = aws_cloudfront_distribution.public_pages.arn
    }]
  })
}

resource "aws_iam_policy" "kvs_access" {
  name        = "myadmin-public-pages-kvs-nonprofit-${var.environment}"
  description = "CloudFront KeyValueStore access for both public-pages KVS (nonprofit)"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "KVSAccess"
      Effect = "Allow"
      Action = [
        "cloudfront-keyvaluestore:GetKey",
        "cloudfront-keyvaluestore:PutKey",
        "cloudfront-keyvaluestore:DeleteKey",
        "cloudfront-keyvaluestore:ListKeys",
        "cloudfront-keyvaluestore:DescribeKeyValueStore"
      ]
      Resource = [
        aws_cloudfront_key_value_store.domain_mapping.arn,
        aws_cloudfront_key_value_store.application_embed_origins.arn
      ]
    }]
  })
}

# ============================================================================
# Outputs — the values Phase 6 needs to repoint Railway + the frontend
# ============================================================================
output "public_pages_bucket_name" { value = aws_s3_bucket.public_pages.bucket }
output "cloudfront_distribution_id" { value = aws_cloudfront_distribution.public_pages.id }
output "cloudfront_distribution_domain" { value = aws_cloudfront_distribution.public_pages.domain_name }
output "cloudfront_distribution_zone_id" { value = aws_cloudfront_distribution.public_pages.hosted_zone_id }
output "domain_mapping_kvs_arn" { value = aws_cloudfront_key_value_store.domain_mapping.arn }
output "application_embed_origins_kvs_arn" { value = aws_cloudfront_key_value_store.application_embed_origins.arn }
output "acm_certificate_arn" { value = aws_acm_certificate.jabaki_wildcard.arn }
output "acm_validation_options" { value = aws_acm_certificate.jabaki_wildcard.domain_validation_options }
output "s3_write_policy_arn" { value = aws_iam_policy.s3_public_pages_write.arn }
output "cloudfront_invalidation_policy_arn" { value = aws_iam_policy.cloudfront_invalidation.arn }
output "kvs_access_policy_arn" { value = aws_iam_policy.kvs_access.arn }
