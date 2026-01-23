# GitGuardian Integration for myAdmin

## Overview

GitGuardian has been integrated into myAdmin's git workflow to prevent accidentally committing secrets (API keys, passwords, tokens, etc.) to the repository.

## What's Been Added

### 1. Installation Script

**Location**: `scripts/security/install-gitguardian.ps1`

**Features**:

- Installs `ggshield` (GitGuardian CLI)
- Configures API token
- Sets up pre-commit hooks
- Creates `.gitguardian.yaml` configuration
- Tests the installation

**Usage**:

```powershell
.\scripts\security\install-gitguardian.ps1
```

### 2. Pipeline Integration

**Location**: `scripts/CICD/pipeline.ps1`

**Changes**:

- Added GitGuardian scan in Stage 0 (Git Operations)
- Scans staged changes before committing
- Blocks pipeline if secrets detected
- Allows override with `-Force` flag (with warning)

**Behavior**:

```
Pipeline runs → GitGuardian scans → Secrets found? → Block commit
                                  → No secrets? → Continue
```

### 3. GitUpdate Script Enhancement

**Location**: `scripts/setup/gitUpdate.ps1`

**Changes**:

- Uses GitGuardian if installed
- Falls back to enhanced regex checks if not
- Detects 9+ types of secrets (vs 1 before)
- Better error messages

**New Patterns Detected**:

- OpenRouter API keys
- AWS Access Keys
- Generic API keys
- GitHub tokens
- Slack tokens
- Google API keys
- Google OAuth tokens
- Private keys (RSA, DSA, EC)

### 4. Configuration File

**Location**: `.gitguardian.yaml` (created by install script)

**Excludes**:

- Virtual environments (`.venv`, `venv`)
- Node modules
- Build directories
- MySQL data
- Logs and cache
- Example files (`.env.example`)

### 5. Documentation

**Location**: `scripts/security/README.md`

**Includes**:

- Quick start guide
- Usage examples
- Troubleshooting
- Best practices
- Multi-tenant considerations

## How It Works

### Automatic Protection (Pre-Commit Hook)

```powershell
# User makes changes
git add .
git commit -m "Add new feature"

# GitGuardian automatically scans
# ↓
# Secrets found? → Commit blocked
# No secrets? → Commit proceeds
```

### Pipeline Protection

```powershell
# Run pipeline
.\scripts\CICD\pipeline.ps1

# Stage 0: Git Operations
# ↓
# GitGuardian scans staged changes
# ↓
# Secrets found? → Pipeline stops (unless -Force)
# No secrets? → Pipeline continues
```

### Manual Scanning

```powershell
# Scan current changes
ggshield secret scan pre-commit

# Scan entire repo
ggshield secret scan repo .

# Scan specific file
ggshield secret scan path backend/.env
```

## Setup Instructions

### Step 1: Install GitGuardian

```powershell
.\scripts\security\install-gitguardian.ps1
```

### Step 2: Get Free API Token

1. Go to https://dashboard.gitguardian.com/
2. Sign up (free tier: 200 scans/month)
3. Navigate to **API > Personal Access Tokens**
4. Create token with `scan` permission
5. Copy token

### Step 3: Configure Token

The install script will prompt for the token, or set manually:

```powershell
# Current session
$env:GITGUARDIAN_API_KEY = "your-token-here"

# Persistent (Windows)
[System.Environment]::SetEnvironmentVariable("GITGUARDIAN_API_KEY", "your-token", "User")
```

### Step 4: Test

```powershell
# Test scan
ggshield secret scan repo .

# Test pre-commit hook
git add .
git commit -m "Test"
# Should scan automatically
```

## What GitGuardian Detects

**350+ types of secrets including**:

### API Keys

- OpenRouter: `sk-or-v1-[a-f0-9]{64}`
- AWS: `AKIA[0-9A-Z]{16}`
- Google: `AIza[0-9A-Za-z\-_]{35}`
- GitHub: `ghp_[a-zA-Z0-9]{36}`
- Slack: `xox[baprs]-[0-9a-zA-Z]{10,}`

### Cloud Credentials

- AWS Cognito credentials
- Azure credentials
- GCP service account keys

### Database

- MySQL passwords
- PostgreSQL connection strings
- MongoDB URIs

### Authentication

- JWT secrets
- OAuth tokens
- Private keys

## Integration Points

### 1. Development Workflow

```
Developer writes code
↓
git add .
↓
git commit -m "..."
↓
Pre-commit hook runs GitGuardian
↓
Secrets detected? → Commit blocked
No secrets? → Commit succeeds
```

### 2. CI/CD Pipeline

```
pipeline.ps1 runs
↓
Stage 0: Git Operations
↓
GitGuardian scans staged changes
↓
Secrets detected? → Pipeline stops
No secrets? → Continue to build/deploy
```

### 3. Quick Commits

```
gitUpdate.ps1 "message"
↓
GitGuardian scans (if installed)
↓
Fallback to regex checks (if not)
↓
Secrets detected? → Blocked
No secrets? → Commit & push
```

