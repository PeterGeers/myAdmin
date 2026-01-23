# AWS Cognito User Pool for myAdmin
# This creates a complete authentication system with user management

# User Pool
resource "aws_cognito_user_pool" "myadmin" {
  name = "myAdmin"

  # Username configuration
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Password policy
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # User attributes schema
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = false

    string_attribute_constraints {
      min_length = 5
      max_length = 255
    }
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 255
    }
  }

  # Custom attributes for multi-tenant support
  schema {
    name                = "tenant_id"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 0
      max_length = 50
    }
  }

  schema {
    name                = "tenant_name"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 0
      max_length = 100
    }
  }

  schema {
    name                = "role"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 0
      max_length = 50
    }
  }

  # Email configuration
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # MFA configuration (optional but recommended)
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  # User pool add-ons
  user_pool_add_ons {
    advanced_security_mode = "AUDIT"
  }

  # Tags
  tags = {
    Name        = "myAdmin User Pool"
    Environment = "production"
    Project     = "myAdmin"
    ManagedBy   = "Terraform"
  }
}

# User Pool Client (App Client)
resource "aws_cognito_user_pool_client" "myadmin_client" {
  name         = "myAdmin-client"
  user_pool_id = aws_cognito_user_pool.myadmin.id

  # OAuth settings
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code", "implicit"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  
  # Callback URLs (update these for your deployment)
  callback_urls = [
    "http://localhost:3000/callback",
    "http://localhost:5000/callback",
    "https://your-railway-app.railway.app/callback"
  ]

  logout_urls = [
    "http://localhost:3000/logout",
    "http://localhost:5000/logout",
    "https://your-railway-app.railway.app/logout"
  ]

  # Supported identity providers
  supported_identity_providers = ["COGNITO"]

  # Token validity
  refresh_token_validity = 30
  access_token_validity  = 60
  id_token_validity      = 60

  token_validity_units {
    refresh_token = "days"
    access_token  = "minutes"
    id_token      = "minutes"
  }

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # Read and write attributes
  read_attributes = [
    "email",
    "email_verified",
    "name",
    "custom:tenant_id",
    "custom:tenant_name",
    "custom:role"
  ]

  write_attributes = [
    "email",
    "name",
    "custom:tenant_id",
    "custom:tenant_name",
    "custom:role"
  ]
}

# User Pool Domain (for hosted UI)
resource "aws_cognito_user_pool_domain" "myadmin" {
  domain       = "myadmin-${random_string.domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.myadmin.id
}

# Random string for unique domain
resource "random_string" "domain_suffix" {
  length  = 8
  special = false
  upper   = false
}

# User Groups
resource "aws_cognito_user_group" "administrators" {
  name         = "Administrators"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Full system access - can manage users, settings, and all data"
  precedence   = 1
}

resource "aws_cognito_user_group" "accountants" {
  name         = "Accountants"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Can manage financial data, invoices, and reports"
  precedence   = 2
}

resource "aws_cognito_user_group" "viewers" {
  name         = "Viewers"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Read-only access to reports and data"
  precedence   = 3
}

# Outputs
output "cognito_user_pool_id" {
  description = "The ID of the Cognito User Pool"
  value       = aws_cognito_user_pool.myadmin.id
}

output "cognito_user_pool_arn" {
  description = "The ARN of the Cognito User Pool"
  value       = aws_cognito_user_pool.myadmin.arn
}

output "cognito_client_id" {
  description = "The ID of the Cognito User Pool Client"
  value       = aws_cognito_user_pool_client.myadmin_client.id
}

output "cognito_client_secret" {
  description = "The secret of the Cognito User Pool Client"
  value       = aws_cognito_user_pool_client.myadmin_client.client_secret
  sensitive   = true
}

output "cognito_domain" {
  description = "The Cognito hosted UI domain"
  value       = aws_cognito_user_pool_domain.myadmin.domain
}

output "cognito_hosted_ui_url" {
  description = "The Cognito hosted UI URL"
  value       = "https://${aws_cognito_user_pool_domain.myadmin.domain}.auth.${var.aws_region}.amazoncognito.com"
}
