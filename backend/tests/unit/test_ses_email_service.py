"""
Unit tests for SES Email Service

Tests the SESEmailService class with mocked boto3 SES client.
"""

import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from services.ses_email_service import SESEmailService


@pytest.fixture
def mock_ses_client():
    """Create a mocked SES client"""
    with patch('services.ses_email_service.boto3') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.send_email.return_value = {'MessageId': 'test-message-id-123'}
        yield mock_client


@pytest.fixture
def ses_service(mock_ses_client):
    """Create SESEmailService with mocked client"""
    with patch.dict('os.environ', {
        'SES_SENDER_EMAIL': 'support@jabaki.nl',
        'AWS_REGION': 'eu-west-1'
    }):
        service = SESEmailService()
    return service


# ============================================================================
# is_enabled()
# ============================================================================

class TestIsEnabled:

    def test_enabled_with_sender(self, ses_service):
        assert ses_service.is_enabled() is True

    def test_disabled_without_sender(self, mock_ses_client):
        with patch.dict('os.environ', {'SES_SENDER_EMAIL': ''}, clear=False):
            service = SESEmailService()
            assert service.is_enabled() is False


# ============================================================================
# send_email()
# ============================================================================

class TestSendEmail:

    def test_send_html_and_text(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test Subject',
            html_body='<h1>Hello</h1>',
            text_body='Hello'
        )

        assert result['success'] is True
        assert result['message_id'] == 'test-message-id-123'

        call_args = mock_ses_client.send_email.call_args
        assert call_args[1]['Destination'] == {'ToAddresses': ['user@example.com']}
        assert call_args[1]['Message']['Subject']['Data'] == 'Test Subject'
        assert 'Html' in call_args[1]['Message']['Body']
        assert 'Text' in call_args[1]['Message']['Body']

    def test_send_text_only(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test',
            text_body='Plain text only'
        )

        assert result['success'] is True
        body = mock_ses_client.send_email.call_args[1]['Message']['Body']
        assert 'Text' in body
        assert 'Html' not in body

    def test_send_html_only(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test',
            html_body='<p>HTML only</p>'
        )

        assert result['success'] is True
        body = mock_ses_client.send_email.call_args[1]['Message']['Body']
        assert 'Html' in body
        assert 'Text' not in body

    def test_correct_sender_and_reply_to(self, ses_service, mock_ses_client):
        ses_service.send_email(
            to_email='user@example.com',
            subject='Test',
            text_body='Hello'
        )

        call_args = mock_ses_client.send_email.call_args[1]
        assert call_args['Source'] == 'myAdmin <support@jabaki.nl>'
        assert call_args['ReplyToAddresses'] == ['support@jabaki.nl']

    def test_no_recipient_returns_error(self, ses_service):
        result = ses_service.send_email(
            to_email='',
            subject='Test',
            text_body='Hello'
        )

        assert result['success'] is False
        assert 'No recipient' in result['error']

    def test_no_body_returns_error(self, ses_service):
        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test'
        )

        assert result['success'] is False
        assert 'No email body' in result['error']

    def test_message_rejected_error(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = ClientError(
            {'Error': {'Code': 'MessageRejected', 'Message': 'Email address not verified'}},
            'SendEmail'
        )

        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test',
            text_body='Hello'
        )

        assert result['success'] is False
        assert 'MessageRejected' in result['error']

    def test_domain_not_verified_error(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = ClientError(
            {'Error': {'Code': 'MailFromDomainNotVerifiedException', 'Message': 'Domain not verified'}},
            'SendEmail'
        )

        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test',
            text_body='Hello'
        )

        assert result['success'] is False
        assert 'MailFromDomainNotVerifiedException' in result['error']

    def test_unexpected_exception(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = Exception('Network timeout')

        result = ses_service.send_email(
            to_email='user@example.com',
            subject='Test',
            text_body='Hello'
        )

        assert result['success'] is False
        assert 'Network timeout' in result['error']


# ============================================================================
# send_invitation()
# ============================================================================

class TestSendInvitation:

    def test_send_invitation_success(self, ses_service, mock_ses_client):
        result = ses_service.send_invitation(
            to_email='newuser@example.com',
            subject='Welcome to myAdmin - TestTenant Invitation',
            html_body='<h1>Welcome</h1>',
            text_body='Welcome'
        )

        assert result['success'] is True
        assert result['message_id'] == 'test-message-id-123'
        mock_ses_client.send_email.assert_called_once()

    def test_send_invitation_failure(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = ClientError(
            {'Error': {'Code': 'MessageRejected', 'Message': 'Rejected'}},
            'SendEmail'
        )

        result = ses_service.send_invitation(
            to_email='newuser@example.com',
            subject='Welcome',
            text_body='Welcome'
        )

        assert result['success'] is False


# ============================================================================
# Custom reply-to
# ============================================================================

class TestCustomReplyTo:

    def test_custom_reply_to(self, mock_ses_client):
        with patch.dict('os.environ', {
            'SES_SENDER_EMAIL': 'support@jabaki.nl',
            'SES_REPLY_TO_EMAIL': 'info@jabaki.nl',
            'AWS_REGION': 'eu-west-1'
        }):
            service = SESEmailService()

        service.send_email(
            to_email='user@example.com',
            subject='Test',
            text_body='Hello'
        )

        call_args = mock_ses_client.send_email.call_args[1]
        assert call_args['ReplyToAddresses'] == ['info@jabaki.nl']
