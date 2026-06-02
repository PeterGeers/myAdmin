"""
Unit tests for InvoiceTestService.process_file_dry_run method.

Tests the dry-run pipeline execution including:
- Stage-by-stage error collection
- Timing measurements
- AI metrics collection
- Partial results on failure
- Temporary file cleanup
- Stdout capture for execution log
- Raw text truncation
- Execution log truncation
"""

import os
import sys
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'services'))


@pytest.fixture
def temp_pdf_file():
    """Create a temporary file to simulate an uploaded file."""
    fd, path = tempfile.mkstemp(suffix='.pdf')
    os.write(fd, b'%PDF-1.4 fake pdf content for testing')
    os.close(fd)
    yield path
    # Cleanup in case test didn't trigger cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_csv_file():
    """Create a temporary CSV file."""
    fd, path = tempfile.mkstemp(suffix='.csv')
    os.write(fd, b'date,amount,description\n2024-01-15,150.00,Test Invoice\n')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.unit
class TestProcessFileDryRunSuccess:
    """Tests for successful pipeline execution."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_returns_all_required_keys(self, mock_csv_cls, mock_proc_cls, temp_pdf_file):
        """Result dict should always contain all 5 top-level keys."""
        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text content',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 150.0, 'description': 'Test', 'debet': '4000', 'credit': '1300'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(temp_pdf_file, 'TestVendor')

        assert 'pipeline_result' in result
        assert 'performance' in result
        assert 'ai_usage_preview' in result
        assert 'execution_log' in result
        assert 'errors' in result

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_measures_total_duration(self, mock_csv_cls, mock_proc_cls, temp_pdf_file):
        """Total duration should be a non-negative integer in milliseconds."""
        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
        }
        mock_processor.extract_transactions.return_value = []
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(temp_pdf_file, 'TestVendor')

        assert result['performance']['total_duration_ms'] >= 0
        assert isinstance(result['performance']['total_duration_ms'], int)

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_captures_stdout_as_execution_log(self, mock_csv_cls, mock_proc_cls, temp_pdf_file):
        """Pipeline print statements should be captured in execution_log."""
        mock_processor = MagicMock()

        def fake_process_file(*args, **kwargs):
            print("Starting file processing...")
            return {
                'txt': 'Invoice text',
                'folder': 'TestVendor',
                'url': 'dry-run://test.pdf',
                'name': 'test.pdf',
            }

        mock_processor.process_file.side_effect = fake_process_file
        mock_processor.extract_transactions.return_value = []
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(temp_pdf_file, 'TestVendor')

        assert 'Starting file processing...' in result['execution_log']


@pytest.mark.unit
class TestProcessFileDryRunFileCleanup:
    """Tests for temporary file cleanup."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_temp_file_removed_on_success(self, mock_csv_cls, mock_proc_cls):
        """Temp file should be removed after successful execution."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'%PDF-1.4 test')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'text', 'folder': 'V', 'url': 'x', 'name': 'f',
        }
        mock_processor.extract_transactions.return_value = []
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        service.process_file_dry_run(path, 'TestVendor')

        assert not os.path.exists(path)

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_temp_file_removed_on_parsing_failure(self, mock_csv_cls, mock_proc_cls):
        """Temp file should be removed even when file parsing fails."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'bad data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.side_effect = ValueError("Cannot parse file")
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        service.process_file_dry_run(path, 'TestVendor')

        assert not os.path.exists(path)


