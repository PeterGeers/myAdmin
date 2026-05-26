# myAdmin Infrastructure

## Overview

This directory contains Terraform configurations for myAdmin infrastructure on AWS.

## Current Deployment Strategy

**Primary**: Railway (PaaS) - No AWS infrastructure needed for application hosting
**AWS Services**: Cognito (authentication) + SNS (notifications) + S3 (document storage)

## File Structure

```
infrastructure/
├── main.tf                    # Core Terraform config (provider, variables)
├── cognito.tf                 # AWS Cognito User Pool (authentication)
├── notifications.tf           # AWS SNS (email notifications)
├── s3.tf                      # AWS S3 shared bucket (document storage)
├── variables.tf               # Additional variables
├── ec2.tf.disabled           # EC2 resources (disabled, for future use)
├── setup-cognito.ps1         # Deployment script
├── create-cognito-user.ps1   # User management script
└── README.md                 # This file
```

## Active Resources

### 1. AWS Cognito (cognito.tf)

- **User Pool**: myAdmin authentication
- **App Client**: OAuth 2.0 configuration
- **User Groups**: Administrators, Accountants, Viewers
- **Hosted UI**: Login pages
- **Region**: eu-west-1

### 2. AWS SNS (notifications.tf)

- **Topic**: myadmin-notifications
- **Subscription**: Email notifications
- **Region**: eu-west-1

### 3. AWS S3 (s3.tf)

- **Bucket**: `myadmin-shared-{environment}` (e.g., `myadmin-shared-production`)
- **Purpose**: Shared document storage (invoices, branding, templates)
- **Versioning**: Enabled
- **Encryption**: AES-256 (SSE-S3)
- **Public Access**: Fully blocked
- **Lifecycle**: Transition to STANDARD_IA after 90 days
- **CORS**: Allows browser uploads from production and localhost origins
- **IAM Policy**: Least-privilege access (PutObject, GetObject, DeleteObject, ListBucket)
- **Region**: eu-west-1

## Disabled Resources

### EC2 Infrastructure (ec2.tf.disabled)

- **Status**: Disabled (Railway is used instead)
- **Contains**: EC2 instance, Security Group, Elastic IP
- **To Enable**: Rename `ec2.tf.disabled` to `ec2.tf`

## Quick Start

### Deploy Cognito + SNS

```powershell
# Deploy everything
.\setup-cognito.ps1 -AdminEmail "your-email@example.com"
```

This will:

1. Create Cognito User Pool
2. Create SNS topic
3. Update .env files
4. Create admin user (optional)

### Manual Deployment

```powershell
# Initialize Terraform
terraform init

# Preview changes
terraform plan

# Deploy
terraform apply

# Deploy specific resources only
terraform apply -target=aws_cognito_user_pool.myadmin
```

### Deploy S3 Shared Bucket

After running `terraform apply`, the S3 bucket and IAM policy are created. Two manual steps remain:

#### 1. Attach IAM Policy to Backend User

The IAM policy must be manually attached to the backend service's IAM user/role:

```powershell
# Get the policy ARN from Terraform output
terraform output s3_shared_access_policy_arn

# Attach the policy to the backend IAM user
aws iam attach-user-policy `
    --user-name <backend-iam-user> `
    --policy-arn <policy-arn>
```

Replace `<backend-iam-user>` with the IAM user used by the Railway backend service, and `<policy-arn>` with the output from `terraform output s3_shared_access_policy_arn`.

#### 2. Set Railway Environment Variable

The `S3_SHARED_BUCKET` environment variable **must** be set in Railway's environment variables for the backend service. Without this variable, the backend cannot connect to S3 storage.

- **Variable name**: `S3_SHARED_BUCKET`
- **Value**: The bucket name following the pattern `myadmin-shared-{environment}` (e.g., `myadmin-shared-production`)
- **Where**: Railway dashboard → Backend service → Variables tab

You can retrieve the bucket name from Terraform:

```powershell
terraform output s3_shared_bucket_name
```

#### 3. Post-Apply Verification

```powershell
# Verify bucket exists
aws s3 ls s3://myadmin-shared-production

# Verify versioning is enabled
aws s3api get-bucket-versioning --bucket myadmin-shared-production

# Verify encryption
aws s3api get-bucket-encryption --bucket myadmin-shared-production

# Verify public access is blocked
aws s3api get-public-access-block --bucket myadmin-shared-production

# Verify IAM policy is attached
aws iam list-attached-user-policies --user-name <backend-iam-user>
```

## Variables

### Required

- `aws_region` - AWS region (default: eu-west-1)
- `admin_email` - Email for notifications (default: peter@pgeers.nl)

### Optional

- `project_name` - Project name (default: myAdmin)
- `environment` - Environment name (default: production)

