"""
S4 T8 — property-based proof of TENANT ISOLATION of resolved entitlement.

Feature: s4-token-entitlement-projection, Property 3: Tenant isolation of
entitlement

This is the D1 resolver's *per-tenant scoping* guarantee (R1.1, per-tenant
scoping): a user's resolved capabilities for a tenant ``T`` are a function of
ONLY ``T``'s roles + ``T``'s active modules (and the in-code ``MODULE_REGISTRY``
role rules). They can never depend on another tenant's roles, another tenant's
active modules, or on whether other tenants are present in the state at all.

The property is asserted in the two equivalent framings the design calls for,
both over the SAME generated multi-tenant states:

(a) **Isolation ≡ per-tenant-independent resolution** — resolving the full
    multi-tenant state and reading tenant ``T``'s entry yields the SAME
    capability set as resolving ``T`` ALONE (a single-tenant state containing
    only ``T``'s roles + ``T``'s active modules). If the resolver leaked any
    cross-tenant influence, the full-vs-isolated answers for ``T`` would differ.

(b) **Perturbing another tenant leaves ``T`` unchanged** — take a state, resolve
    it, then arbitrarily mutate a DIFFERENT tenant ``U`` (replace its roles and
    active modules, or drop ``U`` entirely, or add a brand-new tenant), resolve
    again, and assert ``T``'s resolved capability set is byte-for-byte identical.
    Only ``T``'s own inputs may move ``T``'s answer.

Generators
----------
Reuses T6/T7's strategies (``entitlement_state``, ``MODULE_NAMES``,
``TENANT_NAMES``, ``roles_list_st``, ``active_modules_list_st``) — multi-tenant
states drawn over the REAL registry, real ``required_roles``, global/wildcard
roles, an unknown role, and the edge cases (empty state, tenant with no active
modules, role for an inactive module, duplicate roles). A dedicated
``multi_tenant_state`` composite guarantees ≥2 tenants so the isolation
assertions are non-vacuous in the interesting cases, and a separate ``other``
perturbation is drawn independently for framing (b).

**Validates: Requirements R1.1**

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "Correctness Properties → Property 3"; requirement R1.1
  (per-tenant scoping).
"""

import os
import sys

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY

# Reuse T6's generators (drawn over the REAL registry + role maps) rather than
# duplicating strategies.
from test_entitlement_resolver_equivalence_props import (
    TENANT_NAMES,
    active_modules_list_st,
    entitlement_state,
    roles_list_st,
)


# ---------------------------------------------------------------------------
# Generators.
# ---------------------------------------------------------------------------


@st.composite
def multi_tenant_state(draw):
    """A state with >=2 tenants so the isolation assertions are non-vacuous.

    Same per-tenant construction as T6's ``entitlement_state`` (role list may be
    empty / duplicated / hold a global-or-unknown role; active-module set drawn
    independently and may be empty or omit a role's module), but the tenant set
    is forced to at least two distinct tenants from the real pool. Returns
    ``(user_roles_by_tenant, active_modules_by_tenant)``.
    """
    tenants = draw(
        st.lists(
            st.sampled_from(TENANT_NAMES), min_size=2, max_size=4, unique=True
        )
    )

    user_roles_by_tenant = {}
    active_modules_by_tenant = {}
    for tenant in tenants:
        user_roles_by_tenant[tenant] = draw(roles_list_st)
        active_modules_by_tenant[tenant] = draw(active_modules_list_st)

    return user_roles_by_tenant, active_modules_by_tenant


def _resolve(user_roles_by_tenant, active_modules_by_tenant):
    return resolve_entitlement(
        user_roles_by_tenant=user_roles_by_tenant,
        active_modules_by_tenant=active_modules_by_tenant,
        module_registry=MODULE_REGISTRY,
    )


# ---------------------------------------------------------------------------
# Property 3 — tenant isolation of entitlement.
# ---------------------------------------------------------------------------