@pytest.mark.unit
class TestProcessFileDryRunErrors:
    """Tests for error collection behavior."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_file_parsing_error_collected(self, mock_csv_cls, mock_proc_cls):
        """Parsing failure should add error with stage, type, message, trace."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.side_effect = ValueError("Bad PDF format")
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        assert len(result['errors']) == 1
        error = result['errors'][0]
        assert error['stage'] == 'file_parsing'
        assert error['error_type'] == 'ValueError'
        assert 'Bad PDF format' in error['message']
        assert 'stack_trace' in error

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_extraction_error_preserves_raw_text(self, mock_csv_cls, mock_proc_cls):
        """When extraction fails, raw text from parsing should still be present."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Extracted text from PDF',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
        }
        mock_processor.extract_transactions.side_effect = RuntimeError("AI model timeout")
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        # Raw text should be preserved from stage 1
        assert result['pipeline_result']['raw_text'] == 'Extracted text from PDF'
        # Error should be recorded for stage 2
        assert len(result['errors']) == 1
        assert result['errors'][0]['stage'] == 'transaction_formatting'

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    @patch('transaction_logic.TransactionLogic')
    def test_preparation_error_preserves_formatted_transactions(
        self, mock_tl_cls, mock_csv_cls, mock_proc_cls
    ):
        """When preparation fails, formatted transactions should still be present."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 100.0, 'description': 'Inv #1'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        # Make TransactionLogic raise an error
        mock_tl_cls.return_value.get_last_transactions.side_effect = Exception("DB error")

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        # Formatted transactions from stage 2 should be present
        assert len(result['pipeline_result']['formatted_transactions']) == 1
        # Stage 3 error should be recorded
        errors_stage3 = [e for e in result['errors'] if e['stage'] == 'transaction_preparation']
        assert len(errors_stage3) == 1


@pytest.mark.unit
class TestProcessFileDryRunAIMetrics:
    """Tests for AI metrics collection."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_metrics_collected_from_usage(self, mock_csv_cls, mock_proc_cls):
        """AI model, tokens should be collected when AI extraction succeeds."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text content',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
            'ai_data': {
                'date': '2024-01-15',
                'total_amount': 150.0,
                'vat_amount': 31.5,
                'description': 'Invoice #123',
                'vendor': 'TestVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 420,
                    'completion_tokens': 85,
                    'total_tokens': 505,
                },
            },
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 150.0, 'description': 'Invoice #123'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        perf = result['performance']
        assert perf['ai_model'] == 'deepseek/deepseek-chat'
        assert perf['ai_tokens']['prompt_tokens'] == 420
        assert perf['ai_tokens']['completion_tokens'] == 85
        assert perf['ai_tokens']['total_tokens'] == 505
        assert perf['ai_duration_ms'] >= 0

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_csv_rule_parser_omits_ai_metrics(self, mock_csv_cls, mock_proc_cls):
        """When CSV rule is used, AI metrics should all be None."""
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.write(fd, b'date,amount\n2024-01-15,100\n')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'date,amount\n2024-01-15,100',
            'folder': 'Airbnb',
            'url': 'dry-run://test.csv',
            'name': 'test.csv',
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 100.0, 'description': 'Airbnb',
             'parser_used_hint': 'csv_rule'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'Airbnb')

        perf = result['performance']
        assert perf['ai_model'] is None
        assert perf['ai_tokens'] is None
        assert perf['ai_duration_ms'] is None
        assert result['pipeline_result']['parser_used'] == 'csv_rule'


@pytest.mark.unit
class TestProcessFileDryRunTruncation:
    """Tests for text and log truncation."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_raw_text_truncated_at_50k(self, mock_csv_cls, mock_proc_cls):
        """Raw text exceeding 50,000 chars should be truncated with flag."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        long_text = 'x' * 60000
        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': long_text,
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
        }
        mock_processor.extract_transactions.return_value = []
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        assert len(result['pipeline_result']['raw_text']) == 50000
        assert result['pipeline_result']['raw_text_truncated'] is True

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_raw_text_not_truncated_when_short(self, mock_csv_cls, mock_proc_cls):
        """Raw text under 50,000 chars should not be truncated."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        short_text = 'Hello invoice' * 10
        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': short_text,
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
        }
        mock_processor.extract_transactions.return_value = []
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        assert result['pipeline_result']['raw_text'] == short_text
        assert result['pipeline_result']['raw_text_truncated'] is False

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_execution_log_truncated_at_10k(self, mock_csv_cls, mock_proc_cls):
        """Execution log exceeding 10,000 chars should keep most recent."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()

        def verbose_process_file(*args, **kwargs):
            # Print a very long log
            for i in range(2000):
                print(f"Processing line {i:05d} of the verbose output...")
            return {
                'txt': 'text',
                'folder': 'TestVendor',
                'url': 'dry-run://test.pdf',
                'name': 'test.pdf',
            }

        mock_processor.process_file.side_effect = verbose_process_file
        mock_processor.extract_transactions.return_value = []
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor')

        assert len(result['execution_log']) <= 10000


