# ============================================================================
# Connect Local Frontend to Railway Backend
# ============================================================================
# This script starts the local frontend dev server pointing at the Railway
# backend API instead of localhost:5000.
#
# Usage: .\powershell\connect-railway-backend.ps1
# ============================================================================

$RAILWAY_BACKEND_URL = "https://invigorating-celebration-production.up.railway.app"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Connecting local frontend to Railway backend" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Railway Backend: $RAILWAY_BACKEND_URL" -ForegroundColor Yellow
Write-Host ""

# Test Railway backend health first
Write-Host "Testing Railway backend health..." -ForegroundColor Gray
try {
    $response = Invoke-RestMethod -Uri "$RAILWAY_BACKEND_URL/api/health" -TimeoutSec 10
    Write-Host "Backend is healthy!" -ForegroundColor Green
    Write-Host "  Status: $($response.status)" -ForegroundColor Gray
    Write-Host ""
} catch {
    Write-Host "WARNING: Railway backend may be down or sleeping." -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne 'y') { exit 1 }
}

# Set environment and start frontend
Write-Host "Starting frontend with REACT_APP_API_URL=$RAILWAY_BACKEND_URL" -ForegroundColor Green
Write-Host "Frontend will be available at http://localhost:3000" -ForegroundColor Yellow
Write-Host ""

$env:REACT_APP_API_URL = $RAILWAY_BACKEND_URL
Set-Location -Path "$PSScriptRoot\..\frontend"
npm start
