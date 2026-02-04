# Simple Country Report Endpoint Test
# Put your token in token.txt first

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Country Report Endpoint Test" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check for token file
if (-not (Test-Path "token.txt")) {
    Write-Host "Creating token.txt file..." -ForegroundColor Yellow
    Write-Host "Please paste your token and save the file.`n" -ForegroundColor Yellow
    
    # Create empty token file
    "" | Out-File -FilePath "token.txt" -Encoding UTF8
    
    # Open in notepad
    notepad token.txt
    
    Write-Host "`nWaiting for you to save token.txt..." -ForegroundColor Yellow
    Write-Host "Press Enter when done..." -ForegroundColor Yellow
    Read-Host
}

# Read token
$token = Get-Content "token.txt" -Raw
$token = $token.Trim()

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "`n✗ No token found in token.txt`n" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Token loaded from token.txt`n" -ForegroundColor Green

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

# Test the endpoint
Write-Host "Testing endpoint..." -ForegroundColor Yellow
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
    
    # Clean up token file
    Write-Host "Cleaning up token.txt for security..." -ForegroundColor Yellow
    Remove-Item "token.txt" -ErrorAction SilentlyContinue
    
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
