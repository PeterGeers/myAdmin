"""
Unit tests for TripImportService.parse_file method.

Tests CSV/Excel parsing, column mapping, error handling, and data cleaning.
"""
import io
import datetime
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
        assert row["client_name"] == "Acme BV"
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
        assert "client_name" in row
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
        assert row["client_name"] is None
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
        assert row["client_name"] is None
        assert row["notes"] is None

    def test_whitespace_only_values_become_none(self, service):
        """Values with only whitespace become None after stripping."""
        csv_content = "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant\n2026-01-01;A;B;100;200;Zakelijk;Test;   \n"
        stream = make_csv_bytes(csv_content)

        result = service.parse_file(stream, "test.csv")

        row = result["rows"][0]
        assert row["client_name"] is None


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
            "client_name": None,
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
            client_name="Acme BV",
            project_name="Project X",
            notes="Notitie",
        )
        result = service.commit_import("admin1", 7, [row], "peter@example.com")

        assert result["success"] is True
        # Check the first execute call (INSERT trip). The post-redesign INSERT
        # writes 19 columns: no contact_id / is_billable / is_billed / invoice_id;
        # client_name is written at index 11 and route_description at 14 (Req 2.7,
        # 4.6). Positional map:
        #   0 administration, 1 vehicle_id, 2 trip_date, 3 start_time, 4 end_time,
        #   5 start_address, 6 end_address, 7 start_odometer, 8 end_odometer,
        #   9 trip_category, 10 trip_purpose, 11 client_name, 12 project_name,
        #   13 notes, 14 route_description, 15 is_gap_fill, 16 is_cancelled,
        #   17 version, 18 created_by.
        first_call = mock_cursor.execute.call_args_list[0]
        params = first_call[0][1]
        assert len(params) == 19
        assert params[0] == "admin1"      # administration
        assert params[1] == 7             # vehicle_id
        assert params[2] == "2026-03-10"  # trip_date
        assert params[5] == "Den Haag"    # start_address
        assert params[6] == "Rotterdam"   # end_address
        assert params[7] == 60000         # start_odometer
        assert params[8] == 60030         # end_odometer
        assert params[9] == "Privé"       # trip_category
        assert params[10] == "Persoonlijk"  # trip_purpose
        assert params[11] == "Acme BV"    # client_name (replaces contact_id)
        assert params[12] == "Project X"  # project_name
        assert params[13] == "Notitie"    # notes
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


# ---------------------------------------------------------------------------
# Tests: Surface (c) Excel handling — BUG CONDITION exploration (Task 8)
# ---------------------------------------------------------------------------

