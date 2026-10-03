"""Regression tests for ``DatabaseManager._get_connection()`` returning a RAW connection.

Regression: since commit ``8631168`` the scalability manager initializes
successfully, and ``get_connection()`` routed the raw path through
``scalability_manager.get_database_connection()``. That method returns
``AdvancedConnectionPool.get_connection()``, which is a ``@contextmanager``.
Returned WITHOUT entering a ``with`` block it is a ``_GeneratorContextManager``,
so callers doing ``conn = db._get_connection(); conn.cursor(...)`` raised
``AttributeError: '_GeneratorContextManager' object has no attribute 'cursor'``
and the route ``except`` turned that into an HTTP 500.

The fix: the raw ``get_connection()`` accessor must bypass the scalability
manager (whose connection is context-managed / auto-closed) and return a
genuinely open, caller-owned connection — from the legacy pool if present,
else via a direct ``mysql.connector.connect``.

These tests are hermetic: no live DB. We build the ``DatabaseManager`` via
``object.__new__`` so ``__init__`` (which would touch the real scalability
manager / pool) never runs, then set only the attributes the method reads.

Validates: Requirements 2.1, 2.2, 3.3, 3.4
"""

import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from database import DatabaseManager


def _bare_manager():
    """A DatabaseManager instance without running __init__ (no real pools)."""
    mgr = object.__new__(DatabaseManager)
    mgr.config = {
        "host": "localhost",
        "user": "root",
        "password": "",
        "database": "testfinance",
        "port": 3306,
    }
    return mgr


@pytest.fixture(autouse=True)
def _reset_class_state():
    """Snapshot and restore DatabaseManager class-level state around each test."""
    saved = (
        DatabaseManager._scalability_manager,
        DatabaseManager._use_scalability,
        DatabaseManager._legacy_pool,
        DatabaseManager._use_legacy_pool,
    )
    yield
    (
        DatabaseManager._scalability_manager,
        DatabaseManager._use_scalability,
        DatabaseManager._legacy_pool,
        DatabaseManager._use_legacy_pool,
    ) = saved


class _StubScalabilityManager:
    """Mimics the real scalability manager's context-managed accessor.

    ``get_database_connection`` returns a ``@contextmanager`` object — exactly
    what caused the regression when returned without a ``with`` block.
    """

    @contextmanager
    def get_database_connection(self, pool_type="primary"):
        conn = MagicMock(name="pooled_conn")
        try:
            yield conn
        finally:
            conn.close()

    def record_request_metrics(self, *_args, **_kwargs):
        pass


def test_get_connection_returns_raw_conn_when_scalability_manager_active():
    """Regression: with the scalability manager active, get_connection() must
    return a real connection (has a callable .cursor), NOT a _GeneratorContextManager.

    Validates: Requirements 2.1, 2.2
    """
    mgr = _bare_manager()
    DatabaseManager._scalability_manager = _StubScalabilityManager()
    DatabaseManager._legacy_pool = None
    DatabaseManager._use_legacy_pool = True

    raw_conn = MagicMock(name="direct_conn")
    with patch("mysql.connector.connect", return_value=raw_conn) as mock_connect:
        conn = mgr._get_connection()

    # The key regression assertions.
    assert type(conn).__name__ != "_GeneratorContextManager"
    assert hasattr(conn, "cursor") and callable(conn.cursor)
    # cursor() must not raise AttributeError (the original failure mode).
    conn.cursor(dictionary=True)
    # Raw path bypassed the scalability manager and used a direct connection.
    mock_connect.assert_called_once_with(**mgr.config)
    assert conn is raw_conn


def test_get_connection_uses_legacy_pool_when_available():
    """When a legacy pool exists, get_connection() returns its raw pooled connection.

    Validates: Requirement 3.3
    """
    mgr = _bare_manager()
    DatabaseManager._scalability_manager = None
    pooled_conn = MagicMock(name="legacy_pooled_conn")
    legacy_pool = MagicMock(name="legacy_pool")
    legacy_pool.get_connection.return_value = pooled_conn
    DatabaseManager._legacy_pool = legacy_pool
    DatabaseManager._use_legacy_pool = True

    with patch("mysql.connector.connect") as mock_connect:
        conn = mgr._get_connection()

    assert conn is pooled_conn
    assert hasattr(conn, "cursor") and callable(conn.cursor)
    legacy_pool.get_connection.assert_called_once_with()
    mock_connect.assert_not_called()


def test_get_connection_legacy_pool_active_bypasses_scalability_manager():
    """Even with the scalability manager active, the raw path must prefer the
    legacy pool (a real connection) over the context-managed accessor.

    Validates: Requirements 2.1, 3.3
    """
    mgr = _bare_manager()
    DatabaseManager._scalability_manager = _StubScalabilityManager()
    pooled_conn = MagicMock(name="legacy_pooled_conn")
    legacy_pool = MagicMock(name="legacy_pool")
    legacy_pool.get_connection.return_value = pooled_conn
    DatabaseManager._legacy_pool = legacy_pool
    DatabaseManager._use_legacy_pool = True

    with patch("mysql.connector.connect") as mock_connect:
        conn = mgr._get_connection()

    assert conn is pooled_conn
    assert type(conn).__name__ != "_GeneratorContextManager"
    mock_connect.assert_not_called()


def test_get_connection_direct_fallback_when_no_pools():
    """With neither scalability manager nor legacy pool, fall back to a direct
    mysql.connector.connect that returns a raw connection.

    Validates: Requirement 3.4
    """
    mgr = _bare_manager()
    DatabaseManager._scalability_manager = None
    DatabaseManager._legacy_pool = None
    DatabaseManager._use_legacy_pool = False

    raw_conn = MagicMock(name="direct_conn")
    with patch("mysql.connector.connect", return_value=raw_conn) as mock_connect:
        conn = mgr._get_connection()

    assert conn is raw_conn
    assert hasattr(conn, "cursor") and callable(conn.cursor)
    mock_connect.assert_called_once_with(**mgr.config)


def test_get_connection_legacy_pool_failure_falls_back_to_direct():
    """If the legacy pool raises, get_connection() falls back to a direct connect
    and still returns a raw connection.

    Validates: Requirement 3.4
    """
    mgr = _bare_manager()
    DatabaseManager._scalability_manager = None
    legacy_pool = MagicMock(name="legacy_pool")
    legacy_pool.get_connection.side_effect = Exception("pool exhausted")
    DatabaseManager._legacy_pool = legacy_pool
    DatabaseManager._use_legacy_pool = True

    raw_conn = MagicMock(name="direct_conn")
    with patch("mysql.connector.connect", return_value=raw_conn) as mock_connect:
        conn = mgr._get_connection()

    assert conn is raw_conn
    assert hasattr(conn, "cursor") and callable(conn.cursor)
    mock_connect.assert_called_once_with(**mgr.config)
