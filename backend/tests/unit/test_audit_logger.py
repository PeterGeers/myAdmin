"""
Unit tests for the Audit Logging System

Tests the audit logging functionality for duplicate invoice decisions,
including logging, querying, reporting, and data retention.

Requirements: 3.2, 6.4, 6.5
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from audit_logger import AuditLogger


@pytest.fixture
def audit_logger(mock_db):
    """Create an audit logger instance using the shared mock_db fixture."""
    return AuditLogger(db_manager=mock_db)


class TestAuditLoggerBasicLogging:
    """Test basic audit logging functionality"""

    def test_log_continue_decision(self, audit_logger, mock_db):
        """Test logging a 'continue' decision"""
        # execute_query for INSERT should return None (fetch=False)
        mock_db.execute_query.return_value = None

        success = audit_logger.log_decision(
            reference_number='TEST_Vendor1',
            transaction_date='2025-01-15',
            transaction_amount=100.50,
            decision='continue',
            existing_transaction_id=12345,
            new_file_url='https://drive.google.com/file/test123',
            user_id='user_001',
            session_id='session_abc',
            operation_id='op_12345'
        )

        assert success is True
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert 'INSERT INTO' in call_args[0][0]
        assert call_args[1]['fetch'] is False
        assert call_args[1]['commit'] is True

    def test_log_cancel_decision(self, audit_logger, mock_db):
        """Test logging a 'cancel' decision"""
        mock_db.execute_query.return_value = None

        success = audit_logger.log_decision(
            reference_number='TEST_Vendor2',
            transaction_date='2025-01-16',
            transaction_amount=250.75,
            decision='cancel',
            existing_transaction_id=12346,
            new_file_url='https://drive.google.com/file/test456',
            user_id='user_002',
            session_id='session_def',
            operation_id='op_12346'
        )

        assert success is True
        call_args = mock_db.execute_query.call_args
        # Verify the decision value passed to the query
        assert call_args[0][1][4] == 'cancel'

    def test_log_decision_minimal_data(self, audit_logger, mock_db):
        """Test logging with minimal required data"""
        mock_db.execute_query.return_value = None

        success = audit_logger.log_decision(
            reference_number='TEST_Vendor3',
            transaction_date='2025-01-17',
            transaction_amount=50.00,
            decision='continue'
        )

        assert success is True
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        # Optional fields should be None
        assert params[5] is None  # existing_transaction_id
        assert params[6] is None  # new_file_url
        assert params[7] is None  # user_id
        assert params[8] is None  # session_id
        assert params[9] is None  # operation_id


class TestAuditLoggerQuerying:
    """Test audit log querying functionality"""

    def test_query_by_reference_number(self, audit_logger, mock_db):
        """Test querying logs by reference number"""
        mock_db.execute_query.return_value = [
            {
                'id': 1,
                'timestamp': datetime(2025, 1, 15, 10, 0, 0),
                'reference_number': 'TEST_QueryVendor',
                'transaction_date': '2025-01-15',
                'transaction_amount': 100.00,
                'decision': 'continue',
                'existing_transaction_id': None,
                'new_file_url': None,
                'user_id': None,
                'session_id': None,
                'operation_id': None
            }
        ]

        results = audit_logger.query_logs(reference_number='TEST_QueryVendor')

        assert len(results) == 1
        assert results[0]['reference_number'] == 'TEST_QueryVendor'
        # Verify the LIKE parameter was used
        call_args = mock_db.execute_query.call_args
        assert '%TEST_QueryVendor%' in call_args[0][1]

    def test_query_by_date_range(self, audit_logger, mock_db):
        """Test querying logs by date range"""
        mock_db.execute_query.return_value = [
            {
                'id': 2,
                'timestamp': datetime(2025, 1, 20, 10, 0, 0),
                'reference_number': 'TEST_DateVendor2',
                'transaction_date': '2025-01-20',
                'transaction_amount': 200.00,
                'decision': 'cancel',
                'existing_transaction_id': None,
                'new_file_url': None,
                'user_id': None,
                'session_id': None,
                'operation_id': None
            }
        ]

        results = audit_logger.query_logs(
            start_date='2025-01-15',
            end_date='2025-01-25'
        )

        assert len(results) == 1
        assert results[0]['reference_number'] == 'TEST_DateVendor2'
        # Verify date params were passed
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'transaction_date >=' in query
        assert 'transaction_date <=' in query

    def test_query_by_decision_type(self, audit_logger, mock_db):
        """Test querying logs by decision type"""
        mock_db.execute_query.return_value = [
            {
                'id': 1,
                'timestamp': datetime(2025, 1, 15, 10, 0, 0),
                'reference_number': 'TEST_DecisionVendor1',
                'transaction_date': '2025-01-15',
                'transaction_amount': 100.00,
                'decision': 'continue',
                'existing_transaction_id': None,
                'new_file_url': None,
                'user_id': None,
                'session_id': None,
                'operation_id': None
            }
        ]

        results = audit_logger.query_logs(decision='continue')

        assert len(results) == 1
        assert all(r['decision'] == 'continue' for r in results)
        call_args = mock_db.execute_query.call_args
        assert 'decision = %s' in call_args[0][0]

    def test_query_with_pagination(self, audit_logger, mock_db):
        """Test querying logs with pagination"""
        mock_db.execute_query.return_value = [
            {
                'id': i,
                'timestamp': datetime(2025, 1, 15, 10, 0, 0),
                'reference_number': f'TEST_PaginationVendor{i}',
                'transaction_date': '2025-01-15',
                'transaction_amount': 100.00 + i,
                'decision': 'continue',
                'existing_transaction_id': None,
                'new_file_url': None,
                'user_id': None,
                'session_id': None,
                'operation_id': None
            }
            for i in range(3)
        ]

        results = audit_logger.query_logs(
            reference_number='TEST_PaginationVendor',
            limit=3
        )

        assert len(results) <= 3
        # Verify LIMIT and OFFSET are in the query
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'LIMIT' in query
        assert 'OFFSET' in query


class TestAuditLoggerReporting:
    """Test audit log reporting functionality"""

    def test_get_decision_count(self, audit_logger, mock_db):
        """Test getting decision count"""
        mock_db.execute_query.return_value = [{'count': 5}]

        count = audit_logger.get_decision_count(
            start_date='2025-01-15',
            end_date='2025-01-16'
        )

        assert count == 5

    def test_generate_compliance_report(self, audit_logger, mock_db):
        """Test generating compliance report"""
        # The compliance report calls get_decision_count (3 times),
        # query_logs (1 time), and two stats queries.
        # We need to set up side_effect for multiple execute_query calls.
        mock_db.execute_query.side_effect = [
            # 1st call: get_decision_count(start, end) -> total
            [{'count': 10}],
            # 2nd call: get_decision_count(start, end, 'continue')
            [{'count': 7}],
            # 3rd call: get_decision_count(start, end, 'cancel')
            [{'count': 3}],
            # 4th call: query_logs for details
            [
                {
                    'id': 1,
                    'timestamp': datetime(2025, 1, 15, 10, 0, 0),
                    'reference_number': 'TEST_ReportVendor1',
                    'transaction_date': '2025-01-15',
                    'transaction_amount': 100.00,
                    'decision': 'continue',
                    'existing_transaction_id': None,
                    'new_file_url': None,
                    'user_id': None,
                    'session_id': None,
                    'operation_id': None
                }
            ],
            # 5th call: stats by reference_number
            [
                {
                    'reference_number': 'TEST_ReportVendor1',
                    'decision_count': 5,
                    'continue_count': 3,
                    'cancel_count': 2,
                    'total_amount': 500.00
                }
            ],
            # 6th call: daily breakdown
            [
                {
                    'date': '2025-01-15',
                    'decision_count': 5,
                    'continue_count': 3,
                    'cancel_count': 2
                }
            ],
        ]

        report = audit_logger.generate_compliance_report(
            start_date='2025-01-01',
            end_date='2025-01-31',
            include_details=True
        )

        assert 'report_period' in report
        assert 'summary' in report
        assert 'statistics' in report
        assert report['summary']['total_decisions'] == 10
        assert report['summary']['continue_decisions'] == 7
        assert report['summary']['cancel_decisions'] == 3

    def test_get_user_activity_report(self, audit_logger, mock_db):
        """Test generating user activity report"""
        # get_user_activity_report calls:
        # 1. get_decision_count (total) -> execute_query
        # 2. query_logs (user_id, all decisions) -> execute_query
        # 3. query_logs (user_id, continue) -> execute_query
        # 4. query_logs (user_id, cancel) -> execute_query
        # 5. query_logs (recent, limit=20) -> execute_query
        user_log_entry = {
            'id': 1,
            'timestamp': datetime(2025, 1, 15, 10, 0, 0),
            'reference_number': 'TEST_UserVendor1',
            'transaction_date': '2025-01-15',
            'transaction_amount': 100.00,
            'decision': 'continue',
            'existing_transaction_id': None,
            'new_file_url': None,
            'user_id': 'test_user_123',
            'session_id': None,
            'operation_id': None
        }

        mock_db.execute_query.side_effect = [
            # 1. get_decision_count total
            [{'count': 10}],
            # 2. query_logs for user (all decisions) -> returns 2 entries
            [user_log_entry, {**user_log_entry, 'id': 2, 'decision': 'cancel'}],
            # 3. query_logs for user (continue only)
            [user_log_entry],
            # 4. query_logs for user (cancel only)
            [{**user_log_entry, 'id': 2, 'decision': 'cancel'}],
            # 5. query_logs recent decisions
            [user_log_entry, {**user_log_entry, 'id': 2, 'decision': 'cancel'}],
        ]

        report = audit_logger.get_user_activity_report(
            user_id='test_user_123',
            start_date='2025-01-01',
            end_date='2025-01-31'
        )

        assert 'user_id' in report
        assert report['user_id'] == 'test_user_123'
        assert 'summary' in report
        assert report['summary']['total_decisions'] == 2
        assert report['summary']['continue_decisions'] == 1
        assert report['summary']['cancel_decisions'] == 1


class TestAuditLoggerDataRetention:
    """Test audit log data retention functionality"""

    def test_cleanup_old_logs(self, audit_logger, mock_db):
        """Test cleaning up old audit logs"""
        # cleanup_old_logs calls:
        # 1. execute_query for COUNT
        # 2. execute_query for DELETE
        mock_db.execute_query.side_effect = [
            [{'count': 5}],  # count query
            None,            # delete query
        ]

        success, deleted_count = audit_logger.cleanup_old_logs(retention_days=730)

        assert success is True
        assert deleted_count == 5
        assert mock_db.execute_query.call_count == 2


class TestAuditLoggerAuditTrail:
    """Test audit trail functionality"""

    def test_get_audit_trail_for_transaction(self, audit_logger, mock_db):
        """Test getting complete audit trail for a transaction"""
        mock_db.execute_query.return_value = [
            {
                'id': 1,
                'timestamp': datetime(2025, 1, 15, 10, 0, 0),
                'reference_number': 'TEST_TrailVendor',
                'transaction_date': '2025-01-15',
                'transaction_amount': 100.00,
                'decision': 'cancel',
                'existing_transaction_id': None,
                'new_file_url': None,
                'user_id': 'user_001',
                'session_id': None,
                'operation_id': None
            },
            {
                'id': 2,
                'timestamp': datetime(2025, 1, 15, 10, 5, 0),
                'reference_number': 'TEST_TrailVendor',
                'transaction_date': '2025-01-15',
                'transaction_amount': 100.00,
                'decision': 'continue',
                'existing_transaction_id': None,
                'new_file_url': None,
                'user_id': 'user_001',
                'session_id': None,
                'operation_id': None
            }
        ]

        trail = audit_logger.get_audit_trail_for_transaction(
            reference_number='TEST_TrailVendor',
            transaction_date='2025-01-15',
            transaction_amount=100.00
        )

        assert len(trail) == 2
        assert all(r['reference_number'] == 'TEST_TrailVendor' for r in trail)
        # Verify the query used the correct parameters
        call_args = mock_db.execute_query.call_args
        assert call_args[0][1] == ('TEST_TrailVendor', '2025-01-15', 100.00)


class TestAuditLoggerErrorHandling:
    """Test error handling in audit logger"""

    def test_query_with_invalid_dates(self, audit_logger, mock_db):
        """Test querying with invalid date formats"""
        # The mock will just return empty — the real DB would error,
        # but the code catches exceptions and returns []
        mock_db.execute_query.return_value = []

        results = audit_logger.query_logs(
            start_date='invalid-date',
            end_date='2025-01-31'
        )

        assert isinstance(results, list)

    def test_log_decision_with_db_error(self, audit_logger, mock_db):
        """Test logging when database raises an error"""
        mock_db.execute_query.side_effect = Exception("Database error")

        success = audit_logger.log_decision(
            reference_number='TEST_NoTable',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue'
        )

        # The method catches exceptions and returns False
        assert success is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