### EC2 Only (if enabled)

- `key_name` - EC2 key pair name
- `domain_name` - Domain for application

## Outputs

After deployment, Terraform provides:

### Cognito

- `cognito_user_pool_id` - User Pool ID
- `cognito_client_id` - App Client ID
- `cognito_client_secret` - App Client Secret (sensitive)
- `cognito_domain` - Hosted UI domain
- `cognito_hosted_ui_url` - Full Hosted UI URL

### SNS

- `sns_topic_arn` - SNS Topic ARN
- `sns_topic_name` - SNS Topic name

### S3

- `s3_shared_bucket_name` - Shared bucket name
- `s3_shared_bucket_arn` - Shared bucket ARN
- `s3_shared_access_policy_arn` - IAM policy ARN (attach to backend IAM user)

## Cost Estimate

### Current (Cognito + SNS + S3)

- **Cognito**: FREE (< 50,000 MAU)
- **SNS**: FREE (< 1,000 emails/month)
- **S3**: ~$0.02/GB/month (minimal for document storage)
- **Total**: ~$0/month (negligible for typical usage)

### If EC2 Enabled

- **EC2 t3.small**: ~$15/month
- **Elastic IP**: ~$3.60/month
- **Data transfer**: ~$1/month
- **Total**: ~$20/month

## Deployment Scenarios

### Scenario 1: Railway + Cognito + S3 (Current)

```
Railway (Application) → AWS Cognito (Auth) → AWS SNS (Notifications) → AWS S3 (Storage)
Cost: $5/month (Railway) + ~$0 (AWS) = ~$5/month
```

### Scenario 2: EC2 + Cognito (Alternative)

```
EC2 (Application) → AWS Cognito (Auth) → AWS SNS (Notifications)
Cost: $20/month (EC2) + $0 (Cognito/SNS) = $20/month
```

**Recommendation**: Use Scenario 1 (Railway + Cognito)

## Managing Resources

### View Current State

```powershell
terraform show
```

### List Resources

```powershell
terraform state list
```

### Update Resources

```powershell
# Edit .tf files
terraform plan
terraform apply
```

### Destroy Resources

```powershell
# Destroy everything
terraform destroy

# Destroy specific resource
terraform destroy -target=aws_cognito_user_pool.myadmin
```

## User Management

### Create User

```powershell
.\create-cognito-user.ps1 `
    -Email "user@example.com" `
    -Name "User Name" `
    -Group "Accountants"
```

### List Users

```powershell
aws cognito-idp list-users `
    --user-pool-id <USER_POOL_ID> `
    --region eu-west-1
```

### Delete User

```powershell
aws cognito-idp admin-delete-user `
    --user-pool-id <USER_POOL_ID> `
    --username "user@example.com" `
    --region eu-west-1
```

## Troubleshooting

### "Duplicate variable" Error

- **Cause**: Variable defined in multiple files
- **Solution**: Variables are now centralized in main.tf

### "key_name required" Error

- **Cause**: EC2 resources trying to deploy
- **Solution**: EC2 is now disabled by default (ec2.tf.disabled)

### "Region mismatch" Error

- **Cause**: AWS CLI region != Terraform region
- **Solution**: Both are now set to eu-west-1

### Terraform State Issues

```powershell
# Refresh state
terraform refresh

# Re-initialize
terraform init -upgrade
```

## Best Practices

1. **Version Control**: Commit .tf files, NOT .tfstate files
2. **Secrets**: Never commit credentials or secrets
3. **State**: Use remote state for team collaboration
4. **Modules**: Consider modules for reusable components
5. **Tagging**: All resources tagged with Name, Environment, Project

## Future Enhancements

### Potential Additions

- [ ] DynamoDB tables (if needed)
- [ ] Lambda functions (if needed)
- [ ] API Gateway (if needed)
- [ ] CloudWatch alarms
- [ ] Backup policies
- [ ] Multi-region setup

### EC2 Migration Path

If you decide to move from Railway to EC2:

1. Rename `ec2.tf.disabled` to `ec2.tf`
2. Create EC2 key pair in AWS
3. Run: `terraform apply -var="key_name=your-key"`
4. Update DNS to point to EC2 Elastic IP

## Support

- **Terraform Docs**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **AWS Cognito**: https://docs.aws.amazon.com/cognito/
- **AWS SNS**: https://docs.aws.amazon.com/sns/
- **AWS S3**: https://docs.aws.amazon.com/s3/

## Summary

**Current Setup**:

- ✅ Cognito for authentication
- ✅ SNS for notifications
- ✅ S3 for document storage
- ✅ Railway for application hosting
- ✅ No EC2 costs
- ✅ Total AWS cost: ~$0/month

**Clean and Simple!** 🎉
