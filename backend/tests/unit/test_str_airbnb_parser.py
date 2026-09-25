"""
Unit tests for str_airbnb_parser.py

Covers the pure parsing helpers of the new Airbnb export ingest path:
- parse_airbnb_amount() — US / European amount notation, blank/non-numeric → 0.0
- parse_airbnb_date()   — MM/DD/YYYY parsing, padding, blank/garbage → None

Requirements: 4.1–4.4, 5.1
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from datetime import datetime

import pandas as pd

from str_airbnb_parser import parse_airbnb_amount, parse_airbnb_date


class TestParseAirbnbDate:
    """parse_airbnb_date() — MM/DD/YYYY parsing with padding and failure fallback.

    Requirements: 5.1
    """

    def test_parse_airbnb_date_valid_mmddyyyy_returns_datetime(self):
        result = parse_airbnb_date("09/23/2026")
        # parse_airbnb_date returns a naive datetime by design (local-time dates).
        assert result == datetime(2026, 9, 23)  # noqa: DTZ001

    def test_parse_airbnb_date_padded_value_strips_and_parses(self):
        result = parse_airbnb_date(" 09/04/2026 ")
        assert result == datetime(2026, 9, 4)  # noqa: DTZ001

    def test_parse_airbnb_date_blank_returns_none(self):
        assert parse_airbnb_date("") is None

    def test_parse_airbnb_date_whitespace_only_returns_none(self):
        assert parse_airbnb_date("   ") is None

    def test_parse_airbnb_date_garbage_returns_none(self):
        assert parse_airbnb_date("not-a-date") is None

    def test_parse_airbnb_date_none_returns_none(self):
        assert parse_airbnb_date(None) is None

    def test_parse_airbnb_date_nan_returns_none(self):
        assert parse_airbnb_date(pd.NA) is None

    def test_parse_airbnb_date_wrong_order_ddmmyyyy_returns_none(self):
        # 23 is not a valid month, so MM/DD/YYYY parse must fail → None
        assert parse_airbnb_date("23/09/2026") is None


class TestParseAirbnbAmount:
    """parse_airbnb_amount() accepts mixed notations; blank/NaN/non-numeric → 0.0.

    Requirements: 4.1, 4.2, 4.3, 4.4
    """

    def test_parse_airbnb_amount_us_period_decimal_returns_value(self):
        # Req 4.1: period decimal separator (US notation)
        assert parse_airbnb_amount(274.80) == 274.80

    def test_parse_airbnb_amount_european_with_thousands_sep_returns_value(self):
        # Req 4.2: comma decimal + period thousands separator
        assert parse_airbnb_amount("1.234,56") == 1234.56

    def test_parse_airbnb_amount_european_no_thousands_sep_returns_value(self):
        # Req 4.3: comma decimal, no thousands separator
        assert parse_airbnb_amount("42,59") == 42.59

    def test_parse_airbnb_amount_zero_string_returns_zero(self):
        # "0.00" is US-style zero
        assert parse_airbnb_amount("0.00") == 0.0

    def test_parse_airbnb_amount_empty_string_returns_zero(self):
        # Req 4.4: blank → 0.0
        assert parse_airbnb_amount("") == 0.0

    def test_parse_airbnb_amount_nan_returns_zero(self):
        # Req 4.4: NaN (float and pandas) → 0.0
        assert parse_airbnb_amount(float("nan")) == 0.0
        assert parse_airbnb_amount(pd.NA) == 0.0

    def test_parse_airbnb_amount_non_numeric_dash_returns_zero(self):
        # Req 4.4: non-numeric placeholder → 0.0
        assert parse_airbnb_amount("—") == 0.0

    def test_parse_airbnb_amount_padded_value_returns_value(self):
        # Cells are space-padded; padding is stripped before parse
        assert parse_airbnb_amount(" 76.67 ") == 76.67


# Locate the sample the same way test_str_processor_airbnb_scan.py does:
# a path relative to this test file up to the repo-root .agent-output dir.
_SAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", ".agent-output"
)
PENDING_SAMPLE = os.path.join(_SAMPLES_DIR, "airbnb_pending.csv")


@pytest.fixture(scope="module")
def pending_bookings():
    """Parse the real pending sample once, as a Pending_File batch (status planned)."""
    from str_airbnb_parser import process_airbnb_multi

    return process_airbnb_multi([PENDING_SAMPLE], status="planned")


@pytest.fixture(scope="module")
def bookings_by_code(pending_bookings):
    return {b["reservationCode"]: b for b in pending_bookings}


class TestAnchoredExamples:
    """Anchored example tests over the real ``.agent-output/airbnb_pending.csv``.

    Parses the pending sample with ``status="planned"`` and asserts the two verified
    worked examples plus the grouping/defaults contract (design "Anchored example tests").

    Requirements: 3.5, 3.6, 2.2, 2.3, 7.1, 7.2
    """

    def test_hmxdt8waff_gross_and_channel_fee(self, bookings_by_code):
        # Req 3.5: HMXDT8WAFF -> gross 351.47 (274.80 + 76.67), fee 42.59 (42.59 + 0.00)
        booking = bookings_by_code["HMXDT8WAFF"]
        assert booking["amountGross"] == 351.47
        assert booking["amountChannelFee"] == 42.59

    def test_hmtfchfwtp_gross_and_channel_fee(self, bookings_by_code):
        # Req 3.6: HMTFCHFWTP -> gross 109.36 (85.50 + 23.86), fee 13.25 (13.25 + 0.00)
        booking = bookings_by_code["HMTFCHFWTP"]
        assert booking["amountGross"] == 109.36
        assert booking["amountChannelFee"] == 13.25

    def test_both_anchor_codes_present(self, bookings_by_code):
        assert "HMXDT8WAFF" in bookings_by_code
        assert "HMTFCHFWTP" in bookings_by_code

    @pytest.mark.parametrize("code", ["HMXDT8WAFF", "HMTFCHFWTP"])
    def test_anchor_dict_status_channel_and_defaults(self, bookings_by_code, code):
        # Pending file → status planned (Req 6.1 via status="planned"); channel airbnb;
        # guests default 2 (Req 7.1); phone empty (Req 7.2).
        booking = bookings_by_code[code]
        assert booking["status"] == "planned"
        assert booking["channel"] == "airbnb"
        assert booking["guests"] == 2
        assert booking["phone"] == ""

    def test_exactly_one_dict_per_code(self, pending_bookings):
        # Req 2.2: one Booking_Dict per confirmation code (no duplicates from the
        # paired Boeking / Doorloop totaal rows).
        codes = [b["reservationCode"] for b in pending_bookings]
        assert len(codes) == len(set(codes))

    def test_no_blank_reservation_code_payout_dropped(self, pending_bookings):
        # Req 2.3: Payout rows (blank Bevestigingscode) are excluded from grouping,
        # so no emitted dict has a blank or "nan" reservationCode.
        for booking in pending_bookings:
            code = booking["reservationCode"]
            assert code not in ("", "nan", "None")
            assert code.strip() != ""
