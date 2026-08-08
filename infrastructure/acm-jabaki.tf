# ACM Wildcard Certificate for *.jabaki.nl
# Must be in us-east-1 for CloudFront integration.
# DNS validation via Route 53 hosted zone.

# ============================================================================
# ACM Certificate — *.jabaki.nl (us-east-1)
# ============================================================================

resource "aws_acm_certificate" "jabaki_wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.jabaki.nl"
  validation_method = "DNS"

  tags = {
    Name        = "jabaki-wildcard-cert"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================================================
# DNS Validation Record(s) in Route 53
# ============================================================================

resource "aws_route53_record" "jabaki_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.jabaki_wildcard.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = aws_route53_zone.jabaki.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

# ============================================================================
# Certificate Validation — waits for ACM to confirm issuance
# ============================================================================

resource "aws_acm_certificate_validation" "jabaki_wildcard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.jabaki_wildcard.arn
  validation_record_fqdns = [for record in aws_route53_record.jabaki_cert_validation : record.fqdn]
}

# ============================================================================
# Outputs
# ============================================================================

output "jabaki_wildcard_cert_arn" {
  description = "ARN of the *.jabaki.nl wildcard certificate (us-east-1)"
  value       = aws_acm_certificate.jabaki_wildcard.arn
}
