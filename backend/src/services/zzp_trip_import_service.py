"""
TripImportService: CSV/Excel import with validation and preview.

Handles file parsing, row validation, and bulk import of trip records
from CSV or Excel files. Supports column mapping to handle various
file formats from different sources (e.g., TomTom, fleet management).

Business rules:
- Supports CSV (.csv) and Excel (.xlsx, .xls) file formats
- Column mapping allows flexible header-to-field assignment
- Validation checks: required fields, date format, end > start odometer
- Odometer continuity validated within import AND against existing trips
- Duplicate detection (same vehicle + date + start_km + end_km)
- Preview mode: validate without committing
- Commit mode: bulk insert validated rows with audit logging

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §4.4
"""

import io
import logging
from typing import List, Optional

import pandas as pd

from db_exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Default column mapping (Dutch headers → internal field names)
DEFAULT_COLUMN_MAPPING = {
    "Datum": "trip_date",
    "Vertrekadres": "start_address",
    "Bestemming": "end_address",
    "Begin KM": "start_odometer",
    "Eind KM": "end_odometer",
    "Categorie": "trip_category",
    "Doel": "trip_purpose",
    "Klant": "contact_name",
    "Notities": "notes",
}

# Required fields for a valid import row
REQUIRED_IMPORT_FIELDS = [
    "trip_date",
    "start_address",
    "end_address",
    "start_odometer",
    "end_odometer",
    "trip_category",
    "trip_purpose",
]

