"""
TouristTaxCalculator: Dispatches tourist tax computation to the correct formula
based on calc_method from the tax_rates table.

Supported methods: percentage, fixed_per_guest_night, fixed_per_night,
percentage_of_room_price. Unknown methods return amount 0 with a warning.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class TouristTaxCalculator:
    """Calculates tourist tax using municipality-specific methods."""

    def __init__(self, tax_rate_service):
        self.tax_rate_service = tax_rate_service

    def calculate(self, tenant: str, reference_date: date,
                  base_amount_excl_vat: float,
                  number_of_nights: int = 1,
                  number_of_guests: int = 1,
                  room_price: float = None) -> dict:
        """
        Calculate tourist tax using the municipality-specific method.
        Returns dict with amount (rounded to 2 decimals), method, rate, description.
        """
        rate_info = self.tax_rate_service.get_tax_rate(
            tenant, 'tourist_tax', 'standard', reference_date
        )

        if rate_info is None:
            return {'amount': 0, 'method': 'none', 'rate': 0, 'description': ''}

        rate = rate_info['rate']
        method = rate_info.get('calc_method', 'percentage')
        description = rate_info.get('description', '')

        amount = self._dispatch(method, rate, base_amount_excl_vat,
                                number_of_nights, number_of_guests, room_price)

        return {
            'amount': round(amount, 2),
            'method': method,
            'rate': rate,
            'description': description,
        }

    def _dispatch(self, method: str, rate: float, base_amount_excl_vat: float,
                  nights: int, guests: int, room_price: Optional[float]) -> float:
        """Route to the correct formula based on calc_method."""
        if method == 'percentage':
            return self._calc_percentage(base_amount_excl_vat, rate)
        elif method == 'fixed_per_guest_night':
            return self._calc_fixed_per_guest_night(rate, guests, nights)
        elif method == 'fixed_per_night':
            return self._calc_fixed_per_night(rate, nights)
        elif method == 'percentage_of_room_price':
            return self._calc_percentage_of_room_price(room_price or 0, rate)
        else:
            logger.warning("Unknown calc_method '%s' for tourist tax", method)
            return 0

    @staticmethod
    def _calc_percentage(base_amount_excl_vat: float, rate: float) -> float:
        """(base_amount_excl_vat / (100 + rate)) * rate"""
        if (100 + rate) == 0:
            return 0
        return (base_amount_excl_vat / (100 + rate)) * rate

    @staticmethod
    def _calc_fixed_per_guest_night(rate: float, guests: int, nights: int) -> float:
        """rate * guests * nights"""
        return rate * guests * nights

    @staticmethod
    def _calc_fixed_per_night(rate: float, nights: int) -> float:
        """rate * nights"""
        return rate * nights

    @staticmethod
    def _calc_percentage_of_room_price(room_price: float, rate: float) -> float:
        """room_price * (rate / 100)"""
        return room_price * (rate / 100)
