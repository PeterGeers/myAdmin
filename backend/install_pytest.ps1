#!/usr/bin/env pwsh
Set-Location $PSScriptRoot
.\venv\Scripts\python.exe -m pip install pytest pytest-mock
Write-Host "Pytest installed successfully" -ForegroundColor Green