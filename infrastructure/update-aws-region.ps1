# Update AWS CLI Default Region to eu-west-1

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          Update AWS CLI Region to eu-west-1               ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$configFile = "$env:USERPROFILE\.aws\config"

# Check if config file exists
if (-not (Test-Path $configFile)) {
    Write-Host "✗ AWS config file not found: $configFile" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run: aws configure" -ForegroundColor Yellow
    exit 1
}

# Read current config
Write-Host "Current AWS Configuration:" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Get-Content $configFile | ForEach-Object {
    if ($_ -match "region\s*=\s*(.+)") {
        $currentRegion = $matches[1].Trim()
        Write-Host "  Region: $currentRegion" -ForegroundColor White
    }
}
Write-Host ""

# Check current region
$currentRegion = aws configure get region
Write-Host "Current default region: $currentRegion" -ForegroundColor Cyan
Write-Host ""

if ($currentRegion -eq "eu-west-1") {
    Write-Host "✓ Already configured for eu-west-1!" -ForegroundColor Green
    Write-Host ""
    
    # Show resources in eu-west-1
    Write-Host "Your resources in eu-west-1:" -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
    aws cognito-idp list-user-pools --max-results 10 --region eu-west-1 --query 'UserPools[*].[Name,Id]' --output table
    Write-Host ""
    exit 0
}

# Confirm change
Write-Host "This will change your AWS CLI default region from:" -ForegroundColor Yellow
Write-Host "  $currentRegion → eu-west-1" -ForegroundColor White
Write-Host ""
Write-Host "Why eu-west-1?" -ForegroundColor Cyan
Write-Host "  • Your h-dcn project is in eu-west-1" -ForegroundColor White
Write-Host "  • Your existing Cognito pools are in eu-west-1" -ForegroundColor White
Write-Host "  • Better consistency across projects" -ForegroundColor White
Write-Host "  • Lower latency for Netherlands/Belgium" -ForegroundColor White
Write-Host ""
Write-Host "Impact:" -ForegroundColor Cyan
Write-Host "  ✓ Zero downtime" -ForegroundColor Green
Write-Host "  ✓ Zero cost impact" -ForegroundColor Green
Write-Host "  ✓ Zero data migration" -ForegroundColor Green
Write-Host "  ✓ Existing resources unchanged" -ForegroundColor Green
Write-Host ""

$confirm = Read-Host "Change default region to eu-west-1? (yes/no)"

if ($confirm -ne "yes") {
    Write-Host "Cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Updating AWS CLI configuration..." -ForegroundColor Yellow

# Backup current config
$backupFile = "$configFile.backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
Copy-Item $configFile $backupFile
Write-Host "✓ Backup created: $backupFile" -ForegroundColor Green

# Update region
$content = Get-Content $configFile
$newContent = $content -replace 'region\s*=\s*.+', 'region = eu-west-1'
Set-Content -Path $configFile -Value $newContent

Write-Host "✓ Configuration updated" -ForegroundColor Green
Write-Host ""

# Verify change
$newRegion = aws configure get region
Write-Host "New default region: $newRegion" -ForegroundColor Cyan
Write-Host ""

if ($newRegion -eq "eu-west-1") {
    Write-Host "✓ Successfully changed to eu-west-1!" -ForegroundColor Green
    Write-Host ""
    
    # Show resources in eu-west-1
    Write-Host "Your resources in eu-west-1:" -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
    aws cognito-idp list-user-pools --max-results 10 --region eu-west-1 --query 'UserPools[*].[Name,Id]' --output table
    Write-Host ""
    
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║          Configuration Updated Successfully                ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Deploy myAdmin Cognito:" -ForegroundColor Cyan
    Write-Host "     .\infrastructure\setup-cognito.ps1 -AdminEmail 'your-email@example.com'" -ForegroundColor White
    Write-Host ""
    Write-Host "  2. All new resources will be created in eu-west-1" -ForegroundColor Cyan
    Write-Host ""
}
else {
    Write-Host "✗ Failed to update region" -ForegroundColor Red
    Write-Host "  Restoring backup..." -ForegroundColor Yellow
    Copy-Item $backupFile $configFile -Force
    Write-Host "✓ Backup restored" -ForegroundColor Green
    exit 1
}

exit 0
