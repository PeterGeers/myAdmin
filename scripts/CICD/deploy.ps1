# Deployment Script with Database Safety and Smoke Tests
# This script safely deploys the application with critical database protection

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("staging", "production")]
    [string]$Environment = "staging",
    
    [switch]$SkipBackup = $false,
    [switch]$SkipSmokeTests = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# Get the root directory
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $RootDir "scripts\cicd\logs"
$BackupDir = Join-Path $RootDir "scripts\cicd\backups"
$DeployLog = Join-Path $LogDir "deploy-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

# Create necessary directories
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# Ensure we're in the root directory
Push-Location $RootDir

function Write-Log {
    param($Message, $Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "SUCCESS" { "Green" }
        default { "White" }
    }
    
    Write-Host $logMessage -ForegroundColor $color
    Add-Content -Path $DeployLog -Value $logMessage
}

function Exit-WithError {
    param($Message)
    Write-Log $Message "ERROR"
    Write-Log "Deployment failed. Check log: $DeployLog" "ERROR"
    exit 1
}

function Confirm-Action {
    param($Message)
    if ($Force) { return $true }
    
    $response = Read-Host "$Message (yes/no)"
    return $response -eq "yes"
}

Write-Log "=== Starting Deployment to $Environment ===" "INFO"

# Step 0: Pre-flight Container Check
Write-Log "Step 0: Pre-flight container diagnostics..." "INFO"

# Check if Docker is running
try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Exit-WithError "Docker daemon is not running. Please start Docker Desktop."
    }
    Write-Log "Docker daemon is running" "SUCCESS"
}
catch {
    Exit-WithError "Docker is not installed or not running. Please install and start Docker Desktop."
}

# Check for problematic containers
$existingContainers = docker-compose ps -q 2>&1
if ($existingContainers -and $LASTEXITCODE -eq 0) {
    Write-Log "Existing containers detected, checking health..." "INFO"
    
    # Run container health check
    $healthCheckResult = & "scripts/cicd/check-containers.ps1" 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Container health check failed" "WARN"
        Write-Log "Attempting to fix container issues..." "INFO"
        
        # Try to fix automatically
        docker-compose down 2>&1 | Out-Null
        Start-Sleep -Seconds 3
        
        Write-Log "Cleaned up problematic containers" "INFO"
    }
    else {
        Write-Log "Existing containers are healthy" "SUCCESS"
    }
}

# Step 1: Pre-deployment Validation
Write-Log "Step 1: Pre-deployment validation..." "INFO"

if (-not (Test-Path "docker-compose.yml")) {
    Exit-WithError "docker-compose.yml not found"
}

if (-not (Test-Path "frontend/build/index.html")) {
    Exit-WithError "Frontend build not found. Run build.ps1 first"
}

# Check if containers are running
$runningContainers = docker-compose ps -q
if ($runningContainers -and $Environment -eq "production") {
    Write-Log "Production containers are currently running" "WARN"
    if (-not (Confirm-Action "Continue with deployment?")) {
        Write-Log "Deployment cancelled by user" "INFO"
        exit 0
    }
}

Write-Log "Pre-deployment validation passed" "SUCCESS"

# Step 2: CRITICAL - Database Backup
if (-not $SkipBackup) {
    Write-Log "Step 2: Creating database backup (CRITICAL)..." "INFO"
    
    $backupTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupFile = "$BackupDir/mysql-backup-$backupTimestamp.sql"
    
    # Check if MySQL container is running
    $mysqlContainer = docker-compose ps -q mysql
    
    if ($mysqlContainer) {
        Write-Log "MySQL container found, creating backup..." "INFO"
        
        # Get database credentials from .env
        $envFile = Get-Content "backend/.env"
        $dbPassword = ($envFile | Select-String "MYSQL_ROOT_PASSWORD=(.+)").Matches.Groups[1].Value
        
        if (-not $dbPassword) {
            Exit-WithError "Could not read MYSQL_ROOT_PASSWORD from backend/.env"
        }
        
        # Create backup
        docker-compose exec -T mysql mysqldump -u root -p"$dbPassword" --all-databases --single-transaction --quick --lock-tables=false > $backupFile 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            Exit-WithError "Database backup failed"
        }
        
        # Verify backup file
        if (-not (Test-Path $backupFile) -or (Get-Item $backupFile).Length -lt 1KB) {
            Exit-WithError "Backup file is invalid or empty"
        }
        
        Write-Log "Database backup created: $backupFile" "SUCCESS"
        Write-Log "Backup size: $((Get-Item $backupFile).Length / 1MB) MB" "INFO"
        
        # Keep only last 10 backups
        Get-ChildItem $BackupDir -Filter "mysql-backup-*.sql" | 
        Sort-Object LastWriteTime -Descending | 
        Select-Object -Skip 10 | 
        Remove-Item -Force
            
    }
    else {
        Write-Log "MySQL container not running, skipping backup" "WARN"
    }
}
else {
    Write-Log "Step 2: Database backup SKIPPED (not recommended)" "WARN"
}

# Step 3: Stop Current Services Gracefully
Write-Log "Step 3: Stopping current services..." "INFO"

