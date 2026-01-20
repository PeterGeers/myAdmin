# AWS User Notifications Setup Guide

Complete guide to set up email notifications for your myAdmin application using AWS SNS.

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI installed and configured
- Terraform installed (v1.0+)
- Access to your EC2 instance

## Step 1: Install AWS CLI (if not already installed)

### Windows

```powershell
# Download and install from: https://aws.amazon.com/cli/
# Or use chocolatey:
choco install awscli
```

### Verify Installation

```bash
aws --version
```

## Step 2: Configure AWS Credentials

```bash
aws configure
```

You'll be prompted for:

- **AWS Access Key ID**: Your AWS access key
- **AWS Secret Access Key**: Your AWS secret key
- **Default region**: `eu-west-1` (or your preferred region)
- **Default output format**: `json`

### Alternative: Use Environment Variables

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="eu-west-1"
```

## Step 3: Update Terraform Configuration

### 3.1 Update main.tf

The EC2 instance needs to be updated to use the IAM role. Edit `infrastructure/main.tf`:

```terraform
# Remove or comment out the old aws_instance.myadmin_backend
# It will be replaced by aws_instance.myadmin_backend_with_notifications
# from notifications.tf
```

### 3.2 Create terraform.tfvars

Create `infrastructure/terraform.tfvars`:

```hcl
# AWS Configuration
aws_region = "eu-west-1"
key_name   = "your-ec2-key-name"

# Notification Configuration
admin_email = "peter@pgeers.nl"

# Optional: Add more email addresses
additional_notification_emails = [
  # "team@example.com",
  # "alerts@example.com"
]
```

## Step 4: Initialize and Apply Terraform

```bash
cd infrastructure

# Initialize Terraform
terraform init

# Review the changes
terraform plan

# Apply the configuration
terraform apply
```

**Important**: Type `yes` when prompted to confirm.

## Step 5: Confirm Email Subscription

After Terraform completes:

1. **Check your email** (peter@pgeers.nl)
2. Look for: **"AWS Notification - Subscription Confirmation"**
3. **Click the confirmation link** in the email
4. You should see: "Subscription confirmed!"

**Note**: Until you confirm, notifications won't be delivered!

## Step 6: Get SNS Topic ARN

After Terraform completes, note the SNS Topic ARN:

```bash
terraform output sns_topic_arn
```

Example output:

```
arn:aws:sns:eu-west-1:123456789012:myadmin-notifications
```

## Step 7: Configure EC2 Instance

### 7.1 SSH into your EC2 instance

```bash
# Get the SSH command from Terraform
terraform output ssh_command

# Or manually:
ssh -i your-key.pem ec2-user@your-instance-ip
```

### 7.2 Set Environment Variables

Add to your application's environment file:

```bash
# On EC2 instance
sudo nano /etc/environment

# Add these lines:
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:123456789012:myadmin-notifications
AWS_REGION=eu-west-1
```

Or add to your application's `.env` file:

```bash
cd /path/to/myAdmin/backend
nano .env

# Add:
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:123456789012:myadmin-notifications
AWS_REGION=eu-west-1
```

### 7.3 Install boto3 (AWS SDK for Python)

```bash
cd /path/to/myAdmin/backend
source venv/bin/activate  # or .venv/bin/activate
pip install boto3
pip freeze > requirements.txt
```

## Step 8: Test the Notification System

### 8.1 Test from AWS CLI

```bash
aws sns publish \
  --topic-arn arn:aws:sns:eu-west-1:123456789012:myadmin-notifications \
  --message "Test notification from AWS CLI" \
  --subject "Test: myAdmin Notification" \
  --region eu-west-1
```

You should receive an email within seconds!

### 8.2 Test from Python

Create a test script on your EC2 instance:

```bash
cd /path/to/myAdmin/backend
nano test_notifications.py
```

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/path/to/myAdmin/backend/src')

from aws_notifications import get_notification_service

# Test notification
service = get_notification_service()

if service.is_enabled():
    print("✓ Notification service is enabled")
    print(f"  Topic ARN: {service.topic_arn}")
    print(f"  Region: {service.region}")

    # Send test notification
    print("\nSending test notification...")
    success = service.test_notification()

    if success:
        print("✓ Test notification sent successfully!")
        print("  Check your email inbox")
    else:
        print("✗ Failed to send notification")
else:
    print("✗ Notification service is not enabled")
    print("  Check SNS_TOPIC_ARN environment variable")
```

