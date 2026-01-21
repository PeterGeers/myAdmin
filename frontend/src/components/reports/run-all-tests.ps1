# Comprehensive Test Runner for Reports Refactoring
# This script runs all tests to verify the refactored reports work correctly

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Reports Refactoring - Test Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Change to frontend directory
$frontendDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -Path $frontendDir

$testsPassed = 0
$testsFailed = 0

# Test 1: TypeScript Compilation
Write-Host "[1/3] Running TypeScript Compilation Check..." -ForegroundColor Yellow
Write-Host ""

$compileResult = npx tsc --noEmit 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ TypeScript compilation passed" -ForegroundColor Green
    $testsPassed++
}
else {
    Write-Host "❌ TypeScript compilation failed" -ForegroundColor Red
    Write-Host $compileResult -ForegroundColor Red
    $testsFailed++
}
Write-Host ""

# Test 2: Unit Tests
Write-Host "[2/3] Running Unit Tests..." -ForegroundColor Yellow
Write-Host ""

$env:CI = "true"
$testResult = npm test -- --testPathPattern="reports" --watchAll=false --passWithNoTests 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Unit tests passed" -ForegroundColor Green
    $testsPassed++
}
else {
    Write-Host "❌ Unit tests failed" -ForegroundColor Red
    Write-Host $testResult -ForegroundColor Red
    $testsFailed++
}
Write-Host ""

# Test 3: Build Test
Write-Host "[3/3] Running Production Build Test..." -ForegroundColor Yellow
Write-Host ""

$buildResult = npm run build 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Production build passed" -ForegroundColor Green
    $testsPassed++
}
else {
    Write-Host "❌ Production build failed" -ForegroundColor Red
    Write-Host $buildResult -ForegroundColor Red
    $testsFailed++
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Tests Passed: $testsPassed" -ForegroundColor Green
Write-Host "Tests Failed: $testsFailed" -ForegroundColor Red
Write-Host ""

if ($testsFailed -eq 0) {
    Write-Host "🎉 All tests passed! Reports are ready for deployment." -ForegroundColor Green
    exit 0
}
else {
    Write-Host "⚠️  Some tests failed. Please review the errors above." -ForegroundColor Yellow
    exit 1
}
