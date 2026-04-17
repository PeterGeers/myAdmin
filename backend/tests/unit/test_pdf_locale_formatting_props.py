"""
Property-based tests for PDFGeneratorService locale-aware formatting.

Feature: zzp-module
Property 4: Locale-aware formatting matches client country
Property 5: Currency symbol from invoice currency code

Validates: Requirements 21.1, 21.2, 21.3, 21.4, 21.5
Reference: .kiro/specs/zzp-module/design-parameter-enhancements.md §14.8
"""

import sys
import os
import pytest
from datetime import date
from unittest.mock import Mock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.pdf_generator_service import (
    PDFGeneratorService, COUNTRY_LOCALE_MAP, DEFAULT_LOCALE,
)
from babel.numbers import format_currency, format_decimal
from babel.dates import format_date as babel_format_date


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All mapped country keys from COUNTRY_LOCALE_MAP
mapped_country_st = st.sampled_from(list(COUNTRY_LOCALE_MAP.keys()))

# Unmapped country strings that should fall back to nl_NL
unmapped_country_st = st.sampled_from([
    'JP', 'CN', 'BR', 'AU', 'ZA', 'IN', 'KR', 'MX',
    'Japan', 'China', 'Brazil', 'Australia',
])

# Empty/missing country values
empty_country_st = st.sampled_from(['', '  ', None])

# Monetary amounts (positive, reasonable range)
amount_st = st.floats(
    min_value=0.0, max_value=999999.99,
    allow_nan=False, allow_infinity=False,
)

# Positive monetary amounts (non-zero for meaningful currency tests)
positive_amount_st = st.floats(
    min_value=0.01, max_value=999999.99,
    allow_nan=False, allow_infinity=False,
)

# Quantity values (can be whole or fractional)
quantity_st = st.floats(
    min_value=0.0, max_value=99999.99,
    allow_nan=False, allow_infinity=False,
)

# Fractional quantities (never whole numbers)
fractional_qty_st = st.floats(
    min_value=0.01, max_value=99999.99,
    allow_nan=False, allow_infinity=False,
).filter(lambda x: x != int(x))

# Valid invoice dates
invoice_date_st = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2039, 12, 31),
)

# ISO 4217 currency codes commonly used
currency_code_st = st.sampled_from(['EUR', 'USD', 'GBP', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'JPY'])

# Locale identifiers from the map
locale_st = st.sampled_from(list(set(COUNTRY_LOCALE_MAP.values())))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service():
    """Create a PDFGeneratorService with mock dependencies."""
    db = Mock()
    template_svc = Mock(get_template_metadata=Mock(return_value=None))
    param_svc = Mock(get_param=Mock(return_value=None))
    return PDFGeneratorService(
        db=db, template_service=template_svc, parameter_service=param_svc,
    )


def _make_contact(country):
    """Create a contact dict with the given country."""
    if country is None:
        return {}
    return {'country': country}


# ---------------------------------------------------------------------------
# Property 4: Locale-aware formatting matches client country
# Feature: zzp-module, Property 4: Locale-aware formatting matches client country
#
# For any client country and any numeric value (date, currency amount, or
# decimal quantity), the formatted output from the PDF generator SHALL match
# the formatting conventions of the locale derived from that country. If the
# country is not mapped or is empty, the formatting SHALL match the Dutch
# (nl_NL) locale.
#
# Validates: Requirements 21.1, 21.2, 21.3, 21.4
# ---------------------------------------------------------------------------