## Configuration

### Exclude Paths

Edit `.gitguardian.yaml`:

```yaml
paths-ignore:
  - "**/.venv/**"
  - "**/node_modules/**"
  - "**/mysql_data/**"
  - "**/logs/**"
```

### Ignore Specific Patterns

```yaml
secret:
  ignored-matches:
    - name: "Test API Key"
      match: "sk-test-"
    - name: "Example secrets"
      match: "your-api-key-here"
```

## Cost

### Free Tier (Recommended for Start)

- **200 scans/month**
- Unlimited public repos
- Pre-commit hooks
- **Cost**: $0/month

**Sufficient for**:

- Personal use
- Small team (2-3 developers)
- ~10 commits/day

### Team Plan (For SaaS Growth)

- **2000 scans/month**
- Private repos
- Team collaboration
- **Cost**: $15/month

**Sufficient for**:

- Growing SaaS
- 5-10 developers
- ~100 commits/day

### Enterprise (For Large SaaS)

- Unlimited scans
- SSO, SAML
- Custom policies
- **Cost**: Custom pricing

## Best Practices

### 1. Never Commit Secrets

```powershell
# ❌ Bad
$apiKey = "sk-or-v1-abc123..."

# ✅ Good
$apiKey = $env:OPENROUTER_API_KEY
```

### 2. Use .env Files

```bash
# .env (gitignored)
OPENROUTER_API_KEY=sk-or-v1-abc123...
COGNITO_USER_POOL_ID=eu-west-1_ABC123

# .env.example (committed)
OPENROUTER_API_KEY=your-openrouter-api-key-here
COGNITO_USER_POOL_ID=your-cognito-pool-id
```

### 3. Rotate If Leaked

If you accidentally commit a secret:

1. **Immediately rotate** the secret
2. **Revoke** the old one
3. **Update** all environments
4. **Remove** from git history (BFG Repo-Cleaner)

### 4. Review Scan Results

Don't blindly override warnings:

```powershell
# ❌ Bad
git commit --no-verify

# ✅ Good
# Review the detected secret
# Remove it or add to ignored-matches if false positive
```

## Multi-Tenant / SaaS Considerations

When deploying myAdmin as a SaaS:

### 1. Enable in CI/CD

```yaml
# GitHub Actions
- name: GitGuardian scan
  uses: GitGuardian/ggshield-action@v1
  env:
    GITGUARDIAN_API_KEY: ${{ secrets.GITGUARDIAN_API_KEY }}
```

### 2. Scan on Every PR

Prevent secrets from entering main branch

### 3. Monitor Dashboard

Check https://dashboard.gitguardian.com/ regularly

### 4. Team Access

Add team members to GitGuardian organization

### 5. Compliance

Use for SOC2, ISO27001 compliance requirements

## Troubleshooting

### "ggshield: command not found"

```powershell
pip install --user --upgrade ggshield
```

### "API key not configured"

```powershell
$env:GITGUARDIAN_API_KEY = "your-key"
```

### "Pre-commit hook not working"

```powershell
ggshield install --mode local --force
```

### "Too many API calls"

- Free tier: 200 scans/month
- Upgrade to Team plan: $15/month for 2000 scans
- Or use `--exit-zero` for non-critical scans

### "False positive detected"

Add to `.gitguardian.yaml`:

```yaml
secret:
  ignored-matches:
    - name: "My false positive"
      match: "pattern-to-ignore"
```

## Railway Deployment Considerations

When deploying to Railway:

### 1. Environment Variables

Store all secrets in Railway environment variables:

- `OPENROUTER_API_KEY`
- `COGNITO_USER_POOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `DB_PASSWORD`
- `JWT_SECRET`

### 2. Never Hardcode

```python
# ❌ Bad
COGNITO_POOL_ID = "eu-west-1_ABC123"

# ✅ Good
COGNITO_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
```

### 3. Railway Secrets

Railway encrypts environment variables at rest

### 4. Scan Before Deploy

Pipeline automatically scans before Railway deployment

## Summary

GitGuardian integration provides:

✅ **Automatic secret detection** (350+ types)
✅ **Pre-commit protection** (blocks commits with secrets)
✅ **Pipeline integration** (scans before deployment)
✅ **Enhanced gitUpdate.ps1** (better secret detection)
✅ **Free tier available** (200 scans/month)
✅ **Configurable** (.gitguardian.yaml)
✅ **Essential for production** (prevents data breaches)

## Next Steps

1. **Install GitGuardian**:

   ```powershell
   .\scripts\security\install-gitguardian.ps1
   ```

2. **Get API token** from https://dashboard.gitguardian.com/

3. **Test the integration**:

   ```powershell
   ggshield secret scan repo .
   ```

4. **Commit with confidence**:
   ```powershell
   git add .
   git commit -m "My changes"
   # GitGuardian automatically protects you!
   ```

**Your secrets are now protected!** 🔒
