# Test Country Report Endpoint
# This script tests the /api/bnb/generate-country-report endpoint

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Country Report Endpoint Test" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check if backend is running
Write-Host "Checking if backend is running..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5000/health" -Method GET -TimeoutSec 5 -ErrorAction Stop
    Write-Host "✓ Backend is running`n" -ForegroundColor Green
}
catch {
    Write-Host "✗ Backend is not running!" -ForegroundColor Red
    Write-Host "  Please start backend: docker-compose up -d`n" -ForegroundColor Yellow
    exit 1
}

# Prompt for token
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Get your JWT token:" -ForegroundColor Cyan
Write-Host "1. Open http://localhost:3000 in browser" -ForegroundColor White
Write-Host "2. Login if needed" -ForegroundColor White
Write-Host "3. Press F12 → Application → Local Storage" -ForegroundColor White
Write-Host "4. Copy the 'idToken' value" -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor Cyan

$token = Read-Host "Paste your idToken here"

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "`n✗ No token provided. Exiting.`n" -ForegroundColor Red
    exit 1
}

# Test the endpoint
Write-Host "`nTesting endpoint..." -ForegroundColor Yellow
Write-Host "GET http://localhost:5000/api/bnb/generate-country-report`n" -ForegroundColor Gray

try {
    $headers = @{
        "Authorization" = "Bearer $token"
    }
    
    $outputFile = "country_report_test.html"
    
    $response = Invoke-WebRequest `
        -Uri "http://localhost:5000/api/bnb/generate-country-report" `
        -Method GET `
        -Headers $headers `
        -OutFile $outputFile `
        -PassThru
    
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✓ SUCCESS!" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green
    
    Write-Host "Response Details:" -ForegroundColor Cyan
    Write-Host "  Status Code: $($response.StatusCode)" -ForegroundColor White
    Write-Host "  Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor White
    Write-Host "  Content-Disposition: $($response.Headers['Content-Disposition'])" -ForegroundColor White
    Write-Host "  Content Length: $($response.RawContentLength) bytes`n" -ForegroundColor White
    
    Write-Host "File saved to: $outputFile" -ForegroundColor Green
    Write-Host "Opening file in browser...`n" -ForegroundColor Yellow
    
    Start-Process $outputFile
    
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Test completed successfully!" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green
    
}
catch {
    Write-Host "`n========================================" -ForegroundColor Red
    Write-Host "✗ TEST FAILED" -ForegroundColor Red
    Write-Host "========================================`n" -ForegroundColor Red
    
    Write-Host "Error Details:" -ForegroundColor Yellow
    Write-Host "  Status Code: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor White
    Write-Host "  Status Description: $($_.Exception.Response.StatusDescription)" -ForegroundColor White
    Write-Host "  Error Message: $($_.Exception.Message)`n" -ForegroundColor White
    
    if ($_.Exception.Response.StatusCode.value__ -eq 401) {
        Write-Host "Token may be expired or invalid." -ForegroundColor Yellow
        Write-Host "Please get a fresh token from the frontend.`n" -ForegroundColor Yellow
    }
    
    exit 1
}
