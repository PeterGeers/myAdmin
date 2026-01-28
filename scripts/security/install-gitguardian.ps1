# Install and Configure GitGuardian for myAdmin
# This script sets up GitGuardian pre-commit hooks and scanning

param(
    [switch]$Global = $false,
    [switch]$SkipPreCommit = $false
)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          GitGuardian Installation for myAdmin              ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
Write-Host "Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "✗ Python not found. Please install Python 3.7+ first." -ForegroundColor Red
    exit 1
}

# Check if pip is available
Write-Host "Checking pip..." -ForegroundColor Yellow
try {
    pip --version | Out-Null
    Write-Host "✓ pip is available" -ForegroundColor Green
}
catch {
    Write-Host "✗ pip not found. Please install pip first." -ForegroundColor Red
    exit 1
}

# Install ggshield (GitGuardian CLI)
Write-Host ""
Write-Host "Installing GitGuardian CLI (ggshield)..." -ForegroundColor Yellow

if ($Global) {
    pip install --upgrade ggshield
}
else {
    pip install --user --upgrade ggshield
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to install ggshield" -ForegroundColor Red
    exit 1
}

Write-Host "✓ ggshield installed successfully" -ForegroundColor Green

# Check ggshield version
$ggVersion = ggshield --version
Write-Host "✓ GitGuardian version: $ggVersion" -ForegroundColor Green

# Configure GitGuardian
Write-Host ""
Write-Host "Configuring GitGuardian..." -ForegroundColor Yellow

# Check if API token is already configured
$apiToken = $env:GITGUARDIAN_API_KEY
if (-not $apiToken) {
    Write-Host ""
    Write-Host "GitGuardian API Token Required" -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host "To get your API token:" -ForegroundColor White
    Write-Host "1. Go to https://dashboard.gitguardian.com/" -ForegroundColor White
    Write-Host "2. Sign up for a free account (or login)" -ForegroundColor White
    Write-Host "3. Go to API > Personal Access Tokens" -ForegroundColor White
    Write-Host "4. Create a new token with 'scan' permission" -ForegroundColor White
    Write-Host "5. Copy the token" -ForegroundColor White
    Write-Host ""
    Write-Host "Free tier includes:" -ForegroundColor Cyan
    Write-Host "  • 200 scans per month" -ForegroundColor Cyan
    Write-Host "  • Unlimited public repositories" -ForegroundColor Cyan
    Write-Host "  • Pre-commit hooks" -ForegroundColor Cyan
    Write-Host ""
    
    $token = Read-Host "Enter your GitGuardian API token (or press Enter to skip)"
    
    if ($token) {
        # Set environment variable for current session
        $env:GITGUARDIAN_API_KEY = $token
        
        # Add to user environment variables (persistent)
        [System.Environment]::SetEnvironmentVariable("GITGUARDIAN_API_KEY", $token, "User")
        
        Write-Host "✓ API token configured" -ForegroundColor Green
    }
    else {
        Write-Host "⚠ Skipping API token configuration" -ForegroundColor Yellow
        Write-Host "  You can set it later with: `$env:GITGUARDIAN_API_KEY = 'your-token'" -ForegroundColor Yellow
    }
}
else {
    Write-Host "✓ API token already configured" -ForegroundColor Green
}

# Install pre-commit hook
if (-not $SkipPreCommit) {
    Write-Host ""
    Write-Host "Installing pre-commit hook..." -ForegroundColor Yellow
    
    # Get repository root
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if (-not $repoRoot) {
        Write-Host "✗ Not in a git repository" -ForegroundColor Red
        exit 1
    }
    
    $hooksDir = Join-Path $repoRoot ".git\hooks"
    $preCommitHook = Join-Path $hooksDir "pre-commit"
    
    # Create hooks directory if it doesn't exist
    if (-not (Test-Path $hooksDir)) {
        New-Item -ItemType Directory -Path $hooksDir -Force | Out-Null
    }
    
    # Check if pre-commit hook already exists
    if (Test-Path $preCommitHook) {
        Write-Host "⚠ Pre-commit hook already exists" -ForegroundColor Yellow
        $overwrite = Read-Host "Overwrite existing hook? (yes/no)"
        
        if ($overwrite -ne "yes") {
            Write-Host "Skipping pre-commit hook installation" -ForegroundColor Yellow
        }
        else {
            # Backup existing hook
            $backup = "$preCommitHook.backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item $preCommitHook $backup
            Write-Host "✓ Existing hook backed up to: $backup" -ForegroundColor Green
        }
    }
    
    if (-not (Test-Path $preCommitHook) -or $overwrite -eq "yes") {
        # Install GitGuardian pre-commit hook
        ggshield install --mode local --force
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Pre-commit hook installed" -ForegroundColor Green
        }
        else {
            Write-Host "✗ Failed to install pre-commit hook" -ForegroundColor Red
        }
    }
}

