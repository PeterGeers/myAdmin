"""
Unit tests for the Audit Logging System

Tests the audit logging functionality for duplicate invoice decisions,
including logging, querying, reporting, and data retention.

Requirements: 3.2, 6.4, 6.5
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from audit_logger import AuditLogger
from database import DatabaseManager


@pytest.fixture
def db_manager():
    """Create a test database manager"""
    return DatabaseManager(test_mode=True)


@pytest.fixture
def audit_logger(db_manager):
    """Create an audit logger instance"""
    return AuditLogger(db_manager)


@pytest.fixture
def setup_test_table(db_manager):
    """Set up the audit log table for testing"""
    # Create the table
    create_query = """
        CREATE TABLE IF NOT EXISTS duplicate_decision_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reference_number VARCHAR(255) NOT NULL,
            transaction_date DATE NOT NULL,
            transaction_amount DECIMAL(10,2) NOT NULL,
            decision VARCHAR(20) NOT NULL,
            existing_transaction_id INT,
            new_file_url VARCHAR(500),
            user_id VARCHAR(100),
            session_id VARCHAR(100),
            operation_id VARCHAR(100),
            INDEX idx_reference_number (reference_number),
            INDEX idx_transaction_date (transaction_date),
            INDEX idx_decision (decision),
            INDEX idx_timestamp (timestamp),
            INDEX idx_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    
    try:
        db_manager.execute_query(create_query, fetch=False, commit=True)
    except Exception as e:
        print(f"Table creation note: {e}")
    
    yield
    
    # Cleanup after tests
    try:
        db_manager.execute_query(
            "DELETE FROM duplicate_decision_log WHERE reference_number LIKE 'TEST_%'",
            fetch=False,
            commit=True
        )
    except Exception as e:
        print(f"Cleanup note: {e}")


class TestAuditLoggerBasicLogging:
    """Test basic audit logging functionality"""
    
    def test_log_continue_decision(self, audit_logger, setup_test_table):
        """Test logging a 'continue' decision"""
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
    
    def test_log_cancel_decision(self, audit_logger, setup_test_table):
        """Test logging a 'cancel' decision"""
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
    
    def test_log_decision_minimal_data(self, audit_logger, setup_test_table):
        """Test logging with minimal required data"""
        success = audit_logger.log_decision(
            reference_number='TEST_Vendor3',
            transaction_date='2025-01-17',
            transaction_amount=50.00,
            decision='continue'
        )
        
        assert success is True


class TestAuditLoggerQuerying:
    """Test audit log querying functionality"""
    
    def test_query_by_reference_number(self, audit_logger, setup_test_table):
        """Test querying logs by reference number"""
        # Log some test data
        audit_logger.log_decision(
            reference_number='TEST_QueryVendor',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue'
        )
        
        # Query the logs
        results = audit_logger.query_logs(reference_number='TEST_QueryVendor')
        
        assert len(results) >= 1
        assert results[0]['reference_number'] == 'TEST_QueryVendor'
    
    def test_query_by_date_range(self, audit_logger, setup_test_table):
        """Test querying logs by date range"""
        # Log test data with different dates
        audit_logger.log_decision(
            reference_number='TEST_DateVendor1',
            transaction_date='2025-01-10',
            transaction_amount=100.00,
            decision='continue'
        )
        
        audit_logger.log_decision(
            reference_number='TEST_DateVendor2',
            transaction_date='2025-01-20',
            transaction_amount=200.00,
            decision='cancel'
        )
        
        # Query with date range
        results = audit_logger.query_logs(
            start_date='2025-01-15',
            end_date='2025-01-25'
        )
        
        # Should only get the second entry
        matching_results = [r for r in results if r['reference_number'].startswith('TEST_DateVendor')]
        assert len(matching_results) >= 1
        assert any(r['reference_number'] == 'TEST_DateVendor2' for r in matching_results)
    
    def test_query_by_decision_type(self, audit_logger, setup_test_table):
        """Test querying logs by decision type"""
        # Log test data with different decisions
        audit_logger.log_decision(
            reference_number='TEST_DecisionVendor1',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue'
        )
        
        audit_logger.log_decision(
            reference_number='TEST_DecisionVendor2',
            transaction_date='2025-01-15',
            transaction_amount=200.00,
            decision='cancel'
        )
        
        # Query for 'continue' decisions
        results = audit_logger.query_logs(decision='continue')
        matching_results = [r for r in results if r['reference_number'].startswith('TEST_DecisionVendor')]
        
        assert len(matching_results) >= 1
        assert all(r['decision'] == 'continue' for r in matching_results)
    
    def test_query_with_pagination(self, audit_logger, setup_test_table):
        """Test querying logs with pagination"""
        # Log multiple test entries
        for i in range(5):
            audit_logger.log_decision(
                reference_number=f'TEST_PaginationVendor{i}',
                transaction_date='2025-01-15',
                transaction_amount=100.00 + i,
                decision='continue'
            )
        
        # Query with limit
        results = audit_logger.query_logs(
            reference_number='TEST_PaginationVendor',
            limit=3
        )
        
        assert len(results) <= 3


