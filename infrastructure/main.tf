# Terraform Configuration for myAdmin
# Main configuration file - provider and core settings

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-west-1"
}

variable "admin_email" {
  description = "Admin email for notifications"
  type        = string
  default     = "peter@pgeers.nl"
}

# Note: EC2 resources have been moved to ec2.tf.disabled
# To deploy EC2, rename ec2.tf.disabled to ec2.tf and provide key_name variable