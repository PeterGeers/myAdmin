"""Parse-stage helpers for the ZZP trip importer.

Pure, DB-free functions that turn an uploaded file stream into cleaned row
dicts: extension detection, DataFrame reading with Excel multi-sheet selection,
Excel error-marker recovery, and per-row value cleaning. Extracted verbatim
from ``zzp_trip_import_service`` — ``TripImportService`` delegates to these.
"""

import io
import logging

import pandas as pd

from .constants import _SheetSelectionError

logger = logging.getLogger(__name__)


def get_extension(filename: str) -> str:
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


def read_dataframe(file_stream, ext: str, required_headers=None) -> pd.DataFrame:
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
            return restore_excel_error_markers(sheets[sheet_name], raw, sheet_name)

        # Select the first sheet whose stripped headers ⊇ required_headers.
        for sheet_name, sheet_df in sheets.items():
            stripped = {str(c).strip() for c in sheet_df.columns}
            if set(required_headers).issubset(stripped):
                return restore_excel_error_markers(sheet_df, raw, sheet_name)

        # No sheet matched — report the first sheet's columns as "found".
        first_df = next(iter(sheets.values()))
        found = [str(c).strip() for c in first_df.columns]
        raise _SheetSelectionError(found=found, expected=set(required_headers))
    else:
        raise ValueError(f"Unsupported file extension: {ext}")


def restore_excel_error_markers(
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
            for excel_row_idx, ws_row in enumerate(ws.iter_rows(min_row=2), start=0):
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


def clean_row(row: dict) -> dict:
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
