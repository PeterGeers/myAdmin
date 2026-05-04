import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

from banking_processor import BankingProcessor


class TestBankingProcessor:

    @pytest.fixture
    def banking_processor(self, mock_db):
        """Create BankingProcessor instance using mock_db fixture.

        mock_db patches database.DatabaseManager at the module level.
        We also patch banking_processor.DatabaseManager so that
        BankingProcessor.__init__ receives the mock instance for self.db.
        """
        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            processor = BankingProcessor(test_mode=True)
        return processor

    @pytest.fixture
    def mock_connection(self):
        """Provide a mock connection and cursor pair for methods that use
        db.get_connection() directly (check_sequence_numbers,
        save_approved_transactions)."""
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

    def test_init_test_mode(self, mock_db):
        """Test initialization in test mode"""
        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            processor = BankingProcessor(test_mode=True)
        assert processor.test_mode == True
        assert hasattr(processor, 'db')
        assert hasattr(processor, 'download_folder')

    def test_init_production_mode(self, mock_db):
        """Test initialization in production mode"""
        with patch('banking_processor.DatabaseManager', return_value=mock_db):
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
        mock_df = pd.DataFrame([
            ['NL80RABO0107936917', 'RABONL2U', 'Test Account', '1', '2025-01-15',
             '2025-01-15', '+150.50', 'EUR', 'Kuwait Petroleum', 'NL12ABNA0123456789',
             'ABNANL2A', 'GT', '123456', 'REF001', '', '', '', 'Kuwait fuel purchase',
             '', '', '', '-', '-', '-']
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

    def test_save_approved_transactions_success(self, banking_processor, mock_connection):
        """Test successful transaction saving"""
        mock_conn, mock_cursor = mock_connection
        transactions = [
            {
                'row_id': 0,
                'TransactionNumber': 'Rabo 2025-01-15',
                'TransactionAmount': 150.50,
                'TransactionDescription': 'Test transaction',
                'TransactionDate': '2025-01-15',
                'administration': 'GoodwinSolutions',
            },
            {
                'row_id': 1,
                'TransactionNumber': 'Rabo 2025-01-15',
                'TransactionAmount': 0,  # Should be skipped
                'TransactionDescription': 'Zero amount',
                'TransactionDate': '2025-01-15',
                'administration': 'GoodwinSolutions',
            }
        ]

        # No duplicates found
        mock_cursor.fetchall.return_value = []

        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            saved_count = banking_processor.save_approved_transactions(transactions)

        assert saved_count == 1  # Only one transaction saved (zero amount skipped)
        banking_processor.db.insert_transaction.assert_called_once()

    def test_save_approved_transactions_error(self, banking_processor, mock_connection):
        """Test transaction saving with database error"""
        mock_conn, mock_cursor = mock_connection
        transactions = [
            {
                'TransactionNumber': 'Test',
                'TransactionAmount': 150.50,
                'TransactionDescription': 'Test transaction',
                'TransactionDate': '2025-01-15',
                'administration': 'GoodwinSolutions',
            }
        ]

        # No duplicates found
        mock_cursor.fetchall.return_value = []
        # insert_transaction raises an error
        banking_processor.db.insert_transaction.side_effect = Exception("Database error")

        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            saved_count = banking_processor.save_approved_transactions(transactions)

        assert saved_count == 0

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_banking_accounts(self, mock_opening_date, banking_processor):
        """Test banking account balance checking"""
        # Mock get_bank_account_lookups (step 1)
        banking_processor.db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'GoodwinSolutions'}
        ]

        # Mock execute_query for balances (step 2) and last_transactions (step 3)
        banking_processor.db.execute_query.side_effect = [
            # Balance query result
            [{'Reknum': '1600', 'administration': 'GoodwinSolutions', 'calculated_balance': 1000.00, 'account_name': 'Bank Account'}],
            # Last transactions query result
            [{'TransactionDate': '2025-01-15', 'TransactionDescription': 'Last transaction',
              'TransactionAmount': 100.00, 'Debet': '1600', 'Credit': '',
              'Ref2': 'REF001', 'Ref3': 'https://test.com', 'Ref4': ''}]
        ]

        balances = banking_processor.check_banking_accounts()

        assert len(balances) == 1
        assert balances[0]['calculated_balance'] == 1000.00
        assert balances[0]['last_transaction_description'] == 'Last transaction'
        assert 'last_transactions' in balances[0]
        banking_processor.db.get_bank_account_lookups.assert_called_once()

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_banking_accounts_no_accounts(self, mock_opening_date, banking_processor):
        """Test banking account checking with no accounts"""
        banking_processor.db.get_bank_account_lookups.return_value = []

        balances = banking_processor.check_banking_accounts()

        assert balances == []

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_banking_accounts_with_end_date(self, mock_opening_date, banking_processor):
        """Test banking account checking with end date"""
        banking_processor.db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'Account': '1600', 'administration': 'GoodwinSolutions'}
        ]

        banking_processor.db.execute_query.side_effect = [
            [{'Reknum': '1600', 'administration': 'GoodwinSolutions', 'calculated_balance': 500.00, 'account_name': 'Bank Account'}],
            []  # No last transactions
        ]

        balances = banking_processor.check_banking_accounts(end_date='2025-01-31')

        assert len(balances) == 1
        assert balances[0]['last_transaction_description'] == 'No transactions found'

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_sequence_numbers_success(self, mock_opening_date, banking_processor, mock_connection):
        """Test successful sequence number checking"""
        mock_conn, mock_cursor = mock_connection

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

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_sequence_numbers_no_account(self, mock_opening_date, banking_processor, mock_connection):
        """Test sequence checking with no account found"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = None

        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('9999', 'NonExistent')

        assert result['success'] == False
        assert 'No IBAN found' in result['message']

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_sequence_numbers_no_transactions(self, mock_opening_date, banking_processor, mock_connection):
        """Test sequence checking with no transactions"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = []

        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('1600', 'GoodwinSolutions')

        assert result['success'] == False
        assert 'No transactions found' in result['message']

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_sequence_numbers_invalid_sequence(self, mock_opening_date, banking_processor, mock_connection):
        """Test sequence checking with invalid (non-numeric) sequence numbers.

        When all Ref2 values are non-numeric, the code takes the balance_comparison
        branch. We provide a Ref2 that doesn't parse as the expected
        'description_saldo_completiondate' format, so no balance issues are found
        and the result reports success with check_type='balance_comparison'.
        """
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchone.return_value = {'rekeningNummer': 'NL80RABO0107936917'}
        mock_cursor.fetchall.return_value = [
            {'TransactionDate': '2025-01-15', 'TransactionDescription': 'Test', 'Ref2': 'INVALID', 'TransactionAmount': 100.00}
        ]

        with patch.object(banking_processor.db, 'get_connection', return_value=mock_conn):
            result = banking_processor.check_sequence_numbers('1600', 'GoodwinSolutions')

        # Non-numeric Ref2 → balance_comparison branch
        assert result['success'] == True
        assert result['check_type'] == 'balance_comparison'
        assert result['first_sequence'] is None
        assert result['last_sequence'] is None

    @patch('banking_processor._get_opening_balance_date', return_value=None)
    def test_check_sequence_numbers_default_iban(self, mock_opening_date, banking_processor, mock_connection):
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
    def test_download_folder_expansion(self, mock_expanduser, mock_db):
        """Test download folder path expansion"""
        mock_expanduser.return_value = '/home/user/Downloads'

        with patch('banking_processor.DatabaseManager', return_value=mock_db):
            processor = BankingProcessor()

        assert processor.download_folder == '/home/user/Downloads'
        mock_expanduser.assert_called_with("~/Downloads")


if __name__ == '__main__':
    pytest.main([__file__])
