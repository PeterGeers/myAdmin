# myAdmin Startup Script
# Usage: .\start.ps1 [mode] [options]
# Modes: dev, prod, containers
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
        } catch {
            Write-Host "$proc not running" -ForegroundColor Gray
        }
    }
    Start-Sleep -Seconds 2
}

switch ($Mode.ToLower()) {
    "dev" {
        Write-Host "Starting myAdmin Development Mode..." -ForegroundColor Green
        Write-Host "📦 Backend & Database: Docker containers (auto-start)" -ForegroundColor Cyan
        Write-Host "🚀 Starting frontend development server..." -ForegroundColor Yellow
        
        # Check if containers exist and their status
        $existingContainers = docker-compose ps -q
        if (-not $existingContainers) {
            Write-Host "❌ Containers not found!" -ForegroundColor Red
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
            Write-Host "📦 Containers already running" -ForegroundColor Green
        } else {
            Write-Host "📦 Starting containers..." -ForegroundColor Yellow
            docker-compose up -d
        }
        Start-Sleep -Seconds 2
        
        # Start frontend dev server
        Start-Process PowerShell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\frontend'; npm start"
        
        Write-Host "✅ Development environment ready!" -ForegroundColor Green
        Write-Host "Backend API: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "Frontend Dev: http://localhost:3000" -ForegroundColor Cyan
        Write-Host "Database: localhost:3306 (Docker)" -ForegroundColor Cyan
    }
    "prod" {
        Write-Host "Building for Production..." -ForegroundColor Green
        
        # Check if containers exist and their status
        $existingContainers = docker-compose ps -q
        if (-not $existingContainers) {
            Write-Host "❌ Containers not found!" -ForegroundColor Red
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
            Write-Host "📦 Containers already running" -ForegroundColor Green
        } else {
            Write-Host "📦 Starting containers..." -ForegroundColor Yellow
            docker-compose up -d
        }
        
        # Build frontend
        Set-Location "$rootDir\frontend"
        Write-Host "🏗️ Building React frontend..." -ForegroundColor Yellow
        npm run build
        
        Write-Host "✅ Production build complete!" -ForegroundColor Green
        Write-Host "Production server: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "(Backend serves built React app)" -ForegroundColor Gray
    }
    "containers" {
        Write-Host "Managing Docker containers..." -ForegroundColor Green
        
        # Always sync backend/.env to root .env for Docker
        if (Test-Path "backend\.env") {
            Copy-Item "backend\.env" ".env" -Force
            (Get-Content ".env") -replace "DB_HOST=localhost", "DB_HOST=mysql" | Set-Content ".env"
            Write-Host "✅ Synced backend/.env to root .env" -ForegroundColor Green
        } else {
            Write-Host "❌ backend/.env not found!" -ForegroundColor Red
            exit 1
        }
        
        if ($Build) {
            Write-Host "🔨 Rebuilding containers..." -ForegroundColor Yellow
            docker-compose up --build -d
        } else {
            Write-Host "🚀 Starting containers..." -ForegroundColor Yellow
            docker-compose up -d
        }
        
        Write-Host "✅ Containers running!" -ForegroundColor Green
        Write-Host "Backend: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "Database: localhost:3306" -ForegroundColor Cyan
    }
    default {
        Write-Host "myAdmin Startup Options:" -ForegroundColor Yellow
        Write-Host "  .\start.ps1 dev        - Development (containers + frontend dev server)" -ForegroundColor White
        Write-Host "  .\start.ps1 prod       - Production build (containers + built frontend)" -ForegroundColor White
        Write-Host "  .\start.ps1 containers - Manage containers only" -ForegroundColor White
        Write-Host "" -ForegroundColor White
        Write-Host "Options:" -ForegroundColor Yellow
        Write-Host "  --build               - Rebuild Docker containers" -ForegroundColor White
        Write-Host "  --lean                - Close resource-heavy apps first" -ForegroundColor White
    }
}