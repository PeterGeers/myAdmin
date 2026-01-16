# myAdmin Startup Script
# Usage: .\start.ps1 [mode] [options]
# Modes: dev, prod, containers, restart, stop, status
# Options: --build (rebuild containers), --lean (close resource hogs)

param(
    [string]$Mode = "dev",
    [switch]$Build,
    [switch]$Lean
)

$rootDir = $PSScriptRoot

# Close resource-heavy apps if --lean flag is used
if ($Lean) {
    Write-Host "Closing resource-heavy applications..." -ForegroundColor Yellow
    $processesToClose = @("Copilot", "Spotify", "ChatGPT", "OneDrive")
    foreach ($proc in $processesToClose) {
        try {
            Stop-Process -Name $proc -Force -ErrorAction SilentlyContinue
            Write-Host "Closed $proc" -ForegroundColor Green
        }
        catch {
            Write-Host "$proc not running" -ForegroundColor Gray
        }
    }
    Start-Sleep -Seconds 2
}

switch ($Mode.ToLower()) {
    "dev" {
        Write-Host "Starting myAdmin Development Mode..." -ForegroundColor Green
        Write-Host "Backend and Database: Docker containers (auto-start)" -ForegroundColor Cyan
        Write-Host "Starting frontend development server..." -ForegroundColor Yellow
        
        # Sync backend/.env to root and frontend
        if (Test-Path "backend\.env") {
            Copy-Item "backend\.env" ".env" -Force
            Copy-Item "backend\.env" "frontend\.env" -Force
            Write-Host "Synced backend/.env to root and frontend" -ForegroundColor Green
        }
        else {
            Write-Host "backend/.env not found!" -ForegroundColor Red
            exit 1
        }
        
        # Check if containers exist and their status
        $existingContainers = docker-compose ps -q
        if (-not $existingContainers) {
            Write-Host "Containers not found!" -ForegroundColor Red
            Write-Host "" -ForegroundColor White
            Write-Host "Manual action required:" -ForegroundColor Yellow
            Write-Host "1. First time setup: Run '.\start.ps1 containers' to create containers" -ForegroundColor White
            Write-Host "2. Restore from backup: Use your database migration scripts" -ForegroundColor White
            Write-Host "3. Check Docker Desktop: Ensure Docker is running" -ForegroundColor White
            Write-Host "" -ForegroundColor White
            Write-Host "Then run '.\start.ps1 dev' again" -ForegroundColor Cyan
            exit 1
        }
        
        # Check if containers are running
        $runningContainers = docker-compose ps --filter "status=running" -q
        if ($runningContainers) {
            Write-Host "Containers already running" -ForegroundColor Green
        }
        else {
            Write-Host "Starting containers..." -ForegroundColor Yellow
            docker-compose up -d
        }
        Start-Sleep -Seconds 2
        
        # Start frontend dev server
        Start-Process PowerShell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\frontend'; npm start"
        
        Write-Host "Development environment ready!" -ForegroundColor Green
        Write-Host "Backend API: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "Frontend Dev: http://localhost:3000" -ForegroundColor Cyan
        Write-Host "Database: localhost:3306 (Docker)" -ForegroundColor Cyan
        Write-Host "" -ForegroundColor White
        Write-Host "Note: Frontend dev server will open automatically" -ForegroundColor Gray
    }
    "prod" {
        Write-Host "Building for Production..." -ForegroundColor Green
        
        # Sync backend/.env to root and frontend
        if (Test-Path "backend\.env") {
            Copy-Item "backend\.env" ".env" -Force
            Copy-Item "backend\.env" "frontend\.env" -Force
            Write-Host "Synced backend/.env to root and frontend" -ForegroundColor Green
        }
        else {
            Write-Host "backend/.env not found!" -ForegroundColor Red
            exit 1
        }
        
        # Check if containers exist and their status
        $existingContainers = docker-compose ps -q
        if (-not $existingContainers) {
            Write-Host "Containers not found!" -ForegroundColor Red
            Write-Host "" -ForegroundColor White
            Write-Host "Manual action required:" -ForegroundColor Yellow
            Write-Host "1. First time setup: Run '.\start.ps1 containers' to create containers" -ForegroundColor White
            Write-Host "2. Restore from backup: Use your database migration scripts" -ForegroundColor White
            Write-Host "3. Check Docker Desktop: Ensure Docker is running" -ForegroundColor White
            Write-Host "" -ForegroundColor White
            Write-Host "Then run '.\start.ps1 prod' again" -ForegroundColor Cyan
            exit 1
        }
        
        # Check if containers are running
        $runningContainers = docker-compose ps --filter "status=running" -q
        if ($runningContainers) {
            Write-Host "Containers already running" -ForegroundColor Green
        }
        else {
            Write-Host "Starting containers..." -ForegroundColor Yellow
            docker-compose up -d
        }
        
        # Build frontend
        Set-Location "$rootDir\frontend"
        Write-Host "Building React frontend..." -ForegroundColor Yellow
        $buildStart = Get-Date
        npm run build
        $buildEnd = Get-Date
        $buildTime = ($buildEnd - $buildStart).TotalSeconds
        Write-Host "Build completed in $([math]::Round($buildTime, 1)) seconds" -ForegroundColor Cyan
        
        # Restart backend to pick up new build
        Set-Location $rootDir
        Write-Host "Restarting backend for new build..." -ForegroundColor Yellow
        docker-compose restart backend
        
        Write-Host "Production build complete!" -ForegroundColor Green
        Write-Host "Production server: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "(Backend serves built React app)" -ForegroundColor Gray
    }
    "restart" {
        Write-Host "Restarting Docker containers..." -ForegroundColor Yellow
        
        # Check if containers exist
        $existingContainers = docker-compose ps -q
        if (-not $existingContainers) {
            Write-Host "No containers found to restart!" -ForegroundColor Red
            Write-Host "Run '.\start.ps1 containers' first to create containers" -ForegroundColor Cyan
            exit 1
        }
        
        # Restart containers
        docker-compose restart
        
        # Wait a moment for health checks
        Start-Sleep -Seconds 5
        
        # Check status
        Write-Host "Checking container health..." -ForegroundColor Yellow
        docker-compose ps
        
        Write-Host "Containers restarted!" -ForegroundColor Green
        Write-Host "Backend: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "Database: localhost:3306" -ForegroundColor Cyan
    }
    "stop" {
        Write-Host "Stopping Docker containers..." -ForegroundColor Yellow
        
        # Stop containers but keep them for restart
        docker-compose stop
        
        Write-Host "Containers stopped!" -ForegroundColor Green
        Write-Host "Use '.\start.ps1 containers' or '.\start.ps1 restart' to start again" -ForegroundColor Cyan
    }
    "status" {
        Write-Host "Docker Container Status:" -ForegroundColor Yellow
        Write-Host "" -ForegroundColor White
        
        # Show container status
        docker-compose ps
        
        Write-Host "" -ForegroundColor White
        Write-Host "Service Health Check:" -ForegroundColor Yellow
        
        # Test backend API
        try {
            $null = Invoke-RestMethod -Uri "http://localhost:5000/api/health" -TimeoutSec 5
            Write-Host "✅ Backend API: Healthy" -ForegroundColor Green
        }
        catch {
            Write-Host "❌ Backend API: Not responding" -ForegroundColor Red
        }
        
        # Test database connection
        try {
            $dbTest = docker exec myadmin-mysql-1 mysql -u peter -pPeterGeers1953 -e "SELECT 1" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ Database: Connected" -ForegroundColor Green
            }
            else {
                Write-Host "❌ Database: Connection failed" -ForegroundColor Red
            }
        }
        catch {
            Write-Host "❌ Database: Not accessible" -ForegroundColor Red
        }
        
        Write-Host "" -ForegroundColor White
        Write-Host "Access URLs:" -ForegroundColor Yellow
        Write-Host "Backend API: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "Database: localhost:3306" -ForegroundColor Cyan
    }
    "containers" {
        Write-Host "Managing Docker containers..." -ForegroundColor Green
        
        # Always sync backend/.env to root .env for Docker
        if (Test-Path "backend\.env") {
            Copy-Item "backend\.env" ".env" -Force
            (Get-Content ".env") -replace "DB_HOST=localhost", "DB_HOST=mysql" | Set-Content ".env"
            Write-Host "Synced backend/.env to root .env" -ForegroundColor Green
        }
        else {
            Write-Host "backend/.env not found!" -ForegroundColor Red
            exit 1
        }
        
        if ($Build) {
            Write-Host "Rebuilding containers..." -ForegroundColor Yellow
            docker-compose up --build -d
        }
        else {
            Write-Host "Starting containers..." -ForegroundColor Yellow
            docker-compose up -d
        }
        
        Write-Host "Containers running!" -ForegroundColor Green
        Write-Host "Backend: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "Database: localhost:3306" -ForegroundColor Cyan
    }
    default {
        Write-Host "myAdmin Startup Options:" -ForegroundColor Yellow
        Write-Host "  .\start.ps1 dev        - Development (containers + frontend dev server)" -ForegroundColor White
        Write-Host "  .\start.ps1 prod       - Production build (containers + built frontend)" -ForegroundColor White
        Write-Host "  .\start.ps1 containers - Manage containers only" -ForegroundColor White
        Write-Host "  .\start.ps1 restart    - Restart Docker containers" -ForegroundColor White
        Write-Host "  .\start.ps1 stop       - Stop Docker containers" -ForegroundColor White
        Write-Host "  .\start.ps1 status     - Check container and service status" -ForegroundColor White
        Write-Host "" -ForegroundColor White
        Write-Host "Options:" -ForegroundColor Yellow
        Write-Host "  --build               - Rebuild Docker containers" -ForegroundColor White
        Write-Host "  --lean                - Close resource-heavy apps first" -ForegroundColor White
        Write-Host "" -ForegroundColor White
        Write-Host "Quick Commands:" -ForegroundColor Yellow
        Write-Host "  .\start.ps1 restart   - Restart containers (most common)" -ForegroundColor Cyan
        Write-Host "  .\start.ps1 status    - Check if everything is working" -ForegroundColor Cyan
    }
}