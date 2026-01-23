# AWS User Notifications Configuration
# This file sets up AWS SNS for email notifications

# SNS Topic for Application Notifications
resource "aws_sns_topic" "myadmin_notifications" {
  name         = "myadmin-notifications"
  display_name = "MyAdmin Application Notifications"
  fifo_topic   = false

  tags = {
    Name        = "myAdmin-Notifications"
    Environment = "Production"
    Application = "myAdmin"
  }
}

# SNS Topic Policy
resource "aws_sns_topic_policy" "myadmin_notifications_policy" {
  arn = aws_sns_topic.myadmin_notifications.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPublishFromApplication"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "SNS:Publish",
          "SNS:Subscribe"
        ]
        Resource = aws_sns_topic.myadmin_notifications.arn
      }
    ]
  })
}

# Email Subscription
resource "aws_sns_topic_subscription" "admin_email" {
  topic_arn = aws_sns_topic.myadmin_notifications.arn
  protocol  = "email"
  endpoint  = var.admin_email

  # Note: Email subscriptions require manual confirmation
}

# Additional email subscriptions can be added
variable "additional_notification_emails" {
  description = "Additional email addresses for notifications"
  type        = list(string)
  default     = []
}

resource "aws_sns_topic_subscription" "additional_emails" {
  count     = length(var.additional_notification_emails)
  topic_arn = aws_sns_topic.myadmin_notifications.arn
  protocol  = "email"
  endpoint  = var.additional_notification_emails[count.index]
}

# Outputs
output "sns_topic_arn" {
  description = "ARN of the SNS topic for notifications"
  value       = aws_sns_topic.myadmin_notifications.arn
}

output "sns_topic_name" {
  description = "Name of the SNS topic"
  value       = aws_sns_topic.myadmin_notifications.name
}

output "notification_setup_instructions" {
  value = <<-EOT
    
    ========================================
    AWS User Notifications Setup Complete!
    ========================================
    
    SNS Topic ARN: ${aws_sns_topic.myadmin_notifications.arn}
    
    IMPORTANT: Email Confirmation Required
    ---------------------------------------
    1. Check your email inbox (${var.admin_email})
    2. Look for "AWS Notification - Subscription Confirmation"
    3. Click the confirmation link
    
    After confirmation, your application can send notifications!
    
    Test the notification:
    aws sns publish \
      --topic-arn ${aws_sns_topic.myadmin_notifications.arn} \
      --message "Test notification from myAdmin" \
      --subject "Test: myAdmin Notification" \
      --region ${var.aws_region}
    
  EOT
}
