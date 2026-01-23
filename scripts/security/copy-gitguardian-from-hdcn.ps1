# Copy GitGuardian Configuration from h-dcn Project
# This script helps you reuse your existing GitGuardian API token

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     Copy GitGuardian Config from h-dcn to myAdmin          ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Method 1: Check if API key is already in environment variables
Write-Host "Method 1: Checking environment variables..." -ForegroundColor Yellow
Write-Host ""

# Check user environment variable
$userApiKey = [System.Environment]::GetEnvironmentVariable("GITGUARDIAN_API_KEY", "User")
if ($userApiKey) {
    Write-Host "✓ Found GitGuardian API key in user environment variables!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Your API key is already configured system-wide." -ForegroundColor Green
    Write-Host "It should work in myAdmin automatically." -ForegroundColor Green
    Write-Host ""
    Write-Host "To verify, run:" -ForegroundColor Cyan
    Write-Host "  ggshield secret scan repo . --exit-zero" -ForegroundColor White
    Write-Host ""
    exit 0
}

# Check system environment variable
$systemApiKey = [System.Environment]::GetEnvironmentVariable("GITGUARDIAN_API_KEY", "Machine")
if ($systemApiKey) {
    Write-Host "✓ Found GitGuardian API key in system environment variables!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Your API key is already configured system-wide." -ForegroundColor Green
    Write-Host "It should work in myAdmin automatically." -ForegroundColor Green
    Write-Host ""
    Write-Host "To verify, run:" -ForegroundColor Cyan
    Write-Host "  ggshield secret scan repo . --exit-zero" -ForegroundColor White
    Write-Host ""
    exit 0
}

Write-Host "✗ API key not found in environment variables" -ForegroundColor Yellow
Write-Host ""

# Method 2: Check h-dcn project directory
Write-Host "Method 2: Looking for h-dcn project..." -ForegroundColor Yellow
Write-Host ""

# Common locations for h-dcn project
$possiblePaths = @(
    "C:\Users\peter\h-dcn",
    "C:\Users\peter\projects\h-dcn",
    "C:\Users\peter\Documents\h-dcn",
    "C:\Users\peter\aws\h-dcn",
    "C:\projects\h-dcn",
    "C:\h-dcn"
)

$hdcnPath = $null
foreach ($path in $possiblePaths) {
    if (Test-Path $path) {
        $hdcnPath = $path
        Write-Host "✓ Found h-dcn project at: $path" -ForegroundColor Green
        break
    }
}

if (-not $hdcnPath) {
    Write-Host "✗ Could not find h-dcn project in common locations" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please enter the path to your h-dcn project:" -ForegroundColor Cyan
    $customPath = Read-Host "Path"
    
    if ($customPath -and (Test-Path $customPath)) {
        $hdcnPath = $customPath
        Write-Host "✓ Using path: $hdcnPath" -ForegroundColor Green
    }
    else {
        Write-Host "✗ Invalid path" -ForegroundColor Red
        Write-Host ""
        Write-Host "Manual steps to copy API key:" -ForegroundColor Yellow
        Write-Host "1. Go to your h-dcn project" -ForegroundColor White
        Write-Host "2. Look for .env file or environment variables" -ForegroundColor White
        Write-Host "3. Find GITGUARDIAN_API_KEY" -ForegroundColor White
        Write-Host "4. Copy the value" -ForegroundColor White
        Write-Host "5. Run: `$env:GITGUARDIAN_API_KEY = 'your-key-here'" -ForegroundColor White
        Write-Host "6. Make it persistent:" -ForegroundColor White
        Write-Host "   [System.Environment]::SetEnvironmentVariable('GITGUARDIAN_API_KEY', 'your-key', 'User')" -ForegroundColor White
        Write-Host ""
        exit 1
    }
}

Write-Host ""

# Method 3: Check for .env file in h-dcn
Write-Host "Method 3: Checking for .env file in h-dcn..." -ForegroundColor Yellow
Write-Host ""

