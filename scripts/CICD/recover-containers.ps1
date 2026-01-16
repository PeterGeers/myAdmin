# Container Recovery Script
# Quick recovery for common container issues

param(
    [switch]$Restart = $false,
    [switch]$Rebuild = $false
)

$ErrorActionPreference = "Continue"

# Get the root directory
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

Write-Status "=== Container Recovery ===" "INFO"
Write-Status ""

# Check if Docker is running
try {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Status "Docker is not running!" "ERROR"
        Write-Status "Please start Docker Desktop first" "WARN"
        exit 1
    }
}
catch {
    Write-Status "Docker is not available!" "ERROR"
    Write-Status "Please install and start Docker Desktop" "WARN"
    exit 1
}

if ($Rebuild) {
    Write-Status "Rebuilding containers from scratch..." "INFO"
    Write-Status ""
    
    Write-Status "1. Stopping containers..." "INFO"
    docker-compose down
    
    Write-Status "2. Rebuilding images..." "INFO"
    docker-compose build --no-cache
    
    Write-Status "3. Starting containers..." "INFO"
    docker-compose up -d
    
    Write-Status "4. Waiting for startup..." "INFO"
    Start-Sleep -Seconds 15
    
}
elseif ($Restart) {
    Write-Status "Restarting containers..." "INFO"
    Write-Status ""
    
    Write-Status "1. Stopping containers..." "INFO"
    docker-compose down
    
    Write-Status "2. Starting containers..." "INFO"
    docker-compose up -d
    
    Write-Status "3. Waiting for startup..." "INFO"
    Start-Sleep -Seconds 10
    
}
else {
    Write-Status "Quick recovery (restart without rebuild)..." "INFO"
    Write-Status ""
    
    Write-Status "1. Restarting containers..." "INFO"
    docker-compose restart
    
    Write-Status "2. Waiting for startup..." "INFO"
    Start-Sleep -Seconds 10
}

Write-Status ""
Write-Status "Checking container status..." "INFO"
docker-compose ps

Write-Status ""
Write-Status "Recovery complete!" "OK"
Write-Status ""
Write-Status "Options:" "INFO"
Write-Status "  Quick restart:  .\scripts\cicd\recover-containers.ps1" "INFO"
Write-Status "  Full restart:   .\scripts\cicd\recover-containers.ps1 -Restart" "INFO"
Write-Status "  Full rebuild:   .\scripts\cicd\recover-containers.ps1 -Rebuild" "INFO"
Write-Status "  Deep clean:     .\scripts\cicd\deep-clean.ps1" "INFO"

Pop-Location
exit 0
