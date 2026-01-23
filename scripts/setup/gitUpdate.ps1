param([string]$message)

Set-Location (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))

if (-not (Test-Path ".git")) {
    Write-Error "Not in git repository"
    exit 1
}

Write-Host "🔍 Checking for credentials..." -ForegroundColor Yellow

# ═══ GITGUARDIAN SECURITY SCAN ═══
Write-Host ""
Write-Host "Running GitGuardian security scan..." -ForegroundColor Cyan

# Check if ggshield is installed
try {
    ggshield --version | Out-Null
    $ggInstalled = $true
}
catch {
    $ggInstalled = $false
    Write-Host "⚠ GitGuardian not installed - using basic checks only" -ForegroundColor Yellow
    Write-Host "  Install with: scripts/security/install-gitguardian.ps1" -ForegroundColor Yellow
}

if ($ggInstalled -and $env:GITGUARDIAN_API_KEY) {
    Write-Host "Scanning with GitGuardian..." -ForegroundColor Cyan
    
    # Scan current changes
    ggshield secret scan pre-commit
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
        Write-Host "║  🚨 SECURITY ALERT: Secrets detected in your changes!     ║" -ForegroundColor Red
        Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
        Write-Host ""
        Write-Host "GitGuardian found potential secrets in your code." -ForegroundColor Red
        Write-Host "Please review the output above and remove any secrets." -ForegroundColor Red
        Write-Host ""
        Write-Host "Common secrets to check:" -ForegroundColor Yellow
        Write-Host "  • API keys (OpenRouter, AWS, Google, Cognito)" -ForegroundColor Yellow
        Write-Host "  • Database passwords" -ForegroundColor Yellow
        Write-Host "  • JWT secrets" -ForegroundColor Yellow
        Write-Host "  • Private keys" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
    
    Write-Host "✅ GitGuardian scan passed - no secrets detected" -ForegroundColor Green
}
else {
    # Fallback to basic regex checks
    Write-Host "Using basic credential checks..." -ForegroundColor Yellow
    
    $files = git diff --name-only HEAD 2>$null | Where-Object { $_ -and (Test-Path $_) }
    $blocked = $false

    foreach ($file in $files) {
        if ($file -like "*gitUpdate*.ps1" -or $file -like "*requirements*.txt") { continue }
        
        $content = Get-Content $file -ErrorAction SilentlyContinue
        if ($content) {
            # Check for various secret patterns
            $patterns = @(
                @{Pattern = "sk-or-v1-[a-f0-9]{64}"; Name = "OpenRouter API key" },
                @{Pattern = "AKIA[0-9A-Z]{16}"; Name = "AWS Access Key" },
                @{Pattern = "sk-[a-zA-Z0-9]{20,}"; Name = "Generic API key" },
                @{Pattern = "ghp_[a-zA-Z0-9]{36}"; Name = "GitHub Personal Access Token" },
                @{Pattern = "xox[baprs]-[0-9a-zA-Z]{10,}"; Name = "Slack Token" },
                @{Pattern = "AIza[0-9A-Za-z\\-_]{35}"; Name = "Google API Key" },
                @{Pattern = "ya29\.[0-9A-Za-z\\-_]+"; Name = "Google OAuth Token" },
                @{Pattern = "[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com"; Name = "Google OAuth Client ID" },
                @{Pattern = "-----BEGIN (RSA |DSA |EC )?PRIVATE KEY-----"; Name = "Private Key" }
            )
            
            foreach ($pattern in $patterns) {
                if ($content | Select-String $pattern.Pattern -Quiet) {
                    Write-Host "❌ BLOCKED: $($pattern.Name) detected in $file" -ForegroundColor Red
                    $blocked = $true
                }
            }
        }
    }

    if ($blocked) { 
        Write-Host ""
        Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Red
        Write-Host "║  🚨 SECURITY ALERT: Potential secrets detected!           ║" -ForegroundColor Red
        Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Red
        Write-Host ""
        Write-Host "For better security scanning, install GitGuardian:" -ForegroundColor Yellow
        Write-Host "  scripts/security/install-gitguardian.ps1" -ForegroundColor Cyan
        Write-Host ""
        exit 1 
    }
    
    Write-Host "✅ Basic checks passed" -ForegroundColor Green
}

# ═══ END SECURITY SCAN ═══

if (-not $message) { $message = "Auto commit - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" }

Write-Host ""
Write-Host "✅ Safe to commit" -ForegroundColor Green
git add .
git commit -m "$message"
git push origin main
Write-Host "✅ Done" -ForegroundColor Green