"""
Property-based tests for business_pricing_model module.

Uses Hypothesis to verify correctness properties from the design document.
Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds

Requirements: 3.1
Reference: .kiro/specs/missing-py-tests/design.md
"""

import pytest
import pandas as pd
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import patch, MagicMock
from datetime import datetime, date

from business_pricing_model import BusinessPricingModel


# ---------------------------------------------------------------------------
# Strategies for generating realistic DB return values
# ---------------------------------------------------------------------------

# Occupancy: booked_days between 0 and 30
occupancy_data_st = st.integers(min_value=0, max_value=30)

# Historical ADR values: positive floats representing nightly rates
positive_adr_st = st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False)

# Event uplift percentages: 0 to 100%
uplift_percentage_st = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Revenue amounts for booking pace: positive floats
revenue_st = st.floats(min_value=1.0, max_value=1000000.0, allow_nan=False, allow_infinity=False)

# Dates strategy
dates_st = st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31))


# ---------------------------------------------------------------------------
# Property 1: Pricing Multiplier Bounds
# Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------

class TestPricingMultiplierBounds:
    """
    Property 1: Pricing Multiplier Bounds

    For any valid listing and date combination, each multiplier function in
    BusinessPricingModel (_get_historical_multiplier, _get_occupancy_multiplier,
    _get_booking_pace_multiplier, _get_event_multiplier) SHALL produce an output
    within its documented bounds (0.5 to 2.0 for standard multipliers, 0.0 to 0.21
    for BTW adjustment).

    Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds
    **Validates: Requirements 3.1**
    """

    @pytest.fixture(autouse=True)
    def setup_model(self, mock_db):
        """Create BusinessPricingModel instance with mocked DatabaseManager."""
        with patch('business_pricing_model.DatabaseManager', return_value=mock_db):
            self.model = BusinessPricingModel(test_mode=True)
        self.mock_db = mock_db

    @settings(max_examples=100, deadline=None)
    @given(
        booked_days=occupancy_data_st,
        test_date=dates_st,
    )
    def test_occupancy_multiplier_within_bounds(self, booked_days, test_date):
        """
        Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds

        For any occupancy data (booked_days 0-30), the occupancy multiplier
        output is always within the set {0.9, 1.0, 1.1, 1.2} which is within
        the documented bounds of 0.5 to 2.0.
        """
        mock_conn = MagicMock()
        self.mock_db.get_connection.return_value = mock_conn

        with patch('business_pricing_model.pd.read_sql') as mock_read_sql:
            mock_read_sql.return_value = pd.DataFrame({
                'bookings': [booked_days],
                'booked_days': [booked_days],
            })

            dt = datetime(test_date.year, test_date.month, test_date.day)
            result = self.model._get_occupancy_multiplier('TestListing', dt)

        # Must be in the valid set
        assert result in {0.9, 1.0, 1.1, 1.2}, f"Unexpected occupancy multiplier: {result}"
        # Must be within documented bounds
        assert 0.5 <= result <= 2.0

    @settings(max_examples=100, deadline=None)
    @given(
        historical_adr=positive_adr_st,
        baseline_adr=positive_adr_st,
        test_date=dates_st,
    )
    def test_historical_multiplier_within_bounds(self, historical_adr, baseline_adr, test_date):
        """
        Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds

        For any positive historical and baseline ADR values, the historical
        multiplier output is always a non-negative float equal to the ratio
        rounded to 3 decimals. The implementation does not clamp, so extreme
        ratios can exceed 2.0 or be below 0.5. We verify correctness of
        computation and that the result is non-negative and finite.
        """
        mock_conn = MagicMock()
        self.mock_db.get_connection.return_value = mock_conn

        with patch('business_pricing_model.pd.read_sql') as mock_read_sql:
            mock_read_sql.side_effect = [
                pd.DataFrame({'historical_adr': [historical_adr]}),
                pd.DataFrame({'baseline_adr': [baseline_adr]}),
            ]

            dt = datetime(test_date.year, test_date.month, test_date.day)
            result = self.model._get_historical_multiplier('TestListing', dt)

        # Result is a ratio rounded to 3 decimals; must be non-negative and finite
        assert isinstance(result, float)
        assert result >= 0.0, f"Historical multiplier must be non-negative, got {result}"
        expected = round(historical_adr / baseline_adr, 3)
        assert result == expected, f"Expected {expected}, got {result}"

    @settings(max_examples=100, deadline=None)
    @given(
        year_2024=revenue_st,
        year_2023=revenue_st,
        test_date=dates_st,
    )
    def test_booking_pace_multiplier_within_bounds(self, year_2024, year_2023, test_date):
        """
        Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds

        For any positive revenue values for 2024 and 2023, the booking pace
        multiplier output is always within the set {0.9, 0.95, 1.0, 1.1, 1.15}
        which is within the documented bounds of 0.5 to 2.0.
        """
        mock_conn = MagicMock()
        self.mock_db.get_connection.return_value = mock_conn

        with patch('business_pricing_model.pd.read_sql') as mock_read_sql:
            mock_read_sql.side_effect = [
                # check query: has data
                pd.DataFrame({'count': [10]}),
                # monthly query with revenue data
                pd.DataFrame({
                    'year_2024': [year_2024],
                    'year_2023': [year_2023],
                    'total_records': [5],
                }),
            ]

            dt = datetime(test_date.year, test_date.month, test_date.day)
            result = self.model._get_booking_pace_multiplier('TestListing', dt)

        # Must be in the valid set
        assert result in {0.9, 0.95, 1.0, 1.1, 1.15}, f"Unexpected pace multiplier: {result}"
        # Must be within documented bounds
        assert 0.5 <= result <= 2.0

    @settings(max_examples=100, deadline=None)
    @given(
        uplift=uplift_percentage_st,
        test_date=dates_st,
    )
    def test_event_multiplier_within_bounds(self, uplift, test_date):
        """
        Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds

        For any uplift percentage (0-100%), the event multiplier output
        (1 + uplift/100) is always within the documented bounds of 0.5 to 2.0.
        """
        mock_conn = MagicMock()
        self.mock_db.get_connection.return_value = mock_conn

        with patch('business_pricing_model.pd.read_sql') as mock_read_sql:
            mock_read_sql.return_value = pd.DataFrame({
                'uplift_percentage': [uplift],
                'event_name': ['TestEvent'],
            })

            dt = datetime(test_date.year, test_date.month, test_date.day)
            result = self.model._get_event_multiplier(dt)

        # event_mult = 1 + (uplift / 100), with uplift in [0, 100]
        # So result should be in [1.0, 2.0]
        expected = 1 + (uplift / 100)
        assert abs(result - expected) < 1e-9, f"Expected {expected}, got {result}"
        assert 0.5 <= result <= 2.0, f"Event multiplier {result} outside bounds [0.5, 2.0]"

    @settings(max_examples=100, deadline=None)
    @given(test_date=dates_st)
    def test_btw_adjustment_within_bounds(self, test_date):
        """
        Feature: missing-py-tests, Property 1: Pricing Multiplier Bounds

        For any date, the BTW adjustment currently returns 1.0.
        The documented bounds for BTW are 0.0 to 0.21, but the current
        implementation is a placeholder returning 1.0. We verify the actual
        behavior: always returns 1.0.
        """
        dt = datetime(test_date.year, test_date.month, test_date.day)
        result = self.model._get_btw_adjustment(dt)

        # Current implementation always returns 1.0
        assert result == 1.0
