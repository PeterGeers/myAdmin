# Setup AWS Cognito User Pool for myAdmin
# This script deploys Cognito using Terraform

param(
    [string]$AdminEmail = "peter@pgeers.nl",
    [switch]$Destroy = $false,
    [switch]$Plan = $false
)

$ErrorActionPreference = "Stop"

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          AWS Cognito Setup for myAdmin                     ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if Terraform is installed
Write-Host "Checking prerequisites..." -ForegroundColor Yellow
try {
    $tfVersion = terraform version
    Write-Host "✓ Terraform installed: $($tfVersion[0])" -ForegroundColor Green
}
catch {
    Write-Host "✗ Terraform not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Terraform:" -ForegroundColor Yellow
    Write-Host "  .\infrastructure\install-terraform.ps1" -ForegroundColor White
    exit 1
}

# Check AWS CLI
try {
    $awsVersion = aws --version
    Write-Host "✓ AWS CLI installed: $awsVersion" -ForegroundColor Green
}
catch {
    Write-Host "✗ AWS CLI not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Install AWS CLI:" -ForegroundColor Yellow
    Write-Host "  .\infrastructure\setup-aws-cli-only.ps1" -ForegroundColor White
    exit 1
}

# Check AWS credentials
Write-Host ""
Write-Host "Checking AWS credentials..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity --output json | ConvertFrom-Json
    Write-Host "✓ AWS credentials configured" -ForegroundColor Green
    Write-Host "  Account: $($identity.Account)" -ForegroundColor Gray
    Write-Host "  User: $($identity.Arn)" -ForegroundColor Gray
}
catch {
    Write-Host "✗ AWS credentials not configured" -ForegroundColor Red
    Write-Host ""
    Write-Host "Configure AWS credentials:" -ForegroundColor Yellow
    Write-Host "  aws configure" -ForegroundColor White
    exit 1
}

Write-Host ""

# Change to infrastructure directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Initialize Terraform
Write-Host "Initializing Terraform..." -ForegroundColor Yellow
terraform init

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Terraform initialization failed" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Terraform initialized" -ForegroundColor Green
Write-Host ""

# Handle destroy
if ($Destroy) {
    Write-Host "⚠ WARNING: This will DESTROY the Cognito User Pool!" -ForegroundColor Red
    Write-Host "  All users and configurations will be permanently deleted!" -ForegroundColor Red
    Write-Host ""
    $confirm = Read-Host "Type 'yes' to confirm destruction"
    
    if ($confirm -ne "yes") {
        Write-Host "Cancelled" -ForegroundColor Yellow
        exit 0
    }
    
    Write-Host ""
    Write-Host "Destroying Cognito infrastructure..." -ForegroundColor Red
    terraform destroy -auto-approve
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✓ Cognito infrastructure destroyed" -ForegroundColor Green
    }
    else {
        Write-Host "✗ Destruction failed" -ForegroundColor Red
        exit 1
    }
    
    exit 0
}

