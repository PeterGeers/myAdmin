# AWS Cognito Setup Guide for myAdmin

## Overview

This guide shows you how to create a new AWS Cognito User Pool called "myAdmin" using Terraform (recommended) or AWS CLI.

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** installed (or use `.\infrastructure\install-terraform.ps1`)
3. **AWS CLI** configured with credentials

## Option 1: Terraform (Recommended) ⭐

### Why Terraform?

- ✅ Infrastructure as Code (version controlled)
- ✅ Repeatable and consistent
- ✅ Easy to update and maintain
- ✅ Can destroy and recreate easily
- ✅ Automatic .env file updates

### Quick Start

```powershell
# 1. Deploy Cognito User Pool
.\infrastructure\setup-cognito.ps1

# 2. Create admin user (optional)
.\infrastructure\setup-cognito.ps1 -AdminEmail "peter@pgeers.nl"

# 3. View plan before applying
.\infrastructure\setup-cognito.ps1 -Plan
```

### What Gets Created

The Terraform configuration creates:

1. **User Pool** named "myAdmin"
   - Email-based authentication
   - Password policy (8+ chars, uppercase, lowercase, number, symbol)
   - MFA support (optional)
   - Custom attributes for multi-tenant support

2. **User Pool Client** (App Client)
   - OAuth 2.0 flows enabled
   - Callback URLs configured
   - Token validity settings

3. **User Groups**
   - Administrators (full access)
   - Accountants (financial data access)
   - Viewers (read-only access)

4. **Hosted UI Domain**
   - Unique domain for login pages
   - Automatic SSL certificate

### Step-by-Step

#### 1. Review Configuration

Edit `infrastructure/cognito.tf` if needed:

- Callback URLs (add your Railway URL)
- Password policy
- Token validity periods
- Custom attributes

#### 2. Deploy

```powershell
cd infrastructure
.\setup-cognito.ps1
```

**Output:**

```
✓ Terraform initialized
✓ Cognito infrastructure deployed!

User Pool ID:     eu-west-1_ABC123
Client ID:        abc123def456
Client Secret:    xyz789...
Domain:           myadmin-abc12345
Hosted UI URL:    https://myadmin-abc12345.auth.eu-west-1.amazoncognito.com
```

#### 3. Automatic .env Updates

The script automatically updates:

- `.env`
- `backend/.env`
- `frontend/.env`

With your new Cognito credentials!

#### 4. Create Users

```powershell
# Create admin user
.\infrastructure\create-cognito-user.ps1 `
    -Email "admin@example.com" `
    -Name "Admin User" `
    -Group "Administrators"

# Create accountant
.\infrastructure\create-cognito-user.ps1 `
    -Email "accountant@example.com" `
    -Name "John Accountant" `
    -Group "Accountants"

# Create viewer
.\infrastructure\create-cognito-user.ps1 `
    -Email "viewer@example.com" `
    -Name "Jane Viewer" `
    -Group "Viewers"
```

#### 5. Test Hosted UI

Visit the Hosted UI URL from the output:

```
https://myadmin-abc12345.auth.eu-west-1.amazoncognito.com/login?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost:3000/callback
```

### Managing the User Pool

```powershell
# View current configuration
cd infrastructure
terraform show

# Update configuration
# 1. Edit cognito.tf
# 2. Run:
terraform apply

# Destroy (careful!)
.\setup-cognito.ps1 -Destroy
```

## Option 2: AWS CLI (Manual)

### Create User Pool

```powershell
# Create user pool
aws cognito-idp create-user-pool `
    --pool-name "myAdmin" `
    --policies "PasswordPolicy={MinimumLength=8,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true,RequireSymbols=true}" `
    --username-attributes "email" `
    --auto-verified-attributes "email" `
    --mfa-configuration "OPTIONAL" `
    --schema "Name=email,AttributeDataType=String,Required=true,Mutable=false" `
            "Name=name,AttributeDataType=String,Required=true,Mutable=true" `
            "Name=tenant_id,AttributeDataType=String,Mutable=true,DeveloperOnlyAttribute=false" `
            "Name=tenant_name,AttributeDataType=String,Mutable=true,DeveloperOnlyAttribute=false" `
            "Name=role,AttributeDataType=String,Mutable=true,DeveloperOnlyAttribute=false" `
    --region eu-west-1

# Save the UserPoolId from output
$userPoolId = "eu-west-1_ABC123"
```

### Create App Client

```powershell
aws cognito-idp create-user-pool-client `
    --user-pool-id $userPoolId `
    --client-name "myAdmin-client" `
    --generate-secret `
    --allowed-o-auth-flows "code" "implicit" `
    --allowed-o-auth-scopes "email" "openid" "profile" `
    --allowed-o-auth-flows-user-pool-client `
    --callback-urls "http://localhost:3000/callback" "http://localhost:5000/callback" `
    --logout-urls "http://localhost:3000/logout" "http://localhost:5000/logout" `
    --supported-identity-providers "COGNITO" `
    --refresh-token-validity 30 `
    --access-token-validity 60 `
    --id-token-validity 60 `
    --token-validity-units "RefreshToken=days,AccessToken=minutes,IdToken=minutes" `
    --region eu-west-1

# Save ClientId and ClientSecret from output
$clientId = "abc123def456"
$clientSecret = "xyz789..."
```

### Create User Groups

```powershell
# Administrators
aws cognito-idp create-group `
    --user-pool-id $userPoolId `
    --group-name "Administrators" `
    --description "Full system access" `
    --precedence 1 `
    --region eu-west-1

