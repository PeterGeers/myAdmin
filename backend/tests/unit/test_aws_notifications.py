"""
Unit tests for AWS Notification Service

Tests the AWSNotificationService class with mocked boto3 SNS client.
"""

import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from aws_notifications import (
    AWSNotificationService,
    get_notification_service,
    send_notification,
    send_alert,
)


@pytest.fixture
def mock_sns_client():
    """Create a mocked SNS client"""
    with patch('aws_notifications.boto3') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.publish.return_value = {'MessageId': 'test-msg-id-abc123'}
        yield mock_client


@pytest.fixture
def notification_service(mock_sns_client):
    """Create AWSNotificationService with mocked client"""
    with patch.dict('os.environ', {
        'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123456789:myAdmin-alerts',
        'AWS_REGION': 'eu-west-1'
    }):
        service = AWSNotificationService()
    return service


@pytest.fixture
def disabled_service():
    """Create AWSNotificationService without topic ARN (disabled)"""
    with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}, clear=False):
        service = AWSNotificationService(topic_arn=None)
    return service


# ============================================================================
# Initialization
# ============================================================================

class TestInitialization:

    def test_init_with_topic_arn(self, mock_sns_client):
        with patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}):
            service = AWSNotificationService(
                topic_arn='arn:aws:sns:eu-west-1:123:test-topic'
            )
        assert service.topic_arn == 'arn:aws:sns:eu-west-1:123:test-topic'
        assert service.region == 'eu-west-1'
        assert service.sns_client is not None

    def test_init_from_env(self, mock_sns_client):
        with patch.dict('os.environ', {
            'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123:env-topic',
            'AWS_REGION': 'eu-west-1'
        }):
            service = AWSNotificationService()
        assert service.topic_arn == 'arn:aws:sns:eu-west-1:123:env-topic'

    def test_init_without_topic_arn_disables_client(self):
        with patch.dict('os.environ', {'SNS_TOPIC_ARN': ''}, clear=False):
            service = AWSNotificationService(topic_arn=None)
        assert service.sns_client is None

    def test_init_handles_boto3_exception(self):
        with patch('aws_notifications.boto3') as mock_boto3:
            mock_boto3.client.side_effect = Exception('AWS credentials error')
            with patch.dict('os.environ', {
                'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123:topic',
                'AWS_REGION': 'eu-west-1'
            }):
                service = AWSNotificationService()
        assert service.sns_client is None


# ============================================================================
# is_enabled()
# ============================================================================

class TestIsEnabled:

    def test_enabled_when_client_and_arn_present(self, notification_service):
        assert notification_service.is_enabled() is True

    def test_disabled_when_no_client(self, disabled_service):
        assert disabled_service.is_enabled() is False


# ============================================================================
# send_notification()
# ============================================================================

class TestSendNotification:

    def test_send_basic_notification(self, notification_service, mock_sns_client):
        result = notification_service.send_notification(
            subject='Test Alert',
            message='Something happened'
        )

        assert result is True
        mock_sns_client.publish.assert_called_once()
        call_args = mock_sns_client.publish.call_args[1]
        assert call_args['TopicArn'] == 'arn:aws:sns:eu-west-1:123456789:myAdmin-alerts'
        assert call_args['Subject'] == 'Test Alert'
        assert call_args['Message'] == 'Something happened'

    def test_send_with_message_attributes(self, notification_service, mock_sns_client):
        result = notification_service.send_notification(
            subject='Alert',
            message='Details here',
            message_attributes={'type': 'error', 'source': 'backend'}
        )

        assert result is True
        call_args = mock_sns_client.publish.call_args[1]
        attrs = call_args['MessageAttributes']
        assert attrs['type'] == {'DataType': 'String', 'StringValue': 'error'}
        assert attrs['source'] == {'DataType': 'String', 'StringValue': 'backend'}
        assert 'timestamp' in attrs

    def test_subject_truncated_to_100_chars(self, notification_service, mock_sns_client):
        long_subject = 'A' * 150
        notification_service.send_notification(subject=long_subject, message='msg')

        call_args = mock_sns_client.publish.call_args[1]
        assert len(call_args['Subject']) == 100

    def test_returns_false_when_disabled(self, disabled_service):
        result = disabled_service.send_notification(
            subject='Test', message='Will not send'
        )
        assert result is False

    def test_returns_false_on_client_error(self, notification_service, mock_sns_client):
        mock_sns_client.publish.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameter', 'Message': 'Invalid topic'}},
            'Publish'
        )

        result = notification_service.send_notification(
            subject='Test', message='Error case'
        )
        assert result is False

    def test_returns_false_on_unexpected_exception(self, notification_service, mock_sns_client):
        mock_sns_client.publish.side_effect = Exception('Network timeout')

        result = notification_service.send_notification(
            subject='Test', message='Error case'
        )
        assert result is False


# ============================================================================
# send_alert()
# ============================================================================

class TestSendAlert:

    def test_send_alert_formats_subject(self, notification_service, mock_sns_client):
        notification_service.send_alert(
            alert_type='Performance',
            message='High CPU usage',
            severity='WARNING'
        )

        call_args = mock_sns_client.publish.call_args[1]
        assert '[WARNING] myAdmin Alert: Performance' in call_args['Subject']

    def test_send_alert_includes_details(self, notification_service, mock_sns_client):
        notification_service.send_alert(
            alert_type='Error',
            message='DB connection failed',
            severity='ERROR',
            details={'host': 'db.example.com', 'port': '3306'}
        )

        call_args = mock_sns_client.publish.call_args[1]
        assert 'host: db.example.com' in call_args['Message']
        assert 'port: 3306' in call_args['Message']

    def test_send_alert_default_severity_is_info(self, notification_service, mock_sns_client):
        notification_service.send_alert(
            alert_type='Info',
            message='Something noteworthy'
        )

        call_args = mock_sns_client.publish.call_args[1]
        assert '[INFO]' in call_args['Subject']

    def test_send_alert_includes_attributes(self, notification_service, mock_sns_client):
        notification_service.send_alert(
            alert_type='Security',
            message='Unauthorized access',
            severity='CRITICAL'
        )

        call_args = mock_sns_client.publish.call_args[1]
        attrs = call_args['MessageAttributes']
        assert attrs['alert_type'] == {'DataType': 'String', 'StringValue': 'Security'}
        assert attrs['severity'] == {'DataType': 'String', 'StringValue': 'CRITICAL'}
        assert attrs['application'] == {'DataType': 'String', 'StringValue': 'myAdmin'}


