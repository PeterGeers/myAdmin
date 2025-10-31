#!/usr/bin/env pwsh

Write-Host "Starting myAdmin Backend..." -ForegroundColor Green

# Activate virtual environment and start backend
.venv\Scripts\Activate.ps1
cd src
python app.py