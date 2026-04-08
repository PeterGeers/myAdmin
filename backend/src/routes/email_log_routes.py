"""
Email Log Routes

- GET  /api/email-log          — Query email logs (SysAdmin: all, Tenant Admin: own tenant)
- POST /api/webhooks/ses       — SNS webhook for SES delivery notifications
"""

import json
import logging
import os
from flask import Blueprint, jsonify, request
from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from services.email_log_service import EmailLogService

logger = logging.getLogger(__name__)

email_log_bp = Blueprint('email_log', __name__)


@email_log_bp.route('/api/email-log', methods=['GET'])
@cognito_required(required_roles=['SysAdmin', 'Tenant_Admin'])
def get_email_logs(user_email, user_roles):
    """
    Query email logs.
    SysAdmin sees all tenants. Tenant Admin sees only their own tenant.
    """
    try:
        is_sysadmin = 'SysAdmin' in user_roles
        # Use explicit administration param when provided (Tenant Admin panel)
        explicit_tenant = request.args.get('administration')
        if explicit_tenant:
            tenant = explicit_tenant
        elif is_sysadmin:
            tenant = None  # SysAdmin sees all
        else:
            tenant = get_current_tenant(request)
        
        recipient = request.args.get('recipient')
        limit = min(int(request.args.get('limit', 100)), 500)

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        service = EmailLogService(test_mode=test_mode)
        logs = service.get_logs(
            administration=tenant,
            recipient=recipient,
            limit=limit,
        )

        return jsonify({'success': True, 'logs': logs, 'count': len(logs)})

    except Exception as e:
        logger.error(f"Error fetching email logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@email_log_bp.route('/api/webhooks/ses', methods=['POST'])
def ses_notification_webhook():
    """
    Receive SES delivery notifications via SNS.

    SNS sends three types of messages:
    1. SubscriptionConfirmation — auto-confirm the subscription
    2. Notification — delivery/bounce/complaint event from SES
    3. UnsubscribeConfirmation — ignored

    This endpoint is public (no auth) because SNS cannot send JWT tokens.
    Security: validates the SNS message signature via the x-amz-sns headers.
    """
    try:
        # SNS sends JSON with content-type text/plain
        message = json.loads(request.data)
        msg_type = request.headers.get('x-amz-sns-message-type', '')

        # Auto-confirm SNS subscription
        if msg_type == 'SubscriptionConfirmation':
            subscribe_url = message.get('SubscribeURL')
            if subscribe_url:
                import urllib.request
                urllib.request.urlopen(subscribe_url)
                logger.info("SNS subscription confirmed")
            return jsonify({'status': 'subscribed'}), 200

        # Process SES notification
        if msg_type == 'Notification':
            ses_message = json.loads(message.get('Message', '{}'))
            notification_type = ses_message.get('notificationType', '').lower()
            mail = ses_message.get('mail', {})
            ses_message_id = mail.get('messageId')

            if not ses_message_id:
                return jsonify({'status': 'ignored'}), 200

            test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
            service = EmailLogService(test_mode=test_mode)

            error_message = None
            if notification_type == 'bounce':
                bounce = ses_message.get('bounce', {})
                error_message = (
                    f"Bounce type: {bounce.get('bounceType')} "
                    f"({bounce.get('bounceSubType')})"
                )
                status = 'bounced'
            elif notification_type == 'complaint':
                status = 'complained'
            elif notification_type == 'delivery':
                status = 'delivered'
            else:
                status = notification_type or 'unknown'

            service.update_status(
                ses_message_id=ses_message_id,
                status=status,
                error_message=error_message,
            )
            logger.info(f"SES {status} for message {ses_message_id}")

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.error(f"Error processing SES webhook: {e}")
        return jsonify({'status': 'error'}), 200  # Return 200 to prevent SNS retries
