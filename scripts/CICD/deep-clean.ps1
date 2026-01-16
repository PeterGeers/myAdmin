# Deep Clean and Recovery Script
# Use this when containers won't start properly and before restarting your laptop
# This performs aggressive cleanup of Docker resources

param(
    [switch]$Force = $false,
    [switch]$KeepData = $true
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

Write-Status "╔════════════════════════════════════════════════════════════╗" "WARN"
Write-Status "║          DEEP CLEAN & RECOVERY SCRIPT                      ║" "WARN"
Write-Status "║   Use this when containers won't start properly           ║" "WARN"
Write-Status "╚════════════════════════════════════════════════════════════╝" "WARN"
Write-Status ""

if (-not $Force) {
    Write-Host "This script will:" -ForegroundColor Yellow
    Write-Host "  1. Stop all containers" -ForegroundColor White
    Write-Host "  2. Remove all containers" -ForegroundColor White
    Write-Host "  3. Clean up Docker networks" -ForegroundColor White
    Write-Host "  4. Remove dangling images" -ForegroundColor White
    Write-Host "  5. Restart Docker Desktop" -ForegroundColor White
    Write-Host "  6. Rebuild and restart containers" -ForegroundColor White
    Write-Host ""
    
    if ($KeepData) {
        Write-Host "✓ Database data will be PRESERVED (mysql_data folder)" -ForegroundColor Green
    }
    else {
        Write-Host "⚠ WARNING: Database data will be DELETED!" -ForegroundColor Red
    }
    
    Write-Host ""
    $confirm = Read-Host "Type 'CLEAN' to continue or anything else to cancel"
    
    if ($confirm -ne "CLEAN") {
        Write-Status "Operation cancelled" "INFO"
        exit 0
    }
}

Write-Status ""
Write-Status "=== Starting Deep Clean ===" "INFO"
Write-Status ""

# Step 1: Stop all myAdmin containers
Write-Status "Step 1: Stopping all containers..." "INFO"
docker-compose down --remove-orphans 2>&1 | Out-Null
Write-Status "✓ Containers stopped" "OK"
Start-Sleep -Seconds 2

# Step 2: Remove all stopped containers (myAdmin related)
Write-Status "Step 2: Removing stopped containers..." "INFO"
$stoppedContainers = docker ps -a -q --filter "name=myadmin"
if ($stoppedContainers) {
    docker rm -f $stoppedContainers 2>&1 | Out-Null
    Write-Status "✓ Removed stopped containers" "OK"
}
else {
    Write-Status "✓ No stopped containers to remove" "OK"
}

# Step 3: Clean up networks
Write-Status "Step 3: Cleaning up Docker networks..." "INFO"
docker network prune -f 2>&1 | Out-Null
Write-Status "✓ Networks cleaned" "OK"

# Step 4: Remove dangling images
Write-Status "Step 4: Removing dangling images..." "INFO"
docker image prune -f 2>&1 | Out-Null
Write-Status "✓ Dangling images removed" "OK"

# Step 5: Clean build cache (optional, saves space)
Write-Status "Step 5: Cleaning build cache..." "INFO"
docker builder prune -f 2>&1 | Out-Null
Write-Status "✓ Build cache cleaned" "OK"

# Step 6: Remove volumes (only if not keeping data)
if (-not $KeepData) {
    Write-Status "Step 6: Removing volumes (INCLUDING DATABASE DATA)..." "WARN"
    docker volume prune -f 2>&1 | Out-Null
    Write-Status "✓ Volumes removed" "OK"
}
else {
    Write-Status "Step 6: Skipping volume removal (keeping database data)" "OK"
}

# Step 7: Restart Docker Desktop
Write-Status ""
Write-Status "Step 7: Restarting Docker Desktop..." "INFO"
Write-Status "This may take 30-60 seconds..." "INFO"

# Stop Docker Desktop
$dockerDesktop = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if ($dockerDesktop) {
    Write-Status "Stopping Docker Desktop..." "INFO"
    Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
}

# Stop Docker service
Write-Status "Stopping Docker service..." "INFO"
Stop-Service -Name "com.docker.service" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

# Start Docker Desktop
Write-Status "Starting Docker Desktop..." "INFO"
$dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (Test-Path $dockerPath) {
    Start-Process $dockerPath
    Write-Status "Waiting for Docker to start..." "INFO"
    
    # Wait for Docker to be ready (max 60 seconds)
    $maxWait = 60
    $waited = 0
    $dockerReady = $false
    
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 2
        $waited += 2
        
        try {
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $dockerReady = $true
                break
            }
        }
        catch {
            # Docker not ready yet
        }
        
        Write-Host "." -NoNewline
    }
    
    Write-Host ""
    
    if ($dockerReady) {
        Write-Status "✓ Docker Desktop is running" "OK"
    }
    else {
        Write-Status "⚠ Docker Desktop may not be fully ready" "WARN"
        Write-Status "  Waiting additional 10 seconds..." "INFO"
        Start-Sleep -Seconds 10
    }
}
else {
    Write-Status "⚠ Could not find Docker Desktop executable" "WARN"
    Write-Status "  Please start Docker Desktop manually" "WARN"
    Write-Status "  Press Enter when Docker Desktop is running..." "INFO"
    Read-Host
}

