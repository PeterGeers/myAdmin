"""
Unit tests for BudgetAIService — suggest_adjustments,
_call_openrouter graceful degradation, and Property 10 parameter safety.

Tests NOT covered here (already tested elsewhere):
- generate_narrative → test_budget_ai_narrative.py
- translate_query → test_budget_ai_translate_query.py

Feature: fin-budget
Requirements: 9.4, 10.2, 11.4, 11.5
"""

import json
import pytest
from unittest.mock import patch, MagicMock
import requests.exceptions

from services.budget_ai_service import BudgetAIService
from services.ai_model_registry import RegistryError


@pytest.fixture
def ai_service():
    """Create a BudgetAIService instance with mocked env and dependencies."""
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-key'}):
        service = BudgetAIService(db=None)
    return service


@pytest.fixture
def sample_budget_lines():
    """A small set of budget lines for testing suggest_adjustments."""
    return [
        {
            'account_code': '4000',
            'account_name': 'Omzet',
            **{f'month_{i:02d}': 1000.0 for i in range(1, 13)},
        },
        {
            'account_code': '5100',
            'account_name': 'Huur',
            **{f'month_{i:02d}': 2000.0 for i in range(1, 13)},
        },
    ]



# ──────────────────────────────────────────────────────────────────────────────
# suggest_adjustments tests (Requirement 11.4, 11.5)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSuggestAdjustmentsPayloadLimit:
    """Validates: Requirement 11.4 — max 100 lines enforcement."""

    def test_rejects_more_than_100_lines(self, ai_service):
        """When budget_lines exceeds 100, return error without calling AI."""
        lines = [
            {'account_code': f'{i:04d}', 'account_name': f'Acc {i}',
             **{f'month_{m:02d}': 100.0 for m in range(1, 13)}}
            for i in range(101)
        ]

        result = ai_service.suggest_adjustments(lines, "Test notes", "tenant-1")

        assert result['success'] is False
        assert "max 100" in result['error'].lower() or "Too many" in result['error']

    def test_accepts_exactly_100_lines(self, ai_service):
        """Exactly 100 lines should be accepted and sent to AI."""
        lines = [
            {'account_code': f'{i:04d}', 'account_name': f'Acc {i}',
             **{f'month_{m:02d}': 100.0 for m in range(1, 13)}}
            for i in range(100)
        ]

        mock_result = {
            'success': True,
            'content': '[]',
            'model_used': 'test-model',
            'tokens_used': 50,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(lines, "Notes", "tenant-1")

        assert result['success'] is True


@pytest.mark.unit
class TestSuggestAdjustmentsFiltering:
    """Validates: Requirement 11.5 — account code filtering on suggestions."""

    def test_filters_unknown_account_codes(self, ai_service, sample_budget_lines):
        """Suggestions referencing codes not in budget_lines are removed."""
        ai_suggestions = json.dumps([
            {
                'account_code': '4000',
                'account_name': 'Omzet',
                'affected_months': [1, 2, 3],
                'current_amounts': [1000, 1000, 1000],
                'suggested_amounts': [1200, 1200, 1200],
                'reasoning': 'Revenue increase',
            },
            {
                'account_code': '9999',
                'account_name': 'Unknown',
                'affected_months': [1],
                'current_amounts': [0],
                'suggested_amounts': [500],
                'reasoning': 'This account is not in the budget',
            },
        ])

        mock_result = {
            'success': True,
            'content': ai_suggestions,
            'model_used': 'test-model',
            'tokens_used': 200,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(
                sample_budget_lines, "Revenue up", "tenant-1"
            )

        assert result['success'] is True
        suggestions = result['data']['suggestions']
        assert len(suggestions) == 1
        assert suggestions[0]['account_code'] == '4000'

    def test_keeps_all_valid_account_codes(self, ai_service, sample_budget_lines):
        """Suggestions with known account codes are kept."""
        ai_suggestions = json.dumps([
            {
                'account_code': '4000',
                'account_name': 'Omzet',
                'affected_months': [6, 7],
                'current_amounts': [1000, 1000],
                'suggested_amounts': [1100, 1100],
                'reasoning': 'Seasonal increase',
            },
            {
                'account_code': '5100',
                'account_name': 'Huur',
                'affected_months': [6, 7, 8, 9, 10, 11, 12],
                'current_amounts': [2000] * 7,
                'suggested_amounts': [2100] * 7,
                'reasoning': '5% rent increase from June',
            },
        ])

        mock_result = {
            'success': True,
            'content': ai_suggestions,
            'model_used': 'deepseek/deepseek-chat',
            'tokens_used': 400,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(
                sample_budget_lines, "Huur stijgt 5% vanaf juni", "tenant-1"
            )

        assert result['success'] is True
        assert len(result['data']['suggestions']) == 2

    def test_all_unknown_codes_returns_empty_list(self, ai_service, sample_budget_lines):
        """If AI only suggests unknown accounts, result is empty list."""
        ai_suggestions = json.dumps([
            {
                'account_code': '9999',
                'account_name': 'Fake',
                'affected_months': [1],
                'current_amounts': [0],
                'suggested_amounts': [100],
                'reasoning': 'Made up',
            },
        ])

        mock_result = {
            'success': True,
            'content': ai_suggestions,
            'model_used': 'test-model',
            'tokens_used': 100,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(
                sample_budget_lines, "Notes", "tenant-1"
            )

        assert result['success'] is True
        assert result['data']['suggestions'] == []


@pytest.mark.unit
class TestSuggestAdjustmentsSuccess:
    """Test successful parsing of AI suggestions."""

    def test_returns_model_and_tokens(self, ai_service, sample_budget_lines):
        """Success response includes model_used and tokens_used."""
        mock_result = {
            'success': True,
            'content': '[]',
            'model_used': 'google/gemini-flash-1.5',
            'tokens_used': 650,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(
                sample_budget_lines, "No changes", "tenant-1"
            )

        assert result['data']['model_used'] == 'google/gemini-flash-1.5'
        assert result['data']['tokens_used'] == 650

    def test_handles_invalid_json_response_gracefully(self, ai_service, sample_budget_lines):
        """If AI returns non-parseable JSON, suggestions list is empty."""
        mock_result = {
            'success': True,
            'content': "Sorry, I can't provide suggestions right now.",
            'model_used': 'test-model',
            'tokens_used': 30,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(
                sample_budget_lines, "Notes", "tenant-1"
            )

        assert result['success'] is True
        assert result['data']['suggestions'] == []

    def test_handles_markdown_wrapped_json(self, ai_service, sample_budget_lines):
        """AI response wrapped in markdown code block is correctly extracted."""
        suggestion = [{
            'account_code': '4000',
            'account_name': 'Omzet',
            'affected_months': [1],
            'current_amounts': [1000],
            'suggested_amounts': [1500],
            'reasoning': 'Growth forecast',
        }]
        content = f"```json\n{json.dumps(suggestion)}\n```"

        mock_result = {
            'success': True,
            'content': content,
            'model_used': 'test-model',
            'tokens_used': 100,
        }

        with patch.object(ai_service, '_call_openrouter', return_value=mock_result):
            result = ai_service.suggest_adjustments(
                sample_budget_lines, "Growth", "tenant-1"
            )

        assert result['success'] is True
        assert len(result['data']['suggestions']) == 1
        assert result['data']['suggestions'][0]['account_code'] == '4000'


# ──────────────────────────────────────────────────────────────────────────────
# _call_openrouter graceful degradation tests (Requirement 9.4)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCallOpenrouterGracefulDegradation:
    """Test that _call_openrouter handles failures gracefully."""

    def test_no_api_key_returns_error(self):
        """When OPENROUTER_API_KEY is not set, returns graceful error."""
        with patch.dict('os.environ', {}, clear=True):
            service = BudgetAIService(db=None)

        result = service._call_openrouter("system", "user", "tenant-1")

        assert result['success'] is False
        assert 'API key' in result['error']

    def test_registry_error_returns_graceful_error(self, ai_service):
        """When RegistryError is raised, returns AI unavailable error."""
        with patch.object(
            ai_service, '_get_model_chain',
            side_effect=RegistryError("Profile not found")
        ):
            result = ai_service._call_openrouter("system", "user", "tenant-1")

        assert result['success'] is False
        assert 'unavailable' in result['error'].lower()
        assert 'Profile not found' in result['error']

    def test_all_models_timeout_returns_error(self, ai_service):
        """When every model in the chain times out, returns unavailable error."""
        mock_model_1 = MagicMock()
        mock_model_1.model_id = 'model-a'
        mock_model_1.timeout = 10
        mock_model_1.max_tokens = 1000

        mock_model_2 = MagicMock()
        mock_model_2.model_id = 'model-b'
        mock_model_2.timeout = 15
        mock_model_2.max_tokens = 1000

        with patch.object(ai_service, '_get_model_chain', return_value=[mock_model_1, mock_model_2]):
            with patch('requests.post', side_effect=requests.exceptions.Timeout("timeout")):
                result = ai_service._call_openrouter("system", "user", "tenant-1")

        assert result['success'] is False
        assert 'all models failed' in result['error'].lower() or 'unavailable' in result['error'].lower()

    def test_successful_response_returns_content(self, ai_service):
        """Successful OpenRouter response returns content, model_used, tokens_used."""
        mock_model = MagicMock()
        mock_model.model_id = 'google/gemini-flash-1.5'
        mock_model.timeout = 30
        mock_model.max_tokens = 1000

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'AI generated response'}}],
            'usage': {'total_tokens': 250},
        }

        with patch.object(ai_service, '_get_model_chain', return_value=[mock_model]):
            with patch('requests.post', return_value=mock_response):
                result = ai_service._call_openrouter("system", "user", "tenant-1")

        assert result['success'] is True
        assert result['content'] == 'AI generated response'
        assert result['model_used'] == 'google/gemini-flash-1.5'
        assert result['tokens_used'] == 250

    def test_first_model_fails_second_succeeds(self, ai_service):
        """Fallback: first model times out, second model succeeds."""
        mock_model_1 = MagicMock()
        mock_model_1.model_id = 'model-a'
        mock_model_1.timeout = 10
        mock_model_1.max_tokens = 1000

        mock_model_2 = MagicMock()
        mock_model_2.model_id = 'model-b'
        mock_model_2.timeout = 20
        mock_model_2.max_tokens = 1000

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'Fallback response'}}],
            'usage': {'total_tokens': 100},
        }

        def post_side_effect(*args, **kwargs):
            # Check which model is being called via the json body
            body = kwargs.get('json', {})
            if body.get('model') == 'model-a':
                raise requests.exceptions.Timeout("timeout")
            return mock_response

        with patch.object(ai_service, '_get_model_chain', return_value=[mock_model_1, mock_model_2]):
            with patch('requests.post', side_effect=post_side_effect):
                result = ai_service._call_openrouter("system", "user", "tenant-1")

        assert result['success'] is True
        assert result['model_used'] == 'model-b'
        assert result['content'] == 'Fallback response'


