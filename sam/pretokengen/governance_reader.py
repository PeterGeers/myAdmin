"""
S4 D2 — the read-only governance seam for the PreTokenGen Lambda.

This module is the single, small, testable seam between the Lambda handler and
MySQL. It does two things and nothing else:

1. :func:`resolve_db_config` — resolve the DB connection settings from **explicit
   environment variables**, **fail-fast** (raise :class:`GovernanceConfigError`
   if any required var is missing/blank). No silent fallback to ``localhost`` /
   ``root`` / a default database.
2. :class:`GovernanceReader` — read a user's ``user_tenant_roles`` and the active
   ``tenant_modules`` for the tenants involved, **read-only** (parameterized
   SELECTs only, zero writes), via the workspace ``DatabaseManager``.

Why an explicit, fail-fast config (R2.5, foreshadowing R2.5/T12)
----------------------------------------------------------------
The Lambda runs in AWS with **no ambient project ``.env``**, and this repo carries
conflicting ``.env`` DB_HOST values (repo-root ``DB_HOST=mysql`` for in-Docker vs
``backend/.env`` ``DB_HOST=localhost`` for host runs). ``DatabaseManager``'s own
constructor is convenient for the app because it falls back to ``localhost`` /
``root`` / ``finance`` when a var is unset — but that convenience is a **hazard**
here: a missing var could silently resolve the Lambda against the *wrong*
datastore. So this seam resolves the config itself, up front, and refuses to
proceed on a missing var. It then hands the fully-resolved values to
``DatabaseManager`` via a scoped ``os.environ`` patch so the manager sees exactly
the values we validated (and nothing ambient).

Testability (T12 / T13 slot in here)
-------------------------------------
The DB read is entirely behind :class:`GovernanceReader`, whose only I/O is
``DatabaseManager.execute_query(..., fetch=True)``. Unit tests (T13) inject a fake
``DatabaseManager`` (a stub exposing ``execute_query``) so they can assert the
reads are parameterized and read-only (``fetch=True``, never ``commit=True``)
without a live DB. The fail-fast config (T12) is exercised by driving
:func:`resolve_db_config` with missing env vars.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

# The explicit env vars this Lambda REQUIRES for its MySQL connection. These are
# intentionally the S4-specific, unambiguous names — not the app's DB_HOST/etc.
# with their dangerous defaults — so the Lambda's datastore is never guessed.
REQUIRED_DB_ENV_VARS: tuple[str, ...] = (
    "ENTITLEMENT_DB_HOST",
    "ENTITLEMENT_DB_PORT",
    "ENTITLEMENT_DB_USER",
    "ENTITLEMENT_DB_PASSWORD",
    "ENTITLEMENT_DB_NAME",
)


class GovernanceConfigError(RuntimeError):
    """Raised when required DB config is missing/blank (fail-fast, R2.5).

    Never caught-and-defaulted here — a missing datastore setting must surface
    loudly rather than resolve entitlement against the wrong database.
    """


@dataclass(frozen=True)
class DbConfig:
    """Fully-resolved, validated MySQL connection settings for the Lambda."""

    host: str
    port: int
    user: str
    password: str
    database: str


def resolve_db_config(env: Mapping[str, str] | None = None) -> DbConfig:
    """Resolve + validate the Lambda's MySQL config from explicit env vars.

    Fail-fast (R2.5): every var in :data:`REQUIRED_DB_ENV_VARS` must be present
    and non-blank. A missing/blank var raises :class:`GovernanceConfigError` — we
    never fall back to ``localhost`` / ``root`` / a default database, so the
    Lambda can never silently read the wrong datastore.

    Args:
        env: The environment mapping to read (defaults to :data:`os.environ`).
            Injectable so T12/T13 can drive it without mutating the process env.

    Returns:
        A validated :class:`DbConfig`.

    Raises:
        GovernanceConfigError: If any required var is missing/blank, or the port
            is not an integer.
    """
    env = os.environ if env is None else env

    missing = [name for name in REQUIRED_DB_ENV_VARS if not (env.get(name) or "").strip()]
    if missing:
        raise GovernanceConfigError(
            "Missing required DB config for the PreTokenGen Lambda: "
            f"{', '.join(sorted(missing))}. Refusing to fall back to a default "
            "datastore (no-dangerous-fallbacks, R2.5)."
        )

    raw_port = env["ENTITLEMENT_DB_PORT"].strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise GovernanceConfigError(
            f"ENTITLEMENT_DB_PORT must be an integer, got {raw_port!r}."
        ) from exc

    return DbConfig(
        host=env["ENTITLEMENT_DB_HOST"].strip(),
        port=port,
        user=env["ENTITLEMENT_DB_USER"].strip(),
        password=env["ENTITLEMENT_DB_PASSWORD"],
        database=env["ENTITLEMENT_DB_NAME"].strip(),
    )


@contextmanager
def _scoped_db_env(config: DbConfig):
    """Temporarily set the app DB env vars to the validated config values.

    ``DatabaseManager`` reads ``DB_HOST`` / ``DB_USER`` / ... from ``os.environ``.
    Rather than trust whatever ambient values exist (the conflicting-.env hazard),
    we set exactly the values we validated for the duration of the connection and
    restore the prior environment afterwards. ``TEST_MODE`` is forced off so the
    manager targets the real (explicitly-configured) database, not ``testfinance``.
    """
    overrides = {
        "DB_HOST": config.host,
        "DB_PORT": str(config.port),
        "DB_USER": config.user,
        "DB_PASSWORD": config.password,
        "DB_NAME": config.database,
        "TEST_MODE": "false",
    }
    previous = {k: os.environ.get(k) for k in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for k, prior in previous.items():
            if prior is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prior


def _default_db_factory():
    """Build a ``DatabaseManager`` bound to the app DB env (set by the caller)."""
    # Imported lazily so the module imports cleanly where backend/src is only on
    # the path at handler init, and so tests can inject a fake db without this.
    from database import DatabaseManager

    return DatabaseManager(test_mode=False)


class GovernanceReader:
    """Read-only reader for a user's per-tenant roles + active modules (R2.2).

    All access is a parameterized SELECT via ``DatabaseManager.execute_query`` with
    ``fetch=True`` and NO ``commit`` — zero governance writes. This class is the
    Lambda's only MySQL touch, and it happens at token issuance, not on the API
    request path.

    Args:
        db: A ``DatabaseManager``-shaped object exposing
            ``execute_query(query, params, fetch=True)``. Defaults to a manager
            built from the validated config (see :meth:`from_config`). Injectable
            so T13 can pass a fake and assert read-only usage.
    """

    def __init__(self, db):
        self._db = db

    @classmethod
    def from_config(cls, config: DbConfig, db_factory=_default_db_factory) -> "GovernanceReader":
        """Build a reader whose ``DatabaseManager`` is bound to ``config``.

        The manager is constructed inside a scoped env patch so it picks up
        exactly the validated connection settings (never ambient .env values).
        """
        with _scoped_db_env(config):
            db = db_factory()
        return cls(db)

    def get_user_roles_by_tenant(self, email: str) -> dict[str, list[str]]:
        """Return ``{tenant -> [role, ...]}`` from ``user_tenant_roles`` (read-only).

        Parameterized on ``email`` (R2.2, database-patterns: always ``%s``). Rows
        are grouped by ``administration`` (the tenant). Duplicate roles are kept
        as-is (the resolver deduplicates).
        """
        rows = self._db.execute_query(
            "SELECT administration, role FROM user_tenant_roles WHERE email = %s",
            (email,),
            fetch=True,
        )
        roles_by_tenant: dict[str, list[str]] = {}
        for row in rows or []:
            tenant = row["administration"]
            roles_by_tenant.setdefault(tenant, []).append(row["role"])
        return roles_by_tenant

    def get_active_modules_by_tenant(
        self, tenants: Sequence[str]
    ) -> dict[str, list[str]]:
        """Return ``{tenant -> [active module_name, ...]}`` (read-only).

        Reads ``tenant_modules`` for exactly the given ``tenants``, filtered to
        ``is_active`` rows. Parameterized with one ``%s`` per tenant (database
        -patterns). An empty ``tenants`` yields ``{}`` without touching the DB.
        """
        tenant_list = [t for t in tenants if t]
        if not tenant_list:
            return {}

        placeholders = ", ".join(["%s"] * len(tenant_list))
        rows = self._db.execute_query(
            "SELECT administration, module_name FROM tenant_modules "
            f"WHERE administration IN ({placeholders}) AND is_active = TRUE",
            tuple(tenant_list),
            fetch=True,
        )
        active_by_tenant: dict[str, list[str]] = {t: [] for t in tenant_list}
        for row in rows or []:
            active_by_tenant.setdefault(row["administration"], []).append(
                row["module_name"]
            )
        return active_by_tenant
