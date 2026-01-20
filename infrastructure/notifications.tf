# AWS User Notifications Configuration
# This file sets up AWS SNS for email notifications

# SNS Topic for Application Notifications
resource "aws_sns_topic" "myadmin_notifications" {
  name              = "myadmin-notifications"
  display_name      = "MyAdmin Application Notifications"
  fifo_topic        = false
  
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
          AWS = aws_iam_role.myadmin_ec2_role.arn
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

# Email Subscription (replace with your email)
resource "aws_sns_topic_subscription" "admin_email" {
  topic_arn = aws_sns_topic.myadmin_notifications.arn
  protocol  = "email"
  endpoint  = var.admin_email
  
  # Note: Email subscriptions require manual confirmation
}

# Additional email subscriptions can be added
variable "admin_email" {
  description = "Admin email address for notifications"
  type        = string
  default     = "peter@pgeers.nl"
}

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

# IAM Role for EC2 to access SNS
resource "aws_iam_role" "myadmin_ec2_role" {
  name = "myadmin-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "myAdmin-EC2-Role"
  }
}

# IAM Policy for SNS Access
resource "aws_iam_role_policy" "myadmin_sns_policy" {
  name = "myadmin-sns-policy"
  role = aws_iam_role.myadmin_ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish",
          "sns:Subscribe",
          "sns:ListTopics",
          "sns:GetTopicAttributes"
        ]
        Resource = aws_sns_topic.myadmin_notifications.arn
      }
    ]
  })
}

# Instance Profile for EC2
resource "aws_iam_instance_profile" "myadmin_profile" {
  name = "myadmin-instance-profile"
  role = aws_iam_role.myadmin_ec2_role.name
}

# Update EC2 instance to use the IAM role
resource "aws_instance" "myadmin_backend_with_notifications" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t3.small"
  key_name      = var.key_name
  
  vpc_security_group_ids = [aws_security_group.myadmin_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.myadmin_profile.name
  
  user_data = base64encode(templatefile("${path.module}/user-data.sh", {
    domain_name           = var.domain_name
    sns_topic_arn         = aws_sns_topic.myadmin_notifications.arn
    aws_region            = var.aws_region
  }))
  
  tags = {
    Name        = "myAdmin-Backend"
    Environment = "Production"
  }
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
