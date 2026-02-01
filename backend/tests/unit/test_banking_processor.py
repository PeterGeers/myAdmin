import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from banking_processor import BankingProcessor

class TestBankingProcessor:
    
    @pytest.fixture
    def banking_processor(self):
        """Create BankingProcessor instance for testing"""
        return BankingProcessor(test_mode=True)
    
    @pytest.fixture
    def mock_connection(self):
        """Mock database connection"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn, mock_cursor
    
    @pytest.fixture
    def sample_rabo_csv_data(self):
        """Sample Rabobank CSV data"""
        return """IBAN/BBAN,BIC,Naam,Volgnummer,Datum,Rentedatum,Bedrag,Valutacode,Naam tegenpartij,Rekening tegenpartij,BIC tegenpartij,Code,Batch ID,Transactiereferentie,Machtigingskenmerk,Incassant ID,Betalingskenmerk,Omschrijving-1,Omschrijving-2,Omschrijving-3,Reden retour,Oorspr bedrag,Oorspr valuta,Koers
NL80RABO0107936917,RABONL2U,Test Account,1,2025-01-15,2025-01-15,+150.50,EUR,Kuwait Petroleum,NL12ABNA0123456789,ABNANL2A,GT,123456,REF001,,,,Kuwait fuel purchase,,,,-,-,-
NL80RABO0107936917,RABONL2U,Test Account,2,2025-01-16,2025-01-16,-75.25,EUR,Supermarket,NL34INGB0987654321,INGBNL2A,GT,123457,REF002,,,,Groceries,,,,-,-,-"""
    
    @pytest.fixture
    def sample_generic_csv_data(self):
        """Sample generic CSV data"""
        return """Date,Description,Amount
