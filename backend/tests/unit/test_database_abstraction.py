"""
Property-based tests for the Database Abstraction Layer.

Uses hypothesis to verify correctness properties from the design document.
Feature: database-abstraction-layer

Requirements: 2.5, 7.2, 7.3, 7.5
Reference: .kiro/specs/database-abstraction-layer/design.md
"""

import sys
import os
import pytest
from unittest.mock import Mock
from hypothesis import given, strategies as st, settings

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import db_exceptions
import mysql.connector


# ---------------------------------------------------------------------------
# Helper: wrap_mysql_exception
# ---------------------------------------------------------------------------

def wrap_mysql_exception(exc: Exception) -> db_exceptions.DatabaseError:
    """Map a mysql.connector exception to the corresponding agnostic exception.

    Mapping:
        mysql.connector.IntegrityError   -> db_exceptions.IntegrityError
        mysql.connector.OperationalError -> db_exceptions.OperationalError
        mysql.connector.InterfaceError   -> db_exceptions.ConnectionError
        mysql.connector.Error (others)   -> db_exceptions.DatabaseError

    The original error_code and message are preserved, and __cause__ is set.
    """
    error_code = getattr(exc, 'errno', None)
    message = str(exc)

    if isinstance(exc, mysql.connector.IntegrityError):
        return db_exceptions.IntegrityError(message, error_code=error_code, original_error=exc)
    elif isinstance(exc, mysql.connector.OperationalError):
        return db_exceptions.OperationalError(message, error_code=error_code, original_error=exc)
    elif isinstance(exc, mysql.connector.InterfaceError):
        return db_exceptions.ConnectionError(message, error_code=error_code, original_error=exc)
    else:
        return db_exceptions.DatabaseError(message, error_code=error_code, original_error=exc)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

error_code_st = st.one_of(st.none(), st.integers(min_value=1000, max_value=9999))
message_st = st.text(min_size=1, max_size=200)

# Strategy that generates (mysql_exc_class, expected_agnostic_class) pairs
mysql_error_mapping_st = st.sampled_from([
    (mysql.connector.IntegrityError, db_exceptions.IntegrityError),
    (mysql.connector.OperationalError, db_exceptions.OperationalError),
    (mysql.connector.InterfaceError, db_exceptions.ConnectionError),
    (mysql.connector.Error, db_exceptions.DatabaseError),
])


# ---------------------------------------------------------------------------
# Property 2: Error wrapping preserves type, code, and cause
# Feature: database-abstraction-layer, Property 2
# Validates: Requirements 2.5, 7.2, 7.3, 7.5
# ---------------------------------------------------------------------------

class TestErrorWrappingPreservesTypCodeAndCause:
    """For any mysql.connector exception, wrapping preserves type mapping, error_code, and __cause__."""

    @settings(max_examples=100)
    @given(
        mapping=mysql_error_mapping_st,
        msg=message_st,
        errno=error_code_st,
    )
    def test_wrapping_maps_to_correct_agnostic_type(self, mapping, msg, errno):
        """**Validates: Requirements 2.5, 7.2, 7.3, 7.5**"""
        mysql_cls, expected_cls = mapping

        # Create the mysql.connector exception
        mysql_exc = mysql_cls(msg=msg, errno=errno)

        # Wrap it
        agnostic_exc = wrap_mysql_exception(mysql_exc)

        # Type mapping is correct
        assert isinstance(agnostic_exc, expected_cls), (
            f"Expected {expected_cls.__name__}, got {type(agnostic_exc).__name__}"
        )

        # All agnostic exceptions are also DatabaseError
        assert isinstance(agnostic_exc, db_exceptions.DatabaseError)

    @settings(max_examples=100)
    @given(
        mapping=mysql_error_mapping_st,
        msg=message_st,
        errno=error_code_st,
    )
    def test_wrapping_preserves_error_code(self, mapping, msg, errno):
        """**Validates: Requirements 2.5, 7.2, 7.3, 7.5**"""
        mysql_cls, _ = mapping
        mysql_exc = mysql_cls(msg=msg, errno=errno)

        agnostic_exc = wrap_mysql_exception(mysql_exc)

        # error_code matches what the mysql.connector exception actually stores
        # (mysql.connector defaults errno to -1 when None is passed)
        assert agnostic_exc.error_code == getattr(mysql_exc, 'errno', None)

    @settings(max_examples=100)
    @given(
        mapping=mysql_error_mapping_st,
        msg=message_st,
        errno=error_code_st,
    )
    def test_wrapping_preserves_cause(self, mapping, msg, errno):
        """**Validates: Requirements 2.5, 7.2, 7.3, 7.5**"""
        mysql_cls, _ = mapping
        mysql_exc = mysql_cls(msg=msg, errno=errno)

        agnostic_exc = wrap_mysql_exception(mysql_exc)

        # __cause__ is set to the original exception
        assert agnostic_exc.__cause__ is mysql_exc
        assert agnostic_exc.original_error is mysql_exc

    @settings(max_examples=100)
    @given(
        mapping=mysql_error_mapping_st,
        msg=message_st,
        errno=error_code_st,
    )
    def test_wrapping_preserves_message(self, mapping, msg, errno):
        """**Validates: Requirements 2.5, 7.2, 7.3, 7.5**"""
        mysql_cls, _ = mapping
        mysql_exc = mysql_cls(msg=msg, errno=errno)

        agnostic_exc = wrap_mysql_exception(mysql_exc)

        # Message is preserved in the agnostic exception
        assert str(mysql_exc) in str(agnostic_exc) or str(agnostic_exc) == str(mysql_exc)


