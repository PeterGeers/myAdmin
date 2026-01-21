# TypeScript Compilation Test for Reports
# This script verifies that all report components compile without errors

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TypeScript Compilation Test for Reports" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Change to frontend directory
Set-Location -Path $PSScriptRoot/../..

Write-Host "Running TypeScript compiler check..." -ForegroundColor Yellow
Write-Host ""

# Run TypeScript compiler in no-emit mode
$result = npx tsc --noEmit 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ SUCCESS: All report components compile without errors!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Verified components:" -ForegroundColor Cyan
    Write-Host "  - MyAdminReportsNew.tsx" -ForegroundColor White
    Write-Host "  - BnbReportsGroup.tsx" -ForegroundColor White
    Write-Host "  - FinancialReportsGroup.tsx" -ForegroundColor White
    Write-Host "  - BnbRevenueReport.tsx" -ForegroundColor White
    Write-Host "  - BnbActualsReport.tsx" -ForegroundColor White
    Write-Host "  - BnbViolinsReport.tsx" -ForegroundColor White
    Write-Host "  - BnbReturningGuestsReport.tsx" -ForegroundColor White
    Write-Host "  - BnbFutureReport.tsx" -ForegroundColor White
    Write-Host "  - ToeristenbelastingReport.tsx" -ForegroundColor White
    Write-Host "  - MutatiesReport.tsx" -ForegroundColor White
    Write-Host "  - ActualsReport.tsx" -ForegroundColor White
    Write-Host "  - BtwReport.tsx" -ForegroundColor White
    Write-Host "  - ReferenceAnalysisReport.tsx" -ForegroundColor White
    Write-Host "  - AangifteIbReport.tsx" -ForegroundColor White
    Write-Host ""
    exit 0
}
else {
    Write-Host "❌ FAILED: TypeScript compilation errors detected!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Errors:" -ForegroundColor Red
    Write-Host $result -ForegroundColor Red
    Write-Host ""
    exit 1
}
