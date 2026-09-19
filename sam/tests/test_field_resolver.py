"""
S5 Task 1.2 — tests for the per-tenant variable field overlay + FieldResolver (design C3).

These pin the resolver's contract: ``resolve(tenant_id)`` = fixed base ⊕ per-tenant overlay.

Unit tests cover the observable behaviour:
- an **empty / unknown** tenant overlay resolves to exactly the fixed base (fail-safe default);
- an overlay **adds** variable fields (under the ``overlay`` group, origin VARIABLE) — adding a
  tenant is pure data, no schema change (R2.2);
- an overlay may **override presentation** of a fixed field (label / visible / order) and may
  **tighten** an optional fixed field to required, but may **never** weaken a platform
  invariant (drop/loosen a required fixed field, collide with a fixed key, enum without
  choices) — those raise :class:`OverlayError`;
- the resolver is **tenant-agnostic** (Property 5): two tenants differ only by their overlay
  data, never by a code path.

Property-based tests assert the merge invariants hold across arbitrary overlays:
- the resolved config always **contains every fixed field** (an overlay is additive, never
  destructive); and
- adding N valid variable fields yields exactly N VARIABLE fields plus the fixed base.

Validates: Requirements R2.2, R2.3
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sam.members.domain.fixed_fields import FIXED_FIELDS, FieldType, canonical_keys
from sam.members.domain.field_resolver import (
    OVERLAY_GROUP,
    FieldConfig,
    FieldOrigin,
    FieldResolver,
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    ResolvedField,
    StaticOverlayProvider,
    TenantOverlay,
    TenantOverlayProvider,
)


# ── Helpers ───────────────────────────────────────────────────────────────────────────


def _resolver(overlays: dict[str, TenantOverlay] | None = None) -> FieldResolver:
    return FieldResolver(StaticOverlayProvider(overlays or {}))


_FIXED_DOTTED = set(canonical_keys())
_FIXED_KEYS = [f.key for f in FIXED_FIELDS]


# ── Fixed base: empty / unknown overlay resolves to exactly the base ──────────────────


def test_resolve_empty_overlay_returns_exactly_the_fixed_base():
    cfg = _resolver().resolve("h-dcn")
    assert isinstance(cfg, FieldConfig)
    assert cfg.tenant_id == "h-dcn"
    assert {f.dotted_key() for f in cfg.fields} == _FIXED_DOTTED
    assert all(f.origin is FieldOrigin.FIXED for f in cfg.fields)
    assert cfg.variable_fields() == ()


def test_resolve_unknown_tenant_is_failsafe_not_error():
    # A tenant with no configured overlay yields the fixed base, never an exception.
    cfg = _resolver({"h-dcn": TenantOverlay()}).resolve("some-other-tenant")
    assert {f.dotted_key() for f in cfg.fields} == _FIXED_DOTTED


def test_resolve_preserves_fixed_field_type_and_choices():
    cfg = _resolver().resolve("h-dcn")
    status = cfg.field("membership.status")
    assert status is not None
    assert status.type is FieldType.ENUM
    assert status.choices is not None and len(status.choices) > 0


def test_resolve_rejects_blank_tenant_id():
    with pytest.raises(ValueError):
        _resolver().resolve("")
    with pytest.raises(ValueError):
        _resolver().resolve("   ")


# ── Overlay adds variable fields (R2.2 — adding a tenant is data, no schema change) ───


def test_overlay_adds_variable_field_under_overlay_group():
    overlay = TenantOverlay(
        fields={"motor_type": OverlayField(key="motor_type", label={"nl": "Motortype"})}
    )
    cfg = _resolver({"h-dcn": overlay}).resolve("h-dcn")

    mt = cfg.field("overlay.motor_type")
    assert mt is not None
    assert mt.group == OVERLAY_GROUP
    assert mt.origin is FieldOrigin.VARIABLE
    assert mt.label == {"nl": "Motortype"}
    # The fixed base is untouched — the overlay is purely additive.
    assert _FIXED_DOTTED.issubset({f.dotted_key() for f in cfg.fields})
    assert [f.key for f in cfg.variable_fields()] == ["motor_type"]


def test_adding_a_tenant_needs_no_schema_change_only_new_overlay_data():
    # Two tenants, same resolver code, differ ONLY by overlay data (Property 5 / R2.2).
    provider = StaticOverlayProvider(
        {
            "club-a": TenantOverlay(fields={"boat_name": OverlayField(key="boat_name")}),
            "club-b": TenantOverlay(fields={"belt_rank": OverlayField(key="belt_rank")}),
        }
    )
    resolver = FieldResolver(provider)
    assert [f.key for f in resolver.resolve("club-a").variable_fields()] == ["boat_name"]
    assert [f.key for f in resolver.resolve("club-b").variable_fields()] == ["belt_rank"]
    # A brand-new tenant not in the provider still resolves (to the base) — no code change.
    assert resolver.resolve("club-c").variable_fields() == ()


def test_enum_variable_field_carries_choices():
    overlay = TenantOverlay(
        fields={
            "fuel": OverlayField(key="fuel", type=FieldType.ENUM, choices=("petrol", "electric"))
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    fuel = cfg.field("overlay.fuel")
    assert fuel is not None and fuel.type is FieldType.ENUM
    assert tuple(fuel.choices) == ("petrol", "electric")


# ── Overlay overrides presentation of fixed fields (R2.3 — frontend renders resolved) ─


def test_override_relabels_reorders_and_hides_a_fixed_field():
    overlay = TenantOverlay(
        overrides={
            "personal.name": FixedFieldOverride(label={"nl": "Volledige naam"}, order=5),
            "personal.birthdate": FixedFieldOverride(visible=False),
        }
    )
    cfg = _resolver({"h-dcn": overlay}).resolve("h-dcn")

    name = cfg.field("personal.name")
    assert name is not None and name.label == {"nl": "Volledige naam"} and name.order == 5
    assert name.origin is FieldOrigin.FIXED  # still a fixed field, just re-presented

    birthdate = cfg.field("personal.birthdate")
    assert birthdate is not None and birthdate.visible is False
    # A hidden fixed field is still present in the config, just excluded from visible_fields().
    assert birthdate not in cfg.visible_fields()
    assert birthdate in cfg.fields


def test_override_can_tighten_optional_fixed_field_to_required():
    # 'personal.address' is optional in the base; a tenant may require it.
    overlay = TenantOverlay(overrides={"personal.address": FixedFieldOverride(required=True)})
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("personal.address").required is True


# ── Overlay may NEVER weaken a platform invariant ─────────────────────────────────────


def test_overlay_cannot_loosen_a_platform_required_field():
    # 'personal.name' is platform-required; an overlay must not make it optional.
    overlay = TenantOverlay(overrides={"personal.name": FixedFieldOverride(required=False)})
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "personal.name" in exc.value.reasons


def test_overlay_cannot_override_an_unknown_fixed_field():
    overlay = TenantOverlay(overrides={"personal.nope": FixedFieldOverride(visible=False)})
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "personal.nope" in exc.value.reasons


def test_variable_field_cannot_collide_with_a_fixed_field_key():
    overlay = TenantOverlay(fields={"status": OverlayField(key="status")})
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert f"{OVERLAY_GROUP}.status" in exc.value.reasons


def test_enum_variable_field_without_choices_is_rejected():
    overlay = TenantOverlay(fields={"grade": OverlayField(key="grade", type=FieldType.ENUM)})
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert f"{OVERLAY_GROUP}.grade" in exc.value.reasons


def test_all_overlay_violations_are_collected_at_once():
    overlay = TenantOverlay(
        fields={"grade": OverlayField(key="grade", type=FieldType.ENUM)},  # missing choices
        overrides={"membership.member_number": FixedFieldOverride(required=False)},  # loosen
    )
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "membership.member_number" in exc.value.reasons
    assert f"{OVERLAY_GROUP}.grade" in exc.value.reasons


# ── Ordering + grouping (the shape the frontend renders) ──────────────────────────────


def test_by_group_buckets_fixed_and_overlay_fields():
    overlay = TenantOverlay(fields={"motor_type": OverlayField(key="motor_type")})
    cfg = _resolver({"h-dcn": overlay}).resolve("h-dcn")
    groups = cfg.by_group()
    assert set(groups) == {"personal", "membership", OVERLAY_GROUP}
    assert all(f.origin is FieldOrigin.VARIABLE for f in groups[OVERLAY_GROUP])


def test_fields_are_deterministically_ordered():
    overlay = TenantOverlay(fields={"z": OverlayField(key="z", order=1), "a": OverlayField(key="a", order=1)})
    cfg = _resolver({"t": overlay}).resolve("t")
    keys = [(f.group, f.order, f.key) for f in cfg.fields]
    assert keys == sorted(keys)


# ── The provider seam is a structural Protocol (mirrors FieldConfigMixin) ─────────────


def test_static_provider_satisfies_the_protocol():
    assert isinstance(StaticOverlayProvider(), TenantOverlayProvider)


def test_resolver_uses_an_injected_provider_not_hardwired_storage():
    class RecordingProvider:
        def __init__(self):
            self.seen: list[str] = []

        def get_overlay(self, tenant_id: str) -> TenantOverlay:
            self.seen.append(tenant_id)
            return TenantOverlay()

    provider = RecordingProvider()
    FieldResolver(provider).resolve("h-dcn")
    assert provider.seen == ["h-dcn"]


# ── Property-based tests ──────────────────────────────────────────────────────────────

# Overlay field keys that never collide with the fixed registry (so overlays are valid).
_safe_key = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",), min_codepoint=97, max_codepoint=122),
    min_size=3,
    max_size=12,
).filter(lambda s: s not in _FIXED_KEYS)


@st.composite
def _valid_overlays(draw) -> TenantOverlay:
    """Build a valid overlay: a set of distinct, non-colliding string variable fields."""
    names = draw(st.lists(_safe_key, min_size=0, max_size=5, unique=True))
    fields = {n: OverlayField(key=n, order=draw(st.integers(min_value=0, max_value=100))) for n in names}
    return TenantOverlay(fields=fields)


@given(_valid_overlays())
def test_property_resolved_config_always_contains_every_fixed_field(overlay):
    # An overlay is additive: no matter what it adds, every fixed field survives (Property 5).
    cfg = FieldResolver(StaticOverlayProvider({"t": overlay})).resolve("t")
    assert _FIXED_DOTTED.issubset({f.dotted_key() for f in cfg.fields})


@given(_valid_overlays())
def test_property_variable_count_matches_overlay_and_base_is_constant(overlay):
    cfg = FieldResolver(StaticOverlayProvider({"t": overlay})).resolve("t")
    fixed = [f for f in cfg.fields if f.origin is FieldOrigin.FIXED]
    variable = [f for f in cfg.fields if f.origin is FieldOrigin.VARIABLE]
    assert len(fixed) == len(FIXED_FIELDS)
    assert len(variable) == len(overlay.fields)
    # Every resolved field key is unique (dotted) — no fixed/variable collision slipped through.
    dotted = [f.dotted_key() for f in cfg.fields]
    assert len(dotted) == len(set(dotted))
