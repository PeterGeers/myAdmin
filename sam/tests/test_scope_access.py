"""
S5 Task 3.1 — tests for ``resolve_scope_access`` (design C4, R3.3, Property 4).

These pin the observable scope-resolution contract that generalizes h-dcn's
``determine_regional_access``: an admin role sees everything (``["*"]``); a scoped grant
(a bare declared-value name) sees its subset (unioned when multi-valued); a ``required_for``
capability held without any scope grant is **denied** (``[]``, ``access_type="none"``) — the
critical deny-by-default safety property; and a disabled / absent dimension collapses to
tenant-wide.

s5d clean break (R2.2/R8.1, design → Projection Components item 4, Property 5): the ``Regio_*``
scope-in-role-name encoding is REMOVED. Scope is an INDEPENDENT axis sourced from
``user_tenant_scope`` → the projected ``scopegrant#`` row, not decoded from a role name — so
there is no ``all_wildcard`` role and no ``Regio_`` prefix decode. A scoped grant is a BARE
declared-value name; the all-access sentinel travels the GRANT side as the projected ``["*"]``
and is mapped at the edge (``_scope_access_from_grant``). This suite covers the domain
resolver's remaining responsibilities (admin, bare scoped grants, deny, tenant-wide collapse).

Validates: Requirements R3.2, R3.3, R3.4
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from sam.members.domain.scope_access import (
    ADMIN_ROLE_DEFAULTS,
    ScopeAccess,
    resolve_scope_access,
    resolve_scope_access_for_config,
)
from sam.members.domain.scope_dimensions import (
    SAMPLE_SCOPE_CONFIG,
    WILDCARD,
    ScopeConfig,
    ScopeDimension,
)

TENANT = "h-dcn"
REGION = SAMPLE_SCOPE_CONFIG[0]

# Sample values DERIVED from the live region config (not hardcoded), so these tests stay
# valid as the h-dcn vocabulary evolves. _V1/_V2 are two distinct declared values in
# declared order; _V1_FIRST/_V2_SECOND preserve that order for union assertions.
_R_VALUES = list(REGION.values)
_V1, _V2 = _R_VALUES[0], _R_VALUES[1]


# ── admin role → ["*"], access_type "admin" ──────────────────────────────────────────


def test_admin_role_grants_full_access_admin():
    for admin in sorted(ADMIN_ROLE_DEFAULTS):
        access = resolve_scope_access(TENANT, REGION, [admin])
        assert access.full_access is True
        assert access.allowed_scopes == [WILDCARD]
        assert access.access_type == "admin"


def test_dimension_declared_admin_role_is_honoured():
    # A tenant may name its own admin role declaratively; the model does not require the
    # field, so a dimension carrying an ``admin_roles`` attribute extends the defaults.
    dim = ScopeDimension(key="region", values=("Noord",))
    object.__setattr__(dim, "admin_roles", ("RegioBeheerder",))
    access = resolve_scope_access(TENANT, dim, ["RegioBeheerder"])
    assert access.access_type == "admin"
    assert access.allowed_scopes == [WILDCARD]


# ── scoped grant (bare declared-value name) → subset, access_type "scoped" ────────────


def test_single_scoped_grant_grants_its_value():
    access = resolve_scope_access(TENANT, REGION, [_V1])
    assert access.full_access is False
    assert access.allowed_scopes == [_V1]
    assert access.access_type == "scoped"


def test_multiple_scoped_grants_union_in_declared_order():
    # Grant the two values out of declared order; the result preserves declared order (_V1, _V2).
    access = resolve_scope_access(TENANT, REGION, [_V2, _V1])
    assert access.allowed_scopes == [_V1, _V2]
    assert access.access_type == "scoped"


def test_multiple_grants_union_across_dimension_values():
    # The USER GRANT is multi-value: two granted values union into the allowed set.
    dim = ScopeDimension(
        key="team",
        enabled=True,
        values=("A", "B", "C"),
        required_for=("Members_CRUD",),
    )
    access = resolve_scope_access("soccer", dim, ["A", "C"])
    assert access.allowed_scopes == ["A", "C"]
    assert access.access_type == "scoped"


def test_unknown_scoped_grant_grants_nothing():
    # A value the dimension does not declare is ignored → deny.
    access = resolve_scope_access(TENANT, REGION, ["Onbekend"])
    assert access.allowed_scopes == []
    assert access.access_type == "none"


# ── deny: required_for capability without a grant (Property 4) ────────────────────────


def test_required_for_capability_without_grant_is_denied():
    # h-dcn: holding Members_CRUD with NO region grant → deny (permission requires region).
    access = resolve_scope_access(TENANT, REGION, ["Members_CRUD"])
    assert access.full_access is False
    assert access.allowed_scopes == []
    assert access.access_type == "none"
    assert access.is_denied() is True


def test_empty_roles_are_denied_when_dimension_enabled():
    access = resolve_scope_access(TENANT, REGION, [])
    assert access.allowed_scopes == []
    assert access.access_type == "none"


def test_unrelated_roles_are_denied():
    access = resolve_scope_access(TENANT, REGION, ["SomeOtherApp_Reader"])
    assert access.allowed_scopes == []
    assert access.access_type == "none"


# ── disabled / absent dimension → tenant-wide (R3.2) ─────────────────────────────────


def test_disabled_dimension_collapses_to_tenant_wide():
    disabled = ScopeDimension(key="region", enabled=False, values=("Noord",))
    access = resolve_scope_access(TENANT, disabled, ["Members_CRUD"])
    assert access.full_access is True
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


def test_none_dimension_is_tenant_wide():
    access = resolve_scope_access(TENANT, None, [])
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


# ── resolve_scope_access_for_config wrapper ──────────────────────────────────────────


def test_for_config_resolves_the_named_dimension():
    cfg = ScopeConfig(tenant_id=TENANT, dimensions=SAMPLE_SCOPE_CONFIG)
    access = resolve_scope_access_for_config(cfg, "region", [_V2])
    assert access.allowed_scopes == [_V2]
    assert access.access_type == "scoped"


def test_for_config_tenant_wide_config_is_wildcard():
    cfg = ScopeConfig(tenant_id="plain-club", dimensions=())
    access = resolve_scope_access_for_config(cfg, "region", ["Members_CRUD"])
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


def test_for_config_absent_dimension_key_is_tenant_wide():
    cfg = ScopeConfig(tenant_id=TENANT, dimensions=SAMPLE_SCOPE_CONFIG)
    access = resolve_scope_access_for_config(cfg, "season", [_V1])
    # The requested dimension does not exist → nothing to scope by → tenant-wide.
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


# ── Property-based tests ──────────────────────────────────────────────────────────────

_VALUES = tuple(REGION.values)  # the live h-dcn region vocabulary (derived, not hardcoded)


@given(st.lists(st.sampled_from(_VALUES), min_size=1, max_size=4, unique=True))
def test_property_scoped_grants_resolve_to_their_union(chosen):
    # Any non-empty set of bare declared-value grants resolves to exactly that set of values,
    # in the dimension's declared order, with access_type "scoped" (never a wildcard).
    access = resolve_scope_access(TENANT, REGION, list(chosen))
    assert access.access_type == "scoped"
    assert access.allowed_scopes == [v for v in _VALUES if v in set(chosen)]
    assert WILDCARD not in access.allowed_scopes


@given(st.lists(st.text(min_size=1, max_size=10), max_size=5))
def test_property_no_scope_grant_never_yields_wildcard(noise):
    # Roles that are neither an admin role nor a declared scope value must never yield
    # tenant-wide access — scope-deny is the default (Property 4).
    forbidden = ADMIN_ROLE_DEFAULTS | set(_VALUES)
    roles = [r for r in noise if r not in forbidden]
    access = resolve_scope_access(TENANT, REGION, roles)
    assert access.allowed_scopes == []
    assert access.access_type == "none"
    assert access.full_access is False
