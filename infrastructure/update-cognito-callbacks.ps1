# Update Cognito User Pool Client Callback URLs
# This script updates the callback URLs for the Cognito User Pool Client

Write-Host "Updating Cognito User Pool Client Callback URLs..." -ForegroundColor Cyan

# Load environment variables
$envFile = Join-Path $PSScriptRoot ".." "backend" ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

$userPoolId = $env:COGNITO_USER_POOL_ID
$clientId = $env:COGNITO_CLIENT_ID
$region = $env:AWS_REGION

if (-not $userPoolId -or -not $clientId) {
    Write-Host "ERROR: COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID not found in environment" -ForegroundColor Red
    Write-Host "Please ensure backend/.env has these variables set" -ForegroundColor Yellow
    exit 1
}

Write-Host "User Pool ID: $userPoolId" -ForegroundColor Green
Write-Host "Client ID: $clientId" -ForegroundColor Green
Write-Host "Region: $region" -ForegroundColor Green

# Get current client configuration
Write-Host "`nFetching current client configuration..." -ForegroundColor Cyan
$currentConfig = aws cognito-idp describe-user-pool-client `
    --user-pool-id $userPoolId `
    --client-id $clientId `
    --region $region `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to fetch client configuration" -ForegroundColor Red
    exit 1
}

Write-Host "Current Callback URLs:" -ForegroundColor Yellow
$currentConfig.UserPoolClient.CallbackURLs | ForEach-Object { Write-Host "  - $_" }

# Update with new callback URLs
Write-Host "`nUpdating callback URLs..." -ForegroundColor Cyan

$callbackUrls = @(
    "http://localhost:3000/",
    "http://localhost:3000/callback",
    "http://localhost:5000/",
    "http://localhost:5000/callback"
)

$logoutUrls = @(
    "http://localhost:3000/",
    "http://localhost:3000/login",
    "http://localhost:5000/",
    "http://localhost:5000/login"
)

aws cognito-idp update-user-pool-client `
    --user-pool-id $userPoolId `
    --client-id $clientId `
    --region $region `
    --callback-urls $callbackUrls `
    --logout-urls $logoutUrls `
    --allowed-o-auth-flows "code" `
    --allowed-o-auth-scopes "openid" "email" "profile" `
    --allowed-o-auth-flows-user-pool-client `
    --supported-identity-providers "COGNITO"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSUCCESS: Callback URLs updated!" -ForegroundColor Green
    Write-Host "`nNew Callback URLs:" -ForegroundColor Yellow
    $callbackUrls | ForEach-Object { Write-Host "  - $_" -ForegroundColor Green }
    Write-Host "`nNew Logout URLs:" -ForegroundColor Yellow
    $logoutUrls | ForEach-Object { Write-Host "  - $_" -ForegroundColor Green }
} else {
    Write-Host "`nERROR: Failed to update callback URLs" -ForegroundColor Red
    exit 1
}
