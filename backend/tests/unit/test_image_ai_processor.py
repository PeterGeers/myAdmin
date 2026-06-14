"""
Unit tests for ImageAIProcessor registry integration.

Tests vision profile resolution, model iteration, fallback to None (Tesseract path)
on chain exhaustion, and registry error handling.

Requirements: 6.1, 6.5, 11.3
"""

import pytest
import json
from unittest.mock import patch, MagicMock, mock_open

from services.ai_model_registry import RegistryError, ResolvedModel


@pytest.mark.unit
class TestVisionProfileResolution:
    """Test that ImageAIProcessor resolves the vision profile and iterates models."""

    @pytest.fixture
    def processor(self, mock_env):
        """Create ImageAIProcessor with mocked environment."""
        with patch('image_ai_processor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                from image_ai_processor import ImageAIProcessor
                proc = ImageAIProcessor()
        return proc

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_vision_profile_resolution_uses_registry_chain(
        self, mock_resolver, mock_post, processor
    ):
        """Verify _try_ai_vision resolves 'vision' profile and uses returned chain."""
        # Set up a known chain from the registry
        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=15,
                max_tokens=500,
                cost_tier="cheap",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="google/gemini-2.0-flash-exp:free",
                timeout=15,
                max_tokens=4096,
                cost_tier="free",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        # Mock successful response from first model
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        "date": "2024-06-15",
                        "total_amount": 99.50,
                        "vat_amount": 17.31,
                        "description": "INV-001",
                        "vendor": "TestVendor"
                    })
                }
            }]
        }
        mock_post.return_value = mock_response

        # Mock file reading
        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        # Verify profile was resolved with "vision"
        mock_resolver.resolve_profile.assert_called_once_with("vision")

        # Verify result uses data from the successful model
        assert result is not None
        assert result['total_amount'] == 99.50
        assert result['vat_amount'] == 17.31
        assert result['vendor'] == 'TestVendor'
        assert result['date'] == '2024-06-15'

        # Verify only one API call was made (first model succeeded)
        assert mock_post.call_count == 1

        # Verify the API was called with the first model's config
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert request_json['model'] == "openai/gpt-4o-mini"
        assert request_json['max_tokens'] == 500

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_vision_iterates_models_in_chain_order(
        self, mock_resolver, mock_post, processor
    ):
        """Verify models are tried in order: first fails, second succeeds."""
        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=15,
                max_tokens=500,
                cost_tier="cheap",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="google/gemini-2.0-flash-exp:free",
                timeout=15,
                max_tokens=4096,
                cost_tier="free",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        # First model returns error status, second succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_fail.text = "Internal Server Error"

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        "date": "2024-07-01",
                        "total_amount": 50.00,
                        "vat_amount": 8.68,
                        "description": "Order-123",
                        "vendor": "Shop"
                    })
                }
            }]
        }
        mock_post.side_effect = [mock_response_fail, mock_response_success]

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        # Both models were tried
        assert mock_post.call_count == 2

        # Second model's result is returned
        assert result is not None
        assert result['total_amount'] == 50.00
        assert result['vendor'] == 'Shop'

        # Verify call order: first call used first model, second used second model
        first_call_json = mock_post.call_args_list[0].kwargs.get('json') or mock_post.call_args_list[0][1].get('json')
        second_call_json = mock_post.call_args_list[1].kwargs.get('json') or mock_post.call_args_list[1][1].get('json')
        assert first_call_json['model'] == "openai/gpt-4o-mini"
        assert second_call_json['model'] == "google/gemini-2.0-flash-exp:free"

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_vision_uses_resolved_timeout_and_max_tokens(
        self, mock_resolver, mock_post, processor
    ):
        """Verify that timeout and max_tokens from resolved model are used in API call."""
        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=20,
                max_tokens=800,
                cost_tier="cheap",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': json.dumps({
                        "date": "2024-01-01",
                        "total_amount": 10.0,
                        "vat_amount": 1.74,
                        "description": "Test",
                        "vendor": "V"
                    })
                }
            }]
        }
        mock_post.return_value = mock_response

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            processor._try_ai_vision("test.png", None, None)

        # Verify timeout was passed to requests.post
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs.get('timeout') or call_kwargs[1].get('timeout') == 20

        # Verify max_tokens in the request JSON
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert request_json['max_tokens'] == 800


