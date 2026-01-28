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

# Use shared GitGuardian scanning module
. "$PSScriptRoot/../security/Invoke-GitGuardianScan.ps1"
$scanResult = Invoke-GitGuardianScan -AllowSkip $true -UseWriteLog $false

if ($scanResult -ne 0) {
    Write-Host "Aborting due to security scan failure." -ForegroundColor Red
    exit 1
}

# If GitGuardian scan passed or was skipped, continue with basic checks
if ($scanResult -eq 0) {
    # Fallback to basic regex checks
    Write-Host "Running additional basic credential checks..." -ForegroundColor Yellow
    
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