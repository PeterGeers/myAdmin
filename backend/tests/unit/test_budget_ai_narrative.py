"""
Unit tests for BudgetAIService.generate_narrative method.

Tests the narrative generation feature including:
- Row truncation to 50 rows max
- Empty data handling
- Dutch prompt construction
- Proper response structure
- 15-second timeout enforcement
"""
import pytest
from unittest.mock import patch, MagicMock

from services.budget_ai_service import BudgetAIService


@pytest.fixture
def ai_service():
    """Create a BudgetAIService instance with mocked dependencies."""
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        service = BudgetAIService(db=None)
    return service


@pytest.fixture
def sample_dashboard_data():
    """Dashboard data with a few rows for testing."""
    return {
        'rows': [
            {'code': '4000', 'name': 'Omzet', 'budget': 45000.00, 'actual': 42350.75, 'variance': -2649.25},
            {'code': '5000', 'name': 'Kosten', 'budget': 30000.00, 'actual': 31200.50, 'variance': 1200.50},
            {'code': '5100', 'name': 'Huur', 'budget': 12000.00, 'actual': 12000.00, 'variance': 0.00},
        ]
    }


@pytest.mark.unit
class TestGenerateNarrativeSuccess:
    """Test successful narrative generation scenarios."""

    def test_returns_narrative_on_success(self, ai_service, sample_dashboard_data):
        """Successful AI call returns narrative, model_used, and tokens_used."""
        mock_result = {
            'success': True,
            'content': 'De omzet ligt onder budget terwijl kosten hoger uitvallen.',
            'model_used': 'google/gemini-flash-1.5',
            'tokens_used': 120,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.generate_narrative(
                sample_dashboard_data, 'ytd', 2025, 'tenant-1'
            )

        assert result['success'] is True
        assert result['data']['narrative'] == mock_result['content']
        assert result['data']['model_used'] == 'google/gemini-flash-1.5'
        assert result['data']['tokens_used'] == 120

    def test_calls_openrouter_with_dutch_system_prompt(self, ai_service, sample_dashboard_data):
        """System prompt must instruct generation in Dutch."""
        mock_result = {
            'success': True,
            'content': 'Samenvatting...',
            'model_used': 'model-1',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result) as mock_call:
            ai_service.generate_narrative(sample_dashboard_data, 'ytd', 2025, 'tenant-1')

        args = mock_call.call_args
        system_prompt = args[0][0]
        assert 'Nederlands' in system_prompt
        assert '2-4 zinnen' in system_prompt

    def test_calls_openrouter_with_period_and_year_in_user_prompt(self, ai_service, sample_dashboard_data):
        """User prompt includes the fiscal year and period."""
        mock_result = {
            'success': True,
            'content': 'Samenvatting...',
            'model_used': 'model-1',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result) as mock_call:
            ai_service.generate_narrative(sample_dashboard_data, 'q2', 2025, 'tenant-1')

        args = mock_call.call_args
        user_prompt = args[0][1]
        assert '2025' in user_prompt
        assert 'q2' in user_prompt

    def test_calls_openrouter_with_max_tokens_500(self, ai_service, sample_dashboard_data):
        """generate_narrative uses max_tokens_override=500."""
        mock_result = {
            'success': True,
            'content': 'Samenvatting...',
            'model_used': 'model-1',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result) as mock_call:
            ai_service.generate_narrative(sample_dashboard_data, 'ytd', 2025, 'tenant-1')

        kwargs = mock_call.call_args[1]
        assert kwargs['max_tokens_override'] == 500

    def test_calls_openrouter_with_timeout_override_15(self, ai_service, sample_dashboard_data):
        """generate_narrative enforces 15-second timeout via timeout_override."""
        mock_result = {
            'success': True,
            'content': 'Samenvatting...',
            'model_used': 'model-1',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result) as mock_call:
            ai_service.generate_narrative(sample_dashboard_data, 'ytd', 2025, 'tenant-1')

        kwargs = mock_call.call_args[1]
        assert kwargs['timeout_override'] == 15


@pytest.mark.unit
class TestGenerateNarrativeRowTruncation:
    """Test that dashboard rows are limited to 50."""

    def test_truncates_rows_to_50(self, ai_service):
        """When dashboard has more than 50 rows, only first 50 are used."""
        rows = [
            {'code': f'{i:04d}', 'name': f'Account {i}', 'budget': 1000.0, 'actual': 1100.0, 'variance': 100.0}
            for i in range(75)
        ]
        dashboard_data = {'rows': rows}

        mock_result = {
            'success': True,
            'content': 'Samenvatting...',
            'model_used': 'model-1',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result) as mock_call:
            ai_service.generate_narrative(dashboard_data, 'ytd', 2025, 'tenant-1')

        user_prompt = mock_call.call_args[0][1]
        # Each row starts with "- " prefix; count occurrences
        row_count = user_prompt.count('\n- ') + (1 if '\n- ' in user_prompt else 0)
        # Simpler: count lines that start with "- "
        data_section = user_prompt.split('Data:\n')[1]
        row_count = len([line for line in data_section.split('\n') if line.startswith('- ')])
        assert row_count == 50

    def test_uses_all_rows_when_under_50(self, ai_service, sample_dashboard_data):
        """When dashboard has fewer than 50 rows, all are included."""
        mock_result = {
            'success': True,
            'content': 'Samenvatting...',
            'model_used': 'model-1',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result) as mock_call:
            ai_service.generate_narrative(sample_dashboard_data, 'ytd', 2025, 'tenant-1')

        user_prompt = mock_call.call_args[0][1]
        assert '4000' in user_prompt
        assert '5000' in user_prompt
        assert '5100' in user_prompt


@pytest.mark.unit
class TestGenerateNarrativeEmptyData:
    """Test handling of empty or missing dashboard data."""

    def test_empty_rows_returns_no_data_message(self, ai_service):
        """Empty rows list returns a default 'no data' narrative without calling AI."""
        result = ai_service.generate_narrative({'rows': []}, 'ytd', 2025, 'tenant-1')

        assert result['success'] is True
        assert result['data']['narrative'] == 'Geen data beschikbaar voor analyse.'
        assert result['data']['model_used'] is None
        assert result['data']['tokens_used'] == 0

    def test_missing_rows_key_returns_no_data_message(self, ai_service):
        """Missing 'rows' key in dashboard data returns no-data message."""
        result = ai_service.generate_narrative({}, 'ytd', 2025, 'tenant-1')

        assert result['success'] is True
        assert 'Geen data' in result['data']['narrative']


@pytest.mark.unit
class TestGenerateNarrativeFailure:
    """Test error handling when AI service fails."""

    def test_returns_error_when_openrouter_fails(self, ai_service, sample_dashboard_data):
        """When _call_openrouter returns failure, propagate the error."""
        mock_result = {
            'success': False,
            'error': 'AI service unavailable: all models failed',
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.generate_narrative(
                sample_dashboard_data, 'ytd', 2025, 'tenant-1'
            )

        assert result['success'] is False
        assert 'unavailable' in result['error']

    def test_returns_error_when_api_key_missing(self, sample_dashboard_data):
        """When API key not configured, returns unavailable error."""
        with patch.dict('os.environ', {}, clear=True):
            service = BudgetAIService(db=None)
            result = service.generate_narrative(
                sample_dashboard_data, 'ytd', 2025, 'tenant-1'
            )

        assert result['success'] is False
        assert 'API key' in result['error']


@pytest.mark.unit
class TestCallOpenrouterTimeoutOverride:
    """Test that _call_openrouter respects the timeout_override parameter."""

    def test_timeout_override_caps_model_timeout(self, ai_service):
        """When timeout_override is less than model timeout, use the override."""
        mock_model = MagicMock()
        mock_model.model_id = 'test-model'
        mock_model.timeout = 30  # model allows 30s
        mock_model.max_tokens = 1000

        with patch.object(ai_service, '_get_model_chain', return_value=[mock_model]):
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'choices': [{'message': {'content': 'test'}}],
                    'usage': {'total_tokens': 10},
                }
                mock_post.return_value = mock_response

                ai_service._call_openrouter(
                    'system', 'user', 'tenant-1',
                    timeout_override=15
                )

                # Should use 15 (the override) since it's less than model's 30
                mock_post.assert_called_once()
                assert mock_post.call_args[1]['timeout'] == 15

    def test_model_timeout_used_when_less_than_override(self, ai_service):
        """When model timeout is less than override, use model timeout."""
        mock_model = MagicMock()
        mock_model.model_id = 'test-model'
        mock_model.timeout = 10  # model only allows 10s
        mock_model.max_tokens = 1000

        with patch.object(ai_service, '_get_model_chain', return_value=[mock_model]):
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'choices': [{'message': {'content': 'test'}}],
                    'usage': {'total_tokens': 10},
                }
                mock_post.return_value = mock_response

                ai_service._call_openrouter(
                    'system', 'user', 'tenant-1',
                    timeout_override=15
                )

                # Should use 10 (model timeout) since it's less than override's 15
                mock_post.assert_called_once()
                assert mock_post.call_args[1]['timeout'] == 10

    def test_no_timeout_override_uses_model_timeout(self, ai_service):
        """When no timeout_override, use model's configured timeout."""
        mock_model = MagicMock()
        mock_model.model_id = 'test-model'
        mock_model.timeout = 25
        mock_model.max_tokens = 1000

        with patch.object(ai_service, '_get_model_chain', return_value=[mock_model]):
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'choices': [{'message': {'content': 'test'}}],
                    'usage': {'total_tokens': 10},
                }
                mock_post.return_value = mock_response

                ai_service._call_openrouter(
                    'system', 'user', 'tenant-1'
                )

                mock_post.assert_called_once()
                assert mock_post.call_args[1]['timeout'] == 25
