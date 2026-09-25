"""Property-based test for Airbnb amount parsing of blank / non-numeric values.

Feature: airbnb-export-format-update

This file holds the Hypothesis property test for **Property 7: Blank or
non-numeric amounts are zero** (task 2.7), targeting the pure helper
``str_airbnb_parser.parse_airbnb_amount``.

It is kept in a uniquely-named file (``test_str_airbnb_parser_zero_property.py``)
so it does not collide with the sibling parser property files written by the
adjacent tasks (2.4 in ``test_str_airbnb_parser_property.py``, 2.5/2.6 amount
notations, 2.8 grouping, 2.9 dates, 2.10 contract).

``parse_airbnb_amount`` is a pure function (no DB, no mocks), so the property is
exercised against the real code path directly.
"""

import math
import os
import sys

from hypothesis import assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pandas as pd

from str_airbnb_parser import parse_airbnb_amount

# ---------------------------------------------------------------------------
# Generators for values the parser must treat as zero.
# ---------------------------------------------------------------------------

# Blank / whitespace-only cells. The parser strips spaces (and quotes/€) before
# the empty-string check, so any of these collapse to "" -> 0.0.
_blank_values = st.sampled_from(["", " ", "  ", "\t", "\n", "   \t  ", "\r\n"])

# Cells the parser recognises as "not a number" via ``pd.isna`` before any
# string handling: the float NaN and pandas' own NA sentinel.
_nan_values = st.sampled_from([float("nan"), pd.NA, None])


# Characters that can appear in a genuinely non-numeric cell. Deliberately
# EXCLUDES digits, and excludes the characters the parser strips or treats as a
# decimal/thousands separator (space, quote, €, comma, period) so that after
# stripping/normalisation the value can never accidentally become a valid float.
_non_numeric_chars = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyzABCDEFXYZ")
    + list("—–-_/\\*#@$%&!?()[]{}<>:;|~^")
    + ["£", "¥", "kr", "USD", "N/A", "n.v.t.", "tbd"]
)


@st.composite
def _non_numeric_text(draw) -> str:
    """A genuinely non-numeric string.

    We assemble it from letters and non-separator symbols, then defensively
    ``assume`` that ``float()`` on the parser-normalised form actually fails, so
    a fluke like a lone ``-`` (which ``float`` rejects anyway) or an empty draw
    can't sneak a numeric-or-blank value into this generator.
    """
    parts = draw(st.lists(_non_numeric_chars, min_size=1, max_size=6))
    text = "".join(parts)

    # Mirror the parser's own stripping so we can verify the residue is neither
    # blank nor float-parseable (it must fall through to the 0.0 fallback).
    stripped = (
        text.replace('"', "").replace("'", "").replace("€", "").replace(" ", "")
    )
    assume(stripped != "")

    normalised = stripped
    if "," in normalised:
        comma_parts = normalised.split(",")
        if len(comma_parts) == 2:
            normalised = f"{comma_parts[0].replace('.', '')}.{comma_parts[1]}"
        else:
            normalised = normalised.replace(",", ".")
    try:
        float(normalised)
        # Parseable as a number -> not a valid "non-numeric" example; drop it.
        assume(False)
    except (ValueError, TypeError):
        pass

    return text


class TestBlankOrNonNumericAmountsAreZero:
    """Feature: airbnb-export-format-update, Property 7: Blank or non-numeric
    amounts are zero.

    For any blank or non-numeric amount value, ``parse_airbnb_amount`` returns
    ``0.0``.

    Validates: Requirements 4.4
    """

    @settings(max_examples=200)
    @given(value=_blank_values)
    def test_blank_and_whitespace_values_parse_to_zero(self, value):
        result = parse_airbnb_amount(value)
        assert result == 0.0
        assert not math.isnan(result)

    @settings(max_examples=200)
    @given(value=_nan_values)
    def test_nan_and_na_values_parse_to_zero(self, value):
        result = parse_airbnb_amount(value)
        assert result == 0.0
        assert not math.isnan(result)

    @settings(max_examples=200)
    @given(value=_non_numeric_text())
    def test_non_numeric_text_parses_to_zero(self, value):
        result = parse_airbnb_amount(value)
        assert result == 0.0
        assert not math.isnan(result)


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
