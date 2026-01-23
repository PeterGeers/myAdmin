# 🚨 CRITICAL: Comprehensive Secret Cleanup Required

## Severity: CRITICAL

The repository contains **MANY** files with exposed secrets across multiple categories:

### 1. Google OAuth Credentials (CRITICAL)

- `backend/credentials.json` - Contains Google OAuth client secret
- `backend/token.json` - Contains Google OAuth tokens
- These files are in `.gitignore` but were already committed to git history

### 2. AWS Cognito Credentials (HIGH)

- Multiple documentation files
- Frontend configuration files
- Test files

### 3. AWS Account IDs (MEDIUM)

- Infrastructure documentation
- Backend documentation

### 4. Hardcoded Configuration (MEDIUM)

- `frontend/src/aws-exports.ts` - Had hardcoded fallback values (NOW FIXED)

## Immediate Actions Required

### Step 1: Remove Sensitive Files from Git (NOW)

```powershell
# Remove Google credentials from git tracking
git rm --cached backend/credentials.json
git rm --cached backend/token.json
git rm --cached backend/data/credentials.json
git rm --cached backend/data/token.json

# Commit the removal
git commit -m "security: Remove Google OAuth credentials from git tracking"
```

### Step 2: Verify .gitignore

The following should be in `.gitignore` (already there):

```gitignore
credentials.json
token.json
token.pickle
```

### Step 3: Rotate ALL Credentials

#### Google OAuth Credentials

1. Go to: https://console.cloud.google.com/apis/credentials
2. Find project: "handle-files-in-facturen"
3. Delete the exposed OAuth client
4. Create a new OAuth 2.0 Client ID
5. Download new `credentials.json`
6. Place in `backend/` (it will be ignored by git)

#### AWS Cognito

1. Regenerate client secret:
   ```powershell
   cd infrastructure
   terraform taint aws_cognito_user_pool_client.myadmin_client
   terraform apply
   ```

#### OpenRouter API Key

1. Go to: https://openrouter.ai/keys
2. Revoke the old key
3. Generate new key
4. Update local `.env` files

### Step 4: Clean Git History

You MUST remove these files from git history:

```powershell
# Install git-filter-repo
pip install git-filter-repo

# Remove sensitive files from ALL history
git filter-repo --path backend/credentials.json --invert-paths --force
git filter-repo --path backend/token.json --invert-paths --force
git filter-repo --path backend/data/credentials.json --invert-paths --force
git filter-repo --path backend/data/token.json --invert-paths --force

# Force push
git push origin main --force
```

## Files That Need Sanitization

### Documentation Files (Replace real values with placeholders)

1. `.kiro/specs/Common/Cognito/hosted-ui-test-instructions.md`
2. `.kiro/specs/Common/Cognito/hosted-ui-verification-results.md`
3. `.kiro/prompts/MyAdmin Functions.md`
4. `.kiro/prompts/Slim prijsmodel en AI-integratie.md`
5. `.kiro/prompts/STR_Invoice_README.md`
6. `backend/docs/guides/AWS_SNS_SETUP_COMPLETE.md`
7. `infrastructure/AWS_NOTIFICATIONS_SETUP.md`
8. `infrastructure/CLEANUP_AND_SETUP.md`
9. `infrastructure/QUICK_START.md`

### Code Files (Use environment variables only)

1. ✅ `frontend/src/aws-exports.ts` - FIXED (removed hardcoded fallbacks)
2. `backend/src/google_drive_service.py` - Check for hardcoded values
3. `backend/src/app.py` - Check for hardcoded values

### Files to Delete from Git (Already in .gitignore)

1. `backend/credentials.json` - Google OAuth secret
2. `backend/token.json` - Google OAuth token
3. `backend/data/credentials.json` - Duplicate
4. `backend/data/token.json` - Duplicate
5. `backend/frontend/` - Old build artifacts (should not be in git)
6. `frontend/coverage/` - Test coverage (should not be in git)

## Quick Fix Script

```powershell
# 1. Remove sensitive files from git
git rm --cached backend/credentials.json
git rm --cached backend/token.json
git rm --cached backend/data/credentials.json
git rm --cached backend/data/token.json

# 2. Remove old build artifacts
git rm -r --cached backend/frontend/
git rm -r --cached frontend/coverage/

# 3. Commit
git commit -m "security: Remove sensitive files and build artifacts"

# 4. Push
git push origin main
```

## .gitignore Additions Needed

Add these to `.gitignore`:

```gitignore
# Build artifacts
backend/frontend/
frontend/coverage/
frontend/build/

# Test artifacts
*.test.js.snap
coverage/
.nyc_output/

# Cache files
backend/cache/
cache/
```

## Priority Order

1. **CRITICAL (Do Now)**:
   - Remove `credentials.json` and `token.json` from git
   - Rotate Google OAuth credentials
   - Remove from git history

2. **HIGH (Do Today)**:
   - Sanitize all documentation files
   - Rotate AWS Cognito credentials
   - Rotate OpenRouter API key

3. **MEDIUM (Do This Week)**:
   - Clean up build artifacts from git
   - Add missing .gitignore entries
   - Audit all code files for hardcoded values

## Verification

After cleanup, run:

```powershell
# Check for secrets
.\scripts\verify-no-secrets.ps1

# Verify sensitive files are not tracked
git ls-files | Select-String "credentials.json|token.json"
# Should return nothing

# Verify .gitignore is working
git check-ignore -v backend/credentials.json backend/token.json
# Should show they are ignored
```

## Prevention

1. **Pre-commit hook**: Install gitleaks or git-secrets
2. **Regular audits**: Run `verify-no-secrets.ps1` weekly
3. **Team training**: Share `SECURITY_QUICK_REFERENCE.md`
4. **CI/CD checks**: Add secret scanning to your pipeline

## Summary

This is a **comprehensive security issue** that requires:

- Immediate removal of Google OAuth credentials from git
- Rotation of ALL exposed credentials
- Sanitization of documentation files
- Cleanup of git history
- Better .gitignore configuration

**Estimated Time**: 2-3 hours to complete all steps

**Risk Level**: HIGH - Multiple types of credentials exposed

---

**Created**: 2026-01-23
**Status**: URGENT - Action Required
