# AWS Notifications - Quick Start

## 5-Minute Setup

### 1. Prerequisites

```bash
# Check you have:
aws --version        # AWS CLI installed
terraform --version  # Terraform installed
aws sts get-caller-identity  # AWS credentials configured
```

### 2. Run Setup Script

**Windows (PowerShell):**

```powershell
cd infrastructure
.\setup-notifications.ps1
```

**Linux/Mac:**

```bash
cd infrastructure
chmod +x setup-notifications.sh
./setup-notifications.sh
```

### 3. Confirm Email

- Check inbox: peter@pgeers.nl
- Click confirmation link in AWS email

### 4. Test

```bash
# Get the topic ARN
terraform output sns_topic_arn

# Send test notification
aws sns publish \
  --topic-arn <YOUR_TOPIC_ARN> \
  --message "Test from myAdmin" \
  --subject "Test" \
  --region eu-west-1
```

### 5. Configure Application

Add to `backend/.env`:

```
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:123456789012:myadmin-notifications
AWS_REGION=eu-west-1
```

Install boto3:

```bash
cd backend
pip install boto3
```

### 6. Use in Code

```python
from aws_notifications import get_notification_service

service = get_notification_service()
service.send_alert(
    alert_type="Test",
    message="Hello from myAdmin!",
    severity="INFO"
)
```

## Done! 🎉

Your notification system is ready.

## Common Commands

```bash
# List SNS topics
aws sns list-topics

# List subscriptions
aws sns list-subscriptions

# Send notification
aws sns publish \
  --topic-arn <ARN> \
  --message "Your message" \
  --subject "Subject"

# View CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/SNS \
  --metric-name NumberOfNotificationsDelivered \
  --dimensions Name=TopicName,Value=myadmin-notifications \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-12-31T23:59:59Z \
  --period 86400 \
  --statistics Sum
```

## Troubleshooting

**No email received?**

1. Check spam folder
2. Verify subscription: `aws sns list-subscriptions-by-topic --topic-arn <ARN>`
3. Confirm email subscription (check inbox again)

**Access denied?**

1. Check IAM role attached to EC2
2. Verify IAM policy allows SNS:Publish

**Can't find topic?**

```bash
aws sns list-topics --region eu-west-1
```

## Cost

- First 1,000 emails/month: **FREE**
- Typical usage: **$0/month**

## Support

See full documentation: `AWS_NOTIFICATIONS_SETUP.md`
