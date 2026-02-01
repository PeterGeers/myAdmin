import sys
import os
import pytest
import mysql.connector
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from transaction_logic import TransactionLogic

class TestTransactionLogic:
    
    @pytest.fixture
    def transaction_logic(self):
        """Create TransactionLogic instance for testing"""
        return TransactionLogic(test_mode=True)
    
    @pytest.fixture
    def mock_connection(self):
        """Mock database connection"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor
    
    @pytest.fixture
    def sample_template_transactions(self):
        """Sample template transactions"""
        return [
            {
                'ID': 1,
                'TransactionNumber': 'Kuwait',
                'TransactionDate': '2025-01-15',
                'TransactionDescription': 'Kuwait Petroleum fuel',
                'TransactionAmount': 150.50,
                'Debet': '4000',
                'Credit': '1300',
                'ReferenceNumber': 'Kuwait',
                'Administration': 'GoodwinSolutions'
            },
            {
                'ID': 2,
                'TransactionNumber': 'Kuwait',
                'TransactionDate': '2025-01-15',
                'TransactionDescription': 'Kuwait Petroleum fuel BTW',
                'TransactionAmount': 19.85,
                'Debet': '2010',
                'Credit': '4000',
                'ReferenceNumber': 'Kuwait',
                'Administration': 'GoodwinSolutions'
            }
        ]
    
    @pytest.fixture
    def sample_vendor_data(self):
        """Sample vendor data"""
        return {
            'date': '2025-01-15',
            'description': 'Kuwait Petroleum fuel purchase',
            'total_amount': 150.50,
            'vat_amount': 19.85,
            'invoice_number': '1234567890'
        }
    
    @pytest.fixture
    def sample_new_data(self):
        """Sample new data for transaction preparation"""
        return {
            'folder_name': 'Kuwait',
            'description': 'PDF processed from invoice.pdf',
            'amount': 150.50,
            'drive_url': 'https://drive.google.com/file/d/test/view',
            'filename': 'invoice.pdf',
            'vendor_data': {
                'date': '2025-01-15',
                'description': 'Kuwait Petroleum fuel',
                'total_amount': 150.50,
                'vat_amount': 19.85
            }
        }
    
    def test_init_test_mode(self):
        """Test initialization in test mode"""
        logic = TransactionLogic(test_mode=True)
        assert logic.test_mode == True
        assert logic.table_name == 'mutaties'
    
    def test_init_production_mode(self):
        """Test initialization in production mode"""
        logic = TransactionLogic(test_mode=False)
        assert logic.test_mode == False
        assert logic.table_name == 'mutaties'
    
    @patch.dict(os.environ, {'TEST_MODE': 'true', 'TEST_DB_NAME': 'testfinance'})
    def test_environment_detection(self):
        """Test automatic test mode detection from environment"""
        logic = TransactionLogic()
        assert hasattr(logic, 'config')
        assert 'testfinance' in logic.config['database']
    
    @patch('mysql.connector.connect')
    def test_get_connection_success(self, mock_connect, transaction_logic):
        """Test successful database connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        connection = transaction_logic.get_connection()
        
        assert connection == mock_conn
        mock_connect.assert_called_once_with(**transaction_logic.config)
    
    def test_get_last_transactions_existing(self, transaction_logic, mock_connection, sample_template_transactions):
        """Test getting existing transactions"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = sample_template_transactions
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            transactions = transaction_logic.get_last_transactions('Kuwait')
            
            assert len(transactions) == 2
            assert transactions[0]['TransactionNumber'] == 'Kuwait'
            mock_cursor.execute.assert_called()
            mock_cursor.close.assert_called()
            mock_conn.close.assert_called()
    
    def test_get_last_transactions_fallback_to_gamma(self, transaction_logic, mock_connection, sample_template_transactions):
        """Test fallback to Gamma when no transactions found"""
        mock_conn, mock_cursor = mock_connection
        # First call returns empty, second call returns Gamma transactions
        mock_cursor.fetchall.side_effect = [[], sample_template_transactions]
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            transactions = transaction_logic.get_last_transactions('NewVendor')
            
            assert len(transactions) == 2
            assert transactions[0]['TransactionNumber'] == 'NewVendor'  # Updated from Gamma
            assert mock_cursor.execute.call_count == 2  # Called twice
    
    def test_get_last_transactions_single_duplication(self, transaction_logic, mock_connection):
        """Test single transaction duplication"""
        mock_conn, mock_cursor = mock_connection
        single_transaction = [{
            'ID': 1,
            'TransactionNumber': 'TestVendor',
            'TransactionDate': '2025-01-15',
            'TransactionDescription': 'Test transaction',
            'TransactionAmount': 100.00,
            'Debet': '4000',
            'Credit': '1300',
            'ReferenceNumber': 'TestVendor',
            'Administration': 'GoodwinSolutions'
        }]
        mock_cursor.fetchall.return_value = single_transaction
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            transactions = transaction_logic.get_last_transactions('TestVendor')
            
            assert len(transactions) == 2  # Original + duplicated
            assert transactions[1]['Debet'] == 2010  # VAT account
            assert transactions[1]['Credit'] == '4000'  # Original debet
    
    def test_get_last_transactions_coursera_specific(self, transaction_logic, mock_connection):
        """Test Coursera-specific account codes"""
        mock_conn, mock_cursor = mock_connection
        single_transaction = [{
            'ID': 1,
            'TransactionNumber': 'coursera',
            'TransactionDate': '2025-01-15',
            'TransactionDescription': 'Coursera course',
            'TransactionAmount': 50.00,
            'Debet': '4000',
            'Credit': '1300',
            'ReferenceNumber': 'coursera',
            'Administration': 'GoodwinSolutions'
        }]
        mock_cursor.fetchall.return_value = single_transaction
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            transactions = transaction_logic.get_last_transactions('coursera')
            
            assert len(transactions) == 2
            assert transactions[0]['Debet'] == '6200'  # Training expense
            assert transactions[0]['Credit'] == '1600'  # Bank account
            assert transactions[1]['Debet'] == '2010'  # VAT
            assert transactions[1]['Credit'] == '6200'  # Training expense
    
    def test_get_last_transactions_netflix_specific(self, transaction_logic, mock_connection):
        """Test Netflix-specific account codes"""
        mock_conn, mock_cursor = mock_connection
        single_transaction = [{
            'ID': 1,
            'TransactionNumber': 'netflix',
            'TransactionDate': '2025-01-15',
            'TransactionDescription': 'Netflix subscription',
            'TransactionAmount': 15.99,
            'Debet': '4000',
            'Credit': '1300',
            'ReferenceNumber': 'netflix',
            'Administration': 'GoodwinSolutions'
        }]
        mock_cursor.fetchall.return_value = single_transaction
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            transactions = transaction_logic.get_last_transactions('netflix')
            
            assert len(transactions) == 2
            assert transactions[0]['Debet'] == '6400'  # Entertainment expense
            assert transactions[0]['Credit'] == '1600'  # Bank account
            assert transactions[1]['Debet'] == '2010'  # VAT
            assert transactions[1]['Credit'] == '6400'  # Entertainment expense
    
    def test_check_file_exists(self, transaction_logic):
        """Test file existence check"""
        # Currently returns False (not implemented)
        result = transaction_logic.check_file_exists('test.pdf', 'folder_id')
        assert result == False
    
    def test_generate_unique_filename_no_conflict(self, transaction_logic):
        """Test unique filename generation when no conflict"""
        with patch.object(transaction_logic, 'check_file_exists', return_value=False):
            filename = transaction_logic.generate_unique_filename('test.pdf', 'folder_id')
            assert filename == 'test.pdf'
    
    def test_generate_unique_filename_with_conflict(self, transaction_logic):
        """Test unique filename generation with conflict"""
        with patch.object(transaction_logic, 'check_file_exists', return_value=True):
            filename = transaction_logic.generate_unique_filename('test.pdf', 'folder_id')
            assert filename.startswith('test_')
            assert filename.endswith('.pdf')
            assert len(filename) > len('test.pdf')
    
    def test_prepare_new_transactions_with_vendor_data(self, transaction_logic, sample_template_transactions, sample_new_data):
        """Test transaction preparation with vendor data"""
        transactions = transaction_logic.prepare_new_transactions(sample_template_transactions, sample_new_data)
        
        assert len(transactions) == 2
        assert transactions[0]['TransactionAmount'] == 150.50  # From vendor data
        assert transactions[1]['TransactionAmount'] == 19.85   # VAT from vendor data
        assert transactions[0]['TransactionDate'] == '2025-01-15'  # From vendor data
        assert transactions[0]['Ref3'] == sample_new_data['drive_url']
        assert transactions[0]['Ref4'] == sample_new_data['filename']
    
    def test_prepare_new_transactions_without_vendor_data(self, transaction_logic, sample_template_transactions):
        """Test transaction preparation without vendor data"""
        new_data = {
            'folder_name': 'Kuwait',
            'description': 'Test transaction',
            'amount': 100.00,
            'drive_url': 'https://test.com',
            'filename': 'test.pdf'
        }
        
        transactions = transaction_logic.prepare_new_transactions(sample_template_transactions, new_data)
        
        assert len(transactions) == 2
        assert transactions[0]['TransactionAmount'] == 100.00  # From new_data
        assert transactions[1]['TransactionAmount'] == 100.00  # From new_data (no vendor VAT)
        assert all(t['TransactionDate'] == datetime.now().strftime('%Y-%m-%d') for t in transactions)
    
    def test_prepare_new_transactions_booking_vendor_data(self, transaction_logic, sample_template_transactions):
        """Test transaction preparation with Booking.com vendor data"""
        new_data = {
            'folder_name': 'Booking',
            'description': 'Booking.com commission',
            'drive_url': 'https://test.com',
            'filename': 'booking.pdf',
            'vendor_data': {
                'date': '2025-01-15',
                'description': 'Booking.com accommodation',
                'total_amount': 114.37,
                'vat_amount': 19.85,
                'accommodation_name': 'Test Hotel',
                'accommodation_number': '4392906',
                'invoice_number': '1640115935',
                'commission_type': 'Commission'
            }
        }
        
        transactions = transaction_logic.prepare_new_transactions(sample_template_transactions, new_data)
        
        assert len(transactions) == 2
        assert transactions[0]['Ref1'] == 'Test Hotel'
        assert transactions[0]['Ref2'] == '1640115935'
        assert 'Commission' in transactions[0]['TransactionDescription']
        assert 'BTW' in transactions[1]['TransactionDescription']
    
    def test_save_approved_transactions_success(self, transaction_logic, mock_connection):
        """Test successful transaction saving"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.lastrowid = 123
        
        transactions = [
            {
                'TransactionNumber': 'Kuwait',
                'TransactionDate': '2025-01-15',
                'TransactionDescription': 'Test transaction',
                'TransactionAmount': 150.50,
                'Debet': '4000',
                'Credit': '1300',
                'ReferenceNumber': 'Kuwait',
                'Ref1': 'NA',
                'Ref2': 'NA',
                'Ref3': 'https://test.com',
                'Ref4': 'test.pdf',
                'Administration': 'GoodwinSolutions'
            }
        ]
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            saved = transaction_logic.save_approved_transactions(transactions)
            
            assert len(saved) == 1
            assert saved[0]['ID'] == 123
            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()
    
    def test_save_approved_transactions_skip_zero_amount(self, transaction_logic, mock_connection):
        """Test skipping transactions with zero amount"""
        mock_conn, mock_cursor = mock_connection
        
        transactions = [
            {
                'TransactionNumber': 'Kuwait',
                'TransactionDate': '2025-01-15',
                'TransactionDescription': 'Zero amount transaction',
                'TransactionAmount': 0,
                'Debet': '4000',
                'Credit': '1300',
                'ReferenceNumber': 'Kuwait',
                'Ref1': 'NA',
                'Ref2': 'NA',
                'Ref3': 'https://test.com',
                'Ref4': 'test.pdf',
                'Administration': 'GoodwinSolutions'
            }
        ]
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            saved = transaction_logic.save_approved_transactions(transactions)
            
            assert len(saved) == 0  # Zero amount transaction skipped
            mock_cursor.execute.assert_not_called()
    
    @patch('mysql.connector.connect')
    def test_connection_error_handling(self, mock_connect, transaction_logic):
        """Test database connection error handling"""
        mock_connect.side_effect = mysql.connector.Error("Connection failed")
        
        with pytest.raises(mysql.connector.Error):
            transaction_logic.get_connection()
    
    def test_multiple_ref3_groups_handling(self, transaction_logic, mock_connection):
        """Test handling multiple transactions with different Ref3 values"""
        mock_conn, mock_cursor = mock_connection
        multiple_transactions = [
            {'ID': 1, 'Ref3': 'url1', 'TransactionNumber': 'Kuwait', 'Debet': '4000'},
            {'ID': 2, 'Ref3': 'url1', 'TransactionNumber': 'Kuwait', 'Debet': '2010'},
            {'ID': 3, 'Ref3': 'url2', 'TransactionNumber': 'Kuwait', 'Debet': '4000'},
            {'ID': 4, 'Ref3': 'url2', 'TransactionNumber': 'Kuwait', 'Debet': '2010'}
        ]
        mock_cursor.fetchall.return_value = multiple_transactions
        
        with patch.object(transaction_logic, 'get_connection', return_value=mock_conn):
            transactions = transaction_logic.get_last_transactions('Kuwait')
            
            # Should return only the first Ref3 group
            assert len(transactions) == 2
            assert all(t['Ref3'] == 'url1' for t in transactions)
    
    def test_transaction_date_formatting(self, transaction_logic, sample_template_transactions):
        """Test proper date formatting in prepared transactions"""
        new_data = {
            'folder_name': 'Kuwait',
            'description': 'Test transaction',
            'drive_url': 'https://test.com',
            'filename': 'test.pdf',
            'vendor_data': {
                'date': '2025-01-15'
            }
        }
        
        transactions = transaction_logic.prepare_new_transactions(sample_template_transactions, new_data)
        
        for transaction in transactions:
            # Check date format is YYYY-MM-DD
            date_str = transaction['TransactionDate']
            assert len(date_str) == 10
            assert date_str.count('-') == 2
            datetime.strptime(date_str, '%Y-%m-%d')  # Should not raise exception

if __name__ == '__main__':
    pytest.main([__file__])