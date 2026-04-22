"""
Query Helper Utilities

Provides helper functions for building sargable SQL query conditions.
These helpers convert non-sargable patterns (e.g., YEAR(column)) into
index-friendly date range conditions.
"""


def year_to_date_range(year):
    """Convert a year to sargable date range conditions.

    Returns (start_date, end_date) where:
      start_date = '{year}-01-01'
      end_date = '{year+1}-01-01'

    Usage in SQL:
      WHERE TransactionDate >= %s AND TransactionDate < %s

    This replaces non-sargable YEAR(TransactionDate) = %s patterns,
    allowing MySQL to use indexes on TransactionDate.

    Args:
        year: Year as int or string (will be coerced to int).

    Returns:
        tuple: (start_date, end_date) as strings in 'YYYY-MM-DD' format.

    Raises:
        ValueError: If year cannot be converted to an integer.
    """
    year_int = int(year)
    start_date = f"{year_int}-01-01"
    end_date = f"{year_int + 1}-01-01"
    return (start_date, end_date)


def years_to_date_range_conditions(years):
    """Convert a list of years to sargable date range OR conditions.

    For contiguous years, optimizes to a single range.
    For non-contiguous years, produces individual range conditions.

    Args:
        years: List of years (int or string).

    Returns:
        tuple: (sql_fragment, params) where sql_fragment is a SQL condition
               string using %s placeholders and params is a list of values.

    Raises:
        ValueError: If years list is empty or contains non-integer values.
    """
    if not years:
        raise ValueError("years list must not be empty")

    year_ints = sorted(int(y) for y in years)

    # Check if years are contiguous
    is_contiguous = all(
        year_ints[i] + 1 == year_ints[i + 1]
        for i in range(len(year_ints) - 1)
    )

    if is_contiguous and len(year_ints) > 1:
        # Single range covering all contiguous years
        start_date = f"{year_ints[0]}-01-01"
        end_date = f"{year_ints[-1] + 1}-01-01"
        return ("TransactionDate >= %s AND TransactionDate < %s", [start_date, end_date])

    if len(year_ints) == 1:
        start_date, end_date = year_to_date_range(year_ints[0])
        return ("TransactionDate >= %s AND TransactionDate < %s", [start_date, end_date])

    # Non-contiguous: build OR conditions
    conditions = []
    params = []
    for y in year_ints:
        start_date, end_date = year_to_date_range(y)
        conditions.append("(TransactionDate >= %s AND TransactionDate < %s)")
        params.extend([start_date, end_date])

    sql_fragment = "(" + " OR ".join(conditions) + ")"
    return (sql_fragment, params)
