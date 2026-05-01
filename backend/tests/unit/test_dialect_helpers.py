"""
Property-based tests for SQL dialect helpers.

Uses hypothesis to verify correctness properties from the design document.
Feature: database-abstraction-layer

Properties tested:
    Property 3: JSON dialect helpers produce valid SQL fragments
    Property 4: Date and utility dialect helpers produce valid SQL fragments
    Property 5: Identifier quoting is idempotent
    Property 6: Introspection query generators produce valid SQL containing the target name

Requirements: 4.1–4.4, 5.1–5.6, 6.1–6.4, 12.1–12.3
Reference: .kiro/specs/database-abstraction-layer/design.md
"""

import sys
import os
import pytest
from hypothesis import given, strategies as st, settings

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from dialect_helpers import dialect, MySQLDialect


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid SQL column names: start with a letter, followed by letters/digits/underscores
_column_name_st = st.from_regex(r'[a-zA-Z][a-zA-Z0-9_]{0,30}', fullmatch=True)

# JSON path expressions like $.key, $.nested.key, $.array[0]
_json_path_st = st.from_regex(r'\$\.[a-zA-Z_][a-zA-Z0-9_.]{0,30}', fullmatch=True)

# Positive integers for interval values
_interval_value_st = st.integers(min_value=1, max_value=9999)

# MySQL interval units
_interval_unit_st = st.sampled_from([
    'DAY', 'MONTH', 'YEAR', 'HOUR', 'MINUTE', 'SECOND', 'WEEK', 'QUARTER',
])

# MySQL date format strings (common patterns)
_format_string_st = st.sampled_from([
    '%Y-%m-%d', '%Y-%m', '%d/%m/%Y', '%Y', '%m', '%d',
    '%Y-%m-%d %H:%i:%s', '%H:%i', '%W',
])

# Valid SQL identifier names (table/view names)
_identifier_st = st.from_regex(r'[a-zA-Z][a-zA-Z0-9_]{0,30}', fullmatch=True)

# Value placeholders for json_set
_value_placeholder_st = st.sampled_from(['%s', 'CAST(%s AS JSON)', "'default_value'"])

# JSON value strings for json_contains
_json_value_st = st.sampled_from(["'true'", "'false'", '%s', "CAST(%s AS JSON)", "'\"some_val\"'"])

# Default expression for ifnull
_default_expr_st = st.sampled_from(["0", "'N/A'", "''", "NULL", "0.00"])

# String expressions for str_to_date
_string_expr_st = st.sampled_from(["'2023-01-15'", "%s", "'15/06/2024'", "some_column"])


# ---------------------------------------------------------------------------
# Property 3: JSON dialect helpers produce valid SQL fragments
# Feature: database-abstraction-layer, Property 3
# Validates: Requirements 4.1, 4.2, 4.3, 4.4, 12.1
# ---------------------------------------------------------------------------

class TestJsonDialectHelpersProduceValidSqlFragments:
    """For any valid column name and JSON path, JSON helpers produce
    structurally valid SQL fragments containing the inputs."""

    @settings(max_examples=100)
    @given(column=_column_name_st, path=_json_path_st)
    def test_json_extract_contains_inputs(self, column, path):
        """**Validates: Requirements 4.1, 12.1**"""
        result = dialect.json_extract(column, path)
        assert column in result
        assert path in result
        assert result.startswith("JSON_EXTRACT(")
        assert result.endswith(")")

    @settings(max_examples=100)
    @given(column=_column_name_st, path=_json_path_st)
    def test_json_unquote_extract_contains_inputs(self, column, path):
        """**Validates: Requirements 4.2, 12.1**"""
        result = dialect.json_unquote_extract(column, path)
        assert column in result
        assert path in result
        assert result.startswith("JSON_UNQUOTE(JSON_EXTRACT(")
        assert result.endswith("))")

    @settings(max_examples=100)
    @given(
        column=_column_name_st,
        path=_json_path_st,
        placeholder=_value_placeholder_st,
    )
    def test_json_set_contains_inputs(self, column, path, placeholder):
        """**Validates: Requirements 4.3, 12.1**"""
        result = dialect.json_set(column, path, placeholder)
        assert column in result
        assert path in result
        assert placeholder in result
        assert result.startswith("JSON_SET(COALESCE(")
        assert "'{}'" in result  # NULL-safe default

    @settings(max_examples=100)
    @given(column=_column_name_st, value=_json_value_st)
    def test_json_contains_contains_inputs(self, column, value):
        """**Validates: Requirements 4.4, 12.1**"""
        result = dialect.json_contains(column, value)
        assert column in result
        assert value in result
        assert result.startswith("JSON_CONTAINS(")
        assert result.endswith(")")

    def test_json_extract_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.json_extract('parameters', '$.bank_account') == \
            "JSON_EXTRACT(parameters, '$.bank_account')"

    def test_json_unquote_extract_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.json_unquote_extract('parameters', '$.name') == \
            "JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.name'))"

    def test_json_set_exact_output_default_placeholder(self):
        """Smoke test with default placeholder."""
        assert dialect.json_set('parameters', '$.key') == \
            "JSON_SET(COALESCE(parameters, '{}'), '$.key', %s)"

    def test_json_contains_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.json_contains('parameters', "'true'") == \
            "JSON_CONTAINS(parameters, 'true')"


