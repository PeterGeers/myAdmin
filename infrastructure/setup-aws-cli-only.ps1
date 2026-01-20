# AWS Notifications Setup - AWS CLI Only
# This script uses only AWS CLI (no Terraform)

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "AWS Notifications Setup (CLI Only)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$REGION = "eu-west-1"
$TOPIC_NAME = "myadmin-notifications"
$EMAIL = "peter@pgeers.nl"

Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Region: $REGION" -ForegroundColor Gray
Write-Host "  Topic: $TOPIC_NAME" -ForegroundColor Gray
Write-Host "  Email: $EMAIL" -ForegroundColor Gray
Write-Host ""

# Check credentials
Write-Host "Checking AWS credentials..." -ForegroundColor Cyan
$identity = aws sts get-caller-identity | ConvertFrom-Json
Write-Host "OK - Logged in as: $($identity.Arn)" -ForegroundColor Green
Write-Host ""

# List existing key pairs
Write-Host "Your existing EC2 key pairs:" -ForegroundColor Cyan
aws ec2 describe-key-pairs --region $REGION --query 'KeyPairs[*].KeyName' --output table
Write-Host ""

$createKey = Read-Host "Do you want to create a new key pair? (yes/no)"
if ($createKey -eq "yes") {
    $keyName = Read-Host "Enter key pair name [myadmin-key]"
    if ([string]::IsNullOrWhiteSpace($keyName)) { $keyName = "myadmin-key" }
    
    Write-Host "Creating key pair: $keyName..." -ForegroundColor Cyan
    
    # Create .ssh directory if it doesn't exist
    $sshDir = "$env:USERPROFILE\.ssh"
    if (-not (Test-Path $sshDir)) {
        New-Item -ItemType Directory -Path $sshDir | Out-Null
    }
    
    $keyPath = "$sshDir\$keyName.pem"
    
    try {
        aws ec2 create-key-pair `
            --key-name $keyName `
            --region $REGION `
            --query 'KeyMaterial' `
            --output text | Out-File -Encoding ascii -FilePath $keyPath
        
        Write-Host "OK - Key pair created" -ForegroundColor Green
        Write-Host "  Name: $keyName" -ForegroundColor Gray
        Write-Host "  File: $keyPath" -ForegroundColor Gray
    }
    catch {
        Write-Host "ERROR - Failed to create key pair" -ForegroundColor Red
        Write-Host "  It may already exist" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Creating SNS Topic..." -ForegroundColor Cyan

# Create SNS Topic
try {
    $topicArn = aws sns create-topic `
        --name $TOPIC_NAME `
        --region $REGION `
        --query 'TopicArn' `
        --output text
    
    Write-Host "OK - SNS Topic created" -ForegroundColor Green
    Write-Host "  ARN: $topicArn" -ForegroundColor Gray
}
catch {
    Write-Host "ERROR - Failed to create topic" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Subscribing email to topic..." -ForegroundColor Cyan

# Subscribe email
try {
    $subscriptionArn = aws sns subscribe `
        --topic-arn $topicArn `
        --protocol email `
        --notification-endpoint $EMAIL `
        --region $REGION `
        --query 'SubscriptionArn' `
        --output text
    
    Write-Host "OK - Email subscription created" -ForegroundColor Green
    Write-Host "  Email: $EMAIL" -ForegroundColor Gray
}
catch {
    Write-Host "ERROR - Failed to subscribe email" -ForegroundColor Red
}

# Show credentials location
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Your AWS Files" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "AWS Credentials:" -ForegroundColor Yellow
Write-Host "  $env:USERPROFILE\.aws\credentials" -ForegroundColor Gray
Write-Host "  $env:USERPROFILE\.aws\config" -ForegroundColor Gray
Write-Host ""
Write-Host "SSH Keys:" -ForegroundColor Yellow
Write-Host "  $env:USERPROFILE\.ssh\" -ForegroundColor Gray
Write-Host ""

# Next steps
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. IMPORTANT: Check your email ($EMAIL)" -ForegroundColor Yellow
Write-Host "   Click the AWS confirmation link" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Test notification:" -ForegroundColor White
Write-Host "   aws sns publish --topic-arn $topicArn --message 'Test' --subject 'Test' --region $REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Add to backend/.env:" -ForegroundColor White
Write-Host "   SNS_TOPIC_ARN=$topicArn" -ForegroundColor Gray
Write-Host "   AWS_REGION=$REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "4. View your credentials:" -ForegroundColor White
Write-Host "   notepad $env:USERPROFILE\.aws\credentials" -ForegroundColor Gray
Write-Host ""
Write-Host "Setup completed!" -ForegroundColor Green
