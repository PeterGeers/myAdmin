# myAdmin Infrastructure

## Overview

This directory contains Terraform configurations for myAdmin infrastructure on AWS.

## Current Deployment Strategy

**Primary**: Railway (PaaS) - No AWS infrastructure needed for application hosting
**AWS Services**: Cognito (authentication) + SNS (notifications)

## File Structure

```
infrastructure/
├── main.tf                    # Core Terraform config (provider, variables)
├── cognito.tf                 # AWS Cognito User Pool (authentication)
├── notifications.tf           # AWS SNS (email notifications)
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

## Cost Estimate

### Current (Cognito + SNS)
- **Cognito**: FREE (< 50,000 MAU)
- **SNS**: FREE (< 1,000 emails/month)
- **Total**: $0/month

### If EC2 Enabled
- **EC2 t3.small**: ~$15/month
- **Elastic IP**: ~$3.60/month
- **Data transfer**: ~$1/month
- **Total**: ~$20/month

## Deployment Scenarios

### Scenario 1: Railway + Cognito (Current)
```
Railway (Application) → AWS Cognito (Auth) → AWS SNS (Notifications)
Cost: $5/month (Railway) + $0 (AWS) = $5/month
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

## Summary

**Current Setup**:
- ✅ Cognito for authentication
- ✅ SNS for notifications
- ✅ Railway for application hosting
- ✅ No EC2 costs
- ✅ Total AWS cost: $0/month

**Clean and Simple!** 🎉
