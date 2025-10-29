#!/usr/bin/env pwsh

Write-Host "Starting myAdmin backend with Gunicorn..." -ForegroundColor Green

# Change to backend directory
Set-Location "backend"

# Install requirements if needed
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
& ".\venv\Scripts\Activate.ps1"

# Install/update requirements
pip install -r requirements.txt

# Start Gunicorn server
Write-Host "Starting Gunicorn server on http://127.0.0.1:5000" -ForegroundColor Green
& ".\venv\Scripts\waitress-serve.exe" --host=127.0.0.1 --port=5000 --threads=4 app:app