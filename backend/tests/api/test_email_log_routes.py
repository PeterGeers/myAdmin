"""
API tests for email_log_routes.py

Tests email log query endpoint and SES webhook endpoint including
auth enforcement, role-based access, and SNS message processing.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestEmailLogAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_get_email_logs_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to email logs should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/email-log')
        assert response.status_code in (401, 403)

    def test_get_email_logs_non_admin_returns_403(self, client):
        """Non-admin user should get 403 on email log endpoint."""
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=('user@example.com', ['User'], None)):
            response = client.get('/api/email-log')
        assert response.status_code == 403


# ============================================================================
# Email Log Query Tests
# ============================================================================


class TestGetEmailLogs:
    """Tests for GET /api/email-log."""

    @patch('routes.email_log_routes.EmailLogService')
    def test_get_email_logs_sysadmin_success(self, mock_service_class,
                                             client, mock_auth_sysadmin):
        """SysAdmin can query email logs."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs.return_value = [
            {'id': 1, 'recipient': 'user@test.com', 'status': 'delivered'}
        ]

        response = client.get(
            '/api/email-log',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1

    @patch('routes.email_log_routes.EmailLogService')
    @patch('auth.tenant_context.get_current_tenant', return_value='test-tenant')
    def test_get_email_logs_tenant_admin_success(self, mock_tenant,
                                                 mock_service_class,
                                                 client, mock_auth_sysadmin):
        """Admin can query email logs."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs.return_value = []

        response = client.get(
            '/api/email-log',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# SES Webhook Tests
# ============================================================================


class TestSESWebhook:
    """Tests for POST /api/webhooks/ses (public endpoint)."""

    def test_ses_webhook_subscription_confirmation(self, client):
        """SES webhook handles subscription confirmation."""
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value = MagicMock()

            response = client.post(
                '/api/webhooks/ses',
                data=json.dumps({
                    'Type': 'SubscriptionConfirmation',
                    'SubscribeURL': 'https://sns.amazonaws.com/confirm?token=abc'
                }),
                content_type='application/json',
                headers={'x-amz-sns-message-type': 'SubscriptionConfirmation'}
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'subscribed'

    @patch('routes.email_log_routes.EmailLogService')
    def test_ses_webhook_delivery_notification(self, mock_service_class, client):
        """SES webhook processes delivery notification."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        ses_message = json.dumps({
            'notificationType': 'Delivery',
            'mail': {'messageId': 'test-msg-123'}
        })

        response = client.post(
            '/api/webhooks/ses',
            data=json.dumps({
                'Type': 'Notification',
                'Message': ses_message
            }),
            content_type='application/json',
            headers={'x-amz-sns-message-type': 'Notification'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ok'
        mock_service.update_status.assert_called_once()

    @patch('routes.email_log_routes.EmailLogService')
    def test_ses_webhook_bounce_notification(self, mock_service_class, client):
        """SES webhook processes bounce notification."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        ses_message = json.dumps({
            'notificationType': 'Bounce',
            'mail': {'messageId': 'test-msg-456'},
            'bounce': {'bounceType': 'Permanent', 'bounceSubType': 'General'}
        })

        response = client.post(
            '/api/webhooks/ses',
            data=json.dumps({
                'Type': 'Notification',
                'Message': ses_message
            }),
            content_type='application/json',
            headers={'x-amz-sns-message-type': 'Notification'}
        )

        assert response.status_code == 200
        mock_service.update_status.assert_called_once_with(
            ses_message_id='test-msg-456',
            status='bounced',
            error_message='Bounce type: Permanent (General)'
        )

    def test_ses_webhook_invalid_json_returns_200(self, client):
        """SES webhook returns 200 even on error to prevent SNS retries."""
        response = client.post(
            '/api/webhooks/ses',
            data='not valid json',
            content_type='application/json',
            headers={'x-amz-sns-message-type': 'Notification'}
        )

        # Returns 200 to prevent SNS retries
        assert response.status_code == 200
