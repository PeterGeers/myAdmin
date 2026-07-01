import sys
import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime
from contextlib import contextmanager

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
        assert hasattr(logic, 'db')
        assert logic.db is not None
    
    def test_get_connection_success(self, transaction_logic):
        """Test successful database connection delegates to DatabaseManager"""
        mock_conn = MagicMock()
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_connection.return_value = mock_conn
        
        connection = transaction_logic.get_connection()
        
        assert connection == mock_conn
        transaction_logic.db.get_connection.assert_called_once()
    
    def test_get_last_transactions_existing(self, transaction_logic, mock_connection, sample_template_transactions):
        """Test getting existing transactions"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = sample_template_transactions
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        transactions = transaction_logic.get_last_transactions('Kuwait')
        
        assert len(transactions) == 2
        assert transactions[0]['TransactionNumber'] == 'Kuwait'
        mock_cursor.execute.assert_called()

    def test_get_last_transactions_zero_results_returns_error(self, transaction_logic, mock_connection):
        """Test that 0 results returns error dict instead of Gamma fallback"""
        mock_conn, mock_cursor = mock_connection
        mock_cursor.fetchall.return_value = []
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        result = transaction_logic.get_last_transactions('NewVendor')
        
        # Should return error dict, NOT fall back to Gamma
        assert isinstance(result, dict)
        assert result['error'] is True
        assert 'NewVendor' in result['message']
        assert 'Manual account selection required' in result['message']
        assert result['results'] == []
        # Should only execute ONE query (no Gamma fallback query)
        assert mock_cursor.execute.call_count == 1
    
    def test_get_last_transactions_single_resolves_vat_from_tax_service(self, transaction_logic, mock_connection):
        """Test single transaction resolves VAT account from TaxRateService, not hardcoded '2010'"""
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
        
        # Mock TaxRateService to return a specific VAT account
        mock_tax_svc = MagicMock()
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 21.0,
            'ledger_account': '2020',
            'description': 'BTW hoog'
        }
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        with patch('services.tax_rate_service.TaxRateService', return_value=mock_tax_svc):
            transactions = transaction_logic.get_last_transactions('TestVendor')
            
            assert len(transactions) == 2  # Original + duplicated
            # VAT account should come from TaxRateService, not hardcoded '2010'
            assert transactions[1]['Debet'] == '2020'
            assert transactions[1]['Credit'] == '4000'  # Original debet
            # Verify TaxRateService was called with self.db
            mock_tax_svc.get_tax_rate.assert_called_once()
    
    def test_get_last_transactions_single_vat_fallback_when_no_rate(self, transaction_logic, mock_connection):
        """Test graceful fallback to '2010' when TaxRateService returns None"""
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
        
        # Mock TaxRateService to return None (no rate configured)
        mock_tax_svc = MagicMock()
        mock_tax_svc.get_tax_rate.return_value = None
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        with patch('services.tax_rate_service.TaxRateService', return_value=mock_tax_svc):
            transactions = transaction_logic.get_last_transactions('TestVendor')
            
            assert len(transactions) == 2
            # Should gracefully fall back to '2010'
            assert transactions[1]['Debet'] == '2010'
    
    def test_no_coursera_vendor_overrides(self, transaction_logic, mock_connection):
        """Test that Coursera vendor-specific overrides no longer exist — DB accounts used as-is"""
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
        
        mock_tax_svc = MagicMock()
        mock_tax_svc.get_tax_rate.return_value = {'rate': 21.0, 'ledger_account': '2010', 'description': 'BTW hoog'}
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        with patch('services.tax_rate_service.TaxRateService', return_value=mock_tax_svc):
            transactions = transaction_logic.get_last_transactions('coursera')
            
            assert len(transactions) == 2
            # DB accounts should be used as-is — no override to '6200'/'1600'
            assert transactions[0]['Debet'] == '4000'  # Original from DB, NOT '6200'
            assert transactions[0]['Credit'] == '1300'  # Original from DB, NOT '1600'
    
    def test_no_netflix_vendor_overrides(self, transaction_logic, mock_connection):
        """Test that Netflix vendor-specific overrides no longer exist — DB accounts used as-is"""
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
        
        mock_tax_svc = MagicMock()
        mock_tax_svc.get_tax_rate.return_value = {'rate': 21.0, 'ledger_account': '2010', 'description': 'BTW hoog'}
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        with patch('services.tax_rate_service.TaxRateService', return_value=mock_tax_svc):
            transactions = transaction_logic.get_last_transactions('netflix')
            
            assert len(transactions) == 2
            # DB accounts should be used as-is — no override to '6400'/'1600'
            assert transactions[0]['Debet'] == '4000'  # Original from DB, NOT '6400'
            assert transactions[0]['Credit'] == '1300'  # Original from DB, NOT '1600'
    
    def test_single_transaction_vendors_no_duplication(self, transaction_logic, mock_connection):
        """Test vendors in single_transaction_vendors list return 1 result (no duplication)"""
        mock_conn, mock_cursor = mock_connection
        single_transaction = [{
            'ID': 1,
            'TransactionNumber': 'SomeVendor',
            'TransactionDate': '2025-01-15',
            'TransactionDescription': 'SomeVendor transaction',
            'TransactionAmount': 100.00,
            'Debet': '4000',
            'Credit': '1300',
            'ReferenceNumber': 'SomeVendor',
            'Administration': 'GoodwinSolutions'
        }]
        mock_cursor.fetchall.return_value = single_transaction
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
        transactions = transaction_logic.get_last_transactions('SomeVendor')
        
        # SomeVendor is in single_transaction_vendors — should NOT duplicate
        assert len(transactions) == 1
        assert transactions[0]['Debet'] == '4000'
    
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
        
        @contextmanager
        def mock_transaction():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.transaction = mock_transaction
        
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
        
        saved = transaction_logic.save_approved_transactions(transactions)
        
        assert len(saved) == 1
        assert saved[0]['ID'] == 123
        mock_cursor.execute.assert_called_once()
    
    def test_save_approved_transactions_skip_zero_amount(self, transaction_logic, mock_connection):
        """Test skipping transactions with zero amount"""
        mock_conn, mock_cursor = mock_connection
        
        @contextmanager
        def mock_transaction():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.transaction = mock_transaction
        
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
        
        saved = transaction_logic.save_approved_transactions(transactions)
        
        assert len(saved) == 0  # Zero amount transaction skipped
        mock_cursor.execute.assert_not_called()
    
    def test_connection_error_handling(self, transaction_logic):
        """Test database connection error handling"""
        from db_exceptions import DatabaseError
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_connection.side_effect = DatabaseError("Connection failed")
        
        with pytest.raises(DatabaseError):
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
        
        @contextmanager
        def mock_get_cursor():
            yield mock_cursor, mock_conn
        
        transaction_logic.db = MagicMock()
        transaction_logic.db.get_cursor = mock_get_cursor
        
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


class TestInvoiceServiceErrorHandling:
    """Test that invoice_service.py handles error dict from get_last_transactions()"""
    
    @patch('services.invoice_service.PDFProcessor')
    @patch('services.invoice_service.TransactionLogic')
    @patch('services.invoice_service.DatabaseManager')
    @patch('services.invoice_service.GoogleDriveService', create=True)
    def test_process_invoice_file_handles_error_dict(self, mock_drive, mock_db, mock_tl, mock_proc):
        """Test that process_invoice_file returns template_error when get_last_transactions returns error"""
        from services.invoice_service import InvoiceService
        
        service = InvoiceService(test_mode=True)
        
        # Mock processor to return valid file processing result
        mock_result = {
            'folder': 'TestVendor',
            'txt': 'Some extracted text\npdfplumber used'
        }
        service.processor.process_file.return_value = mock_result
        service.processor.extract_transactions.return_value = []
        
        # Mock get_last_transactions to return error dict
        error_dict = {
            'error': True,
            'message': 'No booking history found for vendor "NewVendor". Manual account selection required.',
            'results': []
        }
        service.transaction_logic.get_last_transactions.return_value = error_dict
        
        result = service.process_invoice_file(
            temp_path='/tmp/test.pdf',
            drive_result={'id': 'test', 'url': 'http://test.com/file'},
            folder_name='NewVendor',
            tenant='TestTenant'
        )
        
        # Should still succeed (file was processed) but with template_error
        assert result['success'] is True
        # prepared_transactions may contain default entries for manual processing
        assert result['template_transactions'] == []
        assert 'template_error' in result
        assert 'NewVendor' in result['template_error']


class TestPdfProcessorErrorHandling:
    """Test that pdf_processor.py handles error dict from get_last_transactions()"""
    
    @patch('transaction_logic.TransactionLogic')
    def test_format_vendor_transactions_handles_error_dict(self, mock_tl_cls):
        """Test that _format_vendor_transactions handles error dict gracefully"""
        from pdf_processor import PDFProcessor
        
        processor = PDFProcessor(test_mode=True)
        
        # Mock TransactionLogic to return error dict from get_last_transactions
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = {
            'error': True,
            'message': 'No booking history found for vendor "NewVendor". Manual account selection required.',
            'results': []
        }
        mock_tl_cls.return_value = mock_tl
        
        vendor_data = {
            'date': '2025-01-15',
            'description': 'Test invoice',
            'total_amount': 100.00,
            'vat_amount': 21.00
        }
        file_data = {
            'folder': 'NewVendor',
            'url': 'http://test.com/file',
            'name': 'test.pdf'
        }
        
        # Should handle error gracefully — falls back to default accounts via exception handler
        transactions = processor._format_vendor_transactions(vendor_data, file_data)
        
        # Should still produce transactions (using fallback accounts from except block)
        assert len(transactions) >= 1
        # The fallback accounts from the except block
        assert transactions[0]['debet'] == '4000'
        assert transactions[0]['credit'] == '1300'


if __name__ == '__main__':
    pytest.main([__file__])
