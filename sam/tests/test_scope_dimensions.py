"""
S5 Task 1.3 — tests for the scope-dimension model (multi-valued-capable; h-dcn = region).

Unit tests pin the model's shape (a LIST of dimensions, each with enabled / multi_valued /
values / all_wildcard / required_for), its config validation (fail fast on a
misconfiguration), the tenant-wide collapse when a dimension is disabled, the provider seam
(empty config for unknown tenants), and the h-dcn wiring (single, single-valued region). A
property test asserts that any list of enabled dimensions with distinct keys and non-empty,
unique values always constructs, and that the tenant-wide collapse holds iff no dimension is
enabled.

Validates: Requirements R3.2, R3.3, R3.4
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sam.members.domain.scope_dimensions import (
    HDCN_SCOPE_CONFIG,
    WILDCARD,
    ScopeConfig,
    ScopeConfigError,
    ScopeConfigProvider,
    ScopeDimension,
    StaticScopeConfigProvider,
    enabled_dimensions,
)


# ── Model shape ───────────────────────────────────────────────────────────────────────


def test_scope_dimensions_is_a_list_supporting_multiple_dimensions():
    # R3.2/R3.4: multi-dimension capable from day one (region + season).
    region = ScopeDimension(key="region", values=("Noord",))
    season = ScopeDimension(key="season", values=("2024-2025",))
    cfg = ScopeConfig(tenant_id="soccer", dimensions=(region, season))
    assert cfg.dimensions == (region, season)
    assert cfg.dimension("region") is region
    assert cfg.dimension("season") is season
    assert cfg.dimension("nope") is None


def test_dimension_carries_all_configured_facets():
    d = ScopeDimension(
        key="region",
        label={"nl": "Regio", "en": "Region"},
        enabled=True,
        multi_valued=False,
        values=("Noord", "Zuid"),
        all_wildcard="Regio_All",
        required_for=("Members_CRUD",),
    )
    assert d.key == "region"
    assert d.enabled is True
    assert d.multi_valued is False
    assert d.values == ("Noord", "Zuid")
    assert d.all_wildcard == "Regio_All"
    assert d.required_for == ("Members_CRUD",)


def test_dimension_is_immutable():
    d = ScopeDimension(key="region", values=("Noord",))
    with pytest.raises((AttributeError, TypeError)):
        d.key = "mutated"  # type: ignore[misc]


def test_dimension_defaults_are_conservative():
    # A bare dimension is single-valued, has no wildcard/required_for, empty values/label.
    d = ScopeDimension(key="region", values=("Noord",))
    assert d.multi_valued is False
    assert d.all_wildcard is None
    assert d.required_for == ()
    assert dict(d.label) == {}


def test_allows_value_and_normalized_values():
    d = ScopeDimension(key="region", values=("Noord", "Zuid", "Noord"))
    assert d.allows_value("Noord") is True
    assert d.allows_value("Onbekend") is False
    # normalized_values de-duplicates while preserving first-seen order.
    assert d.normalized_values() == ("Noord", "Zuid")


# ── The tenant-wide collapse (enabled:false → ["*"]) ─────────────────────────────────


def test_empty_config_is_tenant_wide():
    cfg = ScopeConfig(tenant_id="plain-club", dimensions=())
    assert cfg.is_tenant_wide() is True
    assert cfg.enabled() == ()


def test_disabled_dimension_collapses_to_tenant_wide():
    # enabled:false must be a no-op — no enabled dimensions => tenant-wide (R3.2).
    disabled = ScopeDimension(key="region", enabled=False, values=("Noord",))
    cfg = ScopeConfig(tenant_id="club", dimensions=(disabled,))
    assert cfg.is_tenant_wide() is True
    assert cfg.enabled() == ()


def test_enabled_dimensions_filters_out_disabled_ones():
    on = ScopeDimension(key="region", enabled=True, values=("Noord",))
    off = ScopeDimension(key="season", enabled=False, values=("2024",))
    assert enabled_dimensions((on, off)) == (on,)


def test_at_least_one_enabled_dimension_is_not_tenant_wide():
    on = ScopeDimension(key="region", enabled=True, values=("Noord",))
    cfg = ScopeConfig(tenant_id="club", dimensions=(on,))
    assert cfg.is_tenant_wide() is False
    assert cfg.enabled() == (on,)


def test_wildcard_token_is_stable():
    assert WILDCARD == "*"


# ── Config validation (fail fast) ─────────────────────────────────────────────────────


def test_empty_tenant_id_rejected():
    with pytest.raises(ScopeConfigError):
        ScopeConfig(tenant_id="   ", dimensions=())


def test_blank_dimension_key_rejected():
    with pytest.raises(ScopeConfigError):
        ScopeConfig(tenant_id="club", dimensions=(ScopeDimension(key="  ", values=("A",)),))


def test_duplicate_dimension_keys_rejected():
    with pytest.raises(ScopeConfigError) as exc:
        ScopeConfig(
            tenant_id="club",
            dimensions=(
                ScopeDimension(key="region", values=("Noord",)),
                ScopeDimension(key="region", values=("Zuid",)),
            ),
        )
    assert "region" in exc.value.reasons


def test_enabled_dimension_without_values_rejected():
    with pytest.raises(ScopeConfigError) as exc:
        ScopeConfig(tenant_id="club", dimensions=(ScopeDimension(key="region", values=()),))
    assert "region" in exc.value.reasons


def test_disabled_dimension_without_values_is_allowed():
    # A disabled dimension is a no-op; it need not declare values.
    cfg = ScopeConfig(
        tenant_id="club",
        dimensions=(ScopeDimension(key="region", enabled=False, values=()),),
    )
    assert cfg.is_tenant_wide() is True


def test_blank_scope_value_rejected():
    with pytest.raises(ScopeConfigError) as exc:
        ScopeConfig(
            tenant_id="club",
            dimensions=(ScopeDimension(key="region", values=("Noord", "  ")),),
        )
    assert "region" in exc.value.reasons


def test_duplicate_scope_values_rejected():
    with pytest.raises(ScopeConfigError) as exc:
        ScopeConfig(
            tenant_id="club",
            dimensions=(ScopeDimension(key="region", values=("Noord", "Noord")),),
        )
    assert "region" in exc.value.reasons


def test_all_wildcard_must_not_be_a_scope_value():
    with pytest.raises(ScopeConfigError) as exc:
        ScopeConfig(
            tenant_id="club",
            dimensions=(
                ScopeDimension(
                    key="region", values=("Noord", "Regio_All"), all_wildcard="Regio_All"
                ),
            ),
        )
    assert "region" in exc.value.reasons


def test_all_config_errors_collected_at_once():
    with pytest.raises(ScopeConfigError) as exc:
        ScopeConfig(
            tenant_id="club",
            dimensions=(
                ScopeDimension(key="region", values=()),          # no values
                ScopeDimension(key="season", values=("A", "A")),  # duplicate values
            ),
        )
    assert set(exc.value.reasons) == {"region", "season"}


# ── The provider seam ─────────────────────────────────────────────────────────────────


def test_static_provider_returns_configured_tenant():
    provider = StaticScopeConfigProvider({"h-dcn": HDCN_SCOPE_CONFIG})
    cfg = provider.get_scope_config("h-dcn")
    assert cfg.tenant_id == "h-dcn"
    assert cfg.dimension("region") is not None


def test_static_provider_unknown_tenant_is_empty_tenant_wide():
    provider = StaticScopeConfigProvider({"h-dcn": HDCN_SCOPE_CONFIG})
    cfg = provider.get_scope_config("someone-else")
    assert cfg.dimensions == ()
    assert cfg.is_tenant_wide() is True


def test_static_provider_empty_by_default():
    provider = StaticScopeConfigProvider()
    assert provider.get_scope_config("anyone").is_tenant_wide() is True


def test_static_provider_validates_eagerly():
    # A malformed tenant config fails at provider construction, not lazily on read.
    with pytest.raises(ScopeConfigError):
        StaticScopeConfigProvider({"bad": (ScopeDimension(key="region", values=()),)})


def test_static_provider_satisfies_protocol():
    assert isinstance(StaticScopeConfigProvider(), ScopeConfigProvider)


# ── h-dcn wiring (single, single-valued region — R3.4) ───────────────────────────────


def test_hdcn_is_a_single_single_valued_region_dimension():
    cfg = ScopeConfig(tenant_id="h-dcn", dimensions=HDCN_SCOPE_CONFIG)
    enabled = cfg.enabled()
    assert len(enabled) == 1
    region = enabled[0]
    assert region.key == "region"
    assert region.multi_valued is False
    assert region.enabled is True
    assert region.all_wildcard == "Regio_All"
    assert set(region.values) == {"Noord", "Zuid", "Oost", "West"}
    assert "Members_CRUD" in region.required_for


def test_hdcn_disabled_collapses_to_tenant_wide():
    # Flipping h-dcn's dimension off must be a pure no-op (R3.2) — no code path differs.
    region = HDCN_SCOPE_CONFIG[0]
    disabled = ScopeDimension(
        key=region.key,
        label=region.label,
        enabled=False,
        multi_valued=region.multi_valued,
        values=region.values,
        all_wildcard=region.all_wildcard,
        required_for=region.required_for,
    )
    cfg = ScopeConfig(tenant_id="h-dcn", dimensions=(disabled,))
    assert cfg.is_tenant_wide() is True


# ── Property-based test ───────────────────────────────────────────────────────────────

_KEY = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12)
_VALUE = st.text(min_size=1, max_size=8).filter(lambda s: s.strip() != "")


@st.composite
def _enabled_dimensions(draw) -> tuple[ScopeDimension, ...]:
    """A list of enabled dimensions with distinct keys and non-empty, unique values."""
    keys = draw(st.lists(_KEY, min_size=0, max_size=4, unique=True))
    dims: list[ScopeDimension] = []
    for k in keys:
        values = draw(st.lists(_VALUE, min_size=1, max_size=5, unique=True))
        dims.append(
            ScopeDimension(
                key=k,
                enabled=True,
                multi_valued=draw(st.booleans()),
                values=tuple(values),
            )
        )
    return tuple(dims)


@given(_enabled_dimensions())
def test_property_well_formed_enabled_config_always_constructs(dims):
    # Any well-formed list of enabled dimensions must construct without error, and
    # tenant-wide holds iff there are no enabled dimensions (R3.2).
    cfg = ScopeConfig(tenant_id="t", dimensions=dims)
    assert cfg.enabled() == dims
    assert cfg.is_tenant_wide() is (len(dims) == 0)


@given(_enabled_dimensions())
def test_property_disabling_all_dimensions_is_tenant_wide(dims):
    disabled = tuple(
        ScopeDimension(
            key=d.key,
            enabled=False,
            multi_valued=d.multi_valued,
            values=d.values,
        )
        for d in dims
    )
    cfg = ScopeConfig(tenant_id="t", dimensions=disabled)
    assert cfg.is_tenant_wide() is True
    assert cfg.enabled() == ()
