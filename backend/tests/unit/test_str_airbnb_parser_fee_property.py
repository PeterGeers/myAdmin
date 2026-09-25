"""Property-based tests for the Airbnb parser's channel-fee assembly.

Feature: airbnb-export-format-update

This file holds the Hypothesis property test for the channel fee at the
``build_booking_from_group`` level of ``str_airbnb_parser``. It lives in its own
uniquely-named file (task 2.5) so it does not collide with the sibling parser
property tests (tasks 2.4/2.6/2.7/2.9/2.10).

- Property 5: Channel fee is the sum of Servicekosten (no hardcoded factor)
  (task 2.5).

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
# Generators: amount cells in the notations parse_airbnb_amount accepts.
# Servicekosten and Bruto-inkomsten are generated independently so the fee is
# exercised across the full input space, decoupled from the gross amount.
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
def _amount_value(draw) -> str:
    """A single amount cell in one of the accepted notations, optionally
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
    one Bevestigingscode, with Servicekosten and Bruto-inkomsten each drawn in a
    varied notation, independently of each other."""
    n_rows = draw(st.integers(min_value=1, max_value=4))
    rows = []
    for i in range(n_rows):
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
                # Independently varied so the fee cannot be inferred from gross.
                "Servicekosten": draw(_amount_value()),
                "Bruto-inkomsten": draw(_amount_value()),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Property 5: Channel fee is the sum of Servicekosten (no hardcoded factor)
# ---------------------------------------------------------------------------
class TestChannelFeeIsSumOfServicekosten:
    """Feature: airbnb-export-format-update, Property 5: Channel fee is the sum
    of Servicekosten (no hardcoded factor).

    For any Booking_Group, the emitted ``amountChannelFee`` equals the sum of the
    parsed ``Servicekosten`` values across all rows in the group (accounting for
    the ``round(..., 2)`` the implementation applies), independent of the gross
    amount, and never derived from a hardcoded 15% of gross.

    Validates: Requirements 3.2, 3.4
    """

    @settings(max_examples=200)
    @given(group=_booking_group())
    def test_amount_channel_fee_equals_sum_of_parsed_servicekosten(self, group):
        booking = build_booking_from_group(
            code="HMTESTCODE",
            rows=group,
            source_file="airbnb_test.csv",
            status="planned",
            tax_rate_service=None,
            tenant="ExampleTenant",
        )

        expected = round(
            sum(parse_airbnb_amount(v) for v in group["Servicekosten"]), 2
        )

        assert booking["amountChannelFee"] == expected

    @settings(max_examples=200)
    @given(group=_booking_group())
    def test_channel_fee_decoupled_from_gross_no_hardcoded_factor(self, group):
        """The fee tracks Servicekosten, not gross: it must equal the summed
        Servicekosten even where that differs from a hardcoded 15% of gross.

        This rejects the old ``amountChannelFee = 0.15 * amountGross`` behaviour
        (Req 3.4). We only assert the decoupling on examples where 15% of gross
        actually differs from the summed fee (which is the general case, since the
        two amounts are drawn independently)."""
        booking = build_booking_from_group(
            code="HMTESTCODE",
            rows=group,
            source_file="airbnb_test.csv",
            status="planned",
            tax_rate_service=None,
            tenant="ExampleTenant",
        )

        expected_fee = round(
            sum(parse_airbnb_amount(v) for v in group["Servicekosten"]), 2
        )
        gross = round(sum(parse_airbnb_amount(v) for v in group["Bruto-inkomsten"]), 2)
        hardcoded_15pct = round(gross * 0.15, 2)

        # The emitted fee is always the summed Servicekosten.
        assert booking["amountChannelFee"] == expected_fee

        # Where the summed fee genuinely differs from 15% of gross, the emitted
        # fee follows the fee, proving no hardcoded factor is applied.
        if expected_fee != hardcoded_15pct:
            assert booking["amountChannelFee"] != hardcoded_15pct

    @settings(max_examples=200)
    @given(
        service_values=st.lists(_amount_value(), min_size=1, max_size=6),
    )
    def test_fee_independent_of_row_order(self, service_values):
        """The fee sum does not depend on the order of the rows in the group:
        summation is commutative, so a group and its reverse yield the same
        emitted ``amountChannelFee``."""
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
            "Bruto-inkomsten": "100.00",
        }
        forward = pd.DataFrame(
            [{**base_row, "Servicekosten": v} for v in service_values]
        )
        reverse = pd.DataFrame(
            [{**base_row, "Servicekosten": v} for v in reversed(service_values)]
        )

        fee_forward = build_booking_from_group(
            "HMORDERCODE", forward, "airbnb_test.csv", "planned", None, "ExampleTenant"
        )["amountChannelFee"]
        fee_reverse = build_booking_from_group(
            "HMORDERCODE", reverse, "airbnb_test.csv", "planned", None, "ExampleTenant"
        )["amountChannelFee"]

        assert fee_forward == fee_reverse


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
