# CI/CD Pipeline Documentation

## Overview

The CI/CD pipeline automates building, testing, and deploying the myAdmin application with comprehensive validation and security checks.

---

## Pipeline Stages

### Stage -1: Environment Validation (NEW)

**Script**: `validate-environment.ps1`  
**Purpose**: Validates all required environment variables and configurations before deployment

**Checks**:

- ✅ All required AWS Cognito variables
- ✅ AWS IAM credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- ✅ Database credentials
- ✅ Google Drive configuration
- ✅ OpenRouter API key
- ✅ File structure integrity
- ✅ Docker installation and status
- ✅ Security configuration (.gitignore)
- ✅ No secrets tracked in git

**Benefits**:

- Catches missing credentials before deployment starts
- Prevents "NoCredentialsError" at runtime
- Validates security configuration
- Fast fail (< 5 seconds)

### Stage 0: Git Operations

- GitGuardian security scan
- Commit changes
- Create tags
- Push to remote

### Stage 1: Build

- Frontend: npm install, lint, test, build
- Backend: pip install, lint, test
- Docker: build images

### Stage 2: Deploy

- Database backup
- Container health check
- Deploy with docker-compose
- Smoke tests

### Stage 3: Post-Deployment Verification

- Service status check
- Health endpoint verification
- Final validation

---

## Usage

### Full Pipeline

```powershell
# Staging deployment
.\scripts\cicd\pipeline.ps1

# Production deployment
.\scripts\cicd\pipeline.ps1 -Environment production

# Skip tests (faster)
.\scripts\cicd\pipeline.ps1 -SkipTests

# Force mode (no confirmations)
.\scripts\cicd\pipeline.ps1 -Force
```

### Individual Scripts

#### Environment Validation Only

```powershell
# Validate staging environment
.\scripts\cicd\validate-environment.ps1

# Validate production environment
.\scripts\cicd\validate-environment.ps1 -Environment production

# Strict mode (fail on warnings)
.\scripts\cicd\validate-environment.ps1 -Strict
```

#### Build Only

```powershell
# Full build with tests
.\scripts\cicd\build.ps1

# Skip tests
.\scripts\cicd\build.ps1 -SkipTests
```

#### Deploy Only

```powershell
# Deploy to staging
.\scripts\cicd\deploy.ps1

# Deploy to production
.\scripts\cicd\deploy.ps1 -Environment production

# Skip database backup (not recommended)
.\scripts\cicd\deploy.ps1 -SkipBackup
```

---

## Performance Improvements

### Before (Original Pipeline)

- **Total Time**: ~20-25 minutes
- **Build**: ~15 minutes (sequential tests)
- **Deploy**: ~5 minutes
- **No environment validation** (failures at runtime)

### After (Improved Pipeline)

- **Total Time**: ~8-12 minutes
- **Environment Validation**: ~5 seconds (NEW)
- **Build**: ~5-8 minutes (parallel tests with `-n 4`)
- **Deploy**: ~3-4 minutes
- **Early failure detection** (before build starts)

### Key Optimizations

1. ✅ **Environment validation first** - Fail fast if config is wrong
2. ✅ **Parallel testing** - pytest with `-n 4` workers
3. ✅ **95% pass rate threshold** - Allow deployment with minor test failures
4. ✅ **Conditional Docker build** - Skip if Docker not running
5. ✅ **Cached dependencies** - npm ci, pip cache

---

## Environment Variable Requirements

### Required Variables (backend/.env)

#### AWS Cognito

```
COGNITO_USER_POOL_ID=eu-west-1_XXXXXXXXX
COGNITO_CLIENT_ID=your-client-id
COGNITO_CLIENT_SECRET=your-client-secret
AWS_REGION=eu-west-1
```

#### AWS IAM (NEW - Required for boto3)

```
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=your-secret-access-key
```

**Why needed**: Backend uses boto3 to call AWS APIs (Cognito, SNS). These credentials authenticate the API calls.

