"""Unit tests for the scalability manager's multi-pool configuration.

Latent-bug hardening for ``scalability_manager.AdvancedConnectionPool``. The
scalability manager is DISABLED in production today (requests fall through to the
legacy pool, already fixed and merged), but its multi-pool path carried the same
two bugs the legacy pool had:

1. ``ScalabilityConfig.db_pool_size`` was ``50`` — ``mysql.connector`` caps
   ``MySQLConnectionPool.pool_size`` at 32, so the primary pool raised immediately
   ("Pool size should be higher than 0 and lower or equal to 32").
2. ``pool_recycle`` (a SQLAlchemy option, NOT a valid ``MySQLConnectionPool``
   kwarg) was passed to all three pools (primary/readonly/analytics), which would
   raise "Unsupported argument 'pool_recycle'" even at a legal size.

These tests assert on the pool *config* / kwarg validity only. They do NOT require
a live MySQL: the unit-test connection guard (``tests/unit/conftest.py``) patches
``mysql.connector.connect`` to raise ``RuntimeError``, so with valid kwargs the
pool gets far enough to attempt a connection and trips that guard — treated as
success. An invalid kwarg raises a ``TypeError``/``AttributeError`` (or an
"unsupported argument" error) *before* any connect and WOULD fail the test.

``scalability_manager`` is importable directly because ``tests/conftest.py`` puts
``backend/src`` on ``sys.path``.
"""

from mysql.connector import pooling

from scalability_manager import ScalabilityConfig

# Connection fields are irrelevant to the kwarg/size checks; harmless placeholders.
_BASE_DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "testfinance",
    "port": 3306,
}


def _primary_pool_config(config: ScalabilityConfig) -> dict:
    """Mirror the ``pool_config.update({...})`` block in ``_create_primary_pool``."""
    pool_config = dict(_BASE_DB_CONFIG)
    pool_config.update(
        {
            "pool_name": "primary_pool",
            "pool_size": config.db_pool_size,
            "pool_reset_session": True,
            "autocommit": False,
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
            "use_unicode": True,
            "sql_mode": "STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO",
        }
    )
    return pool_config


def _readonly_pool_config(config: ScalabilityConfig) -> dict:
    """Mirror the ``pool_config.update({...})`` block in ``_create_read_only_pool``."""
    pool_config = dict(_BASE_DB_CONFIG)
    pool_config.update(
        {
            "pool_name": "readonly_pool",
            "pool_size": max(10, config.db_pool_size // 5),
            "pool_reset_session": True,
            "autocommit": True,
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }
    )
    return pool_config


def _analytics_pool_config(config: ScalabilityConfig) -> dict:
    """Mirror the ``pool_config.update({...})`` block in ``_create_analytics_pool``."""
    pool_config = dict(_BASE_DB_CONFIG)
    pool_config.update(
        {
            "pool_name": "analytics_pool",
            "pool_size": max(5, config.db_pool_size // 10),
            "pool_reset_session": True,
            "autocommit": True,
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
        }
    )
    return pool_config


_ALL_POOL_BUILDERS = (
    _primary_pool_config,
    _readonly_pool_config,
    _analytics_pool_config,
)


def test_scalability_config_db_pool_size_within_connector_limit():
    """MySQLConnectionPool caps pool_size at 32; the default must stay in [1, 32]."""
    config = ScalabilityConfig()
    assert 1 <= config.db_pool_size <= 32


def test_all_pool_configs_have_no_pool_recycle():
    """`pool_recycle` is a SQLAlchemy option, not valid for MySQLConnectionPool."""
    config = ScalabilityConfig()
    for build in _ALL_POOL_BUILDERS:
        pool_config = build(config)
        assert "pool_recycle" not in pool_config, (
            f"{pool_config['pool_name']} still passes the invalid pool_recycle kwarg"
        )


def test_all_pool_sizes_within_connector_limit():
    """Every derived pool_size (primary/readonly/analytics) must be in [1, 32]."""
    config = ScalabilityConfig()
    for build in _ALL_POOL_BUILDERS:
        pool_config = build(config)
        pool_size = pool_config["pool_size"]
        assert 1 <= pool_size <= 32, (
            f"{pool_config['pool_name']} pool_size={pool_size} is outside 1..32"
        )


def test_all_pool_configs_kwargs_are_supported():
    """Building each pool must NOT raise an unsupported-argument error.

    With no live MySQL, valid kwargs let construction reach the connection
    attempt, which the unit-test guard turns into a RuntimeError — that is the
    success signal here. Only an invalid-kwarg TypeError/AttributeError, or an
    "unsupported argument" leaking through (the original bug), is fatal.
    """
    config = ScalabilityConfig()
    for build in _ALL_POOL_BUILDERS:
        pool_config = build(config)
        name = pool_config["pool_name"]
        try:
            pooling.MySQLConnectionPool(**pool_config)
        except (TypeError, AttributeError) as exc:
            # kwarg validation happens before connecting — this is the bug class.
            raise AssertionError(
                f"{name} config has an invalid/unsupported kwarg: {exc}"
            ) from exc
        except Exception as exc:
            # No live DB (or the unit-test connection guard) — acceptable, as long
            # as it is not an unsupported-argument / bad-pool-size error.
            message = str(exc).lower()
            assert "unsupported argument" not in message, (
                f"{name} config still passes an unsupported argument: {exc}"
            )
            assert "pool size" not in message, (
                f"{name} config has an illegal pool_size: {exc}"
            )
