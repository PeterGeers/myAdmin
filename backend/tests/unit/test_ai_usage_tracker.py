"""
Unit tests for AIUsageTracker

Tests AI usage logging, cost calculation, and usage summary retrieval.

This is a unit test suite - all external dependencies are mocked.
No database connections, no file system operations, no external API calls.
"""

import pytest
import os
import sys
from unittest.mock import Mock, MagicMock
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.ai_usage_tracker import AIUsageTracker


@pytest.mark.unit
class TestAIUsageTracker:
    """Test suite for AIUsageTracker"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database manager"""
        db = Mock()
        db.execute_query = Mock()
        return db
    
    @pytest.fixture
    def tracker(self, mock_db):
        """Create an AIUsageTracker instance with mocked dependencies"""
        return AIUsageTracker(mock_db)
    
    # ========================================================================
    # Initialization Tests
    # ========================================================================
    
    def test_initialization(self, mock_db):
        """Test tracker initializes correctly"""
        tracker = AIUsageTracker(mock_db)
        assert tracker.db == mock_db
    
    def test_model_pricing_defined(self, tracker):
        """Test model pricing dictionary is properly defined"""
        assert 'google/gemini-flash-1.5' in tracker.MODEL_PRICING
        assert 'meta-llama/llama-3.2-3b-instruct:free' in tracker.MODEL_PRICING
        assert 'deepseek/deepseek-chat' in tracker.MODEL_PRICING
        assert 'anthropic/claude-3.5-sonnet' in tracker.MODEL_PRICING
        assert 'default' in tracker.MODEL_PRICING
    
    def test_free_models_have_zero_cost(self, tracker):
        """Test free models have zero pricing"""
        assert tracker.MODEL_PRICING['google/gemini-flash-1.5'] == 0.0
        assert tracker.MODEL_PRICING['meta-llama/llama-3.2-3b-instruct:free'] == 0.0
    
    # ========================================================================
    # Cost Calculation Tests
    # ========================================================================
    
    def test_calculate_cost_free_model(self, tracker):
        """Test cost calculation for free models"""
        cost = tracker._calculate_cost(1000, 'google/gemini-flash-1.5')
        assert cost == Decimal('0.000000')
    
    def test_calculate_cost_paid_model(self, tracker):
        """Test cost calculation for paid models"""
        # deepseek: $0.685 per 1M tokens
        cost = tracker._calculate_cost(1_000_000, 'deepseek/deepseek-chat')
        assert cost == Decimal('0.685000')
    
    def test_calculate_cost_small_token_count(self, tracker):
        """Test cost calculation for small token counts"""
        # 1000 tokens with deepseek ($0.685/1M)
        cost = tracker._calculate_cost(1000, 'deepseek/deepseek-chat')
        expected = Decimal('0.000685')
        assert cost == expected
    
    def test_calculate_cost_unknown_model_uses_default(self, tracker):
        """Test cost calculation falls back to default for unknown models"""
        cost = tracker._calculate_cost(1_000_000, 'unknown/model')
        assert cost == Decimal('0.500000')  # default pricing
    
    def test_calculate_cost_no_model_uses_default(self, tracker):
        """Test cost calculation uses default when no model specified"""
        cost = tracker._calculate_cost(1_000_000, None)
        assert cost == Decimal('0.500000')
    
    def test_calculate_cost_zero_tokens(self, tracker):
        """Test cost calculation with zero tokens"""
        cost = tracker._calculate_cost(0, 'deepseek/deepseek-chat')
        assert cost == Decimal('0.000000')
    
    def test_calculate_cost_precision(self, tracker):
        """Test cost calculation maintains 6 decimal places"""
        cost = tracker._calculate_cost(123, 'deepseek/deepseek-chat')
        # Should have exactly 6 decimal places
        assert str(cost).count('.') == 1
        decimal_part = str(cost).split('.')[1]
        assert len(decimal_part) == 6
    
    # ========================================================================
    # Log AI Request Tests
    # ========================================================================
    
    def test_log_ai_request_success(self, tracker, mock_db):
        """Test successful logging of AI request"""
        mock_db.execute_query.return_value = None
        
        result = tracker.log_ai_request(
            administration='TestTenant',
            template_type='str_invoice_nl',
            tokens_used=1500,
            model_used='google/gemini-flash-1.5'
        )
        
        assert result is True
        mock_db.execute_query.assert_called_once()
        
        # Verify query parameters
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        
        assert 'INSERT INTO ai_usage_log' in query
        assert params[0] == 'TestTenant'
        assert params[1] == 'template_help_str_invoice_nl'
        assert params[2] == 1500
        assert params[3] == Decimal('0.000000')  # Free model
    
    def test_log_ai_request_with_paid_model(self, tracker, mock_db):
        """Test logging with paid model calculates correct cost"""
        mock_db.execute_query.return_value = None
        
        result = tracker.log_ai_request(
            administration='TestTenant',
            template_type='btw_aangifte',
            tokens_used=2000,
            model_used='deepseek/deepseek-chat'
        )
        
        assert result is True
        
        # Verify cost calculation
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        expected_cost = Decimal('0.001370')  # 2000 * 0.685 / 1M
        assert params[3] == expected_cost
    
    def test_log_ai_request_without_model(self, tracker, mock_db):
        """Test logging without model uses default pricing"""
        mock_db.execute_query.return_value = None
        
        result = tracker.log_ai_request(
            administration='TestTenant',
            template_type='aangifte_ib',
            tokens_used=1000
        )
        
        assert result is True
        
        # Verify default cost calculation
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        expected_cost = Decimal('0.000500')  # 1000 * 0.5 / 1M
        assert params[3] == expected_cost
    
    def test_log_ai_request_builds_correct_feature_name(self, tracker, mock_db):
        """Test feature name is correctly formatted"""
        mock_db.execute_query.return_value = None
        
        tracker.log_ai_request(
            administration='TestTenant',
            template_type='toeristenbelasting',
            tokens_used=500
        )
        
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        assert params[1] == 'template_help_toeristenbelasting'
    
    def test_log_ai_request_database_error_returns_false(self, tracker, mock_db):
        """Test logging returns False on database error"""
        mock_db.execute_query.side_effect = Exception("Database error")
        
        result = tracker.log_ai_request(
            administration='TestTenant',
            template_type='str_invoice_nl',
            tokens_used=1000
        )
        
        assert result is False
    
    def test_log_ai_request_uses_commit_flag(self, tracker, mock_db):
        """Test logging uses commit=True flag"""
        mock_db.execute_query.return_value = None
        
        tracker.log_ai_request(
            administration='TestTenant',
            template_type='str_invoice_nl',
            tokens_used=1000
        )
        
        call_args = mock_db.execute_query.call_args
        kwargs = call_args[1]
        assert kwargs.get('commit') is True
        assert kwargs.get('fetch') is False
    
    # ========================================================================
    # Get Usage Summary Tests
    # ========================================================================
    
    def test_get_usage_summary_with_data(self, tracker, mock_db):
        """Test usage summary retrieval with data"""
        # Mock aggregated data
        mock_db.execute_query.side_effect = [
            # First call: aggregated totals
            [{
                'total_requests': 10,
                'total_tokens': 15000,
                'total_cost': Decimal('0.010275')
            }],
            # Second call: breakdown by feature
            [
                {
                    'feature': 'template_help_str_invoice_nl',
                    'requests': 6,
                    'tokens': 9000,
                    'cost': Decimal('0.006165')
                },
                {
                    'feature': 'template_help_btw_aangifte',
                    'requests': 4,
                    'tokens': 6000,
                    'cost': Decimal('0.004110')
                }
            ]
        ]
        
        summary = tracker.get_usage_summary('TestTenant', days=30)
        
        assert summary['total_requests'] == 10
        assert summary['total_tokens'] == 15000
        assert summary['total_cost'] == Decimal('0.010275')
        assert len(summary['by_feature']) == 2
        assert 'template_help_str_invoice_nl' in summary['by_feature']
        assert summary['by_feature']['template_help_str_invoice_nl']['requests'] == 6
    
    def test_get_usage_summary_no_data(self, tracker, mock_db):
        """Test usage summary with no data returns zeros"""
        mock_db.execute_query.return_value = []
        
        summary = tracker.get_usage_summary('TestTenant', days=30)
        
        assert summary['total_requests'] == 0
        assert summary['total_tokens'] == 0
        assert summary['total_cost'] == Decimal('0.000000')
        assert summary['by_feature'] == {}
    
    def test_get_usage_summary_custom_days(self, tracker, mock_db):
        """Test usage summary with custom day range"""
        mock_db.execute_query.side_effect = [
            [{'total_requests': 5, 'total_tokens': 7500, 'total_cost': Decimal('0.005138')}],
            []
        ]
        
        summary = tracker.get_usage_summary('TestTenant', days=7)
        
        # Verify the days parameter was passed correctly
        call_args = mock_db.execute_query.call_args_list[0]
        params = call_args[0][1]
        assert params[1] == 7
    
    def test_get_usage_summary_handles_null_values(self, tracker, mock_db):
        """Test usage summary handles NULL values from database"""
        mock_db.execute_query.side_effect = [
            [{'total_requests': None, 'total_tokens': None, 'total_cost': None}],
            []
        ]
        
        summary = tracker.get_usage_summary('TestTenant', days=30)
        
        assert summary['total_requests'] == 0
        assert summary['total_tokens'] == 0
        assert summary['total_cost'] == Decimal('0.000000')
    
    def test_get_usage_summary_database_error_returns_empty(self, tracker, mock_db):
        """Test usage summary returns empty dict on database error"""
        mock_db.execute_query.side_effect = Exception("Database error")
        
        summary = tracker.get_usage_summary('TestTenant', days=30)
        
        assert summary['total_requests'] == 0
        assert summary['total_tokens'] == 0
        assert summary['total_cost'] == Decimal('0.000000')
        assert summary['by_feature'] == {}
    
    def test_get_usage_summary_feature_breakdown_structure(self, tracker, mock_db):
        """Test feature breakdown has correct structure"""
        mock_db.execute_query.side_effect = [
            [{'total_requests': 5, 'total_tokens': 5000, 'total_cost': Decimal('0.003425')}],
            [{
                'feature': 'template_help_str_invoice_nl',
                'requests': 5,
                'tokens': 5000,
                'cost': Decimal('0.003425')
            }]
        ]
        
        summary = tracker.get_usage_summary('TestTenant', days=30)
        
        feature_data = summary['by_feature']['template_help_str_invoice_nl']
        assert 'requests' in feature_data
        assert 'tokens' in feature_data
        assert 'cost' in feature_data
        assert feature_data['requests'] == 5
        assert feature_data['tokens'] == 5000
        assert feature_data['cost'] == Decimal('0.003425')
    
    # ========================================================================
    # Edge Cases and Error Handling
    # ========================================================================
    
    def test_log_ai_request_with_zero_tokens(self, tracker, mock_db):
        """Test logging with zero tokens"""
        mock_db.execute_query.return_value = None
        
        result = tracker.log_ai_request(
            administration='TestTenant',
            template_type='str_invoice_nl',
            tokens_used=0
        )
        
        assert result is True
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        assert params[2] == 0
        assert params[3] == Decimal('0.000000')
    
    def test_log_ai_request_with_large_token_count(self, tracker, mock_db):
        """Test logging with very large token count"""
        mock_db.execute_query.return_value = None
        
        result = tracker.log_ai_request(
            administration='TestTenant',
            template_type='str_invoice_nl',
            tokens_used=10_000_000,  # 10M tokens
            model_used='deepseek/deepseek-chat'
        )
        
        assert result is True
        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        expected_cost = Decimal('6.850000')  # 10M * 0.685 / 1M
        assert params[3] == expected_cost
    
    def test_calculate_cost_handles_invalid_input(self, tracker):
        """Test cost calculation handles invalid input gracefully"""
        # Should not raise exception, should return 0
        cost = tracker._calculate_cost(None, 'deepseek/deepseek-chat')
        assert cost == Decimal('0.000000')
    
    def test_get_usage_summary_default_days(self, tracker, mock_db):
        """Test usage summary uses default 30 days"""
        mock_db.execute_query.side_effect = [
            [{'total_requests': 1, 'total_tokens': 1000, 'total_cost': Decimal('0.000685')}],
            []
        ]
        
        # Call without specifying days
        summary = tracker.get_usage_summary('TestTenant')
        
        # Verify default 30 days was used
        call_args = mock_db.execute_query.call_args_list[0]
        params = call_args[0][1]
        assert params[1] == 30


# ========================================================================
# Integration Test Markers (for future integration tests)
# ========================================================================

@pytest.mark.integration
class TestAIUsageTrackerIntegration:
    """
    Integration tests for AIUsageTracker (requires real database).
    
    These tests are marked as integration and should be run separately
    from unit tests. They require a test database to be available.
    """
    
    @pytest.mark.skip(reason="Integration test - requires real database")
    def test_log_and_retrieve_usage(self):
        """Test logging and retrieving usage with real database"""
        # This would test with a real database connection
        pass
    
    @pytest.mark.skip(reason="Integration test - requires real database")
    def test_concurrent_logging(self):
        """Test concurrent logging from multiple requests"""
        # This would test thread safety with real database
        pass
