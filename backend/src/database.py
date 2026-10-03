import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import pooling

from database_banking_queries import DatabaseBankingQueriesMixin
from db_exceptions import (
    ConnectionError,
    DatabaseError,
    IntegrityError,
    OperationalError,
)

# Pin backend/.env so this import-time load never picks up the repo-root .env
# (prevents the documented AWS-credential clobber + non-deterministic config).
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager(DatabaseBankingQueriesMixin):
    _scalability_manager = None
    _use_scalability = True
    _legacy_pool = None
    _use_legacy_pool = True

    def __init__(self, test_mode=False):
        # NOTE (test-environment spec, tasks 12 & 15): the `test_mode` parameter is
        # PRESERVED for backward compatibility — many call sites across the
        # codebase still pass `test_mode=...` (their removal is Phase-3 tasks
        # 16/17). As of task 12 it NO LONGER selects a `testfinance` schema: the
        # schema is always `finance`, and TEST vs PROD is distinguished by the
        # RESOLVED connection target (host/credentials), not by the schema name
        # (Req 9.2, 9.3). Task 15 (Step 1 shim, Req 2.6) completes the neutralization:
        # `test_mode` has NO effect on environment/target selection — the active
        # environment is selected solely by `APP_ENV`. The attribute is still stored
        # because other code/tests read `db.test_mode`.
        self.test_mode = test_mode

        # Task 15.2 (Req 2.6): emit a ONE-TIME deprecation warning only when a caller
        # explicitly relies on the old selector (passes a TRUTHY `test_mode`). The
        # default `test_mode=False` must stay silent — otherwise every plain
        # `DatabaseManager()` would spam the log. The environment is now selected by
        # `APP_ENV` (schema is always `finance`); `test_mode` is ignored.
        if test_mode:
            logger.warning(
                "`test_mode` is deprecated and ignored for environment selection; "
                "the environment is selected by `APP_ENV` (schema is always "
                "'finance'). This parameter will be removed in a later release."
            )

        self.config = self._resolve_mysql_config()

        # Try to initialize scalability manager
        self._initialize_scalability_manager()

        # Fallback to legacy pool if scalability manager fails
        if (
            not DatabaseManager._scalability_manager
            and DatabaseManager._use_legacy_pool
            and not DatabaseManager._legacy_pool
        ):
            try:
                pool_config = self.config.copy()
                pool_config.update(
                    {
                        "pool_name": "legacy_pool",
                        "pool_size": 10,  # Conservative size for a single small Railway instance
                        "pool_reset_session": True,
                        "autocommit": False,
                    }
                )
                DatabaseManager._legacy_pool = pooling.MySQLConnectionPool(
                    **pool_config
                )
                logger.info("✅ Legacy connection pool initialized with 10 connections")
            except Exception as e:
                logger.warning(
                    f"⚠️ Legacy connection pool failed, using direct connections: {e}"
                )
                DatabaseManager._use_legacy_pool = False

    # Schema is ALWAYS "finance" for both TEST and PRODUCTION (Req 9.2). The two
    # environments are told apart by their RESOLVED connection target
    # (host/port/user/password), never by the schema name. The legacy
    # `TEST_DB_NAME`/`testfinance` switch has been removed (task 12).
    _SCHEMA = "finance"

    def _resolve_mysql_config(self):
        """Build the MySQL connection config from the resolved environment target.

        Task 12 (test-environment spec, Req 9.1-9.6): the database is no longer
        chosen by a `TEST_DB_NAME`/`testfinance` switch. The schema is ALWAYS
        ``finance`` for both TEST and PRODUCTION; the two are distinguished by the
        resolved connection TARGET (host/port/user/password), not the schema name.

        Target resolution:
        - When ``APP_ENV`` is set, the Environment_Resolver maps it to a
          ``ResolvedConfig.mysql`` (:class:`ResolvedDbTarget`) that names the env
          vars holding this environment's connection values (``host_ref`` etc.).
          Those referenced vars are dereferenced from the environment here — the
          concrete credentials always come from env vars (Req 9.4), never source.
        - A referenced var that is absent falls back to the legacy ``DB_*`` chain,
          so local dev (Docker) and Railway both keep connecting unchanged.
        - When ``APP_ENV`` is unset (e.g. unit tests whose conftest seeds ``DB_*``
          but not ``APP_ENV``), resolution is skipped and the legacy ``DB_*`` chain
          is used directly. ``__init__`` must stay deployable, so a missing
          ``APP_ENV`` is NOT fail-fast here (the fail-fast selector lives in the
          app bootstrap / Consistency_Guard, not in every DatabaseManager).

        In all paths the schema is forced to ``finance`` and ``testfinance`` is
        never selected.
        """
        resolved_mysql = self._resolve_mysql_target()

        def _ref(ref_name, *fallback_names, default=""):
            """Dereference an env-var reference, else the legacy fallback chain."""
            if ref_name:
                value = os.getenv(ref_name)
                if value is not None:
                    return value
            for name in fallback_names:
                value = os.getenv(name)
                if value is not None:
                    return value
            return default

        host_ref = resolved_mysql.host_ref if resolved_mysql else None
        port_ref = resolved_mysql.port_ref if resolved_mysql else None
        user_ref = resolved_mysql.user_ref if resolved_mysql else None
        password_ref = resolved_mysql.password_ref if resolved_mysql else None

        host = _ref(
            host_ref, "DB_HOST", "RAILWAY_PRIVATE_DOMAIN", default="localhost"
        )
        user = _ref(user_ref, "DB_USER", "MYSQL_USER", default="root")
        password = _ref(password_ref, "DB_PASSWORD", "MYSQL_PASSWORD", default="")
        port = _ref(port_ref, "DB_PORT", default="3306")

        return {
            "host": host,
            "user": user,
            "password": password,
            # Schema is ALWAYS the resolved schema `finance` (Req 9.2) — never
            # `testfinance`; the TEST/PROD distinction is the target, not the name.
            "database": self._SCHEMA,
            "port": int(port),
        }

    def _resolve_mysql_target(self):
        """Return the resolved ``ResolvedDbTarget`` for the active APP_ENV, or None.

        Returns ``None`` (so the legacy ``DB_*`` chain is used) when ``APP_ENV`` is
        unset or the environment package cannot be resolved — keeping the
        constructor deployable in every context (including the unit-test suite,
        whose conftest seeds ``DB_*`` but not necessarily ``APP_ENV``). This method
        performs NO database I/O and never raises for a missing ``APP_ENV``.
        """
        raw_app_env = os.getenv("APP_ENV")
        if not raw_app_env or raw_app_env.strip() == "":
            return None
        try:
            from environment.app_env import parse_app_env
            from environment.environment_definition import ENVIRONMENT_DEFINITION
            from environment.resolver import resolve

            app_env = parse_app_env(raw_app_env)
            return resolve(app_env, ENVIRONMENT_DEFINITION).mysql
        except Exception as e:  # pragma: no cover - defensive, stays deployable
            logger.warning(
                "⚠️ Could not resolve MySQL target from APP_ENV=%r; "
                "falling back to DB_* env vars (schema still 'finance'): %s",
                raw_app_env,
                e,
            )
            return None

    def _initialize_scalability_manager(self):
        """Initialize scalability manager for advanced connection pooling"""
        if (
            DatabaseManager._scalability_manager is None
            and DatabaseManager._use_scalability
        ):
            try:
                # Import here to avoid circular imports
                from scalability_manager import get_scalability_manager

                DatabaseManager._scalability_manager = get_scalability_manager(
                    self.config
                )
                logger.info(
                    "🚀 Scalability Manager initialized for database connections"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ Scalability Manager initialization failed, using legacy pool: {e}"
                )
                DatabaseManager._use_scalability = False

    def _get_db_config(self):
        """Get database configuration for SQLAlchemy"""
        return self.config

    def _get_connection(self, pool_type="primary"):
        """Get a RAW, caller-owned database connection. PRIVATE/INTERNAL.

        This accessor is private (Req 6.1): external modules MUST NOT call it.
        The only in-tree callers are internal to the DatabaseManager hierarchy
        (``get_cursor()``'s legacy fallback here, and the ``STRDatabase`` subclass
        constructor). Every other site uses the context-managed public API
        (``get_cursor`` / ``transaction`` / ``execute_query`` /
        ``execute_batch_queries`` / ``execute_ddl``).

        Callers of this accessor use the raw pattern
        ``conn = self._get_connection(); conn.cursor(...); ...; conn.close()`` and
        therefore own the connection's lifecycle.

        The scalability manager is DELIBERATELY bypassed here. Its
        ``get_database_connection()`` returns ``AdvancedConnectionPool.get_connection``,
        which is a ``@contextmanager`` that CLOSES the connection in its ``finally``
        when the ``with`` block exits. Returning it from this raw accessor either
        hands back a ``_GeneratorContextManager`` (no ``.cursor``) — the regression
        that turned every raw-pattern endpoint into an HTTP 500 — or, if we entered
        it here, an already-closed connection. Neither is a usable raw connection.
        The context-managed path is still used correctly by ``get_cursor`` /
        ``transaction`` inside a ``with`` block; only this raw accessor skips it.

        ``pool_type`` is accepted for signature compatibility but has no effect on
        the raw path (the legacy pool does not accept a pool type).
        """
        # Prefer the legacy pool: it returns a real pooled connection that the
        # caller closes itself.
        if DatabaseManager._use_legacy_pool and DatabaseManager._legacy_pool:
            try:
                return DatabaseManager._legacy_pool.get_connection()
            except Exception as e:
                logger.warning(
                    f"⚠️ Legacy pool connection failed, using direct connection: {e}"
                )
                DatabaseManager._use_legacy_pool = False

        # Final fallback to direct connection
        return mysql.connector.connect(**self.config)

    @contextmanager
    def transaction(self, pool_type="primary"):
        """Context manager for multi-statement transactions.

        Usage:
            with db.transaction() as (cursor, conn):
                cursor.execute("INSERT ...", params1)
                cursor.execute("UPDATE ...", params2)
            # auto-commits on success, auto-rollbacks on exception
        """
        with self.get_cursor(pool_type=pool_type) as (cursor, conn):
            try:
                yield cursor, conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def get_cursor(self, dictionary=True, pool_type="primary"):
        """Context manager for database operations with scalability improvements"""
        start_time = time.time()

        # Use scalability manager's connection context if available
        if DatabaseManager._scalability_manager:
            _yielded = False
            try:
                with DatabaseManager._scalability_manager.get_database_connection(
                    pool_type
                ) as conn:
                    cursor = conn.cursor(dictionary=dictionary)
                    try:
                        _yielded = True
                        yield cursor, conn
                    except mysql.connector.IntegrityError as e:
                        conn.rollback()
                        raise IntegrityError(
                            str(e),
                            error_code=getattr(e, "errno", None),
                            original_error=e,
                        ) from e
                    except mysql.connector.OperationalError as e:
                        conn.rollback()
                        raise OperationalError(
                            str(e),
                            error_code=getattr(e, "errno", None),
                            original_error=e,
                        ) from e
                    except mysql.connector.InterfaceError as e:
                        conn.rollback()
                        raise ConnectionError(
                            str(e),
                            error_code=getattr(e, "errno", None),
                            original_error=e,
                        ) from e
                    except mysql.connector.Error as e:
                        conn.rollback()
                        raise DatabaseError(
                            str(e),
                            error_code=getattr(e, "errno", None),
                            original_error=e,
                        ) from e
                    except Exception:
                        conn.rollback()
                        raise
                    finally:
                        cursor.close()

                        # Record performance metrics
                        response_time = time.time() - start_time
                        DatabaseManager._scalability_manager.record_request_metrics(
                            response_time
                        )
                return
            except (DatabaseError, IntegrityError, ConnectionError, OperationalError):
                raise
            except Exception as e:
                # Only fall back to legacy if the scalability manager failed during setup
                # (before yield). If user code raised inside the yield, re-raise directly.
                if _yielded:
                    raise
                logger.warning(
                    f"⚠️ Scalability manager cursor failed, falling back: {e}"
                )

        # Fallback to legacy approach
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        try:
            yield cursor, conn
        except mysql.connector.IntegrityError as e:
            conn.rollback()
            raise IntegrityError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except mysql.connector.OperationalError as e:
            conn.rollback()
            raise OperationalError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except mysql.connector.InterfaceError as e:
            conn.rollback()
            raise ConnectionError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except mysql.connector.Error as e:
            conn.rollback()
            raise DatabaseError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @contextmanager
    def get_cursor_only(self, dictionary=True, pool_type="primary"):
        """Cursor-only context manager for READ paths that never touch the connection.

        Identical lifecycle/exception semantics to get_cursor() (it delegates), but
        yields just the cursor so call sites don't unpack an unused conn (prevents
        the recurring RUF059 'unpacked variable conn is never used'). Use get_cursor()
        / transaction() when you DO need conn (commit/rollback).
        """
        with self.get_cursor(dictionary=dictionary, pool_type=pool_type) as (
            cursor,
            _conn,
        ):
            yield cursor

    def execute_query(
        self, query, params=None, fetch=True, commit=False, pool_type="primary"
    ):
        """Execute query with automatic connection management and scalability improvements"""
        # Determine optimal pool type based on query
        if pool_type == "primary" and (
            query.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE", "EXPLAIN"))
        ):
            if "pattern_" in query.lower() or "analytics" in query.lower():
                pool_type = "analytics"
            else:
                pool_type = "readonly"

        try:
            with self.get_cursor(pool_type=pool_type) as (cursor, conn):
                cursor.execute(query, params or ())
                if commit:
                    conn.commit()
                    return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
                return cursor.fetchall() if fetch else None
        except IntegrityError as e:
            # Check for FK constraint violation (errno 1452) — preserve existing behavior
            original = e.original_error or e.__cause__
            errno = e.error_code
            if errno == 1452:
                msg = str(e)
                if "fk_mutaties_debet" in msg:
                    raise ValueError(
                        "Debet account does not exist in the chart of accounts (rekeningschema) "
                        "for this administration. Please check the account number."
                    ) from (original or e)
                elif "fk_mutaties_credit" in msg:
                    raise ValueError(
                        "Credit account does not exist in the chart of accounts (rekeningschema) "
                        "for this administration. Please check the account number."
                    ) from (original or e)
                else:
                    raise ValueError(f"Foreign key constraint violation: {msg}") from (
                        original or e
                    )
            raise
        except mysql.connector.IntegrityError as e:
            # Direct mysql.connector.IntegrityError (not yet wrapped by get_cursor)
            if e.errno == 1452:
                msg = str(e)
                if "fk_mutaties_debet" in msg:
                    raise ValueError(
                        "Debet account does not exist in the chart of accounts (rekeningschema) "
                        "for this administration. Please check the account number."
                    ) from e
                elif "fk_mutaties_credit" in msg:
                    raise ValueError(
                        "Credit account does not exist in the chart of accounts (rekeningschema) "
                        "for this administration. Please check the account number."
                    ) from e
                else:
                    raise ValueError(f"Foreign key constraint violation: {msg}") from e
            raise IntegrityError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except mysql.connector.OperationalError as e:
            raise OperationalError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except mysql.connector.InterfaceError as e:
            raise ConnectionError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e
        except mysql.connector.Error as e:
            raise DatabaseError(
                str(e), error_code=getattr(e, "errno", None), original_error=e
            ) from e

    def execute_ddl(self, statement):
        """Execute a DDL statement (CREATE, ALTER, DROP) with auto-commit.

        For migration scripts that need database-specific DDL.
        """
        return self.execute_query(statement, fetch=False, commit=True)

    def execute_batch_queries(self, queries_with_params, commit=True):
        """Execute multiple queries in batch for better performance"""
        if not queries_with_params:
            return []

        # Use scalability manager for batch processing if available
        if DatabaseManager._scalability_manager:
            try:

                def execute_single_query(query_params):
                    query, params = query_params
                    return self.execute_query(query, params, fetch=False, commit=False)

                results = DatabaseManager._scalability_manager.batch_process_items(
                    queries_with_params, execute_single_query
                )

                # Commit all changes at once
                if commit:
                    with self.get_cursor() as (cursor, conn):
                        conn.commit()

                return results
            except Exception as e:
                logger.warning(
                    f"⚠️ Batch processing failed, falling back to sequential: {e}"
                )

        # Fallback to sequential processing
        results = []
        with self.get_cursor() as (cursor, conn):
            for query, params in queries_with_params:
                cursor.execute(query, params or ())
                results.append(cursor.rowcount)

            if commit:
                conn.commit()

        return results

    def execute_async_query(self, query, params=None, fetch=True, commit=False):
        """Execute query asynchronously using scalability manager"""
        if DatabaseManager._scalability_manager:
            future = DatabaseManager._scalability_manager.submit_async_task(
                "io", self.execute_query, query, params, fetch, commit
            )
            return future
        else:
            # Fallback to synchronous execution
            return self.execute_query(query, params, fetch, commit)

    def create_tables(self):
        self.execute_query(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date DATE,
                description TEXT,
                amount DECIMAL(10,2),
                debet DECIMAL(10,2),
                credit DECIMAL(10,2),
                ref VARCHAR(255),
                ref3 VARCHAR(500),
                ref4 VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
            fetch=False,
            commit=True,
        )

    def get_bnb_lookup(self, lookup_type):
        """Get BnB lookup data based on lookup type (e.g., 'bdc')"""
        return self.execute_query(
            "SELECT * FROM bnblookup WHERE bnblookup.lookUp LIKE %s", (lookup_type,)
        )

    def insert_transactions(self, transactions):
        with self.get_cursor(dictionary=False) as (cursor, conn):
            query = """
                INSERT INTO transactions (date, description, amount, debet, credit, ref, ref3, ref4)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """

            data = [
                (
                    t["date"],
                    t["description"],
                    t["amount"],
                    t["debet"],
                    t["credit"],
                    t.get("ref", ""),
                    t.get("ref3", ""),
                    t.get("ref4", ""),
                )
                for t in transactions
            ]

            cursor.executemany(query, data)
            conn.commit()

    def insert_transaction(self, transaction, table_name="mutaties"):
        """Insert a single transaction into the specified table"""
        administration = transaction.get("Administration") or transaction.get(
            "administration"
        )
        if not administration:
            raise ValueError(
                "Administration is required for tenant-scoped insert into mutaties"
            )

        return self.execute_query(
            f"""INSERT INTO {table_name} 
                (TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, 
                 Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                transaction.get("TransactionNumber", ""),
                transaction.get("TransactionDate", ""),
                transaction.get("TransactionDescription", ""),
                transaction.get("TransactionAmount", 0),
                transaction.get("Debet", ""),
                transaction.get("Credit", ""),
                transaction.get("ReferenceNumber", ""),
                transaction.get("Ref1", ""),
                transaction.get("Ref2", ""),
                transaction.get("Ref3", ""),
                transaction.get("Ref4", ""),
                administration,
            ),
            fetch=False,
            commit=True,
        )

    # Database optimization methods
    def get_migration_manager(self):
        """Get database migration manager"""
        from database_migrations import DatabaseMigration

        return DatabaseMigration(self.test_mode)

    def get_query_optimizer(self):
        """Get query optimizer with caching"""
        from database_migrations import QueryOptimizer

        return QueryOptimizer(self.test_mode)

    def optimize_database(self):
        """Run database optimization"""
        migrator = self.get_migration_manager()
        return migrator.optimize_database()

    def check_indexes(self):
        """Check database indexes"""
        migrator = self.get_migration_manager()
        return migrator.check_indexes()

    def create_recommended_indexes(self):
        """Create recommended indexes"""
        migrator = self.get_migration_manager()
        return migrator.create_recommended_indexes()

    def cleanup_database(self):
        """Run database cleanup"""
        migrator = self.get_migration_manager()
        return migrator.cleanup_database()

    def run_migrations(self):
        """Run pending migrations"""
        migrator = self.get_migration_manager()
        return migrator.run_all_migrations()

    def get_migration_status(self):
        """Get migration status"""
        migrator = self.get_migration_manager()
        return migrator.get_migration_status()

    def cached_query(self, query, params=None, cache_key=None, ttl=None):
        """Execute query with caching"""
        optimizer = self.get_query_optimizer()
        return optimizer.cached_query(query, params, cache_key, ttl)

    def analyze_query(self, query):
        """Analyze query performance"""
        optimizer = self.get_query_optimizer()
        return optimizer.analyze_query(query)

    def optimize_query(self, query):
        """Get query optimization suggestions"""
        optimizer = self.get_query_optimizer()
        return optimizer.optimize_query(query)

    def get_cache_stats(self):
        """Get query cache statistics"""
        optimizer = self.get_query_optimizer()
        return optimizer.get_cache_stats()

    def clear_query_cache(self):
        """Clear query cache"""
        optimizer = self.get_query_optimizer()
        return optimizer.clear_cache()

    # Scalability monitoring and management methods
    def get_scalability_statistics(self):
        """Get comprehensive scalability statistics"""
        if DatabaseManager._scalability_manager:
            return DatabaseManager._scalability_manager.get_comprehensive_statistics()
        else:
            return {
                "scalability_manager": "Not initialized",
                "legacy_pool_active": DatabaseManager._use_legacy_pool,
                "direct_connections": not DatabaseManager._use_legacy_pool,
            }

    def get_scalability_health(self):
        """Get scalability health status"""
        if DatabaseManager._scalability_manager:
            return DatabaseManager._scalability_manager.get_health_status()
        else:
            return {
                "health_score": 50,
                "status": "limited",
                "issues": ["Scalability manager not initialized"],
                "scalability_ready": False,
                "concurrent_user_capacity": "1x baseline",
                "recommendations": [
                    "Initialize scalability manager for 10x improvement"
                ],
            }

    def optimize_for_concurrency(self):
        """Optimize database settings for high concurrency"""
        optimizations = []

        try:
            # Check current connection limits
            max_connections = self.execute_query(
                "SHOW VARIABLES LIKE 'max_connections'"
            )
            if max_connections:
                current_max = int(max_connections[0]["Value"])
                if current_max < 500:
                    optimizations.append(
                        {
                            "setting": "max_connections",
                            "current": current_max,
                            "recommended": 500,
                            "query": "SET GLOBAL max_connections = 500;",
                        }
                    )

            # Check thread cache size
            thread_cache = self.execute_query("SHOW VARIABLES LIKE 'thread_cache_size'")
            if thread_cache:
                current_cache = int(thread_cache[0]["Value"])
                if current_cache < 100:
                    optimizations.append(
                        {
                            "setting": "thread_cache_size",
                            "current": current_cache,
                            "recommended": 100,
                            "query": "SET GLOBAL thread_cache_size = 100;",
                        }
                    )

            # Check query cache
            query_cache = self.execute_query("SHOW VARIABLES LIKE 'query_cache_size'")
            if query_cache:
                current_cache = int(query_cache[0]["Value"])
                if current_cache < 268435456:  # 256MB
                    optimizations.append(
                        {
                            "setting": "query_cache_size",
                            "current": current_cache,
                            "recommended": 268435456,
                            "query": "SET GLOBAL query_cache_size = 268435456;",
                        }
                    )

            return {
                "optimizations_available": len(optimizations),
                "recommendations": optimizations,
                "scalability_impact": "2-3x improvement in concurrent performance",
            }

        except Exception as e:
            logger.error(f"❌ Error checking database optimization: {e}")
            return {
                "error": str(e),
                "optimizations_available": 0,
                "recommendations": [],
            }

    def get_connection_pool_status(self):
        """Get detailed connection pool status"""
        status = {
            "scalability_manager_active": DatabaseManager._scalability_manager
            is not None,
            "legacy_pool_active": DatabaseManager._use_legacy_pool,
            "direct_connections_fallback": not DatabaseManager._use_legacy_pool
            and not DatabaseManager._scalability_manager,
        }

        if DatabaseManager._scalability_manager:
            status["scalability_stats"] = (
                DatabaseManager._scalability_manager.connection_pool.get_pool_statistics()
            )

        return status

    @classmethod
    def shutdown_scalability_manager(cls):
        """Shutdown scalability manager gracefully"""
        if cls._scalability_manager:
            cls._scalability_manager.shutdown()
            cls._scalability_manager = None
            logger.info("✅ Scalability manager shutdown complete")
