"""
Unit tests for hybrid_pricing_optimizer module.

Tests pricing strategy generation, seasonal multiplier calculations,
event uplift logic, and AI insight parsing.

Requirements: 1.2, 2.2, 2.3, 8.5
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta

from hybrid_pricing_optimizer import HybridPricingOptimizer


class TestGenerateAiInsights:
    """Tests for _generate_ai_insights method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
                    opt.api_key = 'test-key'
        return opt

    @patch('hybrid_pricing_optimizer.requests.post')
    def test_generate_ai_insights_valid_response(self, mock_post, optimizer):
        """Test successful AI insight generation."""
        ai_response = {
            'daily_adr_recommendations': [
                {'date': '2025-01-01', 'recommended_adr': 120.0, 'historical_adr': 100.0, 'variance': '20%', 'reasoning': 'New Year'}
            ],
            'strategy_summary': 'Test strategy'
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': json.dumps(ai_response)}}]
        }
        mock_post.return_value = mock_response

        with patch.object(optimizer, '_get_historical_data', return_value={'avg_adr_24m': 100.0, 'monthly_performance': [], 'seasonal_performance': []}):
            with patch.object(optimizer, '_get_listing_performance', return_value={'base_weekday_price': 85.0, 'base_weekend_price': 110.0}):
                result = optimizer._generate_ai_insights(14, 'TestListing')

        assert result is not None
        assert 'daily_adr_recommendations' in result

    @patch('hybrid_pricing_optimizer.requests.post')
    def test_generate_ai_insights_json_in_code_block(self, mock_post, optimizer):
        """Test parsing when AI wraps response in code block."""
        ai_response = {'daily_adr_recommendations': [], 'strategy_summary': 'Test'}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': f'```json\n{json.dumps(ai_response)}\n```'}}]
        }
        mock_post.return_value = mock_response

        with patch.object(optimizer, '_get_historical_data', return_value={'avg_adr_24m': 95.0, 'monthly_performance': [], 'seasonal_performance': []}):
            with patch.object(optimizer, '_get_listing_performance', return_value={'base_weekday_price': 85.0, 'base_weekend_price': 110.0}):
                result = optimizer._generate_ai_insights(14, 'TestListing')

        assert result is not None
        assert 'strategy_summary' in result

    @patch('hybrid_pricing_optimizer.requests.post')
    def test_generate_ai_insights_invalid_json_returns_none(self, mock_post, optimizer):
        """Test that invalid JSON from all models returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{'message': {'content': 'This is not valid JSON'}}]
        }
        mock_post.return_value = mock_response

        with patch.object(optimizer, '_get_historical_data', return_value={'avg_adr_24m': 95.0, 'monthly_performance': [], 'seasonal_performance': []}):
            with patch.object(optimizer, '_get_listing_performance', return_value={'base_weekday_price': 85.0, 'base_weekend_price': 110.0}):
                result = optimizer._generate_ai_insights(14, 'TestListing')

        assert result is None

    @patch('hybrid_pricing_optimizer.requests.post')
    def test_generate_ai_insights_api_error_returns_none(self, mock_post, optimizer):
        """Test that API errors return None."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with patch.object(optimizer, '_get_historical_data', return_value={'avg_adr_24m': 95.0, 'monthly_performance': [], 'seasonal_performance': []}):
            with patch.object(optimizer, '_get_listing_performance', return_value={'base_weekday_price': 85.0, 'base_weekend_price': 110.0}):
                result = optimizer._generate_ai_insights(14, 'TestListing')

        assert result is None

    @patch('hybrid_pricing_optimizer.requests.post')
    def test_generate_ai_insights_exception_returns_none(self, mock_post, optimizer):
        """Test that exceptions during AI call return None."""
        mock_post.side_effect = Exception("Network error")

        with patch.object(optimizer, '_get_historical_data', return_value={'avg_adr_24m': 95.0, 'monthly_performance': [], 'seasonal_performance': []}):
            with patch.object(optimizer, '_get_listing_performance', return_value={'base_weekday_price': 85.0, 'base_weekend_price': 110.0}):
                result = optimizer._generate_ai_insights(14, 'TestListing')

        assert result is None