# ---------------------------------------------------------------------------
# Property 4: Date and utility dialect helpers produce valid SQL fragments
# Feature: database-abstraction-layer, Property 4
# Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 12.2
# ---------------------------------------------------------------------------

class TestDateAndUtilityDialectHelpersProduceValidSqlFragments:
    """For any valid column, interval, unit, and format, date/utility helpers
    produce structurally valid SQL fragments containing the inputs."""

    @settings(max_examples=100)
    @given(column=_column_name_st)
    def test_year_contains_column(self, column):
        """**Validates: Requirements 5.1, 12.2**"""
        result = dialect.year(column)
        assert column in result
        assert result == f"YEAR({column})"

    @settings(max_examples=100)
    @given(column=_column_name_st)
    def test_month_contains_column(self, column):
        """**Validates: Requirements 5.1, 12.2**"""
        result = dialect.month(column)
        assert column in result
        assert result == f"MONTH({column})"

    def test_current_date_returns_curdate(self):
        """**Validates: Requirements 5.2, 12.2**"""
        assert dialect.current_date() == "CURDATE()"

    def test_current_timestamp_returns_now(self):
        """**Validates: Requirements 5.2, 12.2**"""
        assert dialect.current_timestamp() == "NOW()"

    @settings(max_examples=100)
    @given(
        column=_column_name_st,
        interval_value=_interval_value_st,
        interval_unit=_interval_unit_st,
    )
    def test_date_subtract_contains_inputs(self, column, interval_value, interval_unit):
        """**Validates: Requirements 5.3, 12.2**"""
        result = dialect.date_subtract(column, interval_value, interval_unit)
        assert column in result
        assert str(interval_value) in result
        assert interval_unit in result
        assert result.startswith("DATE_SUB(")
        assert "INTERVAL" in result

    @settings(max_examples=100)
    @given(
        column=_column_name_st,
        interval_value=_interval_value_st,
        interval_unit=_interval_unit_st,
    )
    def test_date_add_contains_inputs(self, column, interval_value, interval_unit):
        """**Validates: Requirements 5.3, 12.2**"""
        result = dialect.date_add(column, interval_value, interval_unit)
        assert column in result
        assert str(interval_value) in result
        assert interval_unit in result
        assert result.startswith("DATE_ADD(")
        assert "INTERVAL" in result

    @settings(max_examples=100)
    @given(date1=_column_name_st, date2=_column_name_st)
    def test_date_diff_contains_inputs(self, date1, date2):
        """**Validates: Requirements 5.3, 12.2**"""
        result = dialect.date_diff(date1, date2)
        assert date1 in result
        assert date2 in result
        assert result.startswith("DATEDIFF(")

    @settings(max_examples=100)
    @given(column=_column_name_st, fmt=_format_string_st)
    def test_date_format_contains_inputs(self, column, fmt):
        """**Validates: Requirements 5.5, 12.2**"""
        result = dialect.date_format(column, fmt)
        assert column in result
        assert fmt in result
        assert result.startswith("DATE_FORMAT(")

    @settings(max_examples=100)
    @given(string_expr=_string_expr_st, fmt=_format_string_st)
    def test_str_to_date_contains_inputs(self, string_expr, fmt):
        """**Validates: Requirements 5.6, 12.2**"""
        result = dialect.str_to_date(string_expr, fmt)
        assert string_expr in result
        assert fmt in result
        assert result.startswith("STR_TO_DATE(")

    @settings(max_examples=100)
    @given(expr=_column_name_st, default=_default_expr_st)
    def test_ifnull_contains_inputs(self, expr, default):
        """**Validates: Requirements 5.4, 12.2**"""
        result = dialect.ifnull(expr, default)
        assert expr in result
        assert default in result
        assert result.startswith("IFNULL(")

    def test_date_subtract_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.date_subtract('CURDATE()', 30, 'DAY') == \
            "DATE_SUB(CURDATE(), INTERVAL 30 DAY)"

    def test_date_add_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.date_add('NOW()', 1, 'MONTH') == \
            "DATE_ADD(NOW(), INTERVAL 1 MONTH)"

    def test_date_format_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.date_format('entry_date', '%Y-%m-%d') == \
            "DATE_FORMAT(entry_date, '%Y-%m-%d')"

    def test_str_to_date_exact_output(self):
        """Smoke test with known inputs."""
        assert dialect.str_to_date('%s', '%Y-%m-%d') == \
            "STR_TO_DATE(%s, '%Y-%m-%d')"


