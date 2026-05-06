"""
Unit tests for business_pricing_model module.

Tests the 7-factor price calculation, each multiplier function in isolation,
base rate weekday/weekend logic, BTW adjustment, and fallback behavior.

Requirements: 1.1, 2.2, 2.1, 8.5
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime, date

from business_pricing_model import BusinessPricingModel


class TestBusinessPricingModel:
    """Tests for BusinessPricingModel class."""

    @pytest.fixture
    def mock_conn(self):
        """Provide a mock connection for methods using db.get_connection()."""
        return MagicMock()

    @pytest.fixture
    def pricing_model(self, mock_db):
        """Create BusinessPricingModel instance with mocked DatabaseManager."""
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    # -----------------------------------------------------------------------
    # calculate_business_price (end-to-end 7-factor)
    # -----------------------------------------------------------------------

    @patch('business_pricing_model.pd.read_sql')
    def test_calculate_business_price_all_factors_applied(self, mock_read_sql, pricing_model):
        """Test full 7-factor calculation with all multipliers active."""
        # Setup: listing found with base prices, historical data, high occupancy, growth, event
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # Sequence of pd.read_sql calls:
        # 1. _get_base_rate: listing found
        # 2. _get_historical_multiplier: historical ADR query
        # 3. _get_historical_multiplier: baseline ADR query
        # 4. _get_occupancy_multiplier: occupancy query
        # 5. _get_booking_pace_multiplier: check query
        # 6. _get_booking_pace_multiplier: monthly query
        # 7. _get_event_multiplier: event query
        mock_read_sql.side_effect = [
            # _get_base_rate: listing with weekday=100, weekend=130
            pd.DataFrame({'base_weekday_price': [100.0], 'base_weekend_price': [130.0]}),
            # _get_historical_multiplier: historical ADR = 120
            pd.DataFrame({'historical_adr': [120.0]}),
            # _get_historical_multiplier: baseline ADR = 100
            pd.DataFrame({'baseline_adr': [100.0]}),
            # _get_occupancy_multiplier: high occupancy (>85%)
            pd.DataFrame({'bookings': [30], 'booked_days': [28]}),
            # _get_booking_pace_multiplier: check count > 0
            pd.DataFrame({'count': [5]}),
            # _get_booking_pace_multiplier: 2024 vs 2023 strong growth
            pd.DataFrame({'year_2024': [2000.0], 'year_2023': [1000.0], 'total_records': [10]}),
            # _get_event_multiplier: 15% uplift event
            pd.DataFrame({'uplift_percentage': [15.0], 'event_name': ['Festival']}),
        ]

        # Wednesday = weekday (weekday() == 2)
        test_date = datetime(2024, 7, 10)
        result = pricing_model.calculate_business_price('TestListing', test_date)

        assert 'base_rate' in result
        assert 'historical_mult' in result
        assert 'occupancy_mult' in result
        assert 'pace_mult' in result
        assert 'event_mult' in result
        assert 'ai_correction' in result
        assert 'btw_adjustment' in result
        assert 'final_price' in result

        # Verify individual factors
        assert result['base_rate'] == 100.0  # weekday price
        assert result['historical_mult'] == 1.2  # 120/100
        assert result['occupancy_mult'] == 1.2  # >85%
        assert result['pace_mult'] == 1.15  # >1.5x growth
        assert result['event_mult'] == 1.15  # 1 + 15/100
        assert result['ai_correction'] == 1.05
        assert result['btw_adjustment'] == 1.0

        # Final = 100 * 1.2 * 1.2 * 1.15 * 1.15 * 1.05 * 1.0
        expected = round(100.0 * 1.2 * 1.2 * 1.15 * 1.15 * 1.05 * 1.0, 2)
        assert result['final_price'] == expected

    @patch('business_pricing_model.pd.read_sql')
    def test_calculate_business_price_all_defaults(self, mock_read_sql, pricing_model):
        """Test calculation when all multipliers fall back to defaults."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            # _get_base_rate: listing not found
            pd.DataFrame(),
            # _get_historical_multiplier: no historical data
            pd.DataFrame({'historical_adr': [None]}),
            # _get_occupancy_multiplier: moderate occupancy
            pd.DataFrame({'bookings': [15], 'booked_days': [15]}),
            # _get_booking_pace_multiplier: no bnbfuture data
            pd.DataFrame({'count': [0]}),
            # _get_event_multiplier: no event
            pd.DataFrame(),
        ]

        # Monday = weekday (weekday() == 0)
        test_date = datetime(2024, 7, 8)
        result = pricing_model.calculate_business_price('TestListing', test_date)

        assert result['base_rate'] == 85  # weekday fallback
        assert result['historical_mult'] == 1.0  # no data
        assert result['occupancy_mult'] == 1.0  # 15/30 = 50%, between 40-70%
        assert result['pace_mult'] == 1.0  # no bnbfuture data
        assert result['event_mult'] == 1.0  # no event
        assert result['ai_correction'] == 1.05
        assert result['btw_adjustment'] == 1.0

        expected = round(85 * 1.0 * 1.0 * 1.0 * 1.0 * 1.05 * 1.0, 2)
        assert result['final_price'] == expected


