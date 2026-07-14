"""
Unit tests for TripImportService.parse_file method.

Tests CSV/Excel parsing, column mapping, error handling, and data cleaning.
"""
import io
import pytest
import pandas as pd
from unittest.mock import MagicMock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.zzp_trip_import_service import (
    TripImportService,
    DEFAULT_COLUMN_MAPPING,
)


@pytest.fixture
def service():
    """Create TripImportService with a mock database."""
    mock_db = MagicMock()
    return TripImportService(db=mock_db)


# ---------------------------------------------------------------------------
# Helper functions to create test file streams
# ---------------------------------------------------------------------------

def make_csv_bytes(content: str) -> io.BytesIO:
    """Create a BytesIO stream from CSV string content."""
    return io.BytesIO(content.encode("utf-8"))


def make_xlsx_bytes(df: pd.DataFrame) -> io.BytesIO:
    """Create a BytesIO stream containing an XLSX file from a DataFrame."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Tests: CSV parsing with semicolon separator (Dutch standard)
# ---------------------------------------------------------------------------

class TestParseCSVSemicolon:
    """Tests for CSV parsing with semicolon separator."""

    def test_basic_csv_semicolon(self, service):
        """Parse a standard semicolon-separated CSV with Dutch headers."""
        csv_content = (
            "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant;Notities\n"
            "2026-01-15;Amsterdam;Utrecht;45000;45045;Zakelijk;Klantbezoek;Acme BV;Test rit\n"
            "2026-01-16;Utrecht;Amsterdam;45045;45090;Privé;Persoonlijk;;\n"
        )
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "trips.csv")

        assert result["success"] is True
        assert result["total_rows"] == 2
        assert result["error"] is None
        assert len(result["rows"]) == 2

        # Check column mapping applied
        row = result["rows"][0]
        assert row["trip_date"] == "2026-01-15"
        assert row["start_address"] == "Amsterdam"
        assert row["end_address"] == "Utrecht"
        assert row["start_odometer"] == 45000
        assert row["end_odometer"] == 45045
        assert row["trip_category"] == "Zakelijk"
        assert row["trip_purpose"] == "Klantbezoek"
        assert row["contact_name"] == "Acme BV"
        assert row["notes"] == "Test rit"

    def test_csv_mapped_columns_reported(self, service):
        """Verify columns_mapped contains the internal field names."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n2026-01-15;A;B;100;200;Zakelijk;Test\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "data.csv")

        assert result["success"] is True
        assert "trip_date" in result["columns_mapped"]
        assert "start_address" in result["columns_mapped"]
        assert "end_address" in result["columns_mapped"]
        assert "start_odometer" in result["columns_mapped"]
        assert "end_odometer" in result["columns_mapped"]
        assert "trip_category" in result["columns_mapped"]
        assert "trip_purpose" in result["columns_mapped"]


# ---------------------------------------------------------------------------
# Tests: CSV parsing with comma separator (auto-detection fallback)
# ---------------------------------------------------------------------------

class TestParseCSVComma:
    """Tests for CSV parsing with comma separator (auto-detection)."""

    def test_csv_comma_separated(self, service):
        """Parse comma-separated CSV when semicolon produces single column."""
        csv_content = (
            "Datum,Vertrekadres,Bestemming,Begin KM,Eind KM,Categorie,Doel\n"
            "2026-02-01,Den Haag,Rotterdam,50000,50030,Zakelijk,Vergadering\n"
        )
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "export.csv")

        assert result["success"] is True
        assert result["total_rows"] == 1
        row = result["rows"][0]
        assert row["trip_date"] == "2026-02-01"
        assert row["start_address"] == "Den Haag"
        assert row["end_address"] == "Rotterdam"
        assert row["start_odometer"] == 50000
        assert row["end_odometer"] == 50030


# ---------------------------------------------------------------------------
# Tests: XLSX file parsing
# ---------------------------------------------------------------------------

