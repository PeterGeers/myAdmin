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

Phase 3 step 8 (R1.2) collapses the former two-section fixed/overlay presentation into ONE
unified field list where each resolved field carries a DERIVED ``provenance`` marker
(``base`` / ``tenant_added`` / ``base_overridden``). The provenance cases below assert that
marker; crucially they do NOT touch the resolved field SET or the ``(group, order, key)``
ordering (Property 1, R1.6) — the collapse re-presents, it adds/removes/reorders nothing.

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

from sam.members.domain.calculated_fields import CALCULATED_FIELDS
from sam.members.domain.field_resolver import (
    OVERLAY_GROUP,
    FieldConfig,
    FieldOrigin,
    FieldProvenance,
    FieldResolver,
    FieldScope,
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
    TenantOverlayProvider,
)
from sam.members.domain.fixed_fields import FIXED_FIELDS, FieldType, canonical_keys

# ── Helpers ───────────────────────────────────────────────────────────────────────────


def _resolver(overlays: dict[str, TenantOverlay] | None = None) -> FieldResolver:
    return FieldResolver(StaticOverlayProvider(overlays or {}))


_FIXED_DOTTED = set(canonical_keys())
_FIXED_KEYS = [f.key for f in FIXED_FIELDS]
# Calculated (derived, read-only, never-stored) keys — added row-by-row from the design
# classification table (task 1.3). With no overlay the resolved config is the fixed base PLUS
# these derived fields; the property generators must also exclude these reserved keys so a
# variable-field draw never collides with e.g. ``age``.
_CALCULATED_DOTTED = {c.dotted_key() for c in CALCULATED_FIELDS}
_CALCULATED_KEYS = [c.key for c in CALCULATED_FIELDS]
# The resolved config with an empty overlay = fixed base ⊕ calculated derived fields.
_BASE_DOTTED = _FIXED_DOTTED | _CALCULATED_DOTTED
_RESERVED_KEYS = set(_FIXED_KEYS) | set(_CALCULATED_KEYS)


# ── Fixed base: empty / unknown overlay resolves to the base ⊕ calculated fields ──────


def test_resolve_empty_overlay_returns_exactly_the_fixed_base():
    # With no overlay the config is the fixed base PLUS the derived calculated fields (task 1.3);
    # every field is either FIXED or CALCULATED, and there are no VARIABLE (overlay) fields.
    cfg = _resolver().resolve("h-dcn")
    assert isinstance(cfg, FieldConfig)
    assert cfg.tenant_id == "h-dcn"
    assert {f.dotted_key() for f in cfg.fields} == _BASE_DOTTED
    assert all(
        f.origin in (FieldOrigin.FIXED, FieldOrigin.CALCULATED) for f in cfg.fields
    )
    assert {f.dotted_key() for f in cfg.fields if f.origin is FieldOrigin.FIXED} == _FIXED_DOTTED
    assert {
        f.dotted_key() for f in cfg.fields if f.origin is FieldOrigin.CALCULATED
    } == _CALCULATED_DOTTED
    assert cfg.variable_fields() == ()
    # Single-list provenance (R1.2): with NO overrides, every base field's badge is BASE.
    assert all(f.provenance is FieldProvenance.BASE for f in cfg.fields)


def test_resolve_unknown_tenant_is_failsafe_not_error():
    # A tenant with no configured overlay yields the base ⊕ calculated fields, never an exception.
    cfg = _resolver({"h-dcn": TenantOverlay()}).resolve("some-other-tenant")
    assert {f.dotted_key() for f in cfg.fields} == _BASE_DOTTED


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
    # Single-list provenance (R1.2): a tenant-defined overlay field badges as TENANT_ADDED.
    assert mt.provenance is FieldProvenance.TENANT_ADDED
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
            "personal.first_name": FixedFieldOverride(label={"nl": "Volledige naam"}, order=5),
            "personal.birth_date": FixedFieldOverride(visible=False),
        }
    )
    cfg = _resolver({"h-dcn": overlay}).resolve("h-dcn")

    name = cfg.field("personal.first_name")
    assert name is not None and name.label == {"nl": "Volledige naam"} and name.order == 5
    assert name.origin is FieldOrigin.FIXED  # still a fixed field, just re-presented
    # Single-list provenance (R1.2): an overridden base field badges as BASE_OVERRIDDEN.
    assert name.provenance is FieldProvenance.BASE_OVERRIDDEN

    birthdate = cfg.field("personal.birth_date")
    assert birthdate is not None and birthdate.visible is False
    assert birthdate.provenance is FieldProvenance.BASE_OVERRIDDEN
    # A hidden fixed field is still present in the config, just excluded from visible_fields().
    assert birthdate not in cfg.visible_fields()
    assert birthdate in cfg.fields

    # A base field with NO override in the same config still badges as plain BASE — the collapse
    # marks provenance per-field, it does not flip untouched base fields.
    last = cfg.field("personal.last_name")
    assert last is not None and last.provenance is FieldProvenance.BASE


def test_override_can_tighten_optional_fixed_field_to_required():
    # 'personal.street' is optional in the base; a tenant may require it.
    overlay = TenantOverlay(overrides={"personal.street": FixedFieldOverride(required=True)})
    cfg = _resolver({"t": overlay}).resolve("t")
    street = cfg.field("personal.street")
    assert street.required is True
    # Tightening is a presentation override, so the field badges as BASE_OVERRIDDEN (R1.2).
    assert street.provenance is FieldProvenance.BASE_OVERRIDDEN


# ── Overlay may NEVER weaken a platform invariant ─────────────────────────────────────


