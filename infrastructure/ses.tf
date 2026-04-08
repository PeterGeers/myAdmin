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

# ============================================================================
# SES Email Delivery Tracking (via SNS)
# ============================================================================
# Tracks delivery status (sent, delivered, bounced, complained) for all
# emails sent through SES. Events are published to a dedicated SNS topic,
# which forwards them to the backend webhook for logging in email_log table.

variable "backend_webhook_url" {
  description = "Backend URL for SES delivery notification webhook"
  type        = string
  default     = "https://myadmin-backend-production.up.railway.app/api/webhooks/ses"
}

# Dedicated SNS topic for SES delivery events (separate from app notifications)
resource "aws_sns_topic" "ses_delivery_notifications" {
  name         = "myadmin-ses-delivery"
  display_name = "myAdmin SES Delivery Notifications"

  tags = {
    Name        = "myAdmin-SES-Delivery"
    Environment = "Production"
    Application = "myAdmin"
  }
}

# Allow SES to publish to this SNS topic
resource "aws_sns_topic_policy" "ses_delivery_policy" {
  arn = aws_sns_topic.ses_delivery_notifications.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSESPublish"
        Effect = "Allow"
        Principal = {
          Service = "ses.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.ses_delivery_notifications.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# SES Configuration Set — groups email sending settings
resource "aws_ses_configuration_set" "myadmin_emails" {
  name = "myadmin-emails"
}

# Event destination: publish delivery events to SNS
resource "aws_ses_event_destination" "delivery_tracking" {
  name                   = "delivery-tracking"
  configuration_set_name = aws_ses_configuration_set.myadmin_emails.name
  enabled                = true

  matching_types = [
    "send",
    "delivery",
    "bounce",
    "complaint",
    "reject",
  ]

  sns_destination {
    topic_arn = aws_sns_topic.ses_delivery_notifications.arn
  }
}

# Subscribe the backend webhook to the SNS topic
resource "aws_sns_topic_subscription" "ses_webhook" {
  topic_arn = aws_sns_topic.ses_delivery_notifications.arn
  protocol  = "https"
  endpoint  = var.backend_webhook_url

  # Raw message delivery sends the SES notification JSON directly
  # instead of wrapping it in an SNS envelope
  raw_message_delivery = false
}

# Data source for account ID (used in SNS policy)
data "aws_caller_identity" "current" {}

# Outputs
output "ses_configuration_set_name" {
  description = "SES Configuration Set name — use in send_email calls"
  value       = aws_ses_configuration_set.myadmin_emails.name
}

output "ses_delivery_topic_arn" {
  description = "SNS topic ARN for SES delivery notifications"
  value       = aws_sns_topic.ses_delivery_notifications.arn
}

output "ses_delivery_setup_instructions" {
  value = <<-EOT

    ========================================
    SES Email Delivery Tracking Setup
    ========================================

    Configuration Set: ${aws_ses_configuration_set.myadmin_emails.name}
    SNS Topic: ${aws_sns_topic.ses_delivery_notifications.arn}
    Webhook: ${var.backend_webhook_url}

    Backend env var to add:
       SES_CONFIGURATION_SET=myadmin-emails

    The webhook subscription will auto-confirm via the
    /api/webhooks/ses endpoint's SubscriptionConfirmation handler.

  EOT
}
