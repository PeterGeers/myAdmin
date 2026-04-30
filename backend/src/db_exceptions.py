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
