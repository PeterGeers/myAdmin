#!/usr/bin/env pwsh
# Safe Docker Restart Script - NEVER uses -v flag

Write-Host "🔄 Safe Docker Restart (preserves data)" -ForegroundColor Green
Write-Host "⚠️  This script NEVER deletes volumes or data" -ForegroundColor Yellow

# Create backup first
Write-Host "1. Creating backup before restart..." -ForegroundColor Cyan
& .\backup-database.ps1

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Backup failed - aborting restart for safety" -ForegroundColor Red
    exit 1
}

# Stop containers (WITHOUT -v flag)
Write-Host "2. Stopping containers (keeping data)..." -ForegroundColor Cyan
docker-compose down

# Start containers
Write-Host "3. Starting containers..." -ForegroundColor Cyan
docker-compose up -d

# Wait and test
Write-Host "4. Waiting for services to start..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

# Test database connection
Write-Host "5. Testing database connection..." -ForegroundColor Cyan
$testResult = docker exec myadmin-mysql-1 mysql -u peter -pPeterGeers1953 finance -e "SELECT COUNT(*) FROM vw_mutaties LIMIT 1;" 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Database is working - data preserved!" -ForegroundColor Green
}
else {
    Write-Host "❌ Database test failed - check logs" -ForegroundColor Red
}

Write-Host "🎉 Safe restart completed" -ForegroundColor Green