# Accountants
aws cognito-idp create-group `
    --user-pool-id $userPoolId `
    --group-name "Accountants" `
    --description "Financial data access" `
    --precedence 2 `
    --region eu-west-1

# Viewers
aws cognito-idp create-group `
    --user-pool-id $userPoolId `
    --group-name "Viewers" `
    --description "Read-only access" `
    --precedence 3 `
    --region eu-west-1
```

### Create Domain

```powershell
aws cognito-idp create-user-pool-domain `
    --user-pool-id $userPoolId `
    --domain "myadmin-$(Get-Random -Minimum 10000000 -Maximum 99999999)" `
    --region eu-west-1
```

### Create Users

```powershell
# Create admin user
aws cognito-idp admin-create-user `
    --user-pool-id $userPoolId `
    --username "admin@example.com" `
    --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true Name=name,Value="Administrator" `
    --message-action SUPPRESS `
    --region eu-west-1

# Add to Administrators group
aws cognito-idp admin-add-user-to-group `
    --user-pool-id $userPoolId `
    --username "admin@example.com" `
    --group-name "Administrators" `
    --region eu-west-1

# Set password
aws cognito-idp admin-set-user-password `
    --user-pool-id $userPoolId `
    --username "admin@example.com" `
    --password "YourSecurePassword123!" `
    --permanent `
    --region eu-west-1
```

## Option 3: AWS Console (GUI)

### Step-by-Step

1. **Go to AWS Console**
   - Navigate to: https://console.aws.amazon.com/cognito/
   - Select region: eu-west-1

2. **Create User Pool**
   - Click "Create user pool"
   - Choose "Email" for sign-in
   - Configure password policy
   - Enable MFA (optional)
   - Add custom attributes: tenant_id, tenant_name, role

3. **Create App Client**
   - In User Pool, go to "App clients"
   - Click "Add an app client"
   - Name: "myAdmin-client"
   - Generate client secret: Yes
   - Configure OAuth flows

4. **Create Groups**
   - Go to "Groups"
   - Create: Administrators, Accountants, Viewers

5. **Create Domain**
   - Go to "App integration" > "Domain name"
   - Choose a unique domain prefix

6. **Create Users**
   - Go to "Users"
   - Click "Create user"
   - Enter email, name, and assign to group

## Comparison

| Method        | Pros                                      | Cons                         | Best For                 |
| ------------- | ----------------------------------------- | ---------------------------- | ------------------------ |
| **Terraform** | Version controlled, repeatable, automated | Requires Terraform knowledge | Production, teams        |
| **AWS CLI**   | Scriptable, no extra tools                | Manual, error-prone          | Quick tests              |
| **Console**   | Visual, easy to understand                | Not repeatable, manual       | Learning, one-time setup |

## Recommendation

**Use Terraform** for myAdmin because:

1. You already have infrastructure code
2. Easy to version control
3. Can recreate environment easily
4. Automatic .env updates
5. Consistent across deployments

## After Setup

### 1. Update .env Files

If using AWS CLI or Console, manually update:

```bash
# .env, backend/.env, frontend/.env
COGNITO_USER_POOL_ID=eu-west-1_ABC123
COGNITO_CLIENT_ID=abc123def456
COGNITO_CLIENT_SECRET=xyz789...
AWS_REGION=eu-west-1
```

### 2. Test Authentication

```powershell
# Test with hosted UI
# Visit: https://YOUR_DOMAIN.auth.eu-west-1.amazoncognito.com/login

# Or test with AWS CLI
aws cognito-idp admin-initiate-auth `
    --user-pool-id $userPoolId `
    --client-id $clientId `
    --auth-flow ADMIN_NO_SRP_AUTH `
    --auth-parameters USERNAME=admin@example.com,PASSWORD=YourPassword123! `
    --region eu-west-1
```

### 3. Integrate with Application

See: `.kiro/specs/Common/Cognito/implementation-guide.md`

## Costs

**AWS Cognito Pricing (Free Tier):**

- First 50,000 MAUs (Monthly Active Users): **FREE**
- After 50,000: $0.0055 per MAU

**For myAdmin:**

- Expected users: < 100
- **Cost: $0/month** (within free tier)

## Security Best Practices

1. ✅ Enable MFA for admin users
2. ✅ Use strong password policy
3. ✅ Rotate client secrets regularly
4. ✅ Use HTTPS for all callbacks
5. ✅ Monitor failed login attempts
6. ✅ Enable advanced security features

## Troubleshooting

### "Terraform not found"

```powershell
.\infrastructure\install-terraform.ps1
```

### "AWS credentials not configured"

```powershell
aws configure
# Enter: Access Key ID, Secret Access Key, Region (eu-west-1)
```

### "User pool already exists"

```powershell
# Destroy existing
.\infrastructure\setup-cognito.ps1 -Destroy

# Create new
.\infrastructure\setup-cognito.ps1
```

## Next Steps

1. ✅ Create User Pool (this guide)
2. ⏭️ Integrate with backend (Python/Flask)
3. ⏭️ Integrate with frontend (React)
4. ⏭️ Deploy to Railway
5. ⏭️ Configure production callback URLs

## Summary

**Recommended approach:**

```powershell
# 1. Deploy Cognito
.\infrastructure\setup-cognito.ps1 -AdminEmail "your-email@example.com"

# 2. Create additional users
.\infrastructure\create-cognito-user.ps1 -Email "user@example.com" -Name "User Name" -Group "Accountants"

# 3. Test
# Visit the Hosted UI URL from output

# 4. Integrate with your app
# .env files are already updated!
```

That's it! Your Cognito User Pool is ready for myAdmin! 🎉