@pytest.mark.unit
class TestProcessFileDryRunAIUsagePreview:
    """Tests for AI usage preview generation."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_usage_preview_generated_for_ai_parser(self, mock_csv_cls, mock_proc_cls):
        """AI usage preview should be present when AI extraction was used."""
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
            'ai_data': {
                'date': '2024-01-15',
                'total_amount': 150.0,
                'vat_amount': 31.5,
                'description': 'Invoice #123',
                'vendor': 'TestVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 420,
                    'completion_tokens': 85,
                    'total_tokens': 505,
                },
            },
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 150.0, 'description': 'Invoice #123'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor', 'MyAdmin')

        preview = result['ai_usage_preview']
        assert preview is not None
        assert preview['administration'] == 'MyAdmin'
        assert preview['feature'] == 'invoice_extraction_TestVendor'
        assert preview['tokens_used'] == 505
        # Cost: (505 / 1000000) * 0.685 = 0.000346
        assert preview['cost_estimate'] == '0.000346'
        assert preview['cost_breakdown']['model'] == 'deepseek/deepseek-chat'
        assert preview['cost_breakdown']['rate_per_million'] == 0.685
        assert preview['cost_breakdown']['total_tokens'] == 505

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_no_ai_usage_preview_for_csv_rule(self, mock_csv_cls, mock_proc_cls):
        """AI usage preview should be None when CSV rule was used."""
        fd, path = tempfile.mkstemp(suffix='.csv')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'csv content',
            'folder': 'Airbnb',
            'url': 'dry-run://test.csv',
            'name': 'test.csv',
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 100.0, 'description': 'Airbnb',
             'parser_used_hint': 'csv_rule'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'Airbnb')

        assert result['ai_usage_preview'] is None

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_usage_preview_zero_tokens_when_no_token_info(self, mock_csv_cls, mock_proc_cls):
        """AI usage preview should show tokens_used=0, cost_estimate=0.000000 when AI lacks token info.

        Validates: Requirements 5.5
        """
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
            'ai_data': {
                'date': '2024-01-15',
                'total_amount': 150.0,
                'vat_amount': 31.5,
                'description': 'Invoice #123',
                'vendor': 'TestVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                },
            },
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 150.0, 'description': 'Invoice #123'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor', 'MyAdmin')

        preview = result['ai_usage_preview']
        assert preview is not None
        assert preview['tokens_used'] == 0
        assert preview['cost_estimate'] == '0.000000'

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_usage_preview_cost_breakdown_formula(self, mock_csv_cls, mock_proc_cls):
        """Cost breakdown should contain correct formula string.

        Validates: Requirements 5.1, 5.2
        """
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
            'ai_data': {
                'date': '2024-01-15',
                'total_amount': 200.0,
                'vat_amount': 42.0,
                'description': 'Invoice #456',
                'vendor': 'TestVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 300,
                    'completion_tokens': 100,
                    'total_tokens': 400,
                },
            },
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 200.0, 'description': 'Invoice #456'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'TestVendor', 'MyAdmin')

        breakdown = result['ai_usage_preview']['cost_breakdown']
        assert breakdown['model'] == 'deepseek/deepseek-chat'
        assert breakdown['rate_per_million'] == 0.685
        assert breakdown['total_tokens'] == 400
        assert breakdown['formula'] == '(400 / 1000000) * 0.685'

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_usage_preview_defaults_administration(self, mock_csv_cls, mock_proc_cls):
        """When administration is None, it should default to 'test-tool-dry-run'.

        Validates: Requirements 5.1
        """
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'TestVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
            'ai_data': {
                'date': '2024-01-15',
                'total_amount': 100.0,
                'vat_amount': 21.0,
                'description': 'Invoice',
                'vendor': 'TestVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 200,
                    'completion_tokens': 50,
                    'total_tokens': 250,
                },
            },
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-01-15', 'amount': 100.0, 'description': 'Invoice'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        # Call without administration parameter
        result = service.process_file_dry_run(path, 'TestVendor')

        preview = result['ai_usage_preview']
        assert preview['administration'] == 'test-tool-dry-run'

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_usage_preview_feature_format(self, mock_csv_cls, mock_proc_cls):
        """Feature field should be 'invoice_extraction_{folder_name}'.

        Validates: Requirements 5.1
        """
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.write(fd, b'data')
        os.close(fd)

        mock_processor = MagicMock()
        mock_processor.process_file.return_value = {
            'txt': 'Invoice text',
            'folder': 'MyCustomVendor',
            'url': 'dry-run://test.pdf',
            'name': 'test.pdf',
            'ai_data': {
                'date': '2024-02-01',
                'total_amount': 500.0,
                'vat_amount': 105.0,
                'description': 'Invoice #789',
                'vendor': 'MyCustomVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 600,
                    'completion_tokens': 150,
                    'total_tokens': 750,
                },
            },
        }
        mock_processor.extract_transactions.return_value = [
            {'date': '2024-02-01', 'amount': 500.0, 'description': 'Invoice #789'}
        ]
        mock_processor._extract_with_ai = MagicMock()
        mock_proc_cls.return_value = mock_processor

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()
        service.processor = mock_processor

        result = service.process_file_dry_run(path, 'MyCustomVendor', 'admin1')

        assert result['ai_usage_preview']['feature'] == 'invoice_extraction_MyCustomVendor'


# ============================================================================
# get_vendor_history Tests
# ============================================================================


@pytest.mark.unit
class TestGetVendorHistory:
    """Tests for InvoiceTestService.get_vendor_history method."""

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_returns_transactions_with_correct_format(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Returned transactions should have date, amount, description keys."""
        from datetime import date

        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = [
            {
                'TransactionDate': date(2024, 1, 15),
                'TransactionAmount': 150.00,
                'TransactionDescription': 'Invoice #12345',
                'ID': 1,
                'TransactionNumber': 'TestVendor',
            },
            {
                'TransactionDate': date(2024, 1, 15),
                'TransactionAmount': 31.50,
                'TransactionDescription': 'BTW Invoice #12345',
                'ID': 2,
                'TransactionNumber': 'TestVendor',
            },
        ]
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        result = service.get_vendor_history('TestVendor', 'admin1')

        assert len(result) == 2
        assert result[0] == {'date': '2024-01-15', 'amount': 150.00, 'description': 'Invoice #12345'}
        assert result[1] == {'date': '2024-01-15', 'amount': 31.50, 'description': 'BTW Invoice #12345'}

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_returns_empty_list_when_no_transactions(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should return empty list when no transactions found."""
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = []
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        result = service.get_vendor_history('UnknownVendor')

        assert result == []

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_returns_empty_list_on_error(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should return empty list when TransactionLogic raises an exception."""
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.side_effect = Exception("Database connection failed")
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        result = service.get_vendor_history('TestVendor')

        assert result == []

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_defaults_folder_name_to_test_vendor(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should default folder_name to 'TestVendor' when empty/None."""
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = []
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        service.get_vendor_history('')

        mock_tl.get_last_transactions.assert_called_once_with('TestVendor', None)

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_limits_results_to_20(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should return at most 20 transactions."""
        from datetime import date

        # Create 25 transactions
        transactions = [
            {
                'TransactionDate': date(2024, 1, i + 1),
                'TransactionAmount': float(i * 10),
                'TransactionDescription': f'Transaction #{i}',
            }
            for i in range(25)
        ]
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = transactions
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        result = service.get_vendor_history('BigVendor')

        assert len(result) == 20

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_handles_error_dict_response(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should return empty list when get_last_transactions returns error dict."""
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = {'error': True, 'message': 'Not found'}
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        result = service.get_vendor_history('TestVendor')

        assert result == []

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_passes_administration_to_transaction_logic(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should pass administration parameter to TransactionLogic."""
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = []
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        service.get_vendor_history('MyVendor', 'tenant-abc')

        mock_tl.get_last_transactions.assert_called_once_with('MyVendor', 'tenant-abc')

    @patch('transaction_logic.TransactionLogic')
    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_handles_string_date(self, mock_csv_cls, mock_proc_cls, mock_tl_cls):
        """Should handle string dates returned from database."""
        mock_tl = MagicMock()
        mock_tl.get_last_transactions.return_value = [
            {
                'TransactionDate': '2024-03-20',
                'TransactionAmount': 99.99,
                'TransactionDescription': 'String date test',
            }
        ]
        mock_tl_cls.return_value = mock_tl

        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        result = service.get_vendor_history('TestVendor')

        assert result[0]['date'] == '2024-03-20'
        assert result[0]['amount'] == 99.99
        assert result[0]['description'] == 'String date test'


# ============================================================================
# rerun_with_custom_prompt Tests
# ============================================================================


@pytest.mark.unit
class TestRerunWithCustomPrompt:
    """Tests for InvoiceTestService.rerun_with_custom_prompt method."""

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_successful_rerun_returns_all_required_keys(self, mock_csv_cls, mock_proc_cls):
        """Result dict should contain success, extraction_result, performance, ai_usage_preview, errors."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        # Mock _call_ai_with_custom_prompt to return a successful result
        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-01-15',
                'total_amount': 150.0,
                'vat_amount': 31.5,
                'description': 'Invoice #12345',
                'vendor': 'TestVendor',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 380,
                    'completion_tokens': 90,
                    'total_tokens': 470,
                },
            }

            result = service.rerun_with_custom_prompt(
                'Some invoice text', 'Extract invoice fields:', 'TestVendor'
            )

        assert 'success' in result
        assert 'extraction_result' in result
        assert 'performance' in result
        assert 'ai_usage_preview' in result
        assert 'errors' in result

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_successful_rerun_returns_extraction_result_with_five_fields(self, mock_csv_cls, mock_proc_cls):
        """Extraction result should have all 5 fields: date, total_amount, vat_amount, description, vendor."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-03-20',
                'total_amount': 250.0,
                'vat_amount': 52.5,
                'description': 'Order #999',
                'vendor': 'AcmeCorp',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 400,
                    'completion_tokens': 80,
                    'total_tokens': 480,
                },
            }

            result = service.rerun_with_custom_prompt(
                'Invoice text here', 'Custom prompt', 'AcmeCorp'
            )

        extraction = result['extraction_result']
        assert extraction['date'] == '2024-03-20'
        assert extraction['total_amount'] == 250.0
        assert extraction['vat_amount'] == 52.5
        assert extraction['description'] == 'Order #999'
        assert extraction['vendor'] == 'AcmeCorp'

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_successful_rerun_measures_ai_duration(self, mock_csv_cls, mock_proc_cls):
        """Performance should include ai_duration_ms as a non-negative integer."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-01-15',
                'total_amount': 100.0,
                'vat_amount': 21.0,
                'description': 'Test',
                'vendor': 'V',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 200,
                    'completion_tokens': 50,
                    'total_tokens': 250,
                },
            }

            result = service.rerun_with_custom_prompt('text', 'prompt')

        assert result['performance']['ai_duration_ms'] >= 0
        assert isinstance(result['performance']['ai_duration_ms'], int)

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_successful_rerun_collects_model_and_tokens(self, mock_csv_cls, mock_proc_cls):
        """Performance should include ai_model and ai_tokens from the AI response."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-01-15',
                'total_amount': 100.0,
                'vat_amount': 21.0,
                'description': 'Test',
                'vendor': 'V',
                '_usage': {
                    'model': 'google/gemini-flash-1.5',
                    'prompt_tokens': 500,
                    'completion_tokens': 120,
                    'total_tokens': 620,
                },
            }

            result = service.rerun_with_custom_prompt('text', 'prompt')

        perf = result['performance']
        assert perf['ai_model'] == 'google/gemini-flash-1.5'
        assert perf['ai_tokens']['prompt_tokens'] == 500
        assert perf['ai_tokens']['completion_tokens'] == 120
        assert perf['ai_tokens']['total_tokens'] == 620

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_successful_rerun_ai_usage_preview_format(self, mock_csv_cls, mock_proc_cls):
        """AI usage preview should use administration='test-tool-rerun' and feature='invoice_extraction_rerun'."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-01-15',
                'total_amount': 100.0,
                'vat_amount': 21.0,
                'description': 'Test',
                'vendor': 'V',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 300,
                    'completion_tokens': 100,
                    'total_tokens': 400,
                },
            }

            result = service.rerun_with_custom_prompt('text', 'prompt')

        preview = result['ai_usage_preview']
        assert preview['administration'] == 'test-tool-rerun'
        assert preview['feature'] == 'invoice_extraction_rerun'
        assert preview['tokens_used'] == 400
        # Cost: (400 / 1000000) * 0.685 = 0.000274
        assert preview['cost_estimate'] == '0.000274'
        assert preview['cost_breakdown']['model'] == 'deepseek/deepseek-chat'
        assert preview['cost_breakdown']['rate_per_million'] == 0.685

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_failure_returns_error_with_details(self, mock_csv_cls, mock_proc_cls):
        """When AI fails, result should have success=False and error details."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.side_effect = RuntimeError("All 6 AI models failed")

            result = service.rerun_with_custom_prompt('text', 'prompt')

        assert result['success'] is False
        assert result['extraction_result'] is None
        assert len(result['errors']) == 1
        error = result['errors'][0]
        assert error['stage'] == 'ai_extraction'
        assert error['error_type'] == 'RuntimeError'
        assert 'All 6 AI models failed' in error['message']
        assert 'stack_trace' in error

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_ai_failure_preserves_performance_metrics(self, mock_csv_cls, mock_proc_cls):
        """On AI failure, performance dict should still be present (with None values)."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.side_effect = RuntimeError("Timeout")

            result = service.rerun_with_custom_prompt('text', 'prompt')

        perf = result['performance']
        assert perf['ai_duration_ms'] is None
        assert perf['ai_model'] is None
        assert perf['ai_tokens'] is None

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_vendor_hint_used_in_extraction_result(self, mock_csv_cls, mock_proc_cls):
        """When vendor_hint is provided and AI returns empty vendor, it should use the hint."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-06-01',
                'total_amount': 75.0,
                'vat_amount': 15.75,
                'description': 'Service fee',
                'vendor': '',  # Empty vendor from AI
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 200,
                    'completion_tokens': 60,
                    'total_tokens': 260,
                },
            }

            result = service.rerun_with_custom_prompt('text', 'prompt', 'MyVendor')

        # When vendor is empty in AI result but vendor_hint provided, should use hint
        assert result['extraction_result']['vendor'] == 'MyVendor'

    @patch('pdf_processor.PDFProcessor')
    @patch('csv_rules.CsvRuleEngine')
    def test_success_is_true_on_successful_extraction(self, mock_csv_cls, mock_proc_cls):
        """success should be True when extraction completes without errors."""
        from services.invoice_test_service import InvoiceTestService
        service = InvoiceTestService()

        with patch.object(service, '_call_ai_with_custom_prompt') as mock_call:
            mock_call.return_value = {
                'date': '2024-01-15',
                'total_amount': 100.0,
                'vat_amount': 21.0,
                'description': 'Test',
                'vendor': 'V',
                '_usage': {
                    'model': 'deepseek/deepseek-chat',
                    'prompt_tokens': 100,
                    'completion_tokens': 50,
                    'total_tokens': 150,
                },
            }

            result = service.rerun_with_custom_prompt('text', 'prompt')

        assert result['success'] is True
