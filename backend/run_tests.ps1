#!/usr/bin/env pwsh
# Individual Component Test Runner
# For comprehensive testing with detailed reporting, use: .\test_all_comprehensive.ps1

param(
    [string]$TestType = "all"
)

Set-Location $PSScriptRoot

switch ($TestType.ToLower()) {
    "database" {
        Write-Host "Running Database tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_database.py -v
    }
    "pdf" {
        Write-Host "Running PDF Processor tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_pdf_processor.py -v
    }
    "transaction" {
        Write-Host "Running Transaction Logic tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_transaction_logic.py -v
    }
    "banking" {
        Write-Host "Running Banking Processor tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_banking_processor.py -v
    }
    "str" {
        Write-Host "Running STR Processor tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_str_processor.py -v
    }
    "drive" {
        Write-Host "Running Google Drive tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_google_drive.py -v
    }
    "xlsx" {
        Write-Host "Running XLSX Export tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_xlsx_export.py -v
    }
    "reporting" {
        Write-Host "Running Reporting Routes tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_reporting_routes.py -v
    }
    "validation" {
        Write-Host "Running PDF Validation tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_pdf_validation.py -v
    }
    "image-ai" {
        Write-Host "Running Image AI Processor tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_image_ai.py -v
    }
    "alignment" {
        Write-Host "Running API Alignment tests..." -ForegroundColor Green
        Write-Host "(Checks if frontend API calls match backend routes)" -ForegroundColor Gray
        .\venv\Scripts\python.exe test/test_api_alignment.py
    }
    "environment" {
        Write-Host "Running Environment Mode tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_environment.py -v
    }
    "infrastructure" {
        Write-Host "Running Test Infrastructure tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_infrastructure.py -v
    }
    "str-channel" {
        Write-Host "Running STR Channel Revenue tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_str_channel.py -v
    }
    "all" {
        Write-Host "Running all tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/ -v
    }
    default {
        Write-Host "=== Individual Component Test Runner ===" -ForegroundColor Cyan
        Write-Host "Usage: .\run_tests.ps1 [component]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Available components:" -ForegroundColor White
        Write-Host "  database     - Database operations and connections" -ForegroundColor Gray
        Write-Host "  pdf          - PDF text extraction and parsing" -ForegroundColor Gray
        Write-Host "  transaction  - Business logic and validation" -ForegroundColor Gray
        Write-Host "  banking      - CSV processing and pattern matching" -ForegroundColor Gray
        Write-Host "  str          - Short-term rental data processing" -ForegroundColor Gray
        Write-Host "  drive        - Google Drive integration" -ForegroundColor Gray
        Write-Host "  xlsx         - Excel report generation" -ForegroundColor Gray
        Write-Host "  reporting    - API reporting endpoints" -ForegroundColor Gray
        Write-Host "  validation   - URL validation and tracking" -ForegroundColor Gray
        Write-Host "  image-ai     - AI image processing tests" -ForegroundColor Gray
        Write-Host "  alignment    - Frontend-backend API route matching" -ForegroundColor Yellow
        Write-Host "  environment  - Mode switching and configuration" -ForegroundColor Gray
        Write-Host "  infrastructure - Test framework validation" -ForegroundColor Gray
        Write-Host "  str-channel  - STR Channel Revenue calculations" -ForegroundColor Gray
        Write-Host "  all          - Run all pytest tests" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor White
        Write-Host "  .\run_tests.ps1 alignment    # Check API route alignment" -ForegroundColor Yellow
        Write-Host "  .\run_tests.ps1 image-ai     # Test AI image processing" -ForegroundColor Gray
        Write-Host "  .\run_tests.ps1 all          # Run all pytest tests" -ForegroundColor Gray
        Write-Host ""
        Write-Host "For comprehensive testing with detailed reporting:" -ForegroundColor Cyan
        Write-Host "  .\test_all_comprehensive.ps1" -ForegroundColor Green
    }
}