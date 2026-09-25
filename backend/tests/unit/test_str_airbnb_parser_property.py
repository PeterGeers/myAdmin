"""Property-based tests for the Airbnb parser's per-group dict assembly.

Feature: airbnb-export-format-update

This file holds the Hypothesis property tests that target the pure
parsing/grouping/calculation logic of ``str_airbnb_parser`` at the
``build_booking_from_group`` level (as opposed to the amount/date helper unit
tests in ``test_str_airbnb_parser.py`` and the DB keyed-refresh properties in
``test_str_database_airbnb_property.py``).

Tasks 2.5-2.10 also write parser property tests; to keep them from colliding,
each property lives in its own uniquely-named ``Test*`` class here. This file
starts with:

- Property 4: Gross is the sum of Bruto-inkomsten (task 2.4).

``build_booking_from_group`` calls ``calculate_str_taxes`` internally; with
``tax_rate_service=None`` that uses the hardcoded-rate fallback (no DB access),
so these tests exercise the real code path without mocks.
"""

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pandas as pd

from str_airbnb_parser import build_booking_from_group, parse_airbnb_amount


# ---------------------------------------------------------------------------
# Generators: Bruto-inkomsten values in the notations parse_airbnb_amount accepts
# ---------------------------------------------------------------------------
def _us_notation(draw) -> str:
    """US notation: period decimal, no thousands separator (e.g. ``274.80``)."""
    whole = draw(st.integers(min_value=0, max_value=99999))
    cents = draw(st.integers(min_value=0, max_value=99))
    return f"{whole}.{cents:02d}"


def _european_no_thousands(draw) -> str:
    """European notation without a thousands separator (e.g. ``"42,59"``)."""
    whole = draw(st.integers(min_value=0, max_value=999))
    cents = draw(st.integers(min_value=0, max_value=99))
    return f"{whole},{cents:02d}"


def _european_with_thousands(draw) -> str:
    """Quoted European notation with a period thousands separator
    (e.g. ``"1.234,56"``)."""
    thousands = draw(st.integers(min_value=1, max_value=999))
    rest = draw(st.integers(min_value=0, max_value=999))
    cents = draw(st.integers(min_value=0, max_value=99))
    return f"{thousands}.{rest:03d},{cents:02d}"


@st.composite
def _bruto_value(draw) -> str:
    """A single Bruto-inkomsten cell in one of the accepted notations, optionally
    space-padded (as Airbnb exports are)."""
    style = draw(st.sampled_from(["us", "eu", "eu_thousands"]))
    if style == "us":
        raw = _us_notation(draw)
    elif style == "eu":
        raw = _european_no_thousands(draw)
    else:
        raw = _european_with_thousands(draw)
    # Airbnb cells arrive space-padded; the parser strips them.
    lpad = " " * draw(st.integers(min_value=0, max_value=3))
    rpad = " " * draw(st.integers(min_value=0, max_value=3))
    return f"{lpad}{raw}{rpad}"


@st.composite
def _booking_group(draw) -> pd.DataFrame:
    """A group of rows (1-4, normally the Boeking + Doorloop totaal pair) sharing
    one Bevestigingscode, each with a Bruto-inkomsten in a varied notation."""
    n_rows = draw(st.integers(min_value=1, max_value=4))
    bruto_values = [draw(_bruto_value()) for _ in range(n_rows)]
    rows = []
    for i, bruto in enumerate(bruto_values):
        rows.append(
            {
                "Type": "Boeking" if i == 0 else "Doorloop totaal",
                "Bevestigingscode": "HMTESTCODE",
                "Boekingsdatum": "08/01/2026",
                "Begindatum": "09/23/2026",
                "Einddatum": "09/25/2026",
                "Nachten": "2",
                "Gast": "Test Guest",
                "Advertentie": "Test Listing",
                "Informatie": "",
                "Servicekosten": "0.00",
                "Bruto-inkomsten": bruto,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Property 4: Gross is the sum of Bruto-inkomsten
# ---------------------------------------------------------------------------
class TestGrossIsSumOfBrutoInkomsten:
    """Feature: airbnb-export-format-update, Property 4: Gross is the sum of
    Bruto-inkomsten.

    For any Booking_Group, the emitted ``amountGross`` equals the sum of the
    parsed ``Bruto-inkomsten`` values across all rows in the group (accounting
    for the ``round(..., 2)`` the implementation applies).

    Validates: Requirements 3.1
    """

    @settings(max_examples=200)
    @given(group=_booking_group())
    def test_amount_gross_equals_sum_of_parsed_bruto_inkomsten(self, group):
        booking = build_booking_from_group(
            code="HMTESTCODE",
            rows=group,
            source_file="airbnb_test.csv",
            status="planned",
            tax_rate_service=None,
            tenant="ExampleTenant",
        )

        expected = round(
            sum(parse_airbnb_amount(v) for v in group["Bruto-inkomsten"]), 2
        )

        assert booking["amountGross"] == expected

    @settings(max_examples=200)
    @given(
        bruto_values=st.lists(_bruto_value(), min_size=1, max_size=6),
    )
    def test_gross_independent_of_row_order(self, bruto_values):
        """The gross sum does not depend on the order of the rows in the group:
        summation is commutative, so a group and its reverse yield the same
        emitted ``amountGross``."""
        base_row = {
            "Type": "Boeking",
            "Bevestigingscode": "HMORDERCODE",
            "Boekingsdatum": "08/01/2026",
            "Begindatum": "09/23/2026",
            "Einddatum": "09/25/2026",
            "Nachten": "2",
            "Gast": "Test Guest",
            "Advertentie": "Test Listing",
            "Informatie": "",
            "Servicekosten": "0.00",
        }
        forward = pd.DataFrame(
            [{**base_row, "Bruto-inkomsten": v} for v in bruto_values]
        )
        reverse = pd.DataFrame(
            [{**base_row, "Bruto-inkomsten": v} for v in reversed(bruto_values)]
        )

        gross_forward = build_booking_from_group(
            "HMORDERCODE", forward, "airbnb_test.csv", "planned", None, "ExampleTenant"
        )["amountGross"]
        gross_reverse = build_booking_from_group(
            "HMORDERCODE", reverse, "airbnb_test.csv", "planned", None, "ExampleTenant"
        )["amountGross"]

        assert gross_forward == gross_reverse


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
