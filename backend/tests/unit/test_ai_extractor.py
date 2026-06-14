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
        required_keys = {'date', 'total_amount', 'vat_amount', 'description', 'vendor', '_usage'}
        assert set(result.keys()) == required_keys

    def test_fallback_data_usage_has_zero_tokens(self, extractor):
        result = extractor._fallback_data('Test')
        assert result['_usage']['prompt_tokens'] == 0
        assert result['_usage']['completion_tokens'] == 0
        assert result['_usage']['total_tokens'] == 0
        assert result['_usage']['model'] == ''


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
            }],
            'usage': {
                'prompt_tokens': 500,
                'completion_tokens': 50,
                'total_tokens': 550
            }
        }
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice from Ziggo")

        assert result['date'] == '2024-03-15'
        assert result['total_amount'] == 125.50
        assert result['vat_amount'] == 21.84
        assert result['description'] == 'INV-2024-001'
        assert result['vendor'] == 'Ziggo'
        assert '_usage' in result
        assert result['_usage']['prompt_tokens'] == 500
        assert result['_usage']['completion_tokens'] == 50
        assert result['_usage']['total_tokens'] == 550
        assert result['_usage']['model'] == 'deepseek/deepseek-chat'

    @patch('ai_extractor.requests.post')
    def test_extract_invoice_data_usage_defaults_when_missing(self, mock_post, extractor):
        """Test that _usage defaults to zeros when API response has no usage field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-03-15", "total_amount": 100.0, "vat_amount": 21.0, "description": "Test", "vendor": "TestVendor"}'
                }
            }]
        }
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice text")

        assert result['_usage']['prompt_tokens'] == 0
        assert result['_usage']['completion_tokens'] == 0
        assert result['_usage']['total_tokens'] == 0
        assert result['_usage']['model'] == 'deepseek/deepseek-chat'

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
    def test_extract_invoice_data_all_models_fail_returns_error(self, mock_post, extractor):
        """Test that when all models fail, an error dict is returned."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = extractor.extract_invoice_data("Invoice text", vendor_hint="TestVendor")

        assert 'error' in result
        assert result['error'] == "AI extraction failed: invalid response format"

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