2025-01-15,Test transaction 1,100.00
2025-01-16,Test transaction 2,-50.00"""
    
    def test_init_test_mode(self):
        """Test initialization in test mode"""
        processor = BankingProcessor(test_mode=True)
        assert processor.test_mode == True
        assert hasattr(processor, 'db')
        assert hasattr(processor, 'download_folder')
    
    def test_init_production_mode(self):
        """Test initialization in production mode"""
        processor = BankingProcessor(test_mode=False)
        assert processor.test_mode == False
        assert hasattr(processor, 'db')
    
    @patch('glob.glob')
    def test_get_csv_files_rabo_pattern(self, mock_glob, banking_processor):
        """Test getting Rabobank CSV files"""
        mock_glob.side_effect = [
            ['/downloads/CSV_O123.csv', '/downloads/CSV_A456.csv'],  # Rabo files
            ['/downloads/CSV_O123.csv', '/downloads/CSV_A456.csv', '/downloads/other.csv']  # All files
        ]
        
        files = banking_processor.get_csv_files('/downloads')
        
        assert len(files['rabo_files']) == 2
        assert len(files['other_files']) == 1
        assert 'CSV_O123.csv' in files['rabo_files'][0]
        assert 'other.csv' in files['other_files'][0]
    
    @patch('glob.glob')
    def test_get_csv_files_no_files(self, mock_glob, banking_processor):
        """Test getting CSV files when none exist"""
        mock_glob.return_value = []
        
        files = banking_processor.get_csv_files('/downloads')
        
        assert len(files['rabo_files']) == 0
        assert len(files['other_files']) == 0
    
    @patch('pandas.read_csv')
    def test_read_rabo_csv_success(self, mock_read_csv, banking_processor, sample_rabo_csv_data):
        """Test successful Rabobank CSV reading"""
        # Create mock DataFrame with proper structure
        mock_df = pd.DataFrame([
            ['NL80RABO0107936917', 'RABONL2U', 'Test Account', '1', '2025-01-15', '2025-01-15', '+150.50', 'EUR', 'Kuwait Petroleum', 'NL12ABNA0123456789', 'ABNANL2A', 'GT', '123456', 'REF001', '', '', '', 'Kuwait fuel purchase', '', '', '', '-', '-', '-']
        ])
        mock_read_csv.return_value = mock_df
        
        result = banking_processor.read_rabo_csv('test.csv')
        
        assert not result.empty
        assert 'TransactionDate' in result.columns
        assert 'TransactionAmount' in result.columns
        assert 'Ref1' in result.columns
        mock_read_csv.assert_called_once()
    
    @patch('pandas.read_csv')
    def test_read_rabo_csv_error(self, mock_read_csv, banking_processor):
        """Test Rabobank CSV reading error handling"""
        mock_read_csv.side_effect = Exception("File not found")
        
        result = banking_processor.read_rabo_csv('nonexistent.csv')
        
        assert result.empty
    
    @patch('pandas.read_csv')
    def test_read_generic_csv_success(self, mock_read_csv, banking_processor):
        """Test successful generic CSV reading"""
        mock_df = pd.DataFrame({
            'Date': ['2025-01-15', '2025-01-16'],
            'Description': ['Test 1', 'Test 2'],
            'Amount': [100.00, -50.00]
        })
        mock_read_csv.return_value = mock_df
        
        result = banking_processor.read_generic_csv('test.csv')
        
        assert not result.empty
        assert 'TransactionDate' in result.columns
        assert 'TransactionDescription' in result.columns
        assert 'TransactionAmount' in result.columns
    
    @patch('pandas.read_csv')
    def test_read_generic_csv_error(self, mock_read_csv, banking_processor):
        """Test generic CSV reading error handling"""
        mock_read_csv.side_effect = Exception("Invalid format")
        
        result = banking_processor.read_generic_csv('invalid.csv')
        
        assert result.empty
    
    def test_find_column_case_insensitive(self, banking_processor):
        """Test column finding with case insensitive matching"""
        df = pd.DataFrame({'DATE': [], 'Amount': [], 'DESCRIPTION': []})
        
        date_col = banking_processor.find_column(df, ['date', 'datum'])
        amount_col = banking_processor.find_column(df, ['amount', 'bedrag'])
        desc_col = banking_processor.find_column(df, ['description', 'omschrijving'])
        
        assert date_col == 'DATE'
        assert amount_col == 'Amount'
        assert desc_col == 'DESCRIPTION'
    
    def test_find_column_not_found(self, banking_processor):
        """Test column finding when column doesn't exist"""
        df = pd.DataFrame({'Other': [], 'Columns': []})
        
        result = banking_processor.find_column(df, ['date', 'amount'])
        
        assert result is None
    
    @patch.object(BankingProcessor, 'read_rabo_csv')
    @patch.object(BankingProcessor, 'read_generic_csv')
    def test_process_csv_files_mixed(self, mock_generic, mock_rabo, banking_processor):
        """Test processing mixed CSV files"""
        # Mock return values
        rabo_df = pd.DataFrame({'TransactionDate': ['2025-01-15'], 'TransactionAmount': [150.50]})
        generic_df = pd.DataFrame({'TransactionDate': ['2025-01-16'], 'TransactionAmount': [100.00]})
        
        mock_rabo.return_value = rabo_df
        mock_generic.return_value = generic_df
        
        files = ['CSV_O123.csv', 'other.csv']
        result = banking_processor.process_csv_files(files)
        
        assert len(result) == 2
        mock_rabo.assert_called_once_with('CSV_O123.csv')
        mock_generic.assert_called_once_with('other.csv')
    
    @patch.object(BankingProcessor, 'read_rabo_csv')
    def test_process_csv_files_empty_result(self, mock_rabo, banking_processor):
        """Test processing CSV files with empty results"""
        mock_rabo.return_value = pd.DataFrame()
        
        result = banking_processor.process_csv_files(['CSV_O123.csv'])
        
        assert result.empty
    
    def test_prepare_for_review(self, banking_processor):
        """Test preparing data for frontend review"""
        df = pd.DataFrame({
            'TransactionDate': [pd.Timestamp('2025-01-15'), pd.NaT],
            'TransactionAmount': [150.50, None],
            'TransactionDescription': ['Test', 'Another']
        })
        
        records = banking_processor.prepare_for_review(df)
        
        assert len(records) == 2
        assert records[0]['row_id'] == 0
        assert records[0]['TransactionDate'] == '2025-01-15'
        assert records[1]['TransactionAmount'] == ''  # NaN converted to empty string
    
    def test_save_approved_transactions_success(self, banking_processor):
        """Test successful transaction saving"""
        transactions = [
            {
                'row_id': 0,
                'TransactionNumber': 'Rabo 2025-01-15',
                'TransactionAmount': 150.50,
                'TransactionDescription': 'Test transaction'
            },
            {
                'row_id': 1,
                'TransactionNumber': 'Rabo 2025-01-15',
                'TransactionAmount': 0,  # Should be skipped
                'TransactionDescription': 'Zero amount'
            }
        ]
        
        with patch.object(banking_processor.db, 'insert_transaction') as mock_insert:
            mock_insert.return_value = None
            
            saved_count = banking_processor.save_approved_transactions(transactions)
            
            assert saved_count == 1  # Only one transaction saved (zero amount skipped)
            mock_insert.assert_called_once()
    
    def test_save_approved_transactions_error(self, banking_processor):
        """Test transaction saving with database error"""
        transactions = [
            {
                'TransactionNumber': 'Test',
                'TransactionAmount': 150.50
            }
        ]
        
        with patch.object(banking_processor.db, 'insert_transaction') as mock_insert:
            mock_insert.side_effect = Exception("Database error")
            
            saved_count = banking_processor.save_approved_transactions(transactions)
            
            assert saved_count == 0
    
    def test_check_banking_accounts(self, banking_processor, mock_connection):
        """Test banking account balance checking"""
        mock_conn, mock_cursor = mock_connection
        
        # Mock account lookup results
        mock_cursor.fetchall.side_effect = [
            [{'Administration': 'GoodwinSolutions', 'Account': '1600'}],  # Accounts
            [{'Reknum': '1600', 'administration': 'GoodwinSolutions', 'calculated_balance': 1000.00, 'account_name': 'Bank Account'}],  # Balances (lowercase 'administration' to match SQL alias)
            [{'TransactionDate': '2025-01-15', 'TransactionDescription': 'Last transaction', 'TransactionAmount': 100.00, 'Ref2': 'REF001', 'Ref3': 'https://test.com'}]  # Last transactions
        ]
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            balances = banking_processor.check_banking_accounts()
            
            assert len(balances) == 1
            assert balances[0]['calculated_balance'] == 1000.00
            assert balances[0]['last_transaction_description'] == 'Last transaction'
            assert 'last_transactions' in balances[0]
    
    def test_check_banking_accounts_no_accounts(self, banking_processor, mock_connection):
        """Test banking account checking with no accounts"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            balances = banking_processor.check_banking_accounts()
            
            assert balances == []
    
    def test_check_banking_accounts_with_end_date(self, banking_processor, mock_connection):
        """Test banking account checking with end date"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.side_effect = [
            [{'Administration': 'GoodwinSolutions', 'Account': '1600'}],
            [{'Reknum': '1600', 'administration': 'GoodwinSolutions', 'calculated_balance': 500.00, 'account_name': 'Bank Account'}],  # lowercase 'administration' to match SQL alias
            []  # No last transactions
        ]
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            balances = banking_processor.check_banking_accounts(end_date='2025-01-31')
            
            assert len(balances) == 1
            assert balances[0]['last_transaction_description'] == 'No transactions found'
    
    def test_check_sequence_numbers_success(self, banking_processor, mock_connection):
        """Test successful sequence number checking"""
        mock_conn, mock_cursor = mock_connection
        
        # Mock lookup and transaction results
        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2025-01-15', 'TransactionDescription': 'Test 1', 'Ref2': '1', 'TransactionAmount': 100.00},
            {'TransactionDate': '2025-01-16', 'TransactionDescription': 'Test 2', 'Ref2': '2', 'TransactionAmount': 150.00},
            {'TransactionDate': '2025-01-17', 'TransactionDescription': 'Test 3', 'Ref2': '4', 'TransactionAmount': 200.00}  # Gap at 3
        ]
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('1600', 'GoodwinSolutions')
            
            assert result['success'] == True
            assert result['total_transactions'] == 3
            assert result['first_sequence'] == 1
            assert result['last_sequence'] == 4
            assert result['has_gaps'] == True
            assert len(result['sequence_issues']) == 1
            assert result['sequence_issues'][0]['expected'] == 3
            assert result['sequence_issues'][0]['found'] == 4
    
    def test_check_sequence_numbers_no_account(self, banking_processor, mock_connection):
        """Test sequence checking with no account found"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = None
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('9999', 'NonExistent')
            
            assert result['success'] == False
            assert 'No IBAN found' in result['message']
    
    def test_check_sequence_numbers_no_transactions(self, banking_processor, mock_connection):
        """Test sequence checking with no transactions"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = []
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('1600', 'GoodwinSolutions')
            
            assert result['success'] == False
            assert 'No transactions found' in result['message']
    
    def test_check_sequence_numbers_invalid_sequence(self, banking_processor, mock_connection):
        """Test sequence checking with invalid sequence numbers"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2025-01-15', 'TransactionDescription': 'Test', 'Ref2': 'INVALID', 'TransactionAmount': 100.00}
        ]
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('1600', 'GoodwinSolutions')
            
            assert result['success'] == True
            assert len(result['sequence_issues']) == 1
            assert 'Invalid sequence number' in result['sequence_issues'][0]['error']
            # first_sequence and last_sequence should handle ValueError gracefully
            assert result['first_sequence'] is None
            assert result['last_sequence'] is None
    
    def test_check_sequence_numbers_default_iban(self, banking_processor, mock_connection):
        """Test sequence checking without account parameters (uses default IBAN)"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2025-01-15', 'TransactionDescription': 'Test', 'Ref2': '1', 'TransactionAmount': 100.00}
        ]
        
        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers()
            
            assert result['success'] == True
            assert result['iban'] == 'NL80RABO0107936917'
            assert result['total_transactions'] == 1
    
    @patch('os.path.expanduser')
    def test_download_folder_expansion(self, mock_expanduser, banking_processor):
        """Test download folder path expansion"""
        mock_expanduser.return_value = '/home/user/Downloads'
        
        processor = BankingProcessor()
        
        assert processor.download_folder == '/home/user/Downloads'
        mock_expanduser.assert_called_with("~/Downloads")

if __name__ == '__main__':
    pytest.main([__file__])