class TestParseXLSX:
    """Tests for Excel (.xlsx) file parsing."""

    def test_basic_xlsx(self, service):
        """Parse an XLSX file with standard Dutch headers."""
        df = pd.DataFrame({
            "Datum": ["2026-03-01", "2026-03-02"],
            "Vertrekadres": ["Eindhoven", "Tilburg"],
            "Bestemming": ["Tilburg", "Eindhoven"],
            "Begin KM": ["60000", "60050"],
            "Eind KM": ["60050", "60100"],
            "Categorie": ["Zakelijk", "Woon-werk"],
            "Doel": ["Klantbezoek", "Pendelen"],
        })
        stream = make_xlsx_bytes(df)

        result = service.parse_file(stream, "trips.xlsx")

        assert result["success"] is True
        assert result["total_rows"] == 2
        row = result["rows"][0]
        assert row["trip_date"] == "2026-03-01"
        assert row["start_address"] == "Eindhoven"
        assert row["end_address"] == "Tilburg"
        assert row["start_odometer"] == 60000
        assert row["end_odometer"] == 60050

    def test_xls_extension_accepted(self, service):
        """The .xls extension should be accepted (uses read_excel)."""
        df = pd.DataFrame({
            "Datum": ["2026-04-01"],
            "Vertrekadres": ["A"],
            "Bestemming": ["B"],
            "Begin KM": ["1000"],
            "Eind KM": ["1050"],
            "Categorie": ["Zakelijk"],
            "Doel": ["Test"],
        })
        # Create as xlsx but pass filename with .xls extension
        stream = make_xlsx_bytes(df)

        result = service.parse_file(stream, "trips.xls")

        assert result["success"] is True
        assert result["total_rows"] == 1


# ---------------------------------------------------------------------------
# Tests: Column mapping
# ---------------------------------------------------------------------------

class TestColumnMapping:
    """Tests for column mapping behavior."""

    def test_default_mapping_applied(self, service):
        """Default mapping converts Dutch headers to internal field names."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant;Notities\n2026-01-01;A;B;100;200;Zakelijk;Test;Klant1;Opmerking\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        # All default mappings should be applied
        assert "trip_date" in row
        assert "start_address" in row
        assert "end_address" in row
        assert "start_odometer" in row
        assert "end_odometer" in row
        assert "trip_category" in row
        assert "trip_purpose" in row
        assert "contact_name" in row
        assert "notes" in row

    def test_custom_mapping(self, service):
        """Custom column mapping overrides default mapping."""
        csv_content = "Date;From;To;Start;End;Type;Purpose\n2026-05-01;Amsterdam;Rotterdam;70000;70040;Business;Meeting\n"
        stream = make_csv_bytes(csv_content)

        custom_mapping = {
            "Date": "trip_date",
            "From": "start_address",
            "To": "end_address",
            "Start": "start_odometer",
            "End": "end_odometer",
            "Type": "trip_category",
            "Purpose": "trip_purpose",
        }

        result = service.parse_file(stream, "english.csv", column_mapping=custom_mapping)

        assert result["success"] is True
        row = result["rows"][0]
        assert row["trip_date"] == "2026-05-01"
        assert row["start_address"] == "Amsterdam"
        assert row["end_address"] == "Rotterdam"
        assert row["start_odometer"] == 70000
        assert row["end_odometer"] == 70040
        assert row["trip_category"] == "Business"
        assert row["trip_purpose"] == "Meeting"

    def test_unmapped_columns_reported(self, service):
        """Columns not in the mapping should appear in unmapped_columns."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;ExtraCol1;ExtraCol2\n2026-01-01;A;B;100;200;Z;T;foo;bar\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        assert "ExtraCol1" in result["unmapped_columns"]
        assert "ExtraCol2" in result["unmapped_columns"]
        assert "Datum" not in result["unmapped_columns"]

    def test_columns_found_lists_original_headers(self, service):
        """columns_found should contain the original file headers."""
        csv_content = "Datum;Vertrekadres;Bestemming;Custom\n2026-01-01;A;B;Val\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        assert "Datum" in result["columns_found"]
        assert "Vertrekadres" in result["columns_found"]
        assert "Bestemming" in result["columns_found"]
        assert "Custom" in result["columns_found"]

    def test_partial_mapping_only_maps_matched_columns(self, service):
        """When mapping only matches some columns, others remain unmapped."""
        csv_content = "Datum;Vertrekadres;Unknown\n2026-01-01;A;X\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        assert "trip_date" in result["columns_mapped"]
        assert "start_address" in result["columns_mapped"]
        assert "Unknown" in result["unmapped_columns"]


# ---------------------------------------------------------------------------
# Tests: Unsupported file type
# ---------------------------------------------------------------------------

