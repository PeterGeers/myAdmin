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

Structure note: the parse and validate stages are implemented as pure, DB-free
helpers in the ``services.zzp_trip_import`` sub-package (``constants`` /
``parsing`` / ``validation``). ``TripImportService`` owns the DB-bound
orchestration and delegates to those helpers; the ``_``-prefixed static methods
below are kept as thin delegators so the historical public surface (including
``TripImportService._clean_row`` / ``._normalize_date`` and the module-level
constants / ``_SheetSelectionError``) stays importable from this path. This is a
pure split — behavior is unchanged.
"""

import io
import logging

from db_exceptions import DatabaseError
from services.zzp_trip_import import parsing, validation
from services.zzp_trip_import.constants import (
    DEFAULT_COLUMN_MAPPING,
    EXCEL_ERROR_MARKERS,
    REQUIRED_IMPORT_FIELDS,
    TEMPLATE_COLUMNS,
    _is_excel_error_marker,
    _SheetSelectionError,
)

logger = logging.getLogger(__name__)

# Re-exported for a stable public import surface (callers / tests import these
# from ``services.zzp_trip_import_service``).
__all__ = [
    "DEFAULT_COLUMN_MAPPING",
    "EXCEL_ERROR_MARKERS",
    "REQUIRED_IMPORT_FIELDS",
    "TEMPLATE_COLUMNS",
    "TripImportService",
    "_SheetSelectionError",
    "_is_excel_error_marker",
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
        import pandas as pd

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
    # Private helpers — thin delegators to the parse/validate stage modules.
    #
    # These keep the historical ``TripImportService._<name>`` surface stable
    # (callers/tests invoke several of them directly, e.g. ``._clean_row`` and
    # ``._normalize_date``) while the actual logic lives in the pure helpers of
    # the ``services.zzp_trip_import`` sub-package.
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_extension(filename: str) -> str:
        """Extract lowercase file extension from filename (see parsing.get_extension)."""
        return parsing.get_extension(filename)

    @staticmethod
    def _read_dataframe(file_stream, ext: str, required_headers=None):
        """Read file stream into a DataFrame (see parsing.read_dataframe)."""
        return parsing.read_dataframe(file_stream, ext, required_headers)

    @staticmethod
    def _restore_excel_error_markers(df, raw: bytes, sheet_name: str):
        """Recover Excel error-marker strings (see parsing.restore_excel_error_markers)."""
        return parsing.restore_excel_error_markers(df, raw, sheet_name)

    @staticmethod
    def _clean_row(row: dict) -> dict:
        """Clean a parsed row (see parsing.clean_row)."""
        return parsing.clean_row(row)

    # -- Validate_import helper methods ---------------------------------------

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
        """Check required fields present/non-empty (see validation.validate_required_fields)."""
        validation.validate_required_fields(row)

    @staticmethod
    def _validate_error_markers(row: dict) -> None:
        """Flag Excel error-marker cells (see validation.validate_error_markers)."""
        validation.validate_error_markers(row)

    @staticmethod
    def _normalize_date(date_value) -> str | None:
        """Normalize a date value to YYYY-MM-DD (see validation.normalize_date)."""
        return validation.normalize_date(date_value)

    def _validate_date_format(self, row: dict) -> None:
        """Validate and normalize trip_date (see validation.validate_date_format)."""
        validation.validate_date_format(row)

    @staticmethod
    def _validate_odometer_values(row: dict) -> None:
        """Validate end_odometer > start_odometer (see validation.validate_odometer_values)."""
        validation.validate_odometer_values(row)

    @staticmethod
    def _validate_category_purpose(
        row: dict,
        valid_categories: list[str] | None,
        valid_purposes: list[str] | None,
    ) -> None:
        """Warn on unknown category/purpose (see validation.validate_category_purpose)."""
        validation.validate_category_purpose(row, valid_categories, valid_purposes)

    @staticmethod
    def _check_internal_continuity(rows: list) -> None:
        """Odometer continuity within the import (see validation.check_internal_continuity)."""
        validation.check_internal_continuity(rows)

    @staticmethod
    def _check_db_continuity(rows: list, last_existing_odometer: int | None) -> None:
        """Odometer continuity vs DB trips (see validation.check_db_continuity)."""
        validation.check_db_continuity(rows, last_existing_odometer)

    @staticmethod
    def _check_duplicates(rows: list, existing_set: set) -> None:
        """Flag duplicate rows (see validation.check_duplicates)."""
        validation.check_duplicates(rows, existing_set)
