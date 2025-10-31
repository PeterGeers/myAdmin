#!/usr/bin/env pwsh
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
    "api" {
        Write-Host "Running API Endpoints tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_api_endpoints.py -v
    }
    "environment" {
        Write-Host "Running Environment Mode tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/test_environment.py -v
    }
    "all" {
        Write-Host "Running all tests..." -ForegroundColor Green
        .\venv\Scripts\python.exe -m pytest test/ -v
    }
    default {
        Write-Host "Usage: .\run_tests.ps1 [database|pdf|transaction|banking|str|drive|xlsx|reporting|validation|api|environment|all]" -ForegroundColor Yellow
        Write-Host "Examples:" -ForegroundColor Yellow
        Write-Host "  .\run_tests.ps1 environment" -ForegroundColor Yellow
        Write-Host "  .\run_tests.ps1 all" -ForegroundColor Yellow
    }
}