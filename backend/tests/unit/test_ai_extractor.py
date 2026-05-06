"""
Unit tests for ai_extractor module.

Tests date validation, JSON parsing from AI responses, fallback model logic,
and data cleaning functions.

Requirements: 1.5, 2.1, 2.3, 8.5
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from ai_extractor import AIExtractor


class TestValidateDate:
    """Tests for _validate_date method."""

    @pytest.fixture
    def extractor(self, mock_env):
        """Create AIExtractor with mocked environment."""
        with patch('ai_extractor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                ext = AIExtractor()
        return ext

    # --- Valid date formats ---

    def test_validate_date_iso_format_returns_iso(self, extractor):
        result = extractor._validate_date('2024-03-15')
        assert result == '2024-03-15'

    def test_validate_date_european_format_returns_iso(self, extractor):
        result = extractor._validate_date('15-03-2024')
        assert result == '2024-03-15'

    def test_validate_date_european_slash_format_returns_iso(self, extractor):
        result = extractor._validate_date('15/03/2024')
        assert result == '2024-03-15'

    def test_validate_date_iso_slash_format_returns_iso(self, extractor):
        result = extractor._validate_date('2024/03/15')
        assert result == '2024-03-15'

    # --- Invalid / missing dates ---

    def test_validate_date_none_returns_today(self, extractor):
        result = extractor._validate_date(None)
        assert result == datetime.now().strftime('%Y-%m-%d')

    def test_validate_date_empty_string_returns_today(self, extractor):
        result = extractor._validate_date('')
        assert result == datetime.now().strftime('%Y-%m-%d')

    def test_validate_date_invalid_format_returns_today(self, extractor):
        result = extractor._validate_date('not-a-date')
        assert result == datetime.now().strftime('%Y-%m-%d')

    def test_validate_date_partial_date_returns_today(self, extractor):
        result = extractor._validate_date('2024-13')
        assert result == datetime.now().strftime('%Y-%m-%d')

    def test_validate_date_garbage_returns_today(self, extractor):
        result = extractor._validate_date('abc123xyz')
        assert result == datetime.now().strftime('%Y-%m-%d')

    # --- Output format consistency ---

    def test_validate_date_always_returns_yyyy_mm_dd(self, extractor):
        """All valid dates should return YYYY-MM-DD format."""
        dates = ['2024-01-01', '31-12-2023', '01/06/2024', '2023/12/25']
        for date_str in dates:
            result = extractor._validate_date(date_str)
            # Verify format: YYYY-MM-DD
            parts = result.split('-')
            assert len(parts) == 3
            assert len(parts[0]) == 4
            assert len(parts[1]) == 2
            assert len(parts[2]) == 2


class TestFallbackData:
    """Tests for _fallback_data method."""

    @pytest.fixture
    def extractor(self, mock_env):
        with patch('ai_extractor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                ext = AIExtractor()
        return ext

    def test_fallback_data_with_vendor_hint(self, extractor):
        result = extractor._fallback_data('Ziggo')
        assert result['vendor'] == 'Ziggo'
        assert result['total_amount'] == 0.0
        assert result['vat_amount'] == 0.0
        assert 'Ziggo' in result['description']
        assert result['date'] == datetime.now().strftime('%Y-%m-%d')

    def test_fallback_data_without_vendor_hint(self, extractor):
        result = extractor._fallback_data(None)
        assert result['vendor'] == 'Unknown'
        assert result['total_amount'] == 0.0
        assert result['vat_amount'] == 0.0
        assert 'Unknown' in result['description']

    def test_fallback_data_returns_all_required_keys(self, extractor):
        result = extractor._fallback_data('Test')
        required_keys = {'date', 'total_amount', 'vat_amount', 'description', 'vendor'}
        assert set(result.keys()) == required_keys


class TestExtractInvoiceData:
    """Tests for extract_invoice_data method."""

    @pytest.fixture
    def extractor(self, mock_env):
        with patch('ai_extractor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                ext = AIExtractor()
        return ext

    def test_extract_invoice_data_no_api_key_returns_fallback(self, mock_env):
        """Without API key, should return fallback data."""
        with patch('ai_extractor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': ''}, clear=False):
                ext = AIExtractor()
                ext.api_key = None

        result = ext.extract_invoice_data("Invoice text content")
        assert result['total_amount'] == 0.0
        assert result['vat_amount'] == 0.0

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_successful_response(self, mock_post, extractor):
        """Test successful AI extraction with valid JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-03-15", "total_amount": 125.50, "vat_amount": 21.84, "description": "INV-2024-001", "vendor": "Ziggo"}'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice from Ziggo")

        assert result['date'] == '2024-03-15'
        assert result['total_amount'] == 125.50
        assert result['vat_amount'] == 21.84
        assert result['description'] == 'INV-2024-001'
        assert result['vendor'] == 'Ziggo'

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_json_in_code_block(self, mock_post, extractor):
        """Test extraction when AI wraps JSON in code block."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '```json\n{"date": "2024-01-10", "total_amount": 50.0, "vat_amount": 8.68, "description": "Order 123", "vendor": "Bol.com"}\n```'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice text")

        assert result['date'] == '2024-01-10'
        assert result['total_amount'] == 50.0
        assert result['vendor'] == 'Bol.com'

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_invalid_json_tries_next_model(self, mock_post, extractor):
        """Test that invalid JSON from first model triggers fallback to next."""
        # First call returns invalid JSON, second returns valid
        mock_response_bad = MagicMock()
        mock_response_bad.status_code = 200
        mock_response_bad.json.return_value = {
            'choices': [{'message': {'content': 'This is not JSON at all'}}]
        }

        mock_response_good = MagicMock()
        mock_response_good.status_code = 200
        mock_response_good.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-06-01", "total_amount": 99.99, "vat_amount": 17.36, "description": "Test", "vendor": "TestVendor"}'
                }
            }]
        }

        mock_post.side_effect = [mock_response_bad, mock_response_good]

        result = extractor.extract_invoice_data("Invoice text")

        assert result['total_amount'] == 99.99
        assert result['vendor'] == 'TestVendor'

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_all_models_fail_returns_fallback(self, mock_post, extractor):
        """Test that when all models fail, fallback data is returned."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice text", vendor_hint="TestVendor")

        assert result['total_amount'] == 0.0
        assert result['vendor'] == 'TestVendor'

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_timeout_tries_next_model(self, mock_post, extractor):
        """Test that timeout on first model triggers next model attempt."""
        import requests as real_requests

        mock_response_good = MagicMock()
        mock_response_good.status_code = 200
        mock_response_good.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-05-01", "total_amount": 75.0, "vat_amount": 13.02, "description": "Timeout test", "vendor": "Vendor"}'
                }
            }]
        }

        mock_post.side_effect = [
            real_requests.exceptions.Timeout("Connection timed out"),
            mock_response_good
        ]

        result = extractor.extract_invoice_data("Invoice text")

        assert result['total_amount'] == 75.0

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_with_previous_transactions(self, mock_post, extractor):
        """Test that previous transactions are included in context."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-04-01", "total_amount": 45.0, "vat_amount": 7.81, "description": "Monthly", "vendor": "KPN"}'
                }
            }]
        }
        mock_post.return_value = mock_response

        previous = [
            {'Datum': '2024-03-01', 'Omschrijving': 'KPN Monthly', 'Bedrag': 45.0},
            {'Datum': '2024-02-01', 'Omschrijving': 'KPN Monthly', 'Bedrag': 45.0},
        ]

        result = extractor.extract_invoice_data("Invoice text", previous_transactions=previous)

        assert result['vendor'] == 'KPN'
        # Verify the API was called (context was built)
        mock_post.assert_called_once()

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_rounds_amounts(self, mock_post, extractor):
        """Test that amounts are rounded to 2 decimal places."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-01-01", "total_amount": 99.999, "vat_amount": 17.3554, "description": "Test", "vendor": "V"}'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice text")

        assert result['total_amount'] == 100.0
        assert result['vat_amount'] == 17.36