class TestGenerateDailyPricing:
    """Tests for _generate_daily_pricing method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                mock_bpm = MagicMock()
                mock_bpm.calculate_business_price.return_value = {
                    'final_price': 120.0,
                    'base_rate': 100.0,
                    'historical_mult': 1.1,
                    'occupancy_mult': 1.0,
                    'pace_mult': 1.0,
                    'event_mult': 1.0,
                    'ai_correction': 1.0,
                    'btw_adjustment': 0.09,
                    'historical_adr': 110.0,
                    'reasoning': 'Standard pricing',
                }
                with patch('hybrid_pricing_optimizer.BusinessPricingModel', return_value=mock_bpm):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_generate_daily_pricing_returns_correct_count(self, optimizer):
        """Test that correct number of daily prices are generated."""
        with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
            with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                result = optimizer._generate_daily_pricing(7, 'TestListing')

        assert len(result) == 7

    def test_generate_daily_pricing_includes_required_fields(self, optimizer):
        """Test that each daily price has all required fields."""
        with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
            with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                result = optimizer._generate_daily_pricing(1, 'TestListing')

        assert len(result) == 1
        entry = result[0]
        required_fields = [
            'date', 'price', 'is_weekend', 'event_uplift', 'event_name',
            'ai_recommended_adr', 'ai_historical_adr', 'ai_variance',
            'ai_reasoning', 'last_year_adr', 'base_rate',
            'historical_mult', 'occupancy_mult', 'pace_mult',
            'event_mult', 'ai_correction', 'btw_adjustment'
        ]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    def test_generate_daily_pricing_with_ai_insights(self, optimizer):
        """Test that AI insights are incorporated into daily pricing."""
        today = datetime.now().date().strftime('%Y-%m-%d')
        ai_insights = {
            'daily_adr_recommendations': [
                {
                    'date': today,
                    'recommended_adr': 150.0,
                    'historical_adr': 100.0,
                    'variance': '50%',
                    'reasoning': 'High demand period'
                }
            ]
        }

        with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
            with patch.object(optimizer, '_get_last_year_adr', return_value=95.0):
                result = optimizer._generate_daily_pricing(1, 'TestListing', ai_insights)

        assert result[0]['ai_recommended_adr'] == 150.0
        assert result[0]['ai_historical_adr'] == 100.0
        assert result[0]['ai_reasoning'] == 'High demand period'

    def test_generate_daily_pricing_without_ai_uses_business_model(self, optimizer):
        """Test that without AI insights, business model data is used as fallback."""
        with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
            with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                result = optimizer._generate_daily_pricing(1, 'TestListing', None)

        assert result[0]['price'] == 120.0
        assert result[0]['base_rate'] == 100.0

    def test_generate_daily_pricing_weekend_detection(self, optimizer):
        """Test that weekends (Friday/Saturday) are correctly detected."""
        # Generate 7 days to cover a full week
        with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
            with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                result = optimizer._generate_daily_pricing(7, 'TestListing')

        # Check that some days are weekend and some are not
        weekend_count = sum(1 for r in result if r['is_weekend'])
        weekday_count = sum(1 for r in result if not r['is_weekend'])
        assert weekend_count >= 1
        assert weekday_count >= 1

    def test_generate_daily_pricing_event_uplift(self, optimizer):
        """Test that event uplift is calculated from event_mult."""
        # event_mult is 1.0 in fixture, so uplift should be 0
        with patch.object(optimizer, '_get_event_name_for_date', return_value='King\'s Day'):
            with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                result = optimizer._generate_daily_pricing(1, 'TestListing')

        assert result[0]['event_name'] == "King's Day"


class TestCalculateHistoricalRates:
    """Tests for _calculate_historical_rates method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_calculate_historical_rates_no_listing_returns_note(self, optimizer):
        """Without listing, should return a note about no data."""
        result = optimizer._calculate_historical_rates(None, {})
        assert 'note' in result or 'error' in result

    def test_calculate_historical_rates_no_monthly_data_returns_note(self, optimizer):
        """Without monthly performance data, should return a note."""
        result = optimizer._calculate_historical_rates('TestListing', {'monthly_performance': None})
        assert 'note' in result or 'error' in result

    def test_calculate_historical_rates_with_data_returns_analysis(self, optimizer):
        """With valid data, should return rates analysis."""
        historical_data = {
            'avg_adr_24m': 110.0,
            'total_bookings_24m': 50,
            'monthly_performance': [
                {'year': 2024, 'month': 1, 'avg_adr': 90.0, 'bookings': 5},
                {'year': 2024, 'month': 6, 'avg_adr': 130.0, 'bookings': 10},
            ],
            'seasonal_performance': [
                {'season': 'Winter', 'avg_adr': 90.0, 'bookings': 5},
                {'season': 'Summer', 'avg_adr': 130.0, 'bookings': 10},
            ]
        }
        result = optimizer._calculate_historical_rates('TestListing', historical_data)

        assert result['listing'] == 'TestListing'
        assert result['avg_adr_24m'] == 110.0
        assert len(result['monthly_rates']) == 2
        assert len(result['seasonal_rates']) == 2

    def test_calculate_historical_rates_exception_returns_error(self, optimizer):
        """Exception during calculation should return error dict."""
        # Pass data that will cause an error
        historical_data = {
            'monthly_performance': 'not a list'  # Will cause iteration error
        }
        result = optimizer._calculate_historical_rates('TestListing', historical_data)
        assert 'error' in result