# Step 8: Verify Docker is working
Write-Status ""
Write-Status "Step 8: Verifying Docker is working..." "INFO"
try {
    docker info | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Status "✓ Docker is responding" "OK"
    }
    else {
        Write-Status "✗ Docker is not responding properly" "ERROR"
        Write-Status "  You may need to restart your laptop" "WARN"
        exit 1
    }
}
catch {
    Write-Status "✗ Docker is not responding" "ERROR"
    Write-Status "  You may need to restart your laptop" "WARN"
    exit 1
}

# Step 9: Rebuild images
Write-Status ""
Write-Status "Step 9: Rebuilding Docker images..." "INFO"
docker-compose build --no-cache 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Status "✓ Images rebuilt successfully" "OK"
}
else {
    Write-Status "⚠ Image rebuild had issues, but continuing..." "WARN"
}

# Step 10: Start containers
Write-Status ""
Write-Status "Step 10: Starting containers..." "INFO"
docker-compose up -d 2>&1 | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Status "✗ Failed to start containers" "ERROR"
    Write-Status ""
    Write-Status "Troubleshooting steps:" "WARN"
    Write-Status "1. Check Docker Desktop is running" "INFO"
    Write-Status "2. View logs: docker-compose logs" "INFO"
    Write-Status "3. Try manual start: docker-compose up -d" "INFO"
    Write-Status "4. If all else fails, restart your laptop" "WARN"
    exit 1
}

Write-Status "✓ Containers started" "OK"
Write-Status "Waiting for services to initialize..." "INFO"
Start-Sleep -Seconds 15

# Step 11: Health check
Write-Status ""
Write-Status "Step 11: Running health check..." "INFO"

$healthCheckPassed = $false
$retries = 0
$maxRetries = 6

while ($retries -lt $maxRetries) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $healthCheckPassed = $true
            break
        }
    }
    catch {
        $retries++
        if ($retries -lt $maxRetries) {
            Write-Host "." -NoNewline
            Start-Sleep -Seconds 5
        }
    }
}

Write-Host ""

if ($healthCheckPassed) {
    Write-Status "✓ Health check passed" "OK"
}
else {
    Write-Status "⚠ Health check failed" "WARN"
    Write-Status "  Containers may still be starting up" "INFO"
    Write-Status "  Check status with: docker-compose ps" "INFO"
}

# Final status
Write-Status ""
Write-Status "=== Deep Clean Complete ===" "OK"
Write-Status ""
Write-Status "Container status:" "INFO"
docker-compose ps

Write-Status ""
Write-Status "Next steps:" "INFO"
Write-Status "1. Check if application is accessible: http://localhost:5000" "INFO"
Write-Status "2. View logs if needed: docker-compose logs -f" "INFO"
Write-Status "3. If still not working, restart your laptop and run:" "INFO"
Write-Status "   docker-compose up -d" "INFO"

Write-Status ""
Write-Status "╔════════════════════════════════════════════════════════════╗" "OK"
Write-Status "║          Recovery process completed                        ║" "OK"
Write-Status "╚════════════════════════════════════════════════════════════╝" "OK"

# Return to original directory
Pop-Location

exit 0
