# IAM User for Railway Backend Service
# Dedicated least-privilege user replacing the broad "WebMaster" account.
# Only grants the permissions the myAdmin backend actually needs.

# ============================================================================
# IAM User
# ============================================================================

resource "aws_iam_user" "railway_backend" {
  name = "myadmin-railway-backend"
  path = "/service-accounts/"

  tags = {
    Name        = "myAdmin-Railway-Backend"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Purpose     = "railway-backend-service"
  }
}

# Access key for Railway environment variables
resource "aws_iam_access_key" "railway_backend" {
  user = aws_iam_user.railway_backend.name
}

# ============================================================================
# Policy Attachments — Existing Scoped Policies
# ============================================================================

# S3 shared bucket (invoices, branding, templates)
resource "aws_iam_user_policy_attachment" "railway_s3_shared" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.s3_shared_access.arn
}

# S3 public pages write (landing page publish/unpublish)
resource "aws_iam_user_policy_attachment" "railway_s3_public_pages" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.s3_public_pages_write.arn
}

# DynamoDB landing pages (CRUD on myadmin-landing-pages table)
resource "aws_iam_user_policy_attachment" "railway_dynamodb_landing_pages" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.dynamodb_landing_pages.arn
}

# ============================================================================
# Cognito User Pool Management — scoped to the myAdmin pool
# ============================================================================

resource "aws_iam_policy" "cognito_user_management" {
  name        = "myadmin-cognito-user-management-${var.environment}"
  description = "Cognito user management for myAdmin backend (admin operations on the myAdmin pool)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCognitoUserManagement"
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminDeleteUser",
          "cognito-idp:AdminEnableUser",
          "cognito-idp:AdminDisableUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:AdminUpdateUserAttributes",
          "cognito-idp:AdminAddUserToGroup",
          "cognito-idp:AdminRemoveUserFromGroup",
          "cognito-idp:AdminListGroupsForUser",
          "cognito-idp:ListUsers",
          "cognito-idp:ListUsersInGroup",
          "cognito-idp:CreateGroup",
          "cognito-idp:DeleteGroup",
          "cognito-idp:UpdateGroup",
          "cognito-idp:ListGroups"
        ]
        Resource = aws_cognito_user_pool.myadmin.arn
      }
    ]
  })

  tags = {
    Name        = "myAdmin-Cognito-User-Management"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_user_policy_attachment" "railway_cognito" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.cognito_user_management.arn
}

# ============================================================================
# SNS — Publish notifications
# ============================================================================

resource "aws_iam_policy" "sns_publish" {
  name        = "myadmin-sns-publish-${var.environment}"
  description = "SNS publish access for myAdmin backend notifications"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSNSPublish"
        Effect = "Allow"
        Action = [
          "sns:Publish",
          "sns:GetTopicAttributes"
        ]
        Resource = aws_sns_topic.myadmin_notifications.arn
      }
    ]
  })

  tags = {
    Name        = "myAdmin-SNS-Publish"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_user_policy_attachment" "railway_sns" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.sns_publish.arn
}

# ============================================================================
# SES — Email sending and identity verification
# ============================================================================

resource "aws_iam_policy" "ses_email_sending" {
  name        = "myadmin-ses-email-sending-${var.environment}"
  description = "SES email sending for myAdmin backend (transactional emails, identity verification)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSESSendEmail"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = [
          "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_domain}",
          "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:configuration-set/${aws_ses_configuration_set.myadmin_emails.name}"
        ]
      },
      {
        Sid    = "AllowSESIdentityVerification"
        Effect = "Allow"
        Action = [
          "ses:VerifyEmailIdentity",
          "ses:GetIdentityVerificationAttributes"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name        = "myAdmin-SES-Email-Sending"
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_user_policy_attachment" "railway_ses" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.ses_email_sending.arn
}

resource "aws_iam_user_policy_attachment" "railway_cloudfront_invalidation" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.cloudfront_invalidation.arn
}

# Custom domains management (ACM certificates, CloudFront distribution updates, KVS)
resource "aws_iam_user_policy_attachment" "railway_custom_domains" {
  user       = aws_iam_user.railway_backend.name
  policy_arn = aws_iam_policy.custom_domains_management.arn
}

# ============================================================================
# Outputs
# ============================================================================

output "railway_backend_user_name" {
  description = "IAM user name for the Railway backend service"
  value       = aws_iam_user.railway_backend.name
}

output "railway_backend_user_arn" {
  description = "IAM user ARN for the Railway backend service"
  value       = aws_iam_user.railway_backend.arn
}

output "railway_backend_access_key_id" {
  description = "Access Key ID for the Railway backend (set as AWS_ACCESS_KEY_ID in Railway)"
  value       = aws_iam_access_key.railway_backend.id
}

output "railway_backend_secret_access_key" {
  description = "Secret Access Key for the Railway backend (set as AWS_SECRET_ACCESS_KEY in Railway)"
  value       = aws_iam_access_key.railway_backend.secret
  sensitive   = true
}

output "railway_backend_credential_instructions" {
  description = "Instructions for rotating Railway credentials"
  value       = <<-EOT

    ========================================
    Railway Backend IAM User Created
    ========================================

    User: myadmin-railway-backend
    Path: /service-accounts/

    Attached policies:
      - myadmin-s3-shared-access-${var.environment}
      - myadmin-s3-public-pages-write-${var.environment}
      - myadmin-dynamodb-landing-pages-${var.environment}
      - myadmin-cognito-user-management-${var.environment}
      - myadmin-sns-publish-${var.environment}
      - myadmin-ses-email-sending-${var.environment}

    To get the credentials for Railway:
      terraform output railway_backend_access_key_id
      terraform output -raw railway_backend_secret_access_key

    Then update Railway env vars:
      AWS_ACCESS_KEY_ID=<access_key_id>
      AWS_SECRET_ACCESS_KEY=<secret_access_key>

    After verifying Railway works with new credentials,
    clean up the WebMaster user:
      aws iam delete-user-policy --user-name WebMaster --policy-name DynamoDBDeveloper
      aws iam detach-user-policy --user-name WebMaster --policy-arn arn:aws:iam::344561557829:policy/myadmin-s3-shared-access-production
      aws iam detach-user-policy --user-name WebMaster --policy-arn arn:aws:iam::344561557829:policy/myadmin-s3-public-pages-write-production
      aws iam detach-user-policy --user-name WebMaster --policy-arn arn:aws:iam::344561557829:policy/myadmin-dynamodb-landing-pages-production

  EOT
}