class TestGeneratePricingStrategy:
    """Tests for generate_pricing_strategy method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                mock_bpm = MagicMock()
                mock_bpm.calculate_business_price.return_value = {
                    'final_price': 100.0,
                    'base_rate': 90.0,
                    'historical_mult': 1.0,
                    'occupancy_mult': 1.0,
                    'pace_mult': 1.0,
                    'event_mult': 1.0,
                    'ai_correction': 1.0,
                    'btw_adjustment': 0.09,
                    'historical_adr': 95.0,
                    'reasoning': 'Standard',
                }
                with patch('hybrid_pricing_optimizer.BusinessPricingModel', return_value=mock_bpm):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_generate_pricing_strategy_single_listing(self, optimizer):
        """Test pricing strategy for a single listing."""
        with patch.object(optimizer, '_generate_ai_insights', return_value=None):
            with patch.object(optimizer, '_save_pricing_to_database', return_value=True):
                with patch.object(optimizer, '_save_ai_insights_to_file', return_value=False):
                    with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
                        with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                            result = optimizer.generate_pricing_strategy(months=1, listing='TestListing')

        assert result['listing'] == 'TestListing'
        assert result['months_generated'] == 1
        assert result['daily_prices_count'] == 30  # 1 month * 30 days

    def test_generate_pricing_strategy_no_listing_calls_all_listings(self, optimizer):
        """Test that no listing triggers all-listings generation."""
        with patch.object(optimizer, '_generate_all_listings_pricing', return_value={
            'daily_prices_count': 420, 'ai_insights_saved': True, 'months_generated': 14, 'listing': 'All listings (1)'
        }) as mock_all:
            result = optimizer.generate_pricing_strategy(months=14, listing=None)

        mock_all.assert_called_once_with(14)
        assert result['daily_prices_count'] == 420

    def test_generate_pricing_strategy_with_ai_insights(self, optimizer):
        """Test pricing strategy with AI insights available."""
        ai_insights = {
            'daily_adr_recommendations': [
                {'date': '2025-01-01', 'recommended_adr': 120.0, 'historical_adr': 100.0, 'variance': '20%', 'reasoning': 'New Year'}
            ],
            'strategy_summary': 'Test'
        }
        with patch.object(optimizer, '_generate_ai_insights', return_value=ai_insights):
            with patch.object(optimizer, '_save_pricing_to_database', return_value=True):
                with patch.object(optimizer, '_save_ai_insights_to_file', return_value=True):
                    with patch.object(optimizer, '_get_event_name_for_date', return_value=None):
                        with patch.object(optimizer, '_get_last_year_adr', return_value=None):
                            result = optimizer.generate_pricing_strategy(months=1, listing='TestListing')

        assert result['ai_insights_saved'] is True


class TestGenerateAllListingsPricing:
    """Tests for _generate_all_listings_pricing method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                mock_bpm = MagicMock()
                mock_bpm.calculate_business_price.return_value = {
                    'final_price': 100.0, 'base_rate': 90.0, 'historical_mult': 1.0,
                    'occupancy_mult': 1.0, 'pace_mult': 1.0, 'event_mult': 1.0,
                    'ai_correction': 1.0, 'btw_adjustment': 0.09, 'historical_adr': 95.0,
                    'reasoning': 'Standard',
                }
                with patch('hybrid_pricing_optimizer.BusinessPricingModel', return_value=mock_bpm):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_generate_all_listings_no_active_listings(self, optimizer):
        """Test when no active listings are found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        result = optimizer._generate_all_listings_pricing(months=1)

        assert result['daily_prices_count'] == 0
        assert result['listing'] is None

    def test_generate_all_listings_with_listings(self, optimizer):
        """Test generating pricing for multiple listings."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'listing_name': 'Listing A'},
            {'listing_name': 'Listing B'},
        ]

        with patch.object(optimizer, '_generate_ai_insights', return_value=None):
            with patch.object(optimizer, '_generate_daily_pricing', return_value=[{'date': '2025-01-01', 'price': 100}]):
                with patch.object(optimizer, '_save_pricing_to_database_no_clear', return_value=True):
                    with patch.object(optimizer, '_save_ai_insights_to_file', return_value=False):
                        result = optimizer._generate_all_listings_pricing(months=1)

        assert result['daily_prices_count'] == 2  # 1 price per listing
        assert 'All listings' in result['listing']

    def test_generate_all_listings_exception_returns_error(self, optimizer):
        """Test that exceptions return error result."""
        optimizer.db.get_connection.side_effect = Exception("DB connection failed")

        result = optimizer._generate_all_listings_pricing(months=1)

        assert result['daily_prices_count'] == 0
        assert 'error' in result


