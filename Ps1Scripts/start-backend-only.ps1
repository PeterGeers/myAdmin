# Start only the backend server in virtual environment
Write-Host "Starting myAdmin backend server..." -ForegroundColor Green

# Kill any existing Python processes
Write-Host "Stopping existing Python processes..." -ForegroundColor Yellow
taskkill /f /im python.exe 2>$null

# Get the parent directory (myAdmin root)
$rootDir = Split-Path -Parent $PSScriptRoot

# Activate virtual environment and start backend
Set-Location "$rootDir\backend"
.\.venv\Scripts\Activate.ps1
Set-Location src
python app.py