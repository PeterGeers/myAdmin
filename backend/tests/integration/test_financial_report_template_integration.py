"""
Integration tests for Financial Report Generation

Tests the complete flow from data retrieval to structured data preparation
for financial reports (XLSX export).
"""

import pytest
from unittest.mock import Mock, MagicMock
from report_generators import financial_report_generator


@pytest.mark.integration
class TestFinancialReportIntegration:
    """Integration tests for financial report generation"""
    
    def test_make_ledgers_with_balance_and_transactions(self):
        """Test make_ledgers with balance and transaction data"""
        # Mock database
        mock_db = Mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock balance data (previous years)
        balance_data = [
            {
                'Reknum': '1001',
                'AccountName': 'Bank Account',
                'Parent': '1000',
                'Administration': 'GoodwinSolutions',
                'Amount': 50000.00
            },
            {
                'Reknum': '2010',
                'AccountName': 'Betaalde BTW',
                'Parent': '2000',
                'Administration': 'GoodwinSolutions',
                'Amount': 10000.00
            }
        ]
        
        # Mock transaction data (current year)
        transaction_data = [
            {
                'TransactionNumber': 'TRX001',
                'TransactionDate': '2025-01-15',
                'TransactionDescription': 'Payment received',
                'Amount': 1000.00,
                'Reknum': '1001',
                'AccountName': 'Bank Account',
                'Parent': '1000',
                'Administration': 'GoodwinSolutions',
                'VW': 'N',
                'jaar': 2025,
                'kwartaal': 1,
                'maand': 1,
                'week': 3,
                'ReferenceNumber': 'REF001',
                'DocUrl': '',
                'Document': ''
            },
            {
                'TransactionNumber': 'TRX002',
                'TransactionDate': '2025-02-20',
                'TransactionDescription': 'Expense paid',
                'Amount': -500.00,
                'Reknum': '4001',
                'AccountName': 'Expenses',
                'Parent': '4000',
                'Administration': 'GoodwinSolutions',
                'VW': 'V',
                'jaar': 2025,
                'kwartaal': 1,
                'maand': 2,
                'week': 8,
                'ReferenceNumber': 'REF002',
                'DocUrl': '',
                'Document': ''
            }
        ]
        
        # Setup cursor to return data
        mock_cursor.fetchall.side_effect = [balance_data, transaction_data]
        
        # Call function
        result = financial_report_generator.make_ledgers(mock_db, 2025, 'GoodwinSolutions')
        
        # Verify results
        assert len(result) == 4  # 2 balance records + 2 transactions
        
        # Verify beginning balance records
        balance_records = [r for r in result if 'Beginbalans' in r['TransactionNumber']]
        assert len(balance_records) == 2
        assert balance_records[0]['Amount'] == 50000.00
        assert balance_records[0]['TransactionDate'] == '2025-01-01'
        
        # Verify transaction records
        transaction_records = [r for r in result if 'TRX' in r['TransactionNumber']]
        assert len(transaction_records) == 2
        assert transaction_records[0]['Amount'] == 1000.00
        assert transaction_records[1]['Amount'] == -500.00
    
    def test_prepare_financial_report_data_success(self):
        """Test prepare_financial_report_data with successful data"""
        # Mock database
        mock_db = Mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock data
        balance_data = [
            {
                'Reknum': '1001',
                'AccountName': 'Bank',
                'Parent': '1000',
                'Administration': 'TestAdmin',
                'Amount': 10000.00
            }
        ]
        
        transaction_data = [
            {
                'TransactionNumber': 'TRX001',
                'TransactionDate': '2025-01-15',
                'TransactionDescription': 'Test transaction',
                'Amount': 1000.00,
                'Reknum': '1001',
                'AccountName': 'Bank',
                'Parent': '1000',
                'Administration': 'TestAdmin',
                'VW': 'N',
                'jaar': 2025,
                'kwartaal': 1,
                'maand': 1,
                'week': 3,
                'ReferenceNumber': 'REF001',
                'DocUrl': '',
                'Document': ''
            }
        ]
        
        mock_cursor.fetchall.side_effect = [balance_data, transaction_data]
        
        # Call function
        result = financial_report_generator.prepare_financial_report_data(
            mock_db,
            'TestAdmin',
            2025
        )
        
        # Verify structure
        assert 'ledger_data' in result
        assert 'metadata' in result
        assert result['metadata']['administration'] == 'TestAdmin'
        assert result['metadata']['year'] == 2025
        assert result['metadata']['record_count'] == 2
    
    def test_prepare_financial_report_data_empty(self):
        """Test prepare_financial_report_data with no data"""
        # Mock database
        mock_db = Mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock empty data
        mock_cursor.fetchall.side_effect = [[], []]
        
        # Call function
        result = financial_report_generator.prepare_financial_report_data(
            mock_db,
            'TestAdmin',
            2025
        )
        
        # Verify structure
        assert 'ledger_data' in result
        assert 'metadata' in result
        assert result['metadata']['record_count'] == 0
    
    def test_make_ledgers_filters_by_administration(self):
        """Test that make_ledgers correctly filters by administration"""
        # Mock database
        mock_db = Mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock data
        balance_data = [
            {
                'Reknum': '1001',
                'AccountName': 'Bank',
                'Parent': '1000',
                'Administration': 'GoodwinSolutions',
                'Amount': 10000.00
            }
        ]
        
        transaction_data = []
        
        mock_cursor.fetchall.side_effect = [balance_data, transaction_data]
        
        # Call function
        result = financial_report_generator.make_ledgers(mock_db, 2025, 'GoodwinSolutions')
        
        # Verify SQL queries were called with correct parameters
        assert mock_cursor.execute.call_count == 2
        
        # Check first call (balance query)
        first_call_args = mock_cursor.execute.call_args_list[0]
        assert 'GoodwinSolutions%' in first_call_args[0][1]
        assert 2025 in first_call_args[0][1]
        
        # Check second call (transactions query)
        second_call_args = mock_cursor.execute.call_args_list[1]
        assert 'GoodwinSolutions%' in second_call_args[0][1]
        assert 2025 in second_call_args[0][1]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
