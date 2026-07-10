"""
Closure-aware helpers for balance sheet cumulation.

Balance sheet accounts (VW='N') cumulate across years. When a fiscal year is
closed, an OpeningBalance record is created in the following year that carries
forward all prior history. To avoid double-counting (summing both the closed
year's raw transactions AND the OpeningBalance that summarizes them), all
balance queries must start cumulation at `last_closed_year + 1`.

This module provides `get_closure_aware_start_year()` — the single source of
truth for determining the correct lower bound year for balance sheet queries.

Pattern:
    start_year = get_closure_aware_start_year(db, administration)
    if start_year:
        filtered = df[(df["jaar"] >= start_year) & (df["jaar"] <= target_year)]
    else:
        # No closures — full cumulation from the beginning
        filtered = df[df["jaar"] <= target_year]

Edge cases handled by callers (verified in Task 3.7):
    - Target year is closed: callers use `jaar == target_year` (existing closed-year
      branch in actuals_routes per_year mode). This helper's return value is irrelevant
      for that branch since the closed-year check takes precedence.
    - Future year exclusion: all callers preserve `jaar <= target_year` (or `jaar < year`
      for beginning balance) as the upper bound. The start_year only adds a LOWER bound.
    - start_year == target_year: results in `jaar >= X AND jaar <= X` → single year only.
      This is correct (e.g., year 2024 closed, querying 2025 gets only 2025 data).
    - target_year < start_year: degenerate case that shouldn't occur in practice (would
      mean querying a year older than the last closed year). The per_year closed-year
      branch handles this; in non-per_year mode it returns an empty result set (safe).
    - No closures: returns None, callers fall back to `jaar <= target_year`.
    - Database error: returns None with warning log (safe fallback).
"""

import logging


def get_closure_aware_start_year(db, administration):
    """Determine the first year to include in balance sheet cumulation.

    Queries the year_closure_status table to find the most recently closed year
    for the given administration. Returns last_closed_year + 1, which is the
    year that contains the OpeningBalance records carrying forward all prior
    history.

    Args:
        db: DatabaseManager instance (uses db.execute_query)
        administration: tenant identifier string

    Returns:
        int: The start year for cumulation (last_closed_year + 1), or
        None: When no closures exist (caller should fall back to full cumulation
              with jaar <= target_year)

    Examples:
        >>> start_year = get_closure_aware_start_year(db, "admin1")
        >>> # If year 2023 is closed: returns 2024
        >>> # If no years closed: returns None
    """
    try:
        query = """
            SELECT MAX(year) as max_year
            FROM year_closure_status
            WHERE administration = %s
        """
        rows = db.execute_query(query, [administration])

        if rows and rows[0]["max_year"] is not None:
            return int(rows[0]["max_year"]) + 1

        return None

    except Exception as e:
        logging.warning(
            f"Could not determine closure-aware start year for {administration}: {e}. "
            f"Falling back to full cumulation (no lower bound)."
        )
        return None
