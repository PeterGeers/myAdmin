# Environment Validation Script for CI/CD Pipeline
# Validates that all required environment variables and configurations are in place

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("staging", "production")]
    [string]$Environment = "staging",
    
    [switch]$Strict = $false  # Fail on warnings in strict mode
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $RootDir

$errors = @()
$warnings = @()
$passed = @()

function Test-EnvVariable {
    param(
        [string]$FilePath,
        [string]$VarName,
        [string]$Description,
        [bool]$Required = $true,
        [bool]$IsSensitive = $false
    )
    
    if (-not (Test-Path $FilePath)) {
        if ($Required) {
            $script:errors += "File not found: $FilePath"
        }
        else {
            $script:warnings += "File not found: $FilePath"
        }
        return
    }
    
    $content = Get-Content $FilePath -Raw
    
    if ($content -match "$VarName\s*=\s*(.+)") {
        $value = $Matches[1].Trim()
        
        # Check if it's a placeholder
        if ($value -match "<.*>|your-.*|XXXXXXXXX|example") {
            if ($Required) {
                $script:errors += "$VarName in $FilePath is still a placeholder"
            }
            else {
                $script:warnings += "$VarName in $FilePath is still a placeholder"
            }
            return
        }
        
        # Check if it's empty
        if ([string]::IsNullOrWhiteSpace($value)) {
            if ($Required) {
                $script:errors += "$VarName in $FilePath is empty"
            }
            else {
                $script:warnings += "$VarName in $FilePath is empty"
            }
            return
        }
        
        # Success
        if ($IsSensitive) {
            $displayValue = $value.Substring(0, [Math]::Min(4, $value.Length)) + "..." + 
            $value.Substring([Math]::Max(0, $value.Length - 4))
        }
        else {
            $displayValue = $value
        }
        
        $script:passed += "$VarName ($Description): $displayValue"
    }
    else {
        if ($Required) {
            $script:errors += "$VarName not found in $FilePath"
        }
        else {
            $script:warnings += "$VarName not found in $FilePath"
        }
    }
}

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     Environment Validation - $($Environment.PadRight(32))║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ═══ BACKEND ENVIRONMENT VALIDATION ═══
Write-Host "Validating backend/.env..." -ForegroundColor Yellow

# AWS Cognito (Required)
Test-EnvVariable "backend/.env" "COGNITO_USER_POOL_ID" "Cognito User Pool" $true $false
Test-EnvVariable "backend/.env" "COGNITO_CLIENT_ID" "Cognito Client ID" $true $false
Test-EnvVariable "backend/.env" "COGNITO_CLIENT_SECRET" "Cognito Client Secret" $true $true
Test-EnvVariable "backend/.env" "AWS_REGION" "AWS Region" $true $false

# AWS IAM Credentials (Required for boto3)
Test-EnvVariable "backend/.env" "AWS_ACCESS_KEY_ID" "AWS Access Key" $true $true
Test-EnvVariable "backend/.env" "AWS_SECRET_ACCESS_KEY" "AWS Secret Key" $true $true

# Database (Required)
Test-EnvVariable "backend/.env" "DB_HOST" "Database Host" $true $false
Test-EnvVariable "backend/.env" "DB_USER" "Database User" $true $false
Test-EnvVariable "backend/.env" "DB_PASSWORD" "Database Password" $true $true
Test-EnvVariable "backend/.env" "DB_NAME" "Database Name" $true $false
Test-EnvVariable "backend/.env" "MYSQL_ROOT_PASSWORD" "MySQL Root Password" $true $true

# Google Drive (Required)
Test-EnvVariable "backend/.env" "FACTUREN_FOLDER_ID" "Google Drive Folder" $true $false

# OpenRouter (Required)
Test-EnvVariable "backend/.env" "OPENROUTER_API_KEY" "OpenRouter API Key" $true $true

# AWS SNS (Optional)
Test-EnvVariable "backend/.env" "SNS_TOPIC_ARN" "SNS Topic ARN" $false $false

# Test Environment (Optional)
Test-EnvVariable "backend/.env" "TEST_MODE" "Test Mode Flag" $false $false
Test-EnvVariable "backend/.env" "TEST_DB_NAME" "Test Database Name" $false $false

