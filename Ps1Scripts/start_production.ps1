#!/usr/bin/env pwsh

Write-Host "Starting myAdmin Production Environment..." -ForegroundColor Green

# Get the parent directory (myAdmin root)
$rootDir = Split-Path -Parent $PSScriptRoot

# Build React frontend first
Write-Host "Building React frontend..." -ForegroundColor Yellow
Set-Location "$rootDir\frontend"
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "Frontend build failed!" -ForegroundColor Red
    exit 1
}

# Setup backend
Write-Host "Setting up backend..." -ForegroundColor Yellow
Set-Location "$rootDir\backend"

# Install requirements if needed
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
& ".\venv\Scripts\Activate.ps1"

# Install/update requirements
pip install -r requirements.txt

# Start Flask server (serves both React build and API)
Write-Host "Starting Flask server on http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "Access the app at: http://127.0.0.1:5000" -ForegroundColor Cyan
Set-Location "src"
python app.py