"""
Unit tests for EmailLogService

Tests log retrieval and filtering capabilities with mocked DatabaseManager.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.email_log_service import EmailLogService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mocked DatabaseManager."""
    db = Mock()
    db.execute_query = Mock(return_value=[])
    return db


@pytest.fixture
def service(mock_db):
    """Create EmailLogService with mocked DatabaseManager."""
    with patch('services.email_log_service.DatabaseManager', return_value=mock_db):
        svc = EmailLogService(test_mode=True)
    return svc


# ============================================================================
# get_logs — basic retrieval
# ============================================================================

@pytest.mark.unit
class TestGetLogsRetrieval:
    """Test get_logs retrieval functionality."""

    def test_returns_all_logs_when_no_filters(self, service, mock_db):
        """get_logs with no filters returns all rows up to limit."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'recipient': 'a@test.com', 'email_type': 'invoice',
             'administration': 'tenant1', 'status': 'sent',
             'ses_message_id': 'msg-1', 'subject': 'Invoice #1',
             'sent_by': 'user@test.com', 'error_message': None,
             'created_at': '2024-01-01 10:00:00', 'updated_at': None},
            {'id': 2, 'recipient': 'b@test.com', 'email_type': 'verification',
             'administration': 'tenant2', 'status': 'delivered',
             'ses_message_id': 'msg-2', 'subject': 'Verify',
             'sent_by': 'system', 'error_message': None,
             'created_at': '2024-01-01 09:00:00', 'updated_at': None},
        ]

        result = service.get_logs()

        assert len(result) == 2
        assert result[0]['recipient'] == 'a@test.com'
        assert result[1]['recipient'] == 'b@test.com'
        # Default limit of 100 applied
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert call_args[0][1] == (100,)

    def test_returns_empty_list_when_no_rows(self, service, mock_db):
        """get_logs returns empty list when database has no matching rows."""
        mock_db.execute_query.return_value = []

        result = service.get_logs()

        assert result == []

    def test_returns_empty_list_when_query_returns_none(self, service, mock_db):
        """get_logs returns empty list when execute_query returns None."""
        mock_db.execute_query.return_value = None

        result = service.get_logs()

        assert result == []

    def test_returns_empty_list_on_exception(self, service, mock_db):
        """get_logs returns empty list when database raises an exception."""
        mock_db.execute_query.side_effect = Exception("Connection lost")

        result = service.get_logs()

        assert result == []

    def test_custom_limit_is_applied(self, service, mock_db):
        """get_logs uses the provided limit parameter."""
        mock_db.execute_query.return_value = []

        service.get_logs(limit=50)

        call_args = mock_db.execute_query.call_args
        assert call_args[0][1] == (50,)

    def test_limit_is_capped_at_500(self, service, mock_db):
        """get_logs caps the limit at 500 even if a larger value is passed."""
        mock_db.execute_query.return_value = []

        service.get_logs(limit=1000)

        call_args = mock_db.execute_query.call_args
        assert call_args[0][1] == (500,)

    def test_query_orders_by_created_at_desc(self, service, mock_db):
        """get_logs orders results by created_at DESC."""
        mock_db.execute_query.return_value = []

        service.get_logs()

        query = mock_db.execute_query.call_args[0][0]
        assert 'ORDER BY created_at DESC' in query


# ============================================================================
# get_logs — filtering
# ============================================================================

@pytest.mark.unit
class TestGetLogsFiltering:
    """Test get_logs filtering capabilities."""

    def test_filter_by_administration(self, service, mock_db):
        """get_logs filters by administration (tenant)."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'recipient': 'a@test.com', 'email_type': 'invoice',
             'administration': 'tenant1', 'status': 'sent',
             'ses_message_id': 'msg-1', 'subject': 'Invoice',
             'sent_by': 'user@test.com', 'error_message': None,
             'created_at': '2024-01-01', 'updated_at': None},
        ]

        result = service.get_logs(administration='tenant1')

        assert len(result) == 1
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert 'tenant1' in params

    def test_filter_by_recipient(self, service, mock_db):
        """get_logs filters by recipient email."""
        mock_db.execute_query.return_value = [
            {'id': 2, 'recipient': 'b@test.com', 'email_type': 'verification',
             'administration': 'tenant2', 'status': 'delivered',
             'ses_message_id': 'msg-2', 'subject': 'Verify',
             'sent_by': 'system', 'error_message': None,
             'created_at': '2024-01-02', 'updated_at': None},
        ]

        result = service.get_logs(recipient='b@test.com')

        assert len(result) == 1
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'recipient = %s' in query
        assert 'b@test.com' in params

    def test_filter_by_both_administration_and_recipient(self, service, mock_db):
        """get_logs combines administration and recipient filters with AND."""
        mock_db.execute_query.return_value = []

        service.get_logs(administration='tenant1', recipient='a@test.com')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert 'recipient = %s' in query
        assert 'AND' in query
        assert params == ('tenant1', 'a@test.com', 100)

    def test_no_where_clause_without_filters(self, service, mock_db):
        """get_logs omits WHERE clause when no filters are provided."""
        mock_db.execute_query.return_value = []

        service.get_logs()

        query = mock_db.execute_query.call_args[0][0]
        assert 'WHERE' not in query

    def test_sysadmin_sees_all_tenants_when_no_administration(self, service, mock_db):
        """When administration is None, no tenant filter is applied (SysAdmin view)."""
        mock_db.execute_query.return_value = [
            {'id': 1, 'administration': 'tenant1'},
            {'id': 2, 'administration': 'tenant2'},
        ]

        result = service.get_logs(administration=None)

        query = mock_db.execute_query.call_args[0][0]
        assert 'administration = %s' not in query
        assert len(result) == 2

    def test_filter_combined_with_custom_limit(self, service, mock_db):
        """Filters work correctly combined with a custom limit."""
        mock_db.execute_query.return_value = []

        service.get_logs(administration='tenant1', recipient='x@y.com', limit=25)

        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        assert params == ('tenant1', 'x@y.com', 25)
