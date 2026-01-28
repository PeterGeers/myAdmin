# Test script to demonstrate color coding in build output

Write-Host "`n=== Testing Color Coding ===" -ForegroundColor Cyan
Write-Host ""

# Simulate npm warnings (should be yellow/orange)
Write-Host "npm warn deprecated package@1.0.0: This package is deprecated" -ForegroundColor Yellow
Write-Host "npm WARN optional SKIPPING OPTIONAL DEPENDENCY" -ForegroundColor Yellow
Write-Host "warning: React Hook useEffect has a missing dependency" -ForegroundColor Yellow

Write-Host ""

# Simulate errors (should be red)
Write-Host "error: 'availableAdmins' is assigned a value but never used" -ForegroundColor Red
Write-Host "ERROR: Build failed" -ForegroundColor Red
Write-Host "✗ Test failed" -ForegroundColor Red

Write-Host ""

# Simulate success (should be green)
Write-Host "PASS src/components/PDFValidation.test.tsx" -ForegroundColor Green
Write-Host "✓ All tests passed" -ForegroundColor Green
Write-Host "SUCCESS: Build completed" -ForegroundColor Green

Write-Host ""

# Simulate test summary (should be cyan)
Write-Host "Test Suites: 41 passed, 41 total" -ForegroundColor Cyan
Write-Host "Tests:       439 passed, 439 total" -ForegroundColor Cyan
Write-Host "Snapshots:   0 total" -ForegroundColor Cyan
Write-Host "Time:        52.219 s" -ForegroundColor Cyan

Write-Host ""

# Simulate coverage table (should be cyan)
Write-Host "File                                | % Stmts | % Branch | % Funcs | % Lines |" -ForegroundColor Cyan
Write-Host "------------------------------------|---------|----------|---------|---------|" -ForegroundColor Cyan
Write-Host "All files                           |   13.61 |     9.22 |   10.63 |   14.06 |" -ForegroundColor White

Write-Host "`n=== Color Test Complete ===" -ForegroundColor Cyan
