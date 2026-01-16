# Build Script with Validation
# This script validates, lints, and builds both frontend and backend

param(
    [switch]$SkipTests = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"

# Get the root directory (where the script should be run from)
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$LogDir = Join-Path $RootDir "scripts\cicd\logs"
$BuildLog = Join-Path $LogDir "build-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

# Create logs directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Ensure we're in the root directory
Push-Location $RootDir

function Write-Log {
    param($Message, $Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage
    Add-Content -Path $BuildLog -Value $logMessage
}

function Exit-WithError {
    param($Message)
    Write-Log $Message "ERROR"
    exit 1
}

Write-Log "=== Starting Build Process ===" "INFO"

# Step 1: Validate Environment
Write-Log "Step 1: Validating environment..." "INFO"

if (-not (Test-Path "frontend/package.json")) {
    Exit-WithError "Frontend package.json not found"
}

if (-not (Test-Path "backend/requirements.txt")) {
    Exit-WithError "Backend requirements.txt not found"
}

if (-not (Test-Path "docker-compose.yml")) {
    Exit-WithError "docker-compose.yml not found"
}

Write-Log "Environment validation passed" "INFO"

# Step 2: Frontend Validation and Build
Write-Log "Step 2: Building Frontend..." "INFO"

Push-Location frontend

try {
    Write-Log "Installing frontend dependencies..." "INFO"
    npm ci 2>&1 | Tee-Object -FilePath $BuildLog -Append
    if ($LASTEXITCODE -ne 0) { Exit-WithError "Frontend dependency installation failed" }

    Write-Log "Running ESLint..." "INFO"
    npm run lint 2>&1 | Tee-Object -FilePath $BuildLog -Append
    if ($LASTEXITCODE -ne 0) { 
        Write-Log "ESLint warnings detected, continuing..." "WARN"
    }

    if (-not $SkipTests) {
        Write-Log "Running frontend tests..." "INFO"
        $env:CI = "true"
        npm test -- --watchAll=false --coverage 2>&1 | Tee-Object -FilePath $BuildLog -Append
        if ($LASTEXITCODE -ne 0) { Exit-WithError "Frontend tests failed" }
    }

    Write-Log "Building frontend production bundle..." "INFO"
    npm run build 2>&1 | Tee-Object -FilePath $BuildLog -Append
    if ($LASTEXITCODE -ne 0) { Exit-WithError "Frontend build failed" }

    if (-not (Test-Path "build/index.html")) {
        Exit-WithError "Frontend build output not found"
    }

    Write-Log "Frontend build completed successfully" "INFO"
}
finally {
    Pop-Location
}

# Step 3: Backend Validation
Write-Log "Step 3: Validating Backend..." "INFO"

Push-Location backend

try {
    Write-Log "Checking Python virtual environment..." "INFO"
    
    if (-not (Test-Path ".venv")) {
        Write-Log "Creating Python virtual environment..." "INFO"
        python -m venv .venv
    }

    Write-Log "Activating virtual environment..." "INFO"
    & .venv\Scripts\Activate.ps1

    Write-Log "Installing backend dependencies..." "INFO"
    pip install -r requirements.txt 2>&1 | Tee-Object -FilePath $BuildLog -Append
    if ($LASTEXITCODE -ne 0) { Exit-WithError "Backend dependency installation failed" }

    Write-Log "Running Python linting (flake8)..." "INFO"
    pip install flake8 2>&1 | Out-Null
    flake8 src --max-line-length=120 --exclude=__pycache__, venv, .venv 2>&1 | Tee-Object -FilePath $BuildLog -Append
    if ($LASTEXITCODE -ne 0) { 
        Write-Log "Flake8 warnings detected, continuing..." "WARN"
    }

    if (-not $SkipTests) {
        Write-Log "Running backend tests..." "INFO"
        if (Test-Path "requirements-test.txt") {
            pip install -r requirements-test.txt 2>&1 | Out-Null
        }
        pytest test/ -v 2>&1 | Tee-Object -FilePath $BuildLog -Append
        if ($LASTEXITCODE -ne 0) { Exit-WithError "Backend tests failed" }
    }

    Write-Log "Backend validation completed successfully" "INFO"
}
finally {
    Pop-Location
}

# Step 4: Docker Image Build (Optional - images will be built during deployment if needed)
Write-Log "Step 4: Building Docker images..." "INFO"

# Check if Docker is running
Write-Log "Checking Docker daemon..." "INFO"
try {
    docker info 2>&1 | Out-Null
    $dockerRunning = ($LASTEXITCODE -eq 0)
}
catch {
    $dockerRunning = $false
}

if (-not $dockerRunning) {
    Write-Log "Docker is not running" "WARN"
    Write-Log "" "INFO"
    Write-Log "Docker images will be built during deployment when containers are started." "INFO"
    Write-Log "To pre-build images now, start Docker Desktop and re-run this script." "INFO"
    Write-Log "" "INFO"
    Write-Log "Container management options:" "INFO"
    Write-Log "  - Start Docker Desktop manually" "INFO"
    Write-Log "  - Run: scripts\cicd\check-containers.ps1 -Fix" "INFO"
    Write-Log "  - Run: scripts\cicd\deep-clean.ps1 (if containers won't start)" "INFO"
    Write-Log "" "INFO"
    Write-Log "Skipping Docker image build (not critical)" "WARN"
}
else {
    # Docker is running, pre-build images to catch errors early
    Write-Log "Docker is running, building images..." "INFO"
    docker-compose build 2>&1 | Tee-Object -FilePath $BuildLog -Append
    
    if ($LASTEXITCODE -ne 0) { 
        Write-Log "Docker build failed" "ERROR"
        Write-Log "Images will be rebuilt during deployment" "WARN"
    }
    else {
        Write-Log "Docker images built successfully" "SUCCESS"
    }
}

# Step 5: Build Summary
Write-Log "=== Build Process Completed Successfully ===" "INFO"
Write-Log "Build log saved to: $BuildLog" "INFO"

# Return to original directory
Pop-Location

exit 0
