"""
S4 T2 — example-level proof that the pure resolver ≡ the Flask plane's decision.

This is the *one-rule-two-carriers* guarantee (R1.3, R4.1): for a given
``(user, tenant)`` and MySQL state, the capability set produced by the S4
resolver (:func:`auth.entitlement_resolver.resolve_entitlement`, the token
carrier) must equal what the Flask plane grants today via

    role_cache.get_tenant_roles  →  module gate  →  permission expansion.

To make the equivalence trustworthy, the reference "Flask decision" oracle in
this file is composed from the **real** Flask functions — it does NOT
reimplement the resolution rule:

- ``auth.role_cache.get_tenant_roles`` — the actual cached per-tenant role
  reader (driven here through a ``mock_db`` so the real cache/query path runs,
  no real MySQL, per testing-standards).
- ``services.module_registry`` ``has_module`` + a module's ``required_roles`` —
  the actual module gate that turns a raw role into an access decision.
- ``auth.cognito_utils.get_permissions_for_roles`` — the exact function
  :func:`auth.cognito_utils.validate_permissions` uses to expand the surviving
  roles into capabilities (including the wildcard short-circuit).

The property-based version of this equivalence (≥100 generated states) is T6;
this file pins the contract with representative examples.

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "D1 — The pure resolver" (equivalence to role_cache.py); R1.3, R4.1.
"""

import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth import role_cache
from auth.cognito_utils import get_permissions_for_roles
from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY, has_module


# ---------------------------------------------------------------------------
# The reference "Flask decision" oracle — composed from the REAL Flask
# functions, not a reimplementation of the rule.
# ---------------------------------------------------------------------------

def flask_capabilities_for_tenant(email, tenant, db, active_modules, module_registry):
    """Capabilities the Flask plane would grant for one (user, tenant).

    Composes the actual Flask decision path:

    1. ``role_cache.get_tenant_roles`` — the user's raw per-tenant roles
       (the same MySQL-backed cached reader the Flask ``cognito_required``
       decorator calls). Driven here via a ``mock_db``.
    2. **module gate** — keep a role only if some module that is ACTIVE for the
       tenant (``has_module``) lists it in ``required_roles``. This is exactly
       the gate ``module_required`` / ``has_module`` enforce on a Flask route.
    3. ``get_permissions_for_roles`` — expand the surviving roles into
       capabilities (the same function ``validate_permissions`` uses, wildcard
       short-circuit included).

    Returns the sorted capability list so it is directly comparable to the
    resolver's per-tenant output.
    """
    # Step 1 — real cached per-tenant role reader (real query path, mock_db).
    raw_roles = set(role_cache.get_tenant_roles(email, tenant, db))

    # Step 2 — real module gate: a role survives iff an ACTIVE module requires it.
    surviving = set()
    for module_name in active_modules:
        # has_module is the real gate; it reads tenant_modules via the same db.
        if not has_module(db, tenant, module_name):
            continue
        descriptor = module_registry.get(module_name) or {}
        for role in descriptor.get("required_roles", []) or []:
            if role in raw_roles:
                surviving.add(role)

    # Step 3 — real permission expansion (wildcard short-circuits to ['*']).
    perms = get_permissions_for_roles(sorted(surviving))
    if "*" in perms:
        return ["*"]
    return sorted(perms)


