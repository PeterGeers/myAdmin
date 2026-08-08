# Route 53 Hosted Zone for jabaki.nl
# Phase 0: Domain Migration — Step 1
# Creates the hosted zone so we can recreate DNS records before switching nameservers.

resource "aws_route53_zone" "jabaki" {
  name = "jabaki.nl"

  tags = {
    Name        = "jabaki.nl-zone"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# ============================================================================
# DNS Records — Recreate all existing jabaki.nl records
# Phase 0: Domain Migration — Step 2
# ============================================================================

# --- A record: jabaki.nl → CloudFront distribution (alias, replaces hardcoded IPs) ---
resource "aws_route53_record" "jabaki_a" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "jabaki.nl"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.public_pages.domain_name
    zone_id                = aws_cloudfront_distribution.public_pages.hosted_zone_id
    evaluate_target_health = false
  }
}

# --- AAAA record: jabaki.nl → CloudFront distribution (alias, replaces hardcoded IPv6) ---
resource "aws_route53_record" "jabaki_aaaa" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "jabaki.nl"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.public_pages.domain_name
    zone_id                = aws_cloudfront_distribution.public_pages.hosted_zone_id
    evaluate_target_health = false
  }
}

# --- Wildcard A record: *.jabaki.nl → CloudFront distribution (NEW for landing pages) ---
resource "aws_route53_record" "jabaki_wildcard" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "*.jabaki.nl"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.public_pages.domain_name
    zone_id                = aws_cloudfront_distribution.public_pages.hosted_zone_id
    evaluate_target_health = false
  }
}

# --- MX records: jabaki.nl → ImprovMX for email receiving ---
resource "aws_route53_record" "jabaki_mx" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "jabaki.nl"
  type    = "MX"
  ttl     = 14400

  records = [
    "10 mx1.improvmx.com",
    "20 mx2.improvmx.com",
  ]
}

# --- TXT records: SPF, Stripe verification, Google site verification ---
resource "aws_route53_record" "jabaki_txt" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "jabaki.nl"
  type    = "TXT"
  ttl     = 300

  records = [
    "v=spf1 ip4:62.221.252.160 a a:spf.spamexperts.axc.nl include:_spf.google.com include:spf.improvmx.com mx ~all",
    "stripe-verification=58202da3c4518a8f279cabab915236186ae53f4983eb9ddc7aee21fdcf56bb10",
    "google-site-verification=XuxXmfmMpIIhFKwMOYV5gpWUnwbVmsNY3tpWCCdar5g",
  ]
}

# --- SES domain verification TXT record ---
resource "aws_route53_record" "jabaki_ses_verification" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "_amazonses.jabaki.nl"
  type    = "TXT"
  ttl     = 300

  records = [
    aws_ses_domain_identity.jabaki.verification_token,
  ]
}

# --- SES DKIM CNAME records (3 tokens) ---
resource "aws_route53_record" "jabaki_ses_dkim" {
  for_each = toset(aws_ses_domain_dkim.jabaki.dkim_tokens)

  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "${each.value}._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "${each.value}.dkim.amazonses.com",
  ]
}

# ============================================================================
# Outputs — NS records for nameserver switch at Squarespace
# ============================================================================

output "jabaki_zone_id" {
  description = "Zone ID of the jabaki.nl hosted zone"
  value       = aws_route53_zone.jabaki.zone_id
}

output "jabaki_nameservers" {
  description = "NS records for jabaki.nl — set these as nameservers at Squarespace"
  value       = aws_route53_zone.jabaki.name_servers
}
