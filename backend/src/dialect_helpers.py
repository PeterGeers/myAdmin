"""SQL dialect helpers for database-agnostic query construction.

Provides database-agnostic SQL fragment generators so application code
never embeds MySQL-specific syntax directly. Each method returns a SQL
string fragment for the configured dialect. The initial implementation
supports MySQL only; adding PostgreSQL later requires implementing the
same interface for a different dialect class.

Usage:
    from dialect_helpers import dialect

    query = f"SELECT {dialect.json_extract('parameters', '$.bank_account')} FROM rekeningschema"

Feature: database-abstraction-layer
Requirements: 4.1–4.4, 5.1–5.6, 6.1–6.4, 12.1–12.3
Reference: .kiro/specs/database-abstraction-layer/design.md — Component 2
"""


class MySQLDialect:
    """MySQL-specific SQL fragment generators.

    Every method is a pure function (static) that takes column names,
    paths, or other SQL identifiers and returns a SQL fragment string
    valid for MySQL 8.0+.
    """

    name = "mysql"

    # --- JSON operations (Requirements 4.1–4.4) ---

    @staticmethod
    def json_extract(column: str, path: str) -> str:
        """Generate ``JSON_EXTRACT(column, 'path')``.

        Args:
            column: Column name containing JSON data.
            path: JSON path expression (e.g. ``'$.bank_account'``).

        Returns:
            SQL fragment string.
        """
        return f"JSON_EXTRACT({column}, '{path}')"

    @staticmethod
    def json_unquote_extract(column: str, path: str) -> str:
        """Generate ``JSON_UNQUOTE(JSON_EXTRACT(column, 'path'))``.

        Extracts a JSON value and removes the surrounding quotes,
        returning a plain text value.

        Args:
            column: Column name containing JSON data.
            path: JSON path expression.

        Returns:
            SQL fragment string.
        """
        return f"JSON_UNQUOTE(JSON_EXTRACT({column}, '{path}'))"

    @staticmethod
    def json_set(column: str, path: str, value_placeholder: str = "%s") -> str:
        """Generate ``JSON_SET(COALESCE(column, '{}'), 'path', value)``.

        Uses COALESCE to handle NULL columns safely, matching the
        existing pattern in the codebase.

        Args:
            column: Column name containing JSON data.
            path: JSON path expression.
            value_placeholder: Placeholder for the value (default ``%s``).

        Returns:
            SQL fragment string.
        """
        return f"JSON_SET(COALESCE({column}, '{{}}'), '{path}', {value_placeholder})"

    @staticmethod
    def json_contains(column: str, value: str) -> str:
        """Generate ``JSON_CONTAINS(column, value)``.

        Args:
            column: Column name containing JSON data.
            value: JSON value or placeholder to check for containment.

        Returns:
            SQL fragment string.
        """
        return f"JSON_CONTAINS({column}, {value})"

    # --- Date operations (Requirements 5.1–5.6) ---

    @staticmethod
    def year(column: str) -> str:
        """Generate ``YEAR(column)``.

        Args:
            column: Column or expression containing a date.

        Returns:
            SQL fragment string.
        """
        return f"YEAR({column})"

    @staticmethod
    def month(column: str) -> str:
        """Generate ``MONTH(column)``.

        Args:
            column: Column or expression containing a date.

        Returns:
            SQL fragment string.
        """
        return f"MONTH({column})"

    @staticmethod
    def current_date() -> str:
        """Generate ``CURDATE()``.

        Returns:
            SQL fragment string for the current date.
        """
        return "CURDATE()"

    @staticmethod
    def current_timestamp() -> str:
        """Generate ``NOW()``.

        Returns:
            SQL fragment string for the current timestamp.
        """
        return "NOW()"

    @staticmethod
    def date_subtract(date_expr: str, interval_value: int, interval_unit: str) -> str:
        """Generate ``DATE_SUB(date_expr, INTERVAL value unit)``.

        Args:
            date_expr: Date expression or column name.
            interval_value: Numeric interval value.
            interval_unit: Interval unit (DAY, MONTH, YEAR, etc.).

        Returns:
            SQL fragment string.
        """
        return f"DATE_SUB({date_expr}, INTERVAL {interval_value} {interval_unit})"

    @staticmethod
    def date_add(date_expr: str, interval_value: int, interval_unit: str) -> str:
        """Generate ``DATE_ADD(date_expr, INTERVAL value unit)``.

        Args:
            date_expr: Date expression or column name.
            interval_value: Numeric interval value.
            interval_unit: Interval unit (DAY, MONTH, YEAR, etc.).

        Returns:
            SQL fragment string.
        """
        return f"DATE_ADD({date_expr}, INTERVAL {interval_value} {interval_unit})"

    @staticmethod
    def date_diff(date1: str, date2: str) -> str:
        """Generate ``DATEDIFF(date1, date2)``.

        Args:
            date1: First date expression.
            date2: Second date expression.

        Returns:
            SQL fragment string.
        """
        return f"DATEDIFF({date1}, {date2})"

    @staticmethod
    def date_format(column: str, format_string: str) -> str:
        """Generate ``DATE_FORMAT(column, 'format')``.

        Args:
            column: Column or expression containing a date.
            format_string: MySQL date format string (e.g. ``'%Y-%m-%d'``).

        Returns:
            SQL fragment string.
        """
        return f"DATE_FORMAT({column}, '{format_string}')"

    @staticmethod
    def str_to_date(string_expr: str, format_string: str) -> str:
        """Generate ``STR_TO_DATE(string_expr, 'format')``.

        Args:
            string_expr: String expression or placeholder to parse.
            format_string: MySQL date format string.

        Returns:
            SQL fragment string.
        """
        return f"STR_TO_DATE({string_expr}, '{format_string}')"

    # --- Utility functions (Requirement 5.4) ---

    @staticmethod
    def ifnull(expr: str, default: str) -> str:
        """Generate ``IFNULL(expr, default)``.

        Args:
            expr: Expression that may be NULL.
            default: Default value when *expr* is NULL.

        Returns:
            SQL fragment string.
        """
        return f"IFNULL({expr}, {default})"

    # --- Identifier quoting (Requirement 6.1) ---

    @staticmethod
    def quote_identifier(name: str) -> str:
        """Quote an identifier with backticks.

        Idempotent — already-quoted names are stripped and re-quoted,
        producing the same result. This prevents double-quoting bugs.

        Args:
            name: SQL identifier (table name, column name, etc.).

        Returns:
            Backtick-quoted identifier string.
        """
        stripped = name.strip('`')
        return f"`{stripped}`"

    # --- Introspection queries (Requirements 6.2–6.4) ---

    @staticmethod
    def get_view_definition(view_name: str) -> str:
        """Return SQL to retrieve a view's CREATE statement.

        Args:
            view_name: Name of the view.

        Returns:
            SQL query string.
        """
        return f"SHOW CREATE VIEW {view_name}"

    @staticmethod
    def list_tables() -> str:
        """Return SQL to list all tables and views in the current database.

        Returns:
            SQL query string.
        """
        return "SHOW FULL TABLES"

    @staticmethod
    def describe_table(table_name: str) -> str:
        """Return SQL to describe a table's columns.

        Args:
            table_name: Name of the table.

        Returns:
            SQL query string.
        """
        return f"DESCRIBE {table_name}"


# Module-level singleton — import this in application code.
# Switching to PostgreSQL later means swapping the class behind this singleton.
dialect = MySQLDialect()
