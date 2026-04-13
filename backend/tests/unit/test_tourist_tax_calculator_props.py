"""
Property-based tests for TouristTaxCalculator.

Feature: parameter-driven-config, Property 6: Tourist Tax Calculator Method Dispatch
Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7

Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import pytest
from datetime import date
from unittest.mock import Mock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tourist_tax_calculator import TouristTaxCalculator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_tax_rate_service(rate_info):
    """Create a mock TaxRateService that returns the given rate_info."""
    svc = Mock()
    svc.get_tax_rate = Mock(return_value=rate_info)
    return svc


# Strategies
rate_st = st.floats(min_value=0.001, max_value=50.0, allow_nan=False, allow_infinity=False)
amount_st = st.floats(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False)
positive_amount_st = st.floats(min_value=0.01, max_value=10000, allow_nan=False, allow_infinity=False)
nights_st = st.integers(min_value=0, max_value=365)
guests_st = st.integers(min_value=0, max_value=50)
valid_methods = ['percentage', 'fixed_per_guest_night', 'fixed_per_night', 'percentage_of_room_price']


# ---------------------------------------------------------------------------
# Property 6: Tourist Tax Calculator Method Dispatch
# Feature: parameter-driven-config, Property 6: Tourist Tax Calculator Method Dispatch
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
# ---------------------------------------------------------------------------

class TestTouristTaxMethodDispatch:
    """Correct formula applied per method, 2 decimal rounding, zero for unknown."""

    @settings(max_examples=100)
    @given(rate=rate_st, base_amount=amount_st)
    def test_percentage_method(self, rate, base_amount):
        rate_info = {
            'rate': rate, 'calc_method': 'percentage',
            'description': 'Test', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), base_amount)

        expected = round((base_amount / (100 + rate)) * rate, 2)
        assert result['amount'] == expected
        assert result['method'] == 'percentage'
        assert result['rate'] == rate

    @settings(max_examples=100)
    @given(rate=rate_st, nights=nights_st, guests=guests_st)
    def test_fixed_per_guest_night_method(self, rate, nights, guests):
        rate_info = {
            'rate': rate, 'calc_method': 'fixed_per_guest_night',
            'description': 'Test', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), 0,
                                number_of_nights=nights, number_of_guests=guests)

        expected = round(rate * guests * nights, 2)
        assert result['amount'] == expected
        assert result['method'] == 'fixed_per_guest_night'

    @settings(max_examples=100)
    @given(rate=rate_st, nights=nights_st)
    def test_fixed_per_night_method(self, rate, nights):
        rate_info = {
            'rate': rate, 'calc_method': 'fixed_per_night',
            'description': 'Test', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), 0,
                                number_of_nights=nights)

        expected = round(rate * nights, 2)
        assert result['amount'] == expected
        assert result['method'] == 'fixed_per_night'

    @settings(max_examples=100)
    @given(rate=rate_st, room_price=positive_amount_st)
    def test_percentage_of_room_price_method(self, rate, room_price):
        rate_info = {
            'rate': rate, 'calc_method': 'percentage_of_room_price',
            'description': 'Test', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), 0, room_price=room_price)

        expected = round(room_price * (rate / 100), 2)
        assert result['amount'] == expected
        assert result['method'] == 'percentage_of_room_price'

    @settings(max_examples=50)
    @given(
        method=st.text(min_size=1, max_size=30).filter(lambda m: m not in valid_methods),
        rate=rate_st,
    )
    def test_unknown_method_returns_zero(self, method, rate):
        rate_info = {
            'rate': rate, 'calc_method': method,
            'description': 'Test', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), 100.0)

        assert result['amount'] == 0
        assert result['method'] == method
        assert result['rate'] == rate

    @settings(max_examples=50)
    @given(base_amount=amount_st)
    def test_no_rate_configured_returns_zero(self, base_amount):
        trs = make_mock_tax_rate_service(None)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), base_amount)

        assert result['amount'] == 0
        assert result['method'] == 'none'
        assert result['rate'] == 0

    @settings(max_examples=100)
    @given(
        method=st.sampled_from(valid_methods),
        rate=rate_st,
        base_amount=amount_st,
        nights=nights_st,
        guests=guests_st,
        room_price=positive_amount_st,
    )
    def test_result_always_rounded_to_2_decimals(self, method, rate, base_amount,
                                                  nights, guests, room_price):
        rate_info = {
            'rate': rate, 'calc_method': method,
            'description': 'Test', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), base_amount,
                                number_of_nights=nights, number_of_guests=guests,
                                room_price=room_price)

        assert result['amount'] == round(result['amount'], 2)

    @settings(max_examples=100)
    @given(
        method=st.sampled_from(valid_methods),
        rate=rate_st,
        base_amount=amount_st,
    )
    def test_result_contains_required_keys(self, method, rate, base_amount):
        rate_info = {
            'rate': rate, 'calc_method': method,
            'description': 'Desc', 'calc_params': None,
        }
        trs = make_mock_tax_rate_service(rate_info)
        calc = TouristTaxCalculator(trs)

        result = calc.calculate('T1', date(2026, 1, 1), base_amount)

        assert 'amount' in result
        assert 'method' in result
        assert 'rate' in result
        assert 'description' in result
