# Sync Environment Files
# This script helps maintain consistency across .env files

param(
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          Environment Files Sync Utility                    ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Get repository root
$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    $repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

$sharedEnv = Join-Path $repoRoot ".env.shared"
$rootEnv = Join-Path $repoRoot ".env"
$backendEnv = Join-Path $repoRoot "backend\.env"
$frontendEnv = Join-Path $repoRoot "frontend\.env"

# Check if .env.shared exists
if (-not (Test-Path $sharedEnv)) {
    Write-Host "✗ .env.shared not found" -ForegroundColor Red
    Write-Host "  This file contains shared configuration" -ForegroundColor Yellow
    Write-Host "  Run this script to create it from existing .env files" -ForegroundColor Yellow
    exit 1
}

Write-Host "Environment Files Status:" -ForegroundColor White
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

# Function to check if file exists and show status
function Show-FileStatus {
    param($path, $name)
    
    if (Test-Path $path) {
        $lines = (Get-Content $path).Count
        Write-Host "  ✓ $name" -ForegroundColor Green -NoNewline
        Write-Host " ($lines lines)" -ForegroundColor Gray
        return $true
    }
    else {
        Write-Host "  ✗ $name" -ForegroundColor Red -NoNewline
        Write-Host " (missing)" -ForegroundColor Gray
        return $false
    }
}

$sharedExists = Show-FileStatus $sharedEnv ".env.shared"
$rootExists = Show-FileStatus $rootEnv ".env (root)"
$backendExists = Show-FileStatus $backendEnv "backend/.env"
$frontendExists = Show-FileStatus $frontendEnv "frontend/.env"

Write-Host ""

if (-not ($rootExists -and $backendExists -and $frontendExists)) {
    Write-Host "⚠ Some .env files are missing" -ForegroundColor Yellow
    Write-Host "  Please create them manually or restore from backup" -ForegroundColor Yellow
    exit 1
}

# Show differences
Write-Host "Key Differences:" -ForegroundColor White
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

# Check DB_HOST
$rootDbHost = (Get-Content $rootEnv | Select-String "^DB_HOST=").ToString() -replace "DB_HOST=", ""
$backendDbHost = (Get-Content $backendEnv | Select-String "^DB_HOST=").ToString() -replace "DB_HOST=", ""
$frontendDbHost = (Get-Content $frontendEnv | Select-String "^DB_HOST=").ToString() -replace "DB_HOST=", ""

Write-Host "  DB_HOST:" -ForegroundColor Cyan
Write-Host "    Root:     $rootDbHost" -ForegroundColor White -NoNewline
if ($rootDbHost -eq "mysql") {
    Write-Host " ✓ (Docker)" -ForegroundColor Green
}
else {
    Write-Host " ⚠ (Expected: mysql)" -ForegroundColor Yellow
}

Write-Host "    Backend:  $backendDbHost" -ForegroundColor White -NoNewline
if ($backendDbHost -eq "localhost") {
    Write-Host " ✓ (Local)" -ForegroundColor Green
}
else {
    Write-Host " ⚠ (Expected: localhost)" -ForegroundColor Yellow
}

Write-Host "    Frontend: $frontendDbHost" -ForegroundColor White -NoNewline
if ($frontendDbHost -eq "localhost") {
    Write-Host " ✓ (Local)" -ForegroundColor Green
}
else {
    Write-Host " ⚠ (Expected: localhost)" -ForegroundColor Yellow
}

Write-Host ""

# Check SNS (backend only)
$backendSns = Get-Content $backendEnv | Select-String "^SNS_TOPIC_ARN="
$frontendSns = Get-Content $frontendEnv | Select-String "^SNS_TOPIC_ARN="

Write-Host "  SNS_TOPIC_ARN:" -ForegroundColor Cyan
if ($backendSns) {
    Write-Host "    Backend:  Present ✓" -ForegroundColor Green
}
else {
    Write-Host "    Backend:  Missing ✗" -ForegroundColor Red
}

if ($frontendSns) {
    Write-Host "    Frontend: Present ⚠ (not needed)" -ForegroundColor Yellow
}
else {
    Write-Host "    Frontend: Not present ✓" -ForegroundColor Green
}

Write-Host ""

# Summary
Write-Host "Summary:" -ForegroundColor White
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""
Write-Host "  • .env.shared:   Shared configuration (reference)" -ForegroundColor Cyan
Write-Host "  • .env (root):   Docker Compose (DB_HOST=mysql)" -ForegroundColor Cyan
Write-Host "  • backend/.env:  Python/Flask (DB_HOST=localhost + SNS)" -ForegroundColor Cyan
Write-Host "  • frontend/.env: React (DB_HOST=localhost)" -ForegroundColor Cyan
Write-Host ""

Write-Host "Recommendations:" -ForegroundColor White
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""
Write-Host "  1. Keep .env.shared as reference for common values" -ForegroundColor White
Write-Host "  2. Update secrets in all three .env files when changed" -ForegroundColor White
Write-Host "  3. Use this script to verify consistency" -ForegroundColor White
Write-Host ""

# Check for common secrets consistency
Write-Host "Checking Secret Consistency:" -ForegroundColor White
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host ""

$secretKeys = @(
    "COGNITO_USER_POOL_ID",
    "COGNITO_CLIENT_ID",
    "COGNITO_CLIENT_SECRET",
    "AWS_REGION",
    "DB_USER",
    "DB_PASSWORD",
    "OPENROUTER_API_KEY"
)

$allConsistent = $true

foreach ($key in $secretKeys) {
    $rootValue = (Get-Content $rootEnv | Select-String "^$key=").ToString() -replace "$key=", ""
    $backendValue = (Get-Content $backendEnv | Select-String "^$key=").ToString() -replace "$key=", ""
    $frontendValue = (Get-Content $frontendEnv | Select-String "^$key=").ToString() -replace "$key=", ""
    
    if ($rootValue -eq $backendValue -and $backendValue -eq $frontendValue) {
        Write-Host "  ✓ $key" -ForegroundColor Green -NoNewline
        Write-Host " (consistent)" -ForegroundColor Gray
    }
    else {
        Write-Host "  ✗ $key" -ForegroundColor Red -NoNewline
        Write-Host " (INCONSISTENT!)" -ForegroundColor Red
        $allConsistent = $false
    }
}

Write-Host ""

if ($allConsistent) {
    Write-Host "✓ All secrets are consistent across environments!" -ForegroundColor Green
}
else {
    Write-Host "⚠ Some secrets are inconsistent!" -ForegroundColor Yellow
    Write-Host "  Please update them manually to match" -ForegroundColor Yellow
}

Write-Host ""

exit 0