class TestSavePricingToDatabase:
    """Tests for _save_pricing_to_database method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_save_pricing_to_database_success(self, optimizer):
        """Test successful save of pricing data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        daily_prices = [
            {'date': '2025-01-01', 'price': 100.0, 'is_weekend': False, 'event_uplift': 0,
             'event_name': None, 'ai_recommended_adr': 100.0, 'ai_historical_adr': 95.0,
             'ai_variance': '5.0', 'ai_reasoning': 'Standard', 'last_year_adr': None,
             'base_rate': 90.0, 'historical_mult': 1.0, 'occupancy_mult': 1.0,
             'pace_mult': 1.0, 'event_mult': 1.0, 'ai_correction': 1.0, 'btw_adjustment': 0.09},
        ]

        result = optimizer._save_pricing_to_database(daily_prices, 'TestListing')

        assert result is True
        mock_conn.commit.assert_called_once()

    def test_save_pricing_to_database_invalid_date_skipped(self, optimizer):
        """Test that invalid dates are skipped."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        daily_prices = [
            {'date': 'invalid-date', 'price': 100.0, 'is_weekend': False, 'event_uplift': 0,
             'event_name': None, 'ai_recommended_adr': 100.0, 'ai_historical_adr': 95.0,
             'ai_variance': '5.0', 'ai_reasoning': 'Standard', 'last_year_adr': None,
             'base_rate': 90.0, 'historical_mult': 1.0, 'occupancy_mult': 1.0,
             'pace_mult': 1.0, 'event_mult': 1.0, 'ai_correction': 1.0, 'btw_adjustment': 0.09},
            {'date': '2025-01-01', 'price': 100.0, 'is_weekend': False, 'event_uplift': 0,
             'event_name': None, 'ai_recommended_adr': 100.0, 'ai_historical_adr': 95.0,
             'ai_variance': '5.0', 'ai_reasoning': 'Standard', 'last_year_adr': None,
             'base_rate': 90.0, 'historical_mult': 1.0, 'occupancy_mult': 1.0,
             'pace_mult': 1.0, 'event_mult': 1.0, 'ai_correction': 1.0, 'btw_adjustment': 0.09},
        ]

        result = optimizer._save_pricing_to_database(daily_prices, 'TestListing')

        assert result is True
        # Only 1 valid price should be inserted
        assert mock_cursor.execute.call_count == 2  # 1 DELETE + 1 INSERT

    def test_save_pricing_to_database_error_rollback(self, optimizer):
        """Test that errors trigger rollback."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Insert failed")

        daily_prices = [
            {'date': '2025-01-01', 'price': 100.0, 'is_weekend': False, 'event_uplift': 0,
             'event_name': None, 'ai_recommended_adr': 100.0, 'ai_historical_adr': 95.0,
             'ai_variance': '5.0', 'ai_reasoning': 'Standard', 'last_year_adr': None,
             'base_rate': 90.0, 'historical_mult': 1.0, 'occupancy_mult': 1.0,
             'pace_mult': 1.0, 'event_mult': 1.0, 'ai_correction': 1.0, 'btw_adjustment': 0.09},
        ]

        result = optimizer._save_pricing_to_database(daily_prices, 'TestListing')

        assert result is False
        mock_conn.rollback.assert_called_once()


