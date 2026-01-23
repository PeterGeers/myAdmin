# Security Scripts for myAdmin

This directory contains security-related scripts to protect your codebase from accidentally committing secrets.

## GitGuardian Integration

GitGuardian is a secrets detection tool that scans your code for API keys, passwords, and other sensitive information before you commit them.

### Quick Start

```powershell
# Install GitGuardian
.\scripts\security\install-gitguardian.ps1
```

This will:
1. Install `ggshield` (GitGuardian CLI)
2. Set up pre-commit hooks
3. Create `.gitguardian.yaml` configuration
4. Prompt for API token (free tier available)

### Get Your Free API Token

1. Go to https://dashboard.gitguardian.com/
2. Sign up for a free account
3. Navigate to **API > Personal Access Tokens**
4. Create a new token with `scan` permission
5. Copy the token

**Free Tier Includes**:
- 200 scans per month
- Unlimited public repositories
- Pre-commit hooks
- Secret detection

### Usage

#### Automatic Scanning (Pre-Commit Hook)
Once installed, GitGuardian automatically scans every commit:

```powershell
git add .
git commit -m "My changes"
# GitGuardian automatically scans before commit
```

If secrets are detected, the commit is blocked.

#### Manual Scanning

```powershell
# Scan current changes
ggshield secret scan pre-commit

# Scan entire repository
ggshield secret scan repo .

# Scan specific file
ggshield secret scan path backend/.env

# Scan commit range
ggshield secret scan commit-range HEAD~10..HEAD

# Scan with CI mode (for pipelines)
ggshield secret scan ci
```

### Integration with Existing Scripts

GitGuardian is automatically integrated into:

#### 1. `pipeline.ps1`
The CI/CD pipeline now includes GitGuardian scanning in Stage 0 (Git Operations):

```powershell
.\scripts\CICD\pipeline.ps1
# Automatically scans before committing
```

If secrets are detected:
- Pipeline stops
- Shows detailed report
- Requires manual override (`-Force` flag)

#### 2. `gitUpdate.ps1`
The git update script now uses GitGuardian:

```powershell
.\scripts\setup\gitUpdate.ps1 "My commit message"
# Scans with GitGuardian if installed
# Falls back to basic regex checks if not
```

### Configuration

The `.gitguardian.yaml` file controls what gets scanned:

```yaml
# Paths to exclude
paths-ignore:
  - "**/.venv/**"
  - "**/node_modules/**"
  - "**/mysql_data/**"

# Files to exclude
exclude:
  - ".env.example"
  - "backend/.env.example"

# Ignored patterns (for known test secrets)
secret:
  ignored-matches:
    - name: "Test API Key"
      match: "sk-test-"
```

### What GitGuardian Detects

GitGuardian scans for 350+ types of secrets including:

**API Keys**:
- OpenRouter API keys
- AWS Access Keys & Secret Keys
- Google API keys
- GitHub tokens
- Slack tokens

**Cloud Credentials**:
- AWS Cognito credentials
- Azure credentials
- GCP service account keys

**Database**:
- MySQL passwords
- PostgreSQL connection strings
- MongoDB URIs

**Authentication**:
- JWT secrets
- OAuth tokens
- Private keys (RSA, DSA, EC)

**And many more...**

### Bypassing GitGuardian (Not Recommended)

If you absolutely need to commit something flagged by GitGuardian:

#### Option 1: Add to Ignored Matches
Edit `.gitguardian.yaml`:

```yaml
secret:
  ignored-matches:
    - name: "My specific case"
      match: "pattern-to-ignore"
```

#### Option 2: Use Git Commit Flag
```powershell
git commit --no-verify -m "Message"
```

⚠️ **Warning**: Only use this if you're absolutely sure there are no real secrets!

### Troubleshooting

#### "ggshield: command not found"
```powershell
# Reinstall GitGuardian
pip install --user --upgrade ggshield

# Or install globally
pip install --upgrade ggshield
```

#### "API key not configured"
```powershell
# Set environment variable
$env:GITGUARDIAN_API_KEY = "your-api-key-here"

# Make it persistent (Windows)
[System.Environment]::SetEnvironmentVariable("GITGUARDIAN_API_KEY", "your-key", "User")
```

#### "Pre-commit hook not working"
```powershell
# Reinstall hook
ggshield install --mode local --force
```

#### "Too many API calls"
Free tier has 200 scans/month. If you exceed:
- Upgrade to paid plan ($15/month for 2000 scans)
- Use `--exit-zero` flag for non-critical scans
- Reduce scan frequency

### Best Practices

1. **Never commit secrets**: Use environment variables
2. **Use .env files**: Keep secrets in `.env` (gitignored)
3. **Use .env.example**: Commit example files with placeholders
4. **Rotate secrets**: If accidentally committed, rotate immediately
5. **Review scan results**: Don't blindly override warnings

### For Multi-Tenant / SaaS

When deploying myAdmin as a SaaS:

1. **Enable GitGuardian in CI/CD**: Scan on every deployment
2. **Scan on PR**: Add GitHub Action for pull requests
3. **Monitor dashboard**: Check GitGuardian dashboard regularly
4. **Team access**: Add team members to GitGuardian
5. **Compliance**: Use for SOC2, ISO27001 compliance

### GitHub Actions Integration (Future)

For automated scanning on GitHub:

```yaml
# .github/workflows/gitguardian.yml
name: GitGuardian Scan

on: [push, pull_request]

jobs:
  scanning:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: GitGuardian scan
        uses: GitGuardian/ggshield-action@v1
        env:
          GITGUARDIAN_API_KEY: ${{ secrets.GITGUARDIAN_API_KEY }}
```

### Cost

**Free Tier** (Recommended for start):
- 200 scans/month
- Unlimited public repos
- Pre-commit hooks
- **Cost**: $0

**Team Plan** (For SaaS growth):
- 2000 scans/month
- Private repos
- Team collaboration
- **Cost**: $15/month

**Enterprise** (For large SaaS):
- Unlimited scans
- SSO, SAML
- Custom policies
- **Cost**: Custom pricing

### Support

- **Documentation**: https://docs.gitguardian.com/
- **Dashboard**: https://dashboard.gitguardian.com/
- **Support**: support@gitguardian.com

### Summary

GitGuardian provides:
- ✅ Automatic secret detection
- ✅ Pre-commit protection
- ✅ 350+ secret types detected
- ✅ Free tier for personal use
- ✅ Integrated into pipeline.ps1 and gitUpdate.ps1
- ✅ Configurable via .gitguardian.yaml
- ✅ Essential for production deployment

**Install now to protect your secrets!**

```powershell
.\scripts\security\install-gitguardian.ps1
```
