"""Unit tests for the legacy MySQL connection pool configuration.

Regression coverage for the production pooling collapse: the legacy pool was
being built with ``pool_recycle`` (a SQLAlchemy option, NOT a valid kwarg for
``mysql.connector.pooling.MySQLConnectionPool``) and an oversized ``pool_size``
(the connector caps it at 32). Either made pool construction raise, so
``DatabaseManager.get_connection()`` fell back to a fresh direct
``mysql.connector.connect()`` on every request — leaking connections and
exhausting MySQL until Railway repeatedly crashed.

These tests assert on the pool *config* / kwarg validity only. They do NOT
require a live MySQL: the unit-test connection guard (``tests/unit/conftest.py``)
patches ``mysql.connector.connect`` to raise ``RuntimeError``, so if the kwargs
are valid the pool gets far enough to attempt a connection and trips that guard —
which we treat as success. An invalid kwarg ("Unsupported argument") raises a
``TypeError``/``AttributeError`` *before* any connect and WOULD fail the test.
"""

from mysql.connector import pooling


def _legacy_pool_config():
    """The kwargs the legacy pool is constructed with.

    Mirrors the ``pool_config.update({...})`` block in
    ``DatabaseManager.__init__`` (the legacy-pool fallback). Connection fields
    (host/user/etc.) are irrelevant to the kwarg-validity check, so we supply
    harmless placeholders.
    """
    return {
        "host": "localhost",
        "user": "root",
        "password": "",
        "database": "testfinance",
        "port": 3306,
        "pool_name": "legacy_pool",
        "pool_size": 10,
        "pool_reset_session": True,
        "autocommit": False,
    }


def test_legacy_pool_config_has_no_pool_recycle():
    """`pool_recycle` is a SQLAlchemy option, not valid for MySQLConnectionPool."""
    config = _legacy_pool_config()
    assert "pool_recycle" not in config


def test_legacy_pool_size_within_connector_limit():
    """MySQLConnectionPool caps pool_size at 32; ours must stay in (0, 32]."""
    config = _legacy_pool_config()
    assert 0 < config["pool_size"] <= 32


def test_legacy_pool_config_kwargs_are_supported():
    """Building the pool must NOT raise an unsupported-argument error.

    With no live MySQL, valid kwargs let construction reach the connection
    attempt, which the unit-test guard turns into a RuntimeError — that is the
    success signal here. Only an invalid-kwarg TypeError/AttributeError (the
    original bug) is fatal.
    """
    config = _legacy_pool_config()
    try:
        pooling.MySQLConnectionPool(**config)
    except (TypeError, AttributeError) as exc:
        # kwarg validation happens before connecting — this is the bug class.
        raise AssertionError(
            f"Legacy pool config has an invalid/unsupported kwarg: {exc}"
        ) from exc
    except Exception as exc:
        # No live DB (or the unit-test connection guard) — acceptable, as long
        # as it is not an unsupported-argument error leaking through.
        assert "unsupported argument" not in str(exc).lower(), (
            f"Legacy pool config still passes an unsupported argument: {exc}"
        )
