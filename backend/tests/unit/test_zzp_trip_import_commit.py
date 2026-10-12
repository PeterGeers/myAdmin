"""
Unit tests for TripImportService: commit_import, get_template_csv, and end-to-end flows.

Tests bulk insert (commit), CSV template generation, and integration scenarios
combining parse_file → validate_import → commit_import.
"""
import io
import pytest
from unittest.mock import MagicMock, patch, call

from hypothesis import given, strategies as st, settings, HealthCheck

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.zzp_trip_import_service import TripImportService, TEMPLATE_COLUMNS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Create a mock database that returns no existing trips by default."""
    db = MagicMock()
    db.execute_query.return_value = []
    return db


@pytest.fixture
def service(mock_db):
    """Create TripImportService with a mock database."""
    return TripImportService(db=mock_db)


@pytest.fixture
def mock_db_with_transaction():
    """Create a mock database with transaction context manager support."""
    db = MagicMock()
    db.execute_query.return_value = []
    mock_cursor = MagicMock()
    mock_cursor.lastrowid = 1
    mock_conn = MagicMock()
    # Make transaction() work as context manager
    db.transaction.return_value.__enter__ = MagicMock(return_value=(mock_cursor, mock_conn))
    db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    return db, mock_cursor, mock_conn


@pytest.fixture
def commit_service(mock_db_with_transaction):
    """Create TripImportService configured for commit_import tests."""
    db, mock_cursor, mock_conn = mock_db_with_transaction
    service = TripImportService(db=db)
    return service, mock_cursor, mock_conn


def make_import_row(**overrides):
    """Helper to create a validated import row with sensible defaults."""
    row = {
        "trip_date": "2026-01-15",
        "start_time": None,
        "end_time": None,
        "start_address": "Amsterdam",
        "end_address": "Utrecht",
        "start_odometer": 45000,
        "end_odometer": 45045,
        "trip_category": "Zakelijk",
        "trip_purpose": "Klantbezoek",
        "client_name": None,
        "project_name": None,
        "notes": "Test import",
        "_status": "ok",
        "_messages": [],
        "_row_number": 1,
    }
    row.update(overrides)
    return row


def make_csv_bytes(content: str) -> io.BytesIO:
    """Create a BytesIO stream from CSV string content."""
    return io.BytesIO(content.encode("utf-8"))


# ===========================================================================
# commit_import tests
# ===========================================================================

class TestCommitImportEmptyRows:
    """Tests for commit_import with empty input."""

    def test_empty_rows_returns_success_with_zero_imported(self, commit_service):
        """Empty rows list → success with 0 imported."""
        service, mock_cursor, _ = commit_service

        result = service.commit_import("tenant1", 1, [], "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_empty_rows_does_not_open_transaction(self, commit_service):
        """Empty rows list should not open a database transaction."""
        service, mock_cursor, _ = commit_service

        service.commit_import("tenant1", 1, [], "user@test.com")

        service.db.transaction.assert_not_called()


class TestCommitImportValidRows:
    """Tests for commit_import with valid rows."""

    def test_all_valid_rows_inserted_correct_count(self, commit_service):
        """All valid rows inserted successfully → correct imported count."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 10

        rows = [
            make_import_row(trip_date="2026-01-15", _row_number=1),
            make_import_row(trip_date="2026-01-16", _row_number=2),
            make_import_row(trip_date="2026-01-17", _row_number=3),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 3
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_insert_called_for_each_valid_row(self, commit_service):
        """cursor.execute is called twice per valid row (INSERT + audit)."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 1

        rows = [
            make_import_row(_row_number=1),
            make_import_row(_row_number=2),
        ]
        service.commit_import("tenant1", 1, rows, "user@test.com")

        # 2 rows × 2 execute calls each (insert + audit) = 4
        assert mock_cursor.execute.call_count == 4

    def test_correct_data_inserted_into_zzp_trips(self, commit_service):
        """Verify SQL params for the INSERT into zzp_trips."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 42

        row = make_import_row(
            trip_date="2026-03-10",
            start_time="08:00",
            end_time="09:30",
            start_address="Den Haag",
            end_address="Rotterdam",
            start_odometer=60000,
            end_odometer=60030,
            trip_category="Privé",
            trip_purpose="Persoonlijk",
            client_name="Acme BV",
            project_name="Project X",
            notes="Notitie",
        )
        result = service.commit_import("admin1", 7, [row], "peter@example.com")

        assert result["success"] is True
        # First execute call is the INSERT trip. Post-redesign the INSERT writes
        # 19 columns, with client_name at index 11 (replacing the removed
        # contact_id) and route_description at index 14; is_billable/is_billed/
        # invoice_id are no longer written (Req 2.7, 4.6). Positional map:
        #   0 administration, 1 vehicle_id, 2 trip_date, 3 start_time, 4 end_time,
        #   5 start_address, 6 end_address, 7 start_odometer, 8 end_odometer,
        #   9 trip_category, 10 trip_purpose, 11 client_name, 12 project_name,
        #   13 notes, 14 route_description, 15 is_gap_fill, 16 is_cancelled,
        #   17 version, 18 created_by.
        first_call = mock_cursor.execute.call_args_list[0]
        params = first_call[0][1]
        assert len(params) == 19
        assert params[0] == "admin1"          # administration
        assert params[1] == 7                 # vehicle_id
        assert params[2] == "2026-03-10"      # trip_date
        assert params[3] == "08:00"           # start_time
        assert params[4] == "09:30"           # end_time
        assert params[5] == "Den Haag"        # start_address
        assert params[6] == "Rotterdam"       # end_address
        assert params[7] == 60000             # start_odometer
        assert params[8] == 60030             # end_odometer
        assert params[9] == "Privé"           # trip_category
        assert params[10] == "Persoonlijk"    # trip_purpose
        assert params[11] == "Acme BV"       # client_name (replaces contact_id)
        assert params[12] == "Project X"     # project_name
        assert params[13] == "Notitie"       # notes
        assert params[15] is False           # is_gap_fill
        assert params[16] is False           # is_cancelled
        assert params[17] == 1              # version
        assert params[18] == "peter@example.com"  # created_by


class TestCommitImportErrorRows:
    """Tests for commit_import with error rows."""

    def test_error_rows_skipped_correct_count(self, commit_service):
        """Error rows are skipped → correct skipped count."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 1

        rows = [
            make_import_row(trip_date="2026-01-15", _status="ok", _row_number=1),
            make_import_row(trip_date="2026-01-16", _status="error", _messages=["Bad date"], _row_number=2),
            make_import_row(trip_date="2026-01-17", _status="error", _messages=["Missing field"], _row_number=3),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 1
        assert result["skipped"] == 2

    def test_all_error_rows_no_transaction(self, commit_service):
        """When all rows are errors, no transaction is opened."""
        service, mock_cursor, _ = commit_service

        rows = [
            make_import_row(_status="error", _row_number=1),
            make_import_row(_status="error", _row_number=2),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 0
        assert result["skipped"] == 2
        service.db.transaction.assert_not_called()


class TestCommitImportWarningRows:
    """Tests for commit_import with warning rows."""

    def test_warning_rows_still_imported(self, commit_service):
        """Warning rows are imported (only errors are skipped)."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 1

        rows = [
            make_import_row(_status="warning", _messages=["Possible duplicate"], _row_number=1),
            make_import_row(_status="warning", _messages=["Gap in odometer"], _row_number=2),
            make_import_row(_status="ok", _row_number=3),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 3
        assert result["skipped"] == 0

    def test_mixed_warning_and_error_only_errors_skipped(self, commit_service):
        """Mix of warning and error rows: only errors are skipped."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 1

        rows = [
            make_import_row(_status="ok", _row_number=1),
            make_import_row(_status="warning", _row_number=2),
            make_import_row(_status="error", _row_number=3),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 2
        assert result["skipped"] == 1


class TestCommitImportAuditLog:
    """Tests for audit log creation during commit."""

    def test_audit_log_entry_created_for_each_imported_trip(self, commit_service):
        """Each imported trip gets an audit log entry."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 55

        rows = [
            make_import_row(_row_number=1),
            make_import_row(_row_number=2),
        ]
        service.commit_import("tenant1", 1, rows, "user@test.com")

        # Each row: 1 INSERT + 1 audit = 2 calls per row = 4 total
        assert mock_cursor.execute.call_count == 4

        # Check audit calls (every second call)
        audit_call_1 = mock_cursor.execute.call_args_list[1]
        audit_query_1 = audit_call_1[0][0]
        audit_params_1 = audit_call_1[0][1]
        assert "zzp_trip_audit" in audit_query_1
        assert "'created'" in audit_query_1
        assert audit_params_1[0] == "tenant1"       # administration
        assert audit_params_1[1] == 55              # trip_id from lastrowid
        assert audit_params_1[2] == 1               # version
        assert audit_params_1[3] == "user@test.com"  # changed_by

    def test_audit_log_uses_correct_trip_id(self, commit_service):
        """Audit log references the correct trip_id from lastrowid."""
        service, mock_cursor, _ = commit_service
        # Simulate different lastrowid for each insert
        mock_cursor.lastrowid = 100

        rows = [make_import_row()]
        service.commit_import("tenant1", 1, rows, "admin@firm.nl")

        audit_call = mock_cursor.execute.call_args_list[1]
        audit_params = audit_call[0][1]
        assert audit_params[1] == 100  # trip_id


class TestCommitImportCreatedBy:
    """Tests for created_by propagation."""

    def test_created_by_propagated_to_insert(self, commit_service):
        """created_by value appears in the INSERT params."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 1

        rows = [make_import_row()]
        service.commit_import("tenant1", 1, rows, "admin@company.nl")

        insert_call = mock_cursor.execute.call_args_list[0]
        params = insert_call[0][1]
        assert params[18] == "admin@company.nl"

    def test_created_by_propagated_to_audit(self, commit_service):
        """created_by value appears in the audit log params."""
        service, mock_cursor, _ = commit_service
        mock_cursor.lastrowid = 1

        rows = [make_import_row()]
        service.commit_import("tenant1", 1, rows, "admin@company.nl")

        audit_call = mock_cursor.execute.call_args_list[1]
        audit_params = audit_call[0][1]
        assert audit_params[3] == "admin@company.nl"


class TestCommitImportDatabaseError:
    """Tests for database error handling during commit."""

    def test_database_error_returns_success_false(self, commit_service):
        """DatabaseError during transaction → returns success=False."""
        from db_exceptions import DatabaseError

        service, mock_cursor, _ = commit_service
        # Make transaction context raise DatabaseError
        service.db.transaction.return_value.__enter__ = MagicMock(
            side_effect=DatabaseError("Connection lost")
        )

        rows = [make_import_row()]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is False
        assert result["imported"] == 0
        assert len(result["errors"]) == 1
        assert "Database error" in result["errors"][0]

    def test_database_error_preserves_skipped_count(self, commit_service):
        """DatabaseError still reports correct skipped count for error rows."""
        from db_exceptions import DatabaseError

        service, mock_cursor, _ = commit_service
        service.db.transaction.return_value.__enter__ = MagicMock(
            side_effect=DatabaseError("Timeout")
        )

        rows = [
            make_import_row(_status="ok", _row_number=1),
            make_import_row(_status="error", _row_number=2),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is False
        assert result["skipped"] == 1  # The error row was counted as skipped


# ===========================================================================
# get_template_csv tests
# ===========================================================================

class TestGetTemplateCSV:
    """Tests for get_template_csv method."""

    def test_returns_bytes_not_empty(self, service):
        """Returns bytes, not empty."""
        result = service.get_template_csv()

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_starts_with_utf8_bom(self, service):
        """File starts with UTF-8 BOM (EF BB BF)."""
        result = service.get_template_csv()

        # UTF-8 BOM bytes
        assert result[:3] == b'\xef\xbb\xbf'

    def test_contains_all_expected_dutch_column_headers(self, service):
        """Contains all expected Dutch column headers separated by semicolons."""
        result = service.get_template_csv()
        content = result.decode("utf-8")

        # Strip BOM character
        if content.startswith("\ufeff"):
            content = content[1:]

        # First line is the header
        header_line = content.split("\n")[0]
        headers = header_line.split(";")

        expected = [
            "Datum",
            "Vertrekadres",
            "Bestemming",
            "Begin KM",
            "Eind KM",
            "Categorie",
            "Doel",
            "Klant",
            "Notities",
        ]
        assert headers == expected

    def test_contains_example_data_rows(self, service):
        """Template contains example data rows (at least 2)."""
        result = service.get_template_csv()
        content = result.decode("utf-8")

        if content.startswith("\ufeff"):
            content = content[1:]

        lines = [line for line in content.split("\n") if line.strip()]
        # First line is header, rest are data rows
        data_lines = lines[1:]
        assert len(data_lines) >= 2

    def test_uses_semicolon_as_separator(self, service):
        """Template uses semicolons as field separator."""
        result = service.get_template_csv()
        content = result.decode("utf-8")

        if content.startswith("\ufeff"):
            content = content[1:]

        lines = [line for line in content.split("\n") if line.strip()]
        # Check header has semicolons and correct number of fields
        header_fields = lines[0].split(";")
        assert len(header_fields) == 9  # 9 columns

        # Check data rows also have semicolons
        for data_line in lines[1:]:
            fields = data_line.split(";")
            assert len(fields) == 9

    def test_example_rows_have_realistic_data(self, service):
        """Example rows contain realistic Dutch data (dates, addresses, km)."""
        result = service.get_template_csv()
        content = result.decode("utf-8")

        if content.startswith("\ufeff"):
            content = content[1:]

        lines = [line for line in content.split("\n") if line.strip()]
        first_data = lines[1].split(";")

        # Should have a date-like value in first field
        assert "-" in first_data[0]
        # Should have addresses
        assert len(first_data[1]) > 0
        assert len(first_data[2]) > 0
        # Should have numeric km values
        assert first_data[3].isdigit()
        assert first_data[4].isdigit()


# ===========================================================================
# End-to-end flow tests
# ===========================================================================

class TestEndToEndFlow:
    """Integration tests combining parse_file → validate_import → commit_import."""

    def test_happy_path_parse_validate_commit(self):
        """Full happy path: parse → validate → commit with valid data."""
        # Setup: DB with transaction support
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 1
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        service = TripImportService(db=mock_db)

        # Step 1: Parse file
        csv_content = (
            "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant;Notities\n"
            "15-01-2026;Amsterdam;Utrecht;45000;45045;Zakelijk;Klantbezoek;Acme BV;Bespreking\n"
            "15-01-2026;Utrecht;Amsterdam;45045;45090;Zakelijk;Klantbezoek;Acme BV;Retour\n"
        )
        stream = io.BytesIO(csv_content.encode("utf-8"))
        parse_result = service.parse_file(stream, "import.csv")

        assert parse_result["success"] is True
        assert parse_result["total_rows"] == 2

        # Step 2: Validate
        validate_result = service.validate_import("tenant1", 1, parse_result["rows"])

        assert validate_result["success"] is True
        assert validate_result["errors"] == 0
        assert validate_result["valid"] == 2

        # Step 3: Commit
        commit_result = service.commit_import(
            "tenant1", 1, validate_result["rows"], "user@test.com"
        )

        assert commit_result["success"] is True
        assert commit_result["imported"] == 2
        assert commit_result["skipped"] == 0
        assert commit_result["errors"] == []

    def test_bad_format_error_returned_early(self):
        """parse_file with unsupported format → error returned, no further processing."""
        mock_db = MagicMock()
        service = TripImportService(db=mock_db)

        stream = io.BytesIO(b"some data")
        parse_result = service.parse_file(stream, "trips.pdf")

        assert parse_result["success"] is False
        assert "Unsupported file type" in parse_result["error"]
        assert parse_result["rows"] == []
        # Should not proceed to validate or commit
        mock_db.execute_query.assert_not_called()

    def test_mixed_valid_error_rows_commit_skips_errors(self):
        """validate_import with mixed rows → commit skips error rows only."""
        # Setup: DB with transaction support
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 1
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        service = TripImportService(db=mock_db)

        # CSV with one good row and one bad row (end_km < start_km)
        csv_content = (
            "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n"
            "15-01-2026;Amsterdam;Utrecht;45000;45045;Zakelijk;Klantbezoek\n"
            "16-01-2026;Utrecht;Den Haag;45090;45050;Zakelijk;Vergadering\n"
        )
        stream = io.BytesIO(csv_content.encode("utf-8"))

        # Parse
        parse_result = service.parse_file(stream, "mixed.csv")
        assert parse_result["success"] is True
        assert parse_result["total_rows"] == 2

        # Validate
        validate_result = service.validate_import("tenant1", 1, parse_result["rows"])
        assert validate_result["success"] is True
        assert validate_result["errors"] == 1  # Bad odometer row
        assert validate_result["valid"] == 1

        # Commit — should skip the error row
        commit_result = service.commit_import(
            "tenant1", 1, validate_result["rows"], "user@test.com"
        )

        assert commit_result["success"] is True
        assert commit_result["imported"] == 1
        assert commit_result["skipped"] == 1

    def test_template_can_be_parsed_back(self):
        """Template CSV generated by get_template_csv can be parsed by parse_file."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []
        service = TripImportService(db=mock_db)

        # Generate template
        template_bytes = service.get_template_csv()

        # Parse the template back
        stream = io.BytesIO(template_bytes)
        parse_result = service.parse_file(stream, "template.csv")

        assert parse_result["success"] is True
        assert parse_result["total_rows"] >= 2  # At least the example rows
        # All expected columns should be mapped
        assert "trip_date" in parse_result["columns_mapped"]
        assert "start_address" in parse_result["columns_mapped"]
        assert "end_address" in parse_result["columns_mapped"]
        assert "start_odometer" in parse_result["columns_mapped"]
        assert "end_odometer" in parse_result["columns_mapped"]


# ===========================================================================
# Property-based tests (Hypothesis) — rittenregistratie-tax-log-redesign
# ===========================================================================
#
# These exercise commit_import against the post-redesign model where the import
# writes a free-text client_name (Klant) and no billing columns. Each example
# builds its OWN mock DB + service (rather than a function-scoped fixture) so
# Hypothesis's function-scoped-fixture HealthCheck does not fire, and route-preset
# learning is patched out so a committed row never reaches a real RoutePresetService.
#
# INSERT positional map (19 cols): client_name is params[11].

# Column index of client_name in the commit_import INSERT (see positional map).
_CLIENT_NAME_PARAM_INDEX = 11


def _build_commit_service():
    """Build a TripImportService backed by a fresh transaction-aware mock DB.

    Returns ``(service, mock_cursor)``. The cursor records every ``execute`` call
    so a test can read the persisted INSERT params (committed client_name lives at
    ``params[_CLIENT_NAME_PARAM_INDEX]``).
    """
    db = MagicMock()
    db.execute_query.return_value = []
    mock_cursor = MagicMock()
    mock_cursor.lastrowid = 1
    mock_conn = MagicMock()
    db.transaction.return_value.__enter__ = MagicMock(return_value=(mock_cursor, mock_conn))
    db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    return TripImportService(db=db), mock_cursor


def _persisted_client_names(mock_cursor):
    """Extract the client_name value written by each INSERT into zzp_trips.

    commit_import issues two execute calls per committed row (INSERT trip + audit);
    the INSERT is the one whose query targets ``zzp_trips``. Returns the committed
    client_name values in insertion order.
    """
    values = []
    for c in mock_cursor.execute.call_args_list:
        query = c[0][0]
        params = c[0][1] if len(c[0]) > 1 else None
        if params is not None and "INSERT INTO zzp_trips" in query:
            values.append(params[_CLIENT_NAME_PARAM_INDEX])
    return values


# Klant cell values whose trimmed form is non-empty (<= 255 chars so they persist).
# Avoid NUL/control-only edge cases but allow surrounding whitespace to exercise trim.
_nonblank_klant = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), min_codepoint=0x20),
    min_size=1,
    max_size=120,
).filter(lambda s: s.strip() != "")

