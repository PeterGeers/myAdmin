# Quick Container Restart Script for myAdmin
# Usage: .\restart-containers.ps1 [options]
# Options: --build (rebuild containers), --status (show status after restart)

param(
    [switch]$Build,
    [switch]$Status
)

$rootDir = $PSScriptRoot

Write-Host "🔄 myAdmin Container Restart" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

# Check if Docker is running
try {
    docker version | Out-Null
}
catch {
    Write-Host "❌ Docker is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}

# Check if containers exist
Write-Host "Checking for existing containers..." -ForegroundColor Yellow
$existingContainers = docker-compose ps -q 2>$null
if (-not $existingContainers) {
    Write-Host "❌ No containers found!" -ForegroundColor Red
    Write-Host "" -ForegroundColor White
    Write-Host "Available options:" -ForegroundColor Yellow
    Write-Host "1. Create containers: .\start.ps1 containers" -ForegroundColor White
    Write-Host "2. Start development: .\start.ps1 dev" -ForegroundColor White
    Write-Host "3. Check Docker Desktop for existing containers" -ForegroundColor White
    exit 1
}

# Show current status
Write-Host "Current container status:" -ForegroundColor Yellow
docker-compose ps

if ($Build) {
    Write-Host "" -ForegroundColor White
    Write-Host "🔨 Rebuilding and restarting containers..." -ForegroundColor Yellow
    
    # Stop containers first
    docker-compose down
    
    # Rebuild and start
    docker-compose up -d --build
    
    Write-Host "✅ Containers rebuilt and restarted!" -ForegroundColor Green
}
else {
    Write-Host "" -ForegroundColor White
    Write-Host "🔄 Restarting containers..." -ForegroundColor Yellow
    
    # Simple restart
    docker-compose restart
    
    Write-Host "✅ Containers restarted!" -ForegroundColor Green
}

# Wait for services to be ready
Write-Host "" -ForegroundColor White
Write-Host "⏳ Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 8

# Health check
Write-Host "🏥 Checking service health..." -ForegroundColor Yellow

# Test backend API
$backendHealthy = $false
try {
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/health" -TimeoutSec 10
    Write-Host "✅ Backend API: Healthy" -ForegroundColor Green
    $backendHealthy = $true
}
catch {
    Write-Host "❌ Backend API: Not responding (may need more time)" -ForegroundColor Red
}

# Test database
$databaseHealthy = $false
try {
    $dbTest = docker exec myadmin-mysql-1 mysql -u peter -pPeterGeers1953 -e "SELECT 1" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Database: Connected" -ForegroundColor Green
        $databaseHealthy = $true
    }
    else {
        Write-Host "❌ Database: Connection failed" -ForegroundColor Red
    }
}
catch {
    Write-Host "❌ Database: Not accessible" -ForegroundColor Red
}

# Show final status if requested or if there are issues
if ($Status -or -not ($backendHealthy -and $databaseHealthy)) {
    Write-Host "" -ForegroundColor White
    Write-Host "📊 Final Container Status:" -ForegroundColor Yellow
    docker-compose ps
}

# Summary
Write-Host "" -ForegroundColor White
Write-Host "🎯 Restart Summary:" -ForegroundColor Cyan
if ($backendHealthy -and $databaseHealthy) {
    Write-Host "✅ All services are healthy and ready!" -ForegroundColor Green
}
else {
    Write-Host "⚠️  Some services may need more time to start" -ForegroundColor Yellow
    Write-Host "   Try accessing the services in a few moments" -ForegroundColor Gray
}

Write-Host "" -ForegroundColor White
Write-Host "🌐 Access URLs:" -ForegroundColor Cyan
Write-Host "   Backend API: http://localhost:5000" -ForegroundColor White
Write-Host "   Database: localhost:3306" -ForegroundColor White
Write-Host "   Frontend Dev: http://localhost:3000 (if running)" -ForegroundColor Gray

Write-Host "" -ForegroundColor White
Write-Host "💡 Quick Commands:" -ForegroundColor Yellow
Write-Host "   .\start.ps1 dev     - Start development environment" -ForegroundColor White
Write-Host "   .\start.ps1 status  - Check detailed status" -ForegroundColor White
Write-Host "   .\restart-containers.ps1 --build  - Rebuild containers" -ForegroundColor White