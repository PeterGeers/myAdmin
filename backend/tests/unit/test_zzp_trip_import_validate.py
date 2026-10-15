"""
Unit tests for TripImportService.validate_import method.

Tests validation logic: required fields, date formats, odometer checks,
continuity (internal and DB), duplicate detection, and category/purpose warnings.
"""
import pytest
from unittest.mock import MagicMock, patch

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.zzp_trip_import_service import TripImportService


@pytest.fixture
def mock_db():
    """Create a mock database that returns no existing trips by default."""
    db = MagicMock()
    db.execute_query.return_value = []
    return db


@pytest.fixture
def service(mock_db):
    """Create TripImportService with a mock database and no parameter_service."""
    return TripImportService(db=mock_db)


@pytest.fixture
def service_with_params(mock_db):
    """Create TripImportService with mock parameter_service for category/purpose validation."""
    param_service = MagicMock()
    param_service.get_param.side_effect = lambda ns, key, tenant=None: {
        "trip_categories": ["Zakelijk", "Privé", "Woon-werk"],
        "trip_purposes": ["Klantbezoek", "Vergadering", "Overig"],
    }.get(key)
    return TripImportService(db=mock_db, parameter_service=param_service)


def make_valid_row(**overrides):
    """Helper to create a valid row dict with sensible defaults."""
    row = {
        "trip_date": "2026-01-15",
        "start_address": "Amsterdam",
        "end_address": "Utrecht",
        "start_odometer": 45000,
        "end_odometer": 45050,
        "trip_category": "Zakelijk",
        "trip_purpose": "Klantbezoek",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Tests: Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """Tests for empty row list."""

    def test_empty_rows_returns_success(self, service):
        """Empty row list returns success with zero counts."""
        result = service.validate_import("tenant1", 1, [])

        assert result["success"] is True
        assert result["total_rows"] == 0
        assert result["valid"] == 0
        assert result["warnings"] == 0
        assert result["errors"] == 0
        assert result["rows"] == []
        assert result["preview"] == []


# ---------------------------------------------------------------------------
# Tests: Required fields validation
# ---------------------------------------------------------------------------

class TestRequiredFields:
    """Tests for required field validation."""

    def test_all_required_fields_present(self, service):
        """Row with all required fields passes validation."""
        rows = [make_valid_row()]
        result = service.validate_import("tenant1", 1, rows)

        assert result["valid"] == 1
        assert result["errors"] == 0
        assert result["rows"][0]["_status"] == "ok"

    def test_missing_trip_date(self, service):
        """Missing trip_date is an error."""
        rows = [make_valid_row(trip_date=None)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        assert result["rows"][0]["_status"] == "error"
        assert any("trip_date" in msg for msg in result["rows"][0]["_messages"])

    def test_missing_start_address(self, service):
        """Missing start_address is an error."""
        rows = [make_valid_row(start_address=None)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        assert result["rows"][0]["_status"] == "error"

    def test_missing_multiple_fields(self, service):
        """Multiple missing fields all generate error messages."""
        rows = [make_valid_row(trip_date=None, start_address=None, trip_category=None)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        messages = result["rows"][0]["_messages"]
        assert len(messages) >= 3

    def test_empty_string_field_is_error(self, service):
        """Empty string value for required field is an error."""
        rows = [make_valid_row(trip_purpose="")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        assert any("trip_purpose" in msg for msg in result["rows"][0]["_messages"])


# ---------------------------------------------------------------------------
# Tests: Date format validation
# ---------------------------------------------------------------------------

class TestDateValidation:
    """Tests for date format validation and normalization."""

    def test_iso_format_accepted(self, service):
        """YYYY-MM-DD format is accepted."""
        rows = [make_valid_row(trip_date="2026-03-15")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"
        assert result["rows"][0]["trip_date"] == "2026-03-15"

    def test_dutch_dash_format_normalized(self, service):
        """DD-MM-YYYY is accepted and normalized to YYYY-MM-DD."""
        rows = [make_valid_row(trip_date="15-03-2026")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"
        assert result["rows"][0]["trip_date"] == "2026-03-15"

    def test_dutch_slash_format_normalized(self, service):
        """DD/MM/YYYY is accepted and normalized to YYYY-MM-DD."""
        rows = [make_valid_row(trip_date="15/03/2026")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"
        assert result["rows"][0]["trip_date"] == "2026-03-15"

    def test_invalid_date_format_is_error(self, service):
        """Invalid date format triggers an error."""
        rows = [make_valid_row(trip_date="March 15, 2026")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        assert any("datumformaat" in msg.lower() for msg in result["rows"][0]["_messages"])

    def test_invalid_month_is_error(self, service):
        """Date with month > 12 is an error."""
        rows = [make_valid_row(trip_date="2026-13-01")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1


# ---------------------------------------------------------------------------
# Tests: Odometer validation
# ---------------------------------------------------------------------------

class TestOdometerValidation:
    """Tests for odometer value validation."""

    def test_valid_odometer(self, service):
        """end_odometer > start_odometer passes."""
        rows = [make_valid_row(start_odometer=45000, end_odometer=45050)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"

    def test_end_less_than_start_is_error(self, service):
        """end_odometer < start_odometer is an error."""
        rows = [make_valid_row(start_odometer=45050, end_odometer=45000)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        assert any("km-stand" in msg.lower() for msg in result["rows"][0]["_messages"])

    def test_end_equals_start_is_error(self, service):
        """end_odometer == start_odometer is an error."""
        rows = [make_valid_row(start_odometer=45000, end_odometer=45000)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1

    def test_non_numeric_odometer_is_error(self, service):
        """Non-numeric odometer value is an error."""
        rows = [make_valid_row(start_odometer="abc", end_odometer=45050)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["errors"] == 1
        assert any("geen getal" in msg for msg in result["rows"][0]["_messages"])


# ---------------------------------------------------------------------------
# Tests: Internal odometer continuity
# ---------------------------------------------------------------------------

class TestInternalContinuity:
    """Tests for odometer continuity within the import set."""

    def test_continuous_odometers_no_warning(self, service):
        """Continuous odometer readings produce no warnings."""
        rows = [
            make_valid_row(trip_date="2026-01-01", start_odometer=45000, end_odometer=45050),
            make_valid_row(trip_date="2026-01-02", start_odometer=45050, end_odometer=45100),
            make_valid_row(trip_date="2026-01-03", start_odometer=45100, end_odometer=45150),
        ]
        result = service.validate_import("tenant1", 1, rows)

        assert result["warnings"] == 0
        assert all(r["_status"] == "ok" for r in result["rows"])

    def test_gap_in_odometer_is_warning(self, service):
        """Gap between consecutive row odometers triggers a warning."""
        rows = [
            make_valid_row(trip_date="2026-01-01", start_odometer=45000, end_odometer=45050),
            make_valid_row(trip_date="2026-01-02", start_odometer=45060, end_odometer=45100),
        ]
        result = service.validate_import("tenant1", 1, rows)

        # Second row should have warning
        assert result["rows"][1]["_status"] == "warning"
        assert any("aansluitend" in msg.lower() for msg in result["rows"][1]["_messages"])

    def test_rows_sorted_by_date_before_continuity_check(self, service):
        """Rows are sorted by date before continuity check."""
        rows = [
            make_valid_row(trip_date="2026-01-03", start_odometer=45100, end_odometer=45150),
            make_valid_row(trip_date="2026-01-01", start_odometer=45000, end_odometer=45050),
            make_valid_row(trip_date="2026-01-02", start_odometer=45050, end_odometer=45100),
        ]
        result = service.validate_import("tenant1", 1, rows)

        # After sorting by date, continuity should be OK
        assert result["warnings"] == 0
        assert all(r["_status"] == "ok" for r in result["rows"])


# ---------------------------------------------------------------------------
# Tests: DB continuity
# ---------------------------------------------------------------------------

class TestDBContinuity:
    """Tests for odometer continuity against existing DB trips."""

    def test_matches_db_no_warning(self, mock_db):
        """First row matching last DB trip's end_odometer: no warning."""
        mock_db.execute_query.return_value = [
            {"trip_date": "2026-01-10", "start_odometer": 44950, "end_odometer": 45000}
        ]
        service = TripImportService(db=mock_db)

        rows = [make_valid_row(trip_date="2026-01-11", start_odometer=45000, end_odometer=45050)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["warnings"] == 0
        assert result["rows"][0]["_status"] == "ok"

    def test_gap_from_db_is_warning(self, mock_db):
        """Gap between last DB trip and first import row triggers warning."""
        mock_db.execute_query.return_value = [
            {"trip_date": "2026-01-10", "start_odometer": 44950, "end_odometer": 45000}
        ]
        service = TripImportService(db=mock_db)

        rows = [make_valid_row(trip_date="2026-01-11", start_odometer=45020, end_odometer=45050)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "warning"
        assert any("bestaande ritten" in msg.lower() for msg in result["rows"][0]["_messages"])

    def test_no_existing_trips_no_db_warning(self, service):
        """When no existing trips in DB, no DB continuity warning."""
        rows = [make_valid_row(start_odometer=1000, end_odometer=1050)]
        result = service.validate_import("tenant1", 1, rows)

        # No DB-related messages
        assert not any("bestaande ritten" in msg.lower() for r in result["rows"] for msg in r["_messages"])


# ---------------------------------------------------------------------------
# Tests: Duplicate detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    """Tests for duplicate trip detection."""

    def test_duplicate_detected_as_warning(self, mock_db):
        """Row matching existing trip (date + odometers) gets a warning."""
        from datetime import date
        mock_db.execute_query.return_value = [
            {"trip_date": date(2026, 1, 15), "start_odometer": 45000, "end_odometer": 45050}
        ]
        service = TripImportService(db=mock_db)

        rows = [make_valid_row(trip_date="2026-01-15", start_odometer=45000, end_odometer=45050)]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "warning"
        assert any("duplicaat" in msg.lower() for msg in result["rows"][0]["_messages"])

    def test_non_duplicate_no_warning(self, mock_db):
        """Row not matching any existing trip: no duplicate warning."""
        mock_db.execute_query.return_value = [
            {"trip_date": "2026-01-14", "start_odometer": 44950, "end_odometer": 45000}
        ]
        service = TripImportService(db=mock_db)

        rows = [make_valid_row(trip_date="2026-01-15", start_odometer=45000, end_odometer=45050)]
        result = service.validate_import("tenant1", 1, rows)

        assert not any("duplicaat" in msg.lower() for r in result["rows"] for msg in r["_messages"])


# ---------------------------------------------------------------------------
# Tests: Category/purpose validation
# ---------------------------------------------------------------------------

class TestCategoryPurposeValidation:
    """Tests for category and purpose validation against parameter lists."""

    def test_valid_category_no_warning(self, service_with_params):
        """Valid category from parameter list: no warning."""
        rows = [make_valid_row(trip_category="Zakelijk", trip_purpose="Klantbezoek")]
        result = service_with_params.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"

    def test_invalid_category_is_warning(self, service_with_params):
        """Invalid category triggers a warning (not error)."""
        rows = [make_valid_row(trip_category="Onbekend", trip_purpose="Klantbezoek")]
        result = service_with_params.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "warning"
        assert any("categorie" in msg.lower() for msg in result["rows"][0]["_messages"])

    def test_free_text_purpose_no_warning(self, service_with_params):
        """trip_purpose is free-text (business-owned): an unknown purpose is
        accepted on import with NO warning (only trip_category is checked). This
        matches the create path, which no longer validates purpose against an
        allow-list."""
        rows = [make_valid_row(trip_category="Zakelijk", trip_purpose="Onbekend")]
        result = service_with_params.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"
        assert not any("doel" in msg.lower() for msg in result["rows"][0]["_messages"])

    def test_no_param_service_no_category_warning(self, service):
        """Without parameter_service, no category/purpose warnings."""
        rows = [make_valid_row(trip_category="Anything", trip_purpose="Whatever")]
        result = service.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "ok"


# ---------------------------------------------------------------------------
# Tests: Return format
# ---------------------------------------------------------------------------

class TestReturnFormat:
    """Tests for the correct return format structure."""

    def test_return_structure(self, service):
        """validate_import returns all expected keys."""
        rows = [make_valid_row()]
        result = service.validate_import("tenant1", 1, rows)

        assert "success" in result
        assert "total_rows" in result
        assert "valid" in result
        assert "warnings" in result
        assert "errors" in result
        assert "rows" in result
        assert "preview" in result

    def test_row_has_status_and_messages(self, service):
        """Each row has _status, _messages, and _row_number fields."""
        rows = [make_valid_row()]
        result = service.validate_import("tenant1", 1, rows)

        row = result["rows"][0]
        assert "_status" in row
        assert "_messages" in row
        assert "_row_number" in row
        assert isinstance(row["_messages"], list)
        assert row["_row_number"] == 1

    def test_preview_limited_to_20_rows(self, service):
        """Preview contains at most 20 rows."""
        rows = [make_valid_row(
            trip_date=f"2026-01-{(i % 28) + 1:02d}",
            start_odometer=45000 + i * 50,
            end_odometer=45000 + (i + 1) * 50,
        ) for i in range(30)]
        result = service.validate_import("tenant1", 1, rows)

        assert len(result["preview"]) == 20
        assert result["total_rows"] == 30

    def test_counts_correct(self, service_with_params):
        """Counts (valid, warnings, errors) match row statuses."""
        rows = [
            make_valid_row(trip_date="2026-01-01", start_odometer=45000, end_odometer=45050),
            make_valid_row(trip_date="2026-01-02", start_odometer=45050, end_odometer=45100, trip_category="Onbekend"),
            make_valid_row(trip_date="2026-01-03", start_odometer=45100, end_odometer=45050),  # error: end < start
        ]
        result = service_with_params.validate_import("tenant1", 1, rows)

        assert result["valid"] == 1
        assert result["warnings"] == 1
        assert result["errors"] == 1
        assert result["total_rows"] == 3


# ---------------------------------------------------------------------------
# Tests: Database error handling
# ---------------------------------------------------------------------------

class TestDatabaseErrorHandling:
    """Tests for graceful handling of database errors."""

    def test_db_error_does_not_crash(self):
        """DatabaseError during fetch is caught gracefully."""
        from db_exceptions import DatabaseError

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = DatabaseError("Connection failed")
        service = TripImportService(db=mock_db)

        rows = [make_valid_row()]
        result = service.validate_import("tenant1", 1, rows)

        # Should still succeed with validation (just no DB checks)
        assert result["success"] is True
        assert result["total_rows"] == 1

# ---------------------------------------------------------------------------
# Tests: _normalize_date (surface b — non-padded numeric dates)
# ---------------------------------------------------------------------------

class TestNormalizeDate:
    """Direct tests for TripImportService._normalize_date (static method, no DB).

    Property 1 (Bug Condition) — Non-Padded Numeric Dates Rejected.

    These are FIX tests: each case asserts the post-fix expected zero-padded
    YYYY-MM-DD output. On UNFIXED code every branch of _normalize_date is guarded
    by `len(date_str) == 10` with separators at fixed positions, so a valid
    non-zero-padded numeric Dutch/ISO date (8-9 chars, or "2026-5-5") fails every
    branch and the method returns None — so these assertions FAIL, which confirms
    the bug exists. After the surface-(b) fix (task 3) the same assertions pass.

    Scoped-PBT approach: the accepted date set is small and fully enumerated in the
    design's Fix Checking table, so each table row is one explicit assertion for
    reproducibility rather than randomized generation.

    Validates: Requirements 5.1, 5.2, 5.3
    """

    # (input, expected normalized output) — the design Fix Checking table rows.
    # Hyphen-separated non-padded Dutch dates (D-M-YYYY family) — Requirement 5.1
    NON_PADDED_DASH_CASES = [
        ("5-5-2026", "2026-05-05"),
        ("3-6-2026", "2026-06-03"),
        ("17-5-2026", "2026-05-17"),
        ("5-12-2026", "2026-12-05"),
    ]

    # Slash-separated non-padded Dutch dates (D/M/YYYY family) — Requirement 5.2
    NON_PADDED_SLASH_CASES = [
        ("5/5/2026", "2026-05-05"),
        ("3/6/2026", "2026-06-03"),
        ("17/5/2026", "2026-05-17"),
    ]

    # Non-padded ISO date (YYYY-M-D) — Requirement 5.3
    NON_PADDED_ISO_CASES = [
        ("2026-5-5", "2026-05-05"),
    ]

    @pytest.mark.parametrize("date_str,expected", NON_PADDED_DASH_CASES)
    def test_normalize_date_non_padded_dash_normalizes_to_iso(self, date_str, expected):
        """Non-zero-padded hyphen Dutch date normalizes to zero-padded YYYY-MM-DD.

        Validates: Requirements 5.1
        """
        result = TripImportService._normalize_date(date_str)
        assert result == expected

    @pytest.mark.parametrize("date_str,expected", NON_PADDED_SLASH_CASES)
    def test_normalize_date_non_padded_slash_normalizes_to_iso(self, date_str, expected):
        """Non-zero-padded slash Dutch date normalizes to zero-padded YYYY-MM-DD.

        Validates: Requirements 5.2
        """
        result = TripImportService._normalize_date(date_str)
        assert result == expected

    @pytest.mark.parametrize("date_str,expected", NON_PADDED_ISO_CASES)
    def test_normalize_date_non_padded_iso_normalizes_to_iso(self, date_str, expected):
        """Non-zero-padded ISO date (YYYY-M-D) normalizes to zero-padded YYYY-MM-DD.

        Validates: Requirements 5.3
        """
        result = TripImportService._normalize_date(date_str)
        assert result == expected

    @pytest.mark.parametrize(
        "date_str,expected",
        NON_PADDED_DASH_CASES + NON_PADDED_SLASH_CASES + NON_PADDED_ISO_CASES,
    )
    def test_normalize_date_non_padded_matches_iso_pattern(self, date_str, expected):
        """Every normalized non-padded result matches /^\\d{4}-\\d{2}-\\d{2}$/.

        Validates: Requirements 5.1, 5.2, 5.3
        """
        import re

        result = TripImportService._normalize_date(date_str)
        assert result is not None
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)

    # -----------------------------------------------------------------------
    # Property 2 (Preservation) — Already-Valid Dates Unchanged,
    #                             Invalid Dates Still Rejected.
    #
    # Observation-first methodology: each case below was run against the
    # UNFIXED _normalize_date and the OBSERVED output recorded as the expected
    # value, so these assertions PASS on unfixed code (confirming the baseline
    # behavior to preserve) and must continue to pass after the surface-(b) fix.
    #
    #   Observed on unfixed code:
    #     "05-05-2026" -> "2026-05-05"   "15-01-2026" -> "2026-01-15"
    #     "2026-05-05" -> "2026-05-05"   "05/05/2026" -> "2026-05-05"
    #     "5-5" -> None       "2026" -> None        "5-mei" -> None
    #     "5-mei-2026" -> None           "32-5-2026" -> None
    #     "5-13-2026" -> None            "0-5-2026" -> None
    #     "5-5-1899" -> None             "" -> None            None -> None
    #
    # Validates: Requirements 6.1, 6.2, 6.3, 6.4
    # -----------------------------------------------------------------------

    # Already-zero-padded / ISO inputs — normalize to the identical result
    # (Requirement 6.4). Observed output recorded as expected.
    PRESERVED_VALID_CASES = [
        ("05-05-2026", "2026-05-05"),
        ("15-01-2026", "2026-01-15"),
        ("2026-05-05", "2026-05-05"),
        ("05/05/2026", "2026-05-05"),
    ]

    # Truly-invalid inputs — still rejected (observed output: None).
    # Requirements 6.1 (missing year), 6.2 (non-numeric), 6.3 (out-of-range);
    # plus empty / non-string guards. Each is annotated with why it is rejected.
    REJECTED_INVALID_CASES = [
        ("5-5", "missing year / 2 parts"),            # Req 6.1
        ("2026", "missing parts"),                    # Req 6.1
        ("5-mei", "non-numeric component"),           # Req 6.2
        ("5-mei-2026", "non-numeric component"),      # Req 6.2
        ("32-5-2026", "day out of range"),            # Req 6.3
        ("5-13-2026", "month out of range"),          # Req 6.3
        ("0-5-2026", "day out of range"),             # Req 6.3
        ("5-5-1899", "year < 1900"),                  # Req 6.3
        ("", "empty string"),                         # guard
    ]

    @pytest.mark.parametrize("date_str,expected", PRESERVED_VALID_CASES)
    def test_normalize_date_already_valid_returns_identical_iso(self, date_str, expected):
        """Already zero-padded / ISO date normalizes to the identical YYYY-MM-DD.

        Observation-first: expected value is the OBSERVED unfixed output, so this
        passes on unfixed code and must stay stable after the fix.

        Validates: Requirements 6.4
        """
        result = TripImportService._normalize_date(date_str)
        assert result == expected

    @pytest.mark.parametrize(
        "date_str,reason",
        REJECTED_INVALID_CASES,
        ids=[f"{d!r}-{r}" for d, r in REJECTED_INVALID_CASES],
    )
    def test_normalize_date_invalid_string_still_rejected_returns_none(self, date_str, reason):
        """Truly-invalid date string is still rejected (returns None).

        Observation-first: unfixed code returns None for each of these; the fix
        must keep rejecting them.

        Validates: Requirements 6.1, 6.2, 6.3
        """
        result = TripImportService._normalize_date(date_str)
        assert result is None, f"expected None for {date_str!r} ({reason})"

    def test_normalize_date_none_input_still_rejected_returns_none(self):
        """Non-string (None) input is still rejected (returns None).

        Observation-first: unfixed code returns None for a non-string value.

        Validates: Requirements 6.2
        """
        result = TripImportService._normalize_date(None)
        assert result is None

# ---------------------------------------------------------------------------
# Tests: validate_import end-to-end with non-padded dates (surface b)
# ---------------------------------------------------------------------------

class TestValidateImportNonPaddedDates:
    """End-to-end validate_import test with non-zero-padded numeric dates.

    Requirement 5.4 — WHEN every row in an otherwise valid import carries a
    non-zero-padded numeric date THEN the system SHALL report the correct
    `valid` count and a populated preview.

    Requirement 6.5 — rows that pass date validation SHALL CONTINUE to apply
    the existing required-field, odometer-continuity, duplicate-detection, and
    category/purpose-warning validation unchanged.

    The rows below are continuity-respecting (odometers chain, dates are in
    chronological order after normalization) and the only non-standard trait is
    the non-zero-padded `trip_date` values, so with the no-existing-trips
    `mock_db` and no parameter_service there are no warnings or errors — every
    row is `ok`. On UNFIXED code the parser rejects every non-padded date, so
    this would be an all-error preview; it passes only after the surface-(b)
    fix.
    """

    def test_validate_import_non_padded_dates_all_valid(self, service):
        """Non-padded dates across a continuity-respecting import all validate ok.

        Validates: Requirements 5.4, 6.5
        """
        import re

        rows = [
            make_valid_row(trip_date="5-5-2026", start_odometer=45000, end_odometer=45050),
            make_valid_row(trip_date="6-5-2026", start_odometer=45050, end_odometer=45100),
            make_valid_row(trip_date="17-5-2026", start_odometer=45100, end_odometer=45150),
        ]
        result = service.validate_import("tenant1", 1, rows)

        # Correct counts: every row valid, no warnings, no errors.
        assert result["valid"] == len(rows)
        assert result["warnings"] == 0
        assert result["errors"] == 0
        assert result["total_rows"] == len(rows)

        # Populated preview.
        assert len(result["preview"]) == len(rows)

        # Every row is ok and its normalized trip_date is zero-padded ISO.
        for row in result["rows"]:
            assert row["_status"] == "ok"
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", row["trip_date"])

        # Spot-check the exact normalized values (date order preserved).
        normalized_dates = [row["trip_date"] for row in result["rows"]]
        assert normalized_dates == ["2026-05-05", "2026-05-06", "2026-05-17"]

# ---------------------------------------------------------------------------
# Property-based tests: date validation unchanged (rittenregistratie redesign)
#
# Feature: rittenregistratie-tax-log-redesign
# Properties 13-16 — confirm _normalize_date / validate_import reject yearless
# and non-numeric-month dates without inference, name the offending value in a
# bounded message, retain rejected rows in the preview, and accept the
# documented formats (normalizing to ISO). No code change is required: these
# tests pin the existing behavior per Req 8.1-8.5 and the change-with-tests
# contract (Req 10.7).
# ---------------------------------------------------------------------------

import datetime as _dt
import re as _re

from hypothesis import given, strategies as st, settings


# -- Strategies ------------------------------------------------------------

# Yearless Dutch dates: "D-mnd" / "DD-mnd" (no 4-digit year, Dutch month name).
_DUTCH_MONTHS = ["jan", "feb", "mrt", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

_yearless_date_st = st.builds(
    lambda d, m: f"{d}-{m}",
    st.integers(min_value=1, max_value=31),
    st.sampled_from(_DUTCH_MONTHS),
)

# Bare non-numeric month tokens: "mei", "jan", "dec" (no day, no year).
_non_numeric_month_st = st.sampled_from(_DUTCH_MONTHS)

# A valid (year, month, day) triple within the parser's accepted ranges.
_valid_ymd_st = st.builds(
    lambda y, m, d: (y, m, d),
    st.integers(min_value=1900, max_value=2099),
    st.integers(min_value=1, max_value=12),
    st.integers(min_value=1, max_value=28),  # <=28 avoids month-length edge noise
)


def _invalid_date_row(trip_date):
    """A row that is valid except for the (bad) trip_date, so the only error is the date."""
    return make_valid_row(trip_date=trip_date)


def _service_no_existing_trips():
    """A TripImportService whose DB reports no existing trips (stateless mock).

    Built fresh inside each test body so it is safe to use under Hypothesis
    @given (no function-scoped fixture shared across generated inputs).
    """
    db = MagicMock()
    db.execute_query.return_value = []
    return TripImportService(db=db)


@pytest.mark.unit
class TestDatePropertiesRedesign:
    """Hypothesis properties 13-16 for date validation (Req 8.1-8.5, 10.7)."""

    # Feature: rittenregistratie-tax-log-redesign, Property 13: Invalid dates rejected without inference
    @settings(max_examples=150)
    @given(bad_date=st.one_of(_yearless_date_st, _non_numeric_month_st))
    def test_property_13_invalid_dates_rejected_without_inference(self, bad_date):
        """Yearless or non-numeric-month dates are rejected; no year is inferred.

        Validates: Requirements 8.1, 8.2
        """
        service = _service_no_existing_trips()

        # Direct parser: never returns a normalized value (no inference).
        assert service._normalize_date(bad_date) is None

        # End-to-end: the row is an error and its date is NOT silently normalized
        # to any YYYY-MM-DD value (no year substituted in).
        result = service.validate_import("tenant1", 1, [_invalid_date_row(bad_date)])
        row = result["rows"][0]
        assert row["_status"] == "error"
        assert row["trip_date"] == bad_date  # untouched: no inferred year
        assert not _re.match(r"^\d{4}-\d{2}-\d{2}$", str(row["trip_date"]))

    # Feature: rittenregistratie-tax-log-redesign, Property 14: Rejected-date message names the value and is bounded
    @settings(max_examples=150)
    @given(bad_date=st.one_of(_yearless_date_st, _non_numeric_month_st))
    def test_property_14_rejected_date_message_names_value_and_bounded(self, bad_date):
        """The per-row date error names the exact value + expected format, <= 500 chars.

        Validates: Requirements 8.3
        """
        service = _service_no_existing_trips()
        result = service.validate_import("tenant1", 1, [_invalid_date_row(bad_date)])
        row = result["rows"][0]

        date_msgs = [m for m in row["_messages"] if "datumformaat" in m.lower()]
        assert date_msgs, f"expected a date-format message for {bad_date!r}"
        msg = date_msgs[0]

        # Names the exact offending value and the expected formats.
        assert bad_date in msg
        assert "YYYY-MM-DD" in msg
        assert "DD-MM-YYYY" in msg
        assert "DD/MM/YYYY" in msg
        # Bounded length.
        assert len(msg) <= 500

    # Feature: rittenregistratie-tax-log-redesign, Property 15: Rejected rows retained in the preview
    @settings(max_examples=150)
    @given(
        bad_dates=st.lists(_yearless_date_st, min_size=1, max_size=8),
        n_valid=st.integers(min_value=0, max_value=8),
    )
    def test_property_15_rejected_rows_retained_in_preview(self, bad_dates, n_valid):
        """Every input row appears in the preview; invalid-date rows are marked error, never dropped.

        Validates: Requirements 8.4
        """
        service = _service_no_existing_trips()

        # Interleave invalid-date rows with some clean rows; tag each with a
        # unique marker so we can confirm presence by identity in the preview.
        # Keep total <= 20 so the whole set fits the preview window.
        rows = []
        for i, bad in enumerate(bad_dates):
            r = _invalid_date_row(bad)
            r["_marker"] = f"bad-{i}"
            rows.append(r)
        for j in range(n_valid):
            r = make_valid_row(trip_date="2026-01-15")
            r["_marker"] = f"ok-{j}"
            rows.append(r)

        total = len(rows)
        result = service.validate_import("tenant1", 1, rows)

        # Preview retains every input row (set <= 20).
        assert len(result["rows"]) == total
        assert len(result["preview"]) == total
        preview_markers = {r.get("_marker") for r in result["preview"]}
        expected_markers = {r["_marker"] for r in rows}
        assert preview_markers == expected_markers

        # Every invalid-date row is present and marked as an error (never dropped).
        bad_rows = [r for r in result["preview"] if str(r.get("_marker", "")).startswith("bad-")]
        assert len(bad_rows) == len(bad_dates)
        for r in bad_rows:
            assert r["_status"] == "error"
            assert any("datumformaat" in m.lower() for m in r["_messages"])

    # Feature: rittenregistratie-tax-log-redesign, Property 16: Accepted date formats normalize to ISO
    @settings(max_examples=150)
    @given(ymd=_valid_ymd_st, fmt=st.sampled_from(["iso", "dash", "slash", "datetime", "date"]))
    def test_property_16_accepted_formats_normalize_to_iso(self, ymd, fmt):
        """Accepted formats (ISO; DD-MM-YYYY / DD/MM/YYYY padded or not; datetime/date) normalize to ISO.

        Validates: Requirements 8.5
        """
        service = _service_no_existing_trips()
        year, month, day = ymd
        expected = f"{year:04d}-{month:02d}-{day:02d}"

        if fmt == "iso":
            value = f"{year:04d}-{month}-{day}"            # YYYY-M-D (non-padded ok)
        elif fmt == "dash":
            value = f"{day}-{month}-{year:04d}"            # D-M-YYYY (non-padded)
        elif fmt == "slash":
            value = f"{day:02d}/{month:02d}/{year:04d}"    # DD/MM/YYYY (padded)
        elif fmt == "datetime":
            value = _dt.datetime(year, month, day, 0, 0, 0)
        else:  # date
            value = _dt.date(year, month, day)

        # Direct parser normalizes to zero-padded ISO.
        assert service._normalize_date(value) == expected

        # End-to-end: the row is not rejected for date validity and carries the
        # normalized ISO date.
        result = service.validate_import("tenant1", 1, [make_valid_row(trip_date=value)])
        row = result["rows"][0]
        assert not any("datumformaat" in m.lower() for m in row["_messages"])
        assert row["trip_date"] == expected
        assert _re.match(r"^\d{4}-\d{2}-\d{2}$", row["trip_date"])
