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

  # Multi-tenant support: JSON array of tenant names
  schema {
    name                = "tenants"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 0
      max_length = 2048 # Support up to 100 tenants in JSON array
    }
  }

  # User preferred language (e.g. "en", "nl")
  schema {
    name                = "preferred_language"
    attribute_data_type = "String"
    mutable             = true

    string_attribute_constraints {
      min_length = 2
      max_length = 5
    }
  }

  # Email configuration — use SES for better deliverability
  # Sends password reset / verification emails from support@jabaki.nl
  # instead of no-reply@verificationemail.com (which lands in spam)
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = "arn:aws:ses:${var.aws_region}:344561557829:identity/support@jabaki.nl"
    from_email_address    = "myAdmin <support@jabaki.nl>"
  }

  # MFA disabled to enable passkeys (Decision 1.1)
  # Passkeys are inherently multi-factor (device possession + biometric/PIN)
  mfa_configuration = "OFF"

  # User pool add-ons — ENFORCED required for choice-based auth (USER_AUTH / passkeys)
  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  # NOTE: SignInPolicy.AllowedFirstAuthFactors (PASSWORD + WEB_AUTHN) is not yet
  # supported by the Terraform AWS provider. It must be set via AWS CLI after apply:
  #
  #   aws cognito-idp update-user-pool \
  #     --user-pool-id eu-west-1_Hdp40eWmu \
  #     --region eu-west-1 \
  #     --policies "SignInPolicy={AllowedFirstAuthFactors=[PASSWORD,WEB_AUTHN]}"
  #
  # This enables choice-based sign-in with passkey support.

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

  # Auth flows for choice-based sign-in (Task 1.3 — passkey + password support)
  explicit_auth_flows = [
    "ALLOW_USER_AUTH",         # Choice-based (passkey + password)
    "ALLOW_USER_SRP_AUTH",     # Password with SRP (existing)
    "ALLOW_REFRESH_TOKEN_AUTH" # Token refresh
  ]

  # OAuth settings
  generate_secret                      = false # Public client for browser apps
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"] # Authorization code flow with PKCE
  allowed_oauth_scopes                 = ["email", "openid", "profile"]

  # Callback URLs
  callback_urls = [
    "http://localhost:3000/",
    "http://localhost:3000/callback",
    "http://localhost:5000/",
    "http://localhost:5000/callback",
    "https://petergeers.github.io/myAdmin/", # Production (GitHub Pages)
    "https://petergeers.github.io/myAdmin/callback"
  ]

  logout_urls = [
    "http://localhost:3000/",
    "http://localhost:3000/logout",
    "http://localhost:5000/",
    "http://localhost:5000/logout",
    "https://petergeers.github.io/myAdmin/", # Production (GitHub Pages)
    "https://petergeers.github.io/myAdmin/logout"
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
    "custom:role",
    "custom:tenants"
  ]

  write_attributes = [
    "email",
    "name",
    "custom:tenant_id",
    "custom:tenant_name",
    "custom:role",
    "custom:tenants"
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
# Tenant Admin Group (for multi-tenant support)
resource "aws_cognito_user_group" "tenant_admin" {
  name         = "Tenant_Admin"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Tenant administrator - can manage tenant config, users, and secrets for assigned tenants"
  precedence   = 4
}

# Module-based groups for RBAC
resource "aws_cognito_user_group" "finance_read" {
  name         = "Finance_Read"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Read-only access to financial data (invoices, transactions, reports)"
  precedence   = 10
}

resource "aws_cognito_user_group" "finance_crud" {
  name         = "Finance_CRUD"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Full access to financial data - create, read, update, delete"
  precedence   = 9
}

resource "aws_cognito_user_group" "finance_export" {
  name         = "Finance_Export"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Permission to export financial data and reports"
  precedence   = 11
}

resource "aws_cognito_user_group" "str_read" {
  name         = "STR_Read"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Read-only access to short-term rental data (bookings, pricing, reports)"
  precedence   = 20
}

resource "aws_cognito_user_group" "str_crud" {
  name         = "STR_CRUD"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Full access to STR data - create, read, update, delete bookings and pricing"
  precedence   = 19
}

resource "aws_cognito_user_group" "str_export" {
  name         = "STR_Export"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "Permission to export STR data and reports"
  precedence   = 21
}

resource "aws_cognito_user_group" "sysadmin" {
  name         = "SysAdmin"
  user_pool_id = aws_cognito_user_pool.myadmin.id
  description  = "System administration - logs, config, templates (no tenant data access)"
  precedence   = 5
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