class TestExcelHandlingBugCondition:
    """Fixed behavior for surface (c): Excel handling (post-fix assertions).

    Property 5 (Expected Behavior) — Correct Sheet Selected, Datetime Dates
    Normalize, Error Markers Flagged.

    These were originally the bug-condition exploration assertions (task 8) that
    documented the WRONG behavior on unfixed code. Per the bugfix methodology, the
    fix (tasks 10.1–10.3) is now applied, so the exploration assertions have been
    FLIPPED to encode the CORRECT post-fix behavior:

    - The matching second worksheet IS selected (not the decoy first sheet).
    - A date string carrying a time component normalizes to the date portion, and
      a datetime/date object normalizes to its ISO date.
    - An Excel error marker (``#N/A``) in a mapped cell flags the row ``error`` with
      a message naming the column + marker.

    The scenario-level end-to-end assertions (two-sheet selection, no-match failure,
    error-marker in-sheet) live in the task-11 ``validate_import`` tests below; these
    retain the direct unit-level checks of the three fixed behaviors.
    """

    @pytest.fixture
    def excel_service(self, mock_db):
        """TripImportService backed by the shared mock_db (no existing trips)."""
        mock_db.execute_query.return_value = []
        return TripImportService(db=mock_db)

    @staticmethod
    def _make_two_sheet_xlsx() -> io.BytesIO:
        """Build an .xlsx with a decoy FIRST sheet and a full SECOND sheet.

        - FIRST sheet ``Blad1``: only a subset of headers (missing the required
          Datum/Bestemming/Begin KM/Eind KM columns).
        - SECOND sheet ``ritten_import_template``: ALL mapped headers with two
          continuity-respecting data rows.
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            decoy = pd.DataFrame({
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
                "Klant": ["Acme BV", "Acme BV"],
                "Notities": ["rit 1", "rit 2"],
            })
            decoy.to_excel(writer, sheet_name="Blad1", index=False)

            full = pd.DataFrame({
                "Datum": ["2026-05-05", "2026-05-06"],
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Bestemming": ["Utrecht", "Amsterdam"],
                "Begin KM": ["45000", "45050"],
                "Eind KM": ["45050", "45100"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
                "Klant": ["Acme BV", "Acme BV"],
                "Notities": ["rit 1", "rit 2"],
            })
            full.to_excel(writer, sheet_name="ritten_import_template", index=False)
        buf.seek(0)
        return buf

    # -- Property 5(1): Wrong sheet read -----------------------------------

    def test_parse_file_two_sheet_workbook_selects_matching_second_sheet(self, excel_service):
        """FIXED: parse_file skips the decoy first sheet and selects the matching second.

        Expected behavior — header-matching worksheet selection returns the first
        sheet whose stripped headers ⊇ the required set. The decoy ``Blad1`` lacks
        ``Datum/Bestemming/Begin KM/Eind KM``, so the full ``ritten_import_template``
        sheet is chosen and ``columns_found`` reflects its nine headers.
        """
        stream = self._make_two_sheet_xlsx()

        result = excel_service.parse_file(stream, "ritten.xlsx")

        # The matching second sheet is selected — not the decoy first sheet.
        assert result["success"] is True
        assert result["columns_found"] == [
            "Datum", "Vertrekadres", "Bestemming", "Begin KM", "Eind KM",
            "Categorie", "Doel", "Klant", "Notities",
        ]
        # The required headers from the second sheet are now present.
        assert "Datum" in result["columns_found"]
        assert "Bestemming" in result["columns_found"]
        assert "Begin KM" in result["columns_found"]
        assert "Eind KM" in result["columns_found"]

    def test_validate_import_two_sheet_workbook_rows_valid(self, excel_service):
        """FIXED: selecting the matching second sheet makes its rows validate ``ok``.

        Expected behavior — because the chosen sheet carries all required columns,
        the two continuity-respecting rows validate (``valid > 0``), replacing the
        pre-fix empty/all-error preview.
        """
        stream = self._make_two_sheet_xlsx()
        parsed = excel_service.parse_file(stream, "ritten.xlsx")

        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["total_rows"] == 2
        assert result["valid"] == 2
        assert result["errors"] == 0
        for row in result["rows"]:
            assert row["_status"] == "ok"
            assert row["_messages"] == []

    # -- Property 5(3): Datetime-valued date rejected ----------------------

    def test_normalize_date_datetime_string_normalizes_to_date_portion(self):
        """FIXED: a date string carrying a time component normalizes to the date portion.

        Expected behavior — the leading date token is split off on whitespace (or
        ``'T'``), so ``"2026-05-05 00:00:00"`` normalizes to ``"2026-05-05"``. No
        time/timezone semantics are applied.
        """
        assert TripImportService._normalize_date("2026-05-05 00:00:00") == "2026-05-05"
        assert TripImportService._normalize_date("2026-05-05T00:00:00") == "2026-05-05"

    def test_normalize_date_date_object_normalizes_to_iso(self):
        """FIXED: a datetime/date object is normalized to its ISO date string.

        Expected behavior — a ``datetime.date`` (and ``datetime.datetime``) reaches
        the object branch and returns ``value.strftime("%Y-%m-%d")``.
        """
        assert TripImportService._normalize_date(datetime.date(2026, 5, 5)) == "2026-05-05"
        assert (
            TripImportService._normalize_date(datetime.datetime(2026, 5, 5, 0, 0, 0))
            == "2026-05-05"
        )

    # -- Property 5(4): Error marker silently unflagged --------------------

    def test_validate_import_na_marker_specially_flagged(self, excel_service):
        """FIXED: an Excel error marker ('#N/A') in a mapped date cell is specially flagged.

        Expected behavior — pandas coerces the ``#N/A`` cell to NaN, but openpyxl
        reports it as an error-type cell (``data_type == "e"``) and the fix restores
        the literal marker before validation. The row is flagged ``error`` with a
        message naming BOTH the column (``trip_date``) and the marker (``#N/A``):
        ``"Formulewaarde niet berekend: '#N/A' in kolom trip_date"``.
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df = pd.DataFrame({
                "Datum": ["#N/A", "2026-05-06"],
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Bestemming": ["Utrecht", "Amsterdam"],
                "Begin KM": ["45000", "45050"],
                "Eind KM": ["45050", "45100"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
            })
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buf.seek(0)

        parsed = excel_service.parse_file(buf, "markers.xlsx")
        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        # Locate the row originating from the '#N/A' cell (restored marker string).
        na_rows = [r for r in result["rows"] if r.get("trip_date") == "#N/A"]
        assert na_rows, "expected a row carrying the restored '#N/A' marker"

        for row in na_rows:
            assert row["_status"] == "error"
            marker_msgs = [m for m in row["_messages"] if "Formulewaarde niet berekend" in m]
            assert marker_msgs, "expected an error-marker message naming the column + marker"
            joined = " | ".join(marker_msgs)
            assert "trip_date" in joined
            assert "#N/A" in joined


# ---------------------------------------------------------------------------
# Tests: Surface (c) Excel handling — PRESERVATION (Task 9)
# ---------------------------------------------------------------------------

class TestExcelHandlingPreservation:
    """Preservation tests for surface (c): Excel handling.

    Property 6 (Preservation) — Single-Sheet/First-Match/CSV Identical, Extra
    Columns Ignored, Cached Values and Empty/None Unchanged.

    Observation-first: each assertion encodes behavior OBSERVED on the UNFIXED
    reader, so these PASS now (confirming the baseline to preserve) and must keep
    passing after the task-10 fix. The ``mock_db`` fixture returns no existing
    trips (``execute_query`` default ``[]``), so odometer-continuity and duplicate
    detection do not interfere.
    """

    @pytest.fixture
    def excel_service(self, mock_db):
        """TripImportService backed by the shared mock_db (no existing trips)."""
        mock_db.execute_query.return_value = []
        return TripImportService(db=mock_db)

    @staticmethod
    def _single_sheet_xlsx() -> io.BytesIO:
        """One-sheet .xlsx: FIRST (only) sheet has all mapped headers + rows.

        make_xlsx_bytes writes a single-sheet df, which is exactly the
        first-sheet-matching case Requirement 9.1 preserves.
        """
        df = pd.DataFrame({
            "Datum": ["2026-05-05", "2026-05-06", "2026-05-07"],
            "Vertrekadres": ["Amsterdam", "Utrecht", "Den Haag"],
            "Bestemming": ["Utrecht", "Den Haag", "Rotterdam"],
            "Begin KM": ["45000", "45050", "45100"],
            "Eind KM": ["45050", "45100", "45150"],
            "Categorie": ["Zakelijk", "Zakelijk", "Zakelijk"],
            "Doel": ["Klantbezoek", "Klantbezoek", "Klantbezoek"],
            "Klant": ["Acme BV", "Acme BV", "Acme BV"],
            "Notities": ["rit 1", "rit 2", "rit 3"],
        })
        return make_xlsx_bytes(df)

    # -- Requirement 9.1: single-sheet first-match reads the same sheet ----

    def test_parse_file_single_sheet_reads_all_mapped_headers(self, excel_service):
        """Observed: the only sheet is read; all nine mapped headers are found."""
        parsed = excel_service.parse_file(self._single_sheet_xlsx(), "single.xlsx")

        assert parsed["success"] is True
        assert parsed["total_rows"] == 3
        assert parsed["columns_found"] == [
            "Datum", "Vertrekadres", "Bestemming", "Begin KM", "Eind KM",
            "Categorie", "Doel", "Klant", "Notities",
        ]

    def test_validate_import_single_sheet_all_rows_valid(self, excel_service):
        """Observed: a single-sheet workbook validates all rows ``ok`` (valid == 3)."""
        parsed = excel_service.parse_file(self._single_sheet_xlsx(), "single.xlsx")

        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["success"] is True
        assert result["total_rows"] == 3
        assert result["valid"] == 3
        assert result["warnings"] == 0
        assert result["errors"] == 0
        # Mapped row values are read correctly and dates normalized (surface b).
        expected = [
            ("2026-05-05", "Amsterdam", "Utrecht", 45000, 45050),
            ("2026-05-06", "Utrecht", "Den Haag", 45050, 45100),
            ("2026-05-07", "Den Haag", "Rotterdam", 45100, 45150),
        ]
        by_row = {r["_row_number"]: r for r in result["rows"]}
        for idx, (date, start, end, skm, ekm) in enumerate(expected, start=1):
            row = by_row[idx]
            assert row["_status"] == "ok"
            assert row["_messages"] == []
            assert row["trip_date"] == date
            assert row["start_address"] == start
            assert row["end_address"] == end
            assert row["start_odometer"] == skm
            assert row["end_odometer"] == ekm

    # -- Requirement 9.2: CSV unaffected by worksheet selection ------------

    def test_parse_file_csv_semicolon_unaffected_by_sheet_selection(self, excel_service):
        """Observed: a semicolon-separated CSV parses via the existing path.

        Worksheet selection is an Excel-only concern and must not affect CSV.
        """
        csv_content = (
            "Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant;Notities\n"
            "2026-05-05;Amsterdam;Utrecht;45000;45050;Zakelijk;Klantbezoek;Acme BV;rit 1\n"
            "2026-05-06;Utrecht;Den Haag;45050;45100;Zakelijk;Klantbezoek;Acme BV;rit 2\n"
        )
        parsed = excel_service.parse_file(make_csv_bytes(csv_content), "trips.csv")

        assert parsed["success"] is True
        assert parsed["total_rows"] == 2

        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["valid"] == 2
        assert result["warnings"] == 0
        assert result["errors"] == 0
        by_row = {r["_row_number"]: r for r in result["rows"]}
        assert by_row[1]["_status"] == "ok"
        assert by_row[1]["trip_date"] == "2026-05-05"
        assert by_row[1]["start_odometer"] == 45000
        assert by_row[2]["_status"] == "ok"
        assert by_row[2]["trip_date"] == "2026-05-06"
        assert by_row[2]["end_odometer"] == 45100

    # -- Requirement 9.3: extra / unmapped columns ignored -----------------

    def test_parse_file_extra_unmapped_columns_ignored(self, excel_service):
        """Observed: trailing extra / Unnamed-style columns are reported as unmapped.

        The extra columns are listed in ``unmapped_columns`` (not mapped to any
        internal field) and do not interfere with reading the mapped fields.
        """
        df = pd.DataFrame({
            "Datum": ["2026-05-05", "2026-05-06"],
            "Vertrekadres": ["Amsterdam", "Utrecht"],
            "Bestemming": ["Utrecht", "Den Haag"],
            "Begin KM": ["45000", "45050"],
            "Eind KM": ["45050", "45100"],
            "Categorie": ["Zakelijk", "Zakelijk"],
            "Doel": ["Klantbezoek", "Klantbezoek"],
            "Klant": ["Acme BV", "Acme BV"],
            "Notities": ["rit 1", "rit 2"],
            "Afstand": ["50", "50"],          # extra, mapped to nothing
            "Unnamed: 10": ["x", "y"],        # stray Unnamed-style column
        })
        parsed = excel_service.parse_file(make_xlsx_bytes(df), "extra.xlsx")

        assert parsed["success"] is True
        # Extra columns are recognized as unmapped (ignored by the mapping).
        assert "Afstand" in parsed["unmapped_columns"]
        assert "Unnamed: 10" in parsed["unmapped_columns"]
        # The mapped internal fields are still produced from the mapped headers.
        for field in (
            "trip_date", "start_address", "end_address", "start_odometer",
            "end_odometer", "trip_category", "trip_purpose",
        ):
            assert field in parsed["columns_mapped"]

    def test_validate_import_extra_columns_do_not_affect_validation(self, excel_service):
        """Observed: extra/unmapped columns do not break mapped-field validation."""
        df = pd.DataFrame({
            "Datum": ["2026-05-05", "2026-05-06"],
            "Vertrekadres": ["Amsterdam", "Utrecht"],
            "Bestemming": ["Utrecht", "Den Haag"],
            "Begin KM": ["45000", "45050"],
            "Eind KM": ["45050", "45100"],
            "Categorie": ["Zakelijk", "Zakelijk"],
            "Doel": ["Klantbezoek", "Klantbezoek"],
            "Afstand": ["50", "50"],
            "Unnamed: 10": ["x", "y"],
        })
        parsed = excel_service.parse_file(make_xlsx_bytes(df), "extra.xlsx")

        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["valid"] == 2
        assert result["errors"] == 0
        for row in result["rows"]:
            assert row["_status"] == "ok"
            assert row["_messages"] == []

    # -- Requirements 9.5, 9.6: valid cached formula value read directly ---

    def test_validate_import_cached_value_read_as_plain_value(self, excel_service):
        """Observed: an ordinary (already-computed) cell value is read directly.

        A mapped cell carrying a plain string/number — the kind of cached "view"
        value pandas returns for a resolved formula — is read as that value and
        the row validates ``ok``. No formula evaluation is performed.
        """
        df = pd.DataFrame({
            "Datum": ["2026-05-05", "2026-05-06"],
            "Vertrekadres": ["Amsterdam", "Utrecht"],
            "Bestemming": ["Utrecht", "Den Haag"],
            "Begin KM": ["45000", "45050"],
            "Eind KM": ["45050", "45100"],
            "Categorie": ["Zakelijk", "Zakelijk"],
            "Doel": ["Klantbezoek", "Klantbezoek"],
            "Klant": ["CachedKlant", "CachedKlant"],  # cached value from another tab
            "Notities": ["rit 1", "rit 2"],
        })
        parsed = excel_service.parse_file(make_xlsx_bytes(df), "cached.xlsx")

        # The plain value is read straight through the mapping.
        assert parsed["rows"][0]["client_name"] == "CachedKlant"

        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["valid"] == 2
        assert result["errors"] == 0
        for row in result["rows"]:
            assert row["_status"] == "ok"
            assert row["client_name"] == "CachedKlant"
            assert row["_messages"] == []

    # -- Requirement 9.6: empty/None cell → normal required-field error ----

    def test_validate_import_empty_required_cell_normal_required_error(self, excel_service):
        """Observed: an empty/None required cell yields the normal required-field error.

        Row 2 is missing the required Bestemming (end_address). It is flagged
        ``error`` with the standard "Verplicht veld ontbreekt" message — NOT an
        error-marker ("Formulewaarde niet berekend") message.
        """
        df = pd.DataFrame({
            "Datum": ["2026-05-05", "2026-05-06"],
            "Vertrekadres": ["Amsterdam", "Utrecht"],
            "Bestemming": ["Utrecht", None],  # row 2 missing required end_address
            "Begin KM": ["45000", "45050"],
            "Eind KM": ["45050", "45100"],
            "Categorie": ["Zakelijk", "Zakelijk"],
            "Doel": ["Klantbezoek", "Klantbezoek"],
        })
        parsed = excel_service.parse_file(make_xlsx_bytes(df), "empty.xlsx")

        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["total_rows"] == 2
        assert result["valid"] == 1
        assert result["errors"] == 1

        by_row = {r["_row_number"]: r for r in result["rows"]}
        # Row 1 is unaffected.
        assert by_row[1]["_status"] == "ok"
        assert by_row[1]["end_address"] == "Utrecht"
        # Row 2: normal required-field error, not an error-marker message.
        assert by_row[2]["_status"] == "error"
        assert by_row[2]["end_address"] is None
        assert "Verplicht veld ontbreekt: end_address" in by_row[2]["_messages"]
        joined = " | ".join(by_row[2]["_messages"])
        assert "Formulewaarde niet berekend" not in joined


# ---------------------------------------------------------------------------
# Tests: Surface (c) Excel handling — FIXED end-to-end (Task 11)
# ---------------------------------------------------------------------------

class TestValidateImportFixedExcelBehavior:
    """End-to-end ``validate_import`` tests encoding the FIXED Property-5 behavior.

    Post-fix assertions (tasks 10.1–10.3 applied):
      - header-matching worksheet selection picks the sheet whose headers ⊇ the
        required set, or returns ``success: False`` naming found vs expected when
        no sheet matches;
      - Excel datetime-valued dates (surfacing as ``"YYYY-MM-DD HH:MM:SS"`` under
        ``dtype=str``) normalize to the date portion and validate ``ok``;
      - an Excel error marker (``#N/A``) in a mapped cell flags the row ``error``
        with a message naming the column + marker.

    The ``mock_db`` fixture returns no existing trips so odometer-continuity and
    duplicate detection do not interfere.
    """

    @pytest.fixture
    def excel_service(self, mock_db):
        """TripImportService backed by the shared mock_db (no existing trips)."""
        mock_db.execute_query.return_value = []
        return TripImportService(db=mock_db)

    @staticmethod
    def _make_two_sheet_xlsx() -> io.BytesIO:
        """Build an .xlsx with a decoy FIRST sheet and a full SECOND sheet.

        - FIRST sheet ``Blad1``: only a subset of headers (missing the required
          Datum/Bestemming/Begin KM/Eind KM columns).
        - SECOND sheet ``ritten_import_template``: ALL mapped headers with two
          continuity-respecting data rows.
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            decoy = pd.DataFrame({
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
                "Klant": ["Acme BV", "Acme BV"],
                "Notities": ["rit 1", "rit 2"],
            })
            decoy.to_excel(writer, sheet_name="Blad1", index=False)

            full = pd.DataFrame({
                "Datum": ["2026-05-05", "2026-05-06"],
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Bestemming": ["Utrecht", "Amsterdam"],
                "Begin KM": ["45000", "45050"],
                "Eind KM": ["45050", "45100"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
                "Klant": ["Acme BV", "Acme BV"],
                "Notities": ["rit 1", "rit 2"],
            })
            full.to_excel(writer, sheet_name="ritten_import_template", index=False)
        buf.seek(0)
        return buf

    # -- Property 5(1): correct sheet selected end-to-end ------------------

    def test_parse_file_decoy_first_sheet_selects_matching_second_sheet(self, excel_service):
        """FIXED: the decoy first sheet is skipped and the matching second is used.

        Asserts ``success is True``, the mapped ``columns_found`` come from the
        second sheet, ``total_rows`` matches that sheet's data, and
        ``validate_import`` reports ``valid > 0``.
        """
        stream = self._make_two_sheet_xlsx()

        result = excel_service.parse_file(stream, "ritten.xlsx")

        assert result["success"] is True
        # columns_found / mapped fields come from the SECOND (matching) sheet.
        assert result["columns_found"] == [
            "Datum", "Vertrekadres", "Bestemming", "Begin KM", "Eind KM",
            "Categorie", "Doel", "Klant", "Notities",
        ]
        for field in (
            "trip_date", "start_address", "end_address", "start_odometer",
            "end_odometer", "trip_category", "trip_purpose",
        ):
            assert field in result["columns_mapped"]
        # total_rows matches the second sheet's two data rows.
        assert result["total_rows"] == 2

        validated = excel_service.validate_import("tenant1", 1, result["rows"])
        assert validated["valid"] > 0
        assert validated["valid"] == 2
        assert validated["errors"] == 0
        # The mapped values are the second sheet's rows (date normalized).
        by_row = {r["_row_number"]: r for r in validated["rows"]}
        assert by_row[1]["trip_date"] == "2026-05-05"
        assert by_row[1]["start_odometer"] == 45000
        assert by_row[2]["trip_date"] == "2026-05-06"
        assert by_row[2]["end_odometer"] == 45100

    # -- Property 5(1): no sheet matches → success: False ------------------

    def test_parse_file_no_sheet_matches_returns_success_false(self, excel_service):
        """FIXED: a workbook where NO sheet carries the required headers fails cleanly.

        Asserts ``success is False`` and that the ``error`` string names BOTH the
        columns actually found and the expected (required) columns, so the wizard
        would keep the user on Upload rather than render an empty preview.
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame({
                "Kolom A": ["x", "y"],
                "Kolom B": ["1", "2"],
            }).to_excel(writer, sheet_name="Overzicht", index=False)
            pd.DataFrame({
                "Vertrekadres": ["Amsterdam"],
                "Categorie": ["Zakelijk"],
            }).to_excel(writer, sheet_name="Deels", index=False)
        buf.seek(0)

        result = excel_service.parse_file(buf, "geen_match.xlsx")

        assert result["success"] is False
        assert result["rows"] == []
        assert result["total_rows"] == 0
        error = result["error"]
        assert error is not None
        # The found columns (first sheet) are named in the error.
        assert "Kolom A" in error
        assert "Kolom B" in error
        # The expected/required columns are also named in the error.
        for expected in ("Datum", "Bestemming", "Begin KM", "Eind KM", "Vertrekadres",
                         "Categorie", "Doel"):
            assert expected in error

    # -- Property 5(3): datetime-valued dates in-sheet normalize + validate -

    def test_validate_import_datetime_valued_dates_in_sheet_ok(self, excel_service):
        """FIXED: Excel datetime-valued Datum cells normalize to the date portion.

        Writing ``pd.Timestamp`` values into the Datum column stores genuine Excel
        datetimes; under ``dtype=str`` they surface as ``"YYYY-MM-DD HH:MM:SS"``.
        After the fix those rows normalize to ``YYYY-MM-DD`` and validate ``ok``.
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df = pd.DataFrame({
                "Datum": [pd.Timestamp("2026-05-05"), pd.Timestamp("2026-05-06")],
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Bestemming": ["Utrecht", "Amsterdam"],
                "Begin KM": ["45000", "45050"],
                "Eind KM": ["45050", "45100"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
            })
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buf.seek(0)

        parsed = excel_service.parse_file(buf, "datetimes.xlsx")
        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        assert result["total_rows"] == 2
        assert result["valid"] == 2
        assert result["errors"] == 0
        by_row = {r["_row_number"]: r for r in result["rows"]}
        # Only the YYYY-MM-DD date portion is kept — no time component.
        assert by_row[1]["_status"] == "ok"
        assert by_row[1]["trip_date"] == "2026-05-05"
        assert by_row[2]["_status"] == "ok"
        assert by_row[2]["trip_date"] == "2026-05-06"

    # -- Property 5(4): error marker in-sheet flags the row ----------------

    def test_validate_import_na_marker_flags_row_error(self, excel_service):
        """FIXED: a mapped trip_date cell equal to '#N/A' flags that row ``error``.

        Asserts the ``#N/A`` row's ``_status == "error"`` and that a ``_messages``
        entry names BOTH the column (``trip_date``) and the marker (``#N/A``).
        """
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df = pd.DataFrame({
                "Datum": ["#N/A", "2026-05-06"],
                "Vertrekadres": ["Amsterdam", "Utrecht"],
                "Bestemming": ["Utrecht", "Amsterdam"],
                "Begin KM": ["45000", "45050"],
                "Eind KM": ["45050", "45100"],
                "Categorie": ["Zakelijk", "Zakelijk"],
                "Doel": ["Klantbezoek", "Klantbezoek"],
            })
            df.to_excel(writer, sheet_name="Sheet1", index=False)
        buf.seek(0)

        parsed = excel_service.parse_file(buf, "markers.xlsx")
        result = excel_service.validate_import("tenant1", 1, parsed["rows"])

        na_rows = [r for r in result["rows"] if r.get("trip_date") == "#N/A"]
        assert na_rows, "expected a row carrying the restored '#N/A' marker"

        marked = na_rows[0]
        assert marked["_status"] == "error"
        marker_msgs = [
            m for m in marked["_messages"] if "trip_date" in m and "#N/A" in m
        ]
        assert marker_msgs, (
            "expected a _messages entry naming both the column (trip_date) and "
            "the marker (#N/A)"
        )