class TestUnsupportedFileType:
    """Tests for unsupported file type handling."""

    def test_unsupported_extension_returns_error(self, service):
        """Unsupported file type (e.g., .txt) returns error."""
        stream = io.BytesIO(b"some data")

        result = service.parse_file(stream, "data.txt")

        assert result["success"] is False
        assert "Unsupported file type" in result["error"]
        assert "'.txt'" in result["error"]
        assert result["rows"] == []
        assert result["total_rows"] == 0

    def test_no_extension_returns_error(self, service):
        """File with no extension returns error."""
        stream = io.BytesIO(b"some data")

        result = service.parse_file(stream, "noextension")

        assert result["success"] is False
        assert "Unsupported file type" in result["error"]

    def test_pdf_extension_returns_error(self, service):
        """PDF file returns error."""
        stream = io.BytesIO(b"%PDF-1.4")

        result = service.parse_file(stream, "trips.pdf")

        assert result["success"] is False
        assert "Unsupported file type" in result["error"]

    def test_json_extension_returns_error(self, service):
        """JSON file returns error."""
        stream = io.BytesIO(b'{"data": []}')

        result = service.parse_file(stream, "trips.json")

        assert result["success"] is False
        assert "Unsupported file type" in result["error"]


# ---------------------------------------------------------------------------
# Tests: Empty file
# ---------------------------------------------------------------------------

class TestEmptyFile:
    """Tests for empty file handling."""

    def test_empty_csv_with_headers_only(self, service):
        """CSV with headers but no data rows returns empty rows list."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "empty.csv")

        assert result["success"] is True
        assert result["rows"] == []
        assert result["total_rows"] == 0

    def test_empty_xlsx(self, service):
        """XLSX with headers but no data rows returns empty rows list."""
        df = pd.DataFrame(columns=["Datum", "Vertrekadres", "Bestemming", "Begin KM", "Eind KM", "Categorie", "Doel"])
        stream = make_xlsx_bytes(df)

        result = service.parse_file(stream, "empty.xlsx")

        assert result["success"] is True
        assert result["rows"] == []
        assert result["total_rows"] == 0


# ---------------------------------------------------------------------------
# Tests: Malformed file
# ---------------------------------------------------------------------------

class TestMalformedFile:
    """Tests for malformed file handling."""

    def test_binary_garbage_as_csv(self, service):
        """Binary garbage data returns error."""
        stream = io.BytesIO(b"\x00\x01\x02\x03\x04\x05\x80\x81\x82")

        result = service.parse_file(stream, "bad.csv")

        # Should either parse with garbage or return error
        # The implementation catches exceptions and returns error
        assert result["success"] is False or result["total_rows"] == 0

    def test_invalid_xlsx_binary(self, service):
        """Invalid binary data with .xlsx extension returns error."""
        stream = io.BytesIO(b"This is not a valid xlsx file at all")

        result = service.parse_file(stream, "corrupted.xlsx")

        assert result["success"] is False
        assert "Could not read file" in result["error"]
        assert result["rows"] == []


# ---------------------------------------------------------------------------
# Tests: Odometer fields converted to integers
# ---------------------------------------------------------------------------

class TestOdometerConversion:
    """Tests for odometer field conversion to integers."""

    def test_odometer_string_to_int(self, service):
        """String odometer values are converted to integers."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n2026-01-01;A;B;45000;45050;Zakelijk;Test\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["start_odometer"] == 45000
        assert isinstance(row["start_odometer"], int)
        assert row["end_odometer"] == 45050
        assert isinstance(row["end_odometer"], int)

    def test_odometer_decimal_to_int(self, service):
        """Decimal odometer values (e.g. '45000.0') are converted to int."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n2026-01-01;A;B;45000.0;45050.0;Zakelijk;Test\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["start_odometer"] == 45000
        assert isinstance(row["start_odometer"], int)
        assert row["end_odometer"] == 45050
        assert isinstance(row["end_odometer"], int)

    def test_odometer_non_numeric_stays_string(self, service):
        """Non-numeric odometer values remain as strings."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n2026-01-01;A;B;abc;xyz;Zakelijk;Test\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["start_odometer"] == "abc"
        assert row["end_odometer"] == "xyz"