def build_mock_db(mock_db, roles_by_tenant, active_modules_by_tenant):
    """Wire ``mock_db.execute_query`` to answer BOTH real Flask queries.

    The oracle exercises two real DB-backed readers through this one mock:

    - ``role_cache.get_tenant_roles`` issues
      ``SELECT role FROM user_tenant_roles WHERE email=%s AND administration=%s``
      → return ``[{"role": r}, ...]`` for that tenant.
    - ``module_registry.has_module`` issues
      ``SELECT is_active FROM tenant_modules WHERE administration=%s AND module_name=%s``
      → return ``[{"is_active": 1}]`` iff that module is active for the tenant.

    This keeps the real query/cache code on the path (no reimplementation) while
    honouring the testing-standards "mock_db for any role_cache DB read" rule.
    """

    def _execute_query(query, params=None, fetch=True, commit=False):
        params = params or ()
        q = " ".join(query.split())  # normalise whitespace
        if "FROM user_tenant_roles" in q:
            email, tenant = params
            roles = roles_by_tenant.get(tenant, [])
            return [{"role": r} for r in roles]
        if "FROM tenant_modules" in q:
            tenant, module_name = params
            active = active_modules_by_tenant.get(tenant, [])
            return [{"is_active": 1}] if module_name in active else []
        raise AssertionError(f"Unexpected query in oracle: {q!r}")

    mock_db.execute_query.side_effect = _execute_query
    return mock_db


@pytest.fixture(autouse=True)
def _clear_role_cache():
    """Ensure the module-level role cache never leaks between examples."""
    role_cache._role_cache.clear()
    yield
    role_cache._role_cache.clear()


def assert_resolver_equals_flask(mock_db, email, roles_by_tenant, active_by_tenant):
    """Core assertion: resolver output == the composed Flask-decision oracle.

    Builds both answers from the SAME inputs and asserts they are identical for
    every tenant — the R1.3/R4.1 one-rule-two-carriers guarantee.
    """
    build_mock_db(mock_db, roles_by_tenant, active_by_tenant)

    resolver_out = resolve_entitlement(
        user_roles_by_tenant=roles_by_tenant,
        active_modules_by_tenant=active_by_tenant,
        module_registry=MODULE_REGISTRY,
    )

    flask_out = {
        tenant: flask_capabilities_for_tenant(
            email, tenant, mock_db, active_by_tenant.get(tenant, []), MODULE_REGISTRY
        )
        for tenant in roles_by_tenant
    }

    assert resolver_out == flask_out
    return resolver_out, flask_out


# ---------------------------------------------------------------------------
# Representative example states (per the task test matrix).
# ---------------------------------------------------------------------------

class TestFullAccessEquivalence:
    """A CRUD user in a tenant with the module active → identical decision."""

    def test_finance_crud_fin_active_matches_flask(self, mock_db):
        resolver_out, flask_out = assert_resolver_equals_flask(
            mock_db,
            email="crud@example.com",
            roles_by_tenant={"ExampleTenant": ["Finance_CRUD"]},
            active_by_tenant={"ExampleTenant": ["FIN"]},
        )
        # Non-vacuous: the shared decision actually grants write access.
        assert "finance_create" in resolver_out["ExampleTenant"]
        assert "finance_delete" in flask_out["ExampleTenant"]

    def test_multi_module_union_matches_flask(self, mock_db):
        assert_resolver_equals_flask(
            mock_db,
            email="crud@example.com",
            roles_by_tenant={"ExampleTenant": ["Finance_CRUD", "STR_CRUD"]},
            active_by_tenant={"ExampleTenant": ["FIN", "STR"]},
        )


class TestReadOnlyEquivalence:
    """A read-only user resolves to the same read/list caps on both carriers."""

    def test_finance_read_matches_flask(self, mock_db):
        resolver_out, _ = assert_resolver_equals_flask(
            mock_db,
            email="reader@example.com",
            roles_by_tenant={"ExampleTenant": ["Finance_Read"]},
            active_by_tenant={"ExampleTenant": ["FIN"]},
        )
        caps = resolver_out["ExampleTenant"]
        assert "finance_read" in caps
        assert "finance_create" not in caps  # read-only really is read-only


