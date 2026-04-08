"""
SES Email Service

Sends user-facing emails (invitations, password resets) via AWS SES.
Admin/system notifications remain on SNS (aws_notifications.py).
"""

import os
import boto3
import logging
from botocore.exceptions import ClientError
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Lazy-loaded email log service to avoid circular imports
_email_log_service = None


def _get_email_log():
    """Lazy-load EmailLogService"""
    global _email_log_service
    if _email_log_service is None:
        from services.email_log_service import EmailLogService
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        _email_log_service = EmailLogService(test_mode=test_mode)
    return _email_log_service


class SESEmailService:
    """Send emails directly to recipients via AWS SES"""

    def __init__(self, region: Optional[str] = None):
        self.region = region or os.getenv('AWS_REGION', 'eu-west-1')
        self.sender = os.getenv('SES_SENDER_EMAIL', 'support@jabaki.nl')
        self.reply_to = os.getenv('SES_REPLY_TO_EMAIL', self.sender)
        self.configuration_set = os.getenv('SES_CONFIGURATION_SET', '')
        self.client = boto3.client('ses', region_name=self.region)

    def is_enabled(self) -> bool:
        """Check if SES is configured"""
        return bool(self.sender)

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: Optional[str] = None,
        text_body: Optional[str] = None,
        email_type: Optional[str] = None,
        administration: Optional[str] = None,
        sent_by: Optional[str] = None,
    ) -> Dict:
        """
        Send email to a specific recipient.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML content (optional)
            text_body: Plain text content (optional, used as fallback)
            email_type: Type for logging (invitation, tenant_added, etc.)
            administration: Tenant for logging
            sent_by: Admin email who triggered the send

        Returns:
            Dict with 'success' and 'message_id' or 'error'
        """
        if not to_email:
            return {'success': False, 'error': 'No recipient email provided'}

        if not html_body and not text_body:
            return {'success': False, 'error': 'No email body provided'}

        try:
            body = {}
            if html_body:
                body['Html'] = {'Data': html_body, 'Charset': 'UTF-8'}
            if text_body:
                body['Text'] = {'Data': text_body, 'Charset': 'UTF-8'}

            send_kwargs = {
                'Source': f'myAdmin <{self.sender}>',
                'Destination': {'ToAddresses': [to_email]},
                'Message': {
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': body
                },
                'ReplyToAddresses': [self.reply_to],
            }
            if self.configuration_set:
                send_kwargs['ConfigurationSetName'] = self.configuration_set

            response = self.client.send_email(**send_kwargs)

            message_id = response.get('MessageId')
            logger.info(f"Email sent to {to_email}, MessageId: {message_id}")

            # Log to email_log table
            if email_type:
                try:
                    _get_email_log().log_sent(
                        recipient=to_email,
                        email_type=email_type,
                        administration=administration,
                        ses_message_id=message_id,
                        subject=subject,
                        sent_by=sent_by,
                    )
                except Exception as log_err:
                    logger.warning(f"Email sent but logging failed: {log_err}")

            return {'success': True, 'message_id': message_id}

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(f"SES error sending to {to_email}: [{error_code}] {error_msg}")

            # Log failure
            if email_type:
                try:
                    _get_email_log().log_failed(
                        recipient=to_email,
                        email_type=email_type,
                        administration=administration,
                        error_message=f"{error_code}: {error_msg}",
                        sent_by=sent_by,
                    )
                except Exception as log_err:
                    logger.warning(f"Email failed and logging also failed: {log_err}")

            return {'success': False, 'error': f"{error_code}: {error_msg}"}

        except Exception as e:
            logger.error(f"Unexpected error sending email to {to_email}: {e}")
            return {'success': False, 'error': str(e)}

    def send_invitation(
        self,
        to_email: str,
        subject: str,
        html_body: Optional[str] = None,
        text_body: Optional[str] = None,
        administration: Optional[str] = None,
        sent_by: Optional[str] = None,
    ) -> Dict:
        """Send invitation email with invitation-specific logging."""
        logger.info(f"Sending invitation email to {to_email}")
        result = self.send_email(
            to_email, subject, html_body, text_body,
            email_type='invitation',
            administration=administration,
            sent_by=sent_by,
        )
        if result['success']:
            logger.info(f"Invitation delivered to {to_email}")
        else:
            logger.warning(f"Invitation failed for {to_email}: {result.get('error')}")
        return result
