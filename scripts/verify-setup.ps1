# Setup Verification Script
# Checks that all required configuration is in place before starting the application

Write-Host "🔍 Verifying myAdmin Setup..." -ForegroundColor Cyan
Write-Host "=" * 60

$errors = @()
$warnings = @()

# Check if backend/.env exists
if (Test-Path "backend/.env") {
    Write-Host "✅ backend/.env exists" -ForegroundColor Green
    
    # Check for required variables in backend/.env
    $envContent = Get-Content "backend/.env" -Raw
    
    $requiredVars = @(
        "COGNITO_USER_POOL_ID",
        "COGNITO_CLIENT_ID",
        "COGNITO_CLIENT_SECRET",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "DB_HOST",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
        "FACTUREN_FOLDER_ID",
        "OPENROUTER_API_KEY"
    )
    
    foreach ($var in $requiredVars) {
        if ($envContent -match "$var=.+") {
            Write-Host "  ✅ $var is set" -ForegroundColor Green
        }
        else {
            Write-Host "  ❌ $var is MISSING" -ForegroundColor Red
            $errors += "$var is missing from backend/.env"
        }
    }
}
else {
    Write-Host "❌ backend/.env NOT FOUND" -ForegroundColor Red
    $errors += "backend/.env file does not exist. Copy from backend/.env.example"
}

Write-Host ""

# Check if Docker is running
try {
    docker ps | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "❌ Docker is NOT running" -ForegroundColor Red
    $errors += "Docker is not running. Start Docker Desktop."
}

# Check if containers are running
$backendRunning = docker ps --filter "name=myadmin-backend-1" --format "{{.Names}}"
$mysqlRunning = docker ps --filter "name=myadmin-mysql-1" --format "{{.Names}}"

if ($backendRunning) {
    Write-Host "✅ Backend container is running" -ForegroundColor Green
}
else {
    Write-Host "⚠️  Backend container is NOT running" -ForegroundColor Yellow
    $warnings += "Backend container is not running. Run: docker-compose up -d"
}

if ($mysqlRunning) {
    Write-Host "✅ MySQL container is running" -ForegroundColor Green
}
else {
    Write-Host "⚠️  MySQL container is NOT running" -ForegroundColor Yellow
    $warnings += "MySQL container is not running. Run: docker-compose up -d"
}

Write-Host ""
Write-Host "=" * 60

# Summary
if ($errors.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "✅ ALL CHECKS PASSED - System is ready!" -ForegroundColor Green
    exit 0
}
else {
    if ($errors.Count -gt 0) {
        Write-Host "❌ ERRORS FOUND ($($errors.Count)):" -ForegroundColor Red
        foreach ($error in $errors) {
            Write-Host "   - $error" -ForegroundColor Red
        }
    }
    
    if ($warnings.Count -gt 0) {
        Write-Host "⚠️  WARNINGS ($($warnings.Count)):" -ForegroundColor Yellow
        foreach ($warning in $warnings) {
            Write-Host "   - $warning" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-Host "💡 Fix the errors above before starting the application" -ForegroundColor Cyan
    exit 1
}
