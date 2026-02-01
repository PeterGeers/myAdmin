"""
Property-based tests for DuplicateChecker component.

These tests verify the correctness properties of duplicate detection functionality
using property-based testing with hypothesis to generate test cases.
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, assume
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from duplicate_checker import DuplicateChecker
from database import DatabaseManager


class TestDuplicateChecker:
    """Test suite for DuplicateChecker component."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock DatabaseManager for testing."""
        return Mock(spec=DatabaseManager)
    
    @pytest.fixture
    def duplicate_checker(self, mock_db_manager):
        """Create DuplicateChecker instance with mock database."""
        return DuplicateChecker(mock_db_manager)
    
    def test_init(self, mock_db_manager):
        """Test DuplicateChecker initialization."""
        checker = DuplicateChecker(mock_db_manager)
        assert checker.db == mock_db_manager
    
    def test_check_for_duplicates_no_results(self, duplicate_checker, mock_db_manager):
        """Test duplicate check when no duplicates exist."""
        mock_db_manager.execute_query.return_value = []
        
        result = duplicate_checker.check_for_duplicates(
            'TestVendor', '2024-01-01', 100.00
        )
        
        assert result == []
        mock_db_manager.execute_query.assert_called_once()
    
    def test_check_for_duplicates_with_results(self, duplicate_checker, mock_db_manager):
        """Test duplicate check when duplicates exist."""
        mock_results = [
            {
                'ID': 1,
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': 100.00,
                'TransactionDescription': 'Test transaction'
            }
        ]
        mock_db_manager.execute_query.return_value = mock_results
        
        result = duplicate_checker.check_for_duplicates(
            'TestVendor', '2024-01-01', 100.00
        )
        
        assert result == mock_results
        mock_db_manager.execute_query.assert_called_once()
    
    def test_check_for_duplicates_database_error(self, duplicate_checker, mock_db_manager):
        """Test duplicate check handles database errors gracefully."""
        mock_db_manager.execute_query.side_effect = Exception("Database error")
        
        result = duplicate_checker.check_for_duplicates(
            'TestVendor', '2024-01-01', 100.00
        )
        
        # Should return empty list on error (graceful degradation)
        assert result == []
    
    def test_format_duplicate_info_no_duplicates(self, duplicate_checker):
        """Test formatting when no duplicates exist."""
        result = duplicate_checker.format_duplicate_info([])
        
        expected = {
            'has_duplicates': False,
            'duplicate_count': 0,
            'existing_transactions': [],
            'requires_user_decision': False
        }
        assert result == expected
    
    def test_format_duplicate_info_with_duplicates(self, duplicate_checker):
        """Test formatting when duplicates exist."""
        duplicates = [
            {
                'ID': 1,
                'TransactionNumber': 'T001',
                'TransactionDate': '2024-01-01',
                'TransactionDescription': 'Test transaction',
                'TransactionAmount': Decimal('100.00'),
                'Debet': '4000',
                'Credit': '1300',
                'ReferenceNumber': 'TestVendor',
                'Ref1': 'ref1',
                'Ref2': 'ref2',
                'Ref3': 'http://example.com/file.pdf',
                'Ref4': 'ref4',
                'Administration': 'Test'
            }
        ]
        
        result = duplicate_checker.format_duplicate_info(duplicates)
        
        assert result['has_duplicates'] == True
        assert result['duplicate_count'] == 1
        assert result['requires_user_decision'] == True
        assert len(result['existing_transactions']) == 1
        
        formatted_tx = result['existing_transactions'][0]
        assert formatted_tx['id'] == 1
        assert formatted_tx['transactionAmount'] == 100.00
        assert formatted_tx['ref3'] == 'http://example.com/file.pdf'
    
    def test_log_duplicate_decision_success(self, duplicate_checker, mock_db_manager):
        """Test successful duplicate decision logging."""
        mock_db_manager.execute_query.return_value = None
        
        duplicate_info = {
            'existing_transactions': [{'id': 1}]
        }
        new_transaction_data = {
            'ReferenceNumber': 'TestVendor',
            'TransactionDate': '2024-01-01',
            'TransactionAmount': 100.00,
            'Ref3': 'http://example.com/new_file.pdf'
        }
        
        result = duplicate_checker.log_duplicate_decision(
            'continue', duplicate_info, new_transaction_data, 'user123', 'session456'
        )
        
        assert result == True
        mock_db_manager.execute_query.assert_called_once()
    
    def test_log_duplicate_decision_database_error(self, duplicate_checker, mock_db_manager):
        """Test duplicate decision logging handles database errors."""
        mock_db_manager.execute_query.side_effect = Exception("Database error")
        
        duplicate_info = {'existing_transactions': []}
        new_transaction_data = {
            'ReferenceNumber': 'TestVendor',
            'TransactionDate': '2024-01-01',
            'TransactionAmount': 100.00
        }
        
        result = duplicate_checker.log_duplicate_decision(
            'cancel', duplicate_info, new_transaction_data
        )
        
        # Should return False on error but not raise exception
        assert result == False