Write-Host ""

# ═══ FILE STRUCTURE VALIDATION ═══
Write-Host "Validating file structure..." -ForegroundColor Yellow

$requiredFiles = @(
    "docker-compose.yml",
    "backend/Dockerfile",
    "backend/requirements.txt",
    "backend/src/app.py",
    "frontend/package.json"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        $passed += "File exists: $file"
    }
    else {
        $errors += "Required file missing: $file"
    }
}

Write-Host ""

# ═══ DOCKER VALIDATION ═══
Write-Host "Validating Docker..." -ForegroundColor Yellow

try {
    docker --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $passed += "Docker is installed"
        
        # Check if Docker daemon is running
        docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $passed += "Docker daemon is running"
        }
        else {
            $warnings += "Docker daemon is not running"
        }
    }
    else {
        $errors += "Docker is not installed"
    }
}
catch {
    $errors += "Docker is not installed or not in PATH"
}

Write-Host ""

# ═══ SECURITY VALIDATION ═══
Write-Host "Validating security configuration..." -ForegroundColor Yellow

# Check .gitignore
if (Test-Path ".gitignore") {
    $gitignoreContent = Get-Content ".gitignore" -Raw
    
    $securityPatterns = @(
        @{Pattern = "\.env"; Name = ".env files" },
        @{Pattern = "cache/"; Name = "cache directory" },
        @{Pattern = "backend/cache/"; Name = "backend cache" },
        @{Pattern = "\*\.sql"; Name = "SQL dumps" },
        @{Pattern = "credentials\.json"; Name = "credentials files" }
    )
    
    foreach ($check in $securityPatterns) {
        if ($gitignoreContent -match $check.Pattern) {
            $passed += ".gitignore excludes: $($check.Name)"
        }
        else {
            $warnings += ".gitignore missing: $($check.Name)"
        }
    }
}
else {
    $errors += ".gitignore file not found"
}

# Check for accidentally committed secrets
$sensitiveFiles = @(
    "backend/.env",
    "backend/credentials.json",
    "backend/token.json"
)

foreach ($file in $sensitiveFiles) {
    if (Test-Path $file) {
        $isTracked = git ls-files $file 2>&1
        if ($isTracked -and $LASTEXITCODE -eq 0) {
            $errors += "SECURITY: $file is tracked in git! Remove with: git rm --cached $file"
        }
        else {
            $passed += "Security: $file is not tracked in git"
        }
    }
}

Write-Host ""

# ═══ RESULTS SUMMARY ═══
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    VALIDATION RESULTS                      ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if ($passed.Count -gt 0) {
    Write-Host "✅ PASSED ($($passed.Count)):" -ForegroundColor Green
    foreach ($item in $passed) {
        Write-Host "   $item" -ForegroundColor Green
    }
    Write-Host ""
}

if ($warnings.Count -gt 0) {
    Write-Host "⚠️  WARNINGS ($($warnings.Count)):" -ForegroundColor Yellow
    foreach ($item in $warnings) {
        Write-Host "   $item" -ForegroundColor Yellow
    }
    Write-Host ""
}

if ($errors.Count -gt 0) {
    Write-Host "❌ ERRORS ($($errors.Count)):" -ForegroundColor Red
    foreach ($item in $errors) {
        Write-Host "   $item" -ForegroundColor Red
    }
    Write-Host ""
}

# ═══ EXIT CODE ═══
if ($errors.Count -gt 0) {
    Write-Host "❌ VALIDATION FAILED" -ForegroundColor Red
    Write-Host "Fix the errors above before deploying" -ForegroundColor Red
    Pop-Location
    exit 1
}

if ($Strict -and $warnings.Count -gt 0) {
    Write-Host "⚠️  VALIDATION FAILED (Strict Mode)" -ForegroundColor Yellow
    Write-Host "Fix the warnings above before deploying in strict mode" -ForegroundColor Yellow
    Pop-Location
    exit 1
}

Write-Host "✅ VALIDATION PASSED" -ForegroundColor Green
Write-Host "Environment is ready for deployment" -ForegroundColor Green

Pop-Location
exit 0