# ============================================================================
# send_performance_alert()
# ============================================================================

class TestSendPerformanceAlert:

    def test_sends_performance_alert(self, notification_service, mock_sns_client):
        result = notification_service.send_performance_alert(
            metric_name='response_time',
            current_value=5.5,
            threshold=2.0
        )

        assert result is True
        call_args = mock_sns_client.publish.call_args[1]
        assert 'response_time' in call_args['Message']
        assert '5.50' in call_args['Message']
        assert '2.00' in call_args['Message']

    def test_includes_optional_details(self, notification_service, mock_sns_client):
        notification_service.send_performance_alert(
            metric_name='memory',
            current_value=90.0,
            threshold=80.0,
            details='Consider scaling up'
        )

        call_args = mock_sns_client.publish.call_args[1]
        assert 'Consider scaling up' in call_args['Message']


# ============================================================================
# send_error_notification()
# ============================================================================

class TestSendErrorNotification:

    def test_sends_error_notification(self, notification_service, mock_sns_client):
        result = notification_service.send_error_notification(
            error_type='DatabaseError',
            error_message='Connection refused'
        )

        assert result is True
        call_args = mock_sns_client.publish.call_args[1]
        assert 'DatabaseError' in call_args['Message']
        assert 'Connection refused' in call_args['Message']

    def test_includes_stack_trace(self, notification_service, mock_sns_client):
        notification_service.send_error_notification(
            error_type='ValueError',
            error_message='Invalid input',
            stack_trace='Traceback:\n  File "app.py", line 10\n    raise ValueError'
        )

        call_args = mock_sns_client.publish.call_args[1]
        assert 'Traceback' in call_args['Message']


# ============================================================================
# send_security_alert()
# ============================================================================

class TestSendSecurityAlert:

    def test_sends_security_alert(self, notification_service, mock_sns_client):
        result = notification_service.send_security_alert(
            event_type='Failed Login',
            description='5 failed attempts'
        )

        assert result is True
        call_args = mock_sns_client.publish.call_args[1]
        assert '[CRITICAL]' in call_args['Subject']
        assert 'Security' in call_args['Subject']

    def test_includes_source_ip_and_user(self, notification_service, mock_sns_client):
        notification_service.send_security_alert(
            event_type='Unauthorized Access',
            description='Attempt to access admin panel',
            source_ip='192.168.1.100',
            user='attacker@example.com'
        )

        call_args = mock_sns_client.publish.call_args[1]
        attrs = call_args['MessageAttributes']
        # Details are passed as message_attributes via send_alert
        assert 'source_ip' in call_args['Message'] or 'source_ip' in str(attrs)


# ============================================================================
# send_business_notification()
# ============================================================================

class TestSendBusinessNotification:

    def test_sends_business_notification(self, notification_service, mock_sns_client):
        result = notification_service.send_business_notification(
            title='New Booking',
            message='A new booking was received for property X'
        )

        assert result is True
        call_args = mock_sns_client.publish.call_args[1]
        assert call_args['Subject'] == 'myAdmin: New Booking'
        assert 'New Booking' in call_args['Message']

    def test_includes_data(self, notification_service, mock_sns_client):
        notification_service.send_business_notification(
            title='Payment Received',
            message='Payment processed successfully',
            data={'amount': '€500.00', 'reference': 'INV-001'}
        )

        call_args = mock_sns_client.publish.call_args[1]
        assert 'amount: €500.00' in call_args['Message']
        assert 'reference: INV-001' in call_args['Message']


# ============================================================================
# test_notification()
# ============================================================================

class TestTestNotification:

    def test_sends_test_notification(self, notification_service, mock_sns_client):
        result = notification_service.test_notification()

        assert result is True
        call_args = mock_sns_client.publish.call_args[1]
        assert 'Test' in call_args['Subject']
        assert 'working correctly' in call_args['Message']


# ============================================================================
# Module-level convenience functions
# ============================================================================

class TestConvenienceFunctions:

    def test_get_notification_service_returns_singleton(self, mock_sns_client):
        with patch('aws_notifications._notification_service', None):
            with patch.dict('os.environ', {
                'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123:topic',
                'AWS_REGION': 'eu-west-1'
            }):
                svc1 = get_notification_service()
                svc2 = get_notification_service()
                assert svc1 is svc2

    def test_send_notification_convenience(self, mock_sns_client):
        with patch('aws_notifications._notification_service', None):
            with patch.dict('os.environ', {
                'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123:topic',
                'AWS_REGION': 'eu-west-1'
            }):
                result = send_notification('Subject', 'Message body')
                assert result is True
                mock_sns_client.publish.assert_called_once()

    def test_send_alert_convenience(self, mock_sns_client):
        with patch('aws_notifications._notification_service', None):
            with patch.dict('os.environ', {
                'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123:topic',
                'AWS_REGION': 'eu-west-1'
            }):
                result = send_alert('TestAlert', 'Alert message', 'WARNING')
                assert result is True
