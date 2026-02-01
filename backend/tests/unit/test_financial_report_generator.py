"""
Unit tests for financial_report_generator module
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from report_generators import financial_report_generator


class TestMakeLedgers:
    """Tests for make_ledgers function"""
    
    def test_make_ledgers_with_balance_and_transactions(self):
        """Test make_ledgers with both balance and transaction data"""
        # Mock database
        mock_db = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Mock balance data
        balance_data = [
            {
                'Reknum': '1000',
                'AccountName': 'Bank Account',
                'Parent': 'Assets',
                'Administration': 'TestAdmin',
                'Amount': 5000.00
            }
        ]
        
        # Mock transaction data
        transaction_data = [
            {
                'TransactionNumber': 'T001',
                'TransactionDate': '2024-01-15',
                'TransactionDescription': 'Test Transaction',
                'Amount': 100.00,
                'Reknum': '1000',
                'AccountName': 'Bank Account',
                'Parent': 'Assets',
                'Administration': 'TestAdmin',
                'VW': 'N',
                'jaar': 2024,
                'kwartaal': 1,
                'maand': 1,
                'week': 3,
                'ReferenceNumber': 'REF001',
                'DocUrl': '',
                'Document': ''
            }
        ]
        
        # Setup mock cursor to return data
        mock_cursor.fetchall.side_effect = [balance_data, transaction_data]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Call function
        result = financial_report_generator.make_ledgers(mock_db, 2024, 'TestAdmin')
        
        # Verify results
        assert len(result) == 2  # 1 balance + 1 transaction
        
        # Check beginning balance record
        balance_record = result[0]
        assert balance_record['TransactionNumber'] == 'Beginbalans 2024'
        assert balance_record['TransactionDate'] == '2024-01-01'
        assert balance_record['Amount'] == 5000.00
        assert balance_record['Reknum'] == '1000'
        assert balance_record['VW'] == 'N'
        
        # Check transaction record
        transaction_record = result[1]
        assert transaction_record['TransactionNumber'] == 'T001'
        assert transaction_record['Amount'] == 100.00
        
        # Verify database calls
        assert mock_cursor.execute.call_count == 2
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    def test_make_ledgers_no_balance_data(self):
        """Test make_ledgers with no balance data"""
        # Mock database
        mock_db = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Mock empty balance data
        balance_data = []
        
        # Mock transaction data
        transaction_data = [
            {
                'TransactionNumber': 'T001',
                'TransactionDate': '2024-01-15',
                'TransactionDescription': 'Test Transaction',
                'Amount': 100.00,
                'Reknum': '1000',
                'AccountName': 'Bank Account',
                'Parent': 'Assets',
                'Administration': 'TestAdmin',
                'VW': 'N',
                'jaar': 2024,
                'kwartaal': 1,
                'maand': 1,
                'week': 3,
                'ReferenceNumber': 'REF001',
                'DocUrl': '',
                'Document': ''
            }
        ]
        
        # Setup mock cursor
        mock_cursor.fetchall.side_effect = [balance_data, transaction_data]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Call function
        result = financial_report_generator.make_ledgers(mock_db, 2024, 'TestAdmin')
        
        # Verify results
        assert len(result) == 1  # Only transaction
        assert result[0]['TransactionNumber'] == 'T001'
    
    def test_make_ledgers_no_transactions(self):
        """Test make_ledgers with no transaction data"""
        # Mock database
        mock_db = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Mock balance data
        balance_data = [
            {
                'Reknum': '1000',
                'AccountName': 'Bank Account',
                'Parent': 'Assets',
                'Administration': 'TestAdmin',
                'Amount': 5000.00
            }
        ]
        
        # Mock empty transaction data
        transaction_data = []
        
        # Setup mock cursor
        mock_cursor.fetchall.side_effect = [balance_data, transaction_data]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Call function
        result = financial_report_generator.make_ledgers(mock_db, 2024, 'TestAdmin')
        
        # Verify results
        assert len(result) == 1  # Only balance
        assert result[0]['TransactionNumber'] == 'Beginbalans 2024'
    
    def test_make_ledgers_empty_data(self):
        """Test make_ledgers with no data at all"""
        # Mock database
        mock_db = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()
        
        # Mock empty data
        mock_cursor.fetchall.side_effect = [[], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn
        
        # Call function
        result = financial_report_generator.make_ledgers(mock_db, 2024, 'TestAdmin')
        
        # Verify results
        assert len(result) == 0


class TestPrepareFinancialReportData:
    """Tests for prepare_financial_report_data function"""
    
    @patch('report_generators.financial_report_generator.make_ledgers')
    def test_prepare_financial_report_data_success(self, mock_make_ledgers):
        """Test prepare_financial_report_data with successful data retrieval"""
        # Mock ledger data
        mock_ledger_data = [
            {'TransactionNumber': 'T001', 'Amount': 100.00},
            {'TransactionNumber': 'T002', 'Amount': 200.00}
        ]
        mock_make_ledgers.return_value = mock_ledger_data
        
        # Mock database
        mock_db = Mock()
        
        # Call function
        result = financial_report_generator.prepare_financial_report_data(
            mock_db,
            'TestAdmin',
            2024
        )
        
        # Verify results
        assert 'ledger_data' in result
        assert 'metadata' in result
        assert result['ledger_data'] == mock_ledger_data
        assert result['metadata']['administration'] == 'TestAdmin'
        assert result['metadata']['year'] == 2024
        assert result['metadata']['record_count'] == 2
        assert 'generated_date' in result['metadata']
        
        # Verify make_ledgers was called correctly
        mock_make_ledgers.assert_called_once_with(mock_db, 2024, 'TestAdmin')
    
    @patch('report_generators.financial_report_generator.make_ledgers')
    def test_prepare_financial_report_data_empty(self, mock_make_ledgers):
        """Test prepare_financial_report_data with empty data"""
        # Mock empty ledger data
        mock_make_ledgers.return_value = []
        
        # Mock database
        mock_db = Mock()
        
        # Call function
        result = financial_report_generator.prepare_financial_report_data(
            mock_db,
            'TestAdmin',
            2024
        )
        
        # Verify results
        assert result['ledger_data'] == []
        assert result['metadata']['record_count'] == 0
    
    @patch('report_generators.financial_report_generator.make_ledgers')
    def test_prepare_financial_report_data_error(self, mock_make_ledgers):
        """Test prepare_financial_report_data with database error"""
        # Mock error
        mock_make_ledgers.side_effect = Exception("Database error")
        
        # Mock database
        mock_db = Mock()
        
        # Call function and expect exception
        with pytest.raises(Exception) as exc_info:
            financial_report_generator.prepare_financial_report_data(
                mock_db,
                'TestAdmin',
                2024
            )
        
        assert "Failed to prepare financial report data" in str(exc_info.value)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