def test_overlay_cannot_loosen_a_platform_required_field():
    # 'personal.last_name' is platform-required (the identity anchor); an overlay must not make
    # it optional. (first_name is now optional, so last_name is the still-required example that
    # exercises the guard.)
    overlay = TenantOverlay(overrides={"personal.last_name": FixedFieldOverride(required=False)})
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "personal.last_name" in exc.value.reasons


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
        # loosen a still-required platform field — s5k made member_number optional, so `status`
        # is now the example of a required base field an overlay may NOT weaken.
        overrides={"membership.status": FixedFieldOverride(required=False)},  # loosen
    )
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "membership.status" in exc.value.reasons
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


# ── Single-list provenance (Phase 3 step 8, R1.2) ─────────────────────────────────────
#
# The former two-section fixed/overlay split is collapsed into ONE unified field list; each
# resolved field carries a DERIVED `provenance` badge (base / tenant_added / base_overridden).
# These cases pin that marker across all three origins coexisting in one config, and lock the
# Property-1 invariant at the unit level: adding provenance changes NEITHER the resolved field
# SET nor the `(group.order, field.order, key)` ordering (R1.3/R1.6).
#
# Validates: Requirements R1.6, R1.2


def test_single_list_carries_all_three_provenance_markers():
    # One config exercising all three: an overridden base field, an untouched base field, and a
    # tenant-added variable field — all in the SINGLE resolved list.
    overlay = TenantOverlay(
        overrides={"personal.first_name": FixedFieldOverride(label={"nl": "Naam"})},
        fields={"motor_type": OverlayField(key="motor_type")},
    )
    cfg = _resolver({"t": overlay}).resolve("t")

    assert cfg.field("personal.first_name").provenance is FieldProvenance.BASE_OVERRIDDEN
    assert cfg.field("personal.last_name").provenance is FieldProvenance.BASE  # untouched base
    assert cfg.field("overlay.motor_type").provenance is FieldProvenance.TENANT_ADDED
    # Every resolved field has exactly one of the three single-list provenance markers.
    assert all(
        f.provenance in (
            FieldProvenance.BASE,
            FieldProvenance.TENANT_ADDED,
            FieldProvenance.BASE_OVERRIDDEN,
        )
        for f in cfg.fields
    )


def test_provenance_collapse_preserves_resolved_set_and_order():
    # Property 1 at the unit level (R1.6): the provenance marker is PURELY additive — projecting
    # the resolved fields WITHOUT provenance (dotted key + the `(group, order, key)` sort key)
    # yields the same SET and the same order whether or not any field is overridden/added. The
    # badge re-presents; it adds, removes, and reorders nothing.
    base_overlay = TenantOverlay(fields={"motor_type": OverlayField(key="motor_type", order=5)})
    overridden_overlay = TenantOverlay(
        # Same variable field, PLUS presentation overrides on base fields that only flip
        # provenance to BASE_OVERRIDDEN — never the dotted key, group, order, or membership.
        fields={"motor_type": OverlayField(key="motor_type", order=5)},
        overrides={
            "personal.first_name": FixedFieldOverride(label={"nl": "Naam"}),
            "membership.status": FixedFieldOverride(label={"nl": "Toestand"}),
        },
    )
    base_cfg = _resolver({"t": base_overlay}).resolve("t")
    over_cfg = _resolver({"t": overridden_overlay}).resolve("t")

    # Resolved field SET identical.
    assert {f.dotted_key() for f in base_cfg.fields} == {
        f.dotted_key() for f in over_cfg.fields
    }
    # `(group.order, field.order, key)` ordering identical (the derived order, R1.3).
    assert [(f.group, f.order, f.key) for f in base_cfg.fields] == [
        (f.group, f.order, f.key) for f in over_cfg.fields
    ]
    # The only observable difference is the provenance badge on the two overridden base fields.
    assert over_cfg.field("personal.first_name").provenance is FieldProvenance.BASE_OVERRIDDEN
    assert over_cfg.field("membership.status").provenance is FieldProvenance.BASE_OVERRIDDEN
    assert base_cfg.field("personal.first_name").provenance is FieldProvenance.BASE
    assert base_cfg.field("membership.status").provenance is FieldProvenance.BASE


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
).filter(lambda s: s not in _RESERVED_KEYS)


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


# ══════════════════════════════════════════════════════════════════════════════════════
# S5c Task 1.5 — FieldResolver merge over the BROADENED base
#
# The base is now Fixed ⊕ Calculated, and resolved fields carry functional_group, options,
# show_when, and member_number_format. These tests pin that merge behaviour:
#   - resolve() over an EMPTY overlay yields fixed ⊕ calculated (origins ∈ {FIXED, CALCULATED},
#     zero VARIABLE), with calculated fields read-only and carrying their inputs;
#   - a non-empty overlay adds VARIABLE fields;
#   - functional_group defaults from the base and is overridable via a fixed_overrides entry
#     (for BOTH fixed and calculated fields), with the STORAGE group unchanged;
#   - member_number_format, options, and show_when surface on the resolved fields.
#
# Validates: Requirements R4.4, R4.9, R4.11, R4.12, R4.2, R4.8 (Property 2 basis)
# ══════════════════════════════════════════════════════════════════════════════════════

from sam.members.domain.field_resolver import FunctionalGroup
from sam.members.domain.fixed_fields import (
    EnumOption,
    MemberNumberFormat,
)


def test_empty_overlay_yields_fixed_plus_calculated_zero_variable():
    cfg = _resolver().resolve("t")
    origins = {f.origin for f in cfg.fields}
    assert origins == {FieldOrigin.FIXED, FieldOrigin.CALCULATED}
    assert cfg.variable_fields() == ()
    # One CALCULATED resolved field per calculated registry entry, all read-only + with inputs.
    calc = cfg.calculated_fields()
    assert {f.dotted_key() for f in calc} == _CALCULATED_DOTTED
    assert all(f.read_only for f in calc)
    assert all(f.required is False for f in calc)
    assert all(f.calculated_from for f in calc)
    # With no override, a calculated base field badges as BASE (R1.2) — never TENANT_ADDED.
    assert all(f.provenance is FieldProvenance.BASE for f in calc)


