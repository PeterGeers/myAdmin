# AWS SNS Notifications Setup (No EC2)
# For local development - only creates SNS topic

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "AWS SNS Notifications Setup" -ForegroundColor Cyan
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
    exit 1
}

Write-Host ""
Write-Host "Configuration" -ForegroundColor Cyan
Write-Host "=============" -ForegroundColor Cyan
Write-Host ""

$AWS_REGION = Read-Host "AWS region [eu-west-1]"
if ([string]::IsNullOrWhiteSpace($AWS_REGION)) { $AWS_REGION = "eu-west-1" }

$ADMIN_EMAIL = Read-Host "Admin email [peter@pgeers.nl]"
if ([string]::IsNullOrWhiteSpace($ADMIN_EMAIL)) { $ADMIN_EMAIL = "peter@pgeers.nl" }

# Create SNS topic
Write-Host ""
Write-Host "Creating SNS topic..." -ForegroundColor Cyan

$topicName = "myAdmin-notifications"
try {
    $createResult = aws sns create-topic --name $topicName --region $AWS_REGION 2>&1 | ConvertFrom-Json
    $SNS_TOPIC_ARN = $createResult.TopicArn
    Write-Host "OK - SNS topic created" -ForegroundColor Green
    Write-Host "  ARN: $SNS_TOPIC_ARN" -ForegroundColor Gray
}
catch {
    Write-Host "ERROR - Failed to create SNS topic" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Subscribe email
Write-Host ""
Write-Host "Subscribing email..." -ForegroundColor Cyan

try {
    $subscribeResult = aws sns subscribe `
        --topic-arn $SNS_TOPIC_ARN `
        --protocol email `
        --notification-endpoint $ADMIN_EMAIL `
        --region $AWS_REGION 2>&1 | ConvertFrom-Json
    
    Write-Host "OK - Email subscription created" -ForegroundColor Green
    Write-Host "  Subscription ARN: $($subscribeResult.SubscriptionArn)" -ForegroundColor Gray
}
catch {
    Write-Host "ERROR - Failed to subscribe email" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Test notification
Write-Host ""
$sendTest = Read-Host "Send test notification? (yes/no) [yes]"
if ([string]::IsNullOrWhiteSpace($sendTest)) { $sendTest = "yes" }

if ($sendTest -eq "yes") {
    Write-Host "Sending test notification..." -ForegroundColor Cyan
    try {
        aws sns publish `
            --topic-arn $SNS_TOPIC_ARN `
            --message "Test notification from myAdmin setup" `
            --subject "myAdmin Test Notification" `
            --region $AWS_REGION | Out-Null
        
        Write-Host "OK - Test notification sent" -ForegroundColor Green
    }
    catch {
        Write-Host "WARNING - Failed to send test notification" -ForegroundColor Yellow
        Write-Host $_.Exception.Message -ForegroundColor Yellow
    }
}

# Summary
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "SNS Topic ARN:" -ForegroundColor Cyan
Write-Host "  $SNS_TOPIC_ARN" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "==========" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. CHECK YOUR EMAIL: $ADMIN_EMAIL" -ForegroundColor White
Write-Host "   You will receive an AWS confirmation email" -ForegroundColor Gray
Write-Host "   Click the confirmation link to activate notifications" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Add to backend/.env:" -ForegroundColor White
Write-Host "   SNS_TOPIC_ARN=$SNS_TOPIC_ARN" -ForegroundColor Gray
Write-Host "   AWS_REGION=$AWS_REGION" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Install boto3 (if not already installed):" -ForegroundColor White
Write-Host "   pip install boto3" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Test from Python:" -ForegroundColor White
Write-Host "   python -c `"from backend.src.aws_notifications import get_notification_service; print(get_notification_service().test_notification())`"" -ForegroundColor Gray
Write-Host ""
Write-Host "Setup completed successfully!" -ForegroundColor Green