# ──────────────────────────────────────────────────────────────────────────────
# Property 10 — AI query parameter safety (Requirement 10.2)
# Validates parameter validation logic directly (not duplicating translate_query
# integration tests, but testing the validation rules independently).
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestProperty10ParameterSafety:
    """Validates: Property 10 — AI query parameter safety.

    Tests that translate_query validates parameters:
    - Only allowed keys pass through
    - No SQL fragments in values
    - No semicolons
    - No values > 100 chars
    """

    def test_union_sql_fragment_rejected(self, ai_service):
        """UNION-based SQL injection attempt is rejected."""
        ai_response = json.dumps({
            "parent_code": "4000 UNION SELECT password FROM users",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is False

    def test_update_sql_fragment_rejected(self, ai_service):
        """UPDATE SQL injection attempt is rejected."""
        ai_response = json.dumps({
            "reference_number": "UPDATE budget_lines SET month_01=0",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is False

    def test_alter_sql_fragment_rejected(self, ai_service):
        """ALTER TABLE injection attempt is rejected."""
        ai_response = json.dumps({
            "subparent_code": "ALTER TABLE users ADD admin BOOLEAN",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is False

    def test_exec_sql_fragment_rejected(self, ai_service):
        """EXEC SQL injection attempt is rejected."""
        ai_response = json.dumps({
            "parent_code": "EXEC sp_executesql @sql",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is False

    def test_multiple_semicolons_rejected(self, ai_service):
        """Multiple semicolons (multi-statement injection) rejected."""
        ai_response = json.dumps({
            "level": "account; DROP TABLE x; --",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is False

    def test_safe_values_pass_validation(self, ai_service):
        """Normal parameter values pass the safety checks."""
        ai_response = json.dumps({
            "year": 2025,
            "level": "parent",
            "period": "ytd",
            "parent_code": "4000",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "Show parent YTD", 2025,
                [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is True
        params = result['data']['interpreted_params']
        assert params['year'] == 2025
        assert params['level'] == 'parent'
        assert params['period'] == 'ytd'
        assert params['parent_code'] == '4000'

    def test_only_allowed_keys_in_output(self, ai_service):
        """Even if AI returns extra keys, only allowed ones appear in result."""
        ai_response = json.dumps({
            "level": "account",
            "period": "q1",
            "admin_override": "true",
            "sql_injection": "nope",
            "table_name": "budget_lines",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "Q1 accounts", 2025,
                [{'code': '4000', 'name': 'Omzet'}], "tenant-1"
            )

        assert result['success'] is True
        params = result['data']['interpreted_params']
        allowed = {'year', 'level', 'period', 'parent_code', 'subparent_code', 'reference_number'}
        assert set(params.keys()).issubset(allowed)
        assert 'admin_override' not in params
        assert 'sql_injection' not in params
        assert 'table_name' not in params