def test_calculated_field_carries_its_inputs():
    cfg = _resolver().resolve("t")
    display = cfg.field("personal.display_name")
    assert display is not None
    assert display.origin is FieldOrigin.CALCULATED
    assert tuple(display.calculated_from) == (
        "personal.first_name",
        "personal.name_infix",
        "personal.last_name",
    )


# ── functional_group: base default + tenant override (storage group unchanged) ─────────


def test_functional_group_defaults_from_the_base():
    cfg = _resolver().resolve("t")
    # A plain fixed field defaults its functional group to its storage group.
    assert cfg.field("personal.first_name").functional_group == "personal"
    # created_at carries an explicit base default of "administrative" (per the classification table).
    assert cfg.field("membership.created_at").functional_group == "administrative"
    # A calculated field defaults from the base too. application_year's base functional group
    # is "membership" (application/onboarding is part of the membership lifecycle — it derives
    # from joined_date when created_at is absent).
    assert cfg.field("membership.application_year").functional_group == "membership"


def test_functional_group_is_overridable_for_a_fixed_field_without_moving_storage():
    overlay = TenantOverlay(
        functional_groups={"address": FunctionalGroup(key="address", label={"en": "Address"})},
        overrides={"personal.street": FixedFieldOverride(functional_group="address")},
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    street = cfg.field("personal.street")
    assert street.functional_group == "address"   # display group moved
    assert street.group == "personal"             # storage bucket unchanged


def test_functional_group_is_overridable_for_a_calculated_field():
    overlay = TenantOverlay(
        functional_groups={"admin2": FunctionalGroup(key="admin2")},
        overrides={"membership.application_year": FixedFieldOverride(functional_group="admin2")},
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    ay = cfg.field("membership.application_year")
    assert ay.functional_group == "admin2"
    assert ay.origin is FieldOrigin.CALCULATED
    # A re-presented calculated base field badges as BASE_OVERRIDDEN, never TENANT_ADDED (R1.2).
    assert ay.provenance is FieldProvenance.BASE_OVERRIDDEN


def test_dangling_functional_group_reference_is_rejected():
    # A functional_group that is neither a base key nor in the tenant's authored catalog is
    # rejected fail-fast (Property 7). Here the tenant authored `address` but references
    # `not_in_catalog`, which is absent from BASE ⊕ tenant (R5.3).
    overlay = TenantOverlay(
        functional_groups={"address": FunctionalGroup(key="address")},
        overrides={"personal.city": FixedFieldOverride(functional_group="not_in_catalog")},
    )
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "personal.city" in exc.value.reasons


def test_variable_field_carries_its_functional_group():
    overlay = TenantOverlay(
        functional_groups={"motor": FunctionalGroup(key="motor")},
        fields={"motor_brand": OverlayField(key="motor_brand", functional_group="motor")},
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    mb = cfg.field("overlay.motor_brand")
    assert mb.functional_group == "motor"
    assert mb.origin is FieldOrigin.VARIABLE


# ── Base-group-aware reference validation: BASE_FUNCTIONAL_GROUPS ⊕ tenant (R4.2/R5.3/R5.4) ──
#
# Phase 1 task 4.1 (design §4): the resolver validates a field's `functional_group` against the
# catalog's group set = `BASE_FUNCTIONAL_GROUPS` ⊕ the tenant's authored `functional_groups`.
# A reference to a BASE key is valid even with NO authored catalog (R5.4), while a dangling
# reference to a non-base key is still rejected whether or not a catalog is authored. Nothing
# that resolved before this change fails now — every base-field default is a base key.
#
# Task 4.3 is the base-key-resolves / dangling-raises pair under R4.2/R5.4: a tenant with NO
# authored catalog resolves WITHOUT OverlayError when a field OR an override references a BASE
# key (both referencing paths below), and a dangling NON-base key still raises OverlayError.
#   - override path  → test_base_key_reference_resolves_with_no_authored_catalog
#   - field path     → test_base_key_variable_field_resolves_with_no_authored_catalog
#   - dangling raises → test_dangling_non_base_reference_is_rejected_without_an_authored_catalog
#
# Validates: Requirements R4.2, R5.4


def test_base_key_reference_resolves_with_no_authored_catalog():
    # R5.4: a tenant that authored NO functional_groups catalog but references a BASE group key
    # (here `administrative`, a base key) resolves WITHOUT OverlayError — the former
    # "empty catalog ⇒ unchecked" path is now "validated against the base set", and the base
    # set makes the reference valid.
    overlay = TenantOverlay(
        overrides={"personal.city": FixedFieldOverride(functional_group="administrative")},
    )
    assert not overlay.functional_groups  # no authored catalog
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("personal.city").functional_group == "administrative"


def test_base_key_variable_field_resolves_with_no_authored_catalog():
    # R5.4: a VARIABLE field referencing a base key (`membership`) also resolves against the base
    # set with no authored catalog — this is exactly the shape the scope-dimension overlays use.
    overlay = TenantOverlay(
        fields={"motor_brand": OverlayField(key="motor_brand", functional_group="membership")},
    )
    assert not overlay.functional_groups
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("overlay.motor_brand").functional_group == "membership"


def test_dangling_non_base_reference_is_rejected_without_an_authored_catalog():
    # R5.4 (strict side): with NO authored catalog, a reference to a NON-base key is a dangling
    # reference and is rejected — the base set does not make an arbitrary key valid.
    overlay = TenantOverlay(
        overrides={"personal.city": FixedFieldOverride(functional_group="not_a_base_group")},
    )
    assert not overlay.functional_groups
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "personal.city" in exc.value.reasons


def test_group_set_is_base_merged_with_tenant_catalog():
    # R5.3 (merge rule): the effective group set = BASE ⊕ tenant. A tenant that authored a
    # custom group (`motor`) can reference BOTH a base key (`administrative`) and its own key
    # in the same overlay and both resolve — base keys fill the set, the tenant key extends it.
    overlay = TenantOverlay(
        functional_groups={"motor": FunctionalGroup(key="motor", order=9)},
        overrides={
            "personal.city": FixedFieldOverride(functional_group="administrative"),  # base
        },
        fields={
            "motor_brand": OverlayField(key="motor_brand", functional_group="motor"),  # tenant
        },
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("personal.city").functional_group == "administrative"
    assert cfg.field("overlay.motor_brand").functional_group == "motor"


def test_tenant_may_reauthor_a_base_group_key_and_it_resolves():
    # R5.3 (tenant key wins on collision): a tenant may author a group whose key equals a BASE
    # key (`administrative`) — the reference still resolves (the key is in BASE ⊕ tenant), and
    # the tenant's authored entry is surfaced in the served functional_groups catalog.
    overlay = TenantOverlay(
        functional_groups={
            "administrative": FunctionalGroup(
                key="administrative", label={"en": "Admin (tenant)"}, order=99
            ),
        },
        overrides={"personal.city": FixedFieldOverride(functional_group="administrative")},
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("personal.city").functional_group == "administrative"
    served = {g.key: g for g in cfg.functional_groups}
    assert served["administrative"].label == {"en": "Admin (tenant)"}


# ── options (rich enum {value,label,roles?}) surface on resolved fields (R4.11/R4.12) ──


def test_base_status_options_surface_on_the_resolved_field():
    cfg = _resolver().resolve("t")
    status = cfg.field("membership.status")
    assert status.options is not None
    values = tuple(o.value for o in status.options)
    assert set(values) == set(status.choices)  # options and bare choices stay coherent


def test_overlay_can_supply_role_gated_options_on_a_fixed_enum():
    # gender is a Fixed OPEN enum; the tenant supplies its value list via an override's options.
    overlay = TenantOverlay(
        overrides={
            "personal.gender": FixedFieldOverride(
                options=(
                    EnumOption(value="m", label={"nl": "Man"}),
                    EnumOption(value="v", label={"nl": "Vrouw"}),
                    EnumOption(value="x", label={"nl": "Overig"}, roles=("Members_CRUD",)),
                )
            )
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    gender = cfg.field("personal.gender")
    assert tuple(o.value for o in gender.options) == ("m", "v", "x")
    # choices stay coherent with the supplied options.
    assert tuple(gender.choices) == ("m", "v", "x")
    # The role gate survives onto the resolved option.
    gated = [o for o in gender.options if o.roles]
    assert gated and gated[0].value == "x" and "Members_CRUD" in gated[0].roles


def test_variable_enum_field_options_surface():
    overlay = TenantOverlay(
        fields={
            "payment_method": OverlayField(
                key="payment_method",
                type=FieldType.ENUM,
                options=(
                    EnumOption(value="ideal", label={"nl": "iDEAL"}),
                    EnumOption(value="cash", label={"nl": "Contant"}),
                ),
            )
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    pm = cfg.field("overlay.payment_method")
    assert tuple(o.value for o in pm.options) == ("ideal", "cash")
    assert tuple(pm.choices) == ("ideal", "cash")


# ── show_when surfaces on resolved fields (R4.12) ─────────────────────────────────────


def test_show_when_surfaces_on_a_variable_field():
    cond = {"field": "membership.membership_type", "in": ["motor"]}
    overlay = TenantOverlay(
        fields={"license_plate": OverlayField(key="license_plate", show_when=cond)}
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    lp = cfg.field("overlay.license_plate")
    assert lp.show_when == cond


def test_show_when_can_be_added_to_a_fixed_field_via_override():
    cond = {"field": "personal.gender", "in": ["x"]}
    overlay = TenantOverlay(
        overrides={"personal.name_infix": FixedFieldOverride(show_when=cond)}
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("personal.name_infix").show_when == cond


# ── member_number_format surfaces on the member_number field (R4.2/R4.8) ───────────────


def test_member_number_format_surfaces_via_override():
    fmt = MemberNumberFormat(prefix="Nr-", width=4)
    overlay = TenantOverlay(
        overrides={"membership.member_number": FixedFieldOverride(member_number_format=fmt)}
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    mn = cfg.field("membership.member_number")
    assert mn.member_number_format == fmt
    assert mn.member_number_format.matches("Nr-0001")
    assert not mn.member_number_format.matches("X-1")


def test_member_number_has_no_format_by_default():
    cfg = _resolver().resolve("t")
    assert cfg.field("membership.member_number").member_number_format is None


# ── scope surfaces on resolved fields (remediation R3.5) ──────────────────────────────
#
# Previously DEAD on read: `scope` was never carried onto `ResolvedField` and never serialized
# (defect I-6). The resolver now CARRIES the overlay/override scope onto the resolved field so the
# authoring UI can read the current scope state back. Scope RESOLUTION (`handler/app.py` →
# `allowed_scopes`) is untouched — see test_scope_access.py (P3).


def test_scope_surfaces_on_a_fixed_field_via_override():
    # A tenant marks a fixed enum field (e.g. `gender`) as a scope axis via an override's scope.
    scope = FieldScope(enabled=True, required_for=("Members_CRUD",))
    overlay = TenantOverlay(
        overrides={"personal.gender": FixedFieldOverride(scope=scope)}
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    gender = cfg.field("personal.gender")
    assert gender.scope is scope
    assert gender.scope.enabled is True
    assert tuple(gender.scope.required_for) == ("Members_CRUD",)


def test_scope_surfaces_on_a_variable_field():
    scope = FieldScope(enabled=True, required_for=("Members_CRUD",))
    overlay = TenantOverlay(
        fields={
            "team": OverlayField(
                key="team",
                type=FieldType.ENUM,
                options=(
                    EnumOption(value="a", label={"nl": "A"}),
                    EnumOption(value="b", label={"nl": "B"}),
                ),
                scope=scope,
            )
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    team = cfg.field("overlay.team")
    assert team.scope is scope
    assert team.scope.enabled is True
    assert tuple(team.scope.required_for) == ("Members_CRUD",)


def test_field_has_no_scope_by_default():
    # A field that is not a scope axis carries no scope attribute (stays `None`).
    cfg = _resolver().resolve("t")
    assert cfg.field("personal.gender").scope is None
    assert cfg.field("membership.status").scope is None


# ── public member-application attributes CARRIED onto the resolved field (D20; application-app
#    task 2.2/3.6/4.1). Before this fix `_apply_override` / `_as_variable_field` DROPPED the four
#    sibling attrs, so a tenant that put a field on the public form never saw them downstream.
#    R4.2/R4a/R4b/R7.1.


def test_application_attrs_default_off_on_a_plain_fixed_field():
    # A fixed field with no override is OFF the public form, full choices, optional, no validator.
    cfg = _resolver().resolve("t")
    email = cfg.field("personal.email")
    assert email.application_visible is False
    assert email.application_required is False
    assert email.application_choices is None
    assert email.format is None


def test_application_attrs_carry_from_a_fixed_field_override():
    # A tenant puts a FIXED field on the public form via an override (D20: attrs ride on
    # fixed-field overrides too — e.g. membership_type onto the form).
    from sam.members.domain.field_resolver import FieldFormat

    overlay = TenantOverlay(
        overrides={
            "personal.email": FixedFieldOverride(
                application_visible=True,
                application_required=True,
                format=FieldFormat(checker="EMAIL"),
            ),
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    email = cfg.field("personal.email")
    assert email.application_visible is True
    assert email.application_required is True
    assert email.format == FieldFormat(checker="EMAIL")


def test_application_override_leaves_base_values_when_untouched():
    # An override that does NOT set the application attrs (None sentinels) leaves the base as-is —
    # consistent with how `required`/`visible` behave (None = "leave the base value").
    overlay = TenantOverlay(
        overrides={"personal.email": FixedFieldOverride(label={"en": "Your email"})}
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    email = cfg.field("personal.email")
    assert email.label == {"en": "Your email"}
    assert email.application_visible is False  # untouched → base default
    assert email.format is None


def test_application_choices_subset_carries_from_a_fixed_override():
    # The enum application SUBSET (R4a) survives the resolve onto the resolved field.
    overlay = TenantOverlay(
        overrides={
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                application_choices=("gewoon",),
            )
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    mt = cfg.field("membership.membership_type")
    assert mt.application_visible is True
    assert mt.application_choices == ("gewoon",)


def test_application_attrs_carry_from_a_variable_field():
    # A tenant-added overlay field selected onto the public form carries its attrs 1:1.
    from sam.members.domain.field_resolver import FieldFormat

    overlay = TenantOverlay(
        fields={
            "iban": OverlayField(
                key="iban",
                type=FieldType.STRING,
                label={"nl": "IBAN"},
                application_visible=True,
                application_required=True,
                format=FieldFormat(checker="IBAN"),
            )
        }
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    iban = cfg.field("overlay.iban")
    assert iban.application_visible is True
    assert iban.application_required is True
    assert iban.format == FieldFormat(checker="IBAN")


def test_application_attrs_default_off_on_a_plain_variable_field():
    # A variable field a tenant did NOT select onto the form stays off it (back-compatible).
    overlay = TenantOverlay(
        fields={"club_note": OverlayField(key="club_note", label={"nl": "Notitie"})}
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    note = cfg.field("overlay.club_note")
    assert note.application_visible is False
    assert note.application_required is False
    assert note.application_choices is None
    assert note.format is None


# ══════════════════════════════════════════════════════════════════════════════════════
# Phase 1 — Catalog Backbone, Task 4.2 — resolve() regression lock (byte-for-byte stable)
#
# Task 4.1 extended `FieldResolver._reject_invalid_overlay` to validate a field's
# `functional_group` against `BASE_FUNCTIONAL_GROUPS` ⊕ the tenant's authored catalog. R2.1/R2.4
# require that change to be purely preservation-safe for inputs that already resolved: for every
# existing fixture the resolve() OUTPUT is byte-for-byte identical to before — the change only
# ADDS validity (a base-key reference with no authored catalog) and a stricter rejection of
# dangling NON-base keys, never alters a successful resolve's output.
#
# These tests lock a stable structural projection of resolve() for the two representative
# existing fixtures — the empty / no-overlay case (`h-dcn`) and the committed seed overlay
# (`seed_overlay.build_seed_overlay()`, which exercises variable fields + address fixed-overrides
# into the `address` display group). The projection is the full ordered tuple of every observable
# resolved attribute, so ANY future change that alters the resolved output (a field added/removed,
# a reorder, a relabel, an origin/type/required/read_only/functional_group flip) breaks the lock.
#
# Validates: Requirements R2.1, R2.4
# ══════════════════════════════════════════════════════════════════════════════════════

from sam.members.domain.seed_overlay import build_seed_overlay


def _resolve_projection(cfg: FieldConfig):
    """A stable, byte-for-byte structural projection of a resolved config's ordered fields.

    One tuple per resolved field, in `cfg.fields` order (the resolver's deterministic
    `(group, order, key)` sort), capturing every observable attribute the frontend renders:
    `(dotted_key, origin, type, required, read_only, functional_group, order, sorted-label)`.
    Equality against a committed expected list is the "identical FieldConfig" check (R2.1).
    """
    return [
        (
            f.dotted_key(),
            f.origin.value,
            f.type.value,
            f.required,
            f.read_only,
            f.functional_group,
            f.order,
            tuple(sorted(f.label.items())),
        )
        for f in cfg.fields
    ]


# The resolve() output locked at Phase-1 task 4.1 (the base-group-aware reference validation),
# which that change preserves exactly for passing inputs. Any drift here is a behavior change.
_EMPTY_OVERLAY_PROJECTION = [
    ('membership.member_number', 'fixed', 'string', False, False, 'membership', 10, (('en', 'Member number'), ('nl', 'Lidnummer'))),
    ('membership.status', 'fixed', 'enum', True, False, 'membership', 20, (('en', 'Status'), ('nl', 'Status'))),
    ('membership.membership_type', 'fixed', 'reference', True, False, 'membership', 30, (('en', 'Membership type'), ('nl', 'Lidmaatschapstype'))),
    ('membership.joined_date', 'fixed', 'date', True, False, 'membership', 40, (('en', 'Joined date'), ('nl', 'Ingangsdatum'))),
    ('membership.years_member', 'calculated', 'string', False, True, 'membership', 45, (('en', 'Years member'), ('nl', 'Jaren lid'))),
    ('membership.created_at', 'fixed', 'string', False, False, 'administrative', 90, (('en', 'Created at'), ('nl', 'Aangemaakt op'))),
    ('membership.application_year', 'calculated', 'string', False, True, 'membership', 95, (('en', 'Application year'), ('nl', 'Aanmeldingsjaar'))),
    ('membership.updated_at', 'fixed', 'string', False, False, 'administrative', 100, (('en', 'Updated at'), ('nl', 'Bijgewerkt op'))),
    ('personal.display_name', 'calculated', 'string', False, True, 'personal', 5, (('en', 'Display name'), ('nl', 'Korte naam'))),
    ('personal.first_name', 'fixed', 'string', False, False, 'personal', 10, (('en', 'First name'), ('nl', 'Voornaam'))),
    ('personal.last_name', 'fixed', 'string', True, False, 'personal', 20, (('en', 'Last name'), ('nl', 'Achternaam'))),
    ('personal.name_infix', 'fixed', 'string', False, False, 'personal', 30, (('en', 'Name infix'), ('nl', 'Tussenvoegsel'))),
    ('personal.initials', 'fixed', 'string', False, False, 'personal', 40, (('en', 'Initials'), ('nl', 'Initialen'))),
    ('personal.birth_date', 'fixed', 'date', False, False, 'personal', 50, (('en', 'Date of birth'), ('nl', 'Geboortedatum'))),
    ('personal.age', 'calculated', 'string', False, True, 'personal', 55, (('en', 'Age'), ('nl', 'Leeftijd'))),
    ('personal.birthday', 'calculated', 'string', False, True, 'personal', 56, (('en', 'Birthday'), ('nl', 'Verjaardag'))),
    ('personal.birth_day', 'calculated', 'string', False, True, 'personal', 57, (('en', 'Birth day'), ('nl', 'Geboortedag'))),
    ('personal.birth_month', 'calculated', 'string', False, True, 'personal', 58, (('en', 'Birth month'), ('nl', 'Geboortemaand'))),
    ('personal.birth_year', 'calculated', 'string', False, True, 'personal', 59, (('en', 'Birth year'), ('nl', 'Geboortejaar'))),
    ('personal.birth_quarter', 'calculated', 'string', False, True, 'personal', 60, (('en', 'Birth quarter'), ('nl', 'Geboortekwartaal'))),
    ('personal.gender', 'fixed', 'enum', False, False, 'personal', 60, (('en', 'Gender'), ('nl', 'Geslacht'))),
    ('personal.email', 'fixed', 'string', False, False, 'personal', 70, (('en', 'Email'), ('nl', 'E-mail'))),
    ('personal.phone', 'fixed', 'string', False, False, 'personal', 80, (('en', 'Phone'), ('nl', 'Telefoon'))),
    ('personal.street', 'fixed', 'string', False, False, 'personal', 90, (('en', 'Street'), ('nl', 'Straat'))),
    ('personal.postal_code', 'fixed', 'string', False, False, 'personal', 100, (('en', 'Postal code'), ('nl', 'Postcode'))),
    ('personal.city', 'fixed', 'string', False, False, 'personal', 110, (('en', 'City'), ('nl', 'Woonplaats'))),
    ('personal.country', 'fixed', 'string', False, False, 'personal', 120, (('en', 'Country'), ('nl', 'Land'))),
]

# The committed seed overlay (`seed_overlay.build_seed_overlay()`): the address fixed fields move
# into the `address` DISPLAY group (storage stays `personal`), and two placeholder VARIABLE fields
# (field_a string, field_b enum) land under `group_a`. The fixed/calculated base is otherwise
# identical to the empty-overlay projection above.
_SEED_OVERLAY_PROJECTION = [
    ('membership.member_number', 'fixed', 'string', False, False, 'membership', 10, (('en', 'Member number'), ('nl', 'Lidnummer'))),
    ('membership.status', 'fixed', 'enum', True, False, 'membership', 20, (('en', 'Status'), ('nl', 'Status'))),
    ('membership.membership_type', 'fixed', 'reference', True, False, 'membership', 30, (('en', 'Membership type'), ('nl', 'Lidmaatschapstype'))),
    ('membership.joined_date', 'fixed', 'date', True, False, 'membership', 40, (('en', 'Joined date'), ('nl', 'Ingangsdatum'))),
    ('membership.years_member', 'calculated', 'string', False, True, 'membership', 45, (('en', 'Years member'), ('nl', 'Jaren lid'))),
    ('membership.created_at', 'fixed', 'string', False, False, 'administrative', 90, (('en', 'Created at'), ('nl', 'Aangemaakt op'))),
    ('membership.application_year', 'calculated', 'string', False, True, 'membership', 95, (('en', 'Application year'), ('nl', 'Aanmeldingsjaar'))),
    ('membership.updated_at', 'fixed', 'string', False, False, 'administrative', 100, (('en', 'Updated at'), ('nl', 'Bijgewerkt op'))),
    ('overlay.field_a', 'variable', 'string', False, False, 'group_a', 10, (('en', 'Field A'), ('nl', 'Veld A'))),
    ('overlay.field_b', 'variable', 'enum', False, False, 'group_a', 20, (('en', 'Field B'), ('nl', 'Veld B'))),
    ('personal.display_name', 'calculated', 'string', False, True, 'personal', 5, (('en', 'Display name'), ('nl', 'Korte naam'))),
    ('personal.first_name', 'fixed', 'string', False, False, 'personal', 10, (('en', 'First name'), ('nl', 'Voornaam'))),
    ('personal.last_name', 'fixed', 'string', True, False, 'personal', 20, (('en', 'Last name'), ('nl', 'Achternaam'))),
    ('personal.name_infix', 'fixed', 'string', False, False, 'personal', 30, (('en', 'Name infix'), ('nl', 'Tussenvoegsel'))),
    ('personal.initials', 'fixed', 'string', False, False, 'personal', 40, (('en', 'Initials'), ('nl', 'Initialen'))),
    ('personal.birth_date', 'fixed', 'date', False, False, 'personal', 50, (('en', 'Date of birth'), ('nl', 'Geboortedatum'))),
    ('personal.age', 'calculated', 'string', False, True, 'personal', 55, (('en', 'Age'), ('nl', 'Leeftijd'))),
    ('personal.birthday', 'calculated', 'string', False, True, 'personal', 56, (('en', 'Birthday'), ('nl', 'Verjaardag'))),
    ('personal.birth_day', 'calculated', 'string', False, True, 'personal', 57, (('en', 'Birth day'), ('nl', 'Geboortedag'))),
    ('personal.birth_month', 'calculated', 'string', False, True, 'personal', 58, (('en', 'Birth month'), ('nl', 'Geboortemaand'))),
    ('personal.birth_year', 'calculated', 'string', False, True, 'personal', 59, (('en', 'Birth year'), ('nl', 'Geboortejaar'))),
    ('personal.birth_quarter', 'calculated', 'string', False, True, 'personal', 60, (('en', 'Birth quarter'), ('nl', 'Geboortekwartaal'))),
    ('personal.gender', 'fixed', 'enum', False, False, 'personal', 60, (('en', 'Gender'), ('nl', 'Geslacht'))),
    ('personal.email', 'fixed', 'string', False, False, 'personal', 70, (('en', 'Email'), ('nl', 'E-mail'))),
    ('personal.phone', 'fixed', 'string', False, False, 'personal', 80, (('en', 'Phone'), ('nl', 'Telefoon'))),
    ('personal.street', 'fixed', 'string', False, False, 'address', 90, (('en', 'Street'), ('nl', 'Straat'))),
    ('personal.postal_code', 'fixed', 'string', False, False, 'address', 100, (('en', 'Postal code'), ('nl', 'Postcode'))),
    ('personal.city', 'fixed', 'string', False, False, 'address', 110, (('en', 'City'), ('nl', 'Woonplaats'))),
    ('personal.country', 'fixed', 'string', False, False, 'address', 120, (('en', 'Country'), ('nl', 'Land'))),
]

# The seed overlay's resolved functional-group catalog: BASE_FUNCTIONAL_GROUPS (personal/address/
# membership/administrative) ⊕ the seed-only `group_a`, ordered by (order, key).
_SEED_FUNCTIONAL_GROUPS_PROJECTION = [
    ('personal', 1, (('en', 'Personal'), ('nl', 'Persoonlijk'))),
    ('address', 2, (('en', 'Address'), ('nl', 'Adres'))),
    ('membership', 3, (('en', 'Membership'), ('nl', 'Lidmaatschap'))),
    ('administrative', 4, (('en', 'Administrative'), ('nl', 'Administratie'))),
    ('group_a', 5, (('en', 'Group A'), ('nl', 'Groep A'))),
]


def test_resolve_empty_overlay_output_is_byte_for_byte_identical_to_locked_baseline():
    # R2.1/R2.4: the no-overlay resolve (fixed base ⊕ calculated fields) is unchanged by task 4.1.
    cfg = _resolver().resolve("h-dcn")
    assert _resolve_projection(cfg) == _EMPTY_OVERLAY_PROJECTION


def test_resolve_seed_overlay_output_is_byte_for_byte_identical_to_locked_baseline():
    # R2.1/R2.4: the committed seed overlay — which exercises variable fields AND address
    # fixed-overrides into the `address` display group (a passing input before task 4.1) —
    # resolves to the identical FieldConfig after the base-group-aware validation change.
    cfg = _resolver({"t": build_seed_overlay()}).resolve("t")
    assert _resolve_projection(cfg) == _SEED_OVERLAY_PROJECTION


def test_resolve_seed_overlay_functional_group_catalog_is_identical_to_locked_baseline():
    # R2.1: the served functional_groups catalog (base ⊕ seed-only group_a) is unchanged.
    cfg = _resolver({"t": build_seed_overlay()}).resolve("t")
    served = [
        (g.key, g.order, tuple(sorted(g.label.items()))) for g in cfg.functional_groups
    ]
    assert served == _SEED_FUNCTIONAL_GROUPS_PROJECTION


# ══════════════════════════════════════════════════════════════════════════════════════
# Phase 1 — Catalog Backbone, Task 4.4 — the group merge RULE: resolved group set = BASE ⊕ tenant
#
# R5.3 states the merge rule the resolver's reference validation implements (design §4): the
# effective functional-group set a field's `functional_group` resolves against is
# `BASE_FUNCTIONAL_GROUPS` ⊕ the tenant's authored `functional_groups`, where
#   (a) the resolved set == base keys ∪ tenant keys (merge by key),
#   (b) on a key COLLISION the tenant's authored FunctionalGroup WINS (its label/order override
#       the base) — surfaced in the served catalog,
#   (c) base keys FILL THE REST — every base key stays a valid reference target even when the
#       tenant authored other (or colliding) groups, and
#   (d) a base group is ALWAYS present — all four base keys resolve even with NO authored catalog.
#
# These complement, and deliberately do NOT duplicate:
#   - `test_group_set_is_base_merged_with_tenant_catalog` (one base key + one tenant key resolve),
#   - `test_tenant_may_reauthor_a_base_group_key_and_it_resolves` (a single-key collision),
#   - `test_base_key_reference_resolves_with_no_authored_catalog` (a single base key, override path).
# They assert the rule HOLISTICALLY: the whole base set at once, and that a collision on one base
# key does not displace the OTHER base keys (base keys still fill the rest).
#
# Observability note: the resolver surfaces the merge via its reference VALIDATION group set
# (`_reject_invalid_overlay`) — a reference to a key in BASE ⊕ tenant resolves, one outside it
# raises `OverlayError` — and via the SERVED `functional_groups` catalog carrying the tenant's
# authored entry on a collision. The resolver does NOT inject un-authored base groups into the
# served `functional_groups` tuple (design §7 / D5: the served shape is unchanged in Phase 1);
# the merge rule is a VALIDATION/resolution contract, not a serve-shape change.
#
# Validates: Requirements R5.3

from sam.members.domain.attribute_catalog import BASE_FUNCTIONAL_GROUPS

_BASE_GROUP_KEYS = tuple(g.key for g in BASE_FUNCTIONAL_GROUPS)


def test_every_base_group_is_always_present_with_no_authored_catalog():
    # R5.3 (d) + "a base group is always present": with NO authored catalog, a field may
    # reference ANY of the four base keys and resolve — the full base set fills the group set,
    # not just the one base key the single-key tests exercise.
    overlay = TenantOverlay(
        overrides={
            dotted: FixedFieldOverride(functional_group=base_key)
            for dotted, base_key in zip(
                ("personal.first_name", "personal.city", "membership.member_number", "membership.created_at"),
                _BASE_GROUP_KEYS,
            )
        },
    )
    assert not overlay.functional_groups  # no authored catalog — base set alone fills the rest
    cfg = _resolver({"t": overlay}).resolve("t")
    for dotted, base_key in zip(
        ("personal.first_name", "personal.city", "membership.member_number", "membership.created_at"),
        _BASE_GROUP_KEYS,
    ):
        assert cfg.field(dotted).functional_group == base_key


def test_tenant_collision_wins_without_displacing_the_other_base_keys():
    # R5.3 (b) tenant wins on collision + (c) base keys fill the rest, asserted TOGETHER: a tenant
    # re-authors ONE base key (`administrative`) and adds its own custom key (`motor`). In the same
    # overlay, references to (i) the re-authored key, (ii) a DIFFERENT, non-collided base key
    # (`membership`), and (iii) the tenant's custom key all resolve — the collision on one base key
    # does not knock the OTHER base keys out of the merged set.
    overlay = TenantOverlay(
        functional_groups={
            "administrative": FunctionalGroup(
                key="administrative", label={"en": "Ops (tenant)"}, order=42
            ),
            "motor": FunctionalGroup(key="motor", label={"en": "Motor"}, order=9),
        },
        overrides={
            "membership.created_at": FixedFieldOverride(functional_group="administrative"),  # collided base key
            "personal.city": FixedFieldOverride(functional_group="membership"),              # other base key, still valid
        },
        fields={
            "motor_brand": OverlayField(key="motor_brand", functional_group="motor"),         # tenant-only key
        },
    )
    cfg = _resolver({"t": overlay}).resolve("t")
    # (b) tenant wins on collision — the reference resolves AND the served catalog carries the
    #     tenant's authored label/order for the collided base key (not the base `Administrative`/4).
    assert cfg.field("membership.created_at").functional_group == "administrative"
    served = {g.key: g for g in cfg.functional_groups}
    assert served["administrative"].label == {"en": "Ops (tenant)"}
    assert served["administrative"].order == 42
    # (c) base keys fill the rest — a DIFFERENT base key the tenant did NOT author still resolves.
    assert cfg.field("personal.city").functional_group == "membership"
    # tenant key extends the set too.
    assert cfg.field("overlay.motor_brand").functional_group == "motor"


def test_merge_rule_resolved_set_is_exactly_base_union_tenant_keys():
    # R5.3 (a): the resolved group set is EXACTLY base keys ∪ tenant keys — a reference to any key
    # in that union resolves, and a reference to a key OUTSIDE it (neither base nor authored) is a
    # dangling reference and raises. One overlay exercises both sides of the membership test.
    tenant_only_key = "motor"
    overlay_valid = TenantOverlay(
        functional_groups={tenant_only_key: FunctionalGroup(key=tenant_only_key, order=9)},
    )
    cfg = _resolver(
        {
            "t": TenantOverlay(
                functional_groups=overlay_valid.functional_groups,
                overrides={
                    "personal.city": FixedFieldOverride(functional_group="personal"),   # ∈ base
                    "membership.created_at": FixedFieldOverride(functional_group=tenant_only_key),  # ∈ tenant
                },
            )
        }
    ).resolve("t")
    assert cfg.field("personal.city").functional_group == "personal"
    assert cfg.field("membership.created_at").functional_group == tenant_only_key

    # A key in NEITHER base NOR the tenant catalog is outside the merged set → rejected.
    outside = "neither_base_nor_tenant"
    assert outside not in _BASE_GROUP_KEYS
    overlay_bad = TenantOverlay(
        functional_groups={tenant_only_key: FunctionalGroup(key=tenant_only_key, order=9)},
        overrides={"personal.city": FixedFieldOverride(functional_group=outside)},
    )
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay_bad}).resolve("t")
    assert "personal.city" in exc.value.reasons
