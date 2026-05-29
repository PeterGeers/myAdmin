"""
Unit tests for InvoiceService._determine_parser_used() method and
parser_used reporting in process_invoice_file response.

Validates: Requirements 4.1, 4.2, 4.3, 4.4
"""
import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add backend/src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


@pytest.fixture
def invoice_service():
    """Create InvoiceService instance with mocked dependencies."""
    with patch('services.invoice_service.DatabaseManager'), \
         patch('services.invoice_service.PDFProcessor'), \
         patch('services.invoice_service.TransactionLogic'):
        from services.invoice_service import InvoiceService
        service = InvoiceService(test_mode=True)
        return service


class TestDetermineParserUsedReturnsAi:
    """Tests that _determine_parser_used returns 'ai' for successful extraction."""

    def test_returns_ai_for_valid_amount(self, invoice_service):
        """Requirement 4.1: AI extraction with amount > 0 reports 'ai'."""
        transactions = [{'amount': 150.50, 'description': 'Test invoice', 'date': '2025-01-15'}]
        result = {'folder': 'test_vendor', 'txt': 'some text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai'

    def test_returns_ai_for_ai_data_in_result(self, invoice_service):
        """Requirement 4.1: When ai_data is present in result, reports 'ai'."""
        transactions = [{'amount': 100.00, 'description': 'Image invoice'}]
        result = {'folder': 'test_vendor', 'txt': 'some text', 'ai_data': {'total_amount': 100.0}}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai'

    def test_returns_ai_for_large_amount(self, invoice_service):
        """Requirement 4.1: Large amounts still report 'ai'."""
        transactions = [{'amount': 99999.99, 'description': 'Large invoice'}]
        result = {'folder': 'expensive_vendor', 'txt': 'text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai'

    def test_returns_ai_for_small_positive_amount(self, invoice_service):
        """Requirement 4.1: Small positive amounts report 'ai'."""
        transactions = [{'amount': 0.01, 'description': 'Tiny invoice'}]
        result = {'folder': 'vendor', 'txt': 'text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai'


class TestDetermineParserUsedReturnsAiFailed:
    """Tests that _determine_parser_used returns 'ai_failed' for failed extraction."""

    def test_returns_ai_failed_for_zero_amount(self, invoice_service):
        """Requirement 4.2: Zero amount reports 'ai_failed'."""
        transactions = [{'amount': 0, 'description': 'Failed extraction'}]
        result = {'folder': 'test_vendor', 'txt': 'some text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai_failed'

    def test_returns_ai_failed_for_empty_transactions(self, invoice_service):
        """Requirement 4.2: Empty transaction list reports 'ai_failed'."""
        transactions = []
        result = {'folder': 'test_vendor', 'txt': 'some text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai_failed'

    def test_returns_ai_failed_for_none_transactions(self, invoice_service):
        """Requirement 4.2: None transactions reports 'ai_failed'."""
        transactions = None
        result = {'folder': 'test_vendor', 'txt': 'some text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai_failed'

    def test_returns_ai_failed_for_string_zero_amount(self, invoice_service):
        """Requirement 4.2: String '0' amount reports 'ai_failed'."""
        transactions = [{'amount': '0', 'description': 'Zero string'}]
        result = {'folder': 'vendor', 'txt': 'text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai_failed'

    def test_returns_ai_failed_for_missing_amount_key(self, invoice_service):
        """Requirement 4.2: Missing amount key defaults to 'ai_failed'."""
        transactions = [{'description': 'No amount field'}]
        result = {'folder': 'vendor', 'txt': 'text'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'ai_failed'


class TestDetermineParserUsedReturnsCsvRule:
    """Tests that _determine_parser_used returns 'csv_rule' for CSV rule results."""

    def test_returns_csv_rule_for_parser_used_hint(self, invoice_service):
        """Requirement 4.4: CSV rule marker in transaction reports 'csv_rule'."""
        transactions = [{'amount': 500.0, 'description': 'Hosting Fee', 'parser_used_hint': 'csv_rule'}]
        result = {'folder': 'airbnb', 'txt': 'csv data'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'csv_rule'

    def test_returns_csv_rule_even_with_zero_amount(self, invoice_service):
        """Requirement 4.4: CSV rule marker takes precedence over amount check."""
        transactions = [{'amount': 0, 'description': 'Empty CSV', 'parser_used_hint': 'csv_rule'}]
        result = {'folder': 'airbnb', 'txt': 'csv data'}

        parser_used = invoice_service._determine_parser_used(transactions, result)

        assert parser_used == 'csv_rule'


class TestDetermineParserUsedNeverReturnsVendorSpecific:
    """Tests that _determine_parser_used never returns vendor-specific values."""

    def test_never_returns_vendor_specific_string(self, invoice_service):
        """Requirement 4.3: Never returns 'vendor_specific'."""
        scenarios = [
            ([{'amount': 100.0}], {'folder': 'kuwait', 'txt': 'text'}),
            ([{'amount': 0}], {'folder': 'booking', 'txt': 'text'}),
            ([], {'folder': 'airbnb', 'txt': 'text'}),
            (None, {'folder': 'ziggo', 'txt': 'text'}),
            ([{'amount': 50.0, 'parser_used_hint': 'csv_rule'}], {'folder': 'airbnb', 'txt': 'csv'}),
            ([{'amount': 200.0}], {'folder': 'vendor', 'txt': 'text', 'ai_data': {}}),
        ]

        allowed_values = {'ai', 'ai_failed', 'csv_rule'}

        for transactions, result in scenarios:
            parser_used = invoice_service._determine_parser_used(transactions, result)
            assert parser_used in allowed_values, (
                f"Got '{parser_used}' for transactions={transactions}, result={result}. "
                f"Expected one of {allowed_values}"
            )
            assert parser_used != 'vendor_specific'


class TestProcessInvoiceFileResponseHasNoVendorData:
    """Tests that process_invoice_file response does not contain vendor_data key."""

    def test_response_has_no_vendor_data_key(self, invoice_service):
        """Requirement 4.3: Response dict must not contain 'vendor_data' key."""
        # Mock processor.process_file
        invoice_service.processor.process_file.return_value = {
            'folder': 'test_vendor',
            'txt': 'extracted text content'
        }
        # Mock processor.extract_transactions
        invoice_service.processor.extract_transactions.return_value = [
            {'amount': 100.0, 'description': 'Test', 'date': '2025-01-15'}
        ]
        # Mock transaction_logic.get_last_transactions
        invoice_service.transaction_logic.get_last_transactions.return_value = []

        response = invoice_service.process_invoice_file(
            temp_path='/tmp/test.pdf',
            drive_result={'id': 'file123', 'url': 'https://drive.google.com/file123'},
            folder_name='test_vendor',
            tenant='test_admin'
        )

        assert 'vendor_data' not in response
        assert 'success' in response
        assert response['success'] is True
        assert 'parser_used' in response

    def test_response_has_no_vendor_data_key_on_template_error(self, invoice_service):
        """Requirement 4.3: No vendor_data even when template lookup fails."""
        invoice_service.processor.process_file.return_value = {
            'folder': 'test_vendor',
            'txt': 'extracted text'
        }
        invoice_service.processor.extract_transactions.return_value = [
            {'amount': 50.0, 'description': 'Invoice'}
        ]
        # Simulate template error
        invoice_service.transaction_logic.get_last_transactions.return_value = {
            'error': True,
            'message': 'No booking history found'
        }

        response = invoice_service.process_invoice_file(
            temp_path='/tmp/test.pdf',
            drive_result={'id': 'file456', 'url': 'https://drive.google.com/file456'},
            folder_name='test_vendor',
            tenant='test_admin'
        )

        assert 'vendor_data' not in response
        assert response['success'] is True
        assert 'parser_used' in response
        assert response['parser_used'] == 'ai'
