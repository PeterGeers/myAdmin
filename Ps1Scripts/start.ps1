# Start myAdmin application from Scripts directory
Write-Host "Starting myAdmin application..." -ForegroundColor Green

# Get the parent directory (myAdmin root)
$rootDir = Split-Path -Parent $PSScriptRoot

# Activate virtual environment and start backend
Write-Host "Starting backend server..." -ForegroundColor Yellow
Start-Process PowerShell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\backend'; .\.venv\Scripts\Activate.ps1; cd src; python app.py"

# Wait a moment for backend to start
Start-Sleep -Seconds 3

# Start frontend
Write-Host "Starting frontend server..." -ForegroundColor Yellow
Start-Process PowerShell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\frontend'; npm start"

Write-Host "Both servers starting..." -ForegroundColor Green
Write-Host "Backend: http://localhost:5000" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Cyan