class TestLocaleFormattingMatchesClientCountry:
    """Property 4: Locale-aware formatting matches client country."""

    # -- 4a: Mapped countries resolve to the correct locale ----------------

    @settings(max_examples=100)
    @given(country=mapped_country_st)
    def test_mapped_country_resolves_to_expected_locale(self, country):
        """Any mapped country key resolves to its COUNTRY_LOCALE_MAP value."""
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        assert locale == COUNTRY_LOCALE_MAP[country], (
            f"Country '{country}' should resolve to "
            f"'{COUNTRY_LOCALE_MAP[country]}', got '{locale}'"
        )

    # -- 4b: Unmapped/empty countries default to nl_NL --------------------

    @settings(max_examples=100)
    @given(country=unmapped_country_st)
    def test_unmapped_country_defaults_to_nl_nl(self, country):
        """Any unmapped country falls back to DEFAULT_LOCALE (nl_NL)."""
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        assert locale == DEFAULT_LOCALE, (
            f"Unmapped country '{country}' should default to "
            f"'{DEFAULT_LOCALE}', got '{locale}'"
        )

    @settings(max_examples=100)
    @given(country=empty_country_st)
    def test_empty_country_defaults_to_nl_nl(self, country):
        """Empty or None country falls back to DEFAULT_LOCALE (nl_NL)."""
        svc = _make_service()
        contact = _make_contact(country)
        locale = svc._resolve_locale(contact)
        assert locale == DEFAULT_LOCALE

    # -- 4c: Currency formatting matches locale conventions ----------------

    @settings(max_examples=100)
    @given(country=mapped_country_st, amount=amount_st)
    def test_currency_formatting_matches_locale(self, country, amount):
        """Formatted currency matches babel's output for the resolved locale."""
        svc = _make_service()
        locale = COUNTRY_LOCALE_MAP[country]
        result = svc._format_amount(amount, 'EUR', locale)
        expected = format_currency(float(amount), 'EUR', locale=locale)
        assert result == expected, (
            f"Amount {amount} with locale '{locale}': "
            f"expected '{expected}', got '{result}'"
        )

    # -- 4d: Date formatting matches locale conventions --------------------

    @settings(max_examples=100)
    @given(country=mapped_country_st, d=invoice_date_st)
    def test_date_formatting_matches_locale(self, country, d):
        """Formatted date matches babel's short format for the resolved locale."""
        svc = _make_service()
        locale = COUNTRY_LOCALE_MAP[country]
        result = svc._format_date(d, locale)
        expected = babel_format_date(d, format='short', locale=locale)
        assert result == expected, (
            f"Date {d} with locale '{locale}': "
            f"expected '{expected}', got '{result}'"
        )

    @settings(max_examples=100)
    @given(country=mapped_country_st, d=invoice_date_st)
    def test_date_string_formatting_matches_locale(self, country, d):
        """ISO date string formatted same as date object for the locale."""
        svc = _make_service()
        locale = COUNTRY_LOCALE_MAP[country]
        result_from_string = svc._format_date(d.isoformat(), locale)
        result_from_date = svc._format_date(d, locale)
        assert result_from_string == result_from_date, (
            f"Date string '{d.isoformat()}' should format same as date object"
        )

    # -- 4e: Quantity formatting matches locale conventions -----------------

    @settings(max_examples=100)
    @given(country=mapped_country_st, qty=fractional_qty_st)
    def test_fractional_qty_formatting_matches_locale(self, country, qty):
        """Fractional quantities use locale-specific decimal separator."""
        svc = _make_service()
        locale = COUNTRY_LOCALE_MAP[country]
        result = svc._format_qty(qty, locale)
        expected = format_decimal(qty, format='#,##0.##', locale=locale)
        assert result == expected, (
            f"Qty {qty} with locale '{locale}': "
            f"expected '{expected}', got '{result}'"
        )

    @settings(max_examples=100)
    @given(
        country=mapped_country_st,
        qty=st.integers(min_value=0, max_value=99999).map(float),
    )
    def test_whole_qty_returns_integer_string(self, country, qty):
        """Whole number quantities return plain integer strings regardless of locale."""
        svc = _make_service()
        locale = COUNTRY_LOCALE_MAP[country]
        result = svc._format_qty(qty, locale)
        assert result == str(int(qty)), (
            f"Whole qty {qty} should return '{int(qty)}', got '{result}'"
        )

    # -- 4f: Default locale used when country missing ----------------------

    @settings(max_examples=100)
    @given(amount=positive_amount_st, d=invoice_date_st)
    def test_missing_country_uses_nl_formatting(self, amount, d):
        """When contact has no country, formatting uses nl_NL locale."""
        svc = _make_service()
        locale = svc._resolve_locale({})
        assert locale == 'nl_NL'

        result_amount = svc._format_amount(amount, 'EUR', locale)
        expected_amount = format_currency(float(amount), 'EUR', locale='nl_NL')
        assert result_amount == expected_amount

        result_date = svc._format_date(d, locale)
        expected_date = babel_format_date(d, format='short', locale='nl_NL')
        assert result_date == expected_date


# ---------------------------------------------------------------------------
# Property 5: Currency symbol from invoice currency code
# Feature: zzp-module, Property 5: Currency symbol from invoice currency code
#
# For any invoice with a specified currency code (ISO 4217) and any client
# locale, the currency symbol in the formatted amount SHALL correspond to the
# invoice's currency code, not the locale's default currency.
#
# Validates: Requirements 21.5
# ---------------------------------------------------------------------------