# Template CSV columns (Dutch headers for downloadable template)
TEMPLATE_COLUMNS = [
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


class TripImportService:
    """CSV/Excel import with validation and preview."""

    def __init__(self, db, parameter_service=None):
        """Initialize TripImportService.

        Args:
            db: DatabaseManager instance for database access.
            parameter_service: Optional ParameterService for tenant-scoped config.
        """
        self.db = db
        self.parameter_service = parameter_service

    def parse_file(self, file_stream, filename: str, column_mapping: dict = None) -> dict:
        """Parse a CSV or Excel file and apply column mapping.

        Detects file type by extension, reads via pandas, applies the
        column mapping to normalize headers to internal field names,
        and returns raw rows for subsequent validation.

        Args:
            file_stream: File-like object (BytesIO or similar) with the uploaded data.
            filename: Original filename (used to detect format by extension).
            column_mapping: Dict mapping file column headers to internal field names.
                Keys are the header names in the file, values are internal field names.
                Example: {"Datum": "trip_date", "Van": "start_address", ...}
                If None, uses DEFAULT_COLUMN_MAPPING.

        Returns:
            Dict with keys:
                - success (bool): Whether parsing succeeded.
                - rows (list[dict]): List of parsed row dicts with internal field names.
                - total_rows (int): Number of rows parsed.
                - columns_found (list[str]): Original column headers found in the file.
                - columns_mapped (list[str]): Internal field names after mapping.
                - unmapped_columns (list[str]): File columns not present in the mapping.
                - error (str, optional): Error message if parsing failed.
        """
        mapping = column_mapping or DEFAULT_COLUMN_MAPPING

        # Detect file type by extension
        ext = self._get_extension(filename)
        if ext not in (".csv", ".xlsx", ".xls"):
            return {
                "success": False,
                "rows": [],
                "total_rows": 0,
                "columns_found": [],
                "columns_mapped": [],
                "unmapped_columns": [],
                "error": f"Unsupported file type: '{ext}'. Use .csv, .xlsx, or .xls.",
            }

        try:
            df = self._read_dataframe(file_stream, ext)
        except Exception as e:
            logger.warning("Failed to parse import file '%s': %s", filename, e)
            return {
                "success": False,
                "rows": [],
                "total_rows": 0,
                "columns_found": [],
                "columns_mapped": [],
                "unmapped_columns": [],
                "error": f"Could not read file: {str(e)}",
            }

        if df.empty:
            return {
                "success": True,
                "rows": [],
                "total_rows": 0,
                "columns_found": list(df.columns),
                "columns_mapped": [],
                "unmapped_columns": list(df.columns),
                "error": None,
            }

        # Strip whitespace from column headers
        df.columns = [str(col).strip() for col in df.columns]
        columns_found = list(df.columns)

        # Apply column mapping: rename file headers → internal field names
        # The mapping is {file_header: internal_name}
        rename_map = {}
        for file_col, internal_name in mapping.items():
            if file_col in df.columns:
                rename_map[file_col] = internal_name

        mapped_columns = list(rename_map.values())
        unmapped_columns = [col for col in columns_found if col not in rename_map]

        df = df.rename(columns=rename_map)

        # Convert DataFrame to list of dicts, replacing NaN with None
        df = df.where(pd.notna(df), None)
        rows = df.to_dict(orient="records")

        # Clean up row values: strip strings, convert odometer to int
        rows = [self._clean_row(row) for row in rows]

        return {
            "success": True,
            "rows": rows,
            "total_rows": len(rows),
            "columns_found": columns_found,
            "columns_mapped": mapped_columns,
            "unmapped_columns": unmapped_columns,
            "error": None,
        }

    def validate_import(self, tenant: str, vehicle_id: int, rows: List[dict]) -> dict:
        """Validate parsed rows before import.

        Checks each row for:
        - Required fields present and non-empty
        - Date format valid
        - end_odometer > start_odometer
        - Odometer continuity within the import set
        - Odometer continuity against existing trips in the database
        - Duplicate detection (same vehicle + date + start + end km)

        Args:
            tenant: Administration/tenant identifier.
            vehicle_id: Target vehicle for the import.
            rows: List of parsed row dicts (from parse_file).

        Returns:
            Dict with keys:
                - success (bool): True if validation completed (even with errors).
                - total_rows (int): Total number of rows.
                - valid (int): Number of rows without errors.
                - warnings (int): Number of rows with warnings only.
                - errors (int): Number of rows with errors.
                - rows (list[dict]): Each row with added '_status' and '_messages' fields.
                - preview (list[dict]): First 20 rows for frontend preview.
        """
        if not rows:
            return {
                "success": True,
                "total_rows": 0,
                "valid": 0,
                "warnings": 0,
                "errors": 0,
                "rows": [],
                "preview": [],
            }

        # Fetch existing trips for continuity + duplicate checks
        existing_trips = self._get_existing_trips(tenant, vehicle_id)

        # Build a set of existing (date, start_odometer, end_odometer) for duplicate detection
        existing_set = set()
        for trip in existing_trips:
            trip_date = trip.get("trip_date")
            # Normalize date to string if it's a date object
            if hasattr(trip_date, "strftime"):
                trip_date = trip_date.strftime("%Y-%m-%d")
            existing_set.add((
                str(trip_date),
                int(trip.get("start_odometer", 0)),
                int(trip.get("end_odometer", 0)),
            ))

        # Get the last odometer reading from existing trips
        last_existing_odometer = None
        if existing_trips:
            last_existing_odometer = int(existing_trips[-1].get("end_odometer", 0))

        # Get valid categories and purposes (if parameter_service available)
        valid_categories = self._get_trip_categories(tenant)
        valid_purposes = self._get_trip_purposes(tenant)

        # Annotate each row with _row_number and normalize dates
        annotated_rows = []
        for idx, row in enumerate(rows):
            annotated = dict(row)
            annotated["_row_number"] = idx + 1
            annotated["_messages"] = []
            annotated["_status"] = "ok"
            annotated_rows.append(annotated)

        # Phase 1: Per-row validation (required fields, date, odometer)
        for row in annotated_rows:
            self._validate_required_fields(row)
            self._validate_date_format(row)
            self._validate_odometer_values(row)
            self._validate_category_purpose(row, valid_categories, valid_purposes)

        # Sort rows by normalized date for continuity checks
        annotated_rows.sort(key=lambda r: r.get("_normalized_date", "9999-99-99"))

        # Phase 2: Odometer continuity within the import set
        self._check_internal_continuity(annotated_rows)

        # Phase 3: Odometer continuity against existing DB trips
        self._check_db_continuity(annotated_rows, last_existing_odometer)

        # Phase 4: Duplicate detection
        self._check_duplicates(annotated_rows, existing_set)

        # Calculate totals
        count_valid = sum(1 for r in annotated_rows if r["_status"] == "ok")
        count_warnings = sum(1 for r in annotated_rows if r["_status"] == "warning")
        count_errors = sum(1 for r in annotated_rows if r["_status"] == "error")

        # Clean up internal helper fields
        for row in annotated_rows:
            row.pop("_normalized_date", None)

        return {
            "success": True,
            "total_rows": len(annotated_rows),
            "valid": count_valid,
            "warnings": count_warnings,
            "errors": count_errors,
            "rows": annotated_rows,
            "preview": annotated_rows[:20],
        }

    def commit_import(
        self, tenant: str, vehicle_id: int, rows: List[dict], created_by: str
    ) -> dict:
        """Bulk insert validated rows as trip records.

        Inserts all rows (or only valid rows if skip_error_rows was applied
        during validation). Creates audit log entries for each imported trip.

        Args:
            tenant: Administration/tenant identifier.
            vehicle_id: Target vehicle for the import.
            rows: List of validated row dicts (only rows with _status != 'error').
            created_by: Email/identifier of the user performing the import.

        Returns:
            Dict with keys:
                - success (bool): Whether the commit succeeded.
                - imported (int): Number of trips created.
                - skipped (int): Number of rows skipped (errors).
                - errors (list[str]): Any errors encountered during insert.
        """
        # Separate valid rows from error rows
        valid_rows = [r for r in rows if r.get("_status") != "error"]
        skipped = len(rows) - len(valid_rows)

        if not valid_rows:
            logger.info(
                "Import for tenant=%s vehicle_id=%d: no valid rows to import "
                "(skipped=%d)",
                tenant, vehicle_id, skipped,
            )
            return {
                "success": True,
                "imported": 0,
                "skipped": skipped,
                "errors": [],
            }

        insert_query = """
            INSERT INTO zzp_trips (
                administration, vehicle_id, trip_date, start_time, end_time,
                start_address, end_address, start_odometer, end_odometer,
                trip_category, trip_purpose, contact_id, project_name, notes,
                is_billable, is_gap_fill, is_cancelled, version, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        audit_query = """
            INSERT INTO zzp_trip_audit (
                administration, trip_id, version, action, changed_fields,
                correction_reason, changed_by
            ) VALUES (%s, %s, %s, 'created', NULL, NULL, %s)
        """

        imported = 0
        errors = []

        try:
            with self.db.transaction() as (cursor, conn):
                for row in valid_rows:
                    params = (
                        tenant,
                        vehicle_id,
                        row.get("trip_date"),
                        row.get("start_time"),
                        row.get("end_time"),
                        row.get("start_address"),
                        row.get("end_address"),
                        row.get("start_odometer"),
                        row.get("end_odometer"),
                        row.get("trip_category"),
                        row.get("trip_purpose"),
                        row.get("contact_id"),
                        row.get("project_name"),
                        row.get("notes"),
                        False,   # is_billable
                        False,   # is_gap_fill
                        False,   # is_cancelled
                        1,       # version
                        created_by,
                    )
                    cursor.execute(insert_query, params)
                    trip_id = cursor.lastrowid

                    # Write audit log entry
                    audit_params = (tenant, trip_id, 1, created_by)
                    cursor.execute(audit_query, audit_params)

                    imported += 1

            logger.info(
                "Import committed for tenant=%s vehicle_id=%d: "
                "imported=%d, skipped=%d",
                tenant, vehicle_id, imported, skipped,
            )
            return {
                "success": True,
                "imported": imported,
                "skipped": skipped,
                "errors": errors,
            }

        except DatabaseError as e:
            logger.error(
                "Import failed for tenant=%s vehicle_id=%d: %s",
                tenant, vehicle_id, e,
            )
            return {
                "success": False,
                "imported": 0,
                "skipped": skipped,
                "errors": [f"Database error during import: {str(e)}"],
            }

    def get_template_csv(self) -> bytes:
        """Generate a downloadable CSV template with correct headers and example rows.

        Returns a CSV file (UTF-8 with BOM, semicolon-separated) containing
        the header row with the expected Dutch column names and 2-3 example
        data rows showing the expected format. Users can fill this template
        and import it.

        Returns:
            CSV template file content as bytes (UTF-8-BOM encoded).
        """
        output = io.StringIO()

        # Write UTF-8 BOM for Excel compatibility
        output.write("\ufeff")

        # Write header row
        output.write(";".join(TEMPLATE_COLUMNS) + "\n")

        # Write example data rows
        example_rows = [
            "15-01-2026;Keizersgracht 100, Amsterdam;Stationsplein 1, Utrecht;45000;45045;Zakelijk;Klantbezoek;Acme BV;Projectbespreking Q1",
            "15-01-2026;Stationsplein 1, Utrecht;Keizersgracht 100, Amsterdam;45045;45090;Zakelijk;Klantbezoek;Acme BV;Retour",
            "16-01-2026;Keizersgracht 100, Amsterdam;Nieuwstraat 5, Den Haag;45090;45155;Zakelijk;Vergadering;;Teamoverleg",
        ]
        for row in example_rows:
            output.write(row + "\n")

        return output.getvalue().encode("utf-8")

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_extension(filename: str) -> str:
        """Extract lowercase file extension from filename.

        Args:
            filename: Original filename (e.g., "trips_2026.xlsx").

        Returns:
            Extension with dot (e.g., ".xlsx"), or empty string.
        """
        if not filename:
            return ""
        dot_idx = filename.rfind(".")
        if dot_idx < 0:
            return ""
        return filename[dot_idx:].lower()

    @staticmethod
    def _read_dataframe(file_stream, ext: str) -> pd.DataFrame:
        """Read file stream into a pandas DataFrame based on extension.

        Args:
            file_stream: File-like object with the data.
            ext: File extension (e.g., ".csv", ".xlsx").

        Returns:
            pandas DataFrame with the file contents.

        Raises:
            ValueError: If extension is unsupported.
            Exception: Propagates pandas read errors.
        """
        if ext == ".csv":
            # Try semicolon first (Dutch standard), fall back to comma
            try:
                df = pd.read_csv(file_stream, sep=";", dtype=str)
                # If only 1 column found, it's probably comma-separated
                if len(df.columns) <= 1:
                    file_stream.seek(0)
                    df = pd.read_csv(file_stream, sep=",", dtype=str)
            except Exception:
                file_stream.seek(0)
                df = pd.read_csv(file_stream, sep=",", dtype=str)
            return df
        elif ext in (".xlsx", ".xls"):
            return pd.read_excel(file_stream, dtype=str)
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

    @staticmethod
    def _clean_row(row: dict) -> dict:
        """Clean a parsed row: strip strings, attempt numeric conversion for odometers.

        Args:
            row: Raw row dict from DataFrame.

        Returns:
            Cleaned row dict.
        """
        cleaned = {}
        for key, value in row.items():
            if value is None:
                cleaned[key] = None
            elif isinstance(value, str):
                stripped = value.strip()
                # Try to convert odometer fields to integers
                if key in ("start_odometer", "end_odometer") and stripped:
                    try:
                        # Handle potential decimal values (e.g., "45230.0")
                        cleaned[key] = int(float(stripped))
                    except (ValueError, TypeError):
                        cleaned[key] = stripped
                else:
                    cleaned[key] = stripped if stripped else None
            else:
                cleaned[key] = value
        return cleaned

    # -------------------------------------------------------------------------
    # Validate_import helper methods
    # -------------------------------------------------------------------------

    def _get_existing_trips(self, tenant: str, vehicle_id: int) -> list:
        """Fetch existing trips for the vehicle from DB for continuity/duplicate checks."""
        try:
            query = """
                SELECT trip_date, start_odometer, end_odometer
                FROM zzp_trips
                WHERE administration = %s AND vehicle_id = %s AND is_cancelled = 0
                ORDER BY trip_date, start_odometer
            """
            result = self.db.execute_query(query, (tenant, vehicle_id), fetch=True)
            return result if result else []
        except DatabaseError as e:
            logger.warning("Failed to fetch existing trips for validation: %s", e)
            return []

    def _get_trip_categories(self, tenant: str) -> Optional[List[str]]:
        """Get configured trip categories from parameter_service."""
        if self.parameter_service:
            try:
                categories = self.parameter_service.get_param(
                    "zzp_ritten", "trip_categories", tenant=tenant
                )
                if categories:
                    return categories
            except Exception:
                pass
        return None

    def _get_trip_purposes(self, tenant: str) -> Optional[List[str]]:
        """Get configured trip purposes from parameter_service."""
        if self.parameter_service:
            try:
                purposes = self.parameter_service.get_param(
                    "zzp_ritten", "trip_purposes", tenant=tenant
                )
                if purposes:
                    return purposes
            except Exception:
                pass
        return None

    @staticmethod
    def _validate_required_fields(row: dict) -> None:
        """Check that all required fields are present and non-empty."""
        for field in REQUIRED_IMPORT_FIELDS:
            value = row.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                row["_messages"].append(f"Verplicht veld ontbreekt: {field}")
                row["_status"] = "error"

    @staticmethod
    def _normalize_date(date_str: str) -> Optional[str]:
        """Try to parse and normalize a date string to YYYY-MM-DD format.

        Accepts:
            - YYYY-MM-DD (ISO)
            - DD-MM-YYYY (Dutch)
            - DD/MM/YYYY (Dutch alt)

        Returns:
            Normalized date string (YYYY-MM-DD) or None if invalid.
        """
        if not date_str or not isinstance(date_str, str):
            return None

        date_str = date_str.strip()

        # Try ISO format: YYYY-MM-DD
        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
            try:
                parts = date_str.split("-")
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= month <= 12 and 1 <= day <= 31 and year >= 1900:
                    return date_str
            except (ValueError, IndexError):
                pass

        # Try DD-MM-YYYY
        if len(date_str) == 10 and date_str[2] == "-" and date_str[5] == "-":
            try:
                parts = date_str.split("-")
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= month <= 12 and 1 <= day <= 31 and year >= 1900:
                    return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                pass

        # Try DD/MM/YYYY
        if len(date_str) == 10 and date_str[2] == "/" and date_str[5] == "/":
            try:
                parts = date_str.split("/")
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= month <= 12 and 1 <= day <= 31 and year >= 1900:
                    return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                pass

        return None

    def _validate_date_format(self, row: dict) -> None:
        """Validate and normalize the trip_date field."""
        date_value = row.get("trip_date")
        if date_value is None:
            # Already caught by required fields check
            row["_normalized_date"] = "9999-99-99"
            return

        normalized = self._normalize_date(str(date_value))
        if normalized:
            row["trip_date"] = normalized
            row["_normalized_date"] = normalized
        else:
            row["_messages"].append(
                f"Ongeldig datumformaat: '{date_value}' "
                "(verwacht: YYYY-MM-DD, DD-MM-YYYY, of DD/MM/YYYY)"
            )
            row["_status"] = "error"
            row["_normalized_date"] = "9999-99-99"

    @staticmethod
    def _validate_odometer_values(row: dict) -> None:
        """Validate that end_odometer > start_odometer."""
        start = row.get("start_odometer")
        end = row.get("end_odometer")

        # Only validate if both are numeric
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            # Non-numeric odometers — will be caught as error if they're strings
            if start is not None and not isinstance(start, (int, float)):
                row["_messages"].append(
                    f"Ongeldige km-stand (begin): '{start}' is geen getal"
                )
                row["_status"] = "error"
            if end is not None and not isinstance(end, (int, float)):
                row["_messages"].append(
                    f"Ongeldige km-stand (eind): '{end}' is geen getal"
                )
                row["_status"] = "error"
            return

        if end <= start:
            row["_messages"].append(
                f"Eind km-stand ({end}) moet groter zijn dan begin km-stand ({start})"
            )
            row["_status"] = "error"

    @staticmethod
    def _validate_category_purpose(
        row: dict,
        valid_categories: Optional[List[str]],
        valid_purposes: Optional[List[str]],
    ) -> None:
        """Warn if category or purpose not in configured lists."""
        if valid_categories:
            category = row.get("trip_category")
            if category and category not in valid_categories:
                row["_messages"].append(
                    f"Onbekende categorie: '{category}' "
                    f"(verwacht: {', '.join(valid_categories)})"
                )
                if row["_status"] == "ok":
                    row["_status"] = "warning"

        if valid_purposes:
            purpose = row.get("trip_purpose")
            if purpose and purpose not in valid_purposes:
                row["_messages"].append(
                    f"Onbekend doel: '{purpose}' "
                    f"(verwacht: {', '.join(valid_purposes)})"
                )
                if row["_status"] == "ok":
                    row["_status"] = "warning"

    @staticmethod
    def _check_internal_continuity(rows: list) -> None:
        """Check odometer continuity within the import set.

        Each row's start_odometer should match the previous row's end_odometer.
        Issues a warning (not error) for discontinuities.
        """
        prev_end = None
        for row in rows:
            start = row.get("start_odometer")
            if prev_end is not None and isinstance(start, (int, float)):
                if start != prev_end:
                    gap = start - prev_end
                    row["_messages"].append(
                        f"Km-stand niet aansluitend binnen import: "
                        f"verwacht {prev_end}, gevonden {start} "
                        f"(verschil: {gap} km)"
                    )
                    if row["_status"] == "ok":
                        row["_status"] = "warning"

            end = row.get("end_odometer")
            if isinstance(end, (int, float)):
                prev_end = end

    @staticmethod
    def _check_db_continuity(rows: list, last_existing_odometer: Optional[int]) -> None:
        """Check odometer continuity against existing DB trips.

        The first row's start_odometer should match the last existing trip's end_odometer.
        Issues a warning (not error).
        """
        if last_existing_odometer is None:
            return

        # Find the first row with a valid start_odometer
        for row in rows:
            start = row.get("start_odometer")
            if isinstance(start, (int, float)):
                if start != last_existing_odometer:
                    gap = start - last_existing_odometer
                    row["_messages"].append(
                        f"Km-stand sluit niet aan op bestaande ritten: "
                        f"laatste eindstand in DB is {last_existing_odometer}, "
                        f"import begint op {start} (verschil: {gap} km)"
                    )
                    if row["_status"] == "ok":
                        row["_status"] = "warning"
                break

    @staticmethod
    def _check_duplicates(rows: list, existing_set: set) -> None:
        """Flag rows that appear to be duplicates of existing trips in the DB.

        A duplicate is defined as same date + start_odometer + end_odometer.
        Issues a warning (not error).
        """
        for row in rows:
            date = row.get("trip_date")
            start = row.get("start_odometer")
            end = row.get("end_odometer")

            if (
                date
                and isinstance(start, (int, float))
                and isinstance(end, (int, float))
            ):
                key = (str(date), int(start), int(end))
                if key in existing_set:
                    row["_messages"].append(
                        "Mogelijk duplicaat: rit met dezelfde datum en km-standen "
                        "bestaat al in de database"
                    )
                    if row["_status"] == "ok":
                        row["_status"] = "warning"
