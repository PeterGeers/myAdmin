"""
S4 T7 — property-based proof that ONLY active-module capabilities are entitled.

Feature: s4-token-entitlement-projection, Property 2: Only active-module
capabilities are entitled

This is the D1 resolver's *active-module discipline* (R1.1): a capability may
appear in a tenant's resolved entitlement only when the user holds a role that
grants it AND the module that role belongs to is ACTIVE for that tenant. Roles
for inactive/absent modules contribute nothing; and toggling one module's
activity must move *exactly* that module's capabilities — never another's.

The property has two parts, both asserted for every generated state:

(a) **Attribution** — every capability the resolver emits for a tenant is
    attributable to at least one role the user holds in that tenant whose module
    is active for that tenant. Equivalently, no capability of an inactive/absent
    module appears. The reference "attributable" set is computed from the REAL
    ``MODULE_REGISTRY`` (``required_roles``) + ``ROLE_PERMISSIONS`` maps — never
    hardcoded — so the property tracks the real authority tables.

(b) **Disabling removes exactly a module's capabilities** — take a state, resolve
    it, flip one ACTIVE module to inactive for a tenant, resolve again, and assert
    the removed set equals exactly the capabilities *uniquely* granted by that
    module: caps still reachable via another active module the user holds MUST
    remain (many caps overlap — e.g. ``reports_read`` is granted by both Finance
    and STR roles), and no unrelated cap is disturbed.

Oracle discipline (no reimplementation of the resolver)
-------------------------------------------------------
The reference sets are built from the same two authority maps the resolver reads
(``MODULE_REGISTRY[module]["required_roles"]`` and ``ROLE_PERMISSIONS``) but via
an INDEPENDENT per-module expansion, so the property is a genuine cross-check of
the resolver's composed "roles ∩ active modules → capabilities" rule rather than
a copy of it.

**Validates: Requirements R1.1**

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "Correctness Properties → Property 2"; requirement R1.1.
"""

import os
import sys

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.cognito_utils import ROLE_PERMISSIONS
from auth.entitlement_resolver import resolve_entitlement
from services.module_registry import MODULE_REGISTRY

# Reuse T6's generators (drawn over the REAL registry + role maps) rather than
# duplicating strategies. entitlement_state() yields
# (user_roles_by_tenant, active_modules_by_tenant) over the real module names,
# real required_roles, global/wildcard roles, an unknown role, and edge cases
# (empty state, tenant with no active modules, role for an inactive module,
# duplicate roles, multi-tenant users).
from test_entitlement_resolver_equivalence_props import (
    MODULE_NAMES,
    entitlement_state,
)


# ---------------------------------------------------------------------------
# Reference expansion — computed from the REAL authority maps (not hardcoded),
# but INDEPENDENTLY per module so it is a true cross-check of the resolver.
# ---------------------------------------------------------------------------

def module_capabilities_for_user(module_name, held_roles):
    """Capabilities a single module grants a user, given the roles they hold.

    Reads ONLY the real ``MODULE_REGISTRY[module]["required_roles"]`` and
    ``ROLE_PERMISSIONS`` maps: intersect the module's required roles with the
    roles the user holds, then union those roles' permissions. A wildcard role
    (perms == ["*"]) yields ``{"*"}``.

    This is a per-module expansion — it never looks at other modules — so using
    it to reconstruct the resolver's answer genuinely cross-checks the resolver's
    "roles ∩ active modules" composition rather than restating it.
    """
    descriptor = MODULE_REGISTRY.get(module_name) or {}
    required = descriptor.get("required_roles", []) or []
    caps = set()
    for role in required:
        if role not in held_roles:
            continue
        perms = ROLE_PERMISSIONS.get(role, [])
        if "*" in perms:
            caps.add("*")
            continue
        caps.update(perms)
    return caps


def attributable_capabilities(held_roles, active_modules):
    """The set of caps attributable to the user's roles via ANY active module.

    Union of :func:`module_capabilities_for_user` over the tenant's active
    modules. This is the reference "everything the resolver is allowed to emit"
    set for part (a): a cap outside this set could only come from an inactive or
    absent module (or a role the user does not hold) — a Property-2 violation.
    """
    caps = set()
    for module_name in active_modules:
        caps |= module_capabilities_for_user(module_name, held_roles)
    return caps


def normalise_resolved(cap_list):
    """Resolver output as a set; ``["*"]`` becomes ``{"*"}`` for comparison."""
    return set(cap_list)


# ---------------------------------------------------------------------------
# Property 2 (a) — attribution: no inactive/absent module's capability appears.
# ---------------------------------------------------------------------------