class TestAIExtractorRegistryIntegration:
    """Tests for AIExtractor registry integration.

    Validates that the AIExtractor correctly uses the ai_model_registry
    resolver for fallback chain iteration, error handling, and usage tracking.

    Requirements: 5.2, 5.4, 5.5, 11.3, 11.4
    """

    @pytest.fixture
    def extractor(self, mock_env):
        """Create AIExtractor with mocked environment."""
        with patch('ai_extractor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                ext = AIExtractor()
        return ext

    @pytest.mark.unit
    @patch('ai_extractor.requests.post')
    @patch('ai_extractor.resolver.resolve_profile')
    def test_fallback_iteration_order(self, mock_resolve, mock_post, extractor):
        """Test that AIExtractor iterates models in chain order, using Nth on success.

        Validates: Requirements 5.2 — iterate in order, skip on failure, return first success.
        """
        from services.ai_model_registry import ResolvedModel

        # Set up a 3-model chain
        chain = [
            ResolvedModel(model_id="model-a/first", timeout=10, max_tokens=500, cost_tier="free", supports_vision=False),
            ResolvedModel(model_id="model-b/second", timeout=10, max_tokens=500, cost_tier="cheap", supports_vision=False),
            ResolvedModel(model_id="model-c/third", timeout=15, max_tokens=1000, cost_tier="paid", supports_vision=False),
        ]
        mock_resolve.return_value = chain

        # First two models fail (non-200 status), third succeeds
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-06-01", "total_amount": 200.0, "vat_amount": 34.71, "description": "Test invoice", "vendor": "TestVendor"}'
                }
            }],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}
        }

        mock_post.side_effect = [fail_response, fail_response, success_response]

        result = extractor.extract_invoice_data("Invoice text content")

        # Verify the third model's result is returned
        assert result['total_amount'] == 200.0
        assert result['vendor'] == 'TestVendor'
        assert result['_usage']['model'] == 'model-c/third'

        # Verify all 3 models were attempted
        assert mock_post.call_count == 3

        # Verify call order matches chain order
        calls = mock_post.call_args_list
        assert calls[0][1]['json']['model'] == 'model-a/first'
        assert calls[1][1]['json']['model'] == 'model-b/second'
        assert calls[2][1]['json']['model'] == 'model-c/third'

        # Verify resolve_profile was called with correct profile name
        mock_resolve.assert_called_once_with("structured_extraction")

    @pytest.mark.unit
    @patch('ai_extractor.requests.post')
    @patch('ai_extractor.resolver.resolve_profile')
    def test_registry_error_returns_error_dict(self, mock_resolve, mock_post, extractor):
        """Test that RegistryError from resolve_profile returns proper error dict.

        Validates: Requirements 5.5 — return error dict when registry is unavailable.
        """
        from services.ai_model_registry import RegistryError

        mock_resolve.side_effect = RegistryError(
            "Unknown profile 'structured_extraction'. Available profiles: []"
        )

        result = extractor.extract_invoice_data("Invoice text content")

        # Should return error dict with registry unavailability message
        assert 'error' in result
        assert 'Registry unavailable:' in result['error']
        assert 'structured_extraction' in result['error']

        # Should NOT have attempted any API calls
        mock_post.assert_not_called()

    @pytest.mark.unit
    @patch('ai_extractor.requests.post')
    @patch('ai_extractor.resolver.resolve_profile')
    def test_all_models_fail_returns_terminal_error(self, mock_resolve, mock_post, extractor):
        """Test that when all models fail, the terminal error structure is returned.

        Validates: Requirements 11.3 — error dict with "error" key for AIExtractor.
        """
        from services.ai_model_registry import ResolvedModel

        chain = [
            ResolvedModel(model_id="model-a/first", timeout=10, max_tokens=500, cost_tier="free", supports_vision=False),
            ResolvedModel(model_id="model-b/second", timeout=10, max_tokens=500, cost_tier="cheap", supports_vision=False),
        ]
        mock_resolve.return_value = chain

        # All models return non-200 responses
        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Server Error"
        mock_post.return_value = fail_response

        result = extractor.extract_invoice_data("Invoice text content")

        # Terminal failure: error dict with specific message
        assert result == {"error": "AI extraction failed: invalid response format"}

        # Both models were attempted
        assert mock_post.call_count == 2

    @pytest.mark.unit
    @patch('ai_extractor.requests.post')
    @patch('ai_extractor.resolver.resolve_profile')
    def test_usage_metadata_contains_model_id(self, mock_resolve, mock_post, extractor):
        """Test that _usage.model matches the successful model's model_id from chain.

        Validates: Requirements 11.4 — usage data reports correct model_used.
        """
        from services.ai_model_registry import ResolvedModel

        chain = [
            ResolvedModel(model_id="fail-model/v1", timeout=5, max_tokens=500, cost_tier="free", supports_vision=False),
            ResolvedModel(model_id="success-model/v2", timeout=10, max_tokens=1000, cost_tier="cheap", supports_vision=False),
        ]
        mock_resolve.return_value = chain

        import requests as real_requests

        # First model times out, second succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2024-01-15", "total_amount": 50.0, "vat_amount": 8.68, "description": "Test", "vendor": "Acme"}'
                }
            }],
            'usage': {'prompt_tokens': 200, 'completion_tokens': 30, 'total_tokens': 230}
        }

        mock_post.side_effect = [
            real_requests.exceptions.Timeout("Timed out"),
            success_response,
        ]

        result = extractor.extract_invoice_data("Invoice text content")

        # Usage metadata must contain the successful model's identifier
        assert result['_usage']['model'] == 'success-model/v2'
        assert result['_usage']['prompt_tokens'] == 200
        assert result['_usage']['completion_tokens'] == 30
        assert result['_usage']['total_tokens'] == 230
