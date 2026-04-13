# ============================================================================
# Run SQL queries against Railway MySQL
# ============================================================================
# Execute SQL queries or .sql files directly against Railway MySQL.
#
# Usage:
#   .\powershell\railway-sql.ps1 -Query "SELECT COUNT(*) FROM mutaties"
#   .\powershell\railway-sql.ps1 -File "scripts/database/fix_database_views.py"
#   .\powershell\railway-sql.ps1 -File "sql/my_migration.sql"
#   .\powershell\railway-sql.ps1 -TestDb -Query "SELECT * FROM mutaties LIMIT 5"
# ============================================================================

param(
    [string]$Query,
    [string]$File,
    [switch]$TestDb
)

$RAILWAY_MYSQL_HOST = "shinkansen.proxy.rlwy.net"
$RAILWAY_MYSQL_PORT = 42375
$RAILWAY_MYSQL_USER = "peter"
$DB_NAME = if ($TestDb) { "testfinance" } else { "finance" }

if (-not $Query -and -not $File) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host '  .\powershell\railway-sql.ps1 -Query "SELECT COUNT(*) FROM mutaties"' -ForegroundColor Gray
    Write-Host '  .\powershell\railway-sql.ps1 -File "sql/migration.sql"' -ForegroundColor Gray
    Write-Host '  .\powershell\railway-sql.ps1 -TestDb -Query "SHOW TABLES"' -ForegroundColor Gray
    exit 1
}

# Check mysql client
$mysqlPath = Get-Command mysql -ErrorAction SilentlyContinue
if (-not $mysqlPath) {
    Write-Host "ERROR: mysql CLI not found. Install via: winget install Oracle.MySQL" -ForegroundColor Red
    exit 1
}

Write-Host "Railway MySQL: $RAILWAY_MYSQL_HOST`:$RAILWAY_MYSQL_PORT / $DB_NAME" -ForegroundColor Cyan

$securePassword = Read-Host "Password" -AsSecureString
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))

if ($File) {
    if (-not (Test-Path $File)) {
        Write-Host "ERROR: File not found: $File" -ForegroundColor Red
        exit 1
    }
    Write-Host "Executing file: $File" -ForegroundColor Yellow
    mysql -h $RAILWAY_MYSQL_HOST -P $RAILWAY_MYSQL_PORT -u $RAILWAY_MYSQL_USER -p"$password" $DB_NAME < $File
}
else {
    Write-Host "Executing: $Query" -ForegroundColor Yellow
    mysql -h $RAILWAY_MYSQL_HOST -P $RAILWAY_MYSQL_PORT -u $RAILWAY_MYSQL_USER -p"$password" $DB_NAME -e "$Query"
}
