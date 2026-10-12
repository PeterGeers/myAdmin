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

import datetime
import io
import logging

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
    "Klant": "client_name",
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

# Recognized Excel error markers — the cached value Excel saves for a broken or
# unresolved formula cell (e.g. an XLOOKUP / x.zoeken that did not resolve).
# These are never evaluated; they are detected as literal strings and used to
# flag the row with a specific, column-naming error message.
EXCEL_ERROR_MARKERS = {
    "#N/A",
    "#REF!",
    "#VALUE!",
    "#NAME?",
    "#DIV/0!",
    "#NULL!",
    "#NUM!",
}


def _is_excel_error_marker(value) -> bool:
    """Return True when ``value`` is a recognized Excel error marker string.

    Non-strings (including ``None`` for a plain empty cell) are NOT markers, so an
    unresolved formula that reads as empty continues to be handled by the existing
    required-field check. On the stripped string value, this matches the known
    marker set exactly OR the general leading-``#`` Excel error form (starts with
    ``#`` and ends with ``!`` or ``?``), so forms like ``#GETTING_DATA`` or future
    error strings are still caught.

    Args:
        value: A mapped cell value (any type).

    Returns:
        True if the value is an Excel error marker; False otherwise.
    """
    if not isinstance(value, str):
        return False
    v = value.strip()
    if v in EXCEL_ERROR_MARKERS:
        return True
    return v.startswith("#") and v.endswith(("!", "?"))


