"""
Test AWS SNS Notifications
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = backend_dir / '.env'
load_dotenv(env_path)

print("=" * 50)
print("AWS SNS Notification Test")
print("=" * 50)
print()

# Check environment variables
sns_topic_arn = os.getenv('SNS_TOPIC_ARN')
aws_region = os.getenv('AWS_REGION')

print(f"SNS_TOPIC_ARN: {sns_topic_arn}")
print(f"AWS_REGION: {aws_region}")
print()

if not sns_topic_arn:
    print("ERROR: SNS_TOPIC_ARN not found in .env file")
    print(f"Checked: {env_path}")
    sys.exit(1)

# Import and test notification service
from src.aws_notifications import get_notification_service

service = get_notification_service()

print(f"Service enabled: {service.is_enabled()}")
print(f"Topic ARN: {service.topic_arn}")
print(f"Region: {service.region}")
print()

if service.is_enabled():
    print("Sending test notification...")
    success = service.test_notification()
    print()
    if success:
        print("✓ Test notification sent successfully!")
        print("Check your email: peter@pgeers.nl")
    else:
        print("✗ Failed to send test notification")
        print("Check the logs above for errors")
else:
    print("✗ Notification service is not enabled")
    print("Make sure SNS_TOPIC_ARN is set in .env file")
