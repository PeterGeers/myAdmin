"""
S4 T6 — property-based proof that the pure resolver ≡ the Flask plane's decision.

Feature: s4-token-entitlement-projection, Property 1: Resolver equivalence to the
Flask plane

This is the property-based version of T2's example-level proof
(``test_entitlement_resolver_flask_equivalence.py``): the *one-rule-two-carriers*
guarantee (R1.3, R4.1). For ANY generated MySQL state — tenants × active modules
× per-tenant roles — the capability set produced by the S4 token carrier
(:func:`auth.entitlement_resolver.resolve_entitlement`) must equal what the Flask
plane grants today via

    role_cache.get_tenant_roles  →  module gate  →  permission expansion.

Oracle reuse (no reimplementation of the rule)
----------------------------------------------
The reference "Flask decision" is NOT reimplemented here. It is imported straight
from the T2 module, which composes the REAL Flask functions:

- ``auth.role_cache.get_tenant_roles`` — the real cached per-tenant role reader,
  driven through a ``mock_db`` so the real query/cache path runs (no real MySQL).
- ``services.module_registry.has_module`` + a module's ``required_roles`` — the
  real module gate.
- ``auth.cognito_utils.get_permissions_for_roles`` — the real permission
  expansion (wildcard short-circuit included), the same function
  ``validate_permissions`` uses.

The generators draw over the REAL ``MODULE_REGISTRY`` module names, the real
``required_roles`` on those modules, and the real role names from
``ROLE_PERMISSIONS`` (including a global/wildcard role — R1.4). Edge cases are
built into the generators: empty state, tenants with no active modules, roles for
inactive modules, duplicate roles, multi-tenant users, and a wildcard/global role
mixed in.

**Validates: Requirements 1.3, 4.1**

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "Correctness Properties → Property 1"; requirements R1.3, R4.1.
"""

import os
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth import role_cache
from auth.cognito_utils import ROLE_PERMISSIONS
from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY

# Reuse T2's REAL-Flask oracle rather than reimplementing the resolution rule.
from test_entitlement_resolver_flask_equivalence import (
    build_mock_db,
    flask_capabilities_for_tenant,
)


# ---------------------------------------------------------------------------
# Generators — drawn over the REAL registry + role maps so the property
# exercises the actual resolution rule, not a toy one.
# ---------------------------------------------------------------------------

# Real module names from the registry (FIN / STR / TENADMIN / ZZP ...).
MODULE_NAMES = sorted(MODULE_REGISTRY.keys())

# Every role that some real module lists in required_roles — these are the roles
# that can actually survive the module gate.
MODULE_ROLES = sorted(
    {
        role
        for descriptor in MODULE_REGISTRY.values()
        for role in (descriptor.get("required_roles", []) or [])
    }
)

# Global/wildcard roles (R1.4): no module lists them in required_roles, so the
# gate must drop them from the per-tenant answer. Including them in the draw
# exercises the "global roles are not part of the per-tenant map" edge.
GLOBAL_ROLES = sorted(
    {r for r, perms in ROLE_PERMISSIONS.items() if "*" in perms}
    | {"SysAdmin", "Administrators", "System_CRUD"}
)

# The full role pool a user may hold in a tenant: module-granting roles, global
# roles, and an unknown role (not in any registry / ROLE_PERMISSIONS) to prove
# unknown roles contribute nothing on both carriers.
ALL_ROLES = sorted(set(MODULE_ROLES) | set(GLOBAL_ROLES) | {"UnknownRole"})

# Tenant names: a small fixed pool so the multi-tenant + reuse cases recur and
# generated states stay in the resolver's real input space.
TENANT_NAMES = ["TenantA", "TenantB", "TenantC", "ExampleTenant"]

# A role list for one tenant. Non-unique so DUPLICATE roles are exercised; may be
# empty. Sampled from the real role pool (module + global + unknown).
roles_list_st = st.lists(st.sampled_from(ALL_ROLES), min_size=0, max_size=6)

# Active-module list for one tenant: a SUBSET of the real module names (unique),
# possibly empty. Drawing a subset means inactive-module exclusion is exercised
# whenever a user holds a role for a module that isn't in this subset.
active_modules_list_st = st.lists(
    st.sampled_from(MODULE_NAMES), min_size=0, max_size=len(MODULE_NAMES), unique=True
)


@st.composite
def entitlement_state(draw):
    """Generate a full ``(user_roles_by_tenant, active_modules_by_tenant)`` state.

    - Tenants: a (possibly empty) subset of the fixed tenant pool → covers the
      empty-state and single/multi-tenant cases.
    - Per tenant: a role list (may be empty, may contain duplicates, may hold a
      global/wildcard or unknown role) and an independently drawn active-module
      subset (may be empty → tenant-with-no-active-modules; may omit modules a
      role would grant → role-for-inactive-module).

    ``active_modules_by_tenant`` is keyed by the SAME tenants so every tenant the
    user has roles in also has an (independent) active-module set, matching how
    the Lambda passes rows in.
    """
    tenants = draw(
        st.lists(st.sampled_from(TENANT_NAMES), min_size=0, max_size=4, unique=True)
    )

    user_roles_by_tenant = {}
    active_modules_by_tenant = {}
    for tenant in tenants:
        user_roles_by_tenant[tenant] = draw(roles_list_st)
        active_modules_by_tenant[tenant] = draw(active_modules_list_st)

    return user_roles_by_tenant, active_modules_by_tenant


# ---------------------------------------------------------------------------
# Property 1 — resolver ≡ composed-Flask oracle for every (user, tenant, cap).
# ---------------------------------------------------------------------------

class TestResolverEquivalenceToFlaskPlane:
    """Feature: s4-token-entitlement-projection, Property 1: Resolver equivalence
    to the Flask plane.

    For any generated state, the resolver's per-tenant capability set equals the
    composed-Flask oracle's for the SAME inputs — one rule, two carriers
    (R1.3, R4.1).
    """

    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(state=entitlement_state())
    def test_resolver_capabilities_equal_flask_oracle(self, mock_db, state):
        user_roles_by_tenant, active_modules_by_tenant = state

        # The Flask oracle path (role_cache) caches by email:tenant. Clear it for
        # every generated example so a prior example's roles never leak.
        role_cache._role_cache.clear()

        email = "prop@example.com"

        # Wire the ONE mock_db to answer both real Flask queries
        # (user_tenant_roles for role_cache, tenant_modules for has_module).
        build_mock_db(mock_db, user_roles_by_tenant, active_modules_by_tenant)

        # Carrier 1 — the S4 token resolver under test.
        resolver_out = resolve_entitlement(
            user_roles_by_tenant=user_roles_by_tenant,
            active_modules_by_tenant=active_modules_by_tenant,
            module_registry=MODULE_REGISTRY,
        )

        # Carrier 2 — the composed REAL-Flask decision oracle (T2 helper).
        flask_out = {
            tenant: flask_capabilities_for_tenant(
                email,
                tenant,
                mock_db,
                active_modules_by_tenant.get(tenant, []),
                MODULE_REGISTRY,
            )
            for tenant in user_roles_by_tenant
        }

        # One rule, two carriers: identical for every (user, tenant, capability).
        assert resolver_out == flask_out