class TestOnlyActiveModuleCapabilitiesAreEntitled:
    """Feature: s4-token-entitlement-projection, Property 2: Only active-module
    capabilities are entitled.

    For any generated state, every resolved capability is attributable to a held
    role of an ACTIVE module, and disabling a module removes exactly its unique
    capabilities (R1.1).
    """

    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(state=entitlement_state())
    def test_no_inactive_or_absent_module_capability_appears(self, state):
        """Part (a): every resolved cap is attributable to an active module.

        For each tenant, the resolver's capability set must be a SUBSET of the
        caps attributable to the user's held roles through that tenant's active
        modules. Any cap outside that reference set would necessarily come from
        an inactive/absent module (or an unheld role) — the exact Property-2
        violation. The reference set is derived from the real registry +
        ROLE_PERMISSIONS, so an inactive module cannot smuggle a cap in.
        """
        user_roles_by_tenant, active_modules_by_tenant = state

        resolved = resolve_entitlement(
            user_roles_by_tenant=user_roles_by_tenant,
            active_modules_by_tenant=active_modules_by_tenant,
            module_registry=MODULE_REGISTRY,
        )

        for tenant, roles_seq in user_roles_by_tenant.items():
            held = {r for r in (roles_seq or []) if r}
            active = {
                m for m in (active_modules_by_tenant.get(tenant, []) or []) if m
            }

            allowed = attributable_capabilities(held, active)
            got = normalise_resolved(resolved[tenant])

            # No capability of an inactive/absent module (or an unheld role) may
            # appear: the resolved set is contained in the attributable set.
            assert got <= allowed, (
                f"tenant {tenant!r}: resolver emitted caps not attributable to "
                f"any active module. extra={sorted(got - allowed)} "
                f"held={sorted(held)} active={sorted(active)}"
            )

    # -----------------------------------------------------------------------
    # Property 2 (b) — disabling one module removes exactly its unique caps.
    # -----------------------------------------------------------------------

    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        state=entitlement_state(),
        module_pick=st.integers(min_value=0, max_value=len(MODULE_NAMES) - 1),
        tenant_pick=st.integers(min_value=0, max_value=1000),
    )
    def test_disabling_module_removes_exactly_its_unique_capabilities(
        self, state, module_pick, tenant_pick
    ):
        """Part (b): flipping one active module off removes exactly its unique caps.

        Pick a tenant that has at least one active module and a module active for
        it. Resolve, then re-resolve with that one module made inactive for that
        tenant only. The set difference (removed caps) must equal exactly the caps
        UNIQUELY granted by the disabled module for this user — i.e. caps the user
        can still reach via another still-active module they hold must remain, and
        no unrelated cap (or another tenant's caps) may change.
        """
        user_roles_by_tenant, active_modules_by_tenant = state

        # Find tenants that actually have >=1 active module to disable; skip
        # states where there is nothing to toggle (nothing to assert).
        toggleable = [
            t
            for t in user_roles_by_tenant
            if [m for m in (active_modules_by_tenant.get(t, []) or []) if m]
        ]
        if not toggleable:
            return

        tenant = toggleable[tenant_pick % len(toggleable)]
        active_here = [
            m for m in (active_modules_by_tenant.get(tenant, []) or []) if m
        ]
        # Choose one active module of this tenant to disable.
        target_module = active_here[module_pick % len(active_here)]

        held = {r for r in (user_roles_by_tenant.get(tenant, []) or []) if r}

        # Baseline resolution.
        before = resolve_entitlement(
            user_roles_by_tenant=user_roles_by_tenant,
            active_modules_by_tenant=active_modules_by_tenant,
            module_registry=MODULE_REGISTRY,
        )

        # Flip: disable exactly target_module for this tenant only.
        after_active = {
            t: list(mods) for t, mods in active_modules_by_tenant.items()
        }
        after_active[tenant] = [m for m in active_here if m != target_module]

        after = resolve_entitlement(
            user_roles_by_tenant=user_roles_by_tenant,
            active_modules_by_tenant=after_active,
            module_registry=MODULE_REGISTRY,
        )

        before_caps = normalise_resolved(before[tenant])
        after_caps = normalise_resolved(after[tenant])
        removed = before_caps - after_caps

        # Reference: caps the disabled module grants this user, MINUS caps still
        # reachable via any OTHER module that remains active for the tenant. Those
        # overlapping caps (e.g. reports_read granted by both FIN and STR) must
        # survive; only the disabled module's UNIQUE contribution is removed.
        remaining_active = after_active[tenant]
        disabled_caps = module_capabilities_for_user(target_module, held)
        still_granted = attributable_capabilities(held, remaining_active)
        expected_removed = disabled_caps - still_granted

        assert removed == expected_removed, (
            f"tenant {tenant!r}: disabling {target_module!r} removed "
            f"{sorted(removed)} but expected exactly {sorted(expected_removed)} "
            f"(held={sorted(held)}, disabled_caps={sorted(disabled_caps)}, "
            f"still_granted_via_others={sorted(still_granted)})"
        )

        # Nothing may be ADDED by disabling a module (monotonic removal).
        assert after_caps <= before_caps, (
            f"tenant {tenant!r}: disabling {target_module!r} ADDED caps "
            f"{sorted(after_caps - before_caps)} — disabling must only remove"
        )

        # Isolation: no OTHER tenant's resolved entitlement changed.
        for other in user_roles_by_tenant:
            if other == tenant:
                continue
            assert before[other] == after[other], (
                f"disabling {target_module!r} for {tenant!r} changed unrelated "
                f"tenant {other!r}: {before[other]} -> {after[other]}"
            )
