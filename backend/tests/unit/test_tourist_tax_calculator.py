"""
Unit tests for TouristTaxCalculator.

Example-based tests for each formula with known inputs/outputs and edge cases.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import pytest
from datetime import date
from unittest.mock import Mock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tourist_tax_calculator import TouristTaxCalculator


def make_rate_info(rate, method='percentage', desc='Test'):
    return {
        'rate': rate, 'calc_method': method,
        'description': desc, 'calc_params': None,
    }


def make_calculator(rate_info):
    trs = Mock()
    trs.get_tax_rate = Mock(return_value=rate_info)
    return TouristTaxCalculator(trs)


# ---------------------------------------------------------------------------
# Percentage Method
# ---------------------------------------------------------------------------

class TestPercentageMethod:

    def test_standard_percentage(self):
        """6.9% of 100 excl VAT: (100 / 106.9) * 6.9 = 6.45"""
        calc = make_calculator(make_rate_info(6.9, 'percentage'))
        result = calc.calculate('T1', date(2026, 1, 1), 100.0)
        assert result['amount'] == round((100.0 / 106.9) * 6.9, 2)
        assert result['method'] == 'percentage'

    def test_zero_base_amount(self):
        calc = make_calculator(make_rate_info(6.9, 'percentage'))
        result = calc.calculate('T1', date(2026, 1, 1), 0.0)
        assert result['amount'] == 0.0

    def test_negative_amount_refund(self):
        """Negative amounts are valid for refunds."""
        calc = make_calculator(make_rate_info(6.9, 'percentage'))
        result = calc.calculate('T1', date(2026, 1, 1), -100.0)
        expected = round((-100.0 / 106.9) * 6.9, 2)
        assert result['amount'] == expected


# ---------------------------------------------------------------------------
# Fixed Per Guest Night Method
# ---------------------------------------------------------------------------

class TestFixedPerGuestNight:

    def test_standard_calculation(self):
        """2.50 per guest per night, 2 guests, 3 nights = 15.00"""
        calc = make_calculator(make_rate_info(2.50, 'fixed_per_guest_night'))
        result = calc.calculate('T1', date(2026, 1, 1), 0,
                                number_of_nights=3, number_of_guests=2)
        assert result['amount'] == 15.0

    def test_zero_nights(self):
        calc = make_calculator(make_rate_info(2.50, 'fixed_per_guest_night'))
        result = calc.calculate('T1', date(2026, 1, 1), 0,
                                number_of_nights=0, number_of_guests=2)
        assert result['amount'] == 0.0

    def test_zero_guests(self):
        calc = make_calculator(make_rate_info(2.50, 'fixed_per_guest_night'))
        result = calc.calculate('T1', date(2026, 1, 1), 0,
                                number_of_nights=3, number_of_guests=0)
        assert result['amount'] == 0.0


# ---------------------------------------------------------------------------
# Fixed Per Night Method
# ---------------------------------------------------------------------------

class TestFixedPerNight:

    def test_standard_calculation(self):
        """3.00 per night, 4 nights = 12.00"""
        calc = make_calculator(make_rate_info(3.0, 'fixed_per_night'))
        result = calc.calculate('T1', date(2026, 1, 1), 0, number_of_nights=4)
        assert result['amount'] == 12.0

    def test_zero_nights(self):
        calc = make_calculator(make_rate_info(3.0, 'fixed_per_night'))
        result = calc.calculate('T1', date(2026, 1, 1), 0, number_of_nights=0)
        assert result['amount'] == 0.0


# ---------------------------------------------------------------------------
# Percentage of Room Price Method
# ---------------------------------------------------------------------------

class TestPercentageOfRoomPrice:

    def test_standard_calculation(self):
        """5% of 200 room price = 10.00"""
        calc = make_calculator(make_rate_info(5.0, 'percentage_of_room_price'))
        result = calc.calculate('T1', date(2026, 1, 1), 0, room_price=200.0)
        assert result['amount'] == 10.0

    def test_no_room_price_defaults_to_zero(self):
        calc = make_calculator(make_rate_info(5.0, 'percentage_of_room_price'))
        result = calc.calculate('T1', date(2026, 1, 1), 0)
        assert result['amount'] == 0.0


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_no_rate_configured(self):
        calc = make_calculator(None)
        result = calc.calculate('T1', date(2026, 1, 1), 500.0)
        assert result == {'amount': 0, 'method': 'none', 'rate': 0, 'description': ''}

    def test_unknown_method(self):
        calc = make_calculator(make_rate_info(5.0, 'some_future_method'))
        result = calc.calculate('T1', date(2026, 1, 1), 500.0)
        assert result['amount'] == 0
        assert result['method'] == 'some_future_method'
        assert result['rate'] == 5.0

    def test_result_has_all_keys(self):
        calc = make_calculator(make_rate_info(6.9, 'percentage', 'Toeristenbelasting'))
        result = calc.calculate('T1', date(2026, 1, 1), 100.0)
        assert set(result.keys()) == {'amount', 'method', 'rate', 'description'}
        assert result['description'] == 'Toeristenbelasting'

    def test_rounding_to_2_decimals(self):
        """Verify result is always rounded to 2 decimal places."""
        calc = make_calculator(make_rate_info(7.3, 'percentage'))
        result = calc.calculate('T1', date(2026, 1, 1), 333.33)
        assert result['amount'] == round(result['amount'], 2)
        amount_str = f"{result['amount']:.2f}"
        assert float(amount_str) == result['amount']
