# ============================================================================
# Custom domains — CloudFront MULTI-TENANT distribution (SaaS Manager)
# ============================================================================
# Tenant-owned domains (e.g. www.thecategorystudio.nl) are served by THIS
# distribution, NOT by the *.jabaki.nl distribution in hosting.tf (which stays
# untouched). Each custom domain is a "distribution tenant" the backend creates
# at runtime (DomainService -> CloudFrontDomainService.create_domain_tenant):
#   - domain        = the tenant's domain
#   - parameter     = slug  -> origin path "/{{slug}}" in the shared bucket
#   - certificate   = CloudFront-managed ACM cert, HTTP-validated by CloudFront
#                     (the tenant adds ONE CNAME: domain -> routing endpoint)
# Tenants are runtime data and deliberately NOT managed by Terraform.
#
# Requires AWS provider >= 6.28 (aws_cloudfront_multitenant_distribution).
# ============================================================================

data "aws_caller_identity" "current" {}

# Multi-tenant distributions do not support the legacy TTL fields, so caching
# is a cache policy. TTLs mirror the *.jabaki.nl distribution (default 5 min,
# max 1 h) so a republish shows up on custom domains within minutes without a
# per-tenant invalidation.
resource "aws_cloudfront_cache_policy" "custom_domains" {
  name        = "myadmin-custom-domains-${var.environment}"
  comment     = "Landing pages on custom domains (mirrors *.jabaki.nl TTLs)"
  min_ttl     = 0
  default_ttl = 300
  max_ttl     = 3600

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

# The origin path already scopes every request to /{slug}; this only maps
# extensionless page URLs (/, /about) to the slug's index.html, matching the
# *.jabaki.nl behaviour. No KVS lookup is needed for custom domains.
resource "aws_cloudfront_function" "custom_domains_index_rewrite" {
  name    = "myadmin-custom-domains-index-rewrite-${var.environment}"
  runtime = "cloudfront-js-2.0"
  comment = "Custom domains: extensionless URIs -> /index.html (origin path adds /{slug})"
  publish = true

  code = <<-EOF
    function handler(event) {
      var request = event.request;
      if (!request.uri.includes('.')) {
        request.uri = '/index.html';
      }
      return request;
    }
  EOF
}

resource "aws_cloudfront_multitenant_distribution" "custom_domains" {
  enabled             = true
  comment             = "myAdmin landing pages on tenant custom domains (nonprofit ${var.environment})"
  default_root_object = "index.html"

  origin {
    domain_name              = aws_s3_bucket.public_pages.bucket_regional_domain_name
    id                       = "S3-public-pages"
    origin_access_control_id = aws_cloudfront_origin_access_control.public_pages.id
    origin_path              = "/{{slug}}"
  }

  default_cache_behavior {
    target_origin_id       = "S3-public-pages"
    viewer_protocol_policy = "redirect-to-https"
    cache_policy_id        = aws_cloudfront_cache_policy.custom_domains.id
    compress               = true

    allowed_methods {
      items          = ["GET", "HEAD"]
      cached_methods = ["GET", "HEAD"]
    }

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.custom_domains_index_rewrite.arn
    }
  }

  # No response_page_path: the origin path would resolve it to /{slug}/404.html,
  # which tenants do not have. Missing objects (S3 403 via OAC) become a 404.
  custom_error_response {
    error_code            = 403
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Distribution-level cert is required by the API; tenants each use their own
  # CloudFront-managed certificate. The backend rejects *.jabaki.nl as a
  # custom domain, so this wildcard never serves a tenant.
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.jabaki_wildcard.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tenant_config {
    parameter_definition {
      name = "slug"
      definition {
        string_schema {
          required = true
          comment  = "Tenant slug = top-level folder in the public-pages bucket"
        }
      }
    }
  }

  tags = {
    Name        = "myAdmin-Custom-Domains-CDN-Nonprofit"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "custom-domain-delivery"
  }
}

output "custom_domains_distribution_id" {
  description = "Railway env CLOUDFRONT_CUSTOM_DOMAINS_DISTRIBUTION_ID"
  value       = aws_cloudfront_multitenant_distribution.custom_domains.id
}
