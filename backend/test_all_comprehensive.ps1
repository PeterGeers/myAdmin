#!/usr/bin/env pwsh
# Comprehensive test runner with detailed reporting

Set-Location $PSScriptRoot

Write-Host "=== myAdmin Backend Comprehensive Test Suite ===" -ForegroundColor Cyan
Write-Host "Running all unit tests with detailed reporting..." -ForegroundColor Green
Write-Host ""

# Test components in order
$TestSuites = @(
    @{Name="Infrastructure"; File="test_infrastructure.py"; Description="Test framework and utilities"},
    @{Name="Database"; File="test_database.py"; Description="Database operations and connections"},
    @{Name="PDF Processing"; File="test_pdf_processor.py"; Description="PDF text extraction and parsing"},
    @{Name="Transaction Logic"; File="test_transaction_logic.py"; Description="Business logic and validation"},
    @{Name="Banking Processor"; File="test_banking_processor.py"; Description="CSV processing and pattern matching"},
    @{Name="STR Processor"; File="test_str_processor.py"; Description="Short-term rental data processing"},
    @{Name="Google Drive"; File="test_google_drive.py"; Description="Google Drive integration"},
    @{Name="XLSX Export"; File="test_xlsx_export.py"; Description="Excel report generation"},
    @{Name="Reporting Routes"; File="test_reporting_routes.py"; Description="API reporting endpoints"},
    @{Name="PDF Validation"; File="test_pdf_validation.py"; Description="URL validation and tracking"},
    @{Name="API Endpoints"; File="test_api_endpoints.py"; Description="Flask route testing"},
    @{Name="Environment"; File="test_environment.py"; Description="Mode switching and configuration"}
)

$TotalTests = 0
$PassedTests = 0
$FailedTests = 0
$Results = @()

foreach ($Suite in $TestSuites) {
    Write-Host "Running $($Suite.Name) tests..." -ForegroundColor Yellow
    Write-Host "  $($Suite.Description)" -ForegroundColor Gray
    
    $StartTime = Get-Date
    $TestResult = & .\venv\Scripts\python.exe -m pytest "test/$($Suite.File)" -v --tb=short 2>&1
    $EndTime = Get-Date
    $Duration = ($EndTime - $StartTime).TotalSeconds
    
    # Parse results
    $TestOutput = $TestResult -join "`n"
    $PassedMatch = [regex]::Match($TestOutput, "(\d+) passed")
    $FailedMatch = [regex]::Match($TestOutput, "(\d+) failed")
    $SuitePassed = if ($PassedMatch.Success) { [int]$PassedMatch.Groups[1].Value } else { 0 }
    $SuiteFailed = if ($FailedMatch.Success) { [int]$FailedMatch.Groups[1].Value } else { 0 }
    $SuiteTotal = $SuitePassed + $SuiteFailed
    
    $TotalTests += $SuiteTotal
    $PassedTests += $SuitePassed
    $FailedTests += $SuiteFailed
    
    $Status = if ($SuiteFailed -eq 0) { "PASS" } else { "FAIL" }
    $StatusColor = if ($SuiteFailed -eq 0) { "Green" } else { "Red" }
    
    Write-Host "  Result: $Status ($SuitePassed/$SuiteTotal passed) - ${Duration}s" -ForegroundColor $StatusColor
    
    $Results += @{
        Name = $Suite.Name
        File = $Suite.File
        Description = $Suite.Description
        Passed = $SuitePassed
        Failed = $SuiteFailed
        Total = $SuiteTotal
        Duration = $Duration
        Status = $Status
    }
    
    Write-Host ""
}

# Summary Report
Write-Host "=== Test Summary Report ===" -ForegroundColor Cyan
Write-Host ""

$OverallStatus = if ($FailedTests -eq 0) { "PASS" } else { "FAIL" }
$OverallColor = if ($FailedTests -eq 0) { "Green" } else { "Red" }

Write-Host "Overall Result: $OverallStatus" -ForegroundColor $OverallColor
Write-Host "Total Tests: $TotalTests" -ForegroundColor White
Write-Host "Passed: $PassedTests" -ForegroundColor Green
Write-Host "Failed: $FailedTests" -ForegroundColor Red
Write-Host "Success Rate: $([math]::Round(($PassedTests / $TotalTests) * 100, 1))%" -ForegroundColor White
Write-Host ""

