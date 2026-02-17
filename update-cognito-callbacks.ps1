# Update AWS Cognito User Pool Client with GitHub Pages callback URLs
# Run this script to add GitHub Pages URLs to your Cognito configuration

$UserPoolId = "eu-west-1_Hdp40eWmu"
$ClientId = "66tp0087h9tfbstggonnu5aghp"
$Region = "eu-west-1"

Write-Host "Updating Cognito User Pool Client..." -ForegroundColor Cyan

# Get current client configuration
Write-Host "Fetching current configuration..." -ForegroundColor Yellow
$currentConfig = aws cognito-idp describe-user-pool-client `
    --user-pool-id $UserPoolId `
    --client-id $ClientId `
    --region $Region `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Failed to fetch Cognito configuration. Make sure AWS CLI is configured." -ForegroundColor Red
    exit 1
}

# Add GitHub Pages URLs to callback and logout URLs
$callbackUrls = @(
    "http://localhost:3000/",
    "https://petergeers.github.io/myAdmin/"
)

$logoutUrls = @(
    "http://localhost:3000/",
    "https://petergeers.github.io/myAdmin/"
)

Write-Host "Updating callback and logout URLs..." -ForegroundColor Yellow

# Update the client
aws cognito-idp update-user-pool-client `
    --user-pool-id $UserPoolId `
    --client-id $ClientId `
    --region $Region `
    --callback-urls $callbackUrls `
    --logout-urls $logoutUrls `
    --allowed-o-auth-flows "code" "implicit" `
    --allowed-o-auth-scopes "openid" "email" "profile" `
    --allowed-o-auth-flows-user-pool-client `
    --supported-identity-providers "COGNITO"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Successfully updated Cognito User Pool Client!" -ForegroundColor Green
    Write-Host "`nCallback URLs:" -ForegroundColor Cyan
    $callbackUrls | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
    Write-Host "`nLogout URLs:" -ForegroundColor Cyan
    $logoutUrls | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
    Write-Host "`n🎉 Your frontend at https://petergeers.github.io/myAdmin/ is now ready!" -ForegroundColor Green
} else {
    Write-Host "`n❌ Failed to update Cognito configuration" -ForegroundColor Red
    Write-Host "Please update manually in AWS Console" -ForegroundColor Yellow
    exit 1
}
