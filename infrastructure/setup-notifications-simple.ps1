# AWS Notifications Setup Script for Windows
# Run this outside of Python virtual environment

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "AWS Notifications Setup for myAdmin" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Check AWS CLI
Write-Host "Checking prerequisites..." -ForegroundColor Cyan
try {
    $awsVersion = aws --version 2>&1
    Write-Host "OK - AWS CLI is installed" -ForegroundColor Green
}
catch {
    Write-Host "ERROR - AWS CLI is not installed" -ForegroundColor Red
    Write-Host "Please install AWS CLI first: https://aws.amazon.com/cli/" -ForegroundColor Yellow
    exit 1
}

# Check AWS credentials
try {
    $identity = aws sts get-caller-identity 2>&1 | ConvertFrom-Json
    Write-Host "OK - AWS credentials configured" -ForegroundColor Green
    Write-Host "  Account: $($identity.Account)" -ForegroundColor Gray
}
catch {
    Write-Host "ERROR - AWS credentials not configured" -ForegroundColor Red
    Write-Host "Please run: aws configure" -ForegroundColor Yellow
    exit 1
}

# Get configuration
Write-Host ""
Write-Host "Configuration" -ForegroundColor Cyan
Write-Host "=============" -ForegroundColor Cyan
Write-Host ""

$AWS_REGION = Read-Host "AWS region [eu-west-1]"
if ([string]::IsNullOrWhiteSpace($AWS_REGION)) { $AWS_REGION = "eu-west-1" }

$KEY_NAME = Read-Host "EC2 key pair name (required)"
if ([string]::IsNullOrWhiteSpace($KEY_NAME)) {
    Write-Host "ERROR - Key pair name is required" -ForegroundColor Red
    exit 1
}

$ADMIN_EMAIL = Read-Host "Admin email [peter@pgeers.nl]"
if ([string]::IsNullOrWhiteSpace($ADMIN_EMAIL)) { $ADMIN_EMAIL = "peter@pgeers.nl" }

$DOMAIN_NAME = Read-Host "Domain name [admin.pgeers.nl]"
if ([string]::IsNullOrWhiteSpace($DOMAIN_NAME)) { $DOMAIN_NAME = "admin.pgeers.nl" }

# Create terraform.tfvars
Write-Host ""
Write-Host "Creating configuration..." -ForegroundColor Cyan

$tfvarsContent = @"
aws_region = "$AWS_REGION"
key_name   = "$KEY_NAME"
domain_name = "$DOMAIN_NAME"
admin_email = "$ADMIN_EMAIL"
additional_notification_emails = []
"@

Set-Content -Path "terraform.tfvars" -Value $tfvarsContent -Encoding UTF8
Write-Host "OK - terraform.tfvars created" -ForegroundColor Green

# Initialize Terraform
Write-Host ""
Write-Host "Initializing Terraform..." -ForegroundColor Cyan
terraform init

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR - Terraform init failed" -ForegroundColor Red
    exit 1
}

# Plan
Write-Host ""
Write-Host "Planning changes..." -ForegroundColor Cyan
terraform plan

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR - Terraform plan failed" -ForegroundColor Red
    exit 1
}

# Confirm
Write-Host ""
$CONFIRM = Read-Host "Apply these changes? (yes/no)"
if ($CONFIRM -ne "yes") {
    Write-Host "Setup cancelled" -ForegroundColor Yellow
    exit 0
}

# Apply
Write-Host ""
Write-Host "Applying configuration..." -ForegroundColor Cyan
terraform apply -auto-approve

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR - Terraform apply failed" -ForegroundColor Red
    exit 1
}

# Get outputs
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$SNS_TOPIC_ARN = terraform output -raw sns_topic_arn 2>$null
$INSTANCE_IP = terraform output -raw instance_ip 2>$null

if ($SNS_TOPIC_ARN) {
    Write-Host "SNS Topic ARN:" -ForegroundColor Cyan
    Write-Host "  $SNS_TOPIC_ARN" -ForegroundColor White
}

if ($INSTANCE_IP) {
    Write-Host "EC2 Instance IP:" -ForegroundColor Cyan
    Write-Host "  $INSTANCE_IP" -ForegroundColor White
}

# Next steps
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "==========" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Check email: $ADMIN_EMAIL" -ForegroundColor White
Write-Host "   Click the AWS confirmation link" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Test notification:" -ForegroundColor White
Write-Host "   aws sns publish --topic-arn $SNS_TOPIC_ARN --message Test --subject Test --region $AWS_REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Add to backend/.env:" -ForegroundColor White
Write-Host "   SNS_TOPIC_ARN=$SNS_TOPIC_ARN" -ForegroundColor Gray
Write-Host "   AWS_REGION=$AWS_REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "Setup completed successfully!" -ForegroundColor Green
