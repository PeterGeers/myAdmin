"""
Unit tests for BudgetAIService.translate_query method.

Tests parameter validation, SQL injection rejection, and graceful error handling
for the natural language query translation feature.

Feature: fin-budget
Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# Mock external dependencies before importing
with patch('services.ai_model_registry.resolver'), \
     patch('services.ai_usage_tracker.AIUsageTracker'):
    from services.budget_ai_service import BudgetAIService


@pytest.fixture
def ai_service():
    """Create BudgetAIService instance without database."""
    with patch('services.ai_model_registry.resolver'), \
         patch('services.ai_usage_tracker.AIUsageTracker'):
        service = BudgetAIService(db=None)
    return service


@pytest.fixture
def hierarchy_context():
    """Sample account hierarchy context."""
    return [
        {'code': '4000', 'name': 'Omzet'},
        {'code': '4100', 'name': 'Omzet Airbnb'},
        {'code': '5000', 'name': 'Kosten'},
        {'code': '5100', 'name': 'Huur'},
        {'code': '5200', 'name': 'Onderhoud'},
    ]


class TestTranslateQuerySuccess:
    """Test successful query translation scenarios."""

    def test_valid_json_parameters_returned(self, ai_service, hierarchy_context):
        """Valid AI response is parsed and returned as interpreted_params."""
        ai_response = json.dumps({
            "level": "account",
            "period": "q2",
            "year": 2025
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'google/gemini-flash-1.5',
            'tokens_used': 150,
        }):
            result = ai_service.translate_query(
                "Welke rekeningen zijn over budget dit kwartaal?",
                2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is True
        assert result['data']['interpreted_params'] == {
            'level': 'account',
            'period': 'q2',
            'year': 2025,
        }
        assert result['data']['model_used'] == 'google/gemini-flash-1.5'
        assert result['data']['tokens_used'] == 150
        assert 'filter_description' in result['data']

    def test_extracts_json_from_markdown_code_block(self, ai_service, hierarchy_context):
        """AI response wrapped in markdown code block is correctly extracted."""
        ai_response = '```json\n{"level": "parent", "period": "ytd"}\n```'

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "Show parent level YTD", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is True
        assert result['data']['interpreted_params'] == {
            'level': 'parent',
            'period': 'ytd',
        }

    def test_unknown_keys_filtered_out(self, ai_service, hierarchy_context):
        """Only allowed schema keys are included in validated params."""
        ai_response = json.dumps({
            "level": "account",
            "period": "q1",
            "unknown_key": "should be removed",
            "another_bad_key": 123,
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "Q1 account view", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is True
        params = result['data']['interpreted_params']
        assert 'unknown_key' not in params
        assert 'another_bad_key' not in params
        assert params == {'level': 'account', 'period': 'q1'}

    def test_all_allowed_keys_accepted(self, ai_service, hierarchy_context):
        """All allowed schema keys pass validation when values are safe."""
        ai_response = json.dumps({
            "year": 2025,
            "level": "subparent",
            "period": "month-6",
            "parent_code": "4000",
            "subparent_code": "4100",
            "reference_number": "REF001",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 200,
        }):
            result = ai_service.translate_query(
                "Filter on REF001", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is True
        params = result['data']['interpreted_params']
        assert params == {
            'year': 2025,
            'level': 'subparent',
            'period': 'month-6',
            'parent_code': '4000',
            'subparent_code': '4100',
            'reference_number': 'REF001',
        }


class TestTranslateQuerySecurity:
    """Test SQL injection and safety validation."""

    def test_rejects_semicolons_in_values(self, ai_service, hierarchy_context):
        """Parameters with semicolons are rejected as unsafe."""
        ai_response = json.dumps({
            "level": "account; DROP TABLE budget_lines",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False
        assert "rephras" in result['error'].lower()

    def test_rejects_select_sql_fragment(self, ai_service, hierarchy_context):
        """Parameters with SELECT SQL fragments are rejected."""
        ai_response = json.dumps({
            "parent_code": "SELECT * FROM users",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False
        assert "safely" in result['error'].lower()

    def test_rejects_drop_sql_fragment(self, ai_service, hierarchy_context):
        """Parameters with DROP SQL fragments are rejected."""
        ai_response = json.dumps({
            "reference_number": "DROP TABLE budget_versions",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False
        assert "safely" in result['error'].lower()

    def test_rejects_insert_sql_fragment(self, ai_service, hierarchy_context):
        """Parameters with INSERT SQL fragments are rejected."""
        ai_response = json.dumps({
            "parent_code": "INSERT INTO admin VALUES(1)",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False

    def test_rejects_values_over_100_chars(self, ai_service, hierarchy_context):
        """Parameters with values longer than 100 characters are rejected."""
        long_value = "A" * 101
        ai_response = json.dumps({
            "reference_number": long_value,
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False
        assert "safely" in result['error'].lower()

    def test_accepts_value_exactly_100_chars(self, ai_service, hierarchy_context):
        """Parameters with values exactly 100 characters are accepted."""
        exact_value = "A" * 100
        ai_response = json.dumps({
            "reference_number": exact_value,
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is True
        assert result['data']['interpreted_params']['reference_number'] == exact_value

    def test_sql_check_is_case_insensitive(self, ai_service, hierarchy_context):
        """SQL fragment detection works regardless of case."""
        ai_response = json.dumps({
            "parent_code": "select something",
        })

        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': ai_response,
            'model_used': 'test-model',
            'tokens_used': 100,
        }):
            result = ai_service.translate_query(
                "test", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False


class TestTranslateQueryErrorHandling:
    """Test error handling scenarios."""

    def test_ai_service_failure_propagated(self, ai_service, hierarchy_context):
        """When AI service fails, error is propagated to caller."""
        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': False,
            'error': 'AI service unavailable: all models failed',
        }):
            result = ai_service.translate_query(
                "test question", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False
        assert "AI service unavailable" in result['error']

    def test_invalid_json_response_returns_rephrase_suggestion(self, ai_service, hierarchy_context):
        """When AI returns non-JSON, user gets a rephrase suggestion."""
        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': "I'm sorry, I don't understand that question.",
            'model_used': 'test-model',
            'tokens_used': 50,
        }):
            result = ai_service.translate_query(
                "gibberish question", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is False
        assert "rephras" in result['error'].lower()

    def test_empty_json_response_returns_empty_params(self, ai_service, hierarchy_context):
        """When AI returns empty JSON object, result has empty params."""
        with patch.object(ai_service, '_call_openrouter', return_value={
            'success': True,
            'content': '{}',
            'model_used': 'test-model',
            'tokens_used': 50,
        }):
            result = ai_service.translate_query(
                "vague question", 2025, hierarchy_context, "tenant-1"
            )

        assert result['success'] is True
        assert result['data']['interpreted_params'] == {}


class TestTranslateQueryHierarchyContext:
    """Test that hierarchy context is properly included."""

    def test_hierarchy_limited_to_100_entries(self, ai_service):
        """Hierarchy context is capped at 100 entries to control token usage."""
        large_hierarchy = [
            {'code': f'{i:04d}', 'name': f'Account {i}'}
            for i in range(150)
        ]

        call_args = {}

        def mock_call(system_prompt, user_prompt, administration, max_tokens_override=None):
            call_args['user_prompt'] = user_prompt
            return {
                'success': True,
                'content': '{"level": "parent"}',
                'model_used': 'test-model',
                'tokens_used': 100,
            }

        with patch.object(ai_service, '_call_openrouter', side_effect=mock_call):
            ai_service.translate_query(
                "test", 2025, large_hierarchy, "tenant-1"
            )

        # Should only include 100 entries (0000..0099), not 0100..0149
        assert '0099' in call_args['user_prompt']
        assert '0100' not in call_args['user_prompt']

    def test_hierarchy_names_included_in_prompt(self, ai_service, hierarchy_context):
        """Account names from hierarchy are included in the AI prompt."""
        call_args = {}

        def mock_call(system_prompt, user_prompt, administration, max_tokens_override=None):
            call_args['user_prompt'] = user_prompt
            call_args['system_prompt'] = system_prompt
            return {
                'success': True,
                'content': '{"level": "parent"}',
                'model_used': 'test-model',
                'tokens_used': 100,
            }

        with patch.object(ai_service, '_call_openrouter', side_effect=mock_call):
            ai_service.translate_query(
                "Toon omzet Airbnb", 2025, hierarchy_context, "tenant-1"
            )

        # Verify hierarchy names are in the prompt
        assert 'Omzet' in call_args['user_prompt']
        assert 'Omzet Airbnb' in call_args['user_prompt']
        assert '4000' in call_args['user_prompt']

    def test_fiscal_year_included_in_prompt(self, ai_service, hierarchy_context):
        """The fiscal year is passed as context in the AI prompt."""
        call_args = {}

        def mock_call(system_prompt, user_prompt, administration, max_tokens_override=None):
            call_args['user_prompt'] = user_prompt
            return {
                'success': True,
                'content': '{"year": 2024}',
                'model_used': 'test-model',
                'tokens_used': 100,
            }

        with patch.object(ai_service, '_call_openrouter', side_effect=mock_call):
            ai_service.translate_query(
                "Vorig jaar", 2024, hierarchy_context, "tenant-1"
            )

        assert '2024' in call_args['user_prompt']
