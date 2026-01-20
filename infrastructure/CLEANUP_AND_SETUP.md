# AWS Credentials Cleanup & SNS Setup

## Step 1: Clean Up Duplicate AWS Credentials

You currently have duplicate AWS credentials. Let's fix that first.

### Option A: Manual Cleanup (Recommended)

1. Open the credentials file:

   ```powershell
   notepad C:\Users\peter\.aws\credentials
   ```

2. Keep ONLY the `[default]` section, delete everything else:

   ```ini
   [default]
   aws_access_key_id = YOUR_KEY_HERE
   aws_secret_access_key = YOUR_SECRET_HERE
   ```

3. Save and close

4. Test:
   ```powershell
   aws sts get-caller-identity
   ```

### Option B: Use Cleanup Script

```powershell
cd C:\Users\peter\aws\myAdmin\infrastructure
.\cleanup-aws-credentials.ps1
```

This will:

- Backup your current file to `.backup`
- Keep only the `[default]` profile
- Remove duplicates

## Step 2: Set Up SNS Notifications (No EC2 Required)

Since you're running myAdmin locally, you don't need EC2. Use the simplified SNS-only setup:

```powershell
cd C:\Users\peter\aws\myAdmin\infrastructure
.\setup-sns-only.ps1
```

This will:

1. Create SNS topic: `myAdmin-notifications`
2. Subscribe your email: `peter@pgeers.nl`
3. Send a test notification
4. Give you the SNS Topic ARN

### What to Enter

- **AWS region**: Press Enter (uses `eu-west-1`)
- **Admin email**: Press Enter (uses `peter@pgeers.nl`)
- **Send test notification**: Type `yes` and press Enter

## Step 3: Confirm Email Subscription

⚠️ **IMPORTANT**: Check your email inbox!

1. Look for email from: `AWS Notifications <no-reply@sns.amazonaws.com>`
2. Subject: `AWS Notification - Subscription Confirmation`
3. Click the confirmation link
4. You should see: "Subscription confirmed!"

**Without this step, notifications won't work!**

## Step 4: Configure Your Application

Add to `backend/.env`:

```env
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:344561557829:myAdmin-notifications
AWS_REGION=eu-west-1
```

(The script will show you the exact ARN to use)

## Step 5: Install boto3

```powershell
cd C:\Users\peter\aws\myAdmin\backend
.\.venv\Scripts\Activate.ps1
pip install boto3
```

## Step 6: Test Notifications

### Test from AWS CLI

```powershell
aws sns publish `
  --topic-arn arn:aws:sns:eu-west-1:344561557829:myAdmin-notifications `
  --message "Test from CLI" `
  --subject "Test Notification" `
  --region eu-west-1
```

You should receive an email within 1 minute.

### Test from Python

```powershell
cd C:\Users\peter\aws\myAdmin\backend
.\.venv\Scripts\Activate.ps1
python -c "from src.aws_notifications import get_notification_service; print(get_notification_service().test_notification())"
```

Should print: `True` and you should receive an email.

## Troubleshooting

### "Credentials not configured"

```powershell
aws configure
```

Enter:

- AWS Access Key ID: (your key)
- AWS Secret Access Key: (your secret)
- Default region: `eu-west-1`
- Default output format: `json`

### "Topic already exists"

If the topic already exists, get its ARN:

```powershell
aws sns list-topics --region eu-west-1
```

Look for `myAdmin-notifications` and use that ARN.

### "Email not received"

1. Check spam folder
2. Verify email address is correct
3. Check SNS subscription status:
   ```powershell
   aws sns list-subscriptions --region eu-west-1
   ```

### "boto3 not found"

Make sure you're in the virtual environment:

```powershell
cd C:\Users\peter\aws\myAdmin\backend
.\.venv\Scripts\Activate.ps1
pip install boto3
```

## What About EC2?

The full Terraform setup (`setup-notifications-simple.ps1`) creates:

- SNS topic
- EC2 instance
- IAM roles
- Security groups

**You only need this if you're deploying to AWS EC2.**

For local development, the SNS-only setup is sufficient. Your local machine will send notifications to AWS SNS, which delivers them via email.

## Summary

✅ Clean up duplicate credentials  
✅ Run `setup-sns-only.ps1`  
✅ Confirm email subscription  
✅ Add SNS_TOPIC_ARN to `.env`  
✅ Install boto3  
✅ Test notifications

That's it! No EC2, no Terraform, just SNS notifications.
