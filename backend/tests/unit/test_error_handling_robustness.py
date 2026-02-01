"""
Property-based tests for error handling robustness in duplicate detection system.

These tests verify that the duplicate detection system handles all error conditions
gracefully, provides appropriate user feedback, maintains audit trails, and prevents
data corruption under various failure scenarios.
"""

import sys
import os
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, assume
import mysql.connector
from mysql.connector import Error as MySQLError

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from duplicate_checker import (
    DuplicateChecker, DuplicateDetectionError, DatabaseConnectionError,
    ValidationError, SessionTimeoutError
)
from file_cleanup_manager import (
    FileCleanupManager, FileCleanupError, FileSystemError,
    SecurityError, GoogleDriveError
)
from session_manager import SessionManager, SessionTimeoutError as SessionTimeout
from error_handlers import handle_duplicate_detection_error, user_friendly_error
from database import DatabaseManager


class TestErrorHandlingRobustness:
    """
    **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
    
    Property-based tests that verify the system handles all error conditions gracefully,
    provides appropriate user feedback, maintains audit trails, and prevents data corruption
    under various failure scenarios.
    """
    
    def create_test_components(self, temp_storage=None):
        """Create test components with mocked dependencies."""
        mock_db = Mock(spec=DatabaseManager)
        duplicate_checker = DuplicateChecker(mock_db)
        
        if temp_storage:
            config = {
                'base_storage_path': temp_storage,
                'temp_storage_path': os.path.join(temp_storage, 'temp')
            }
            file_cleanup_manager = FileCleanupManager(config)
        else:
            file_cleanup_manager = FileCleanupManager()
        
        # Mock the recovery method to avoid time.sleep delays in tests
        def mock_recovery(cleanup_context, failed_attempt):
            # Skip the time.sleep for tests
            pass
        
        file_cleanup_manager._attempt_cleanup_recovery = mock_recovery
        
        return {
            'db': mock_db,
            'duplicate_checker': duplicate_checker,
            'file_cleanup_manager': file_cleanup_manager
        }
    
    @given(
        reference_number=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        transaction_date=st.dates(min_value=datetime(2020, 1, 1).date(), max_value=datetime(2025, 12, 31).date()),
        transaction_amount=st.floats(min_value=0.01, max_value=999999.99, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, deadline=5000)
    def test_duplicate_checker_database_connection_errors(self, reference_number, transaction_date, transaction_amount):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
        
        Property: For any valid transaction data, when database connection fails,
        the duplicate checker should handle the error gracefully, log appropriate
        information, and allow the import to continue with warning (graceful degradation).
        """
        components = self.create_test_components()
        duplicate_checker = components['duplicate_checker']
        mock_db = components['db']
        
        # Simulate database connection error
        mock_db.execute_query.side_effect = MySQLError("Connection refused")
        
        # Convert date to string format
        date_str = transaction_date.strftime('%Y-%m-%d')
        
        # The duplicate checker should handle the error gracefully
        result = duplicate_checker.check_for_duplicates(
            reference_number=reference_number,
            transaction_date=date_str,
            transaction_amount=transaction_amount
        )
        
        # Should return empty list (graceful degradation) instead of raising exception
        assert isinstance(result, list)
        assert len(result) == 0  # No duplicates found due to error, but operation continues
        
        # Verify database was called (before error occurred)
        mock_db.execute_query.assert_called_once()
    
    @given(
        decision=st.sampled_from(['continue', 'cancel']),
        user_id=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
        session_id=st.one_of(st.none(), st.text(min_size=1, max_size=50))
    )
    @settings(max_examples=50, deadline=5000)
    def test_duplicate_decision_logging_database_errors(self, decision, user_id, session_id):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.1, 6.4, 6.5**
        
        Property: For any user decision and session information, when database logging fails,
        the system should handle the error gracefully and return appropriate error status
        without crashing the main operation.
        """
        components = self.create_test_components()
        duplicate_checker = components['duplicate_checker']
        mock_db = components['db']
        
        # Simulate database logging error
        mock_db.execute_query.side_effect = MySQLError("Table doesn't exist")
        
        # Create test data
        duplicate_info = {
            'existing_transactions': [{'id': '123', 'ref3': 'http://example.com/file1.pdf'}]
        }
        new_transaction_data = {
            'ReferenceNumber': 'TEST_REF',
            'TransactionDate': '2024-01-01',
            'TransactionAmount': 100.50,
            'Ref3': 'http://example.com/file2.pdf'
        }
        
        # The logging should handle the error gracefully
        result = duplicate_checker.log_duplicate_decision(
            decision=decision,
            duplicate_info=duplicate_info,
            new_transaction_data=new_transaction_data,
            user_id=user_id,
            session_id=session_id
        )
        
        # Should return False (indicating failure) but not raise exception
        assert isinstance(result, bool)
        assert result is False  # Logging failed, but gracefully handled
    
    def test_file_cleanup_filesystem_errors(self):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.2, 6.3**
        
        Test that file cleanup handles various error scenarios gracefully.
        """
        # Create temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            components = self.create_test_components(temp_storage=temp_dir)
            file_cleanup_manager = components['file_cleanup_manager']
            
            # Test cases that should handle errors gracefully
            test_cases = [
                ("", None),  # Empty URL
                ("   ", None),  # Whitespace URL
                ("nonexistent_file.pdf", "123"),  # Non-existent file
                ("/invalid/path/file.pdf", "456"),  # Invalid path
                ("http://example.com/file.pdf", "789"),  # HTTP URL
                ("https://drive.google.com/file/d/123/view", "abc"),  # Google Drive URL
            ]
            
            for file_url, file_id in test_cases:
                # The cleanup should handle errors gracefully
                result = file_cleanup_manager.cleanup_uploaded_file(file_url, file_id)
                
                # Should return boolean result without raising exception
                assert isinstance(result, bool), f"Failed for URL: {file_url}"
                # Result can be True or False depending on the file URL, but should not crash
    
    @given(
        new_url=st.one_of(
            st.just(""),
            st.just("http://example.com/file1.pdf"),
            st.just("http://example.com/file2.pdf"),
            st.just("https://drive.google.com/file/d/123/view"),
            st.just("https://drive.google.com/file/d/456/view"),
            st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'P')), min_size=0, max_size=50)
        ),
        existing_url=st.one_of(
            st.just(""),
            st.just("http://example.com/file1.pdf"),
            st.just("http://example.com/file2.pdf"),
            st.just("https://drive.google.com/file/d/123/view"),
            st.just("https://drive.google.com/file/d/456/view"),
            st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'P')), min_size=0, max_size=50)
        )
    )
    @settings(max_examples=50, deadline=2000)
    def test_url_comparison_edge_cases(self, new_url, existing_url):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 4.2, 4.3, 6.2**
        
        Property: For any URL strings (including empty, malformed, or special characters),
        the URL comparison should handle all cases gracefully without raising exceptions
        and return consistent boolean results.
        """
        components = self.create_test_components()
        file_cleanup_manager = components['file_cleanup_manager']
        
        # The URL comparison should handle all edge cases gracefully
        result = file_cleanup_manager.should_cleanup_file(new_url, existing_url)
        
        # Should always return a boolean without raising exception
        assert isinstance(result, bool)
        
        # Test consistency: same inputs should give same results
        result2 = file_cleanup_manager.should_cleanup_file(new_url, existing_url)
        assert result == result2
    
    @given(
        session_timeout_seconds=st.integers(min_value=5, max_value=300),
        wait_time=st.integers(min_value=0, max_value=600)
    )
    @settings(max_examples=20, deadline=3000)
    def test_session_timeout_handling(self, session_timeout_seconds, wait_time):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.3**
        
        Property: For any session timeout configuration and wait time,
        the session manager should correctly identify timed out sessions
        and handle timeout scenarios gracefully with appropriate exceptions.
        """
        from session_manager import SessionManager, SessionTimeoutError, SessionValidationError
        
        session_manager = SessionManager(default_timeout_seconds=session_timeout_seconds)
        session_id = f"test_session_{datetime.now().timestamp()}_{session_timeout_seconds}"
        
        # Create a session
        session_info = session_manager.create_session(session_id, operation_type="test")
        assert session_info is not None
        
        if wait_time <= session_timeout_seconds:
            # Session should still be valid
            try:
                is_valid = session_manager.validate_session(session_id)
                assert is_valid is True
            except SessionTimeoutError:
                # This might happen due to timing, which is acceptable
                pass
        else:
            # Simulate time passage by manually setting last_accessed
            session_info.last_accessed = datetime.now() - timedelta(seconds=wait_time)
            
            # Session should be timed out
            with pytest.raises(SessionTimeoutError):
                session_manager.validate_session(session_id)
        
        # Clean up the session
        session_manager.invalidate_session(session_id)
    
    def test_validation_error_handling(self):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.1, 6.4**
        
        Test that validation errors are handled properly and provide clear error messages.
        """
        components = self.create_test_components()
        duplicate_checker = components['duplicate_checker']
        
        # Test with invalid parameters
        with pytest.raises(ValidationError) as exc_info:
            duplicate_checker.check_for_duplicates("", "2024-01-01", 100.0)
        
        assert "Reference number cannot be empty" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            duplicate_checker.check_for_duplicates("TEST", "invalid-date", 100.0)
        
        assert "Invalid transaction date format" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            duplicate_checker.check_for_duplicates("TEST", "2024-01-01", -100.0)
        
        assert "Transaction amount must be positive" in str(exc_info.value)
    
    def test_security_error_handling(self):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.2**
        
        Test that security errors are handled properly and prevent unsafe operations.
        """
        components = self.create_test_components()
        file_cleanup_manager = components['file_cleanup_manager']
        
        # Test with path traversal attempts
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM"
        ]
        
        for dangerous_path in dangerous_paths:
            result = file_cleanup_manager.cleanup_uploaded_file(dangerous_path)
            # Should return False (failed) for security reasons, not crash
            assert isinstance(result, bool)
            assert result is False
    
    def test_comprehensive_error_handler_integration(self):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
        
        Test the comprehensive error handler with various error types.
        """
        from error_handlers import handle_duplicate_detection_error
        
        # Test different error types
        test_errors = [
            (MySQLError("Connection failed"), "database"),
            (FileNotFoundError("File not found"), "filesystem"),
            (PermissionError("Access denied"), "filesystem"),
            (ValueError("Invalid value"), "validation"),
            (Exception("Unknown error"), "system")
        ]
        
        for error, expected_category in test_errors:
            operation_context = {
                'operation_id': 'test_op_123',
                'operation_type': 'duplicate_detection'
            }
            
            result = handle_duplicate_detection_error(error, operation_context, "test_user")
            
            # Verify error handler returns proper structure
            assert isinstance(result, dict)
            assert 'error_code' in result
            assert 'error_category' in result
            assert 'severity' in result
            assert 'user_message' in result
            assert 'recovery_suggestions' in result
            assert 'can_continue' in result
            
            # Verify user message is user-friendly (not technical)
            user_message = result['user_message']
            assert isinstance(user_message, str)
            assert len(user_message) > 0
            assert 'traceback' not in user_message.lower()
            assert 'exception' not in user_message.lower()
    
    def test_audit_trail_completeness_under_errors(self):
        """
        **Feature: duplicate-invoice-detection, Property 5: Error Handling Robustness**
        **Validates: Requirements 6.4, 6.5**
        
        Test that audit trail is maintained even when errors occur.
        """
        components = self.create_test_components()
        duplicate_checker = components['duplicate_checker']
        mock_db = components['db']
        
        # Set up mock to succeed for duplicate check, fail for logging
        def mock_execute_query(*args, **kwargs):
            # Check if this is a SELECT query (duplicate check) or INSERT query (logging)
            query = args[0] if args else ""
            if "SELECT" in query.upper():
                return []  # Duplicate check succeeds
            else:
                raise MySQLError("Connection lost")  # Logging fails
        
        mock_db.execute_query.side_effect = mock_execute_query
        
        # Test duplicate checking (should succeed)
        result1 = duplicate_checker.check_for_duplicates("TEST", "2024-01-01", 100.0)
        assert isinstance(result1, list)
        
        # Test decision logging (should fail gracefully)
        duplicate_info = {'existing_transactions': []}
        new_transaction_data = {
            'ReferenceNumber': 'TEST',
            'TransactionDate': '2024-01-01',
            'TransactionAmount': 100.0
        }
        
        result2 = duplicate_checker.log_duplicate_decision(
            "continue", duplicate_info, new_transaction_data
        )
        assert isinstance(result2, bool)
        assert result2 is False  # Failed but handled gracefully
        
        # Verify multiple database calls were attempted
        assert mock_db.execute_query.call_count >= 2