@pytest.mark.unit
class TestAllModelsFailReturnsNone:
    """Test that _try_ai_vision returns None when all models in chain fail."""

    @pytest.fixture
    def processor(self, mock_env):
        """Create ImageAIProcessor with mocked environment."""
        with patch('image_ai_processor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                from image_ai_processor import ImageAIProcessor
                proc = ImageAIProcessor()
        return proc

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_all_models_timeout_returns_none(
        self, mock_resolver, mock_post, processor
    ):
        """When all models timeout, _try_ai_vision returns None."""
        import requests as real_requests

        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=15,
                max_tokens=500,
                cost_tier="cheap",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="google/gemini-2.0-flash-exp:free",
                timeout=15,
                max_tokens=4096,
                cost_tier="free",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        # All calls timeout
        mock_post.side_effect = real_requests.exceptions.Timeout("Connection timed out")

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        assert result is None
        assert mock_post.call_count == 2

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_all_models_api_error_returns_none(
        self, mock_resolver, mock_post, processor
    ):
        """When all models return API errors, _try_ai_vision returns None."""
        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=15,
                max_tokens=500,
                cost_tier="cheap",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="anthropic/claude-3-haiku",
                timeout=15,
                max_tokens=4096,
                cost_tier="cheap",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        # All return 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        assert result is None
        assert mock_post.call_count == 2

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_all_models_invalid_json_returns_none(
        self, mock_resolver, mock_post, processor
    ):
        """When all models return invalid JSON, _try_ai_vision returns None."""
        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=15,
                max_tokens=500,
                cost_tier="cheap",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="google/gemini-2.0-flash-exp:free",
                timeout=15,
                max_tokens=4096,
                cost_tier="free",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        # All return 200 but with non-JSON content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': 'This is not valid JSON at all'
                }
            }]
        }
        mock_post.return_value = mock_response

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        assert result is None
        assert mock_post.call_count == 2

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_mixed_failures_all_fail_returns_none(
        self, mock_resolver, mock_post, processor
    ):
        """When models fail with different errors (timeout, API error, invalid JSON), returns None."""
        import requests as real_requests

        mock_chain = [
            ResolvedModel(
                model_id="openai/gpt-4o-mini",
                timeout=15,
                max_tokens=500,
                cost_tier="cheap",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="google/gemini-2.0-flash-exp:free",
                timeout=15,
                max_tokens=4096,
                cost_tier="free",
                supports_vision=True,
            ),
            ResolvedModel(
                model_id="anthropic/claude-3-haiku",
                timeout=15,
                max_tokens=4096,
                cost_tier="cheap",
                supports_vision=True,
            ),
        ]
        mock_resolver.resolve_profile.return_value = mock_chain

        # Model 1: timeout, Model 2: API error 500, Model 3: invalid JSON
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Server Error"

        mock_response_bad_json = MagicMock()
        mock_response_bad_json.status_code = 200
        mock_response_bad_json.json.return_value = {
            'choices': [{'message': {'content': 'not json'}}]
        }

        mock_post.side_effect = [
            real_requests.exceptions.Timeout("Timeout"),
            mock_response_500,
            mock_response_bad_json,
        ]

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        assert result is None
        assert mock_post.call_count == 3


@pytest.mark.unit
class TestRegistryErrorReturnsNone:
    """Test that registry errors cause _try_ai_vision to return None (proceed to Tesseract)."""

    @pytest.fixture
    def processor(self, mock_env):
        """Create ImageAIProcessor with mocked environment."""
        with patch('image_ai_processor.load_dotenv'):
            with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
                from image_ai_processor import ImageAIProcessor
                proc = ImageAIProcessor()
        return proc

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_registry_error_on_resolve_returns_none(
        self, mock_resolver, mock_post, processor
    ):
        """When resolver.resolve_profile raises RegistryError, returns None."""
        mock_resolver.resolve_profile.side_effect = RegistryError(
            "Unknown profile 'vision'. Available profiles: ['structured_extraction']"
        )

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.png", None, None)

        assert result is None
        # Verify no API calls were made
        mock_post.assert_not_called()

    @patch('image_ai_processor.requests.post')
    @patch('image_ai_processor.resolver')
    def test_registry_error_does_not_call_api(
        self, mock_resolver, mock_post, processor
    ):
        """Registry error should short-circuit without making any API requests."""
        mock_resolver.resolve_profile.side_effect = RegistryError(
            "Registry validation failed"
        )

        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        with patch('builtins.open', mock_open(read_data=fake_image_data)):
            result = processor._try_ai_vision("test.jpg", "SomeVendor", None)

        assert result is None
        mock_post.assert_not_called()
        mock_resolver.resolve_profile.assert_called_once_with("vision")

    @patch('image_ai_processor.resolver')
    def test_registry_error_allows_tesseract_fallback(
        self, mock_resolver, processor
    ):
        """Full process_image flow: registry error → None from AI → Tesseract fallback triggered."""
        mock_resolver.resolve_profile.side_effect = RegistryError(
            "Unknown profile 'vision'"
        )

        # Mock the Tesseract fallback to return fallback data
        with patch.object(processor, '_try_tesseract') as mock_tesseract:
            mock_tesseract.return_value = {
                'date': '2024-01-01',
                'total_amount': 25.00,
                'vat_amount': 4.34,
                'description': 'Tesseract result',
                'vendor': 'TessVendor'
            }

            fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
            with patch('builtins.open', mock_open(read_data=fake_image_data)):
                result = processor.process_image("test.png", "TessVendor")

        # Tesseract fallback was triggered since AI vision returned None
        mock_tesseract.assert_called_once()
        assert result['vendor'] == 'TessVendor'
        assert result['total_amount'] == 25.00
