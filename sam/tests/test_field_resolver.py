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
from sam.members.domain.calculated_fields import CALCULATED_FIELDS
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

    birthdate = cfg.field("personal.birth_date")
    assert birthdate is not None and birthdate.visible is False
    # A hidden fixed field is still present in the config, just excluded from visible_fields().
    assert birthdate not in cfg.visible_fields()
    assert birthdate in cfg.fields


def test_override_can_tighten_optional_fixed_field_to_required():
    # 'personal.street' is optional in the base; a tenant may require it.
    overlay = TenantOverlay(overrides={"personal.street": FixedFieldOverride(required=True)})
    cfg = _resolver({"t": overlay}).resolve("t")
    assert cfg.field("personal.street").required is True


# ── Overlay may NEVER weaken a platform invariant ─────────────────────────────────────


def test_overlay_cannot_loosen_a_platform_required_field():
    # 'personal.first_name' is platform-required; an overlay must not make it optional.
    overlay = TenantOverlay(overrides={"personal.first_name": FixedFieldOverride(required=False)})
    with pytest.raises(OverlayError) as exc:
        _resolver({"t": overlay}).resolve("t")
    assert "personal.first_name" in exc.value.reasons


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

from sam.members.domain.fixed_fields import (  # noqa: E402
    EnumOption,
    MemberNumberFormat,
)
from sam.members.domain.field_resolver import FunctionalGroup  # noqa: E402


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


def test_dangling_functional_group_reference_is_rejected():
    # A functional_group not present in a non-empty catalog is rejected fail-fast (Property 7).
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
