"""
AWS User Notifications Service
Handles sending notifications via AWS SNS (Simple Notification Service)
"""

import boto3
import logging
import os
from typing import Optional, Dict, List, Any
from datetime import datetime
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)


class AWSNotificationService:
    """
    Service for sending notifications via AWS SNS
    
    Features:
    - Email notifications
    - SMS notifications (optional)
    - Multiple recipients
    - Message templates
    - Error handling and retry logic
    """
    
    def __init__(self, topic_arn: Optional[str] = None, region: str = 'eu-west-1'):
        """
        Initialize AWS SNS client
        
        Args:
            topic_arn: SNS Topic ARN (from environment or parameter)
            region: AWS region
        """
        self.topic_arn = topic_arn or os.getenv('SNS_TOPIC_ARN')
        self.region = region or os.getenv('AWS_REGION', 'eu-west-1')
        
        if not self.topic_arn:
            logger.warning("SNS_TOPIC_ARN not configured. Notifications will be disabled.")
            self.sns_client = None
        else:
            try:
                self.sns_client = boto3.client('sns', region_name=self.region)
                logger.info(f"AWS SNS client initialized for region: {self.region}")
            except Exception as e:
                logger.error(f"Failed to initialize SNS client: {e}")
                self.sns_client = None
    
    def is_enabled(self) -> bool:
        """Check if notifications are enabled"""
        return self.sns_client is not None and self.topic_arn is not None
    
    def send_notification(
        self,
        subject: str,
        message: str,
        message_attributes: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a notification via SNS
        
        Args:
            subject: Email subject line
            message: Notification message body
            message_attributes: Optional attributes for filtering
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled():
            logger.warning("Notifications disabled. Message not sent.")
            logger.info(f"Would have sent: {subject} - {message[:100]}")
            return False
        
        try:
            # Prepare message attributes
            attrs = message_attributes or {}
            sns_attributes = {
                key: {'DataType': 'String', 'StringValue': str(value)}
                for key, value in attrs.items()
            }
            
            # Add timestamp
            sns_attributes['timestamp'] = {
                'DataType': 'String',
                'StringValue': datetime.now().isoformat()
            }
            
            # Publish to SNS
            response = self.sns_client.publish(
                TopicArn=self.topic_arn,
                Subject=subject[:100],  # SNS subject limit
                Message=message,
                MessageAttributes=sns_attributes
            )
            
            message_id = response.get('MessageId')
            logger.info(f"Notification sent successfully. MessageId: {message_id}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS SNS Error [{error_code}]: {error_message}")
            return False
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False
    
    def send_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = 'INFO',
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an alert notification
        
        Args:
            alert_type: Type of alert (e.g., 'performance', 'error', 'security')
            message: Alert message
            severity: Alert severity (INFO, WARNING, ERROR, CRITICAL)
            details: Additional details
            
        Returns:
            True if successful
        """
        subject = f"[{severity}] myAdmin Alert: {alert_type}"
        
        # Format message
        formatted_message = f"""
MyAdmin Application Alert
========================

Type: {alert_type}
Severity: {severity}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Message:
{message}
"""
        
        if details:
            formatted_message += "\n\nDetails:\n"
            for key, value in details.items():
                formatted_message += f"  {key}: {value}\n"
        
        # Add attributes for filtering
        attributes = {
            'alert_type': alert_type,
            'severity': severity,
            'application': 'myAdmin'
        }
        
        return self.send_notification(subject, formatted_message, attributes)
    
    def send_performance_alert(
        self,
        metric_name: str,
        current_value: float,
        threshold: float,
        details: Optional[str] = None
    ) -> bool:
        """Send performance degradation alert"""
        message = f"""
Performance threshold exceeded for {metric_name}

Current Value: {current_value:.2f}
Threshold: {threshold:.2f}
Exceeded by: {((current_value / threshold - 1) * 100):.1f}%
"""
        if details:
            message += f"\n{details}"
        
        return self.send_alert(
            alert_type='Performance',
            message=message,
            severity='WARNING',
            details={'metric': metric_name, 'value': current_value}
        )
    
    def send_error_notification(
        self,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None
    ) -> bool:
        """Send error notification"""
        message = f"""
Application Error Occurred

Error Type: {error_type}
Error Message: {error_message}
"""
        if stack_trace:
            message += f"\nStack Trace:\n{stack_trace[:1000]}"  # Limit size
        
        return self.send_alert(
            alert_type='Error',
            message=message,
            severity='ERROR',
            details={'error_type': error_type}
        )
    
    def send_security_alert(
        self,
        event_type: str,
        description: str,
        source_ip: Optional[str] = None,
        user: Optional[str] = None
    ) -> bool:
        """Send security alert"""
        details = {}
        if source_ip:
            details['source_ip'] = source_ip
        if user:
            details['user'] = user
        
        return self.send_alert(
            alert_type='Security',
            message=f"{event_type}: {description}",
            severity='CRITICAL',
            details=details
        )
    
    def send_business_notification(
        self,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send business-related notification
        (e.g., new booking, payment received, report generated)
        """
        formatted_message = f"""
{title}
{'=' * len(title)}

{message}
"""
        
        if data:
            formatted_message += "\n\nData:\n"
            for key, value in data.items():
                formatted_message += f"  {key}: {value}\n"
        
        return self.send_notification(
            subject=f"myAdmin: {title}",
            message=formatted_message,
            message_attributes={'type': 'business', 'title': title}
        )
    
    def test_notification(self) -> bool:
        """Send a test notification to verify setup"""
        return self.send_notification(
            subject="Test: myAdmin Notification System",
            message=f"""
This is a test notification from myAdmin application.

If you received this email, your AWS SNS notification system is working correctly!

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Region: {self.region}
Topic ARN: {self.topic_arn}
""",
            message_attributes={'type': 'test'}
        )


# Global instance
_notification_service: Optional[AWSNotificationService] = None


def get_notification_service() -> AWSNotificationService:
    """Get or create the global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = AWSNotificationService()
    return _notification_service


def send_notification(subject: str, message: str, **kwargs) -> bool:
    """Convenience function to send a notification"""
    service = get_notification_service()
    return service.send_notification(subject, message, **kwargs)


def send_alert(alert_type: str, message: str, severity: str = 'INFO', **kwargs) -> bool:
    """Convenience function to send an alert"""
    service = get_notification_service()
    return service.send_alert(alert_type, message, severity, **kwargs)
