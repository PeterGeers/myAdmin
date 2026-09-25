"""Property-based test for Airbnb amount parsing across notations.

Feature: airbnb-export-format-update

This file holds the Hypothesis property test for task 2.6 — Property 6:
"Amounts parse across notations". It targets ``parse_airbnb_amount`` directly
(the pure amount-parsing helper of ``str_airbnb_parser``).

It lives in its own uniquely-named file/class to avoid colliding with the
sibling parser property tests written by tasks 2.4/2.5/2.7/2.9
(``test_str_airbnb_parser_property.py`` and friends).

Property 6 (design.md): For any amount value written in US notation (period
decimal), quoted European notation with a period thousands separator, or
European notation without a thousands separator, the Airbnb_Parser parses it to
the corresponding numeric value.

Validates: Requirements 4.1, 4.2, 4.3
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from str_airbnb_parser import parse_airbnb_amount

# Amounts are formatted to two decimals in every notation, so any float
# comparison only needs to tolerate binary-float rounding noise, not real
# precision loss.
TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
def _pad(draw, text: str) -> str:
    """Wrap ``text`` in the leading/trailing spaces Airbnb cells arrive with;
    the parser strips them, so padding must not change the parsed value."""
    lpad = " " * draw(st.integers(min_value=0, max_value=3))
    rpad = " " * draw(st.integers(min_value=0, max_value=3))
    return f"{lpad}{text}{rpad}"


@st.composite
def _us_notation(draw):
    """US notation: period decimal, no thousands separator (Req 4.1).

    Returns ``(rendered_cell, expected_value)``.
    """
    whole = draw(st.integers(min_value=0, max_value=99999))
    cents = draw(st.integers(min_value=0, max_value=99))
    rendered = _pad(draw, f"{whole}.{cents:02d}")
    expected = whole + cents / 100.0
    return rendered, expected


@st.composite
def _european_no_thousands(draw):
    """European notation with a comma decimal, no thousands separator (Req 4.3),
    e.g. ``"42,59"``. Returns ``(rendered_cell, expected_value)``."""
    whole = draw(st.integers(min_value=0, max_value=999))
    cents = draw(st.integers(min_value=0, max_value=99))
    rendered = _pad(draw, f"{whole},{cents:02d}")
    expected = whole + cents / 100.0
    return rendered, expected


@st.composite
def _european_with_thousands(draw):
    """Quoted European notation with a period thousands separator and a comma
    decimal (Req 4.2), e.g. ``"1.234,56"``. Returns ``(rendered_cell,
    expected_value)``.

    A single period thousands group is enough to exercise the "drop the '.'
    thousands separator" branch of the parser; the integer part is rebuilt by
    concatenating the groups.
    """
    thousands = draw(st.integers(min_value=1, max_value=999))
    rest = draw(st.integers(min_value=0, max_value=999))
    cents = draw(st.integers(min_value=0, max_value=99))
    rendered = _pad(draw, f"{thousands}.{rest:03d},{cents:02d}")
    expected = int(f"{thousands}{rest:03d}") + cents / 100.0
    return rendered, expected


# A single amount cell drawn from any of the three accepted notations, paired
# with its expected numeric value.
_amount_in_any_notation = st.one_of(
    _us_notation(),
    _european_no_thousands(),
    _european_with_thousands(),
)


# ---------------------------------------------------------------------------
# Property 6: Amounts parse across notations
# ---------------------------------------------------------------------------
class TestAmountsParseAcrossNotations:
    """Feature: airbnb-export-format-update, Property 6: Amounts parse across
    notations.

    For any amount value written in US notation, quoted European notation with a
    period thousands separator, or European notation without a thousands
    separator, ``parse_airbnb_amount`` returns the corresponding numeric value.

    Validates: Requirements 4.1, 4.2, 4.3
    """

    @settings(max_examples=200)
    @given(case=_amount_in_any_notation)
    def test_amount_parses_to_expected_value_in_any_notation(self, case):
        rendered, expected = case
        assert abs(parse_airbnb_amount(rendered) - expected) < TOLERANCE

    @settings(max_examples=200)
    @given(case=_us_notation())
    def test_us_notation_parses_to_expected_value(self, case):
        """Req 4.1: period-decimal notation (e.g. ``274.80``)."""
        rendered, expected = case
        assert abs(parse_airbnb_amount(rendered) - expected) < TOLERANCE

    @settings(max_examples=200)
    @given(case=_european_with_thousands())
    def test_european_with_thousands_parses_to_expected_value(self, case):
        """Req 4.2: comma decimal with a period thousands separator
        (e.g. ``"1.234,56"``)."""
        rendered, expected = case
        assert abs(parse_airbnb_amount(rendered) - expected) < TOLERANCE

    @settings(max_examples=200)
    @given(case=_european_no_thousands())
    def test_european_no_thousands_parses_to_expected_value(self, case):
        """Req 4.3: comma decimal without a thousands separator
        (e.g. ``"42,59"``)."""
        rendered, expected = case
        assert abs(parse_airbnb_amount(rendered) - expected) < TOLERANCE


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
