#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create testfinance database as a copy of finance database

.DESCRIPTION
    This script creates a test database by copying the structure and data
    from the finance database. This allows integration tests to run without
    affecting production data.

.PARAMETER DBHost
    Database host (default: localhost)

.PARAMETER DBUser
    Database user (default: root)

.PARAMETER DBPassword
    Database password (will prompt if not provided)

.EXAMPLE
    .\create_testfinance_db.ps1
    
.EXAMPLE
    .\create_testfinance_db.ps1 -DBHost localhost -DBUser root
#>

param(
    [string]$DBHost = "localhost",
    [string]$DBUser = "root",
    [string]$DBPassword = ""
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Create testfinance Database" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Load environment variables from .env file
if (Test-Path ".env") {
    Write-Host "Loading environment variables from .env..." -ForegroundColor Yellow
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($key -eq "DB_HOST") { $DBHost = $value }
            if ($key -eq "DB_USER") { $DBUser = $value }
            if ($key -eq "DB_PASSWORD") { $DBPassword = $value }
        }
    }
}

# Prompt for password if not provided
if ([string]::IsNullOrEmpty($DBPassword)) {
    $securePassword = Read-Host "Enter MySQL password for user '$DBUser'" -AsSecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $DBPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
}

Write-Host ""
Write-Host "Database Configuration:" -ForegroundColor Green
Write-Host "  Host: $DBHost" -ForegroundColor White
Write-Host "  User: $DBUser" -ForegroundColor White
Write-Host "  Source DB: finance" -ForegroundColor White
Write-Host "  Target DB: testfinance" -ForegroundColor White
Write-Host ""

# Check if mysql command is available
$mysqlCmd = Get-Command mysql -ErrorAction SilentlyContinue
if (-not $mysqlCmd) {
    Write-Host "❌ Error: mysql command not found in PATH" -ForegroundColor Red
    Write-Host "Please install MySQL client or add it to your PATH" -ForegroundColor Yellow
    exit 1
}

Write-Host "Step 1: Creating testfinance database..." -ForegroundColor Cyan
$createDbSql = "CREATE DATABASE IF NOT EXISTS testfinance;"
$createDbSql | mysql -h $DBHost -u $DBUser -p"$DBPassword" 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Failed to create testfinance database" -ForegroundColor Red
    exit 1
}
Write-Host "✅ testfinance database created" -ForegroundColor Green

Write-Host ""
Write-Host "Step 2: Copying database structure and data..." -ForegroundColor Cyan
Write-Host "This may take a few minutes depending on database size..." -ForegroundColor Yellow

# Use mysqldump to export finance database
$dumpFile = "finance_temp_dump.sql"
Write-Host "  Exporting finance database..." -ForegroundColor White

mysqldump -h $DBHost -u $DBUser -p"$DBPassword" --databases finance --add-drop-table --routines --triggers > $dumpFile 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Failed to export finance database" -ForegroundColor Red
    if (Test-Path $dumpFile) { Remove-Item $dumpFile }
    exit 1
}

# Replace database name in dump file
Write-Host "  Modifying dump file for testfinance..." -ForegroundColor White
$content = Get-Content $dumpFile -Raw
$content = $content -replace "CREATE DATABASE.*finance", "CREATE DATABASE IF NOT EXISTS testfinance"
$content = $content -replace "USE `finance`", "USE `testfinance`"
$content | Set-Content $dumpFile

# Import into testfinance
Write-Host "  Importing into testfinance database..." -ForegroundColor White
Get-Content $dumpFile | mysql -h $DBHost -u $DBUser -p"$DBPassword" 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error: Failed to import into testfinance database" -ForegroundColor Red
    if (Test-Path $dumpFile) { Remove-Item $dumpFile }
    exit 1
}

# Clean up dump file
Remove-Item $dumpFile
Write-Host "✅ Database structure and data copied" -ForegroundColor Green

Write-Host ""
Write-Host "Step 3: Verifying the copy..." -ForegroundColor Cyan

# Get table counts
$verifyQuery = @"
SELECT 
    'finance' as database_name,
    COUNT(*) as table_count 
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'finance' 
AND TABLE_TYPE = 'BASE TABLE'
UNION ALL
SELECT 
    'testfinance' as database_name,
    COUNT(*) as table_count 
FROM information_schema.TABLES 
WHERE TABLE_SCHEMA = 'testfinance' 
AND TABLE_TYPE = 'BASE TABLE';
"@

Write-Host ""
$verifyQuery | mysql -h $DBHost -u $DBUser -p"$DBPassword" -t

# Get record counts for mutaties table
$recordQuery = @"
SELECT 
    'finance' as db,
    COUNT(*) as record_count 
FROM finance.mutaties
UNION ALL
SELECT 
    'testfinance' as db,
    COUNT(*) as record_count 
FROM testfinance.mutaties;
"@

Write-Host ""
Write-Host "Sample record counts (mutaties table):" -ForegroundColor White
$recordQuery | mysql -h $DBHost -u $DBUser -p"$DBPassword" -t

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "✅ testfinance database created successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "You can now run integration tests with:" -ForegroundColor Yellow
Write-Host "  python -m pytest tests/integration/test_multitenant_phase5.py -v" -ForegroundColor White
Write-Host ""
