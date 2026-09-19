"""
S5 Task 3.1 — tests for ``resolve_scope_access`` (design C4, R3.3, Property 4).

These pin the observable scope-resolution contract that generalizes h-dcn's
``determine_regional_access``: an admin / all-wildcard role sees everything (``["*"]``); a
scoped role sees its subset (unioned when multi-valued); a ``required_for`` capability held
without any scope grant is **denied** (``[]``, ``access_type="none"``) — the critical
deny-by-default safety property; and a disabled / absent dimension collapses to tenant-wide.
The role→value mapping is derived generically from the dimension (prefix inferred from
``all_wildcard``), not hardcoded to h-dcn's ``Regio_``.

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
    HDCN_SCOPE_CONFIG,
    WILDCARD,
    ScopeConfig,
    ScopeDimension,
)

TENANT = "h-dcn"
REGION = HDCN_SCOPE_CONFIG[0]


# ── all-wildcard role → ["*"], access_type "all" ─────────────────────────────────────


def test_all_wildcard_role_grants_full_access_wildcard():
    access = resolve_scope_access(TENANT, REGION, ["Regio_All"])
    assert access.full_access is True
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"
    assert access.is_wildcard() is True


def test_all_wildcard_wins_over_a_scoped_role():
    # Holding both the national wildcard and a regional role still resolves to tenant-wide.
    access = resolve_scope_access(TENANT, REGION, ["Regio_Noord", "Regio_All"])
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


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
    dim = ScopeDimension(key="region", values=("Noord",), all_wildcard="Regio_All")
    object.__setattr__(dim, "admin_roles", ("RegioBeheerder",))
    access = resolve_scope_access(TENANT, dim, ["RegioBeheerder"])
    assert access.access_type == "admin"
    assert access.allowed_scopes == [WILDCARD]


# ── scoped role → subset, access_type "scoped" ───────────────────────────────────────


def test_single_scoped_role_grants_its_value():
    access = resolve_scope_access(TENANT, REGION, ["Regio_Noord"])
    assert access.full_access is False
    assert access.allowed_scopes == ["Noord"]
    assert access.access_type == "scoped"


def test_multiple_scoped_roles_union_in_declared_order():
    access = resolve_scope_access(TENANT, REGION, ["Regio_West", "Regio_Noord"])
    # Union preserves the dimension's declared value order (Noord before West).
    assert access.allowed_scopes == ["Noord", "West"]
    assert access.access_type == "scoped"


def test_multi_valued_dimension_unions_grants():
    dim = ScopeDimension(
        key="team",
        enabled=True,
        multi_valued=True,
        values=("A", "B", "C"),
        all_wildcard="Team_All",
        required_for=("Members_CRUD",),
    )
    access = resolve_scope_access("soccer", dim, ["Team_A", "Team_C"])
    assert access.allowed_scopes == ["A", "C"]
    assert access.access_type == "scoped"


def test_bare_value_role_also_grants_the_value():
    # A tenant that names its roles exactly after the values (no prefix) still resolves.
    dim = ScopeDimension(key="region", values=("Noord", "Zuid"))
    access = resolve_scope_access(TENANT, dim, ["Noord"])
    assert access.allowed_scopes == ["Noord"]
    assert access.access_type == "scoped"


def test_unknown_scoped_role_grants_nothing():
    # A Regio_* role for a value the dimension does not declare is ignored → deny.
    access = resolve_scope_access(TENANT, REGION, ["Regio_Onbekend"])
    assert access.allowed_scopes == []
    assert access.access_type == "none"


# ── deny: required_for capability without a grant (Property 4) ────────────────────────


def test_required_for_capability_without_grant_is_denied():
    # h-dcn: holding Members_CRUD with NO region role → deny (permission requires region).
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
    disabled = ScopeDimension(
        key="region", enabled=False, values=("Noord",), all_wildcard="Regio_All"
    )
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
    cfg = ScopeConfig(tenant_id=TENANT, dimensions=HDCN_SCOPE_CONFIG)
    access = resolve_scope_access_for_config(cfg, "region", ["Regio_Zuid"])
    assert access.allowed_scopes == ["Zuid"]
    assert access.access_type == "scoped"


def test_for_config_tenant_wide_config_is_wildcard():
    cfg = ScopeConfig(tenant_id="plain-club", dimensions=())
    access = resolve_scope_access_for_config(cfg, "region", ["Members_CRUD"])
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


def test_for_config_absent_dimension_key_is_tenant_wide():
    cfg = ScopeConfig(tenant_id=TENANT, dimensions=HDCN_SCOPE_CONFIG)
    access = resolve_scope_access_for_config(cfg, "season", ["Regio_Noord"])
    # The requested dimension does not exist → nothing to scope by → tenant-wide.
    assert access.allowed_scopes == [WILDCARD]
    assert access.access_type == "all"


# ── Property-based tests ──────────────────────────────────────────────────────────────

_VALUES = ("Noord", "Zuid", "Oost", "West")


@given(st.lists(st.sampled_from(_VALUES), min_size=1, max_size=4, unique=True))
def test_property_scoped_roles_resolve_to_their_union(chosen):
    # Any non-empty set of Regio_<Value> roles resolves to exactly that set of values, in
    # the dimension's declared order, with access_type "scoped" (never a wildcard).
    roles = [f"Regio_{v}" for v in chosen]
    access = resolve_scope_access(TENANT, REGION, roles)
    assert access.access_type == "scoped"
    assert access.allowed_scopes == [v for v in _VALUES if v in set(chosen)]
    assert WILDCARD not in access.allowed_scopes


@given(st.lists(st.text(min_size=1, max_size=10), max_size=5))
def test_property_no_scope_grant_never_yields_wildcard(noise):
    # Roles that are neither admin, the all-wildcard, nor a decodable scoped role must never
    # yield tenant-wide access — scope-deny is the default (Property 4).
    forbidden = ADMIN_ROLE_DEFAULTS | {REGION.all_wildcard}
    forbidden |= {f"Regio_{v}" for v in _VALUES} | set(_VALUES)
    roles = [r for r in noise if r not in forbidden]
    access = resolve_scope_access(TENANT, REGION, roles)
    assert access.allowed_scopes == []
    assert access.access_type == "none"
    assert access.full_access is False
