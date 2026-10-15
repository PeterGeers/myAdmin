"""Constants and shared signals for the ZZP trip importer.

Column mappings, the required-field set, recognized Excel error markers, the
downloadable-template columns, and the ``_SheetSelectionError`` signal used by
the parse stage. Extracted verbatim from ``zzp_trip_import_service`` so the
public module path can re-export them unchanged.
"""

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

    Raised by the Excel branch of the DataFrame reader when, after scanning every
    sheet in insertion order, none has a stripped column set that is a superset of
    the required headers. ``parse_file`` catches this before the generic
    read-error branch and translates it into a found-vs-expected envelope.

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
