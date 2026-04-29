"""
Test SNS Email Delivery

This script tests the SNS email integration without requiring authentication.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from services.email_template_service import EmailTemplateService
import boto3
from botocore.exceptions import ClientError


def test_sns_email():
    """Test SNS email delivery"""
    
    print("=" * 80)
    print("Testing SNS Email Delivery")
    print("=" * 80)
    print()
    
    # Check SNS configuration
    sns_topic_arn = os.getenv('SNS_TOPIC_ARN')
    aws_region = os.getenv('AWS_REGION', 'eu-west-1')
    
    if not sns_topic_arn:
        print("❌ SNS_TOPIC_ARN not configured in .env")
        return False
    
    print(f"✅ SNS Topic ARN: {sns_topic_arn}")
    print(f"✅ AWS Region: {aws_region}")
    print()
    
    # Test data
    test_data = {
        'email': 'test@example.com',
        'temporary_password': 'TestPass123!',
        'tenant': 'TestTenant',
        'login_url': 'http://localhost:3000'
    }
    
    try:
        # Initialize email service
        email_service = EmailTemplateService(administration=test_data['tenant'])
        
        # Render templates
        print("1. Rendering Email Templates")
        print("-" * 80)
        
        html_content = email_service.render_user_invitation(
            email=test_data['email'],
            temporary_password=test_data['temporary_password'],
            tenant=test_data['tenant'],
            login_url=test_data['login_url'],
            format='html'
        )
        
        text_content = email_service.render_user_invitation(
            email=test_data['email'],
            temporary_password=test_data['temporary_password'],
            tenant=test_data['tenant'],
            login_url=test_data['login_url'],
            format='txt'
        )
        
        if html_content and text_content:
            print("✅ Templates rendered successfully")
            print(f"   HTML length: {len(html_content)} characters")
            print(f"   Text length: {len(text_content)} characters")
        else:
            print("❌ Template rendering failed")
            return False
        
        print()
        
        # Get subject line
        subject = email_service.get_invitation_subject(test_data['tenant'])
        print(f"✅ Subject: {subject}")
        print()
        
        # Test SNS connection
        print("2. Testing SNS Connection")
        print("-" * 80)
        
        sns_client = boto3.client('sns', region_name=aws_region)
        
        # Try to get topic attributes (validates connection and permissions)
        try:
            response = sns_client.get_topic_attributes(TopicArn=sns_topic_arn)
            print("✅ SNS connection successful")
            print(f"   Topic Name: {response['Attributes'].get('DisplayName', 'N/A')}")
            print(f"   Subscriptions: {response['Attributes'].get('SubscriptionsConfirmed', '0')}")
        except ClientError as e:
            print(f"❌ SNS connection failed: {e}")
            return False
        
        print()
        
        # Ask user if they want to send a test email
        print("3. Send Test Email")
        print("-" * 80)
        print("⚠️  This will send an actual email via SNS to subscribed addresses.")
        print()
        
        send_test = input("Do you want to send a test email? (yes/no): ").strip().lower()
        
        if send_test == 'yes':
            print()
            print("Sending test email...")
            
            try:
                sns_client.publish(
                    TopicArn=sns_topic_arn,
                    Subject=subject,
                    Message=text_content
                )
                
                print("✅ Test email sent successfully!")
                print()
                print("Check your email inbox (subscribed to SNS topic)")
                print()
                
            except ClientError as e:
                print(f"❌ Failed to send email: {e}")
                return False
        else:
            print("⏭️  Skipped sending test email")
        
        print()
        print("=" * 80)
        print("SNS Email Test Complete")
        print("=" * 80)
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_sns_email()
    sys.exit(0 if success else 1)
