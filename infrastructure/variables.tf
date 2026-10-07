# Terraform Variables for myAdmin Infrastructure
# Note: aws_region and admin_email are defined in main.tf and notifications.tf
# This file contains additional variables for Cognito

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "myAdmin"
}

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be one of: dev, staging, production."
  }
}

# WebAuthn / passkey Relying Party ID. MUST equal the host the app is served from
# (the full host, e.g. "petergeers.github.io" — it CANNOT be "github.io", which is a
# Public Suffix List entry browsers reject as an RP ID). Change this in lockstep with
# the Cognito callback/logout URLs if the app ever moves to a custom domain.
# This is applied via a post-apply AWS CLI step (null_resource in cognito.tf) because
# the Terraform AWS provider does not expose the WebAuthn RP ID yet.
variable "passkey_relying_party_id" {
  description = "WebAuthn Relying Party ID — the host the app is served from"
  type        = string
  default     = "petergeers.github.io"
}

# AWS CLI profile used for the post-apply Cognito CLI steps (identity account —
# the Cognito pool lives in the personal account 344561557829 per steering 23).
variable "cognito_cli_profile" {
  description = "AWS CLI profile for post-apply Cognito CLI steps (identity account)"
  type        = string
  default     = "personal"
}
