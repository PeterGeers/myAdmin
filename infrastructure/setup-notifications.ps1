# AWS Notifications Setup Script for Windows
# This script helps set up AWS SNS notifications for myAdmin

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "AWS Notifications Setup for myAdmin" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Terraform is in PATH, if not, ask for location
$terraformCmd = "terraform"
try {
    $null = & $terraformCmd version 2>&1
    $terraformVersion = & $terraformCmd version 2>&1 | Select-Object -First 1
    Write-Host "✓ Terraform is installed" -ForegroundColor Green
    Write-Host "  $terraformVersion" -ForegroundColor Gray
}
catch {
    Write-Host "✗ Terraform is not in PATH" -ForegroundColor Yellow
    Write-Host ""
    $terraformPath = Read-Host "Enter full path to terraform.exe"
    
    if (Test-Path $terraformPath) {
        $terraformCmd = $terraformPath
        Write-Host "✓ Using Terraform at: $terraformPath" -ForegroundColor Green
    }
    else {
        Write-Host "✗ Terraform not found at: $terraformPath" -ForegroundColor Red
        Write-Host "Please install Terraform or provide correct path" -ForegroundColor Yellow
        exit 1
    }
}

# Check if AWS CLI is installed
try {
    $awsVersion = aws --version 2>&1
    Write-Host "✓ AWS CLI is installed" -ForegroundColor Green
    Write-Host "  $awsVersion" -ForegroundColor Gray
}
catch {
    Write-Host "✗ AWS CLI is not installed" -ForegroundColor Red
    Write-Host "Please install AWS CLI first:" -ForegroundColor Yellow
    Write-Host "  https://aws.amazon.com/cli/" -ForegroundColor Yellow
    exit 1
}

# Check AWS credentials
Write-Host ""
Write-Host "Checking AWS credentials..." -ForegroundColor Cyan
try {
    $identity = aws sts get-caller-identity 2>&1 | ConvertFrom-Json
    Write-Host "✓ AWS credentials are configured" -ForegroundColor Green
    Write-Host "  Account: $($identity.Account)" -ForegroundColor Gray
    Write-Host "  User: $($identity.Arn)" -ForegroundColor Gray
}
catch {
    Write-Host "✗ AWS credentials are not configured" -ForegroundColor Red
    Write-Host "Please run: aws configure" -ForegroundColor Yellow
    exit 1
}

# Get user input
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Configuration" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$AWS_REGION = Read-Host "Enter your AWS region [eu-west-1]"
if ([string]::IsNullOrWhiteSpace($AWS_REGION)) {
    $AWS_REGION = "eu-west-1"
}

$KEY_NAME = Read-Host "Enter your EC2 key pair name"
if ([string]::IsNullOrWhiteSpace($KEY_NAME)) {
    Write-Host "✗ Key pair name is required" -ForegroundColor Red
    exit 1
}

$ADMIN_EMAIL = Read-Host "Enter admin email address [peter@pgeers.nl]"
if ([string]::IsNullOrWhiteSpace($ADMIN_EMAIL)) {
    $ADMIN_EMAIL = "peter@pgeers.nl"
}

$DOMAIN_NAME = Read-Host "Enter domain name [admin.pgeers.nl]"
if ([string]::IsNullOrWhiteSpace($DOMAIN_NAME)) {
    $DOMAIN_NAME = "admin.pgeers.nl"
}

# Create terraform.tfvars
Write-Host ""
Write-Host "Creating terraform.tfvars..." -ForegroundColor Cyan

$tfvarsContent = @"
# AWS Configuration
aws_region = "$AWS_REGION"
key_name   = "$KEY_NAME"
domain_name = "$DOMAIN_NAME"

# Notification Configuration
admin_email = "$ADMIN_EMAIL"

# Optional: Add more email addresses
additional_notification_emails = []
"@

Set-Content -Path "terraform.tfvars" -Value $tfvarsContent -Encoding UTF8
Write-Host "✓ terraform.tfvars created" -ForegroundColor Green

# Initialize Terraform
Write-Host ""
Write-Host "Initializing Terraform..." -ForegroundColor Cyan
& $terraformCmd init

# Plan
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Terraform Plan" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
& $terraformCmd plan

# Ask for confirmation
Write-Host ""
$CONFIRM = Read-Host "Do you want to apply these changes? (yes/no)"
if ($CONFIRM -ne "yes") {
    Write-Host "Setup cancelled" -ForegroundColor Yellow
    exit 0
}

# Apply
Write-Host ""
Write-Host "Applying Terraform configuration..." -ForegroundColor Cyan
& $terraformCmd apply -auto-approve

# Get outputs
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

try {
    $SNS_TOPIC_ARN = & $terraformCmd output -raw sns_topic_arn 2>$null
    Write-Host "✓ SNS Topic created" -ForegroundColor Green
    Write-Host "  ARN: $SNS_TOPIC_ARN" -ForegroundColor Gray
}
catch {
    $SNS_TOPIC_ARN = ""
}

try {
    $INSTANCE_IP = & $terraformCmd output -raw instance_ip 2>$null
    Write-Host "✓ EC2 Instance ready" -ForegroundColor Green
    Write-Host "  IP: $INSTANCE_IP" -ForegroundColor Gray
}
catch {
    $INSTANCE_IP = ""
}

# Instructions
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. " -NoNewline
Write-Host "IMPORTANT:" -ForegroundColor Yellow -NoNewline
Write-Host " Check your email ($ADMIN_EMAIL)"
Write-Host "   Look for 'AWS Notification - Subscription Confirmation'"
Write-Host "   Click the confirmation link"
Write-Host ""
Write-Host "2. Test the notification:" -ForegroundColor Cyan
Write-Host "   aws sns publish ``" -ForegroundColor Gray
Write-Host "     --topic-arn $SNS_TOPIC_ARN ``" -ForegroundColor Gray
Write-Host "     --message 'Test from myAdmin' ``" -ForegroundColor Gray
Write-Host "     --subject 'Test Notification' ``" -ForegroundColor Gray
Write-Host "     --region $AWS_REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Configure your application:" -ForegroundColor Cyan
Write-Host "   Add to backend/.env:" -ForegroundColor Gray
Write-Host "   SNS_TOPIC_ARN=$SNS_TOPIC_ARN" -ForegroundColor Gray
Write-Host "   AWS_REGION=$AWS_REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Install boto3 on your EC2 instance:" -ForegroundColor Cyan
Write-Host "   ssh -i $KEY_NAME.pem ec2-user@$INSTANCE_IP" -ForegroundColor Gray
Write-Host "   cd /path/to/myAdmin/backend" -ForegroundColor Gray
Write-Host "   source venv/bin/activate" -ForegroundColor Gray
Write-Host "   pip install boto3" -ForegroundColor Gray
Write-Host ""
Write-Host "Setup script completed!" -ForegroundColor Green
Write-Host ""