# Values that are empty or whitespace-only → must persist as NULL.
_blank_klant = st.sampled_from(["", " ", "   ", "\t", "  \t ", "\n", None])


class TestClientNameImportRoundTripProperty:
    """Property 4: Client_Name import round-trip (Req 2.1, 2.7)."""

    # Feature: rittenregistratie-tax-log-redesign, Property 4: committing a row
    # persists client_name equal to the trimmed input, and null for empty/blank cells.
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(value=_nonblank_klant)
    def test_property_4_nonblank_klant_persists_trimmed(self, value):
        """**Validates: Requirements 2.1, 2.7**

        A non-blank Klant cell commits a trip whose persisted client_name equals the
        input with leading/trailing whitespace stripped.
        """
        with patch("services.zzp_route_preset_service.RoutePresetService"):
            service, mock_cursor = _build_commit_service()
            row = make_import_row(client_name=value)

            result = service.commit_import("tenant1", 1, [row], "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 1
        assert result["skipped"] == 0
        persisted = _persisted_client_names(mock_cursor)
        assert persisted == [value.strip()]

    # Feature: rittenregistratie-tax-log-redesign, Property 4: committing a row
    # persists client_name equal to the trimmed input, and null for empty/blank cells.
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(value=_blank_klant)
    def test_property_4_blank_klant_persists_null(self, value):
        """**Validates: Requirements 2.1, 2.7**

        An empty or whitespace-only (or absent) Klant cell commits a trip whose
        persisted client_name is NULL.
        """
        with patch("services.zzp_route_preset_service.RoutePresetService"):
            service, mock_cursor = _build_commit_service()
            row = make_import_row(client_name=value)

            result = service.commit_import("tenant1", 1, [row], "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 1
        persisted = _persisted_client_names(mock_cursor)
        assert persisted == [None]


class TestOverLengthKlantRowRejectedProperty:
    """Property 5: Over-length Klant row rejected, others preserved (Req 2.8)."""

    # Feature: rittenregistratie-tax-log-redesign, Property 5: in a mixed batch,
    # over-length (>255) Klant rows become error rows carrying the 255-char message
    # and do not persist, while every other valid row still commits.
    @settings(max_examples=120, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        over_len=st.integers(min_value=256, max_value=600),
        n_valid_before=st.integers(min_value=0, max_value=3),
        n_valid_after=st.integers(min_value=0, max_value=3),
        valid_klant=st.one_of(st.none(), _nonblank_klant),
    )
    def test_property_5_over_length_rejected_others_commit(
        self, over_len, n_valid_before, n_valid_after, valid_klant
    ):
        """**Validates: Requirements 2.8**

        A batch mixing one over-length Klant row with otherwise-valid rows: the
        over-length row is flagged an error with the 255-char message and is NOT
        persisted; every other valid row still commits.
        """
        over_value = "x" * over_len

        valid_before = [
            make_import_row(client_name=valid_klant, _row_number=i + 1)
            for i in range(n_valid_before)
        ]
        over_row = make_import_row(
            client_name=over_value, _row_number=n_valid_before + 1
        )
        valid_after = [
            make_import_row(
                client_name=valid_klant, _row_number=n_valid_before + 2 + i
            )
            for i in range(n_valid_after)
        ]
        rows = valid_before + [over_row] + valid_after
        total_valid = n_valid_before + n_valid_after

        with patch("services.zzp_route_preset_service.RoutePresetService"):
            service, mock_cursor = _build_commit_service()
            result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        # The over-length row is skipped; every other valid row commits.
        assert result["imported"] == total_valid
        assert result["skipped"] == 1

        # The over-length row is flagged an error with a 255-char-limit message.
        assert over_row["_status"] == "error"
        assert any("255" in m for m in over_row["_messages"])

        # The over-length value is never written to the DB; only valid rows persist.
        persisted = _persisted_client_names(mock_cursor)
        assert over_value not in persisted
        assert len(persisted) == total_valid
        expected_valid = valid_klant.strip() if isinstance(valid_klant, str) else None
        assert all(v == expected_valid for v in persisted)
