#!/usr/bin/env pwsh
# Install missing test dependencies for myAdmin frontend

Set-Location $PSScriptRoot

Write-Host "Installing missing test dependencies..." -ForegroundColor Green

# Install MSW (Mock Service Worker) for API mocking
npm install --save-dev msw

# Install additional testing utilities
npm install --save-dev jest-axe

Write-Host "✅ Test dependencies installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Installed packages:" -ForegroundColor Yellow
Write-Host "  - msw (Mock Service Worker for API mocking)" -ForegroundColor White
Write-Host "  - jest-axe (Accessibility testing)" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run 'npx msw init public/' to setup MSW" -ForegroundColor White
Write-Host "  2. Create test setup files as outlined in the test plan" -ForegroundColor White