class TestRoleForInactiveModuleEquivalence:
    """R1.1/R1.3 — a role whose module is inactive grants nothing on BOTH carriers."""

    def test_role_for_inactive_module_matches_flask_empty(self, mock_db):
        # User holds Finance_CRUD, but FIN is NOT active (only STR is), and the
        # user has no STR role → both carriers grant nothing.
        resolver_out, flask_out = assert_resolver_equals_flask(
            mock_db,
            email="stale@example.com",
            roles_by_tenant={"ExampleTenant": ["Finance_CRUD"]},
            active_by_tenant={"ExampleTenant": ["STR"]},
        )
        assert resolver_out == {"ExampleTenant": []}
        assert flask_out == {"ExampleTenant": []}

    def test_mixed_active_inactive_matches_flask(self, mock_db):
        # FIN active, STR inactive; user has both a FIN and an STR role.
        # Only the FIN capabilities survive on both carriers.
        resolver_out, _ = assert_resolver_equals_flask(
            mock_db,
            email="mixed@example.com",
            roles_by_tenant={"ExampleTenant": ["Finance_Read", "STR_CRUD"]},
            active_by_tenant={"ExampleTenant": ["FIN"]},
        )
        assert not any(c.startswith("str_") for c in resolver_out["ExampleTenant"])


class TestMultiTenantEquivalence:
    """Each tenant's decision matches the Flask plane independently."""

    def test_multi_tenant_matches_flask_per_tenant(self, mock_db):
        resolver_out, flask_out = assert_resolver_equals_flask(
            mock_db,
            email="multi@example.com",
            roles_by_tenant={
                "TenantA": ["Finance_CRUD"],
                "TenantB": ["STR_Read"],
                "TenantC": ["Finance_CRUD"],  # FIN inactive here
            },
            active_by_tenant={
                "TenantA": ["FIN"],
                "TenantB": ["STR"],
                "TenantC": ["STR"],  # user has no STR role in C
            },
        )
        # Independent, per-tenant equivalence.
        assert resolver_out["TenantC"] == [] == flask_out["TenantC"]
        assert set(resolver_out) == {"TenantA", "TenantB", "TenantC"}


class TestWildcardGlobalRoleEquivalence:
    """R1.4 — wildcard/global-role interplay resolves identically on both carriers.

    A wildcard-permission role (e.g. ``System_CRUD`` → ``["*"]`` in
    ``ROLE_PERMISSIONS``) is a GLOBAL role: no registry module lists it in
    ``required_roles``, so the module gate drops it on BOTH carriers and the
    per-tenant answer is empty — its authority stays the ``cognito:groups``
    claim, never the per-tenant map. The oracle proves the Flask plane agrees.
    """

    def test_global_wildcard_role_grants_nothing_per_tenant_on_both(self, mock_db):
        resolver_out, flask_out = assert_resolver_equals_flask(
            mock_db,
            email="sysadmin@example.com",
            roles_by_tenant={"ExampleTenant": ["System_CRUD", "Administrators"]},
            active_by_tenant={"ExampleTenant": ["FIN", "STR"]},
        )
        assert resolver_out == {"ExampleTenant": []}
        assert flask_out == {"ExampleTenant": []}

    def test_global_role_mixed_with_tenant_role_matches_flask(self, mock_db):
        # A user with a global role AND a per-tenant module role: only the
        # per-tenant module role contributes; the decision is identical on both.
        resolver_out, _ = assert_resolver_equals_flask(
            mock_db,
            email="mixedadmin@example.com",
            roles_by_tenant={"ExampleTenant": ["Administrators", "Finance_Read"]},
            active_by_tenant={"ExampleTenant": ["FIN"]},
        )
        caps = resolver_out["ExampleTenant"]
        assert "finance_read" in caps
        assert "*" not in caps  # global wildcard authority is NOT in the per-tenant map


class TestTenantWithNoActiveModulesEquivalence:
    """A tenant with no active modules → empty on both carriers."""

    def test_no_active_modules_matches_flask_empty(self, mock_db):
        resolver_out, flask_out = assert_resolver_equals_flask(
            mock_db,
            email="idle@example.com",
            roles_by_tenant={"ExampleTenant": ["Finance_CRUD", "STR_CRUD"]},
            active_by_tenant={"ExampleTenant": []},
        )
        assert resolver_out == {"ExampleTenant": []} == flask_out
