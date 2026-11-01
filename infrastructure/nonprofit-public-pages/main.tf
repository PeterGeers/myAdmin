# ============================================================================
# Nonprofit Public-Pages Hosting  (jabaki.nl migration — new isolated stack)
# ============================================================================
# Builds the NEW *.jabaki.nl landing-page hosting in the nonprofit account
# (506221081911): S3 bucket + CloudFront (OAC) + url-rewrite function + the two
# KeyValueStores + backend IAM. Deliberately isolated from the monolithic
# personal `infrastructure/` state so the build never touches the live site,
# the jabaki.nl zone, or any email record (those stay in the personal account).
#
# NOT APPLIED YET — draft for review. Deployment is manual + plan-first
# (steering 43): terraform plan -out=tf.plan -> review -> terraform apply tf.plan.
#
# Scope deliberately EXCLUDES (vs the personal landing-pages.tf):
#   - the jabaki.nl hosted zone + apex/wildcard/MX/TXT/DKIM/SES records
#     (stay in personal account, D1);
#   - the viewer-RESPONSE `application_form_frame_ancestors` CSP function
#     (deferred, D4 / out of scope). We create its embed-origins KVS so the
#     backend re-seed has a target, but do NOT associate the function.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # State lives separately from the personal monolith. Bucket chosen per
  # decision Q2 (default: nonprofit-owned state bucket). Left as a partial
  # config so `terraform init -backend-config=...` sets the bucket without
  # hardcoding an account-owned name before it exists.
  backend "s3" {
    key     = "nonprofit/public-pages/terraform.tfstate"
    region  = "eu-west-1"
    profile = "nonprofit-deploy"
    # bucket = supplied via -backend-config at init (see README.md)
  }
}

# Main provider — NONPROFIT account via the deploy role / profile.
provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# us-east-1 alias — REQUIRED: CloudFront viewer certs must be in us-east-1.
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile
}

variable "aws_region" {
  description = "AWS region for the hosting resources"
  type        = string
  default     = "eu-west-1"
}

variable "aws_profile" {
  description = "AWS CLI profile for the nonprofit account (506221081911)"
  type        = string
  default     = "nonprofit-deploy"
}

variable "environment" {
  description = "Environment name (kept 'production' for parity with personal stack)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "myAdmin"
}

variable "public_pages_bucket_name" {
  description = "Globally-unique name for the NEW public-pages bucket (nonprofit)"
  type        = string
  default     = "myadmin-public-pages-nonprofit-506221081911"
}

variable "distribution_aliases" {
  description = "CloudFront aliases. EMPTY during build/validation (a CNAME lives on only one distribution at a time). Set to [\"*.jabaki.nl\"] ONLY at Phase 5 cutover, after removing it from the old personal distribution."
  type        = list(string)
  default     = []
}

variable "railway_backend_user_arn" {
  description = "ARN of the personal-account IAM user Railway's backend uses to publish landing pages into this bucket (cross-account)."
  type        = string
  default     = "arn:aws:iam::344561557829:user/service-accounts/myadmin-railway-backend"
}
