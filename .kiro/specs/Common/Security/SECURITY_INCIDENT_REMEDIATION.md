# Security Incident Remediation - GitGuardian Alert

**Date**: 2026-01-23  
**Severity**: HIGH  
**Status**: IN PROGRESS

## Incident Summary

GitGuardian detected 3 types of secrets committed to the repository:

1. **Generic High Entropy Secret** - Database passwords
2. **OpenRouter API Key** - AI service credentials
3. **AWS Cognito OAuth 2.0 Credentials** - Authentication secrets

## Affected Files

Documentation files containing hardcoded secrets:

- `.kiro/specs/Common/Security/Environment-Variables-Consolidation.md`
- `.kiro/specs/Common/Cognito/setup-guide.md`
- `.kiro/specs/Common/Cognito/implementation-guide.md`
- `.kiro/specs/Common/Cognito/terraform-vs-implementation-guide.md`

## Immediate Actions Required

### 1. Rotate All Compromised Credentials ⚠️ URGENT

#### AWS Cognito Credentials

```powershell
# Regenerate Cognito App Client Secret
cd infrastructure
terraform taint aws_cognito_user_pool_client.myadmin_client
terraform apply

# Or via AWS CLI
aws cognito-idp update-user-pool-client \
  --user-pool-id <YOUR_USER_POOL_ID> \
  --client-id <YOUR_CLIENT_ID> \
  --generate-secret
```

#### OpenRouter API Key

1. Go to https://openrouter.ai/keys
2. Revoke the exposed key (check your GitGuardian alert for the specific key)
3. Generate a new API key
4. Update `.env` files locally (NOT in git)

#### Database Passwords

```sql
-- Connect to MySQL
mysql -u root -p

-- Change root password
ALTER USER 'root'@'localhost' IDENTIFIED BY '<new-strong-password>';

-- Change application user password
ALTER USER 'peter'@'%' IDENTIFIED BY '<new-strong-password>';

FLUSH PRIVILEGES;
```

### 2. Update Local Environment Files

Update these files locally (they are already in `.gitignore`):

- `.env`
- `backend/.env`
- `frontend/.env`

**DO NOT commit these files to git!**

### 3. Update Railway Environment Variables

Go to Railway dashboard and update:

```bash
COGNITO_CLIENT_SECRET=<new-secret-from-step-1>
OPENROUTER_API_KEY=<new-key-from-step-1>
DB_PASSWORD=<new-password-from-step-1>
MYSQL_ROOT_PASSWORD=<new-password-from-step-1>
```

### 4. Clean Git History (Optional but Recommended)

⚠️ **WARNING**: This rewrites git history. Coordinate with team members.

```powershell
# Install BFG Repo-Cleaner
# Download from: https://rtyley.github.io/bfg-repo-cleaner/

# Clone a fresh copy
git clone --mirror https://github.com/PeterGeers/myAdmin.git

# Remove secrets from history
java -jar bfg.jar --replace-text passwords.txt myAdmin.git

# Force push (requires force push permissions)
cd myAdmin.git
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

Alternative using git-filter-repo:

```powershell
# Install git-filter-repo
pip install git-filter-repo

# Remove specific files from history
git filter-repo --path .kiro/specs/Common/Security/Environment-Variables-Consolidation.md --invert-paths
```

## Preventive Measures Implemented

### 1. Documentation Sanitized ✅

All documentation files now use placeholder values:

- `<your-client-id>` instead of real client IDs
- `<your-api-key-here>` instead of real API keys
- `<your-db-password>` instead of real passwords

### 2. .gitignore Enhanced ✅

Already properly configured to ignore:

```gitignore
# Environment variables
.env
.env.shared
.secrets
*.env
.env.*
**/secrets.*
**/*secret*
**/*credential*
**/*password*
```

### 3. Pre-commit Hook (Recommended)

Install git-secrets or gitleaks:

```powershell
# Install gitleaks
# Download from: https://github.com/gitleaks/gitleaks/releases

# Initialize in repository
gitleaks protect --staged

# Add to pre-commit hook
# Create .git/hooks/pre-commit:
```

```bash
#!/bin/sh
gitleaks protect --staged --verbose
```

### 4. Environment Variable Templates

Create `.env.example` files with placeholders:

**Root `.env.example`:**

```bash
# AWS Cognito
COGNITO_USER_POOL_ID=eu-west-1_XXXXXXXXX
COGNITO_CLIENT_ID=<your-client-id>
COGNITO_CLIENT_SECRET=<your-client-secret>
AWS_REGION=eu-west-1

# Database
DB_HOST=mysql
DB_USER=<your-db-user>
DB_PASSWORD=<your-db-password>
DB_NAME=finance
DB_PORT=3306

# OpenRouter AI
OPENROUTER_API_KEY=sk-or-v1-<your-api-key>

# AWS SNS
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:<account-id>:myadmin-notifications
```

## Security Best Practices Going Forward

### 1. Never Commit Secrets

- ✅ Use `.env` files (already in `.gitignore`)
- ✅ Use environment variables in CI/CD
- ✅ Use secret management services (AWS Secrets Manager, HashiCorp Vault)

### 2. Use Placeholder Values in Documentation

- ✅ `<your-value-here>` format
- ✅ `XXXXXXXXX` for IDs
- ✅ `***` for sensitive values

### 3. Regular Security Audits

- Set up GitGuardian monitoring (already active)
- Run `gitleaks detect` before commits
- Review Railway environment variables quarterly

### 4. Principle of Least Privilege

- Use separate credentials for dev/staging/production
- Rotate credentials regularly (every 90 days)
- Use IAM roles instead of access keys where possible

## Verification Checklist

- [ ] AWS Cognito client secret rotated
- [ ] OpenRouter API key revoked and regenerated
- [ ] Database passwords changed
- [ ] Railway environment variables updated
- [ ] Local `.env` files updated
- [ ] Application tested with new credentials
- [ ] Documentation sanitized (✅ DONE)
- [ ] `.env.example` files created
- [ ] Pre-commit hooks installed
- [ ] Team notified of credential rotation

## Monitoring

### GitGuardian Dashboard

- Monitor: https://dashboard.gitguardian.com
- Set up alerts for new incidents
- Review weekly security reports

### AWS CloudTrail

- Monitor Cognito API calls
- Set up alerts for unusual activity
- Review access logs monthly

## Contact Information

**Security Team**: security@yourdomain.com  
**AWS Account Owner**: peter@pgeers.nl  
**GitGuardian Support**: https://support.gitguardian.com

## References

- [GitGuardian Best Practices](https://docs.gitguardian.com/secrets-detection/best-practices)
- [AWS Secrets Management](https://docs.aws.amazon.com/secretsmanager/)
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Git History Rewriting](https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History)

---

**Last Updated**: 2026-01-23  
**Next Review**: 2026-02-23
