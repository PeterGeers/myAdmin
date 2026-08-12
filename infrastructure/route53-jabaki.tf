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

# ============================================================================
# Stripe Custom Email Domain — DNS Records
# Required for sending emails from jabaki.nl via Stripe
# ============================================================================

# --- DMARC TXT record for Stripe email ---
resource "aws_route53_record" "jabaki_dmarc" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "_dmarc.jabaki.nl"
  type    = "TXT"
  ttl     = 300

  records = [
    "v=DMARC1; p=none; rua=mailto:info@jabaki.nl",
  ]
}

# --- Stripe bounce CNAME record ---
resource "aws_route53_record" "jabaki_stripe_bounce" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "bounce.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "custom-email-domain.stripe.com.",
  ]
}

# --- Stripe DKIM CNAME records (6 keys) ---
resource "aws_route53_record" "jabaki_stripe_dkim_1" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "zpbrq275kmdm65oiflue2a7eswh3bmdg._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "zpbrq275kmdm65oiflue2a7eswh3bmdg.dkim.custom-email-domain.stripe.com.",
  ]
}

resource "aws_route53_record" "jabaki_stripe_dkim_2" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "o3wj7w2mbytvfbc33xg2opadgyakwyay._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "o3wj7w2mbytvfbc33xg2opadgyakwyay.dkim.custom-email-domain.stripe.com.",
  ]
}

resource "aws_route53_record" "jabaki_stripe_dkim_3" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "d55ffqy3lk5ubilpdnvzjrqb2fe7h6gf._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "d55ffqy3lk5ubilpdnvzjrqb2fe7h6gf.dkim.custom-email-domain.stripe.com.",
  ]
}

resource "aws_route53_record" "jabaki_stripe_dkim_4" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "zsshb7kskblnjoxfuweyqvi6aceylzvn._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "zsshb7kskblnjoxfuweyqvi6aceylzvn.dkim.custom-email-domain.stripe.com.",
  ]
}

resource "aws_route53_record" "jabaki_stripe_dkim_5" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "mztktdox2gzkjo4ima4um24ibexrxlov._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "mztktdox2gzkjo4ima4um24ibexrxlov.dkim.custom-email-domain.stripe.com.",
  ]
}

resource "aws_route53_record" "jabaki_stripe_dkim_6" {
  zone_id = aws_route53_zone.jabaki.zone_id
  name    = "csdvp64vsm3xfkcqdfyr2y4vtx3fjb2d._domainkey.jabaki.nl"
  type    = "CNAME"
  ttl     = 300

  records = [
    "csdvp64vsm3xfkcqdfyr2y4vtx3fjb2d.dkim.custom-email-domain.stripe.com.",
  ]
}

# ============================================================================
# SES Records
# ============================================================================

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
