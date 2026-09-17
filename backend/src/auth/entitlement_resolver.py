"""
S4 D1 — the pure resolved-entitlement resolver (single source of truth).

This module provides :func:`resolve_entitlement`, the ONE resolution rule that
turns a user's per-tenant roles (``user_tenant_roles``) plus a tenant's active
modules (``tenant_modules``) plus the in-code ``MODULE_REGISTRY`` into a
**per-tenant resolved capability map**. It is imported by both carriers of that
answer:

- the Pre-Token-Generation Lambda (S4 T11), which stamps the answer into the
  Pool A token at issuance, and
- the Flask plane (S4 T15), which today computes the same answer via
  ``role_cache.get_tenant_roles`` + the ``module_registry`` gate.

One rule, two carriers: because both call this same function, the token claim
and the Flask plane's server-side decision cannot diverge for the same MySQL
state (the equivalence proven in T2/T6).

Purity (R1.2)
-------------
The resolver is a **pure, deterministic function** of its inputs: no database,
no clock, no environment, no network. The caller fetches the rows and passes
them in as plain ``dict``/``list`` structures. The output ordering is stable
(sorted), so the function is PBT-friendly (T6–T9) and idempotent (T9).

Capability representation (chosen)
----------------------------------
The resolved entitlement for a tenant is a **set of fine-grained capability
strings** (e.g. ``"finance_read"``, ``"str_list"``, ``"tenant_users"``), taken
directly from :data:`auth.cognito_utils.ROLE_PERMISSIONS` — the SAME map the
Flask plane uses in :func:`auth.cognito_utils.get_permissions_for_roles` /
:func:`validate_permissions`. This representation was chosen because it is:

- **derivable purely** from the two existing maps (``ROLE_PERMISSIONS`` expands
  a role into its capabilities; ``MODULE_REGISTRY[module]["required_roles"]``
  maps a module to the roles that grant it), so no new authority is invented; and
- **directly comparable** to the Flask plane's decision — the Flask module gate
  admits a request when the module is active AND the user holds a granting role,
  and then ``validate_permissions`` checks the user's expanded permissions. The
  resolver composes exactly those two steps, so a ``(user, tenant, capability)``
  question has the identical answer on both carriers (the T6 equivalence proof).

The resolved map is returned as ``{tenant -> sorted list[str]}`` so the T4 codec
can encode it compactly and deterministically.

Two-step composition (mirrors ``role_cache.py`` + the module gate)
------------------------------------------------------------------
For each tenant the user belongs to:

1. **roles ∩ active modules** — keep only the user's roles that grant access to
   a module that is ACTIVE for that tenant (per ``active_modules_by_tenant`` +
   ``MODULE_REGISTRY[module]["required_roles"]``). A role whose module is
   inactive/absent contributes nothing (R1.1). This is the module gate.
2. **roles → capabilities** — expand each surviving role into its capabilities
   via ``ROLE_PERMISSIONS`` and union them. This is the ``validate_permissions``
   expansion.

Backing-agnostic (S1/S3 rule)
-----------------------------
The resolver reads ``tenant_modules`` activity + ``MODULE_REGISTRY`` role rules
only; it NEVER inspects a module's optional ``backing`` block. A ``sam`` module
resolves exactly like a ``flask`` one.

Global roles (R1.4)
-------------------
``SysAdmin`` / ``Administrators`` / ``System_CRUD`` are global roles whose
authority is the ``cognito:groups`` claim (S3 contract). They are NOT re-derived
here — the resolver produces the **per-tenant** answer only. A global role
appearing in a user's per-tenant rows is treated like any other role: it is
only honoured if it grants an active module (in practice these global roles are
not module ``required_roles``, so they contribute nothing to the per-tenant
map, which is correct — their authority stays the groups claim).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from auth.cognito_utils import ROLE_PERMISSIONS

# Global roles whose authority is the cognito:groups claim (S3 contract, R1.4).
# The resolver does not re-derive these; they are documented here for callers
# that may want the passthrough set, but the per-tenant map never invents them.
GLOBAL_ROLES: frozenset[str] = frozenset(
    {"SysAdmin", "Administrators", "System_CRUD"}
)


def _roles_granting_active_modules(
    roles: set[str],
    active_modules: set[str],
    module_registry: Mapping[str, Mapping],
) -> set[str]:
    """Return the subset of ``roles`` that grant an ACTIVE module (the module gate).

    A role is kept iff there exists a module that is (a) active for the tenant
    and (b) lists that role in its ``required_roles``. Roles for inactive/absent
    modules are dropped — mirroring ``module_registry`` ``has_module`` +
    ``required_roles`` gate (R1.1). Pure set logic; no I/O.
    """
    granting: set[str] = set()
    for module_name in active_modules:
        descriptor = module_registry.get(module_name)
        if not descriptor:
            # Active module not in the registry contributes no known roles.
            continue
        required = descriptor.get("required_roles", []) or []
        for role in required:
            if role in roles:
                granting.add(role)
    return granting


def resolve_entitlement(
    user_roles_by_tenant: Mapping[str, Sequence[str]],
    active_modules_by_tenant: Mapping[str, Sequence[str]],
    module_registry: Mapping[str, Mapping],
) -> dict[str, list[str]]:
    """Resolve a user's per-tenant entitlement (roles ∩ active modules → caps).

    Pure and deterministic (R1.2): no DB, clock, env, or network. The caller
    (the PreTokenGen Lambda / the Flask plane) fetches the rows and passes them
    in; this function computes the answer.

    Args:
        user_roles_by_tenant: ``{tenant -> [role, ...]}`` — the user's
            ``user_tenant_roles`` grants, grouped by tenant. Duplicate roles are
            tolerated (deduplicated).
        active_modules_by_tenant: ``{tenant -> [module_name, ...]}`` — the
            module names that are ACTIVE (``is_active``) for each tenant (the
            caller filters ``tenant_modules`` to active rows before passing).
        module_registry: ``MODULE_REGISTRY`` (or a compatible mapping). Only the
            module -> ``required_roles`` rule is read; the optional ``backing``
            block is ignored (backing-agnostic).

    Returns:
        ``{tenant -> sorted list[str] of capabilities}`` for every tenant the
        user has roles in. A tenant with no active modules — or whose active
        modules are granted by none of the user's roles — maps to an empty list
        (the tenant key is still present so callers see the user belongs there).
        Ordering is stable (sorted) so the result is deterministic and
        encodes compactly (R1.1, T4).

    Notes:
        - **R1.1** capabilities = union over the user's roles in the tenant,
          filtered to roles whose module is ACTIVE, expanded via
          ``ROLE_PERMISSIONS``. A role for an inactive/absent module contributes
          nothing.
        - **R1.4** global roles are not re-derived — their authority is
          ``cognito:groups``. This produces the per-tenant answer only.
        - A wildcard-permission role (``"*"`` in ``ROLE_PERMISSIONS``) that
          happens to be granted by an active module yields the single ``"*"``
          capability for that tenant, matching
          :func:`auth.cognito_utils.get_permissions_for_roles`.
    """
    resolved: dict[str, list[str]] = {}

    for tenant, roles_seq in user_roles_by_tenant.items():
        roles = {r for r in (roles_seq or []) if r}
        active_modules = {
            m for m in (active_modules_by_tenant.get(tenant, []) or []) if m
        }

        # Step 1 — the module gate: keep only roles that grant an active module.
        granting_roles = _roles_granting_active_modules(
            roles, active_modules, module_registry
        )

        # Step 2 — expand roles into capabilities (mirrors validate_permissions).
        # A wildcard role short-circuits to full access, exactly like
        # get_permissions_for_roles.
        capabilities: set[str] = set()
        wildcard = False
        for role in granting_roles:
            perms = ROLE_PERMISSIONS.get(role, [])
            if "*" in perms:
                wildcard = True
                break
            capabilities.update(perms)

        if wildcard:
            resolved[tenant] = ["*"]
        else:
            resolved[tenant] = sorted(capabilities)

    return resolved