from unittest.mock import patch, MagicMock, PropertyMock
from contextlib import contextmanager


# ---------------------------------------------------------------------------
# Property 1: Transaction context manager commits on success, rolls back on failure
# Feature: database-abstraction-layer, Property 1
# Validates: Requirements 2.2
# ---------------------------------------------------------------------------

# Strategy for generating random query sequences
query_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1, max_size=50
)
query_sequence_st = st.lists(query_st, min_size=1, max_size=5)


class TestTransactionContextManager:
    """Property 1: Transaction context manager commits on success and rolls back on failure."""

    def _create_mock_db(self):
        """Create a DatabaseManager with mocked internals for testing."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()

        # Patch DatabaseManager to avoid real DB connections
        with patch('database.DatabaseManager._scalability_manager', None), \
             patch('database.DatabaseManager._use_scalability', False), \
             patch('database.DatabaseManager._legacy_pool', None), \
             patch('database.DatabaseManager._use_legacy_pool', False):
            db = __import__('database').DatabaseManager.__new__(
                __import__('database').DatabaseManager
            )
            db.test_mode = True
            db.config = {
                'host': 'localhost', 'user': 'test',
                'password': 'test', 'database': 'test', 'port': 3306
            }

        return db, mock_cursor, mock_conn

    @settings(max_examples=50)
    @given(queries=query_sequence_st)
    def test_transaction_commits_on_success(self, queries):
        """**Validates: Requirements 2.2**

        For any sequence of queries that all succeed, the transaction
        context manager SHALL commit the transaction.
        """
        import database

        mock_cursor = MagicMock()
        mock_conn = MagicMock()

        @contextmanager
        def mock_get_cursor(pool_type='primary'):
            yield mock_cursor, mock_conn

        db = MagicMock(spec=database.DatabaseManager)
        db.get_cursor = mock_get_cursor
        db.transaction = database.DatabaseManager.transaction.__get__(db, database.DatabaseManager)

        with db.transaction() as (cursor, conn):
            for q in queries:
                cursor.execute(q)

        # Commit must have been called
        mock_conn.commit.assert_called_once()
        # Rollback must NOT have been called
        mock_conn.rollback.assert_not_called()

    @settings(max_examples=50)
    @given(
        queries=query_sequence_st,
        fail_index=st.integers(min_value=0),
    )
    def test_transaction_rolls_back_on_failure(self, queries, fail_index):
        """**Validates: Requirements 2.2**

        For any sequence of queries where one raises an exception,
        the transaction context manager SHALL rollback and re-raise.
        """
        import database

        fail_index = fail_index % len(queries)

        mock_cursor = MagicMock()
        mock_conn = MagicMock()

        @contextmanager
        def mock_get_cursor(pool_type='primary'):
            yield mock_cursor, mock_conn

        db = MagicMock(spec=database.DatabaseManager)
        db.get_cursor = mock_get_cursor
        db.transaction = database.DatabaseManager.transaction.__get__(db, database.DatabaseManager)

        with pytest.raises(RuntimeError):
            with db.transaction() as (cursor, conn):
                for i, q in enumerate(queries):
                    if i == fail_index:
                        raise RuntimeError("simulated failure")
                    cursor.execute(q)

        # Rollback must have been called
        mock_conn.rollback.assert_called_once()
        # Commit must NOT have been called
        mock_conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Property 7: Connection pool resource management
# Feature: database-abstraction-layer, Property 7
# Validates: Requirements 8.4
# ---------------------------------------------------------------------------

class TestConnectionPoolResourceManagement:
    """Property 7: Connection pool resource management.

    For any sequence of get_cursor() usages (success or exception),
    the underlying connection SHALL be closed/returned when the context exits.
    """

    @settings(max_examples=50)
    @given(should_fail=st.booleans())
    def test_connection_closed_on_legacy_path(self, should_fail):
        """**Validates: Requirements 8.4**

        On the legacy (non-scalability-manager) path, connection.close()
        is called whether the operation succeeds or raises.
        """
        import database

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        db = database.DatabaseManager.__new__(database.DatabaseManager)
        db.test_mode = True
        db.config = {
            'host': 'localhost', 'user': 'test',
            'password': 'test', 'database': 'test', 'port': 3306
        }

        with patch.object(type(db), '_scalability_manager', new_callable=PropertyMock, return_value=None), \
             patch.object(db, 'get_connection', return_value=mock_conn):

            if should_fail:
                with pytest.raises(RuntimeError):
                    with db.get_cursor() as (cursor, conn):
                        raise RuntimeError("simulated failure")
            else:
                with db.get_cursor() as (cursor, conn):
                    pass

        # Connection must always be closed (returned to pool)
        mock_conn.close.assert_called_once()
        # Cursor must always be closed
        mock_cursor.close.assert_called_once()

    @settings(max_examples=50)
    @given(should_fail=st.booleans())
    def test_cursor_closed_on_scalability_path(self, should_fail):
        """**Validates: Requirements 8.4**

        On the scalability manager path, cursor.close() is called
        whether the operation succeeds or raises.
        """
        import database

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_sm = MagicMock()

        @contextmanager
        def mock_get_db_conn(pool_type):
            yield mock_conn

        mock_sm.get_database_connection = mock_get_db_conn
        mock_sm.record_request_metrics = MagicMock()

        db = database.DatabaseManager.__new__(database.DatabaseManager)
        db.test_mode = True
        db.config = {
            'host': 'localhost', 'user': 'test',
            'password': 'test', 'database': 'test', 'port': 3306
        }

        # We need to patch at the class level since get_cursor reads from the class
        original_sm = database.DatabaseManager._scalability_manager
        try:
            database.DatabaseManager._scalability_manager = mock_sm

            if should_fail:
                with pytest.raises(RuntimeError):
                    with db.get_cursor() as (cursor, conn):
                        raise RuntimeError("simulated failure")
            else:
                with db.get_cursor() as (cursor, conn):
                    pass

            # Cursor must always be closed
            mock_cursor.close.assert_called_once()
        finally:
            database.DatabaseManager._scalability_manager = original_sm


# ---------------------------------------------------------------------------
# Unit tests for DatabaseManager enhancements
# Feature: database-abstraction-layer
# Requirements: 3.4, 9.1
# ---------------------------------------------------------------------------

class TestExecuteDdl:
    """Test execute_ddl() delegates correctly to execute_query()."""

    def test_execute_ddl_delegates_to_execute_query(self):
        """execute_ddl() should call execute_query(statement, fetch=False, commit=True)."""
        import database

        db = database.DatabaseManager.__new__(database.DatabaseManager)
        db.execute_query = MagicMock(return_value=42)

        result = db.execute_ddl("CREATE TABLE test (id INT)")

        db.execute_query.assert_called_once_with(
            "CREATE TABLE test (id INT)", fetch=False, commit=True
        )
        assert result == 42

    def test_execute_ddl_passes_through_return_value(self):
        """execute_ddl() should return whatever execute_query() returns."""
        import database

        db = database.DatabaseManager.__new__(database.DatabaseManager)
        db.execute_query = MagicMock(return_value=1)

        result = db.execute_ddl("ALTER TABLE test ADD COLUMN name VARCHAR(255)")
        assert result == 1


class TestBackwardCompatibility:
    """Test backward compatibility of existing public API signatures."""

    def test_execute_query_signature(self):
        """execute_query accepts (query, params, fetch, commit, pool_type)."""
        import database
        import inspect

        sig = inspect.signature(database.DatabaseManager.execute_query)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'query' in params
        assert 'params' in params
        assert 'fetch' in params
        assert 'commit' in params
        assert 'pool_type' in params

    def test_execute_batch_queries_signature(self):
        """execute_batch_queries accepts (queries_with_params, commit)."""
        import database
        import inspect

        sig = inspect.signature(database.DatabaseManager.execute_batch_queries)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'queries_with_params' in params
        assert 'commit' in params

    def test_get_connection_signature(self):
        """get_connection accepts (pool_type)."""
        import database
        import inspect

        sig = inspect.signature(database.DatabaseManager.get_connection)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'pool_type' in params

    def test_get_cursor_signature(self):
        """get_cursor accepts (dictionary, pool_type)."""
        import database
        import inspect

        sig = inspect.signature(database.DatabaseManager.get_cursor)
        params = list(sig.parameters.keys())
        assert 'self' in params
        assert 'dictionary' in params
        assert 'pool_type' in params

    def test_exception_types_re_exported(self):
        """DatabaseError, IntegrityError, ConnectionError, OperationalError are importable from database module."""
        import database

        assert hasattr(database, 'DatabaseError')
        assert hasattr(database, 'IntegrityError')
        assert hasattr(database, 'ConnectionError')
        assert hasattr(database, 'OperationalError')

        # Verify they are the correct classes
        assert database.DatabaseError is db_exceptions.DatabaseError
        assert database.IntegrityError is db_exceptions.IntegrityError
        assert database.ConnectionError is db_exceptions.ConnectionError
        assert database.OperationalError is db_exceptions.OperationalError

    def test_transaction_method_exists(self):
        """DatabaseManager has a transaction() method."""
        import database

        assert hasattr(database.DatabaseManager, 'transaction')
        assert callable(getattr(database.DatabaseManager, 'transaction'))

    def test_execute_ddl_method_exists(self):
        """DatabaseManager has an execute_ddl() method."""
        import database

        assert hasattr(database.DatabaseManager, 'execute_ddl')
        assert callable(getattr(database.DatabaseManager, 'execute_ddl'))