$envFile = Join-Path $hdcnPath ".env"
if (Test-Path $envFile) {
    Write-Host "✓ Found .env file" -ForegroundColor Green
    
    $envContent = Get-Content $envFile
    $apiKeyLine = $envContent | Where-Object { $_ -match "GITGUARDIAN_API_KEY\s*=\s*(.+)" }
    
    if ($apiKeyLine) {
        $apiKey = $apiKeyLine -replace "GITGUARDIAN_API_KEY\s*=\s*", "" -replace '"', '' -replace "'", ''
        $apiKey = $apiKey.Trim()
        
        Write-Host "✓ Found API key in .env file!" -ForegroundColor Green
        Write-Host ""
        Write-Host "API Key (first 20 chars): $($apiKey.Substring(0, [Math]::Min(20, $apiKey.Length)))..." -ForegroundColor Cyan
        Write-Host ""
        
        $confirm = Read-Host "Copy this API key to myAdmin? (yes/no)"
        
        if ($confirm -eq "yes") {
            # Set for current session
            $env:GITGUARDIAN_API_KEY = $apiKey
            
            # Set persistently for user
            [System.Environment]::SetEnvironmentVariable("GITGUARDIAN_API_KEY", $apiKey, "User")
            
            Write-Host ""
            Write-Host "✓ API key configured for myAdmin!" -ForegroundColor Green
            Write-Host ""
            Write-Host "Testing GitGuardian..." -ForegroundColor Yellow
            
            # Test the API key
            ggshield secret scan repo . --exit-zero
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host ""
                Write-Host "✓ GitGuardian is working!" -ForegroundColor Green
                Write-Host ""
                Write-Host "You can now use GitGuardian in myAdmin:" -ForegroundColor Cyan
                Write-Host "  • Pre-commit hooks will work automatically" -ForegroundColor White
                Write-Host "  • pipeline.ps1 will scan before deployment" -ForegroundColor White
                Write-Host "  • gitUpdate.ps1 will scan before push" -ForegroundColor White
                Write-Host ""
            }
            else {
                Write-Host ""
                Write-Host "⚠ API key might be invalid or expired" -ForegroundColor Yellow
                Write-Host "Check your GitGuardian dashboard: https://dashboard.gitguardian.com/" -ForegroundColor Cyan
                Write-Host ""
            }
            
            exit 0
        }
        else {
            Write-Host "Cancelled by user" -ForegroundColor Yellow
            exit 0
        }
    }
    else {
        Write-Host "✗ GITGUARDIAN_API_KEY not found in .env file" -ForegroundColor Yellow
    }
}
else {
    Write-Host "✗ No .env file found in h-dcn project" -ForegroundColor Yellow
}

Write-Host ""

# Method 4: Check for .gitguardian.yaml in h-dcn
Write-Host "Method 4: Checking for .gitguardian.yaml..." -ForegroundColor Yellow
Write-Host ""

$ggConfigFile = Join-Path $hdcnPath ".gitguardian.yaml"
if (Test-Path $ggConfigFile) {
    Write-Host "✓ Found .gitguardian.yaml in h-dcn" -ForegroundColor Green
    Write-Host ""
    Write-Host "Copying configuration to myAdmin..." -ForegroundColor Yellow
    
    $myAdminRoot = Split-Path -Parent $PSScriptRoot
    $myAdminRoot = Split-Path -Parent $myAdminRoot
    $destConfig = Join-Path $myAdminRoot ".gitguardian.yaml"
    
    Copy-Item $ggConfigFile $destConfig -Force
    Write-Host "✓ Configuration copied!" -ForegroundColor Green
    Write-Host ""
}

# Method 5: Manual instructions
Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Manual Steps to Copy API Key from h-dcn:" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option A: From h-dcn .env file" -ForegroundColor White
Write-Host "1. Open: $hdcnPath\.env" -ForegroundColor Cyan
Write-Host "2. Find: GITGUARDIAN_API_KEY=..." -ForegroundColor Cyan
Write-Host "3. Copy the value" -ForegroundColor Cyan
Write-Host ""
Write-Host "Option B: From GitGuardian Dashboard" -ForegroundColor White
Write-Host "1. Go to: https://dashboard.gitguardian.com/" -ForegroundColor Cyan
Write-Host "2. Login with your account" -ForegroundColor Cyan
Write-Host "3. Go to: API > Personal Access Tokens" -ForegroundColor Cyan
Write-Host "4. Copy your existing token (or create a new one)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Then set it in myAdmin:" -ForegroundColor White
Write-Host ""
Write-Host "# For current session:" -ForegroundColor Green
Write-Host "`$env:GITGUARDIAN_API_KEY = 'your-api-key-here'" -ForegroundColor Cyan
Write-Host ""
Write-Host "# Make it persistent:" -ForegroundColor Green
Write-Host "[System.Environment]::SetEnvironmentVariable('GITGUARDIAN_API_KEY', 'your-key', 'User')" -ForegroundColor Cyan
Write-Host ""
Write-Host "# Verify it works:" -ForegroundColor Green
Write-Host "ggshield secret scan repo . --exit-zero" -ForegroundColor Cyan
Write-Host ""

exit 0