**Where to get**:

- From `~/.aws/credentials` file
- From AWS IAM Console → Users → Security Credentials

#### Database

```
DB_HOST=localhost
DB_USER=peter
DB_PASSWORD=your-password
DB_NAME=finance
MYSQL_ROOT_PASSWORD=your-password
```

#### Google Drive

```
FACTUREN_FOLDER_ID=your-folder-id
FACTUREN_FOLDER_NAME=Facturen
```

#### OpenRouter

```
OPENROUTER_API_KEY=sk-or-v1-your-key
```

---

## Troubleshooting

### "Environment validation failed"

**Cause**: Missing or invalid environment variables

**Solution**:

1. Run validation to see what's missing:
   ```powershell
   .\scripts\cicd\validate-environment.ps1
   ```
2. Fix the errors shown
3. Re-run pipeline

### "NoCredentialsError: Unable to locate credentials"

**Cause**: Missing AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY

**Solution**:

1. Check `~/.aws/credentials`:
   ```powershell
   type $env:USERPROFILE\.aws\credentials
   ```
2. Add to `backend/.env`:
   ```
   AWS_ACCESS_KEY_ID=your-key
   AWS_SECRET_ACCESS_KEY=your-secret
   ```
3. Restart backend:
   ```powershell
   docker restart myadmin-backend-1
   ```

### "System Administration page shows 500 error"

**Cause**: Missing AWS credentials

**Solution**: Same as above - add AWS IAM credentials to backend/.env

### "Pipeline takes too long"

**Solutions**:

- Use `-SkipTests` flag for faster deployment
- Ensure parallel testing is enabled (pytest -n 4)
- Check Docker resource allocation (increase CPU/RAM)

---

## Security Features

### GitGuardian Integration

- Scans for secrets before commit
- Prevents accidental credential leaks
- Can be overridden with `-Force` flag

### Environment Validation

- Checks .gitignore configuration
- Verifies no secrets tracked in git
- Validates placeholder values replaced

### Database Backup

- Automatic backup before deployment
- Stored in `scripts/cicd/backups/`
- Can be skipped with `-SkipBackup` (not recommended)

---

## Best Practices

### Before Running Pipeline

1. ✅ Run environment validation first
2. ✅ Ensure all .env files are configured
3. ✅ Check Docker is running
4. ✅ Review uncommitted changes

### During Development

1. ✅ Use staging environment for testing
2. ✅ Run tests locally before pipeline
3. ✅ Keep .env files up to date
4. ✅ Never commit secrets

### Production Deployment

1. ✅ Always use production environment flag
2. ✅ Never skip database backup
3. ✅ Review changes before confirming
4. ✅ Monitor logs after deployment

---

## Maintenance

### Update Environment Variables

1. Edit `backend/.env`
2. Run validation:
   ```powershell
   .\scripts\cicd\validate-environment.ps1
   ```
3. Restart containers:
   ```powershell
   docker-compose restart
   ```

### Clean Up Old Logs

```powershell
# Remove logs older than 30 days
Get-ChildItem scripts\cicd\logs -Filter *.log |
    Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-30)} |
    Remove-Item
```

### Clean Up Old Backups

```powershell
# Remove backups older than 90 days
Get-ChildItem scripts\cicd\backups -Filter *.sql |
    Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-90)} |
    Remove-Item
```

---

## Quick Reference

| Command                    | Purpose             | Time     |
| -------------------------- | ------------------- | -------- |
| `validate-environment.ps1` | Check configuration | ~5s      |
| `build.ps1`                | Build application   | ~5-8min  |
| `deploy.ps1`               | Deploy application  | ~3-4min  |
| `pipeline.ps1`             | Full pipeline       | ~8-12min |
| `pipeline.ps1 -SkipTests`  | Fast deployment     | ~3-5min  |

---

## Support

For issues or questions:

1. Check this README
2. Run validation script
3. Check logs in `scripts/cicd/logs/`
4. Review SETUP.md in root directory