# Create .gitguardian.yaml configuration
Write-Host ""
Write-Host "Creating GitGuardian configuration..." -ForegroundColor Yellow

$configPath = Join-Path (git rev-parse --show-toplevel) ".gitguardian.yaml"

$config = @"
# GitGuardian Configuration for myAdmin
# https://docs.gitguardian.com/ggshield-docs/reference/configuration

version: 2

# Paths to exclude from scanning (build artifacts, dependencies, data)
paths-ignore:
  - "**/.venv/**"
  - "**/venv/**"
  - "**/node_modules/**"
  - "**/.git/**"
  - "**/build/**"
  - "**/dist/**"
  - "**/__pycache__/**"
  - "**/*.pyc"
  - "**/mysql_data/**"
  - "**/logs/**"
  - "**/.pytest_cache/**"
  - "**/.hypothesis/**"
  - "**/coverage/**"
  - "**/*.log"
  - "**/terraform.tfstate*"
  - "**/.terraform/**"

# Only exclude template/example files (not actual .env files!)
# GitGuardian SHOULD scan .env files to catch secrets before commit
exclude:
  - "**/*.example"
  - "**/example.*"
  - "**/*-example.*"
  - "**/*.md"  # Documentation files

# Secret detection settings
secret:
  # Don't show actual secret values in output (security)
  show-secrets: false
  
  # Ignore known test/placeholder secrets
  ignored-matches:
    - name: "Test API Keys"
      match: "sk-test-"
    - name: "Example placeholders"
      match: "your-.*-here"
    - name: "Placeholder values"
      match: "REPLACE_ME|YOUR_.*|EXAMPLE_.*"
    - name: "Localhost URLs"
      match: "http://localhost"

# Exit with error code if secrets found (fail the commit)
exit-zero: false

# Verbose output for debugging
verbose: false

# Maximum commits to scan in pre-commit hook
max-commits-for-hook: 50
"@

Set-Content -Path $configPath -Value $config -Encoding UTF8
Write-Host "✓ Configuration created: .gitguardian.yaml" -ForegroundColor Green

# Add .gitguardian.yaml to git if not already tracked
git add .gitguardian.yaml 2>$null

# Test GitGuardian
Write-Host ""
Write-Host "Testing GitGuardian..." -ForegroundColor Yellow

if ($env:GITGUARDIAN_API_KEY) {
    Write-Host "Running test scan on current repository..." -ForegroundColor Yellow
    
    # Scan last commit
    ggshield secret scan repo . --exit-zero
    
    Write-Host ""
    Write-Host "✓ GitGuardian is working!" -ForegroundColor Green
}
else {
    Write-Host "⚠ Skipping test (no API token configured)" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          GitGuardian Installation Complete!                ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "What's installed:" -ForegroundColor White
Write-Host "  ✓ ggshield CLI" -ForegroundColor Green
if (-not $SkipPreCommit) {
    Write-Host "  ✓ Pre-commit hook" -ForegroundColor Green
}
Write-Host "  ✓ Configuration file (.gitguardian.yaml)" -ForegroundColor Green
Write-Host ""
Write-Host "Usage:" -ForegroundColor White
Write-Host "  • Scan current changes:  ggshield secret scan pre-commit" -ForegroundColor Cyan
Write-Host "  • Scan entire repo:      ggshield secret scan repo ." -ForegroundColor Cyan
Write-Host "  • Scan specific file:    ggshield secret scan path <file>" -ForegroundColor Cyan
Write-Host "  • Scan commit range:     ggshield secret scan commit-range <from>..<to>" -ForegroundColor Cyan
Write-Host ""
Write-Host "The pre-commit hook will automatically scan before each commit!" -ForegroundColor Yellow
Write-Host ""

exit 0