class _SheetSelectionError(Exception):
    """No worksheet in the workbook carried the required header set.

    Raised by ``TripImportService._read_dataframe`` (Excel branch) when, after
    scanning every sheet in insertion order, none has a stripped column set that
    is a superset of the required headers. ``parse_file`` catches this before the
    generic read-error branch and translates it into a found-vs-expected envelope.

    Attributes:
        found: The columns actually present (first sheet's columns, used as a
            readable representation of what the workbook contained).
        expected: The required header set that no sheet satisfied.
    """

    def __init__(self, found: list[str], expected: set[str]):
        self.found = found
        self.expected = expected
        super().__init__(
            f"No worksheet matched the required headers. "
            f"Found: {found}. Expected (⊆ required): {sorted(expected)}."
        )


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

    def parse_file(
        self, file_stream, filename: str, column_mapping: dict | None = None
    ) -> dict:
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

        # Required file-column headers = mapping keys whose internal field name is
        # a required import field (Datum, Vertrekadres, Bestemming, Begin KM,
        # Eind KM, Categorie, Doel). Klant/Notities are optional and excluded.
        required_headers = {
            file_col
            for file_col, field in mapping.items()
            if field in REQUIRED_IMPORT_FIELDS
        }

        try:
            df = self._read_dataframe(file_stream, ext, required_headers)
        except _SheetSelectionError as e:
            logger.warning(
                "No worksheet with required columns in import file '%s': "
                "found=%s expected=%s",
                filename,
                e.found,
                sorted(e.expected),
            )
            return {
                "success": False,
                "rows": [],
                "total_rows": 0,
                "columns_found": e.found,
                "columns_mapped": [],
                "unmapped_columns": [],
                "error": (
                    "Geen werkblad met de verwachte kolommen gevonden. "
                    f"Gevonden kolommen: {e.found}. "
                    f"Verwachte kolommen: {sorted(required_headers)}."
                ),
            }
        except Exception as e:
            logger.warning("Failed to parse import file '%s': %s", filename, e)
            return {
                "success": False,
                "rows": [],
                "total_rows": 0,
                "columns_found": [],
                "columns_mapped": [],
                "unmapped_columns": [],
                "error": f"Could not read file: {e!s}",
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

    def validate_import(self, tenant: str, vehicle_id: int, rows: list[dict]) -> dict:
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
            existing_set.add(
                (
                    str(trip_date),
                    int(trip.get("start_odometer", 0)),
                    int(trip.get("end_odometer", 0)),
                )
            )

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

        # Phase 1: Per-row validation (error markers, required fields, date, odometer)
        for row in annotated_rows:
            self._validate_error_markers(row)
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
        self, tenant: str, vehicle_id: int, rows: list[dict], created_by: str
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
        # Klant (client_name) length guard (Req 2.8): a value longer than 255
        # characters cannot be persisted. Flag the offending row as an error with
        # a message naming the 255-char limit so it is excluded from the commit
        # set below; the batch is NOT aborted — every other valid row still
        # commits. This runs before the valid/error split so flagged rows drop
        # out and are counted as skipped.
        for row in rows:
            client_name = row.get("client_name")
            if isinstance(client_name, str) and len(client_name) > 255:
                row["_status"] = "error"
                messages = row.setdefault("_messages", [])
                messages.append(
                    f"Klant mag maximaal 255 tekens bevatten "
                    f"(ingevoerd: {len(client_name)} tekens)."
                )

        # Separate valid rows from error rows
        valid_rows = [r for r in rows if r.get("_status") != "error"]
        skipped = len(rows) - len(valid_rows)

        if not valid_rows:
            logger.info(
                "Import for tenant=%s vehicle_id=%d: no valid rows to import "
                "(skipped=%d)",
                tenant,
                vehicle_id,
                skipped,
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
                trip_category, trip_purpose, client_name, project_name, notes,
                route_description, is_gap_fill, is_cancelled, version, created_by
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
            with self.db.transaction() as (cursor, _conn):
                for row in valid_rows:
                    # Trim whitespace on the persisted Klant value; a blank or
                    # empty cell persists as NULL (Req 2.1, 2.7).
                    raw_client_name = row.get("client_name")
                    if isinstance(raw_client_name, str):
                        stripped_client_name = raw_client_name.strip()
                        client_name = stripped_client_name or None
                    else:
                        client_name = raw_client_name

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
                        client_name,
                        row.get("project_name"),
                        row.get("notes"),
                        row.get("route_description"),
                        False,  # is_gap_fill
                        False,  # is_cancelled
                        1,  # version
                        created_by,
                    )
                    cursor.execute(insert_query, params)
                    trip_id = cursor.lastrowid

                    # Write audit log entry
                    audit_params = (tenant, trip_id, 1, created_by)
                    cursor.execute(audit_query, audit_params)

                    imported += 1

            # Seed route presets from the committed rows (Req 6.1-6.4). This runs
            # AFTER the transaction above has committed successfully (D2): preset
            # learning is NEVER done inside the per-row insert, so a preset
            # failure can never roll back a committed trip or the import. Only
            # the committed non-error rows (``valid_rows``) are seeded here; error
            # rows were already excluded above and are skipped entirely (Req 6.1).
            self._seed_route_presets(tenant, valid_rows)

            logger.info(
                "Import committed for tenant=%s vehicle_id=%d: imported=%d, skipped=%d",
                tenant,
                vehicle_id,
                imported,
                skipped,
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
                tenant,
                vehicle_id,
                e,
            )
            return {
                "success": False,
                "imported": 0,
                "skipped": skipped,
                "errors": [f"Database error during import: {e!s}"],
            }

    def _seed_route_presets(self, tenant: str, committed_rows: list[dict]) -> None:
        """Seed route presets from committed non-error import rows (Req 6.1-6.4).

        Called once, AFTER ``commit_import`` has committed the trip batch (D2), so
        a preset failure can never roll back a committed trip or the import. For
        each committed non-error row this calls
        ``RoutePresetService.increment_usage`` exactly once for that row's
        from-address/to-address pair, carrying the row's category/purpose and the
        generated distance as preset metadata (Req 6.1). Normalization of the
        from/to pair for matching (case-insensitive, trimmed) is handled inside
        ``RoutePresetService`` (Req 6.2, 6.3).

        Each call is isolated in its own ``try/except``: if learning raises for a
        row, the failure is logged as a warning and a NON-FATAL note is attached
        to that row's ``_messages`` — the committed trip and the import result are
        left untouched (Req 6.4). A failure on one row never prevents the
        remaining rows from being seeded.

        Args:
            tenant: Administration/tenant identifier.
            committed_rows: The non-error rows that were committed by this import.
        """
        from services.zzp_route_preset_service import RoutePresetService

        preset_service = RoutePresetService(self.db, self.parameter_service)

        for row in committed_rows:
            start_address = row.get("start_address")
            end_address = row.get("end_address")

            try:
                start_odometer = row.get("start_odometer")
                end_odometer = row.get("end_odometer")
                typical_distance_km = None
                if isinstance(start_odometer, int) and isinstance(end_odometer, int):
                    typical_distance_km = end_odometer - start_odometer

                preset_service.increment_usage(
                    tenant,
                    start_address,
                    end_address,
                    default_category=row.get("trip_category"),
                    default_purpose=row.get("trip_purpose"),
                    typical_distance_km=typical_distance_km,
                )
            except Exception as exc:
                # Non-fatal: the trip is already committed. Log and annotate the
                # row, but never roll back the committed trip or the import (Req 6.4).
                logger.warning(
                    "Route preset learning failed for committed import row "
                    "(tenant=%s, %r -> %r): %s",
                    tenant,
                    start_address,
                    end_address,
                    exc,
                )
                messages = row.setdefault("_messages", [])
                messages.append(
                    "Rit is geïmporteerd, maar het bijwerken van de "
                    "routesuggestie is niet gelukt."
                )

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
    def _read_dataframe(file_stream, ext: str, required_headers=None) -> pd.DataFrame:
        """Read file stream into a pandas DataFrame based on extension.

        For Excel files, scans all worksheets (in insertion order) and selects the
        first sheet whose stripped column set is a superset of ``required_headers``.
        This handles workbooks where a decoy/summary sheet precedes the data sheet.
        CSV files are single-sheet and ignore ``required_headers`` entirely.

        Args:
            file_stream: File-like object with the data.
            ext: File extension (e.g., ".csv", ".xlsx").
            required_headers: Optional set of file-column headers that the chosen
                worksheet must contain. If falsy, the Excel branch defensively
                returns the first sheet (old behavior).

        Returns:
            pandas DataFrame with the file contents (the selected sheet for Excel).

        Raises:
            ValueError: If extension is unsupported.
            _SheetSelectionError: If no Excel worksheet matches ``required_headers``.
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
            # Buffer the bytes once so we can read with pandas AND re-read with
            # openpyxl to recover Excel error-marker cells (see below).
            raw = file_stream.read()

            # Read ALL sheets as an ordered name->df dict (insertion order).
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, dtype=str)

            # Defensive: no required headers → preserve old first-sheet behavior.
            if not required_headers:
                sheet_name = next(iter(sheets))
                return TripImportService._restore_excel_error_markers(
                    sheets[sheet_name], raw, sheet_name
                )

            # Select the first sheet whose stripped headers ⊇ required_headers.
            for sheet_name, sheet_df in sheets.items():
                stripped = {str(c).strip() for c in sheet_df.columns}
                if set(required_headers).issubset(stripped):
                    return TripImportService._restore_excel_error_markers(
                        sheet_df, raw, sheet_name
                    )

            # No sheet matched — report the first sheet's columns as "found".
            first_df = next(iter(sheets.values()))
            found = [str(c).strip() for c in first_df.columns]
            raise _SheetSelectionError(found=found, expected=set(required_headers))
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

    @staticmethod
    def _restore_excel_error_markers(
        df: pd.DataFrame, raw: bytes, sheet_name: str
    ) -> pd.DataFrame:
        """Recover Excel error-marker strings that pandas coerced to NaN.

        A broken/unresolved formula cell (e.g. an XLOOKUP / ``x.zoeken`` that did
        not resolve) is stored by Excel as an *error-type* cell whose cached value
        is a marker like ``#N/A`` or ``#REF!``. ``pd.read_excel`` reads every
        error-type cell as ``NaN`` regardless of ``keep_default_na``/``na_values``,
        so the marker never survives to the DataFrame. openpyxl, however, exposes
        the literal marker string for such cells (``data_type == "e"``).

        This helper re-reads the selected worksheet with openpyxl and writes the
        marker string back into ``df`` at any cell position where pandas produced a
        null, so the downstream row-level error-marker check can detect it. Formulas
        are NEVER evaluated — only the cached marker string Excel saved is restored.
        Genuine empty cells remain null (openpyxl yields ``None`` for them), so they
        still fall through to the required-field check.

        Args:
            df: The DataFrame pandas produced for the selected sheet.
            raw: The full workbook bytes.
            sheet_name: Name of the selected worksheet.

        Returns:
            The same DataFrame, with error-marker strings restored in place.
        """
        try:
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
            try:
                if sheet_name not in wb.sheetnames:
                    return df
                ws = wb[sheet_name]
                # Row 1 is the header; data starts at worksheet row 2, which maps
                # to DataFrame positional index 0.
                for excel_row_idx, ws_row in enumerate(
                    ws.iter_rows(min_row=2), start=0
                ):
                    if excel_row_idx >= len(df.index):
                        break
                    for col_pos, cell in enumerate(ws_row):
                        if col_pos >= len(df.columns):
                            break
                        if cell.data_type == "e" and isinstance(cell.value, str):
                            # pandas gave NaN for this error cell; restore the marker.
                            df.iat[excel_row_idx, col_pos] = cell.value
            finally:
                wb.close()
        except Exception as exc:
            # Marker recovery is best-effort; never fail the whole read because of
            # it. Without recovery, an error cell simply stays null and is caught
            # by the required-field check (prior behavior).
            logger.debug("Could not restore Excel error markers: %s", exc)
        return df

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

    def _get_trip_categories(self, tenant: str) -> list[str] | None:
        """Get configured trip categories from parameter_service."""
        if self.parameter_service:
            try:
                categories = self.parameter_service.get_param(
                    "zzp_ritten", "trip_categories", tenant=tenant
                )
                if categories:
                    return categories
            except Exception as exc:
                # Optional config; fall back to None (no category constraint).
                logger.debug("Could not read trip_categories param: %s", exc)
        return None

    def _get_trip_purposes(self, tenant: str) -> list[str] | None:
        """Get configured trip purposes from parameter_service."""
        if self.parameter_service:
            try:
                purposes = self.parameter_service.get_param(
                    "zzp_ritten", "trip_purposes", tenant=tenant
                )
                if purposes:
                    return purposes
            except Exception as exc:
                # Optional config; fall back to None (no purpose constraint).
                logger.debug("Could not read trip_purposes param: %s", exc)
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
    def _validate_error_markers(row: dict) -> None:
        """Flag the row when any mapped cell carries an Excel error marker.

        A broken/unresolved formula (XLOOKUP / ``x.zoeken``) leaves an Excel error
        marker (``#N/A``, ``#REF!``, …) as the cell's cached value. Rather than let
        it masquerade as a generic required-field/format error, flag the row
        ``error`` with a specific message naming the column (internal field name)
        and the marker. Formulas are NEVER evaluated — only the cached marker string
        is inspected. A plain empty/``None`` cell is not a marker, so it still falls
        through to the required-field check.

        Only mapped internal field names are inspected; ``_``-prefixed helper keys
        (``_row_number`` / ``_status`` / ``_messages`` / ``_normalized_date``) are
        skipped.

        Args:
            row: An annotated row dict (carries ``_status`` / ``_messages``).
        """
        for field, value in row.items():
            if field.startswith("_"):
                continue
            if _is_excel_error_marker(value):
                marker = value.strip()
                row["_messages"].append(
                    f"Formulewaarde niet berekend: '{marker}' in kolom {field}"
                )
                row["_status"] = "error"

    @staticmethod
    def _normalize_date(date_value) -> str | None:
        """Try to parse and normalize a date value to YYYY-MM-DD format.

        Accepts a datetime/date object or a string. For strings, detects the
        separator and validates numeric ranges rather than relying on fixed
        string length/positions, so non-zero-padded components are accepted.
        A trailing time component (whitespace- or 'T'-separated) is discarded,
        keeping only the date portion; no year inference and no timezone/time
        semantics are applied (the year is always present).

        Accepts:
            - datetime/date objects (Excel-valued dates) -> ISO date portion
            - ISO strings carrying a time component ("2026-05-05 00:00:00",
              "2026-05-05T00:00:00") -> date portion only
            - YYYY-M-D / YYYY-MM-DD (ISO)
            - D-M-YYYY / DD-MM-YYYY (Dutch)
            - D/M/YYYY / DD/MM/YYYY (Dutch alt)
          each zero-padded or not.

        Returns:
            Normalized date string (YYYY-MM-DD) or None if invalid.
        """
        if not date_value:
            return None

        # datetime/date object -> ISO date portion directly. datetime.datetime
        # is a subclass of datetime.date, so this single check covers both and
        # .strftime works on both. No time/timezone semantics are applied.
        if isinstance(date_value, datetime.date):
            return date_value.strftime("%Y-%m-%d")

        if not isinstance(date_value, str):
            return None

        date_str = date_value.strip()

        # Strip a trailing time component by taking the leading date token
        # split on whitespace or 'T':
        #   "2026-05-05 00:00:00" -> "2026-05-05"
        #   "2026-05-05T00:00:00" -> "2026-05-05"
        # A pure date string (no time) is unaffected, so surface-(b) behavior
        # is identical.
        date_str = date_str.replace("T", " ").split()[0] if date_str else date_str

        # Choose the separator: '-' takes precedence, then '/'. Reject when
        # neither is present. This replaces the previous fixed length/position
        # guards so non-zero-padded components are accepted.
        if "-" in date_str:
            sep = "-"
        elif "/" in date_str:
            sep = "/"
        else:
            return None

        parts = date_str.split(sep)
        if len(parts) != 3:
            # Rejects missing-year forms like "5-5" (2 parts).
            return None
        if not all(part and part.isdigit() for part in parts):
            # Rejects empty and non-numeric components ("5-mei").
            return None

        # Infer ordering: a 4-digit first component is ISO (YYYY-M-D),
        # otherwise it is the Dutch day-month-year ordering.
        if len(parts[0]) == 4:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])

        # Numeric-range validation (no year inference).
        if 1 <= month <= 12 and 1 <= day <= 31 and year >= 1900:
            return f"{year:04d}-{month:02d}-{day:02d}"

        return None

    def _validate_date_format(self, row: dict) -> None:
        """Validate and normalize the trip_date field."""
        date_value = row.get("trip_date")
        if date_value is None:
            # Already caught by required fields check
            row["_normalized_date"] = "9999-99-99"
            return

        # Pass the raw value so an actual datetime/date object reaches the
        # object branch in _normalize_date; the isinstance guards there handle
        # both object and string forms.
        normalized = self._normalize_date(date_value)
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
        valid_categories: list[str] | None,
        valid_purposes: list[str] | None,
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
            if (
                prev_end is not None
                and isinstance(start, (int, float))
                and start != prev_end
            ):
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
    def _check_db_continuity(rows: list, last_existing_odometer: int | None) -> None:
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