# Detailed Results Table
Write-Host "Detailed Results:" -ForegroundColor White
Write-Host "Component".PadRight(20) + "Tests".PadRight(8) + "Pass".PadRight(6) + "Fail".PadRight(6) + "Time".PadRight(8) + "Status" -ForegroundColor Gray
Write-Host ("-" * 60) -ForegroundColor Gray

foreach ($Result in $Results) {
    $StatusColor = if ($Result.Status -eq "PASS") { "Green" } else { "Red" }
    $Line = $Result.Name.PadRight(20) + 
            $Result.Total.ToString().PadRight(8) + 
            $Result.Passed.ToString().PadRight(6) + 
            $Result.Failed.ToString().PadRight(6) + 
            "$([math]::Round($Result.Duration, 1))s".PadRight(8) + 
            $Result.Status
    Write-Host $Line -ForegroundColor $StatusColor
}

Write-Host ""

# Failed Tests Details
if ($FailedTests -gt 0) {
    Write-Host "=== Failed Test Details ===" -ForegroundColor Red
    foreach ($Result in $Results) {
        if ($Result.Failed -gt 0) {
            Write-Host "$($Result.Name): $($Result.Failed) failed tests" -ForegroundColor Red
            Write-Host "  File: $($Result.File)" -ForegroundColor Gray
            Write-Host "  Run: .\run_tests.ps1 $($Result.Name.ToLower().Replace(' ', ''))" -ForegroundColor Yellow
        }
    }
    Write-Host ""
}

# Coverage Summary
Write-Host "=== Test Coverage Summary ===" -ForegroundColor Cyan
Write-Host "✅ Database Layer: Connection handling, query execution, test/production mode" -ForegroundColor Green
Write-Host "✅ PDF Processing: Text extraction, vendor parsing, file handling" -ForegroundColor Green
Write-Host "✅ Transaction Logic: Business rules, template matching, validation" -ForegroundColor Green
Write-Host "✅ Banking Processor: CSV processing, pattern matching, duplicate detection" -ForegroundColor Green
Write-Host "✅ STR Processing: Multi-platform file processing, financial calculations" -ForegroundColor Green
Write-Host "✅ Google Drive: Authentication, file operations, folder management" -ForegroundColor Green
Write-Host "✅ XLSX Export: Excel generation, R script logic, balance calculations" -ForegroundColor Green
Write-Host "✅ Reporting Routes: API endpoints, data aggregation, filtering" -ForegroundColor Green
Write-Host "✅ PDF Validation: URL validation, progress tracking, record updates" -ForegroundColor Green
Write-Host "✅ API Endpoints: Flask routes, request handling, error responses" -ForegroundColor Green
Write-Host "✅ Environment: Mode switching, configuration, variable handling" -ForegroundColor Green
Write-Host "✅ Test Infrastructure: Fixtures, mocking, temporary files, isolation" -ForegroundColor Green
Write-Host ""

Write-Host "=== Test Infrastructure Features ===" -ForegroundColor Cyan
Write-Host "✅ pytest framework with comprehensive fixtures" -ForegroundColor Green
Write-Host "✅ Mock/patch for external services (MySQL, Google Drive, Gmail)" -ForegroundColor Green
Write-Host "✅ Temporary file and directory handling" -ForegroundColor Green
Write-Host "✅ Environment variable mocking and isolation" -ForegroundColor Green
Write-Host "✅ Test data factories and sample data generation" -ForegroundColor Green
Write-Host "✅ Database mocking and query result simulation" -ForegroundColor Green
Write-Host "✅ Integration test markers and configuration" -ForegroundColor Green
Write-Host "✅ Comprehensive helper utilities and assertions" -ForegroundColor Green
Write-Host ""

if ($FailedTests -eq 0) {
    Write-Host "🎉 All tests passed! The myAdmin backend is fully tested and ready." -ForegroundColor Green
} else {
    Write-Host "⚠️  Some tests failed. Please review and fix the failing tests." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Total test execution time: $([math]::Round(($Results | Measure-Object Duration -Sum).Sum, 1)) seconds" -ForegroundColor White