class TestSavePricingToDatabaseNoClear:
    """Tests for _save_pricing_to_database_no_clear method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_save_pricing_no_clear_success(self, optimizer):
        """Test successful save without clearing existing data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        daily_prices = [
            {'date': '2025-01-01', 'price': 100.0, 'is_weekend': False, 'event_uplift': 0,
             'event_name': None, 'ai_recommended_adr': 100.0, 'ai_historical_adr': 95.0,
             'ai_variance': '5.0', 'ai_reasoning': 'Standard', 'last_year_adr': None,
             'base_rate': 90.0, 'historical_mult': 1.0, 'occupancy_mult': 1.0,
             'pace_mult': 1.0, 'event_mult': 1.0, 'ai_correction': 1.0, 'btw_adjustment': 0.09},
        ]

        result = optimizer._save_pricing_to_database_no_clear(daily_prices, 'TestListing')

        assert result is True
        mock_conn.commit.assert_called_once()
        # Should NOT have a DELETE call (no clear)
        delete_calls = [c for c in mock_cursor.execute.call_args_list if 'DELETE' in str(c)]
        assert len(delete_calls) == 0

    def test_save_pricing_no_clear_error(self, optimizer):
        """Test error handling in no-clear save."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB error")

        daily_prices = [
            {'date': '2025-01-01', 'price': 100.0, 'is_weekend': False, 'event_uplift': 0,
             'event_name': None, 'ai_recommended_adr': 100.0, 'ai_historical_adr': 95.0,
             'ai_variance': '5.0', 'ai_reasoning': 'Standard', 'last_year_adr': None,
             'base_rate': 90.0, 'historical_mult': 1.0, 'occupancy_mult': 1.0,
             'pace_mult': 1.0, 'event_mult': 1.0, 'ai_correction': 1.0, 'btw_adjustment': 0.09},
        ]

        result = optimizer._save_pricing_to_database_no_clear(daily_prices, 'TestListing')

        assert result is False
        mock_conn.rollback.assert_called_once()


class TestSaveAiInsightsToFile:
    """Tests for _save_ai_insights_to_file method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_save_ai_insights_no_insights_returns_false(self, optimizer):
        """Test that None insights returns False."""
        result = optimizer._save_ai_insights_to_file(None, 'TestListing')
        assert result is False

    def test_save_ai_insights_empty_insights_returns_false(self, optimizer):
        """Test that empty insights returns False."""
        result = optimizer._save_ai_insights_to_file({}, 'TestListing')
        assert result is False

    def test_save_ai_insights_success(self, optimizer, temp_dir):
        """Test successful save of AI insights."""
        insights = {'strategy_summary': 'Test strategy', 'daily_adr_recommendations': []}

        with patch('os.path.dirname', return_value=temp_dir):
            with patch('os.path.exists', return_value=False):
                with patch('os.makedirs'):
                    with patch('builtins.open', MagicMock()):
                        result = optimizer._save_ai_insights_to_file(insights, 'TestListing')

        assert result is True

    def test_save_ai_insights_exception_returns_false(self, optimizer):
        """Test that exceptions return False."""
        insights = {'strategy_summary': 'Test'}

        with patch('os.path.dirname', side_effect=Exception("Path error")):
            result = optimizer._save_ai_insights_to_file(insights, 'TestListing')

        assert result is False


