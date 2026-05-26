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
