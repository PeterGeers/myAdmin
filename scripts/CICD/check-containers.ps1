# Container Health Check and Diagnostics
# This script checks container health and provides detailed diagnostics

param(
    [switch]$Fix = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Continue"

# Get the root directory and ensure we're there
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $RootDir

function Write-Status {
    param($Message, $Status = "INFO")
    $color = switch ($Status) {
        "OK" { "Green" }
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "INFO" { "Cyan" }
        default { "White" }
    }
    Write-Host $Message -ForegroundColor $color
}

Write-Status "=== Container Health Check ===" "INFO"
Write-Status ""

# Check if Docker is running
Write-Status "Checking Docker daemon..." "INFO"
try {
    docker info | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Status "✓ Docker daemon is running" "OK"
    }
    else {
        Write-Status "✗ Docker daemon is not responding" "ERROR"
        Write-Status "  Solution: Start Docker Desktop" "WARN"
        exit 1
    }
}
catch {
    Write-Status "✗ Docker is not installed or not running" "ERROR"
    Write-Status "  Solution: Install Docker Desktop and start it" "WARN"
    exit 1
}

Write-Status ""

# Check docker-compose file
Write-Status "Checking docker-compose.yml..." "INFO"
if (Test-Path "docker-compose.yml") {
    Write-Status "✓ docker-compose.yml found" "OK"
}
else {
    Write-Status "✗ docker-compose.yml not found" "ERROR"
    exit 1
}

Write-Status ""

# Get container status
Write-Status "Checking container status..." "INFO"
$containers = docker-compose ps --format json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Status "✗ Failed to get container status" "ERROR"
    Write-Status "  Error: $containers" "ERROR"
    
    if ($Fix) {
        Write-Status ""
        Write-Status "Attempting to fix by recreating containers..." "WARN"
        docker-compose down
        docker-compose up -d
        Start-Sleep -Seconds 10
        $containers = docker-compose ps --format json
    }
    else {
        Write-Status "  Run with -Fix flag to attempt automatic repair" "INFO"
        exit 1
    }
}

$containerList = $containers | ConvertFrom-Json
$allHealthy = $true
$issues = @()

Write-Status ""
Write-Status "Container Status:" "INFO"
Write-Status "─────────────────────────────────────────────────" "INFO"

foreach ($container in $containerList) {
    $serviceName = $container.Service
    $state = $container.State
    $status = $container.Status
    
    if ($state -eq "running") {
        Write-Status "✓ $serviceName : RUNNING ($status)" "OK"
        
        # Additional health checks for specific services
        if ($serviceName -eq "backend") {
            Start-Sleep -Seconds 2
            try {
                $healthCheck = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
                if ($healthCheck.StatusCode -eq 200) {
                    Write-Status "  └─ Health endpoint: OK" "OK"
                }
                else {
                    Write-Status "  └─ Health endpoint: FAILED (Status: $($healthCheck.StatusCode))" "ERROR"
                    $allHealthy = $false
                    $issues += "Backend health check failed"
                }
            }
            catch {
                Write-Status "  └─ Health endpoint: NOT RESPONDING" "ERROR"
                $allHealthy = $false
                $issues += "Backend not responding to health checks"
            }
        }
        
        if ($serviceName -eq "mysql") {
            # Check MySQL connectivity
            $mysqlCheck = docker-compose exec -T mysql mysqladmin ping -h localhost 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Status "  └─ MySQL ping: OK" "OK"
            }
            else {
                Write-Status "  └─ MySQL ping: FAILED" "ERROR"
                $allHealthy = $false
                $issues += "MySQL not responding to ping"
            }
        }
        
    }
    else {
        Write-Status "✗ $serviceName : $state ($status)" "ERROR"
        $allHealthy = $false
        $issues += "$serviceName is not running (State: $state)"
    }
}

Write-Status "─────────────────────────────────────────────────" "INFO"
Write-Status ""