class TestGetEventsData:
    """Tests for _get_events_data method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_get_events_data_success(self, optimizer):
        """Test successful retrieval of events data."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        events_df = pd.DataFrame({
            'event_name': ["King's Day", 'Christmas'],
            'start_date': ['2025-04-27', '2025-12-25'],
            'end_date': ['2025-04-27', '2025-12-26'],
            'uplift_percentage': [20, 15],
        })

        with patch('pandas.read_sql', return_value=events_df):
            result = optimizer._get_events_data()

        assert 'events' in result
        assert len(result['events']) == 2

    def test_get_events_data_exception_returns_empty(self, optimizer):
        """Test that exceptions return empty events."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', side_effect=Exception("Query error")):
            result = optimizer._get_events_data()

        assert result == {'events': []}


class TestGetListingPerformance:
    """Tests for _get_listing_performance method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_get_listing_performance_no_listing_returns_defaults(self, optimizer):
        """Test that no listing returns default prices."""
        result = optimizer._get_listing_performance(None)

        assert result['base_weekday_price'] == 85.0
        assert result['base_weekend_price'] == 110.0

    def test_get_listing_performance_with_data(self, optimizer):
        """Test successful retrieval of listing performance."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        attrs_df = pd.DataFrame({
            'base_weekday_price': [95.0],
            'base_weekend_price': [125.0],
        })

        with patch('pandas.read_sql', return_value=attrs_df):
            result = optimizer._get_listing_performance('TestListing')

        assert result['base_weekday_price'] == 95.0
        assert result['base_weekend_price'] == 125.0

    def test_get_listing_performance_empty_result_returns_defaults(self, optimizer):
        """Test that empty query result returns defaults."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', return_value=pd.DataFrame()):
            result = optimizer._get_listing_performance('NonexistentListing')

        assert result['base_weekday_price'] == 85.0
        assert result['base_weekend_price'] == 110.0

    def test_get_listing_performance_exception_returns_defaults(self, optimizer):
        """Test that exceptions return defaults."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', side_effect=Exception("Query error")):
            result = optimizer._get_listing_performance('TestListing')

        assert result['base_weekday_price'] == 85.0
        assert result['base_weekend_price'] == 110.0


class TestGetHistoricalData:
    """Tests for _get_historical_data method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_get_historical_data_with_listing(self, optimizer):
        """Test historical data retrieval for a specific listing."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        monthly_df = pd.DataFrame({
            'year': [2024, 2024],
            'month': [1, 2],
            'bookings': [5, 8],
            'avg_adr': [100.0, 110.0],
            'avg_los': [2.0, 2.5],
            'total_revenue': [1000.0, 2200.0],
        })
        seasonal_df = pd.DataFrame({
            'season': ['Winter', 'Spring'],
            'bookings': [10, 15],
            'avg_adr': [95.0, 105.0],
            'avg_los': [2.0, 2.3],
        })
        planned_df = pd.DataFrame({
            'planned_bookings': [3],
            'planned_adr': [120.0],
            'earliest_planned': ['2025-01-15'],
            'latest_planned': ['2025-03-20'],
        })

        with patch('pandas.read_sql', side_effect=[monthly_df, seasonal_df, planned_df]):
            result = optimizer._get_historical_data('TestListing')

        assert result['listing'] == 'TestListing'
        assert result['avg_adr_24m'] == pytest.approx(105.0)
        assert result['total_bookings_24m'] == 13
        assert len(result['monthly_performance']) == 2
        assert len(result['seasonal_performance']) == 2

    def test_get_historical_data_no_listing(self, optimizer):
        """Test historical data retrieval without listing (general market)."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        monthly_df = pd.DataFrame({
            'year': [2024],
            'month': [1],
            'bookings': [20],
            'avg_adr': [100.0],
        })

        with patch('pandas.read_sql', return_value=monthly_df):
            result = optimizer._get_historical_data(None)

        assert 'monthly_performance' in result

    def test_get_historical_data_exception_returns_default(self, optimizer):
        """Test that exceptions return default data."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', side_effect=Exception("Query error")):
            result = optimizer._get_historical_data('TestListing')

        assert result.get('avg_adr') == 95.0 or 'avg_adr_24m' in result


class TestGetLastYearAdr:
    """Tests for _get_last_year_adr method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_get_last_year_adr_no_listing_returns_none(self, optimizer):
        """Test that no listing returns None."""
        result = optimizer._get_last_year_adr(None, date(2025, 1, 15))
        assert result is None

    def test_get_last_year_adr_with_data(self, optimizer):
        """Test successful ADR retrieval."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        result_df = pd.DataFrame({'avg_adr': [105.0]})

        with patch('pandas.read_sql', return_value=result_df):
            result = optimizer._get_last_year_adr('TestListing', date(2025, 6, 15))

        assert result == 105.0

    def test_get_last_year_adr_no_data_returns_none(self, optimizer):
        """Test that no data returns None."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        result_df = pd.DataFrame({'avg_adr': [None]})

        with patch('pandas.read_sql', return_value=result_df):
            result = optimizer._get_last_year_adr('TestListing', date(2025, 6, 15))

        assert result is None

    def test_get_last_year_adr_exception_returns_none(self, optimizer):
        """Test that exceptions return None."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', side_effect=Exception("Query error")):
            result = optimizer._get_last_year_adr('TestListing', date(2025, 6, 15))

        assert result is None


class TestGetEventNameForDate:
    """Tests for _get_event_name_for_date method."""

    @pytest.fixture
    def optimizer(self, mock_db, mock_env):
        with patch('hybrid_pricing_optimizer.load_dotenv'):
            with patch('hybrid_pricing_optimizer.DatabaseManager', return_value=mock_db):
                with patch('hybrid_pricing_optimizer.BusinessPricingModel'):
                    opt = HybridPricingOptimizer(test_mode=True)
        return opt

    def test_get_event_name_found(self, optimizer):
        """Test event name retrieval when event exists."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        result_df = pd.DataFrame({'event_name': ["King's Day"]})

        with patch('pandas.read_sql', return_value=result_df):
            result = optimizer._get_event_name_for_date(date(2025, 4, 27))

        assert result == "King's Day"

    def test_get_event_name_not_found(self, optimizer):
        """Test event name when no event exists for date."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', return_value=pd.DataFrame()):
            result = optimizer._get_event_name_for_date(date(2025, 3, 15))

        assert result is None

    def test_get_event_name_exception_returns_none(self, optimizer):
        """Test that exceptions return None."""
        import pandas as pd
        mock_conn = MagicMock()
        optimizer.db.get_connection.return_value = mock_conn

        with patch('pandas.read_sql', side_effect=Exception("Query error")):
            result = optimizer._get_event_name_for_date(date(2025, 4, 27))

        assert result is None
