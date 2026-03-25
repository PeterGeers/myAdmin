# AWS SES Configuration for myAdmin
# Manages domain verification and email sending for user-facing emails
# (invitation emails, password resets, etc.)
# SNS remains for admin notifications (see notifications.tf)

# SES Domain Identity — jabaki.nl
resource "aws_ses_domain_identity" "jabaki" {
  domain = var.ses_domain
}

# SES Domain DKIM — generates DKIM tokens for email signing
resource "aws_ses_domain_dkim" "jabaki" {
  domain = aws_ses_domain_identity.jabaki.domain
}

# Variables
variable "ses_domain" {
  description = "Domain for SES email sending"
  type        = string
  default     = "jabaki.nl"
}

variable "ses_sender_email" {
  description = "Sender email address for user-facing emails"
  type        = string
  default     = "support@jabaki.nl"
}

# Outputs
output "ses_domain_verification_token" {
  description = "TXT record value for domain verification"
  value       = aws_ses_domain_identity.jabaki.verification_token
}

output "ses_dkim_tokens" {
  description = "DKIM CNAME tokens (add to DNS)"
  value       = aws_ses_domain_dkim.jabaki.dkim_tokens
}

output "ses_sender_email" {
  description = "Configured sender email"
  value       = var.ses_sender_email
}

output "ses_setup_instructions" {
  value = <<-EOT

    ========================================
    AWS SES Email Setup
    ========================================

    Domain: ${var.ses_domain}
    Sender: ${var.ses_sender_email}

    DNS Records Required (at Squarespace):
    ---------------------------------------
    1. TXT record:
       Host: _amazonses
       Value: ${aws_ses_domain_identity.jabaki.verification_token}

    2. DKIM CNAME records (3):
       ${join("\n       ", [for token in aws_ses_domain_dkim.jabaki.dkim_tokens : "${token}._domainkey -> ${token}.dkim.amazonses.com"])}

    Backend env var:
       SES_SENDER_EMAIL=${var.ses_sender_email}

    Note: SES is in sandbox mode (200 emails/day).
    Request production access when needed.

  EOT
}
