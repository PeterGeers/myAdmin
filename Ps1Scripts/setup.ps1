# myAdmin Setup Script
Write-Host "Setting up myAdmin development environment..." -ForegroundColor Green

$rootDir = Split-Path -Parent $PSScriptRoot

# Backend setup
Write-Host "Setting up Python backend..." -ForegroundColor Yellow
cd "$rootDir\backend"
if (!(Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Frontend setup
Write-Host "Setting up React frontend..." -ForegroundColor Yellow
cd "$rootDir\frontend"
npm install

Write-Host "Setup complete! Run 'Start: Both Servers' task to begin." -ForegroundColor Green