# Plan or Apply
if ($Plan) {
    Write-Host "Planning Cognito infrastructure..." -ForegroundColor Yellow
    terraform plan
}
else {
    Write-Host "Deploying Cognito infrastructure..." -ForegroundColor Yellow
    Write-Host ""
    
    # Apply Terraform
    terraform apply -auto-approve
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Deployment failed" -ForegroundColor Red
        exit 1
    }
    
    Write-Host ""
    Write-Host "✓ Cognito infrastructure deployed!" -ForegroundColor Green
    Write-Host ""
    
    # Get outputs
    Write-Host "Retrieving configuration..." -ForegroundColor Yellow
    $userPoolId = terraform output -raw cognito_user_pool_id
    $clientId = terraform output -raw cognito_client_id
    $clientSecret = terraform output -raw cognito_client_secret
    $domain = terraform output -raw cognito_domain
    $hostedUiUrl = terraform output -raw cognito_hosted_ui_url
    
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║          Cognito Configuration                             ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "User Pool ID:     $userPoolId" -ForegroundColor Cyan
    Write-Host "Client ID:        $clientId" -ForegroundColor Cyan
    Write-Host "Client Secret:    $($clientSecret.Substring(0, 20))..." -ForegroundColor Cyan
    Write-Host "Domain:           $domain" -ForegroundColor Cyan
    Write-Host "Hosted UI URL:    $hostedUiUrl" -ForegroundColor Cyan
    Write-Host ""
    
    # Update .env files
    Write-Host "Updating .env files..." -ForegroundColor Yellow
    
    $repoRoot = Split-Path -Parent $scriptDir
    $envFiles = @(
        "$repoRoot\.env",
        "$repoRoot\backend\.env",
        "$repoRoot\frontend\.env"
    )
    
    foreach ($envFile in $envFiles) {
        if (Test-Path $envFile) {
            $content = Get-Content $envFile
            
            # Update or add Cognito variables
            $content = $content -replace 'COGNITO_USER_POOL_ID=.*', "COGNITO_USER_POOL_ID=$userPoolId"
            $content = $content -replace 'COGNITO_CLIENT_ID=.*', "COGNITO_CLIENT_ID=$clientId"
            $content = $content -replace 'COGNITO_CLIENT_SECRET=.*', "COGNITO_CLIENT_SECRET=$clientSecret"
            
            Set-Content -Path $envFile -Value $content
            Write-Host "  ✓ Updated: $envFile" -ForegroundColor Green
        }
    }
    
    Write-Host ""
    
    # Create admin user if email provided
    if ($AdminEmail) {
        Write-Host "Creating admin user..." -ForegroundColor Yellow
        
        try {
            # Create user
            aws cognito-idp admin-create-user `
                --user-pool-id $userPoolId `
                --username $AdminEmail `
                --user-attributes Name=email, Value=$AdminEmail Name=email_verified, Value=true Name=name, Value="Administrator" `
                --message-action SUPPRESS
            
            # Add to Administrators group
            aws cognito-idp admin-add-user-to-group `
                --user-pool-id $userPoolId `
                --username $AdminEmail `
                --group-name Administrators
            
            # Set permanent password
            Write-Host ""
            Write-Host "Set password for admin user:" -ForegroundColor Cyan
            $password = Read-Host "Enter password (min 8 chars, uppercase, lowercase, number, symbol)" -AsSecureString
            $passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
            )
            
            aws cognito-idp admin-set-user-password `
                --user-pool-id $userPoolId `
                --username $AdminEmail `
                --password $passwordPlain `
                --permanent
            
            Write-Host ""
            Write-Host "✓ Admin user created: $AdminEmail" -ForegroundColor Green
            Write-Host "  Group: Administrators" -ForegroundColor Gray
        }
        catch {
            Write-Host "⚠ Failed to create admin user: $_" -ForegroundColor Yellow
            Write-Host "  You can create users manually in AWS Console" -ForegroundColor Yellow
        }
    }
    
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║          Next Steps                                        ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "1. Test the Hosted UI:" -ForegroundColor White
    Write-Host "   $hostedUiUrl/login?client_id=$clientId&response_type=code&redirect_uri=http://localhost:3000/callback" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "2. Create users:" -ForegroundColor White
    Write-Host "   • AWS Console: https://console.aws.amazon.com/cognito/" -ForegroundColor Cyan
    Write-Host "   • Or use: .\infrastructure\create-cognito-user.ps1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "3. Update your application:" -ForegroundColor White
    Write-Host "   • .env files have been updated automatically" -ForegroundColor Cyan
    Write-Host "   • Restart your application to use new credentials" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "4. Configure callback URLs:" -ForegroundColor White
    Write-Host "   • Update cognito.tf with your Railway URL" -ForegroundColor Cyan
    Write-Host "   • Run: terraform apply" -ForegroundColor Cyan
    Write-Host ""
}

exit 0
