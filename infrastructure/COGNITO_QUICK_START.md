# Cognito Quick Start

## TL;DR - Get Started in 2 Minutes

```powershell
# 1. Deploy Cognito User Pool
.\infrastructure\setup-cognito.ps1 -AdminEmail "your-email@example.com"

# 2. Done! Your .env files are automatically updated
```

## What You Get

- ✅ User Pool named "myAdmin"
- ✅ 3 user groups (Administrators, Accountants, Viewers)
- ✅ Hosted UI for login
- ✅ OAuth 2.0 configured
- ✅ MFA support
- ✅ Multi-tenant ready (custom attributes)
- ✅ .env files automatically updated

## Create More Users

```powershell
.\infrastructure\create-cognito-user.ps1 `
    -Email "user@example.com" `
    -Name "User Name" `
    -Group "Accountants"
```

## Test Login

Visit the Hosted UI URL from the setup output:

```
https://myadmin-XXXXXXXX.auth.eu-west-1.amazoncognito.com/login
```

## View Configuration

```powershell
cd infrastructure
terraform show
```

## Update Configuration

1. Edit `infrastructure/cognito.tf`
2. Run: `terraform apply`

## Destroy (if needed)

```powershell
.\infrastructure\setup-cognito.ps1 -Destroy
```

## Files Created

- `infrastructure/cognito.tf` - Terraform configuration
- `infrastructure/variables.tf` - Variables
- `infrastructure/setup-cognito.ps1` - Deployment script
- `infrastructure/create-cognito-user.ps1` - User creation script

## Cost

**FREE** for up to 50,000 monthly active users

## Next Steps

1. ✅ Deploy Cognito (you just did this!)
2. ⏭️ Integrate with backend: See `.kiro/specs/Common/Cognito/implementation-guide.md`
3. ⏭️ Deploy to Railway
4. ⏭️ Update callback URLs with Railway URL

## Support

Full guide: `.kiro/specs/Common/Cognito/setup-guide.md`