# ---------------------------------------------------------------------------
# Property 5: Identifier quoting is idempotent
# Feature: database-abstraction-layer, Property 5
# Validates: Requirements 6.1, 12.3
# ---------------------------------------------------------------------------

class TestIdentifierQuotingIsIdempotent:
    """For any valid identifier name, applying quote_identifier twice
    produces the same result as applying it once."""

    @settings(max_examples=200)
    @given(name=_identifier_st)
    def test_quote_identifier_idempotent(self, name):
        """**Validates: Requirements 6.1, 12.3**"""
        once = dialect.quote_identifier(name)
        twice = dialect.quote_identifier(once)
        assert once == twice, (
            f"quote_identifier is not idempotent: "
            f"once={once!r}, twice={twice!r}"
        )

    @settings(max_examples=200)
    @given(name=_identifier_st)
    def test_quote_identifier_wraps_in_backticks(self, name):
        """**Validates: Requirements 6.1, 12.3**"""
        result = dialect.quote_identifier(name)
        assert result.startswith('`')
        assert result.endswith('`')
        # Inner content should be the stripped name
        assert result[1:-1] == name.strip('`')

    def test_quote_identifier_already_quoted(self):
        """Already-quoted names are returned unchanged."""
        assert dialect.quote_identifier('`my_table`') == '`my_table`'

    def test_quote_identifier_unquoted(self):
        """Unquoted names get backticks added."""
        assert dialect.quote_identifier('my_table') == '`my_table`'

    def test_quote_identifier_triple_application(self):
        """Three applications still produce the same result."""
        name = 'users'
        once = dialect.quote_identifier(name)
        twice = dialect.quote_identifier(once)
        thrice = dialect.quote_identifier(twice)
        assert once == twice == thrice


# ---------------------------------------------------------------------------
# Property 6: Introspection query generators produce valid SQL
# Feature: database-abstraction-layer, Property 6
# Validates: Requirements 6.2, 6.3, 6.4
# ---------------------------------------------------------------------------

class TestIntrospectionQueryGeneratorsProduceValidSql:
    """For any valid table/view name, introspection helpers produce SQL
    strings that contain the target name and are structurally valid."""

    @settings(max_examples=100)
    @given(view_name=_identifier_st)
    def test_get_view_definition_contains_name(self, view_name):
        """**Validates: Requirements 6.2**"""
        result = dialect.get_view_definition(view_name)
        assert view_name in result
        assert result.startswith("SHOW CREATE VIEW ")

    @settings(max_examples=100)
    @given(table_name=_identifier_st)
    def test_describe_table_contains_name(self, table_name):
        """**Validates: Requirements 6.4**"""
        result = dialect.describe_table(table_name)
        assert table_name in result
        assert result.startswith("DESCRIBE ")

    def test_list_tables_returns_valid_sql(self):
        """**Validates: Requirements 6.3**"""
        result = dialect.list_tables()
        assert result == "SHOW FULL TABLES"

    def test_get_view_definition_exact_output(self):
        """Smoke test with known input."""
        assert dialect.get_view_definition('vw_mutaties') == \
            "SHOW CREATE VIEW vw_mutaties"

    def test_describe_table_exact_output(self):
        """Smoke test with known input."""
        assert dialect.describe_table('mutaties') == "DESCRIBE mutaties"


# ---------------------------------------------------------------------------
# Additional: Module-level singleton and class attributes
# ---------------------------------------------------------------------------

class TestDialectSingleton:
    """Verify the module-level singleton is properly configured."""

    def test_dialect_is_mysql_dialect_instance(self):
        assert isinstance(dialect, MySQLDialect)

    def test_dialect_name_is_mysql(self):
        assert dialect.name == "mysql"

    def test_dialect_singleton_identity(self):
        """The module-level dialect is a single shared instance."""
        from dialect_helpers import dialect as dialect2
        assert dialect is dialect2
