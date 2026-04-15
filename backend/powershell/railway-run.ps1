# ============================================================================
# Run Python scripts against Railway MySQL
# ============================================================================
# Executes any Python script with env vars pointing at Railway MySQL.
# Perfect for migrations, data fixes, or ad-hoc testing scripts.
#
# Usage:
#   .\powershell\railway-run.ps1 -Script "scripts/database/fix_database_views.py"
#   .\powershell\railway-run.ps1 -Script "src/app.py"           # Run backend locally against Railway DB
#   .\powershell\railway-run.ps1 -TestDb -Script "my_script.py" # Against testfinance
# ============================================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$Script,
    [switch]$TestDb
)

$RAILWAY_MYSQL_HOST = "shinkansen.proxy.rlwy.net"
$RAILWAY_MYSQL_PORT = 42375
$RAILWAY_MYSQL_USER = "root"
$DB_NAME = if ($TestDb) { "testfinance" } else { "finance" }

if (-not (Test-Path $Script)) {
    Write-Host "ERROR: Script not found: $Script" -ForegroundColor Red
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Run Python against Railway MySQL" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Host:     $RAILWAY_MYSQL_HOST`:$RAILWAY_MYSQL_PORT" -ForegroundColor Yellow
Write-Host "Database: $DB_NAME" -ForegroundColor Yellow
Write-Host "Script:   $Script" -ForegroundColor Yellow
Write-Host ""

$securePassword = Read-Host "Railway MySQL Password" -AsSecureString
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))

# Override DB env vars to point at Railway
$env:DB_HOST = $RAILWAY_MYSQL_HOST
$env:DB_PORT = $RAILWAY_MYSQL_PORT
$env:DB_USER = $RAILWAY_MYSQL_USER
$env:DB_PASSWORD = $password
$env:DB_NAME = $DB_NAME
$env:TEST_MODE = if ($TestDb) { "true" } else { "false" }
$env:TEST_DB_NAME = "testfinance"

Write-Host "Executing..." -ForegroundColor Green
Write-Host ""

# Activate venv if available
$venvActivate = "$PSScriptRoot\..\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

python $Script

# Clean up env vars (restore to local defaults)
$env:DB_HOST = "localhost"
$env:DB_PORT = "3306"
$env:TEST_MODE = "false"
Remove-Variable -Name password -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. DB env vars restored to localhost." -ForegroundColor Green