class TestCurrencySymbolFromInvoiceCurrencyCode:
    """Property 5: Currency symbol from invoice currency code."""

    # -- 5a: Currency symbol matches the invoice currency, not locale ------

    @settings(max_examples=100)
    @given(currency=currency_code_st, locale=locale_st, amount=positive_amount_st)
    def test_formatted_amount_uses_invoice_currency_symbol(self, currency, locale, amount):
        """The formatted amount uses the invoice's currency code, not the locale default."""
        svc = _make_service()
        result = svc._format_amount(amount, currency, locale)
        # Verify by comparing with babel's output for the same currency+locale
        expected = format_currency(float(amount), currency, locale=locale)
        assert result == expected, (
            f"Amount {amount} with currency '{currency}' and locale '{locale}': "
            f"expected '{expected}', got '{result}'"
        )

    @settings(max_examples=100)
    @given(currency=currency_code_st, locale=locale_st, amount=positive_amount_st)
    def test_currency_symbol_differs_from_locale_default_when_appropriate(
        self, currency, locale, amount,
    ):
        """When invoice currency differs from locale's default, the symbol reflects the invoice currency."""
        svc = _make_service()
        result = svc._format_amount(amount, currency, locale)
        # Format the same amount with the locale's default currency (EUR for nl_NL, etc.)
        # The result should use the invoice currency, not the locale default
        result_with_eur = format_currency(float(amount), 'EUR', locale=locale)
        if currency != 'EUR':
            # If the currency is not EUR, the formatted strings should differ
            # (different symbol or code)
            assert result != result_with_eur, (
                f"Currency '{currency}' should produce different output than EUR "
                f"for locale '{locale}', but both gave '{result}'"
            )

    # -- 5b: Non-EUR currencies show correct symbol across all locales -----

    @settings(max_examples=100)
    @given(locale=locale_st, amount=positive_amount_st)
    def test_usd_shows_dollar_symbol_in_any_locale(self, locale, amount):
        """USD formatted amount contains a dollar indicator regardless of locale."""
        svc = _make_service()
        result = svc._format_amount(amount, 'USD', locale)
        # USD should show $ or US$ or USD depending on locale, but never €
        assert '€' not in result, (
            f"USD amount should not contain € symbol, got '{result}'"
        )

    @settings(max_examples=100)
    @given(locale=locale_st, amount=positive_amount_st)
    def test_gbp_shows_pound_symbol_in_any_locale(self, locale, amount):
        """GBP formatted amount contains a pound indicator regardless of locale."""
        svc = _make_service()
        result = svc._format_amount(amount, 'GBP', locale)
        # GBP should show £ or GBP, but never €
        assert '€' not in result, (
            f"GBP amount should not contain € symbol, got '{result}'"
        )

    @settings(max_examples=100)
    @given(locale=locale_st, amount=positive_amount_st)
    def test_eur_shows_euro_symbol_in_any_locale(self, locale, amount):
        """EUR formatted amount contains the euro symbol regardless of locale."""
        svc = _make_service()
        result = svc._format_amount(amount, 'EUR', locale)
        assert '€' in result, (
            f"EUR amount should contain € symbol, got '{result}'"
        )

    # -- 5c: Same amount, different currencies produce different output -----

    @settings(max_examples=100)
    @given(locale=locale_st, amount=positive_amount_st)
    def test_same_amount_different_currencies_differ(self, locale, amount):
        """Same numeric amount formatted with different currencies produces different strings."""
        svc = _make_service()
        eur_result = svc._format_amount(amount, 'EUR', locale)
        usd_result = svc._format_amount(amount, 'USD', locale)
        gbp_result = svc._format_amount(amount, 'GBP', locale)
        # All three should be different (different currency symbols)
        assert len({eur_result, usd_result, gbp_result}) == 3, (
            f"EUR='{eur_result}', USD='{usd_result}', GBP='{gbp_result}' "
            f"should all be different for locale '{locale}'"
        )

    # -- 5d: Currency code is independent of locale resolution -------------

    @settings(max_examples=100)
    @given(
        country=mapped_country_st,
        currency=currency_code_st,
        amount=positive_amount_st,
    )
    def test_locale_resolution_does_not_override_currency(self, country, currency, amount):
        """The resolved locale affects number formatting but not the currency symbol."""
        svc = _make_service()
        locale = svc._resolve_locale(_make_contact(country))
        result = svc._format_amount(amount, currency, locale)
        expected = format_currency(float(amount), currency, locale=locale)
        assert result == expected, (
            f"Country '{country}' (locale '{locale}') with currency '{currency}': "
            f"expected '{expected}', got '{result}'"
        )
