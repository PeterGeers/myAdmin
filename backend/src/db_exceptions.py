"""Database-agnostic exception hierarchy.

All application code should catch these exceptions instead of
mysql.connector.Error or any other driver-specific exception.
"""


class DatabaseError(Exception):
    """Base exception for all database errors."""

    def __init__(self, message: str, error_code: int = None, original_error: Exception = None):
        super().__init__(message)
        self.error_code = error_code
        self.original_error = original_error
        if original_error:
            self.__cause__ = original_error


class IntegrityError(DatabaseError):
    """Raised on constraint violations (unique, foreign key, check)."""
    pass


class ConnectionError(DatabaseError):
    """Raised when a database connection cannot be established or is lost."""
    pass


class OperationalError(DatabaseError):
    """Raised on operational issues (timeout, deadlock, server gone)."""
    pass


class ClosedPeriodError(DatabaseError):
    """Raised when transactions target a closed fiscal year.

    Attributes:
        offending_transactions: list of dicts, each with 'transaction' and 'year'
            identifying which transactions fall in closed periods.
    """

    def __init__(self, offending_transactions: list, message: str = None):
        if message is None:
            years = sorted({t['year'] for t in offending_transactions})
            year_str = ', '.join(str(y) for y in years)
            count = len(offending_transactions)
            message = (
                f"{count} transaction(s) target closed fiscal year(s): {year_str}. "
                f"Batch rejected — no transactions were saved."
            )
        super().__init__(message)
        self.offending_transactions = offending_transactions
