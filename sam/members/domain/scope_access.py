"""
S5 Task 3.1 — ``resolve_scope_access`` (design C4, R3.2/R3.3/R3.4, Property 4).

This module owns the **access-resolution algorithm** that turns a user's roles into the
set of scope values they may see / act on within a tenant. It generalizes h-dcn's
``determine_regional_access`` / ``validate_permissions_with_regions`` (see
``scope-dimension-design.md`` §3) without ever mentioning a tenant by name: the rules are
declarative, derived from the :class:`~sam.members.domain.scope_dimensions.ScopeDimension`
config that task 1.3 produced. h-dcn is simply the first tenant whose config carries a
``region`` dimension — there is **no** ``if tenant == "h-dcn"`` here.

The contract (design C4 / ``scope-dimension-design.md`` §3):

    resolve_scope_access(tenant, dimension, user_roles) -> ScopeAccess {
        full_access:   bool,                    # admin/national → all values
        allowed_scopes: [values] | ["*"],       # the set the user may see/act on
        access_type:    "admin" | "all" | "scoped" | "none",
    }

The rules (each maps 1:1 to the h-dcn behaviour it generalizes):

- **Admin role** — a role in the dimension's ``admin_roles`` (or the tenant-agnostic
  ``ADMIN_ROLE_DEFAULTS``) → ``full_access=True``, ``allowed_scopes=["*"]``,
  ``access_type="admin"``. (h-dcn: a system/national admin sees every region.)
- **Scoped grant(s)** — bare declared-value names the caller carries (``"Noord"``) →
  ``allowed_scopes`` = the union of the granted values, ``access_type="scoped"``. A grant of
  several values naturally unions.
- **Deny (the critical safety default, Property 4)** — the user holds a capability the
  dimension lists in ``required_for`` but has **no** scope grant in this dimension →
  ``full_access=False``, ``allowed_scopes=[]``, ``access_type="none"``. This is h-dcn's
  "permission requires region assignment": ``Members_CRUD`` with no scope grant is a deny,
  never a tenant-wide allow. **Scope-deny is the default**, not an exceptional branch.
- **Disabled / no dimension** — a disabled dimension is a no-op: everyone resolves to
  ``full_access=True``, ``allowed_scopes=["*"]``, ``access_type="all"`` (the tenant-wide
  collapse, R3.2). :func:`resolve_scope_access_for_config` applies this for a whole config.

s5d clean break (R2.2/R8.1, design → Projection Components item 4, Property 5): the ``Regio_*``
scope-in-role-name encoding is REMOVED. Scope is an INDEPENDENT axis sourced from
``user_tenant_scope`` → the projected ``scopegrant#`` row, not decoded from a role name — so
there is no ``all_wildcard`` role, no ``Regio_`` prefix, and no scoped-role decoder. A scoped
grant here is a BARE declared-value name; the all-access sentinel travels the GRANT side as the
projected ``["*"]`` and is mapped at the edge (``_scope_access_from_grant``). Capability roles
(``user_tenant_roles``) never grant scope — removing scope from a role never removes a
capability role.

Layering (per ``sam-module-architecture.md``): SAM-plane **domain** code — storage-agnostic,
tenant-agnostic, no boto3/DynamoDB, no HTTP. The handler edge (``handler/app.py``) calls
this behind its ``_resolve_scope_access`` seam; the repository/domain service then filters
reads by the resolved ``allowed_scopes`` (task 3.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfig,
    ScopeDimension,
)

__all__ = [
    "ScopeAccess",
    "ADMIN_ROLE_DEFAULTS",
    "resolve_scope_access",
    "resolve_scope_access_for_config",
]

#: Roles that grant tenant-wide (``["*"]``) access regardless of any dimension — the
#: platform-level admin/national roles h-dcn's ``determine_regional_access`` treats as
#: "sees everything". A dimension may extend this via ``ScopeDimension.admin_roles`` (not a
#: required field on the model); these defaults are the tenant-agnostic baseline. Kept as a
#: frozenset so it cannot be mutated by a caller.
ADMIN_ROLE_DEFAULTS: frozenset[str] = frozenset(
    {"SystemAdmin", "SysAdmin", "Admin", "TenantAdmin"}
)


@dataclass(frozen=True)
class ScopeAccess:
    """The resolved scope decision for one user against one dimension (design C4).

    Attributes:
        full_access: True when the user may see/act on every value (admin or all-wildcard,
            or a disabled dimension). Equivalent to ``allowed_scopes == [WILDCARD]``.
        allowed_scopes: The scope values the user may see/act on. ``["*"]`` (the
            :data:`~sam.members.domain.scope_dimensions.WILDCARD` sentinel) means
            tenant-wide; a subset means scoped; ``[]`` means **no** grant (deny).
        access_type: ``"admin"`` (platform admin), ``"all"`` (dimension all-wildcard),
            ``"scoped"`` (a subset of values), or ``"none"`` (deny — the safety default).
    """

    full_access: bool
    allowed_scopes: List[str] = field(default_factory=list)
    access_type: str = "none"

    def is_denied(self) -> bool:
        """True when the user has no scope grant (``access_type == "none"``)."""
        return self.access_type == "none"

    def is_wildcard(self) -> bool:
        """True when the user may see everything (``allowed_scopes == ["*"]``)."""
        return self.allowed_scopes == [WILDCARD]


def _admin_roles_for(dimension: ScopeDimension) -> frozenset[str]:
    """The admin roles that grant tenant-wide access for this dimension.

    ``ScopeDimension`` does not require an ``admin_roles`` field; if a tenant declares one
    it is honoured, otherwise the tenant-agnostic :data:`ADMIN_ROLE_DEFAULTS` apply. This
    keeps the model unchanged while letting a tenant name its own admin role declaratively.
    """
    extra = getattr(dimension, "admin_roles", None) or ()
    return ADMIN_ROLE_DEFAULTS | frozenset(str(r) for r in extra)


def _granted_values(dimension: ScopeDimension, user_roles: Sequence[str]) -> List[str]:
    """The subset of the dimension's declared values the user's roles grant (scoped).

    s5d clean break (R2.2/R8.1, Property 5): the ``Regio_*`` scope-in-role-name encoding is
    removed. Scope is now an INDEPENDENT axis sourced from ``user_tenant_scope`` → the
    projected ``scopegrant#`` row, so this decoder no longer infers a role prefix. A grant is
    only ever a BARE value name (``"Noord"``) — the projected value carried verbatim — matched
    against the dimension's declared values (order preserved, de-duplicated). Capability roles
    (``user_tenant_roles``) never grant scope here.
    """
    roles = set(user_roles)
    return [value for value in dimension.normalized_values() if value in roles]


def resolve_scope_access(
    tenant: str,
    dimension: Optional[ScopeDimension],
    user_roles: Sequence[str],
) -> ScopeAccess:
    """Resolve a user's scope access for one dimension (design C4, R3.3, Property 4).

    Generalizes h-dcn's ``determine_regional_access``. The ``tenant`` argument is for
    context/logging/hook dispatch only — the rules are declarative off ``dimension`` and
    ``user_roles`` (no ``if tenant == ...``). ``user_roles`` are the caller's **verified**
    roles (``cognito:groups``); ``dimension`` is the tenant's scope dimension (or ``None`` /
    disabled → tenant-wide).

    Resolution order (first match wins):

    1. **No / disabled dimension** → tenant-wide (``["*"]``, ``"all"``). The collapse (R3.2).
    2. **Admin role** (``ADMIN_ROLE_DEFAULTS`` or the dimension's ``admin_roles``) →
       ``["*"]``, ``"admin"``.
    3. **Scoped grant(s)** (bare declared-value names the caller carries) → the union subset,
       ``"scoped"``.
    4. **Otherwise deny** — the user holds a ``required_for`` capability without a scope
       grant → ``[]``, ``"none"`` (Property 4). If the dimension has an **empty**
       ``required_for`` (scope is optional here), a user with no grant is *not* denied; they
       simply resolve to an empty scope set with ``access_type="none"`` (see below) — the
       domain filter treats that as "see nothing", which is the same safe outcome.

    Note on step 5: whether the user *holds* a ``required_for`` capability is inferred from
    ``user_roles`` — a role or capability name that appears in the dimension's
    ``required_for`` list. This mirrors h-dcn ("holding ``Members_CRUD`` needs a region").
    Either way the resolved ``allowed_scopes`` is empty; ``required_for`` only affects
    whether callers should treat the empty result as an explicit hard deny.

    Returns:
        A :class:`ScopeAccess`. ``allowed_scopes`` is ``["*"]`` (wildcard), a value subset,
        or ``[]`` (deny) — never ``None``.
    """
    # (1) No dimension or a disabled one → the tenant-wide collapse (R3.2). No code path
    #     differs for an un-partitioned tenant.
    if dimension is None or not dimension.enabled:
        return ScopeAccess(full_access=True, allowed_scopes=[WILDCARD], access_type="all")

    roles = set(user_roles)

    # (2) A platform admin role sees everything (h-dcn: national/system admin).
    if roles & _admin_roles_for(dimension):
        return ScopeAccess(
            full_access=True, allowed_scopes=[WILDCARD], access_type="admin"
        )

    # (3) Scoped grants → the union of the bare declared-value names the caller carries.
    #     (s5d clean break: the ``Regio_All`` all-wildcard role name is gone; the all-access
    #     sentinel travels the GRANT side as the projected ``["*"]``, handled at the edge.)
    granted = _granted_values(dimension, user_roles)
    if granted:
        return ScopeAccess(
            full_access=False, allowed_scopes=list(granted), access_type="scoped"
        )

    # (5) No grant → deny (Property 4). This is the DEFAULT: a required_for capability held
    #     without a scope grant is h-dcn's "permission requires region assignment" deny.
    return ScopeAccess(full_access=False, allowed_scopes=[], access_type="none")


def resolve_scope_access_for_config(
    config: ScopeConfig,
    dimension_key: str,
    user_roles: Sequence[str],
) -> ScopeAccess:
    """Resolve scope access for one dimension of a tenant's whole :class:`ScopeConfig`.

    Convenience wrapper the handler seam / domain service uses when it holds the tenant's
    full config rather than a single dimension. A tenant-wide config (no enabled
    dimensions), or a ``dimension_key`` that is absent or disabled, resolves to the
    tenant-wide collapse (``["*"]``, ``"all"``) — the same fail-*open*-to-tenant-wide the
    disabled-dimension rule gives, because an un-partitioned tenant has nothing to scope by.
    """
    if config.is_tenant_wide():
        return ScopeAccess(full_access=True, allowed_scopes=[WILDCARD], access_type="all")
    return resolve_scope_access(config.tenant_id, config.dimension(dimension_key), user_roles)