# Check for orphaned containers
Write-Status "Checking for orphaned containers..." "INFO"
$orphaned = docker ps -a --filter "status=exited" --filter "name=myadmin" --format "{{.Names}}"
if ($orphaned) {
    Write-Status "⚠ Found orphaned containers:" "WARN"
    $orphaned | ForEach-Object { Write-Status "  - $_" "WARN" }
    
    if ($Fix) {
        Write-Status "Removing orphaned containers..." "INFO"
        docker-compose down --remove-orphans
    }
}
else {
    Write-Status "✓ No orphaned containers" "OK"
}

Write-Status ""

# Check disk space
Write-Status "Checking disk space..." "INFO"
$drive = (Get-Location).Drive.Name
$disk = Get-PSDrive $drive
$freeSpaceGB = [math]::Round($disk.Free / 1GB, 2)
$usedSpaceGB = [math]::Round($disk.Used / 1GB, 2)
$totalSpaceGB = [math]::Round(($disk.Free + $disk.Used) / 1GB, 2)
$freePercent = [math]::Round(($disk.Free / ($disk.Free + $disk.Used)) * 100, 1)

Write-Status "Drive $($drive): $freeSpaceGB GB free / $totalSpaceGB GB total ($freePercent% free)" "INFO"

if ($freeSpaceGB -lt 5) {
    Write-Status "⚠ Low disk space! Less than 5GB free" "WARN"
    $issues += "Low disk space"
}
else {
    Write-Status "✓ Sufficient disk space" "OK"
}

Write-Status ""

# Check Docker resources
Write-Status "Checking Docker resources..." "INFO"
$dockerInfo = docker info --format json | ConvertFrom-Json

if ($dockerInfo.MemTotal) {
    $totalMemGB = [math]::Round($dockerInfo.MemTotal / 1GB, 2)
    Write-Status "Docker Memory: $totalMemGB GB total" "INFO"
}

Write-Status ""

# Summary
Write-Status "=== Health Check Summary ===" "INFO"
if ($allHealthy -and $issues.Count -eq 0) {
    Write-Status "✓ All systems healthy" "OK"
    exit 0
}
else {
    Write-Status "✗ Issues detected:" "ERROR"
    foreach ($issue in $issues) {
        Write-Status "  - $issue" "ERROR"
    }
    
    Write-Status ""
    
    if ($Fix) {
        Write-Status "Attempting automatic fix..." "WARN"
        Write-Status ""
        
        # Stop all containers
        Write-Status "1. Stopping all containers..." "INFO"
        docker-compose down
        
        # Remove any dangling volumes (optional, commented out for safety)
        # docker volume prune -f
        
        # Restart containers
        Write-Status "2. Starting containers..." "INFO"
        docker-compose up -d
        
        # Wait for startup
        Write-Status "3. Waiting for services to start..." "INFO"
        Start-Sleep -Seconds 15
        
        # Re-check
        Write-Status "4. Re-checking health..." "INFO"
        & $PSCommandPath
        
    }
    else {
        Write-Status ""
        Write-Status "Suggested actions:" "INFO"
        Write-Status ""
        Write-Status "Option 1 - Quick Fix (try this first):" "INFO"
        Write-Status "   .\scripts\cicd\check-containers.ps1 -Fix" "WARN"
        Write-Status ""
        Write-Status "Option 2 - Deep Clean (if quick fix doesn't work):" "INFO"
        Write-Status "   .\scripts\cicd\deep-clean.ps1" "WARN"
        Write-Status "   This restarts Docker Desktop and rebuilds everything" "INFO"
        Write-Status ""
        Write-Status "Option 3 - Manual recovery:" "INFO"
        Write-Status "   docker-compose down" "INFO"
        Write-Status "   docker-compose up -d" "INFO"
        Write-Status ""
        Write-Status "Option 4 - View logs for debugging:" "INFO"
        Write-Status "   docker-compose logs" "INFO"
        Write-Status ""
        Write-Status "Option 5 - Last resort (if nothing else works):" "INFO"
        Write-Status "   Restart your laptop, then run: docker-compose up -d" "WARN"
    }
    
    exit 1
}
