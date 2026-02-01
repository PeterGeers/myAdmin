"""
API Integration tests for duplicate detection endpoints.

These tests verify the duplicate detection API endpoints work correctly
with various transaction scenarios and handle errors appropriately.
"""

import sys
import os
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from app import app
from duplicate_checker import DuplicateChecker
from database import DatabaseManager

# Skip all API tests - they require authenticated Flask app
pytestmark = [
    pytest.mark.api,
    pytest.mark.skip(reason="Requires authenticated Flask app - TODO: add auth fixtures")
]


class TestDuplicateDetectionAPI:
    """Test suite for duplicate detection API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        app.config['TESTING'] = True
        # Disable security middleware for testing
        with patch.dict(os.environ, {'FLASK_DEBUG': 'true'}):
            with app.test_client() as client:
                yield client
    
    @pytest.fixture
    def mock_database_manager(self):
        """Mock DatabaseManager for API tests."""
        with patch('app.DatabaseManager') as mock_db_class:
            mock_db_instance = Mock(spec=DatabaseManager)
            mock_db_class.return_value = mock_db_instance
            yield mock_db_instance
    
    @pytest.fixture
    def mock_duplicate_checker(self):
        """Mock DuplicateChecker for API tests."""
        with patch('app.DuplicateChecker') as mock_checker_class:
            mock_checker_instance = Mock(spec=DuplicateChecker)
            mock_checker_class.return_value = mock_checker_instance
            yield mock_checker_instance
    
    def test_check_duplicate_endpoint_no_duplicates(self, client, mock_duplicate_checker):
        """Test /api/check-duplicate endpoint when no duplicates exist."""
        # Mock the duplicate checker to return no duplicates
        mock_duplicate_checker.check_for_duplicates.return_value = []
        mock_duplicate_checker.format_duplicate_info.return_value = {
            'has_duplicates': False,
            'duplicate_count': 0,
            'existing_transactions': [],
            'requires_user_decision': False
        }
        
        # Test data
        test_data = {
            'referenceNumber': 'TestVendor',
            'transactionDate': '2024-01-01',
            'transactionAmount': 100.00,
            'newFileUrl': 'http://example.com/test.pdf',
            'newFileId': 'file123'
        }
        
        # Make API request
        response = client.post(
            '/api/check-duplicate',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'duplicateInfo' in data
        
        duplicate_info = data['duplicateInfo']
        assert duplicate_info['has_duplicates'] == False
        assert duplicate_info['duplicate_count'] == 0
        assert duplicate_info['requires_user_decision'] == False
        assert duplicate_info['newFileUrl'] == 'http://example.com/test.pdf'
        assert duplicate_info['newFileId'] == 'file123'
        assert 'checkTimestamp' in duplicate_info
        
        # Verify mock calls
        mock_duplicate_checker.check_for_duplicates.assert_called_once_with(
            'TestVendor', '2024-01-01', 100.00, 'mutaties'
        )
        mock_duplicate_checker.format_duplicate_info.assert_called_once_with([])
    
    def test_check_duplicate_endpoint_with_duplicates(self, client, mock_duplicate_checker):
        """Test /api/check-duplicate endpoint when duplicates exist."""
        # Mock duplicate data
        mock_duplicates = [
            {
                'ID': 1,
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': Decimal('100.00'),
                'TransactionDescription': 'Existing transaction',
                'Debet': '4000',
                'Credit': '1300'
            }
        ]
        
        mock_formatted_info = {
            'has_duplicates': True,
            'duplicate_count': 1,
            'existing_transactions': [{
                'id': 1,
                'transactionDate': '2024-01-01',
                'transactionDescription': 'Existing transaction',
                'transactionAmount': 100.00,
                'referenceNumber': 'TestVendor'
            }],
            'requires_user_decision': True
        }
        
        # Configure mocks
        mock_duplicate_checker.check_for_duplicates.return_value = mock_duplicates
        mock_duplicate_checker.format_duplicate_info.return_value = mock_formatted_info
        
        # Test data
        test_data = {
            'referenceNumber': 'TestVendor',
            'transactionDate': '2024-01-01',
            'transactionAmount': 100.00,
            'tableName': 'mutaties',
            'newFileUrl': 'http://example.com/new.pdf'
        }
        
        # Make API request
        response = client.post(
            '/api/check-duplicate',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        duplicate_info = data['duplicateInfo']
        assert duplicate_info['has_duplicates'] == True
        assert duplicate_info['duplicate_count'] == 1
        assert duplicate_info['requires_user_decision'] == True
        assert len(duplicate_info['existing_transactions']) == 1
        assert duplicate_info['newFileUrl'] == 'http://example.com/new.pdf'
        
        # Verify mock calls
        mock_duplicate_checker.check_for_duplicates.assert_called_once_with(
            'TestVendor', '2024-01-01', 100.00, 'mutaties'
        )
        mock_duplicate_checker.format_duplicate_info.assert_called_once_with(mock_duplicates)
    
    def test_check_duplicate_endpoint_missing_fields(self, client):
        """Test /api/check-duplicate endpoint with missing required fields."""
        # Test data missing required field
        test_data = {
            'referenceNumber': 'TestVendor',
            'transactionDate': '2024-01-01'
            # Missing transactionAmount
        }
        
        # Make API request
        response = client.post(
            '/api/check-duplicate',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify error response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'Missing required field: transactionAmount' in data['error']
    
    def test_check_duplicate_endpoint_invalid_amount(self, client):
        """Test /api/check-duplicate endpoint with invalid transaction amount."""
        # Test data with invalid amount
        test_data = {
            'referenceNumber': 'TestVendor',
            'transactionDate': '2024-01-01',
            'transactionAmount': 'invalid_amount'
        }
        
        # Make API request
        response = client.post(
            '/api/check-duplicate',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify error response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'Invalid data format' in data['error']
    
    def test_check_duplicate_endpoint_database_error(self, client, mock_duplicate_checker):
        """Test /api/check-duplicate endpoint handles database errors gracefully."""
        # Mock database error
        mock_duplicate_checker.check_for_duplicates.side_effect = Exception("Database connection failed")
        
        # Test data
        test_data = {
            'referenceNumber': 'TestVendor',
            'transactionDate': '2024-01-01',
            'transactionAmount': 100.00
        }
        
        # Make API request
        response = client.post(
            '/api/check-duplicate',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify graceful degradation (should not fail the import)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        
        duplicate_info = data['duplicateInfo']
        assert duplicate_info['has_duplicates'] == False
        assert duplicate_info['requires_user_decision'] == False
        assert 'error_message' in duplicate_info
        assert 'Database connection failed' in duplicate_info['error_message']
    
    def test_log_duplicate_decision_continue(self, client, mock_duplicate_checker):
        """Test /api/log-duplicate-decision endpoint with continue decision."""
        # Mock successful logging
        mock_duplicate_checker.log_duplicate_decision.return_value = True
        
        # Test data
        test_data = {
            'decision': 'continue',
            'duplicateInfo': {
                'existing_transactions': [{'id': 1}],
                'duplicate_count': 1
            },
            'newTransactionData': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': 100.00,
                'Ref3': 'http://example.com/new.pdf'
            },
            'userId': 'user123',
            'sessionId': 'session456'
        }
        
        # Make API request
        response = client.post(
            '/api/log-duplicate-decision',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'Decision "continue" logged successfully' in data['message']
        assert 'logTimestamp' in data
        
        # Verify mock call - now uses keyword arguments
        mock_duplicate_checker.log_duplicate_decision.assert_called_once_with(
            decision='continue',
            duplicate_info=test_data['duplicateInfo'],
            new_transaction_data=test_data['newTransactionData'],
            user_id='user123',
            session_id='session456'
        )
    
    def test_log_duplicate_decision_cancel(self, client, mock_duplicate_checker):
        """Test /api/log-duplicate-decision endpoint with cancel decision."""
        # Mock successful logging
        mock_duplicate_checker.log_duplicate_decision.return_value = True
        
        # Test data
        test_data = {
            'decision': 'cancel',
            'duplicateInfo': {
                'existing_transactions': [{'id': 1}],
                'duplicate_count': 1
            },
            'newTransactionData': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': 100.00
            }
        }
        
        # Make API request
        response = client.post(
            '/api/log-duplicate-decision',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'Decision "cancel" logged successfully' in data['message']
    
    def test_log_duplicate_decision_missing_fields(self, client):
        """Test /api/log-duplicate-decision endpoint with missing required fields."""
        # Test data missing required field
        test_data = {
            'decision': 'continue',
            'duplicateInfo': {'existing_transactions': []}
            # Missing newTransactionData
        }
        
        # Make API request
        response = client.post(
            '/api/log-duplicate-decision',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify error response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'Missing required field: newTransactionData' in data['error']
    
    def test_log_duplicate_decision_invalid_decision(self, client):
        """Test /api/log-duplicate-decision endpoint with invalid decision value."""
        # Test data with invalid decision
        test_data = {
            'decision': 'invalid_decision',
            'duplicateInfo': {'existing_transactions': []},
            'newTransactionData': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': 100.00
            }
        }
        
        # Make API request
        response = client.post(
            '/api/log-duplicate-decision',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify error response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] == False
        assert 'Decision must be either "continue" or "cancel"' in data['error']
    
    def test_log_duplicate_decision_logging_failure(self, client, mock_duplicate_checker):
        """Test /api/log-duplicate-decision endpoint handles logging failures gracefully."""
        # Mock logging failure
        mock_duplicate_checker.log_duplicate_decision.return_value = False
        
        # Test data
        test_data = {
            'decision': 'continue',
            'duplicateInfo': {'existing_transactions': []},
            'newTransactionData': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': 100.00
            }
        }
        
        # Make API request
        response = client.post(
            '/api/log-duplicate-decision',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify graceful handling (should not fail user workflow)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'logging may have failed' in data['message']
        assert 'warning' in data
    
    def test_log_duplicate_decision_exception(self, client, mock_duplicate_checker):
        """Test /api/log-duplicate-decision endpoint handles exceptions gracefully."""
        # Mock exception during logging
        mock_duplicate_checker.log_duplicate_decision.side_effect = Exception("Database error")
        
        # Test data
        test_data = {
            'decision': 'continue',
            'duplicateInfo': {'existing_transactions': []},
            'newTransactionData': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': 100.00
            }
        }
        
        # Make API request
        response = client.post(
            '/api/log-duplicate-decision',
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        # Verify graceful handling (should not fail user workflow)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'Decision processed (logging failed)' in data['message']
        assert 'error' in data


class TestDuplicateAPIIntegration:
    """Integration tests for duplicate detection API workflow."""
    
    @pytest.fixture
    def client(self):
        """Create Flask test client."""
        app.config['TESTING'] = True
        # Disable security middleware for testing
        with patch.dict(os.environ, {'FLASK_DEBUG': 'true'}):
            with app.test_client() as client:
                yield client
    
    def test_complete_duplicate_workflow(self, client):
        """Test complete duplicate detection and decision logging workflow."""
        with patch('app.DatabaseManager') as mock_db_class, \
             patch('app.DuplicateChecker') as mock_checker_class:
            
            # Setup mocks
            mock_db_instance = Mock(spec=DatabaseManager)
            mock_db_class.return_value = mock_db_instance
            
            mock_checker_instance = Mock(spec=DuplicateChecker)
            mock_checker_class.return_value = mock_checker_instance
            
            # Mock duplicate found scenario
            mock_duplicates = [{
                'ID': 1,
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionAmount': Decimal('100.00')
            }]
            
            mock_formatted_info = {
                'has_duplicates': True,
                'duplicate_count': 1,
                'existing_transactions': [{'id': 1}],
                'requires_user_decision': True
            }
            
            mock_checker_instance.check_for_duplicates.return_value = mock_duplicates
            mock_checker_instance.format_duplicate_info.return_value = mock_formatted_info
            mock_checker_instance.log_duplicate_decision.return_value = True
            
            # Step 1: Check for duplicates
            check_data = {
                'referenceNumber': 'TestVendor',
                'transactionDate': '2024-01-01',
                'transactionAmount': 100.00
            }
            
            check_response = client.post(
                '/api/check-duplicate',
                data=json.dumps(check_data),
                content_type='application/json'
            )
            
            assert check_response.status_code == 200
            check_result = json.loads(check_response.data)
            assert check_result['success'] == True
            assert check_result['duplicateInfo']['has_duplicates'] == True
            
            # Step 2: Log user decision to continue
            decision_data = {
                'decision': 'continue',
                'duplicateInfo': check_result['duplicateInfo'],
                'newTransactionData': {
                    'ReferenceNumber': 'TestVendor',
                    'TransactionDate': '2024-01-01',
                    'TransactionAmount': 100.00
                }
            }
            
            decision_response = client.post(
                '/api/log-duplicate-decision',
                data=json.dumps(decision_data),
                content_type='application/json'
            )
            
            assert decision_response.status_code == 200
            decision_result = json.loads(decision_response.data)
            assert decision_result['success'] == True
            
            # Verify both API calls were made correctly
            assert mock_checker_instance.check_for_duplicates.call_count == 1
            assert mock_checker_instance.format_duplicate_info.call_count == 1
            assert mock_checker_instance.log_duplicate_decision.call_count == 1
    
    def test_no_duplicates_workflow(self, client):
        """Test workflow when no duplicates are found."""
        with patch('app.DatabaseManager') as mock_db_class, \
             patch('app.DuplicateChecker') as mock_checker_class:
            
            # Setup mocks for no duplicates scenario
            mock_db_instance = Mock(spec=DatabaseManager)
            mock_db_class.return_value = mock_db_instance
            
            mock_checker_instance = Mock(spec=DuplicateChecker)
            mock_checker_class.return_value = mock_checker_instance
            
            mock_checker_instance.check_for_duplicates.return_value = []
            mock_checker_instance.format_duplicate_info.return_value = {
                'has_duplicates': False,
                'duplicate_count': 0,
                'existing_transactions': [],
                'requires_user_decision': False
            }
            
            # Check for duplicates
            check_data = {
                'referenceNumber': 'NewVendor',
                'transactionDate': '2024-01-01',
                'transactionAmount': 150.00
            }
            
            check_response = client.post(
                '/api/check-duplicate',
                data=json.dumps(check_data),
                content_type='application/json'
            )
            
            assert check_response.status_code == 200
            check_result = json.loads(check_response.data)
            assert check_result['success'] == True
            assert check_result['duplicateInfo']['has_duplicates'] == False
            assert check_result['duplicateInfo']['requires_user_decision'] == False
            
            # No decision logging needed when no duplicates found
            # Verify only duplicate check was called
            assert mock_checker_instance.check_for_duplicates.call_count == 1
            assert mock_checker_instance.format_duplicate_info.call_count == 1
            assert mock_checker_instance.log_duplicate_decision.call_count == 0


if __name__ == '__main__':
    pytest.main([__file__])