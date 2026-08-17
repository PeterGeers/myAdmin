"""
Unit tests for str_direct_parser.py

Tests the Guesty CSV parser for dfDirect channel:
- _validate_headers() — header presence validation
- _parse_guesty_date() — date format parsing and validation
- _calculate_direct_row() — row filtering, financial calculation, field mapping
- process_direct_csv() — end-to-end CSV processing

Requirements: 2.1–2.6, 3.1–3.4, 4.1–4.7, 5.1–5.7, 6.1–6.5
"""

import sys
import os
import tempfile
import pytest
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_direct_parser import (
    _validate_headers,
    _parse_guesty_date,
    _calculate_direct_row,
    process_direct_csv,
    REQUIRED_COLUMNS,
)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_tax_result():
    """Standard mock return value for calculate_str_taxes."""
    return {
        "amount_vat": 10.0,
        "amount_tourist_tax": 5.0,
        "amount_nett": 100.0,
        "tax_rates_used": {"vat_rate": 21, "tourist_tax_rate": 6.9},
    }


@pytest.fixture
def col_map():
    """Standard column map (lowercase keys → actual column names)."""
    return {col.lower(): col for col in REQUIRED_COLUMNS}


@pytest.fixture
def valid_row(col_map):
    """A valid confirmed row with parseable data."""
    data = {
        "CHECK-IN": "2026-07-15 02:00 PM",
        "CHECK-OUT": "2026-07-19 10:00 AM",
        "CONFIRMATION CODE": "GY-XiBFAZHQ",
        "LISTING": "Green Studio / Green Studio (17 sqm)",
        "GUEST": "Annemie Gertzen",
        "CREATION DATE": "2026-06-13 04:14 PM",
        "NUMBER OF NIGHTS": "4",
        "NUMBER OF GUESTS": "1",
        "STATUS": "confirmed",
        "BALANCE DUE": "0",
        "TOTAL PAID": "464",
        "TOTAL PAYOUT": "464",
        "PLATFORM": "Manual",
    }
    return pd.Series(data)


# ── _validate_headers Tests ────────────────────────────────────────────────


class TestValidateHeaders:
    """Tests for _validate_headers() — Requirement 2.1, 2.6."""

    def test_all_columns_present_exact_case(self):
        """All 13 required columns present with exact case → empty list."""
        result = _validate_headers(REQUIRED_COLUMNS)
        assert result == []

    def test_all_columns_present_different_case(self):
        """All present but different case → empty list (case-insensitive)."""
        lower_cols = [col.lower() for col in REQUIRED_COLUMNS]
        result = _validate_headers(lower_cols)
        assert result == []

    def test_all_columns_present_mixed_case(self):
        """Mixed case variations → empty list."""
        mixed = ["check-in", "CHECK-OUT", "Confirmation Code", "Listing",
                 "guest", "Creation Date", "number of nights",
                 "NUMBER OF GUESTS", "Status", "Balance Due",
                 "total paid", "TOTAL PAYOUT", "Platform"]
        result = _validate_headers(mixed)
        assert result == []

    def test_all_columns_with_whitespace(self):
        """Columns with leading/trailing whitespace → empty list."""
        padded = [f"  {col}  " for col in REQUIRED_COLUMNS]
        result = _validate_headers(padded)
        assert result == []

    def test_missing_two_columns(self):
        """Missing 2 columns → returns list of 2 missing names."""
        cols = [col for col in REQUIRED_COLUMNS if col not in ("STATUS", "PLATFORM")]
        result = _validate_headers(cols)
        assert len(result) == 2
        assert "STATUS" in result
        assert "PLATFORM" in result

    def test_extra_columns_no_error(self):
        """Extra columns present → empty list (no error)."""
        cols = list(REQUIRED_COLUMNS) + ["EXTRA_COL", "ANOTHER_EXTRA"]
        result = _validate_headers(cols)
        assert result == []

    def test_empty_columns_list(self):
        """Empty column list → all 13 missing."""
        result = _validate_headers([])
        assert len(result) == 13


# ── _parse_guesty_date Tests ───────────────────────────────────────────────


