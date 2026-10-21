# Application Form — Embed enforcement (CSP frame-ancestors)
# ---------------------------------------------------------------------------
# The tenant application form is hosted on the SAME landing-page CloudFront
# pattern (S3 `public_pages` + the `public_pages` distribution, served under
# `*.jabaki.nl`, e.g. `tenant-member-application.jabaki.nl`). It is therefore
# ALREADY served by the existing distribution + the `public_pages_url_rewrite`
# viewer-request function in `landing-pages.tf` — no new S3 bucket, distribution,
# or hosting is required here.
#
# This file adds ONLY the embed-origin enforcement for that hosted form:
#   - a dedicated CloudFront KeyValueStore mapping form host -> allowed embed
#     origins (mirrors the `myadmin-domain-slug-mapping` KVS precedent), and
#   - a `viewer-response` CloudFront function that reads that KVS at the edge
#     and sets `Content-Security-Policy: frame-ancestors <tenant origins>` on
#     the response, controlling who may put the form in an <iframe>.
#
# The ONE tenant-authored list `application_embed_origins` (authored onto
# `config#mail` via `PUT /members/config/mail`, task 5.1) feeds this KVS; the
# same list also feeds the SAM public-API CORS (task 5.3) — two distinct
# enforcement points, one source of truth (design.md §2.3, §6, §9 S3).
#
# Standalone (no origins configured) => NO frame-ancestors header is emitted,
# i.e. the form is NOT embeddable (browser default: top-level navigation only;
# equivalently `frame-ancestors 'none'`). See design.md §10 and task 5.2.
#
# NOT deployed by the task author — deployment is codified (steering 43).

# ============================================================================
# CloudFront KeyValueStore — Form Host -> Allowed Embed Origins
# ============================================================================
# Mirrors `aws_cloudfront_key_value_store.domain_mapping` in landing-pages.tf.
# Key   = the form's public host (e.g. "tenant-member-application.jabaki.nl")
# Value = space-separated list of allowed embed origins, exactly as they must
#         appear in a CSP `frame-ancestors` directive
#         (e.g. "https://www.acme.nl https://portal.acme.nl").
# Populated by the backend from `application_embed_origins` (same write path
# as the domain->slug mapping; see CloudFrontDomainService).

resource "aws_cloudfront_key_value_store" "application_embed_origins" {
  name    = "myadmin-application-embed-origins"
  comment = "Maps the application-form host to its tenant-authored allowed embed origins (CSP frame-ancestors)"
}

# ============================================================================
# CloudFront Function — viewer-response: set CSP frame-ancestors
# ============================================================================
# Reads the request host's allowed embed origins from the KVS and sets the
# Content-Security-Policy `frame-ancestors` directive on the response. When the
# host has no configured origins (standalone), the header is omitted entirely
# so the form is not embeddable. Pure string logic — no network call at the
# edge beyond the <1ms KVS read (mirrors `public_pages_url_rewrite`).

resource "aws_cloudfront_function" "application_form_frame_ancestors" {
  name    = "myadmin-application-form-frame-ancestors-${var.environment}"
  runtime = "cloudfront-js-2.0"
  comment = "Sets CSP frame-ancestors on the application form response from the tenant's application_embed_origins (KVS)"
  publish = true

  key_value_store_associations = [aws_cloudfront_key_value_store.application_embed_origins.arn]

  code = <<-EOF
    import cf from 'cloudfront';

    // KVS binding — associated via Terraform key_value_store_associations.
    // Key = form host; Value = space-separated allowed embed origins.
    var kvsId = '${aws_cloudfront_key_value_store.application_embed_origins.id}';
    var kvs;
    try {
      kvs = cf.kvs(kvsId);
    } catch (err) {
      // KVS not available — fail closed (no frame-ancestors header set).
    }

    async function handler(event) {
      var request = event.request;
      var response = event.response;
      var host = request.headers.host ? request.headers.host.value : '';

      if (!kvs || !host) {
        // Fail closed: standalone / no lookup possible -> not embeddable.
        return response;
      }

      var origins;
      try {
        origins = await kvs.get(host);
      } catch (e) {
        // Key not found or lookup failed -> standalone, no header.
        return response;
      }

      // Normalise: collapse whitespace, drop empties.
      var list = (origins || '')
        .split(/\s+/)
        .filter(function (o) { return o.length > 0; });

      if (list.length === 0) {
        // No configured origins -> standalone, omit the header (not embeddable).
        return response;
      }

      var directive = 'frame-ancestors ' + list.join(' ');
      response.headers['content-security-policy'] = { value: directive };

      return response;
    }
  EOF
}

# ============================================================================
# IAM Policy — Backend access to the embed-origins KVS (Railway)
# ============================================================================
# Lets the backend populate/clear the form-host -> embed-origins mapping when a
# tenant authors `application_embed_origins`. Mirrors the KVS statement in
# `aws_iam_policy.custom_domains_management` (landing-pages.tf).

resource "aws_iam_policy" "application_embed_origins_kvs" {
  name        = "myadmin-application-embed-origins-kvs-${var.environment}"
  description = "CloudFront KeyValueStore access for the application-form embed-origins (CSP frame-ancestors) mapping"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ApplicationEmbedOriginsKVS"
        Effect = "Allow"
        Action = [
          "cloudfront-keyvaluestore:GetKey",
          "cloudfront-keyvaluestore:PutKey",
          "cloudfront-keyvaluestore:DeleteKey",
          "cloudfront-keyvaluestore:ListKeys",
          "cloudfront-keyvaluestore:DescribeKeyValueStore"
        ]
        Resource = aws_cloudfront_key_value_store.application_embed_origins.arn
      }
    ]
  })

  tags = {
    Name        = "myAdmin-Application-Embed-Origins-KVS"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# ============================================================================
# Outputs
# ============================================================================

output "cloudfront_application_embed_origins_kvs_arn" {
  description = "ARN of the CloudFront KeyValueStore mapping the form host to its allowed embed origins (CSP frame-ancestors)"
  value       = aws_cloudfront_key_value_store.application_embed_origins.arn
}

output "cloudfront_application_form_frame_ancestors_function_arn" {
  description = "ARN of the viewer-response CloudFront function that sets CSP frame-ancestors on the application form"
  value       = aws_cloudfront_function.application_form_frame_ancestors.arn
}

output "application_embed_origins_kvs_policy_arn" {
  description = "ARN of the IAM policy for backend access to the application embed-origins KVS"
  value       = aws_iam_policy.application_embed_origins_kvs.arn
}
