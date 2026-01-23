# Security Quick Reference Guide

## 🚨 CRITICAL: GitGuardian Alert Response

**Date**: 2026-01-23  
**Status**: Secrets detected in repository - immediate action required

## What Happened?

GitGuardian detected hardcoded secrets in documentation files that were committed to git:

- AWS Cognito credentials
- OpenRouter API key
- Database passwords

## Immediate Actions (Do This Now!)

### 1. Rotate All Credentials ⚠️

#### AWS Cognito

```powershell
cd infrastructure
terraform taint aws_cognito_user_pool_client.myadmin_client
terraform apply
```

#### OpenRouter API

1. Visit: https://openrouter.ai/keys
2. Revoke the old key
3. Generate a new key
4. Update your local `.env` files

#### Database

```sql
mysql -u root -p
ALTER USER 'root'@'localhost' IDENTIFIED BY '<new-password>';
ALTER USER 'peter'@'%' IDENTIFIED BY '<new-password>';
FLUSH PRIVILEGES;
```

### 2. Update Environment Variables

Update these files **locally** (they are in `.gitignore`):

- `.env`
- `backend/.env`
- `frontend/.env`

**DO NOT commit these files!**

### 3. Update Railway

Go to Railway dashboard → Environment Variables → Update:

- `COGNITO_CLIENT_SECRET`
- `OPENROUTER_API_KEY`
- `DB_PASSWORD`
- `MYSQL_ROOT_PASSWORD`

## Rules to Follow

### ✅ DO

- Use `.env` files for secrets (already in `.gitignore`)
- Use `.env.example` files with placeholders for documentation
- Store secrets in Railway environment variables
- Use `<placeholder>` format in documentation
- Run `git status` before committing to verify no secrets

### ❌ DON'T

- Never commit `.env` files
- Never put real secrets in documentation
- Never put secrets in code comments
- Never share secrets in chat/email
- Never commit files with passwords/keys

## Quick Checks Before Committing

```powershell
# 1. Check what you're about to commit
git status

# 2. Review changes
git diff

# 3. Verify no .env files
git ls-files | Select-String ".env"
# Should only show .env.example files

# 4. Check for secrets (if gitleaks installed)
gitleaks detect --verbose
```

## Setting Up Your Environment

### First Time Setup

```powershell
# 1. Copy example files
copy .env.example .env
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env

# 2. Edit each .env file with your actual values
# Use a text editor, NOT git!

# 3. Verify files are ignored
git check-ignore -v .env backend/.env frontend/.env
# Should show they are ignored
```

## Common Mistakes to Avoid

### ❌ Mistake 1: Committing .env files

```powershell
# WRONG - This commits secrets!
git add .env
git commit -m "Add config"
```

### ✅ Correct: Use .env.example

```powershell
# RIGHT - Only commit the template
git add .env.example
git commit -m "Add config template"
```

### ❌ Mistake 2: Hardcoding in documentation

```markdown
# WRONG

COGNITO_CLIENT_ID=14s1srsurk9epvdunoh9k0b183
```

### ✅ Correct: Use placeholders

```markdown
# RIGHT

COGNITO_CLIENT_ID=<your-client-id>
```

### ❌ Mistake 3: Sharing secrets in code

```python
# WRONG
api_key = "sk-or-v1-abc123..."
```

### ✅ Correct: Use environment variables

```python
# RIGHT
import os
api_key = os.getenv('OPENROUTER_API_KEY')
```

## Emergency Contacts

- **Security Issues**: peter@pgeers.nl
- **GitGuardian Dashboard**: https://dashboard.gitguardian.com
- **AWS Console**: https://console.aws.amazon.com

## More Information

See detailed remediation guide:
`.kiro/specs/Common/Security/SECURITY_INCIDENT_REMEDIATION.md`

---

**Remember**: When in doubt, ask before committing!