class TestGetBaseRate:
    """Tests for _get_base_rate method."""

    @pytest.fixture
    def pricing_model(self, mock_db):
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    def test_get_base_rate_weekday_no_listing(self, pricing_model):
        """Test weekday base rate when no listing provided."""
        # Monday
        test_date = datetime(2024, 7, 8)
        result = pricing_model._get_base_rate(test_date, listing=None)
        assert result == 85

    def test_get_base_rate_weekend_friday_no_listing(self, pricing_model):
        """Test weekend base rate for Friday when no listing provided."""
        # Friday (weekday() == 4)
        test_date = datetime(2024, 7, 12)
        result = pricing_model._get_base_rate(test_date, listing=None)
        assert result == 110

    def test_get_base_rate_weekend_saturday_no_listing(self, pricing_model):
        """Test weekend base rate for Saturday when no listing provided."""
        # Saturday (weekday() == 5)
        test_date = datetime(2024, 7, 13)
        result = pricing_model._get_base_rate(test_date, listing=None)
        assert result == 110

    def test_get_base_rate_sunday_is_weekday(self, pricing_model):
        """Test that Sunday is treated as weekday (not weekend)."""
        # Sunday (weekday() == 6)
        test_date = datetime(2024, 7, 14)
        result = pricing_model._get_base_rate(test_date, listing=None)
        assert result == 85

    @patch('business_pricing_model.pd.read_sql')
    def test_get_base_rate_weekday_with_listing(self, mock_read_sql, pricing_model):
        """Test weekday base rate from listing data."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.return_value = pd.DataFrame({
            'base_weekday_price': [95.0],
            'base_weekend_price': [140.0]
        })

        # Tuesday (weekday() == 1)
        test_date = datetime(2024, 7, 9)
        result = pricing_model._get_base_rate(test_date, listing='MyListing')
        assert result == 95.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_base_rate_weekend_with_listing(self, mock_read_sql, pricing_model):
        """Test weekend base rate from listing data."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.return_value = pd.DataFrame({
            'base_weekday_price': [95.0],
            'base_weekend_price': [140.0]
        })

        # Friday (weekday() == 4)
        test_date = datetime(2024, 7, 12)
        result = pricing_model._get_base_rate(test_date, listing='MyListing')
        assert result == 140.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_base_rate_listing_not_found_fallback(self, mock_read_sql, pricing_model):
        """Test fallback when listing not found in DB."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.return_value = pd.DataFrame()  # Empty result

        # Friday
        test_date = datetime(2024, 7, 12)
        result = pricing_model._get_base_rate(test_date, listing='NonExistent')
        assert result == 110  # Weekend fallback

    @patch('business_pricing_model.pd.read_sql')
    def test_get_base_rate_db_error_fallback(self, mock_read_sql, pricing_model):
        """Test fallback when database raises an error."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.side_effect = Exception("DB connection lost")

        # Wednesday (weekday)
        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_base_rate(test_date, listing='MyListing')
        assert result == 85  # Weekday fallback


