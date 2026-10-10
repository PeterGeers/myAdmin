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
  # Email configuration — using Cognito default sender
  # To use custom SES sender (support@jabaki.nl), verify the identity in SES first
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # MFA disabled to enable passkeys (Decision 1.1)
  # Passkeys are inherently multi-factor (device possession + biometric/PIN)
  mfa_configuration = "OFF"

  # NOTE: advanced_security_mode = "ENFORCED" was removed because it requires
  # Cognito Plus tier. If passkeys/WebAuthn are needed later, upgrade the tier first.

  # NOTE: SignInPolicy.AllowedFirstAuthFactors (PASSWORD + WEB_AUTHN) and the
  # WebAuthn RelyingPartyId are not supported by the Terraform AWS provider yet.
  # They are asserted via AWS CLI after apply by the
  # null_resource.cognito_passkey_post_apply below (idempotent, re-runs on every
  # apply), so they no longer need a manual step and can't silently revert.

  # Tags
  tags = {
    Name        = "myAdmin User Pool"
    Environment = "production"
    Project     = "myAdmin"
    ManagedBy   = "Terraform"
  }

  # Two parts of this pool are owned OUTSIDE Terraform — on purpose — so Terraform
  # must NOT try to manage (and therefore DELETE) them. Without this block,
  # `terraform plan` shows a destructive diff that would break production:
  #
  #   - lambda_config (Pre-Token-Generation trigger):
  #       The V2 PreTokenGen trigger points at a Lambda in the DATA account
  #       (nonprofit-deploy 506221081911), deployed by sam/pretokengen + CI. The
  #       trigger is attached to the pool as a deliberate MANUAL, once-per-pool step
  #       in the IDENTITY account (the SAM pipeline has no creds there). This is by
  #       design — see sam/pretokengen/DEPLOY.md and spec s5e R5. Terraform never
  #       sees it in config, so it would otherwise plan to detach it, stripping the
  #       `custom:entitlements` claim from every token (platform-wide auth breakage).
  #
  #   - web_authn_configuration (passkey Relying Party ID):
  #       Not exposed by the Terraform AWS provider; owned by
  #       null_resource.cognito_passkey_post_apply below (set via AWS CLI). Without
  #       ignoring it here, Terraform plans to null it out, reintroducing the
  #       `RelyingPartyMismatch` passkey bug (see
  #       .kiro/specs/Common/Cognito/PassKey/findings.md F-002).
  #
  # ignore_changes makes Terraform leave both untouched on refresh/plan/apply while
  # still managing everything else about the pool.
  lifecycle {
    ignore_changes = [
      lambda_config,
      web_authn_configuration,
    ]
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

# ---------------------------------------------------------------------------
# Post-apply Cognito CLI steps (NOT expressible in the Terraform AWS provider)
# ---------------------------------------------------------------------------
# Two pool settings the provider does not expose must be asserted via AWS CLI
# after the pool exists. This null_resource re-runs them on every `terraform
# apply` and whenever the pool, app client, or the RP ID input changes, so they
# can no longer silently revert:
#
#   1. SignInPolicy.AllowedFirstAuthFactors = [PASSWORD, WEB_AUTHN]
#      Enables choice-based sign-in (password + passkey).
#
#   2. WebAuthn RelyingPartyId = var.passkey_relying_party_id
#      Without this, Cognito defaults the RP ID to the hosted-UI domain
#      (myadmin-*.auth.<region>.amazoncognito.com). Because the app registers
#      passkeys directly (Amplify associateWebAuthnCredential) from its own host,
#      the browser then throws `RelyingPartyMismatch: Relying party does not match
#      current domain`. See .kiro/specs/Common/Cognito/PassKey/tasks.md §1.4a and
#      .kiro/specs/Common/Cognito/PassKey/findings.md F-002. UserVerification=preferred
#      matches the app's CredentialCreationOptions.
#
# Both commands are idempotent (set-to-desired-state), so re-running is safe.
#
# ⚠️ CRITICAL — `update-user-pool` REPLACES THE WHOLE POOL CONFIG, not just the
# flags you pass. In particular it REPLACES `LambdaConfig`. If you call it with
# only `--policies` (no `--lambda-config`), it BLANKS the Pre-Token-Generation
# trigger — detaching the data-account PreTokenGen Lambda and stripping the
# `custom:entitlements` claim from every token (platform-wide auth breakage).
# This exact mistake happened once (2026-10-07) and had to be recovered by
# re-attaching the trigger (see .kiro/specs/Common/Cognito/PassKey/findings.md
# F-003, and sam/pretokengen/DEPLOY.md "update-user-pool is picky: include
# settings that must persist"). Therefore step 1 below READS the current
# LambdaConfig and PASSES IT BACK UNCHANGED in the same call, so the trigger is
# preserved whether or not SAM/manual has attached it.
resource "null_resource" "cognito_passkey_post_apply" {
  triggers = {
    user_pool_id   = aws_cognito_user_pool.myadmin.id
    app_client_id  = aws_cognito_user_pool_client.myadmin_client.id
    relying_party  = var.passkey_relying_party_id
    cli_profile    = var.cognito_cli_profile
    aws_region     = var.aws_region
    # bump to force a re-apply of the CLI steps without other changes
    script_version = "2"
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail

      POOL_ID="${aws_cognito_user_pool.myadmin.id}"
      PROFILE="${var.cognito_cli_profile}"
      REGION="${var.aws_region}"

      # Preserve any externally-owned LambdaConfig (e.g. the PreTokenGen trigger,
      # owned by sam/pretokengen + a manual identity-account attach). Read it now
      # and pass it back UNCHANGED in the update below, so --policies does not
      # blank it. Defaults to {} if the pool has no triggers.
      CURRENT_LAMBDA_CONFIG="$(aws cognito-idp describe-user-pool \
        --user-pool-id "$POOL_ID" --profile "$PROFILE" --region "$REGION" \
        --query 'UserPool.LambdaConfig' --output json)"
      if [ -z "$CURRENT_LAMBDA_CONFIG" ] || [ "$CURRENT_LAMBDA_CONFIG" = "null" ]; then
        CURRENT_LAMBDA_CONFIG='{}'
      fi
      echo "Preserving LambdaConfig: $CURRENT_LAMBDA_CONFIG"

      # 1) Choice-based first-auth factors (password + passkey).
      #    MUST pass --lambda-config too, or update-user-pool blanks the trigger.
      aws cognito-idp update-user-pool \
        --user-pool-id "$POOL_ID" \
        --policies 'SignInPolicy={AllowedFirstAuthFactors=[PASSWORD,WEB_AUTHN]}' \
        --lambda-config "$CURRENT_LAMBDA_CONFIG" \
        --profile "$PROFILE" \
        --region "$REGION"

      # 2) WebAuthn Relying Party ID — the recurring passkey fix (F-002).
      #    set-user-pool-mfa-config only touches MFA/WebAuthn, never LambdaConfig,
      #    so it is safe. mfa-configuration stays OFF (passkeys are inherently
      #    multi-factor; Decision 1.1). UserVerification matches the app's options.
      aws cognito-idp set-user-pool-mfa-config \
        --user-pool-id "$POOL_ID" \
        --mfa-configuration OFF \
        --web-authn-configuration 'RelyingPartyId=${var.passkey_relying_party_id},UserVerification=preferred' \
        --profile "$PROFILE" \
        --region "$REGION"

      # Verify the trigger survived (fail loud if it was lost).
      AFTER="$(aws cognito-idp describe-user-pool \
        --user-pool-id "$POOL_ID" --profile "$PROFILE" --region "$REGION" \
        --query 'UserPool.LambdaConfig' --output json)"
      if [ "$CURRENT_LAMBDA_CONFIG" != "{}" ] && ! echo "$AFTER" | grep -q 'PreTokenGeneration'; then
        echo "ERROR: PreTokenGen trigger was lost by this step. LambdaConfig now: $AFTER" >&2
        exit 1
      fi

      echo "Cognito passkey post-apply done: RP ID=${var.passkey_relying_party_id}; LambdaConfig preserved: $AFTER"
    EOT
  }
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
