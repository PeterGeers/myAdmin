"""
Shared pytest fixtures for the PreTokenGen Lambda tests (S4 D2).

The handler memoises its :class:`GovernanceReader` on the module for the life of a
warm Lambda container (fail-fast config validated once at cold start, T12). Under
test each case installs its own reader (via the ``patch_reader`` fixture that
patches ``handler._build_reader``), so the process-level cache must be cleared
between tests or the first test's reader would leak into later ones. This autouse
fixture resets that cache around every test — mirroring a fresh cold start.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# ─────────────────────────────────────────────────────────────────────────────────────
# Cross-plane import guard (spec full-test-suite-fixes-2026-10-15, task L2 — durable
# prevention for the C1 class).
#
# The SAM / DynamoDB plane must NEVER transitively import ``mysql.connector``. C1 happened
# because a SAM-plane test imported a Flask/MySQL-plane migration driver whose top-level
# ``from database import DatabaseManager`` pulls in ``mysql.connector`` — a module the SAM
# CI env deliberately does not install. It failed at collection ONLY in CI, because a local
# dev venv HAS mysql-connector-python installed and silently masks the leak (verified: the
# driver is importable in the backend .venv this suite runs under).
#
# This finder makes that leak fail fast and deterministically EVERYWHERE — not just in CI —
# the instant any ``sam`` test transitively does ``import mysql`` / ``import mysql.connector``.
# It is installed at conftest import time (collection), so a re-introduced C1-style leak dies
# at collection with a clear cross-plane-leak message rather than passing locally and only
# reddening the nightly suite. Legitimate SAM imports (boto3 / DynamoDB) are unaffected — the
# finder blocks ONLY the ``mysql`` package.
# ─────────────────────────────────────────────────────────────────────────────────────
_CROSS_PLANE_LEAK_MSG = (
    "SAM plane must not import mysql.connector (cross-plane leak). The SAM/DynamoDB plane is "
    "deliberately MySQL-free; something under sam/ transitively did `import mysql[.connector]`. "
    "The usual cause is reaching into a Flask/MySQL-plane module whose import graph needs the "
    "MySQL driver (e.g. a migration driver that does `from database import DatabaseManager` at "
    "module top level). Fix: import the pure, DB-free helper directly (not via the DB-bound "
    "driver), or make the MySQL import lazy — do NOT add mysql-connector-python to the SAM env."
)


class _BlockMysqlFinder:
    """A ``sys.meta_path`` finder that refuses to import the ``mysql`` package on the SAM plane.

    Raising from ``find_spec`` surfaces at the exact import site (collection/import time) with
    the cross-plane-leak message, so the offending SAM test is pinpointed immediately. Only the
    ``mysql`` top-level package and its submodules are blocked; every other import is passed
    through (``return None`` defers to the rest of ``sys.meta_path``).
    """

    def find_spec(self, name, path, target=None):
        if name == "mysql" or name.startswith("mysql."):
            raise ModuleNotFoundError(_CROSS_PLANE_LEAK_MSG)
        return None


def _install_mysql_import_guard() -> None:
    """Install the mysql block at the front of ``sys.meta_path`` (idempotent).

    Also drops any already-imported ``mysql`` module so the block is real even if something
    imported it before conftest loaded (shouldn't happen on the SAM plane, but keeps the guard
    honest rather than silently defeated by a warm import).
    """
    if any(isinstance(f, _BlockMysqlFinder) for f in sys.meta_path):
        return
    for _m in [m for m in list(sys.modules) if m == "mysql" or m.startswith("mysql.")]:
        del sys.modules[_m]
    sys.meta_path.insert(0, _BlockMysqlFinder())


_install_mysql_import_guard()


from sam.pretokengen import handler as handler_mod


@pytest.fixture(autouse=True)
def _reset_reader_cache():
    """Clear the handler's cold-start reader cache before and after each test."""
    handler_mod._reader_cache = None
    yield
    handler_mod._reader_cache = None


@pytest.fixture(autouse=True)
def _members_config_providers():
    """Install the Members edge's config/overlay providers for each test (S5b task 8.2).

    In production the Members handler builds its scope-config + field-overlay providers from
    the governance projection (a fresh :class:`MembersProjectionReader` per request), whose
    table resolves lazily against DynamoDB. The SAM test suite runs with NO AWS, so this
    autouse fixture installs the S5 reference providers on the edge's test-only override
    seam — the h-dcn ``Static*`` scope config (the first tenant's ``region`` dimension) plus
    an empty overlay — exactly what the S5 edge wired inline before the swap. This keeps the
    612 module tests green (h-dcn scope resolution unchanged) while the production path reads
    the projection. Reset around every test to mirror a fresh cold start; individual tests
    may still override these seams for their own fake-table-backed reader.
    """
    from sam.members.domain.field_resolver import StaticOverlayProvider
    from sam.members.domain.scope_dimensions import StaticScopeConfigProvider
    from sam.members.handler import app as members_app
    from sam.tests._scope_fixtures import SAMPLE_SCOPE_CONFIG

    members_app._SCOPE_CONFIG_PROVIDER_OVERRIDE = StaticScopeConfigProvider(
        {"h-dcn": SAMPLE_SCOPE_CONFIG}
    )
    members_app._OVERLAY_PROVIDER_OVERRIDE = StaticOverlayProvider({})
    # S5b task 8.3: the caller's scope now comes from PROJECTED grants (design C5), not the
    # token groups. Default the grant reader to "no grants for anyone" so a granted capability
    # resolves to deny-by-default (empty allowed_scopes) unless a test injects grants. Tests
    # that exercise scoped/all-access callers install a FakeScopeGrantsReader (see below).
    members_app._SCOPE_GRANTS_READER_OVERRIDE = FakeScopeGrantsReader({})
    yield
    members_app._SCOPE_CONFIG_PROVIDER_OVERRIDE = None
    members_app._OVERLAY_PROVIDER_OVERRIDE = None
    members_app._SCOPE_GRANTS_READER_OVERRIDE = None


class FakeScopeGrantsReader:
    """A tiny in-memory scope-grant reader for the Members edge (S5b task 8.3, design C5).

    Satisfies the edge's ``get_scope_grants(tenant_id, email) -> {dimension: values}`` seam
    from an in-memory ``{(tenant_id, email): {dimension: values}}`` map, mirroring the
    projected ``scopegrant#<email>#<dimension>`` rows the real
    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader` reads —
    so tests drive the projected-grant model (Noord-scoped → ``["Noord"]``, all-access →
    ``["*"]``, a ``required_for`` capability with NO grant → ABSENT → deny) WITHOUT AWS.
    A caller/tenant with no entry resolves to an empty grant map (deny-by-default).
    """

    def __init__(self, grants=None):
        # grants: {(tenant_id, email): {dimension_key: [values] | ["*"]}}
        self._grants = {key: dict(dims) for key, dims in dict(grants or {}).items()}

    def get_scope_grants(self, tenant_id, email):
        return dict(self._grants.get((tenant_id, email or ""), {}))
