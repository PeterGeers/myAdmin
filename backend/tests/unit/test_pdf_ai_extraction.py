"""
Unit tests for pdf_ai_extraction.py

Tests the AI-powered invoice extraction module:
- extract_with_ai() - AI extraction with mocked OpenRouter API
- log_ai_usage() - Usage logging with mocked tracker

Task 52 of Phase 7: Missing Test Coverage
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── extract_with_ai ───────────────────────────────────────────────────────


class TestExtractWithAI:

    @patch('database.DatabaseManager')
    @patch('ai_extractor.AIExtractor')
    def test_success_returns_result(self, mock_extractor_cls, mock_db_cls):
        """extract_with_ai returns AI result on success."""
        mock_extractor = MagicMock()
        mock_extractor_cls.return_value = mock_extractor
        mock_extractor.extract_invoice_data.return_value = {
            'total_amount': 125.50,
            'vendor': 'Acme Corp',
            'date': '2025-06-15',
            '_usage': {'total_tokens': 500, 'model': 'deepseek/deepseek-chat'}
        }
        mock_db_cls.return_value.get_previous_transactions.return_value = []

        from pdf_ai_extraction import extract_with_ai
        result = extract_with_ai(['Invoice #123', 'Total: €125.50'], 'AcmeCorp')

        assert result is not None
        assert result['total_amount'] == 125.50
        assert result['vendor'] == 'Acme Corp'
        mock_extractor.extract_invoice_data.assert_called_once()

    @patch('database.DatabaseManager')
    @patch('ai_extractor.AIExtractor')
    def test_zero_amount_returns_result(self, mock_extractor_cls, mock_db_cls):
        """extract_with_ai returns result even with zero amount."""
        mock_extractor = MagicMock()
        mock_extractor_cls.return_value = mock_extractor
        mock_extractor.extract_invoice_data.return_value = {
            'total_amount': 0,
            'vendor': 'Unknown',
            '_usage': {'total_tokens': 200, 'model': 'deepseek/deepseek-chat'}
        }
        mock_db_cls.return_value.get_previous_transactions.return_value = []

        from pdf_ai_extraction import extract_with_ai
        result = extract_with_ai(['Some text'], 'UnknownVendor')

        assert result is not None
        assert result['total_amount'] == 0

    @patch('database.DatabaseManager')
    @patch('ai_extractor.AIExtractor')
    def test_exception_returns_none(self, mock_extractor_cls, mock_db_cls):
        """extract_with_ai returns None on exception."""
        mock_extractor_cls.side_effect = RuntimeError('API key missing')

        from pdf_ai_extraction import extract_with_ai
        result = extract_with_ai(['text'], 'SomeVendor')

        assert result is None

    @patch('database.DatabaseManager')
    @patch('ai_extractor.AIExtractor')
    def test_db_failure_continues_extraction(self, mock_extractor_cls, mock_db_cls):
        """extract_with_ai continues even if previous transactions lookup fails."""
        mock_db_cls.return_value.get_previous_transactions.side_effect = Exception('DB down')
        mock_extractor = MagicMock()
        mock_extractor_cls.return_value = mock_extractor
        mock_extractor.extract_invoice_data.return_value = {
            'total_amount': 50.0,
            '_usage': {'total_tokens': 100, 'model': 'test'}
        }

        from pdf_ai_extraction import extract_with_ai
        result = extract_with_ai(['Invoice text'], 'Vendor')

        assert result is not None
        assert result['total_amount'] == 50.0

    @patch('database.DatabaseManager')
    @patch('ai_extractor.AIExtractor')
    def test_passes_folder_name_as_vendor_hint(self, mock_extractor_cls, mock_db_cls):
        """extract_with_ai passes folder_name as vendor_hint to AI extractor."""
        mock_extractor = MagicMock()
        mock_extractor_cls.return_value = mock_extractor
        mock_extractor.extract_invoice_data.return_value = {
            'total_amount': 100.0, '_usage': {}
        }
        mock_db_cls.return_value.get_previous_transactions.return_value = [
            {'amount': 95.0, 'date': '2025-05-01'}
        ]

        from pdf_ai_extraction import extract_with_ai
        extract_with_ai(['lines'], 'SpecificVendor')

        call_args = mock_extractor.extract_invoice_data.call_args
        assert call_args[0][1] == 'SpecificVendor'  # vendor_hint
        assert call_args[0][2] == [{'amount': 95.0, 'date': '2025-05-01'}]  # previous_transactions


# ── log_ai_usage ──────────────────────────────────────────────────────────


class TestLogAIUsage:

    @patch('database.DatabaseManager')
    @patch('services.ai_usage_tracker.AIUsageTracker')
    def test_logs_usage_with_tokens(self, mock_tracker_cls, mock_db_cls):
        """log_ai_usage logs when tokens > 0."""
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value = mock_tracker

        from pdf_ai_extraction import log_ai_usage
        log_ai_usage(
            'TestVendor',
            {'total_amount': 100, '_usage': {'total_tokens': 500, 'model': 'deepseek/deepseek-chat'}},
            tenant='TestTenant'
        )

        mock_tracker.log_ai_request.assert_called_once_with(
            administration='TestTenant',
            template_type='invoice_extraction_TestVendor',
            tokens_used=500,
            model_used='deepseek/deepseek-chat'
        )

    @patch('database.DatabaseManager')
    @patch('services.ai_usage_tracker.AIUsageTracker')
    def test_skips_logging_when_zero_tokens(self, mock_tracker_cls, mock_db_cls):
        """log_ai_usage skips logging when tokens_used is 0."""
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value = mock_tracker

        from pdf_ai_extraction import log_ai_usage
        log_ai_usage('Vendor', {'total_amount': 100, '_usage': {'total_tokens': 0}})

        mock_tracker.log_ai_request.assert_not_called()

    @patch('database.DatabaseManager')
    @patch('services.ai_usage_tracker.AIUsageTracker')
    def test_skips_logging_when_no_usage(self, mock_tracker_cls, mock_db_cls):
        """log_ai_usage skips logging when _usage is missing."""
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value = mock_tracker

        from pdf_ai_extraction import log_ai_usage
        log_ai_usage('Vendor', {'total_amount': 100})

        mock_tracker.log_ai_request.assert_not_called()

    @patch('database.DatabaseManager')
    @patch('services.ai_usage_tracker.AIUsageTracker')
    def test_handles_none_result(self, mock_tracker_cls, mock_db_cls):
        """log_ai_usage handles None ai_result gracefully."""
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value = mock_tracker

        from pdf_ai_extraction import log_ai_usage
        log_ai_usage('Vendor', None)

        mock_tracker.log_ai_request.assert_not_called()

    @patch('database.DatabaseManager')
    @patch('services.ai_usage_tracker.AIUsageTracker')
    def test_exception_does_not_propagate(self, mock_tracker_cls, mock_db_cls):
        """log_ai_usage never raises — logging failures are swallowed."""
        mock_tracker_cls.side_effect = RuntimeError('Tracker init failed')

        from pdf_ai_extraction import log_ai_usage
        # Should not raise
        log_ai_usage(
            'Vendor',
            {'_usage': {'total_tokens': 500, 'model': 'test'}},
            tenant='T'
        )

    @patch('database.DatabaseManager')
    @patch('services.ai_usage_tracker.AIUsageTracker')
    def test_uses_unknown_tenant_when_none(self, mock_tracker_cls, mock_db_cls):
        """log_ai_usage defaults to 'unknown' tenant when not provided."""
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value = mock_tracker

        from pdf_ai_extraction import log_ai_usage
        log_ai_usage('Vendor', {'_usage': {'total_tokens': 100, 'model': 'test'}})

        call_args = mock_tracker.log_ai_request.call_args
        assert call_args[1]['administration'] == 'unknown'