Run the test:

```bash
python test_notifications.py
```

## Step 9: Integrate with Your Application

### 9.1 Update requirements.txt

Ensure boto3 is in your requirements:

```bash
cd backend
echo "boto3>=1.28.0" >> requirements.txt
```

### 9.2 Import in your application

In your Flask app or routes:

```python
from aws_notifications import get_notification_service
from notification_integration import get_notification_integration

# Get the service
notification_service = get_notification_service()
integration = get_notification_integration()

# Send notifications
notification_service.send_alert(
    alert_type="Performance",
    message="High CPU usage detected",
    severity="WARNING"
)

# Or use integration helpers
integration.handle_performance_alert(
    pool_name="database",
    avg_response_time=2.5,
    threshold=2.0
)
```

## Step 10: Verify IAM Permissions

Check that your EC2 instance has the correct IAM role:

```bash
# On EC2 instance
aws sts get-caller-identity

# Should show the IAM role
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

## Troubleshooting

### Issue: "No credentials found"

**Solution**: Ensure IAM instance profile is attached to EC2:

```bash
# Check instance profile
aws ec2 describe-instances --instance-ids i-xxxxx \
  --query 'Reservations[0].Instances[0].IamInstanceProfile'

# If missing, attach it:
aws ec2 associate-iam-instance-profile \
  --instance-id i-xxxxx \
  --iam-instance-profile Name=myadmin-instance-profile
```

### Issue: "Email not received"

**Checklist**:

1. ✓ Email subscription confirmed?
2. ✓ Check spam folder
3. ✓ Correct email address in terraform.tfvars?
4. ✓ SNS topic ARN correct in environment variables?

**Test SNS directly**:

```bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:eu-west-1:123456789012:myadmin-notifications
```

### Issue: "Access Denied"

**Solution**: Check IAM policy:

```bash
# View the policy
aws iam get-role-policy \
  --role-name myadmin-ec2-role \
  --policy-name myadmin-sns-policy
```

### Issue: "Topic not found"

**Solution**: Verify topic exists:

```bash
aws sns list-topics --region eu-west-1
```

## Cost Estimation

AWS SNS Pricing (as of 2024):

- **First 1,000 email notifications/month**: FREE
- **Additional emails**: $2.00 per 100,000 notifications
- **Typical usage**: ~100-500 notifications/month = **FREE**

## Security Best Practices

1. **Use IAM roles** (not access keys) for EC2 ✓
2. **Limit SNS permissions** to only what's needed ✓
3. **Enable CloudTrail** for audit logging
4. **Use VPC endpoints** for SNS (optional, for private access)
5. **Rotate credentials** regularly

## Next Steps

1. ✓ Set up notifications
2. ✓ Test the system
3. Configure notification preferences:
   - Which events trigger notifications?
   - Alert thresholds
   - Cooldown periods
4. Monitor notification delivery in CloudWatch
5. Set up SNS delivery status logging (optional)

## Monitoring Notifications

### View SNS Metrics in CloudWatch

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/SNS \
  --metric-name NumberOfNotificationsFailed \
  --dimensions Name=TopicName,Value=myadmin-notifications \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-31T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

### Enable SNS Delivery Status Logging

```bash
aws sns set-topic-attributes \
  --topic-arn arn:aws:sns:eu-west-1:123456789012:myadmin-notifications \
  --attribute-name HTTPSuccessFeedbackRoleArn \
  --attribute-value arn:aws:iam::123456789012:role/SNSSuccessFeedback
```

## Additional Configuration

### Add SMS Notifications (Optional)

```terraform
# In notifications.tf, add:
resource "aws_sns_topic_subscription" "admin_sms" {
  topic_arn = aws_sns_topic.myadmin_notifications.arn
  protocol  = "sms"
  endpoint  = "+31612345678"  # Your phone number
}
```

### Add Slack Integration (Optional)

Use AWS Chatbot or Lambda to forward SNS to Slack.

## Support

If you encounter issues:

1. Check CloudWatch Logs
2. Review IAM permissions
3. Verify SNS topic configuration
4. Test with AWS CLI first
5. Check application logs

## Summary

✓ AWS SNS Topic created
✓ IAM roles and policies configured
✓ Email subscription set up
✓ Python notification service ready
✓ Integration with existing monitoring

Your notification system is ready to use!