# Property-Based Tests
class TestDuplicateCheckerProperties:
    """
    **Feature: duplicate-invoice-detection, Property 1: Duplicate Detection Accuracy**
    
    Property-based tests that verify the duplicate detection system correctly identifies
    all matching transactions within the 2-year window and returns accurate match information
    for any valid transaction data.
    """
    
    def create_duplicate_checker(self):
        """Create DuplicateChecker with mock DatabaseManager for property tests."""
        # Use a mock that behaves like the real database for property testing
        mock_db = Mock(spec=DatabaseManager)
        return DuplicateChecker(mock_db)
    
    # Generate realistic transaction data for property testing
    reference_numbers = st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
        min_size=1,
        max_size=50
    ).filter(lambda x: x.strip() and not x.isspace())
    
    transaction_dates = st.dates(
        min_value=datetime(2022, 1, 1).date(),
        max_value=datetime(2024, 12, 31).date()
    ).map(lambda d: d.strftime('%Y-%m-%d'))
    
    transaction_amounts = st.floats(
        min_value=0.01,
        max_value=999999.99,
        allow_nan=False,
        allow_infinity=False
    ).map(lambda x: round(x, 2))
    
    @given(
        reference_number=reference_numbers,
        transaction_date=transaction_dates,
        transaction_amount=transaction_amounts
    )
    @settings(max_examples=100, deadline=None)
    def test_property_duplicate_detection_accuracy(
        self,
        reference_number,
        transaction_date,
        transaction_amount
    ):
        """
        **Feature: duplicate-invoice-detection, Property 1: Duplicate Detection Accuracy**
        **Validates: Requirements 1.1, 1.3, 1.4**
        
        Property: For any valid transaction with ReferenceNumber, TransactionDate, and 
        TransactionAmount, the duplicate checker should correctly identify all matching 
        existing transactions within the 2-year window and return accurate match information.
        """
        # Assume valid inputs (property testing constraint)
        assume(len(reference_number.strip()) > 0)
        assume(transaction_amount > 0)
        
        # Create a fresh checker for each test
        checker = self.create_duplicate_checker()
        
        # Create mock database responses for different scenarios
        scenarios = [
            # No duplicates scenario
            [],
            # Single duplicate scenario  
            [{
                'ID': 1,
                'ReferenceNumber': reference_number,
                'TransactionDate': transaction_date,
                'TransactionAmount': transaction_amount,
                'TransactionDescription': f'Transaction for {reference_number}',
                'Debet': '4000',
                'Credit': '1300'
            }],
            # Multiple duplicates scenario
            [{
                'ID': 1,
                'ReferenceNumber': reference_number,
                'TransactionDate': transaction_date,
                'TransactionAmount': transaction_amount,
                'TransactionDescription': f'Transaction 1 for {reference_number}',
                'Debet': '4000',
                'Credit': '1300'
            }, {
                'ID': 2,
                'ReferenceNumber': reference_number,
                'TransactionDate': transaction_date,
                'TransactionAmount': transaction_amount,
                'TransactionDescription': f'Transaction 2 for {reference_number}',
                'Debet': '6000',
                'Credit': '1300'
            }]
        ]
        
        for scenario_data in scenarios:
            # Mock the database response
            checker.db.execute_query.return_value = scenario_data
            
            # Test duplicate detection
            result = checker.check_for_duplicates(
                reference_number, transaction_date, transaction_amount
            )
            
            # Property 1: Result should match the database response exactly
            assert result == scenario_data, f"Duplicate detection should return exact database results"
            
            # Property 2: Database query should be called with correct parameters
            last_call = checker.db.execute_query.call_args
            assert last_call is not None, "Database should be queried"
            
            query, params = last_call[0][:2]
            assert reference_number in params, "Reference number should be in query parameters"
            assert transaction_date in params, "Transaction date should be in query parameters"
            assert transaction_amount in params, "Transaction amount should be in query parameters"
            
            # Property 3: Query should include 2-year window constraint
            assert "INTERVAL 2 YEAR" in query, "Query should limit to 2-year window"
            
            # Property 4: Formatted duplicate info should be consistent
            formatted = checker.format_duplicate_info(result)
            
            if not scenario_data:
                # No duplicates case
                assert formatted['has_duplicates'] == False
                assert formatted['duplicate_count'] == 0
                assert formatted['existing_transactions'] == []
                assert formatted['requires_user_decision'] == False
            else:
                # Duplicates found case
                assert formatted['has_duplicates'] == True
                assert formatted['duplicate_count'] == len(scenario_data)
                assert len(formatted['existing_transactions']) == len(scenario_data)
                assert formatted['requires_user_decision'] == True
                
                # Property 5: All duplicate data should be preserved in formatting
                for i, original in enumerate(scenario_data):
                    formatted_tx = formatted['existing_transactions'][i]
                    assert formatted_tx['referenceNumber'] == original.get('ReferenceNumber', '')
                    assert str(formatted_tx['transactionAmount']) == str(float(original.get('TransactionAmount', 0)))
    
    @given(
        decision=st.sampled_from(['continue', 'cancel']),
        reference_number=reference_numbers,
        transaction_date=transaction_dates,
        transaction_amount=transaction_amounts
    )
    @settings(max_examples=50, deadline=None)
    def test_property_decision_logging_consistency(
        self,
        decision,
        reference_number,
        transaction_date,
        transaction_amount
    ):
        """
        Property: For any valid decision and transaction data, the logging should
        consistently record the decision with all required audit information.
        """
        assume(len(reference_number.strip()) > 0)
        assume(transaction_amount > 0)
        
        # Create a fresh checker for each test
        checker = self.create_duplicate_checker()
        checker.db.execute_query.return_value = None  # Successful insert
        
        duplicate_info = {
            'existing_transactions': [{'id': 123}]
        }
        new_transaction_data = {
            'ReferenceNumber': reference_number,
            'TransactionDate': transaction_date,
            'TransactionAmount': transaction_amount,
            'Ref3': 'http://example.com/file.pdf'
        }
        
        # Test decision logging
        result = checker.log_duplicate_decision(
            decision, duplicate_info, new_transaction_data, 'test_user', 'test_session'
        )
        
        # Property: Logging should succeed for valid inputs
        assert result == True, "Decision logging should succeed for valid inputs"
        
        # Property: Database should be called with correct parameters
        last_call = checker.db.execute_query.call_args
        assert last_call is not None, "Database should be called for logging"
        
        query, params = last_call[0][:2]
        kwargs = last_call[1]
        
        # Verify all required parameters are present
        assert decision in params, "Decision should be logged"
        assert reference_number in params, "Reference number should be logged"
        assert transaction_date in params, "Transaction date should be logged"
        assert transaction_amount in params, "Transaction amount should be logged"
        
        # Verify commit flag is set for audit logging
        assert kwargs.get('commit') == True, "Audit log should be committed to database"
        assert kwargs.get('fetch') == False, "Audit log insert should not fetch results"

    @given(
        decision=st.sampled_from(['continue', 'cancel']),
        reference_number=reference_numbers,
        transaction_date=transaction_dates,
        transaction_amount=transaction_amounts,
        file_url=st.one_of(
            st.just('http://example.com/file1.pdf'),
            st.just('http://example.com/file2.pdf'),
            st.just('file:///storage/test1.pdf'),
            st.just('file:///storage/test2.pdf'),
            st.just('https://drive.google.com/file/d/abc123/view'),
            st.just('https://drive.google.com/file/d/def456/view')
        ),
        existing_file_url=st.one_of(
            st.just('http://example.com/file1.pdf'),
            st.just('http://example.com/file2.pdf'),
            st.just('file:///storage/test1.pdf'),
            st.just('file:///storage/test2.pdf'),
            st.just('https://drive.google.com/file/d/abc123/view'),
            st.just('https://drive.google.com/file/d/def456/view')
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_user_decision_processing_consistency(
        self,
        decision,
        reference_number,
        transaction_date,
        transaction_amount,
        file_url,
        existing_file_url
    ):
        """
        **Feature: duplicate-invoice-detection, Property 2: User Decision Processing Consistency**
        **Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.4**
        
        Property: For any user decision (continue or cancel), the system should execute 
        the appropriate workflow (normal processing for continue, cleanup for cancel) 
        while maintaining data integrity and logging the decision appropriately.
        """
        assume(len(reference_number.strip()) > 0)
        assume(transaction_amount > 0)
        assume(len(file_url.strip()) > 0)
        assume(len(existing_file_url.strip()) > 0)
        
        # Import required modules for testing
        from pdf_processor import PDFProcessor
        from file_cleanup_manager import FileCleanupManager
        
        # Create test data structures
        duplicate_info = {
            'has_duplicates': True,
            'duplicate_count': 1,
            'existing_transactions': [{
                'id': 1,
                'referenceNumber': reference_number,
                'transactionDate': transaction_date,
                'transactionAmount': transaction_amount,
                'ref3': existing_file_url
            }],
            'new_transaction': {
                'ReferenceNumber': reference_number,
                'TransactionDate': transaction_date,
                'TransactionAmount': transaction_amount,
                'Ref3': file_url
            }
        }
        
        transactions = [{
            'date': transaction_date,
            'description': f'Test transaction for {reference_number}',
            'amount': transaction_amount,
            'debet': '4000',
            'credit': '1300',
            'ref': reference_number,
            'ref3': file_url,
            'ref4': 'test_file_id'
        }]
        
        file_data = {
            'url': file_url,
            'name': 'test_file_id',
            'folder': reference_number
        }
        
        # Mock the dependencies at the import level
        with patch('database.DatabaseManager') as mock_db_class, \
             patch('duplicate_checker.DuplicateChecker') as mock_checker_class, \
             patch('file_cleanup_manager.FileCleanupManager') as mock_cleanup_class:
            
            # Setup mocks
            mock_db = Mock()
            mock_checker = Mock()
            mock_cleanup = Mock()
            
            mock_db_class.return_value = mock_db
            mock_checker_class.return_value = mock_checker
            mock_cleanup_class.return_value = mock_cleanup
            
            # Configure mock behavior
            mock_checker.log_duplicate_decision.return_value = True
            
            # Configure file cleanup behavior based on URL comparison
            urls_different = file_url != existing_file_url
            mock_cleanup.should_cleanup_file.return_value = urls_different
            mock_cleanup.cleanup_uploaded_file.return_value = True
            
            # Create PDF processor and test decision handling
            processor = PDFProcessor(test_mode=True)
            
            result = processor.handle_duplicate_decision(
                decision, duplicate_info, transactions, file_data, 'test_user', 'test_session'
            )
            
            # Property 1: Decision handling should always succeed for valid inputs
            assert result['success'] == True, f"Decision handling should succeed for {decision}"
            
            # Property 2: Action taken should match the decision
            assert result['action_taken'] == decision, f"Action taken should match decision: {decision}"
            
            # Property 3: Audit logging should be attempted for all decisions
            # Now uses keyword arguments
            mock_checker.log_duplicate_decision.assert_called_once_with(
                decision=decision,
                duplicate_info=duplicate_info,
                new_transaction_data=duplicate_info['new_transaction'],
                user_id='test_user',
                session_id='test_session'
            )
            
            if decision == 'continue':
                # Property 4: Continue decision should preserve transactions
                assert len(result['transactions']) == len(transactions), "Continue should preserve all transactions"
                assert result['cleanup_performed'] == False, "Continue should not perform cleanup"
                
                # Property 5: Continue should remove duplicate_info from transactions
                for tx in result['transactions']:
                    assert 'duplicate_info' not in tx, "Duplicate info should be removed from transactions"
                
                # Property 6: Continue should preserve all transaction data
                original_tx = transactions[0]
                result_tx = result['transactions'][0]
                assert result_tx['date'] == original_tx['date'], "Transaction date should be preserved"
                assert result_tx['amount'] == original_tx['amount'], "Transaction amount should be preserved"
                assert result_tx['ref3'] == original_tx['ref3'], "File URL should be preserved"
                
            elif decision == 'cancel':
                # Property 7: Cancel decision should return no transactions
                assert len(result['transactions']) == 0, "Cancel should return no transactions"
                
                # Property 8: Cancel should check if file cleanup is needed
                mock_cleanup.should_cleanup_file.assert_called_once_with(file_url, existing_file_url)
                
                if urls_different:
                    # Property 9: Cancel with different URLs should perform cleanup
                    mock_cleanup.cleanup_uploaded_file.assert_called_once_with(file_url, 'test_file_id')
                    assert result['cleanup_performed'] == True, "Cancel with different URLs should perform cleanup"
                else:
                    # Property 10: Cancel with same URLs should not perform cleanup
                    assert result['cleanup_performed'] == False, "Cancel with same URLs should not perform cleanup"
            
            # Property 11: All decisions should include a user-friendly message
            assert 'message' in result, "Result should include a user message"
            assert len(result['message']) > 0, "Message should not be empty"
            assert decision in result['message'].lower() or 'duplicate' in result['message'].lower(), \
                "Message should reference the decision or duplicate context"


if __name__ == '__main__':
    pytest.main([__file__])