class TestGetHistoricalMultiplier:
    """Tests for _get_historical_multiplier method."""

    @pytest.fixture
    def pricing_model(self, mock_db):
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    @patch('business_pricing_model.pd.read_sql')
    def test_get_historical_multiplier_with_data(self, mock_read_sql, pricing_model):
        """Test historical multiplier when data is available."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # historical ADR = 150, baseline ADR = 100 -> multiplier = 1.5
        mock_read_sql.side_effect = [
            pd.DataFrame({'historical_adr': [150.0]}),
            pd.DataFrame({'baseline_adr': [100.0]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_historical_multiplier('TestListing', test_date)
        assert result == 1.5

    @patch('business_pricing_model.pd.read_sql')
    def test_get_historical_multiplier_no_historical_data(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 when no historical data exists."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.return_value = pd.DataFrame({'historical_adr': [None]})

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_historical_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_historical_multiplier_empty_result(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 when query returns empty DataFrame."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.return_value = pd.DataFrame()

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_historical_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_historical_multiplier_no_baseline(self, mock_read_sql, pricing_model):
        """Test fallback when historical exists but baseline is None."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            pd.DataFrame({'historical_adr': [120.0]}),
            pd.DataFrame({'baseline_adr': [None]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_historical_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_historical_multiplier_db_error(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 on database error."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.side_effect = Exception("Query failed")

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_historical_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_historical_multiplier_rounds_to_3_decimals(self, mock_read_sql, pricing_model):
        """Test that result is rounded to 3 decimal places."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # 133.33 / 100 = 1.3333... -> 1.333
        mock_read_sql.side_effect = [
            pd.DataFrame({'historical_adr': [133.33]}),
            pd.DataFrame({'baseline_adr': [100.0]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_historical_multiplier('TestListing', test_date)
        assert result == 1.333


class TestGetOccupancyMultiplier:
    """Tests for _get_occupancy_multiplier method."""

    @pytest.fixture
    def pricing_model(self, mock_db):
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    @patch('business_pricing_model.pd.read_sql')
    def test_get_occupancy_multiplier_high_demand(self, mock_read_sql, pricing_model):
        """Test multiplier 1.2 when occupancy > 85%."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # booked_days=27, days_in_month=30 -> 90% occupancy
        mock_read_sql.return_value = pd.DataFrame({'bookings': [30], 'booked_days': [27]})

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_occupancy_multiplier('TestListing', test_date)
        assert result == 1.2

    @patch('business_pricing_model.pd.read_sql')
    def test_get_occupancy_multiplier_good_demand(self, mock_read_sql, pricing_model):
        """Test multiplier 1.1 when occupancy > 70% but <= 85%."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # booked_days=23, days_in_month=30 -> ~77% occupancy
        mock_read_sql.return_value = pd.DataFrame({'bookings': [25], 'booked_days': [23]})

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_occupancy_multiplier('TestListing', test_date)
        assert result == 1.1

    @patch('business_pricing_model.pd.read_sql')
    def test_get_occupancy_multiplier_low_demand(self, mock_read_sql, pricing_model):
        """Test multiplier 0.9 when occupancy < 40%."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # booked_days=10, days_in_month=30 -> ~33% occupancy
        mock_read_sql.return_value = pd.DataFrame({'bookings': [10], 'booked_days': [10]})

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_occupancy_multiplier('TestListing', test_date)
        assert result == 0.9

    @patch('business_pricing_model.pd.read_sql')
    def test_get_occupancy_multiplier_moderate_demand(self, mock_read_sql, pricing_model):
        """Test multiplier 1.0 when occupancy between 40% and 70%."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        # booked_days=15, days_in_month=30 -> 50% occupancy
        mock_read_sql.return_value = pd.DataFrame({'bookings': [15], 'booked_days': [15]})

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_occupancy_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_occupancy_multiplier_empty_result(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 when no data returned."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.return_value = pd.DataFrame()

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_occupancy_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_occupancy_multiplier_db_error(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 on database error."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.side_effect = Exception("Connection timeout")

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_occupancy_multiplier('TestListing', test_date)
        assert result == 1.0


class TestGetBookingPaceMultiplier:
    """Tests for _get_booking_pace_multiplier method."""

    @pytest.fixture
    def pricing_model(self, mock_db):
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_strong_growth(self, mock_read_sql, pricing_model):
        """Test multiplier 1.15 when 2024/2023 ratio > 1.5."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            # check query: has data
            pd.DataFrame({'count': [10]}),
            # monthly query: 2024=2000, 2023=1000 -> ratio 2.0
            pd.DataFrame({'year_2024': [2000.0], 'year_2023': [1000.0], 'total_records': [5]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 1.15

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_good_growth(self, mock_read_sql, pricing_model):
        """Test multiplier 1.1 when 2024/2023 ratio > 1.2 but <= 1.5."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            pd.DataFrame({'count': [10]}),
            # ratio = 1300/1000 = 1.3
            pd.DataFrame({'year_2024': [1300.0], 'year_2023': [1000.0], 'total_records': [5]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 1.1

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_significant_decline(self, mock_read_sql, pricing_model):
        """Test multiplier 0.9 when 2024/2023 ratio < 0.3."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            pd.DataFrame({'count': [10]}),
            # ratio = 200/1000 = 0.2
            pd.DataFrame({'year_2024': [200.0], 'year_2023': [1000.0], 'total_records': [5]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 0.9

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_moderate_decline(self, mock_read_sql, pricing_model):
        """Test multiplier 0.95 when 2024/2023 ratio < 0.7 but >= 0.3."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            pd.DataFrame({'count': [10]}),
            # ratio = 500/1000 = 0.5
            pd.DataFrame({'year_2024': [500.0], 'year_2023': [1000.0], 'total_records': [5]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 0.95

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_stable(self, mock_read_sql, pricing_model):
        """Test multiplier 1.0 when ratio is between 0.7 and 1.2."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.side_effect = [
            pd.DataFrame({'count': [10]}),
            # ratio = 1000/1000 = 1.0
            pd.DataFrame({'year_2024': [1000.0], 'year_2023': [1000.0], 'total_records': [5]}),
        ]

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_no_bnbfuture_data(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 when no bnbfuture data exists."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.return_value = pd.DataFrame({'count': [0]})

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_booking_pace_multiplier_db_error(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 on database error."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.side_effect = Exception("Query timeout")

        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_booking_pace_multiplier('TestListing', test_date)
        assert result == 1.0


class TestGetEventMultiplier:
    """Tests for _get_event_multiplier method."""

    @pytest.fixture
    def pricing_model(self, mock_db):
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    @patch('business_pricing_model.pd.read_sql')
    def test_get_event_multiplier_with_event(self, mock_read_sql, pricing_model):
        """Test event multiplier when active event exists."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.return_value = pd.DataFrame({
            'uplift_percentage': [20.0],
            'event_name': ['Kings Day']
        })

        test_date = datetime(2024, 4, 27)
        result = pricing_model._get_event_multiplier(test_date)
        assert result == 1.2  # 1 + 20/100

    @patch('business_pricing_model.pd.read_sql')
    def test_get_event_multiplier_no_event(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 when no active event."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.return_value = pd.DataFrame()

        test_date = datetime(2024, 3, 5)
        result = pricing_model._get_event_multiplier(test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_event_multiplier_zero_uplift(self, mock_read_sql, pricing_model):
        """Test event with 0% uplift returns 1.0."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn

        mock_read_sql.return_value = pd.DataFrame({
            'uplift_percentage': [0.0],
            'event_name': ['Minor Event']
        })

        test_date = datetime(2024, 5, 1)
        result = pricing_model._get_event_multiplier(test_date)
        assert result == 1.0

    @patch('business_pricing_model.pd.read_sql')
    def test_get_event_multiplier_db_error(self, mock_read_sql, pricing_model):
        """Test fallback to 1.0 on database error."""
        mock_conn = MagicMock()
        pricing_model.db.get_connection.return_value = mock_conn
        mock_read_sql.side_effect = Exception("Table not found")

        test_date = datetime(2024, 4, 27)
        result = pricing_model._get_event_multiplier(test_date)
        assert result == 1.0


class TestGetBtwAdjustment:
    """Tests for _get_btw_adjustment method."""

    @pytest.fixture
    def pricing_model(self, mock_db):
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            model = BusinessPricingModel(test_mode=True)
        return model

    def test_get_btw_adjustment_returns_one(self, pricing_model):
        """Test BTW adjustment currently returns 1.0 (placeholder)."""
        test_date = datetime(2024, 7, 10)
        result = pricing_model._get_btw_adjustment(test_date)
        assert result == 1.0

    def test_get_btw_adjustment_any_date_returns_one(self, pricing_model):
        """Test BTW adjustment returns 1.0 regardless of date."""
        dates = [
            datetime(2024, 1, 1),
            datetime(2024, 6, 15),
            datetime(2025, 1, 1),
        ]
        for d in dates:
            assert pricing_model._get_btw_adjustment(d) == 1.0
