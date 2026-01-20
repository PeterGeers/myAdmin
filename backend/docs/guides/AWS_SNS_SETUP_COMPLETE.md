# AWS SNS Notifications - Setup Complete ✅

## Status: OPERATIONAL

Your AWS SNS notification system is fully configured and working!

## Configuration

- **SNS Topic ARN**: `arn:aws:sns:eu-west-1:344561557829:myadmin-notifications`
- **AWS Region**: `eu-west-1`
- **Email**: `peter@pgeers.nl` (confirmed and active)
- **Subscription Status**: ✅ Confirmed

## Files Configured

- `backend/.env` - Contains SNS_TOPIC_ARN and AWS_REGION
- `backend/src/aws_notifications.py` - Notification service
- `backend/src/notification_integration.py` - Integration helpers
- `backend/requirements.txt` - Includes boto3==1.42.30

## Testing

Test script: `backend/test_sns_notification.py`

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python test_sns_notification.py
```

## Usage Examples

### 1. Send Business Notification

```python
from src.aws_notifications import get_notification_service

service = get_notification_service()

service.send_business_notification(
    title="New Booking Received",
    message="A new booking has been created for Villa Venray",
    data={
        "booking_id": "12345",
        "guest_name": "John Doe",
        "check_in": "2026-02-01",
        "amount": "€450"
    }
)
```

### 2. Send Performance Alert

```python
service.send_performance_alert(
    metric_name="Database Query Time",
    current_value=5.2,
    threshold=2.0,
    details="Query took 5.2 seconds (threshold: 2.0s)"
)
```

### 3. Send Error Notification

```python
service.send_error_notification(
    error_type="DatabaseError",
    error_message="Failed to connect to database",
    stack_trace=traceback.format_exc()
)
```

### 4. Send Security Alert

```python
service.send_security_alert(
    event_type="Failed Login Attempt",
    description="Multiple failed login attempts detected",
    source_ip="192.168.1.100",
    user="admin"
)
```

### 5. Send Custom Notification

```python
service.send_notification(
    subject="Custom Alert",
    message="Your custom message here",
    message_attributes={'type': 'custom', 'priority': 'high'}
)
```

## Integration Points

You can add notifications to:

1. **Banking Processor** - Alert on large transactions or errors
2. **STR Processor** - Notify when reports are generated
3. **Invoice Processing** - Alert on duplicate invoices
4. **PDF Processing** - Notify on processing errors
5. **Performance Monitoring** - Alert on slow queries
6. **Security Events** - Alert on suspicious activity

## Example: Add to Banking Upload

```python
# In your banking upload endpoint
from src.aws_notifications import get_notification_service

@app.route('/api/upload-banking', methods=['POST'])
def upload_banking():
    try:
        # ... your existing code ...

        # Send notification on success
        service = get_notification_service()
        service.send_business_notification(
            title="Banking File Processed",
            message=f"Successfully processed {len(transactions)} transactions",
            data={
                "file_name": file.filename,
                "transactions": len(transactions),
                "total_amount": f"€{total_amount:.2f}"
            }
        )

        return jsonify({"success": True})
    except Exception as e:
        # Send error notification
        service.send_error_notification(
            error_type="BankingUploadError",
            error_message=str(e),
            stack_trace=traceback.format_exc()
        )
        raise
```

## Monitoring

### Check Notification Status

```python
service = get_notification_service()
print(f"Enabled: {service.is_enabled()}")
print(f"Topic: {service.topic_arn}")
print(f"Region: {service.region}")
```

### AWS Console

View notifications in AWS Console:

- https://console.aws.amazon.com/sns/
- Region: eu-west-1
- Topic: myadmin-notifications

## Cost

AWS SNS Pricing (as of 2026):

- First 1,000 email notifications/month: FREE
- Additional emails: $2.00 per 100,000 notifications
- Very cost-effective for typical usage

## Troubleshooting

### Not receiving emails?

1. Check spam folder
2. Verify subscription is confirmed
3. Check AWS SNS console for delivery status
4. Test with: `python test_sns_notification.py`

### "Notifications disabled" message?

1. Check `.env` file has `SNS_TOPIC_ARN`
2. Verify boto3 is installed: `pip list | findstr boto3`
3. Check AWS credentials: `aws sts get-caller-identity`

### AWS credentials error?

1. Verify credentials file: `C:\Users\peter\.aws\credentials`
2. Should have only `[default]` profile
3. Test: `aws sns list-topics --region eu-west-1`

## Next Steps

1. ✅ SNS setup complete
2. ✅ Test notification sent and received
3. ⏭️ Add notifications to your application endpoints
4. ⏭️ Set up CloudWatch monitoring (optional)
5. ⏭️ Add SMS notifications (optional)

## Support

- AWS SNS Documentation: https://docs.aws.amazon.com/sns/
- boto3 Documentation: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html
- Test script: `backend/test_sns_notification.py`

---

**Setup completed**: January 20, 2026  
**Status**: ✅ Operational  
**Last tested**: January 20, 2026
