"""
Integration tests for aws_notifications.py

Tests SNS publish with valid messages, error handling when SNS fails,
and message formatting for different notification types.

Validates: Requirements 4.6, 8.2, 8.4
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


@pytest.fixture
def mock_sns():
    """Mock boto3 SNS client for aws_notifications module."""
    with patch('aws_notifications.boto3.client') as mock_client:
        mock_sns_client = MagicMock()
        mock_client.return_value = mock_sns_client
        mock_sns_client.publish.return_value = {'MessageId': 'test-msg-id-123'}
        yield mock_sns_client


@pytest.fixture
def notification_service(mock_env, mock_sns):
    """Create AWSNotificationService with mocked SNS and env."""
    mock_env['SNS_TOPIC_ARN'] = 'arn:aws:sns:eu-west-1:123456789:test-topic'
    with patch.dict('os.environ', {'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123456789:test-topic'}, clear=False):
        from aws_notifications import AWSNotificationService
        service = AWSNotificationService(topic_arn='arn:aws:sns:eu-west-1:123456789:test-topic')
    return service


@pytest.fixture
def disabled_service():
    """Create AWSNotificationService with no topic ARN (disabled)."""
    env_copy = os.environ.copy()
    env_copy.pop('SNS_TOPIC_ARN', None)
    with patch.dict(os.environ, env_copy, clear=True):
        with patch('aws_notifications.boto3.client') as mock_client:
            from aws_notifications import AWSNotificationService
            service = AWSNotificationService(topic_arn=None)
    return service


class TestIsEnabled:
    """Tests for AWSNotificationService.is_enabled method."""

    def test_is_enabled_returns_true_when_configured(self, notification_service):
        """Test is_enabled returns True when topic_arn and sns_client are set."""
        assert notification_service.is_enabled() is True

    def test_is_enabled_returns_false_when_no_topic_arn(self, disabled_service):
        """Test is_enabled returns False when topic_arn is not configured."""
        assert disabled_service.is_enabled() is False


class TestSendNotification:
    """Tests for AWSNotificationService.send_notification method."""

    def test_send_notification_success_returns_true(self, notification_service, mock_sns):
        """Test send_notification publishes to SNS and returns True."""
        result = notification_service.send_notification(
            subject='Test Subject',
            message='Test message body'
        )

        assert result is True
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert call_kwargs['TopicArn'] == 'arn:aws:sns:eu-west-1:123456789:test-topic'
        assert call_kwargs['Subject'] == 'Test Subject'
        assert call_kwargs['Message'] == 'Test message body'

    def test_send_notification_disabled_returns_false(self, disabled_service):
        """Test send_notification returns False when service is disabled."""
        result = disabled_service.send_notification(
            subject='Test Subject',
            message='Test message body'
        )

        assert result is False

    def test_send_notification_client_error_returns_false(self, notification_service, mock_sns):
        """Test send_notification returns False on ClientError."""
        mock_sns.publish.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameter', 'Message': 'Invalid topic'}},
            'Publish'
        )

        result = notification_service.send_notification(
            subject='Test Subject',
            message='Test message body'
        )

        assert result is False

    def test_send_notification_generic_exception_returns_false(self, notification_service, mock_sns):
        """Test send_notification returns False on generic exception."""
        mock_sns.publish.side_effect = Exception('Network timeout')

        result = notification_service.send_notification(
            subject='Test Subject',
            message='Test message body'
        )

        assert result is False

    def test_send_notification_truncates_subject_to_100_chars(self, notification_service, mock_sns):
        """Test send_notification truncates subject to 100 characters."""
        long_subject = 'A' * 150

        notification_service.send_notification(
            subject=long_subject,
            message='Test message'
        )

        call_kwargs = mock_sns.publish.call_args[1]
        assert len(call_kwargs['Subject']) == 100
        assert call_kwargs['Subject'] == 'A' * 100

    def test_send_notification_adds_timestamp_attribute(self, notification_service, mock_sns):
        """Test send_notification adds timestamp to message attributes."""
        notification_service.send_notification(
            subject='Test Subject',
            message='Test message'
        )

        call_kwargs = mock_sns.publish.call_args[1]
        attrs = call_kwargs['MessageAttributes']
        assert 'timestamp' in attrs
        assert attrs['timestamp']['DataType'] == 'String'
        assert len(attrs['timestamp']['StringValue']) > 0


class TestSendAlert:
    """Tests for AWSNotificationService.send_alert method."""

    def test_send_alert_formats_message_correctly(self, notification_service, mock_sns):
        """Test send_alert formats message with type, severity, and time."""
        result = notification_service.send_alert(
            alert_type='Performance',
            message='High CPU usage detected',
            severity='WARNING'
        )

        assert result is True
        call_kwargs = mock_sns.publish.call_args[1]
        assert '[WARNING]' in call_kwargs['Subject']
        assert 'Performance' in call_kwargs['Subject']
        assert 'High CPU usage detected' in call_kwargs['Message']
        assert 'Severity: WARNING' in call_kwargs['Message']
        assert 'Type: Performance' in call_kwargs['Message']


class TestSendPerformanceAlert:
    """Tests for AWSNotificationService.send_performance_alert method."""

    def test_send_performance_alert_formats_with_metric_details(self, notification_service, mock_sns):
        """Test send_performance_alert includes metric name, value, and threshold."""
        result = notification_service.send_performance_alert(
            metric_name='response_time',
            current_value=5.0,
            threshold=2.0,
            details='API endpoint /users'
        )

        assert result is True
        call_kwargs = mock_sns.publish.call_args[1]
        assert 'response_time' in call_kwargs['Message']
        assert '5.00' in call_kwargs['Message']
        assert '2.00' in call_kwargs['Message']
        assert 'API endpoint /users' in call_kwargs['Message']
        # Should use WARNING severity
        assert '[WARNING]' in call_kwargs['Subject']


class TestSendErrorNotification:
    """Tests for AWSNotificationService.send_error_notification method."""

    def test_send_error_notification_formats_with_error_details(self, notification_service, mock_sns):
        """Test send_error_notification includes error type and message."""
        result = notification_service.send_error_notification(
            error_type='DatabaseError',
            error_message='Connection refused',
            stack_trace='Traceback (most recent call last):\n  File "app.py"'
        )

        assert result is True
        call_kwargs = mock_sns.publish.call_args[1]
        assert 'DatabaseError' in call_kwargs['Message']
        assert 'Connection refused' in call_kwargs['Message']
        assert 'Traceback' in call_kwargs['Message']
        # Should use ERROR severity
        assert '[ERROR]' in call_kwargs['Subject']


class TestSendSecurityAlert:
    """Tests for AWSNotificationService.send_security_alert method."""

    def test_send_security_alert_formats_with_severity_critical(self, notification_service, mock_sns):
        """Test send_security_alert uses CRITICAL severity."""
        result = notification_service.send_security_alert(
            event_type='Unauthorized Access',
            description='Multiple failed login attempts',
            source_ip='192.168.1.100',
            user='attacker@example.com'
        )

        assert result is True
        call_kwargs = mock_sns.publish.call_args[1]
        assert '[CRITICAL]' in call_kwargs['Subject']
        assert 'Security' in call_kwargs['Subject']
        assert 'Unauthorized Access' in call_kwargs['Message']
        assert 'Multiple failed login attempts' in call_kwargs['Message']


class TestSendBusinessNotification:
    """Tests for AWSNotificationService.send_business_notification method."""

    def test_send_business_notification_formats_with_title_and_data(self, notification_service, mock_sns):
        """Test send_business_notification includes title and data dict."""
        result = notification_service.send_business_notification(
            title='New Booking',
            message='A new booking has been received',
            data={'booking_id': 'BK-001', 'amount': '250.00'}
        )

        assert result is True
        call_kwargs = mock_sns.publish.call_args[1]
        assert 'New Booking' in call_kwargs['Subject']
        assert 'A new booking has been received' in call_kwargs['Message']
        assert 'booking_id' in call_kwargs['Message']
        assert 'BK-001' in call_kwargs['Message']
        assert 'amount' in call_kwargs['Message']
        assert '250.00' in call_kwargs['Message']


class TestTestNotification:
    """Tests for AWSNotificationService.test_notification method."""

    def test_test_notification_sends_test_message(self, notification_service, mock_sns):
        """Test test_notification sends a test message via SNS."""
        result = notification_service.test_notification()

        assert result is True
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        assert 'Test' in call_kwargs['Subject']
        assert 'test notification' in call_kwargs['Message'].lower()
