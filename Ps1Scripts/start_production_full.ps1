#!/usr/bin/env pwsh

Write-Host "Starting myAdmin Production Environment..." -ForegroundColor Green

# Build frontend
Write-Host "Building frontend..." -ForegroundColor Yellow
Set-Location "frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Frontend build failed!" -ForegroundColor Red
    exit 1
}

# Start backend
Write-Host "Starting production backend..." -ForegroundColor Yellow
Set-Location "..\backend"

if (-not (Test-Path "venv")) {
    python -m venv venv
}

& ".\venv\Scripts\Activate.ps1"
pip install --upgrade pip
pip uninstall -y numpy pandas
pip install -r requirements.txt

Write-Host "Production server starting on http://127.0.0.1:5000" -ForegroundColor Green
& ".\venv\Scripts\waitress-serve.exe" --host=127.0.0.1 --port=5000 --threads=4 src.app:app