class TestParseGuestyDate:
    """Tests for _parse_guesty_date() — Requirements 6.1–6.5."""

    def test_datetime_pm_format(self):
        """'2026-06-12 02:00 PM' → '2026-06-12'."""
        assert _parse_guesty_date("2026-06-12 02:00 PM") == "2026-06-12"

    def test_datetime_am_format(self):
        """'2026-06-12 10:00 AM' → '2026-06-12'."""
        assert _parse_guesty_date("2026-06-12 10:00 AM") == "2026-06-12"

    def test_date_only_format(self):
        """'2026-06-12' → '2026-06-12'."""
        assert _parse_guesty_date("2026-06-12") == "2026-06-12"

    def test_empty_string(self):
        """'' → None."""
        assert _parse_guesty_date("") is None

    def test_none_value(self):
        """None → None."""
        assert _parse_guesty_date(None) is None

    def test_invalid_string(self):
        """'invalid' → None."""
        assert _parse_guesty_date("invalid") is None

    def test_invalid_month(self):
        """'2026-13-01' (month > 12) → None."""
        assert _parse_guesty_date("2026-13-01") is None

    def test_invalid_day(self):
        """'2026-02-30' (invalid day for Feb) → None."""
        assert _parse_guesty_date("2026-02-30") is None

    def test_leap_year_valid(self):
        """'2024-02-29' (leap year) → '2024-02-29'."""
        assert _parse_guesty_date("2024-02-29") == "2024-02-29"

    def test_non_leap_year_invalid(self):
        """'2025-02-29' (non-leap year) → None."""
        assert _parse_guesty_date("2025-02-29") is None

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed before parsing."""
        assert _parse_guesty_date("  2026-06-12  ") == "2026-06-12"

    def test_nan_float(self):
        """NaN float (pandas empty cell) → None."""
        assert _parse_guesty_date(float('nan')) is None


# ── _calculate_direct_row Tests ────────────────────────────────────────────


class TestCalculateDirectRow:
    """Tests for _calculate_direct_row() — Requirements 3.1–3.4, 4.1–4.7."""

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_confirmed_row_returns_booking(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map, mock_tax_result
    ):
        """Confirmed row with valid data → returns booking dict."""
        mock_taxes.return_value = mock_tax_result

        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="2026-07-01 test.csv",
            row_number=1, tax_rate_service=None, tenant="TestTenant"
        )

        assert "_skip_reason" not in result
        assert result["channel"] == "dfDirect"
        assert result["reservationCode"] == "GY-XiBFAZHQ"
        assert result["guestName"] == "Annemie Gertzen"
        assert result["nights"] == 4
        assert result["guests"] == 1
        assert result["checkinDate"] == "2026-07-15"
        assert result["checkoutDate"] == "2026-07-19"
        assert result["reservationDate"] == "2026-06-13"
        assert result["sourceFile"] == "2026-07-01 test.csv"
        assert result["phone"] == ""

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_status_canceled_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """Status 'canceled' → skip with non_confirmed_status."""
        valid_row["STATUS"] = "canceled"
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "non_confirmed_status"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_status_empty_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """Status '' (empty) → skip with non_confirmed_status."""
        valid_row["STATUS"] = ""
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "non_confirmed_status"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_status_whitespace_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """Status '  ' (whitespace) → skip with non_confirmed_status."""
        valid_row["STATUS"] = "   "
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "non_confirmed_status"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_payout_non_numeric_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """TOTAL PAYOUT = 'abc' → skip with invalid_payout."""
        valid_row["TOTAL PAYOUT"] = "abc"
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "invalid_payout"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_payout_zero_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """TOTAL PAYOUT = '0' → skip with zero_or_negative_payout."""
        valid_row["TOTAL PAYOUT"] = "0"
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "zero_or_negative_payout"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_payout_negative_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """TOTAL PAYOUT = '-100' → skip with zero_or_negative_payout."""
        valid_row["TOTAL PAYOUT"] = "-100"
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "zero_or_negative_payout"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_zero_nights_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """NUMBER OF NIGHTS = '0' → skip with zero_nights."""
        valid_row["NUMBER OF NIGHTS"] = "0"
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "zero_nights"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_unparsable_checkin_date_skipped(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """Unparsable CHECK-IN date → skip with unparsable_date."""
        valid_row["CHECK-IN"] = "invalid-date"
        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )
        assert result == {"_skip_reason": "unparsable_date"}

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_channel_fee_4_percent(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map, mock_tax_result
    ):
        """Financial: 464 gross → channel fee 18.56 (464 * 0.04)."""
        mock_taxes.return_value = mock_tax_result
        valid_row["TOTAL PAYOUT"] = "464"

        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )

        assert result["amountGross"] == 464.0
        assert result["amountChannelFee"] == 18.56

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_channel_fee_rounding_half_up(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map, mock_tax_result
    ):
        """Rounding: 87.625 gross → channel fee 3.51 (half-up, not 3.50)."""
        mock_taxes.return_value = mock_tax_result
        # 87.625 * 0.04 = 3.505 → rounds to 3.51 with half-up
        valid_row["TOTAL PAYOUT"] = "87.625"

        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )

        # Verify half-up rounding: 87.625 * 0.04 = 3.505 → 3.51
        expected_fee = float(
            (Decimal("87.625") * Decimal("0.04")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        assert expected_fee == 3.51
        assert result["amountChannelFee"] == 3.51

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_tax_integration(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map
    ):
        """Tax values from calculate_str_taxes are used in result."""
        mock_taxes.return_value = {
            "amount_vat": 15.50,
            "amount_tourist_tax": 7.25,
            "amount_nett": 422.69,
            "tax_rates_used": {"vat_rate": 21, "tourist_tax_rate": 6.9},
        }

        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )

        assert result["amountVat"] == 15.50
        assert result["amountTouristTax"] == 7.25
        assert result["amountNett"] == 422.69

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_field_mapping_completeness(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map, mock_tax_result
    ):
        """All expected fields are present in the output dict."""
        mock_taxes.return_value = mock_tax_result

        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="2026-07-01 test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )

        expected_keys = [
            "sourceFile", "channel", "listing", "checkinDate", "checkoutDate",
            "nights", "guests", "amountGross", "amountChannelFee", "guestName",
            "phone", "reservationCode", "reservationDate", "status", "addInfo",
            "amountVat", "amountTouristTax", "amountNett", "pricePerNight",
            "year", "q", "m", "daysBeforeReservation", "country",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_add_info_format(
        self, mock_taxes, mock_normalize, mock_country, valid_row, col_map, mock_tax_result
    ):
        """addInfo contains '{confirmation_code} | {guest_name} | {listing}'."""
        mock_taxes.return_value = mock_tax_result

        result = _calculate_direct_row(
            row=valid_row, col_map=col_map, source_file="test.csv",
            row_number=1, tax_rate_service=None, tenant=None
        )

        assert "GY-XiBFAZHQ" in result["addInfo"]
        assert "Annemie Gertzen" in result["addInfo"]
        assert "Green Studio / Green Studio (17 sqm)" in result["addInfo"]


# ── process_direct_csv Tests ───────────────────────────────────────────────


class TestProcessDirectCsv:
    """Tests for process_direct_csv() — Requirements 2.1–2.6, 3.1–3.4, 5.1–5.7."""

    def _write_csv(self, tmp_path, rows, filename="test_direct.csv"):
        """Helper to write a CSV file with given rows."""
        filepath = os.path.join(tmp_path, filename)
        df = pd.DataFrame(rows)
        df.to_csv(filepath, index=False)
        return filepath

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_valid_csv_mixed_statuses(
        self, mock_taxes, mock_normalize, mock_country, tmp_path
    ):
        """Valid CSV with confirmed and canceled rows → correct counts."""
        mock_taxes.return_value = {
            "amount_vat": 10.0,
            "amount_tourist_tax": 5.0,
            "amount_nett": 100.0,
            "tax_rates_used": {"vat_rate": 21, "tourist_tax_rate": 6.9},
        }

        rows = [
            {
                "CHECK-IN": "2026-07-15 02:00 PM",
                "CHECK-OUT": "2026-07-19 10:00 AM",
                "CONFIRMATION CODE": "GY-ABC123",
                "LISTING": "Green Studio",
                "GUEST": "Guest One",
                "CREATION DATE": "2026-06-01 10:00 AM",
                "NUMBER OF NIGHTS": "4",
                "NUMBER OF GUESTS": "2",
                "STATUS": "confirmed",
                "BALANCE DUE": "0",
                "TOTAL PAID": "400",
                "TOTAL PAYOUT": "400",
                "PLATFORM": "Manual",
            },
            {
                "CHECK-IN": "2026-06-12 02:00 PM",
                "CHECK-OUT": "2026-06-14 10:00 AM",
                "CONFIRMATION CODE": "GY-CAN456",
                "LISTING": "Garden House",
                "GUEST": "Guest Two",
                "CREATION DATE": "2026-02-24 05:45 PM",
                "NUMBER OF NIGHTS": "2",
                "NUMBER OF GUESTS": "4",
                "STATUS": "canceled",
                "BALANCE DUE": "-360",
                "TOTAL PAID": "360",
                "TOTAL PAYOUT": "0",
                "PLATFORM": "Manual",
            },
        ]

        filepath = self._write_csv(tmp_path, rows)
        result = process_direct_csv(filepath, tax_rate_service=None, tenant=None)

        assert len(result["bookings"]) == 1
        assert result["bookings"][0]["reservationCode"] == "GY-ABC123"
        assert result["summary"]["total_rows"] == 2
        assert result["summary"]["processed_count"] == 1
        assert result["summary"]["skipped_count"] == 1
        assert "non_confirmed_status" in result["summary"]["skipped_reasons"]

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_status_updates_collected(
        self, mock_taxes, mock_normalize, mock_country, tmp_path
    ):
        """Non-confirmed rows with reservationCode appear in status_updates."""
        mock_taxes.return_value = {
            "amount_vat": 10.0,
            "amount_tourist_tax": 5.0,
            "amount_nett": 100.0,
            "tax_rates_used": {},
        }

        rows = [
            {
                "CHECK-IN": "2026-06-12 02:00 PM",
                "CHECK-OUT": "2026-06-14 10:00 AM",
                "CONFIRMATION CODE": "GY-CANCEL1",
                "LISTING": "Garden House",
                "GUEST": "Cancelled Guest",
                "CREATION DATE": "2026-02-01 10:00 AM",
                "NUMBER OF NIGHTS": "2",
                "NUMBER OF GUESTS": "2",
                "STATUS": "canceled",
                "BALANCE DUE": "0",
                "TOTAL PAID": "0",
                "TOTAL PAYOUT": "0",
                "PLATFORM": "Manual",
            },
        ]

        filepath = self._write_csv(tmp_path, rows)
        result = process_direct_csv(filepath, tax_rate_service=None, tenant=None)

        assert len(result["status_updates"]) == 1
        assert result["status_updates"][0]["reservationCode"] == "GY-CANCEL1"
        assert result["status_updates"][0]["status"] == "canceled"

    def test_missing_headers_raises_valueerror(self, tmp_path):
        """CSV with missing required columns → raises ValueError."""
        rows = [{"CHECK-IN": "2026-01-01", "GUEST": "Someone"}]
        filepath = self._write_csv(tmp_path, rows)

        with pytest.raises(ValueError, match="Missing required columns"):
            process_direct_csv(filepath, tax_rate_service=None, tenant=None)

    @patch("str_direct_parser.detect_country", return_value="")
    @patch("str_direct_parser.normalize_listing_name", side_effect=lambda x: x)
    @patch("str_direct_parser.calculate_str_taxes")
    def test_empty_csv_headers_only(
        self, mock_taxes, mock_normalize, mock_country, tmp_path
    ):
        """Empty CSV (headers only) → empty result with 0 counts."""
        filepath = os.path.join(tmp_path, "empty.csv")
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        df.to_csv(filepath, index=False)

        result = process_direct_csv(filepath, tax_rate_service=None, tenant=None)

        assert result["bookings"] == []
        assert result["status_updates"] == []
        assert result["summary"]["total_rows"] == 0
        assert result["summary"]["processed_count"] == 0
        assert result["summary"]["skipped_count"] == 0
