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

# ============================================================================
# Public-pages hosting migration (spec: jabaki-hosting-migration-to-nonprofit)
# ----------------------------------------------------------------------------
# The published public-pages bucket + the *.jabaki.nl CloudFront distribution
# were MIGRATED out of this personal account (344561557829) into the NONPROFIT
# account (506221081911). Those resources are OWNED by the hosting-migration
# spec's Terraform (its `hosting.tf`), NOT by this personal-account root module
# — so we reference them here by VALUE (name / ARN), never with a cross-account
# `data` source or a hard-coded literal buried in a policy.
#
# This lets the personal-account publish IDENTITY (`myadmin-railway-backend`)
# be granted least-privilege, prefix-scoped write on the nonprofit bucket and
# `cloudfront:CreateInvalidation` on the nonprofit distribution (spec 14 Task
# 9.2 / SEC-8), reconciling the live CLI drift the hosting-migration findings
# recorded (the v2 identity policy that added the nonprofit bucket ARN).
#
# Defaults are the live nonprofit resources recorded in the hosting-migration
# findings. Override per-env via tfvars if they ever change.

variable "nonprofit_public_pages_bucket_name" {
  description = "Name of the NONPROFIT-account public-pages S3 bucket the publish identity writes to (owned by the hosting-migration tf; referenced here only to grant least-privilege write)."
  type        = string
  default     = "myadmin-public-pages-nonprofit-506221081911"
}

variable "nonprofit_public_pages_distribution_arn" {
  description = "ARN of the NONPROFIT-account *.jabaki.nl CloudFront distribution the publish identity invalidates (owned by the hosting-migration tf). CloudFront ARNs are account-scoped + region-less."
  type        = string
  default     = "arn:aws:cloudfront::506221081911:distribution/E3GLUX3TWBIJG"
}