if ($runningContainers) {
    Write-Log "Gracefully stopping containers..." "INFO"
    docker-compose stop 2>&1 | Tee-Object -FilePath $DeployLog -Append
    
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Graceful stop failed, forcing stop..." "WARN"
        docker-compose down 2>&1 | Tee-Object -FilePath $DeployLog -Append
    }
    
    Write-Log "Services stopped" "SUCCESS"
}

# Step 4: Deploy New Version
Write-Log "Step 4: Deploying new version..." "INFO"

Write-Log "Starting services with docker-compose..." "INFO"
docker-compose up -d 2>&1 | Tee-Object -FilePath $DeployLog -Append

if ($LASTEXITCODE -ne 0) {
    Write-Log "Failed to start services, checking for issues..." "ERROR"
    
    # Capture error details
    $dockerLogs = docker-compose logs --tail=50 2>&1
    Write-Log "Recent container logs:" "ERROR"
    $dockerLogs | Tee-Object -FilePath $DeployLog -Append
    
    Exit-WithError "Failed to start services. Check logs above for details."
}

Write-Log "Services started, waiting for initialization..." "INFO"
Start-Sleep -Seconds 15

# Verify containers are actually running
$runningCheck = docker-compose ps --format json | ConvertFrom-Json
$allRunning = $true

foreach ($container in $runningCheck) {
    if ($container.State -ne "running") {
        Write-Log "Container $($container.Service) is not running (State: $($container.State))" "ERROR"
        $allRunning = $false
        
        # Get logs for failed container
        Write-Log "Logs for $($container.Service):" "ERROR"
        docker-compose logs --tail=30 $container.Service 2>&1 | Tee-Object -FilePath $DeployLog -Append
    }
}

if (-not $allRunning) {
    Exit-WithError "Some containers failed to start properly"
}

# Step 5: Health Checks
Write-Log "Step 5: Running health checks..." "INFO"

$maxRetries = 12
$retryCount = 0
$healthCheckPassed = $false

while ($retryCount -lt $maxRetries) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $healthCheckPassed = $true
            Write-Log "Backend health check passed" "SUCCESS"
            break
        }
    }
    catch {
        $retryCount++
        Write-Log "Health check attempt $retryCount/$maxRetries failed, retrying..." "WARN"
        Start-Sleep -Seconds 5
    }
}

if (-not $healthCheckPassed) {
    Write-Log "Health check failed after $maxRetries attempts" "ERROR"
    Write-Log "Rolling back deployment..." "WARN"
    docker-compose down 2>&1 | Out-Null
    Exit-WithError "Deployment failed health checks"
}

# Step 6: Database Connection Test
Write-Log "Step 6: Testing database connection..." "INFO"

$mysqlContainer = docker-compose ps -q mysql
if ($mysqlContainer) {
    $dbTest = docker-compose exec -T mysql mysql -u root -p"$dbPassword" -e "SELECT 1;" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Database connection test passed" "SUCCESS"
    }
    else {
        Write-Log "Database connection test failed" "ERROR"
        Exit-WithError "Database is not accessible"
    }
}

# Step 7: Smoke Tests
if (-not $SkipSmokeTests) {
    Write-Log "Step 7: Running smoke tests..." "INFO"
    
    # Test 1: Frontend accessibility
    try {
        $frontendResponse = Invoke-WebRequest -Uri "http://localhost:5000/" -TimeoutSec 10 -UseBasicParsing
        if ($frontendResponse.StatusCode -eq 200) {
            Write-Log "✓ Frontend is accessible" "SUCCESS"
        }
    }
    catch {
        Exit-WithError "Frontend smoke test failed"
    }
    
    # Test 2: API endpoint test
    try {
        $apiResponse = Invoke-WebRequest -Uri "http://localhost:5000/api/health" -TimeoutSec 10 -UseBasicParsing
        if ($apiResponse.StatusCode -eq 200) {
            Write-Log "✓ API health endpoint responding" "SUCCESS"
        }
    }
    catch {
        Exit-WithError "API smoke test failed"
    }
    
    # Test 3: Database query test
    Write-Log "Testing database query..." "INFO"
    $dbQueryTest = docker-compose exec -T mysql mysql -u root -p"$dbPassword" -e "SHOW DATABASES;" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Log "✓ Database queries working" "SUCCESS"
    }
    else {
        Exit-WithError "Database query test failed"
    }
    
    Write-Log "All smoke tests passed" "SUCCESS"
}
else {
    Write-Log "Step 7: Smoke tests SKIPPED" "WARN"
}

# Step 8: Deployment Summary
Write-Log "=== Deployment Completed Successfully ===" "SUCCESS"
Write-Log "Environment: $Environment" "INFO"
Write-Log "Deployment log: $DeployLog" "INFO"

if (-not $SkipBackup) {
    Write-Log "Database backup: $backupFile" "INFO"
}

Write-Log "Services status:" "INFO"
docker-compose ps 2>&1 | Tee-Object -FilePath $DeployLog -Append

Write-Log "" "INFO"
Write-Log "Application is now running at:" "INFO"
Write-Log "  Frontend: http://localhost:5000" "INFO"
Write-Log "  Backend API: http://localhost:5000/api" "INFO"
Write-Log "  MySQL: localhost:3306" "INFO"

# Return to original directory
Pop-Location

exit 0
