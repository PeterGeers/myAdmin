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
    from sam.members.handler import app as members_app
    from sam.members.domain.field_resolver import StaticOverlayProvider
    from sam.members.domain.scope_dimensions import (
        HDCN_SCOPE_CONFIG,
        StaticScopeConfigProvider,
    )

    members_app._SCOPE_CONFIG_PROVIDER_OVERRIDE = StaticScopeConfigProvider(
        {"h-dcn": HDCN_SCOPE_CONFIG}
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