class TestTenantIsolationOfEntitlement:
    """Feature: s4-token-entitlement-projection, Property 3: Tenant isolation of
    entitlement.

    For any multi-tenant state, a user's resolved capabilities for tenant ``T``
    depend only on ``T``'s roles + ``T``'s active modules, never on another
    tenant's roles/modules or on which other tenants exist (R1.1, per-tenant
    scoping).
    """

    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(state=multi_tenant_state())
    def test_full_resolution_matches_per_tenant_isolated_resolution(self, state):
        """Framing (a): full-state entry for T equals resolving T alone.

        Resolve the whole multi-tenant state once. Then, for each tenant ``T``,
        resolve a single-tenant state containing ONLY ``T``'s roles + ``T``'s
        active modules and assert the isolated answer equals ``T``'s entry in the
        full resolution. Any cross-tenant leakage would make these differ.
        """
        user_roles_by_tenant, active_modules_by_tenant = state

        full = _resolve(user_roles_by_tenant, active_modules_by_tenant)

        for tenant in user_roles_by_tenant:
            isolated = _resolve(
                {tenant: user_roles_by_tenant[tenant]},
                {tenant: active_modules_by_tenant.get(tenant, [])},
            )

            assert isolated[tenant] == full[tenant], (
                f"tenant {tenant!r}: isolated resolution "
                f"{isolated[tenant]} != full-state entry {full[tenant]} — "
                f"resolution leaked cross-tenant influence"
            )

    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        state=multi_tenant_state(),
        target_pick=st.integers(min_value=0, max_value=1000),
        other_roles=roles_list_st,
        other_modules=active_modules_list_st,
        extra_tenant_roles=roles_list_st,
        extra_tenant_modules=active_modules_list_st,
        mutation=st.integers(min_value=0, max_value=2),
    )
    def test_perturbing_another_tenant_leaves_target_unchanged(
        self,
        state,
        target_pick,
        other_roles,
        other_modules,
        extra_tenant_roles,
        extra_tenant_modules,
        mutation,
    ):
        """Framing (b): mutating a DIFFERENT tenant never changes T's answer.

        Pick a target tenant ``T``. Apply one of three perturbations to the rest
        of the state (never touching ``T``): (0) replace another tenant ``U``'s
        roles + active modules with independently generated ones; (1) drop ``U``
        entirely; (2) add a brand-new tenant not already present. Re-resolve and
        assert ``T``'s capability set is unchanged. Only ``T``'s own inputs may
        move ``T``'s answer (R1.1, per-tenant scoping).
        """
        user_roles_by_tenant, active_modules_by_tenant = state

        tenants = list(user_roles_by_tenant)
        target = tenants[target_pick % len(tenants)]

        # Baseline: T's resolved caps in the original multi-tenant state.
        before = _resolve(user_roles_by_tenant, active_modules_by_tenant)
        before_target = before[target]

        # Build a perturbed state that is IDENTICAL for T but differs elsewhere.
        pert_roles = {t: list(v) for t, v in user_roles_by_tenant.items()}
        pert_modules = {t: list(v) for t, v in active_modules_by_tenant.items()}

        others = [t for t in tenants if t != target]

        if mutation == 0 and others:
            # Replace one other tenant's roles + active modules wholesale.
            victim = others[target_pick % len(others)]
            pert_roles[victim] = list(other_roles)
            pert_modules[victim] = list(other_modules)
        elif mutation == 1 and others:
            # Drop one other tenant entirely.
            victim = others[target_pick % len(others)]
            del pert_roles[victim]
            del pert_modules[victim]
        else:
            # Add a brand-new tenant not already present (mutation == 2, or a
            # fallback when there are no "others" to touch).
            new_name = next(
                (n for n in TENANT_NAMES if n not in pert_roles), None
            )
            if new_name is None:
                new_name = "BrandNewTenant"
            pert_roles[new_name] = list(extra_tenant_roles)
            pert_modules[new_name] = list(extra_tenant_modules)

        # T's own inputs must be untouched by construction — guard the invariant.
        assert pert_roles[target] == list(user_roles_by_tenant[target])
        assert pert_modules[target] == list(
            active_modules_by_tenant.get(target, [])
        )

        after = _resolve(pert_roles, pert_modules)

        assert after[target] == before_target, (
            f"target tenant {target!r} changed after perturbing another tenant "
            f"(mutation={mutation}): {before_target} -> {after[target]} — "
            f"resolution is NOT tenant-isolated"
        )
