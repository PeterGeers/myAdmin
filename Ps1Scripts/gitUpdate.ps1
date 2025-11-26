param([string]$message)

# Change to myAdmin project root directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptPath "..")

# Verify we're in the correct directory (should contain .git folder)
if (-not (Test-Path ".git")) {
    Write-Error "Not in a git repository. Current location: $(Get-Location)"
    exit 1
}

# 🔍 CREDENTIAL LEAK PREVENTION
Write-Host "🔍 Checking for credential leaks..." -ForegroundColor Yellow

# Check for API keys in staged/modified files
$modifiedFiles = git diff --name-only HEAD 2>$null | Where-Object { $_ -and (Test-Path $_) }
foreach ($file in $modifiedFiles) {
    $content = Get-Content $file -ErrorAction SilentlyContinue
    # Skip checking this script file to avoid false positives
    if ($file -like "*gitUpdate.ps1") { continue }
    
    if ($content -and ($content | Select-String "sk-[a-zA-Z0-9]{20,}" -Quiet)) {
        Write-Host "❌ BLOCKED: API key found in $file" -ForegroundColor Red
        Write-Host "Please replace with placeholder values" -ForegroundColor Yellow
        exit 1
    }
    
    # Check for hardcoded passwords (not env vars)
    if ($file -notlike "*.example*" -and $content -and ($content | Select-String 'MYSQL_ROOT_PASSWORD.*=.*"[^"\$]{6,}"' -Quiet)) {
        Write-Host "❌ BLOCKED: Hardcoded password found in $file" -ForegroundColor Red
        Write-Host "Please use environment variables" -ForegroundColor Yellow
        exit 1
    }

}

# Show what will be committed
Write-Host "📋 Files to be committed:" -ForegroundColor Cyan
git status --porcelain

# Set default message if none provided
if (-not $message) {
    $message = "Auto commit - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

Write-Host "✅ No credential leaks detected" -ForegroundColor Green

# Commit with safety checks passed
git add .
git commit -m "$message - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
git push origin main

Write-Host "✅ Safe commit completed" -ForegroundColor Green

# .\gitUpdate.ps1 "Your message here"
# Examples:
# .\gitUpdate.ps1 "Fixed frontend compilation errors"
# .\gitUpdate.ps1 "Added new features"
# .\gitUpdate.ps1 (no message, just date/time)