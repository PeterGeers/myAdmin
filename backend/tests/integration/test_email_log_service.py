"""
Integration tests for email_log_service.py

Tests email logging, delivery status updates, and query filtering.
Validates: Requirements 4.2, 8.2, 8.4
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def email_service(mock_db):
    """Create EmailLogService with mocked DatabaseManager."""
    with patch('services.email_log_service.DatabaseManager', return_value=mock_db):
        from services.email_log_service import EmailLogService
        service = EmailLogService(test_mode=True)
    return service


class TestLogSent:
    """Tests for EmailLogService.log_sent method."""

    def test_log_sent_all_fields_returns_result(self, mock_db, email_service):
        """Test log_sent with all fields populated returns execute_query result."""
        mock_db.execute_query.return_value = 1

        result = email_service.log_sent(
            recipient='user@example.com',
            email_type='invoice',
            administration='tenant1',
            ses_message_id='ses-msg-123',
            subject='Your Invoice',
            sent_by='admin@example.com',
        )

        assert result == 1
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert call_args[1]['fetch'] is False
        assert call_args[1]['commit'] is True
        # Verify params contain all values
        params = call_args[0][1]
        assert 'user@example.com' in params
        assert 'invoice' in params
        assert 'tenant1' in params
        assert 'ses-msg-123' in params
        assert 'Your Invoice' in params
        assert 'admin@example.com' in params

    def test_log_sent_optional_fields_none_returns_result(self, mock_db, email_service):
        """Test log_sent with optional fields as None still succeeds."""
        mock_db.execute_query.return_value = 1

        result = email_service.log_sent(
            recipient='user@example.com',
            email_type='reminder',
            administration='tenant1',
            ses_message_id='ses-msg-456',
            subject=None,
            sent_by=None,
        )

        assert result == 1
        mock_db.execute_query.assert_called_once()
        params = mock_db.execute_query.call_args[0][1]
        # subject and sent_by are None in the params tuple
        assert params[-1] is None  # sent_by
        assert params[-2] is None  # subject

    def test_log_sent_db_exception_returns_none(self, mock_db, email_service):
        """Test log_sent returns None when DB raises an exception."""
        mock_db.execute_query.side_effect = Exception("DB connection failed")

        result = email_service.log_sent(
            recipient='user@example.com',
            email_type='invoice',
            administration='tenant1',
            ses_message_id='ses-msg-789',
        )

        assert result is None


class TestLogFailed:
    """Tests for EmailLogService.log_failed method."""

    def test_log_failed_with_error_message_returns_result(self, mock_db, email_service):
        """Test log_failed stores error message and returns result."""
        mock_db.execute_query.return_value = 1

        result = email_service.log_failed(
            recipient='user@example.com',
            email_type='invoice',
            administration='tenant1',
            error_message='SES rate limit exceeded',
            sent_by='admin@example.com',
        )

        assert result == 1
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert call_args[1]['fetch'] is False
        assert call_args[1]['commit'] is True
        params = call_args[0][1]
        assert 'user@example.com' in params
        assert 'invoice' in params
        assert 'tenant1' in params
        assert 'SES rate limit exceeded' in params
        assert 'admin@example.com' in params

    def test_log_failed_db_exception_returns_none(self, mock_db, email_service):
        """Test log_failed returns None when DB raises an exception."""
        mock_db.execute_query.side_effect = Exception("DB timeout")

        result = email_service.log_failed(
            recipient='user@example.com',
            email_type='reminder',
            administration='tenant1',
            error_message='Connection refused',
        )

        assert result is None


class TestUpdateStatus:
    """Tests for EmailLogService.update_status method."""

    def test_update_status_success_returns_true(self, mock_db, email_service):
        """Test update_status returns True on successful update."""
        mock_db.execute_query.return_value = None

        result = email_service.update_status(
            ses_message_id='ses-msg-123',
            status='delivered',
            error_message=None,
        )

        assert result is True
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert call_args[1]['fetch'] is False
        assert call_args[1]['commit'] is True
        params = call_args[0][1]
        assert 'delivered' in params
        assert 'ses-msg-123' in params

    def test_update_status_with_error_message_returns_true(self, mock_db, email_service):
        """Test update_status with error_message stores it correctly."""
        mock_db.execute_query.return_value = None

        result = email_service.update_status(
            ses_message_id='ses-msg-456',
            status='bounced',
            error_message='Mailbox full',
        )

        assert result is True
        params = mock_db.execute_query.call_args[0][1]
        assert 'bounced' in params
        assert 'Mailbox full' in params
        assert 'ses-msg-456' in params

    def test_update_status_db_exception_returns_false(self, mock_db, email_service):
        """Test update_status returns False when DB raises an exception."""
        mock_db.execute_query.side_effect = Exception("DB error")

        result = email_service.update_status(
            ses_message_id='ses-msg-789',
            status='delivered',
        )

        assert result is False


class TestGetLogs:
    """Tests for EmailLogService.get_logs method."""

    def test_get_logs_no_filters_returns_all(self, mock_db, email_service):
        """Test get_logs with no filters returns all rows."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'recipient': 'a@example.com', 'status': 'sent'},
            {'id': 2, 'recipient': 'b@example.com', 'status': 'delivered'},
        ]

        result = email_service.get_logs()

        assert len(result) == 2
        assert result[0]['recipient'] == 'a@example.com'
        assert result[1]['recipient'] == 'b@example.com'
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert call_args[1]['fetch'] is True
        # No WHERE clause filters, only LIMIT
        query = call_args[0][0]
        assert 'WHERE' not in query
        params = call_args[0][1]
        assert params == (100,)

    def test_get_logs_filtered_by_administration(self, mock_db, email_service):
        """Test get_logs filters by administration when provided."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'recipient': 'a@example.com', 'administration': 'tenant1'},
        ]

        result = email_service.get_logs(administration='tenant1')

        assert len(result) == 1
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'administration = %s' in query
        params = call_args[0][1]
        assert 'tenant1' in params

    def test_get_logs_filtered_by_recipient(self, mock_db, email_service):
        """Test get_logs filters by recipient when provided."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'recipient': 'user@example.com', 'status': 'sent'},
        ]

        result = email_service.get_logs(recipient='user@example.com')

        assert len(result) == 1
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'recipient = %s' in query
        params = call_args[0][1]
        assert 'user@example.com' in params

    def test_get_logs_limit_capped_at_500(self, mock_db, email_service):
        """Test get_logs caps limit at 500 even if higher value requested."""
        mock_db.execute_query.return_value = []

        email_service.get_logs(limit=1000)

        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        # The last param is the limit, capped at 500
        assert params[-1] == 500

    def test_get_logs_db_exception_returns_empty_list(self, mock_db, email_service):
        """Test get_logs returns empty list when DB raises an exception."""
        mock_db.execute_query.side_effect = Exception("Query failed")

        result = email_service.get_logs()

        assert result == []

    def test_get_logs_both_filters_combined(self, mock_db, email_service):
        """Test get_logs with both administration and recipient filters."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'recipient': 'user@example.com', 'administration': 'tenant1'},
        ]

        result = email_service.get_logs(administration='tenant1', recipient='user@example.com')

        assert len(result) == 1
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'administration = %s' in query
        assert 'recipient = %s' in query
        params = call_args[0][1]
        assert 'tenant1' in params
        assert 'user@example.com' in params
