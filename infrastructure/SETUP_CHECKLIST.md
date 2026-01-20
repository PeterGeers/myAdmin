# AWS Notifications Setup Checklist

Use this checklist to track your setup progress.

## Prerequisites ✓

- [ ] AWS Account created
- [ ] AWS CLI installed (`aws --version`)
- [ ] AWS credentials configured (`aws configure`)
- [ ] Terraform installed (`terraform --version`)
- [ ] EC2 key pair available

## Setup Steps

### 1. Run Setup Script

- [ ] Navigate to `infrastructure` folder
- [ ] Run setup script:
  - Windows: `.\setup-notifications.ps1`
  - Linux/Mac: `./setup-notifications.sh`
- [ ] Provide configuration:
  - [ ] AWS Region (default: eu-west-1)
  - [ ] EC2 Key Name
  - [ ] Admin Email (default: peter@pgeers.nl)
  - [ ] Domain Name (default: admin.pgeers.nl)
- [ ] Review Terraform plan
- [ ] Confirm and apply (type `yes`)

### 2. Confirm Email Subscription ⚠️ IMPORTANT

- [ ] Check email inbox: peter@pgeers.nl
- [ ] Find email: "AWS Notification - Subscription Confirmation"
- [ ] Click confirmation link
- [ ] See "Subscription confirmed!" message

### 3. Get Configuration Values

- [ ] Note SNS Topic ARN: `terraform output sns_topic_arn`
- [ ] Note EC2 Instance IP: `terraform output instance_ip`

### 4. Test Notification (AWS CLI)

```bash
aws sns publish \
  --topic-arn <YOUR_TOPIC_ARN> \
  --message "Test from myAdmin" \
  --subject "Test Notification" \
  --region eu-west-1
```

- [ ] Command executed successfully
- [ ] Email received within 1 minute

### 5. Configure EC2 Instance

- [ ] SSH into EC2: `ssh -i <key>.pem ec2-user@<instance-ip>`
- [ ] Navigate to application: `cd /path/to/myAdmin/backend`
- [ ] Activate virtual environment: `source venv/bin/activate`
- [ ] Install boto3: `pip install boto3`
- [ ] Update requirements: `pip freeze > requirements.txt`

### 6. Configure Application

- [ ] Edit `.env` file: `nano .env`
- [ ] Add: `SNS_TOPIC_ARN=<your-topic-arn>`
- [ ] Add: `AWS_REGION=eu-west-1`
- [ ] Save and exit

### 7. Test from Python

Create test file: `test_notifications.py`

```python
from aws_notifications import get_notification_service

service = get_notification_service()
print(f"Enabled: {service.is_enabled()}")
print(f"Topic: {service.topic_arn}")

success = service.test_notification()
print(f"Test sent: {success}")
```

- [ ] Run: `python test_notifications.py`
- [ ] See "Enabled: True"
- [ ] See "Test sent: True"
- [ ] Receive test email

### 8. Integrate with Application

- [ ] Import notification service in your code
- [ ] Add notification calls where needed
- [ ] Test each notification type
- [ ] Restart application

### 9. Verify IAM Permissions

- [ ] Check instance profile: `curl http://169.254.169.254/latest/meta-data/iam/security-credentials/`
- [ ] Should show: `myadmin-ec2-role`
- [ ] Test AWS identity: `aws sts get-caller-identity`

### 10. Monitor and Verify

- [ ] Send test notifications
- [ ] Check CloudWatch metrics
- [ ] Verify email delivery
- [ ] Check application logs

## Post-Setup

### Configuration

- [ ] Set alert thresholds
- [ ] Configure cooldown periods
- [ ] Add additional email addresses (if needed)
- [ ] Set up SMS notifications (optional)

### Documentation

- [ ] Document notification types used
- [ ] Update team on new notification system
- [ ] Create runbook for common issues

### Monitoring

- [ ] Set up CloudWatch dashboard
- [ ] Configure SNS delivery status logging
- [ ] Set up billing alerts

## Troubleshooting Checklist

If notifications not working:

- [ ] Email subscription confirmed?
- [ ] SNS_TOPIC_ARN set correctly?
- [ ] boto3 installed?
- [ ] IAM role attached to EC2?
- [ ] IAM policy allows SNS:Publish?
- [ ] Check application logs
- [ ] Check CloudWatch logs
- [ ] Test with AWS CLI first

## Success Criteria

✅ All items checked above
✅ Test email received
✅ Python test successful
✅ Application sending notifications
✅ No errors in logs

## Rollback Plan

If you need to remove the setup:

```bash
cd infrastructure
terraform destroy
```

This will:

- Delete SNS topic
- Remove IAM roles and policies
- Detach instance profile from EC2

## Support Resources

- **Quick Start**: `QUICK_START.md`
- **Full Guide**: `AWS_NOTIFICATIONS_SETUP.md`
- **Summary**: `../AWS_NOTIFICATIONS_SUMMARY.md`
- **AWS SNS Docs**: https://docs.aws.amazon.com/sns/
- **boto3 Docs**: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html

## Notes

Date Started: ******\_\_\_******
Date Completed: ******\_\_\_******
SNS Topic ARN: **********************\_\_\_**********************
EC2 Instance IP: ******\_\_\_******
Issues Encountered: **********************\_\_\_**********************

---

---

## Sign-off

Setup completed by: ******\_\_\_******
Date: ******\_\_\_******
Verified by: ******\_\_\_******
Date: ******\_\_\_******
