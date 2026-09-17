"""
S4 T9 — property-based proof that the pure resolver is pure / deterministic.

Feature: s4-token-entitlement-projection, Property 4: Purity / determinism

For ANY generated MySQL state — tenants × active modules × per-tenant roles —
:func:`auth.entitlement_resolver.resolve_entitlement` must behave as a
deterministic function of its inputs alone (R1.2):

- (a) **Idempotent / deterministic** — resolving the SAME inputs twice yields
  identical maps. No hidden state, clock, env, or I/O leaks into the answer.
- (b) **Order-independence** — shuffling the order of roles within a tenant, and
  shuffling the insertion order of the tenant / active-module dicts, does not
  change the resolved result. The resolver must not depend on input ordering.
- (c) **No input mutation** — the resolver does not mutate its inputs; the caller
  (the PreTokenGen Lambda / the Flask plane) can safely reuse the rows it passed
  in. Asserted by deep-equality of the inputs before/after a call.
- (d) **Sorted output** — every per-tenant capability list is sorted (stable
  ordering), which the T4 codec relies on for a compact, deterministic encoding.

Generator reuse (T6/T7/T8)
--------------------------
The state generator is imported directly from the T6 property module
(``entitlement_state`` — the SAME strategy T6/T7/T8 draw over the REAL
``MODULE_REGISTRY`` module names, ``required_roles``, global/wildcard roles, and
an unknown role, with edge cases built in: empty state, tenants with no active
modules, roles for inactive modules, duplicate roles, multi-tenant users). This
keeps Property 4 in the exact input space the other resolver properties use.

**Validates: Requirements R1.2**

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "Correctness Properties → Property 4"; requirement R1.2.
"""

import copy
import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY

# Reuse the T6/T7/T8 generator so Property 4 exercises the same input space.
from test_entitlement_resolver_equivalence_props import entitlement_state


def _shuffled_state(draw, user_roles_by_tenant, active_modules_by_tenant):
    """Return an order-permuted copy of the state with identical *content*.

    - The role list for each tenant is permuted (order within a tenant changed).
    - The tenant keys are reinserted in a permuted order for BOTH dicts
      (dict insertion order changed).
    - The active-module list for each tenant is permuted.

    Content (as sets / multisets) is preserved — only ordering differs — so the
    resolver, if truly order-independent, must produce the identical result.
    """
    tenants = list(user_roles_by_tenant.keys())
    permuted_tenants = draw(st.permutations(tenants))

    shuffled_roles: dict[str, list[str]] = {}
    shuffled_modules: dict[str, list[str]] = {}
    for tenant in permuted_tenants:
        roles = list(user_roles_by_tenant[tenant])
        shuffled_roles[tenant] = draw(st.permutations(roles))
        modules = list(active_modules_by_tenant.get(tenant, []))
        shuffled_modules[tenant] = draw(st.permutations(modules))

    return shuffled_roles, shuffled_modules


class TestResolverPurityDeterminism:
    """Feature: s4-token-entitlement-projection, Property 4: Purity / determinism.

    For any generated state, ``resolve_entitlement`` is a deterministic, pure,
    order-independent, non-mutating function whose per-tenant capability lists are
    sorted (R1.2).
    """

    @settings(max_examples=200)
    @given(data=st.data())
    def test_resolve_is_pure_deterministic_and_order_independent(self, data):
        user_roles_by_tenant, active_modules_by_tenant = data.draw(entitlement_state())

        # Deep copies of the inputs to detect any mutation by the resolver (c).
        roles_before = copy.deepcopy(user_roles_by_tenant)
        modules_before = copy.deepcopy(active_modules_by_tenant)

        # First resolution.
        result_1 = resolve_entitlement(
            user_roles_by_tenant=user_roles_by_tenant,
            active_modules_by_tenant=active_modules_by_tenant,
            module_registry=MODULE_REGISTRY,
        )

        # (c) No input mutation — the resolver must not touch the rows it was given.
        assert user_roles_by_tenant == roles_before, (
            "resolve_entitlement mutated user_roles_by_tenant"
        )
        assert active_modules_by_tenant == modules_before, (
            "resolve_entitlement mutated active_modules_by_tenant"
        )

        # (a) Idempotent / deterministic — resolving the same inputs again is equal.
        result_2 = resolve_entitlement(
            user_roles_by_tenant=user_roles_by_tenant,
            active_modules_by_tenant=active_modules_by_tenant,
            module_registry=MODULE_REGISTRY,
        )
        assert result_1 == result_2, "resolve_entitlement is not deterministic"

        # (b) Order-independence — same content, permuted ordering → same answer.
        shuffled_roles, shuffled_modules = _shuffled_state(
            data.draw, user_roles_by_tenant, active_modules_by_tenant
        )
        result_shuffled = resolve_entitlement(
            user_roles_by_tenant=shuffled_roles,
            active_modules_by_tenant=shuffled_modules,
            module_registry=MODULE_REGISTRY,
        )
        assert result_shuffled == result_1, (
            "resolve_entitlement depends on input ordering"
        )

        # (d) Sorted output — every capability list is sorted (codec relies on it).
        for tenant, capabilities in result_1.items():
            assert capabilities == sorted(capabilities), (
                f"capabilities for tenant {tenant!r} are not sorted: {capabilities!r}"
            )
