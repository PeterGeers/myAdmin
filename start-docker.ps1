# Start myAdmin with Docker containers
Write-Host "Starting myAdmin with Docker..." -ForegroundColor Green

# Use Docker environment file
if (Test-Path ".env.docker") {
    Copy-Item ".env.docker" ".env"
    Write-Host "Using Docker environment configuration" -ForegroundColor Yellow
} else {
    Write-Host "Warning: .env.docker not found" -ForegroundColor Red
}

# Check if rebuild is requested
$rebuild = $args[0] -eq "--build"

if ($rebuild) {
    Write-Host "Rebuilding containers..." -ForegroundColor Yellow
    docker-compose up --build -d
} else {
    Write-Host "Starting existing containers..." -ForegroundColor Yellow
    docker-compose up -d
}

Write-Host "Docker containers started. Backend: http://localhost:5000" -ForegroundColor Green
Write-Host "Use '.\start-docker.ps1 --build' to rebuild containers" -ForegroundColor Cyan