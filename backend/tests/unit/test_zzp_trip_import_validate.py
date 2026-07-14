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

    def test_invalid_purpose_is_warning(self, service_with_params):
        """Invalid purpose triggers a warning (not error)."""
        rows = [make_valid_row(trip_category="Zakelijk", trip_purpose="Onbekend")]
        result = service_with_params.validate_import("tenant1", 1, rows)

        assert result["rows"][0]["_status"] == "warning"
        assert any("doel" in msg.lower() for msg in result["rows"][0]["_messages"])

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
