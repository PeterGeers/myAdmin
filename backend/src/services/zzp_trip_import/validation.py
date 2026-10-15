"""Validate-stage helpers for the ZZP trip importer.

Pure, DB-free functions that annotate parsed rows with ``_status`` / ``_messages``:
per-row checks (Excel error markers, required fields, date normalization,
odometer values, category/purpose) and cross-row checks (internal continuity,
DB continuity, duplicate detection). Extracted verbatim from
``zzp_trip_import_service`` — ``TripImportService`` delegates to these.
"""

import datetime

from .constants import REQUIRED_IMPORT_FIELDS, _is_excel_error_marker


def validate_required_fields(row: dict) -> None:
    """Check that all required fields are present and non-empty."""
    for field in REQUIRED_IMPORT_FIELDS:
        value = row.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            row["_messages"].append(f"Verplicht veld ontbreekt: {field}")
            row["_status"] = "error"


def validate_error_markers(row: dict) -> None:
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


def normalize_date(date_value) -> str | None:
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


def validate_date_format(row: dict) -> None:
    """Validate and normalize the trip_date field."""
    date_value = row.get("trip_date")
    if date_value is None:
        # Already caught by required fields check
        row["_normalized_date"] = "9999-99-99"
        return

    # Pass the raw value so an actual datetime/date object reaches the
    # object branch in normalize_date; the isinstance guards there handle
    # both object and string forms.
    normalized = normalize_date(date_value)
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


def validate_odometer_values(row: dict) -> None:
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


def validate_category_purpose(
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


def check_internal_continuity(rows: list) -> None:
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


def check_db_continuity(rows: list, last_existing_odometer: int | None) -> None:
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


def check_duplicates(rows: list, existing_set: set) -> None:
    """Flag rows that appear to be duplicates of existing trips in the DB.

    A duplicate is defined as same date + start_odometer + end_odometer.
    Issues a warning (not error).
    """
    for row in rows:
        date = row.get("trip_date")
        start = row.get("start_odometer")
        end = row.get("end_odometer")

        if date and isinstance(start, (int, float)) and isinstance(end, (int, float)):
            key = (str(date), int(start), int(end))
            if key in existing_set:
                row["_messages"].append(
                    "Mogelijk duplicaat: rit met dezelfde datum en km-standen "
                    "bestaat al in de database"
                )
                if row["_status"] == "ok":
                    row["_status"] = "warning"
