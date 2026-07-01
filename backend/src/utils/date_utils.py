"""
Date utility functions for normalizing date fields in query results.

This module provides functions to convert Python datetime.date objects
to ISO-8601 formatted strings before JSON serialization, ensuring the
frontend can correctly detect and sort date columns.

Without explicit conversion, Flask's jsonify serializes datetime.date objects
as HTTP date strings (e.g., "Mon, 15 Jan 2024 00:00:00 GMT") which the
frontend's isISODateString() regex cannot match, causing sort failures.
"""

import datetime


def normalize_dates(rows: list[dict], date_fields: list[str]) -> list[dict]:
    """
    Normalize date fields in a list of row dictionaries to ISO-8601 strings.

    Iterates over rows and converts any datetime.date or datetime.datetime
    objects in the specified fields to ISO-8601 date strings (YYYY-MM-DD).

    Behavior:
        - datetime.date objects → .isoformat() (e.g., "2024-01-15")
        - datetime.datetime objects → .date().isoformat() (date-only)
        - None values → unchanged (remain None)
        - String values → unchanged (pass through as-is)
        - Missing fields → skipped (no error)

    Args:
        rows: List of dictionaries from cursor.fetchall() or execute_query().
        date_fields: List of field names that should be normalized.

    Returns:
        The same list (mutated in place) with date fields converted to strings.
    """
    for row in rows:
        for field in date_fields:
            if field not in row:
                continue
            value = row[field]
            if value is None:
                continue
            if isinstance(value, datetime.datetime):
                row[field] = value.date().isoformat()
            elif isinstance(value, datetime.date):
                row[field] = value.isoformat()
    return rows