# ---------------------------------------------------------------------------
# Tests: Whitespace stripping
# ---------------------------------------------------------------------------

class TestWhitespaceStripping:
    """Tests for whitespace stripping from values."""

    def test_strip_whitespace_from_values(self, service):
        """Leading/trailing whitespace in values is stripped."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n 2026-01-01 ; Amsterdam ;  Utrecht ; 45000 ; 45050 ; Zakelijk ; Test \n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["trip_date"] == "2026-01-01"
        assert row["start_address"] == "Amsterdam"
        assert row["end_address"] == "Utrecht"
        assert row["start_odometer"] == 45000
        assert row["end_odometer"] == 45050
        assert row["trip_category"] == "Zakelijk"
        assert row["trip_purpose"] == "Test"

    def test_strip_whitespace_from_column_headers(self, service):
        """Whitespace in column headers is stripped before mapping."""
        csv_content = " Datum ; Vertrekadres ; Bestemming ; Begin KM ; Eind KM ; Categorie ; Doel \n2026-01-01;A;B;100;200;Zakelijk;Test\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        assert result["success"] is True
        assert result["total_rows"] == 1
        row = result["rows"][0]
        assert row["trip_date"] == "2026-01-01"


# ---------------------------------------------------------------------------
# Tests: NaN/None handling
# ---------------------------------------------------------------------------

class TestNanNoneHandling:
    """Tests for NaN and None value handling."""

    def test_empty_values_become_none(self, service):
        """Empty CSV cells become None in the parsed rows."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant;Notities\n2026-01-01;A;B;100;200;Zakelijk;Test;;\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["contact_name"] is None
        assert row["notes"] is None

    def test_nan_in_xlsx_becomes_none(self, service):
        """NaN values in XLSX are converted to None."""
        df = pd.DataFrame({
            "Datum": ["2026-01-01"],
            "Vertrekadres": ["Amsterdam"],
            "Bestemming": ["Utrecht"],
            "Begin KM": ["50000"],
            "Eind KM": ["50050"],
            "Categorie": ["Zakelijk"],
            "Doel": ["Test"],
            "Klant": [None],  # Will be NaN in pandas
            "Notities": [None],
        })
        stream = make_xlsx_bytes(df)

        result = service.parse_file(stream, "test.xlsx")

        row = result["rows"][0]
        assert row["contact_name"] is None
        assert row["notes"] is None

    def test_whitespace_only_values_become_none(self, service):
        """Values with only whitespace become None after stripping."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant\n2026-01-01;A;B;100;200;Zakelijk;Test;   \n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["contact_name"] is None


# ---------------------------------------------------------------------------
# Tests: _get_extension helper
# ---------------------------------------------------------------------------

class TestGetExtension:
    """Tests for the _get_extension static method."""

    def test_csv_extension(self, service):
        assert TripImportService._get_extension("file.csv") == ".csv"

    def test_xlsx_extension(self, service):
        assert TripImportService._get_extension("file.xlsx") == ".xlsx"

    def test_xls_extension(self, service):
        assert TripImportService._get_extension("file.xls") == ".xls"

    def test_uppercase_extension(self, service):
        assert TripImportService._get_extension("FILE.CSV") == ".csv"

    def test_no_extension(self, service):
        assert TripImportService._get_extension("noextension") == ""

    def test_empty_filename(self, service):
        assert TripImportService._get_extension("") == ""

    def test_multiple_dots(self, service):
        assert TripImportService._get_extension("my.trips.2026.csv") == ".csv"


# ---------------------------------------------------------------------------
# Tests: _clean_row helper
# ---------------------------------------------------------------------------

class TestCleanRow:
    """Tests for the _clean_row static method."""

    def test_clean_row_strips_strings(self):
        row = {"trip_date": " 2026-01-01 ", "start_address": " Amsterdam "}
        cleaned = TripImportService._clean_row(row)
        assert cleaned["trip_date"] == "2026-01-01"
        assert cleaned["start_address"] == "Amsterdam"

    def test_clean_row_converts_odometer_to_int(self):
        row = {"start_odometer": "45000", "end_odometer": "45050"}
        cleaned = TripImportService._clean_row(row)
        assert cleaned["start_odometer"] == 45000
        assert cleaned["end_odometer"] == 45050

    def test_clean_row_handles_decimal_odometer(self):
        row = {"start_odometer": "45000.5", "end_odometer": "45050.9"}
        cleaned = TripImportService._clean_row(row)
        assert cleaned["start_odometer"] == 45000
        assert cleaned["end_odometer"] == 45050

    def test_clean_row_preserves_none(self):
        row = {"trip_date": None, "start_odometer": None}
        cleaned = TripImportService._clean_row(row)
        assert cleaned["trip_date"] is None
        assert cleaned["start_odometer"] is None

    def test_clean_row_empty_string_becomes_none(self):
        row = {"trip_date": "", "start_address": "  "}
        cleaned = TripImportService._clean_row(row)
        assert cleaned["trip_date"] is None
        assert cleaned["start_address"] is None

    def test_clean_row_non_string_preserved(self):
        row = {"some_field": 42, "another": 3.14}
        cleaned = TripImportService._clean_row(row)
        assert cleaned["some_field"] == 42
        assert cleaned["another"] == 3.14


# ---------------------------------------------------------------------------
# Tests: Multiple rows and edge cases
# ---------------------------------------------------------------------------

class TestMultipleRows:
    """Tests for multiple rows and edge cases."""

    def test_large_csv_many_rows(self, service):
        """Parse a CSV with many rows (simulating bulk import)."""
        header = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n"
        rows = ""
        for i in range(100):
            km_start = 45000 + (i * 50)
            km_end = km_start + 50
            rows += f"2026-01-{(i % 28) + 1:02d};City{i};City{i+1};{km_start};{km_end};Zakelijk;Trip {i}\n"

        stream = make_csv_bytes(header + rows)
        result = service.parse_file(stream, "bulk.csv")

        assert result["success"] is True
        assert result["total_rows"] == 100
        assert len(result["rows"]) == 100

    def test_case_sensitive_filename_extension(self, service):
        """File extension detection is case-insensitive."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n2026-01-01;A;B;100;200;Zakelijk;Test\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "TRIPS.CSV")

        assert result["success"] is True
        assert result["total_rows"] == 1

    def test_special_characters_in_values(self, service):
        """Special characters (accents, commas in addresses) are preserved."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel\n2026-01-01;Keizersgracht 100, Amsterdam;Café René, Straße 5;100;200;Zakelijk;Bezoek café\n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        assert result["success"] is True
        row = result["rows"][0]
        assert "Keizersgracht" in row["start_address"]
        assert "Café" in row["end_address"] or "Caf" in row["end_address"]


# ---------------------------------------------------------------------------
# Tests: commit_import method
# ---------------------------------------------------------------------------

class TestCommitImport:
    """Tests for the commit_import method (task 12.4)."""

    @pytest.fixture
    def import_service(self):
        """Create TripImportService with a mock DB that supports transaction context."""
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        # Setup transaction context manager
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        # Track lastrowid auto-increment
        mock_cursor.lastrowid = 1
        service = TripImportService(db=mock_db)
        return service, mock_cursor, mock_conn

    def _make_valid_row(self, **overrides):
        """Create a valid import row with defaults."""
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
            "contact_id": None,
            "project_name": None,
            "notes": "Test import",
            "_status": "ok",
            "_messages": [],
            "_row_number": 1,
        }
        row.update(overrides)
        return row

    def test_commit_import_success_single_row(self, import_service):
        """Successfully import a single valid row."""
        service, mock_cursor, _ = import_service
        mock_cursor.lastrowid = 42

        rows = [self._make_valid_row()]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_commit_import_success_multiple_rows(self, import_service):
        """Successfully import multiple valid rows."""
        service, mock_cursor, _ = import_service
        # Simulate auto-increment IDs
        mock_cursor.lastrowid = 1

        rows = [
            self._make_valid_row(trip_date="2026-01-15", start_odometer=45000, end_odometer=45045),
            self._make_valid_row(trip_date="2026-01-16", start_odometer=45045, end_odometer=45090, _row_number=2),
            self._make_valid_row(trip_date="2026-01-17", start_odometer=45090, end_odometer=45130, _row_number=3),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 3
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_commit_import_skips_error_rows(self, import_service):
        """Error rows are skipped and counted correctly."""
        service, mock_cursor, _ = import_service
        mock_cursor.lastrowid = 10

        rows = [
            self._make_valid_row(trip_date="2026-01-15"),
            self._make_valid_row(trip_date="2026-01-16", _status="error", _messages=["Invalid date"]),
            self._make_valid_row(trip_date="2026-01-17", _row_number=3),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 2
        assert result["skipped"] == 1
        assert result["errors"] == []

    def test_commit_import_all_rows_are_errors(self, import_service):
        """When all rows are errors, no insert happens and skipped count matches."""
        service, mock_cursor, _ = import_service

        rows = [
            self._make_valid_row(_status="error"),
            self._make_valid_row(_status="error", _row_number=2),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 0
        assert result["skipped"] == 2
        assert result["errors"] == []
        # Transaction should not be opened when there are no valid rows
        service.db.transaction.assert_not_called()

    def test_commit_import_empty_rows_list(self, import_service):
        """Empty rows list results in zero imports."""
        service, mock_cursor, _ = import_service

        result = service.commit_import("tenant1", 1, [], "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_commit_import_inserts_correct_values(self, import_service):
        """Verify the INSERT query uses correct parameters."""
        service, mock_cursor, _ = import_service
        mock_cursor.lastrowid = 99

        row = self._make_valid_row(
            trip_date="2026-03-10",
            start_address="Den Haag",
            end_address="Rotterdam",
            start_odometer=60000,
            end_odometer=60030,
            trip_category="Privé",
            trip_purpose="Persoonlijk",
            contact_id=5,
            project_name="Project X",
            notes="Notitie",
        )
        result = service.commit_import("admin1", 7, [row], "peter@example.com")

        assert result["success"] is True
        # Check the first execute call (INSERT trip)
        first_call = mock_cursor.execute.call_args_list[0]
        params = first_call[0][1]
        assert params[0] == "admin1"      # administration
        assert params[1] == 7             # vehicle_id
        assert params[2] == "2026-03-10"  # trip_date
        assert params[5] == "Den Haag"    # start_address
        assert params[6] == "Rotterdam"   # end_address
        assert params[7] == 60000         # start_odometer
        assert params[8] == 60030         # end_odometer
        assert params[9] == "Privé"       # trip_category
        assert params[10] == "Persoonlijk"  # trip_purpose
        assert params[11] == 5            # contact_id
        assert params[12] == "Project X"  # project_name
        assert params[13] == "Notitie"    # notes
        assert params[14] is False        # is_billable
        assert params[15] is False        # is_gap_fill
        assert params[16] is False        # is_cancelled
        assert params[17] == 1            # version
        assert params[18] == "peter@example.com"  # created_by

    def test_commit_import_writes_audit_log(self, import_service):
        """Each imported trip gets an audit log entry with action 'created'."""
        service, mock_cursor, _ = import_service
        mock_cursor.lastrowid = 55

        rows = [self._make_valid_row()]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        # Second execute call should be the audit entry
        audit_call = mock_cursor.execute.call_args_list[1]
        audit_query = audit_call[0][0]
        audit_params = audit_call[0][1]
        assert "'created'" in audit_query
        assert audit_params[0] == "tenant1"     # administration
        assert audit_params[1] == 55            # trip_id (from lastrowid)
        assert audit_params[2] == 1             # version
        assert audit_params[3] == "user@test.com"  # changed_by

    def test_commit_import_database_error_returns_failure(self, import_service):
        """DatabaseError during insert returns success=False with error details."""
        service, mock_cursor, _ = import_service
        from db_exceptions import DatabaseError

        # Make the transaction context raise DatabaseError
        service.db.transaction.return_value.__enter__ = MagicMock(
            side_effect=DatabaseError("Connection lost")
        )

        rows = [self._make_valid_row()]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is False
        assert result["imported"] == 0
        assert len(result["errors"]) == 1
        assert "Database error" in result["errors"][0]

    def test_commit_import_warning_rows_are_imported(self, import_service):
        """Rows with _status='warning' should be imported (only errors are skipped)."""
        service, mock_cursor, _ = import_service
        mock_cursor.lastrowid = 1

        rows = [
            self._make_valid_row(_status="warning", _messages=["Possible duplicate"]),
            self._make_valid_row(_status="ok", _row_number=2),
        ]
        result = service.commit_import("tenant1", 1, rows, "user@test.com")

        assert result["success"] is True
        assert result["imported"] == 2
        assert result["skipped"] == 0
