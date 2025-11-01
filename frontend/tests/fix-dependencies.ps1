#!/usr/bin/env pwsh

Write-Host "Fixing Frontend Test Dependencies..." -ForegroundColor Green

Set-Location $PSScriptRoot\..

Write-Host "Installing missing Chakra UI dependencies..." -ForegroundColor Yellow
npm install @chakra-ui/system @chakra-ui/theme-tools @chakra-ui/styled-system

Write-Host "Updating test dependencies..." -ForegroundColor Yellow  
npm install --save-dev @testing-library/jest-dom@latest @testing-library/react@latest

Write-Host "Dependencies fixed! Now you can run:" -ForegroundColor Green
Write-Host "npm test -- app.routing.test.tsx --watchAll=false" -ForegroundColor Cyan