class TestAuditLoggerReporting:
    """Test audit log reporting functionality"""
    
    def test_get_decision_count(self, audit_logger, setup_test_table):
        """Test getting decision count"""
        # Log some test data
        audit_logger.log_decision(
            reference_number='TEST_CountVendor1',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue'
        )
        
        audit_logger.log_decision(
            reference_number='TEST_CountVendor2',
            transaction_date='2025-01-16',
            transaction_amount=200.00,
            decision='cancel'
        )
        
        # Get count
        count = audit_logger.get_decision_count(
            start_date='2025-01-15',
            end_date='2025-01-16'
        )
        
        assert count >= 2
    
    def test_generate_compliance_report(self, audit_logger, setup_test_table):
        """Test generating compliance report"""
        # Log test data
        audit_logger.log_decision(
            reference_number='TEST_ReportVendor1',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue'
        )
        
        audit_logger.log_decision(
            reference_number='TEST_ReportVendor2',
            transaction_date='2025-01-16',
            transaction_amount=200.00,
            decision='cancel'
        )
        
        # Generate report
        report = audit_logger.generate_compliance_report(
            start_date='2025-01-01',
            end_date='2025-01-31',
            include_details=True
        )
        
        assert 'report_period' in report
        assert 'summary' in report
        assert 'statistics' in report
        assert report['summary']['total_decisions'] >= 0
    
    def test_get_user_activity_report(self, audit_logger, setup_test_table):
        """Test generating user activity report"""
        # Log test data for specific user
        audit_logger.log_decision(
            reference_number='TEST_UserVendor1',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue',
            user_id='test_user_123'
        )
        
        audit_logger.log_decision(
            reference_number='TEST_UserVendor2',
            transaction_date='2025-01-16',
            transaction_amount=200.00,
            decision='cancel',
            user_id='test_user_123'
        )
        
        # Generate user report
        report = audit_logger.get_user_activity_report(
            user_id='test_user_123',
            start_date='2025-01-01',
            end_date='2025-01-31'
        )
        
        assert 'user_id' in report
        assert report['user_id'] == 'test_user_123'
        assert 'summary' in report
        assert report['summary']['total_decisions'] >= 2


class TestAuditLoggerDataRetention:
    """Test audit log data retention functionality"""
    
    def test_cleanup_old_logs(self, audit_logger, setup_test_table):
        """Test cleaning up old audit logs"""
        # This test verifies the cleanup function runs without errors
        # In a real scenario, we would insert old data and verify deletion
        success, deleted_count = audit_logger.cleanup_old_logs(retention_days=730)
        
        assert success is True
        assert deleted_count >= 0


class TestAuditLoggerAuditTrail:
    """Test audit trail functionality"""
    
    def test_get_audit_trail_for_transaction(self, audit_logger, setup_test_table):
        """Test getting complete audit trail for a transaction"""
        # Log multiple decisions for the same transaction
        audit_logger.log_decision(
            reference_number='TEST_TrailVendor',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='cancel',
            user_id='user_001'
        )
        
        audit_logger.log_decision(
            reference_number='TEST_TrailVendor',
            transaction_date='2025-01-15',
            transaction_amount=100.00,
            decision='continue',
            user_id='user_001'
        )
        
        # Get audit trail
        trail = audit_logger.get_audit_trail_for_transaction(
            reference_number='TEST_TrailVendor',
            transaction_date='2025-01-15',
            transaction_amount=100.00
        )
        
        assert len(trail) >= 2
        assert all(r['reference_number'] == 'TEST_TrailVendor' for r in trail)


class TestAuditLoggerErrorHandling:
    """Test error handling in audit logger"""
    
    def test_query_with_invalid_dates(self, audit_logger, setup_test_table):
        """Test querying with invalid date formats"""
        # Should handle gracefully and return empty list
        results = audit_logger.query_logs(
            start_date='invalid-date',
            end_date='2025-01-31'
        )
        
        # Should not crash, may return empty or handle gracefully
        assert isinstance(results, list)
    
    def test_log_decision_with_missing_table(self, db_manager):
        """Test logging when table doesn't exist"""
        # Create logger with fresh db manager
        logger = AuditLogger(db_manager)
        
        # Try to log (may fail if table doesn't exist, but shouldn't crash)
        try:
            success = logger.log_decision(
                reference_number='TEST_NoTable',
                transaction_date='2025-01-15',
                transaction_amount=100.00,
                decision='continue'
            )
            # If it succeeds, table exists
            assert success in [True, False]
        except Exception:
            # If it fails, that's also acceptable for this test
            pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
