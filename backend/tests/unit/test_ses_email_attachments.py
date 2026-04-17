"""Unit tests for SESEmailService.send_email_with_attachments."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from services.ses_email_service import SESEmailService


@pytest.fixture
def ses_service():
    with patch('services.ses_email_service.boto3') as mock_boto:
        mock_client = Mock()
        mock_client.send_raw_email.return_value = {'MessageId': 'test-msg-123'}
        mock_boto.client.return_value = mock_client

        svc = SESEmailService.__new__(SESEmailService)
        svc.region = 'eu-west-1'
        svc.sender = 'test@example.com'
        svc.reply_to = 'test@example.com'
        svc.configuration_set = ''
        svc.client = mock_client
        yield svc, mock_client


# ── send_email_with_attachments ─────────────────────────────


def test_send_email_with_attachments_success_returns_message_id(ses_service):
    svc, mock_client = ses_service
    result = svc.send_email_with_attachments(
        to_email='recipient@test.com',
        subject='Invoice INV-2026-0001',
        html_body='<p>See attached</p>',
        attachments=[{
            'filename': 'INV-2026-0001.pdf',
            'content': b'%PDF-fake-content',
            'content_type': 'application/pdf',
        }],
    )
    assert result['success'] is True
    assert result['message_id'] == 'test-msg-123'
    mock_client.send_raw_email.assert_called_once()


def test_send_email_with_attachments_mime_contains_attachment(ses_service):
    svc, mock_client = ses_service
    svc.send_email_with_attachments(
        to_email='recipient@test.com',
        subject='Test',
        html_body='<p>Body</p>',
        attachments=[{
            'filename': 'invoice.pdf',
            'content': b'%PDF-data',
            'content_type': 'application/pdf',
        }],
    )
    raw_msg = mock_client.send_raw_email.call_args[1]['RawMessage']['Data']
    assert 'invoice.pdf' in raw_msg


def test_send_email_with_attachments_bcc_included_in_destinations(ses_service):
    svc, mock_client = ses_service
    svc.send_email_with_attachments(
        to_email='recipient@test.com',
        subject='Test',
        html_body='<p>Body</p>',
        attachments=[],
        bcc=['admin@test.com'],
    )
    destinations = mock_client.send_raw_email.call_args[1]['Destinations']
    assert 'admin@test.com' in destinations
    assert 'recipient@test.com' in destinations


def test_send_email_with_attachments_multiple_attachments(ses_service):
    svc, mock_client = ses_service
    svc.send_email_with_attachments(
        to_email='recipient@test.com',
        subject='Test',
        html_body='<p>Body</p>',
        attachments=[
            {'filename': 'invoice.pdf', 'content': b'pdf-data', 'content_type': 'application/pdf'},
            {'filename': 'timesheet.xlsx', 'content': b'xlsx-data', 'content_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},
        ],
    )
    raw_msg = mock_client.send_raw_email.call_args[1]['RawMessage']['Data']
    assert 'invoice.pdf' in raw_msg
    assert 'timesheet.xlsx' in raw_msg


def test_send_email_with_attachments_no_recipient_returns_error(ses_service):
    svc, _ = ses_service
    result = svc.send_email_with_attachments(
        to_email='',
        subject='Test',
        html_body='<p>Body</p>',
        attachments=[],
    )
    assert result['success'] is False
    assert 'No recipient' in result['error']


def test_send_email_with_attachments_ses_error_returns_error(ses_service):
    svc, mock_client = ses_service
    from botocore.exceptions import ClientError
    mock_client.send_raw_email.side_effect = ClientError(
        {'Error': {'Code': 'MessageRejected', 'Message': 'Email rejected'}},
        'SendRawEmail',
    )
    result = svc.send_email_with_attachments(
        to_email='recipient@test.com',
        subject='Test',
        html_body='<p>Body</p>',
        attachments=[],
    )
    assert result['success'] is False
    assert 'MessageRejected' in result['error']


@patch('services.ses_email_service._get_email_log')
def test_send_email_with_attachments_logs_sent_email(mock_log_factory, ses_service):
    svc, _ = ses_service
    mock_log = Mock()
    mock_log_factory.return_value = mock_log

    svc.send_email_with_attachments(
        to_email='recipient@test.com',
        subject='Invoice',
        html_body='<p>Body</p>',
        attachments=[],
        email_type='invoice',
        administration='T1',
        sent_by='user@test.com',
    )
    mock_log.log_sent.assert_called_once()
