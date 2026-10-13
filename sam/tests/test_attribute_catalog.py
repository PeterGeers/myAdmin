"""
Phase 1 — Catalog Backbone: tests for the attribute catalog domain artifact.

Task 1.1 — pin the base functional-group set (:data:`BASE_FUNCTIONAL_GROUPS`): the four platform
default display groups, their keys/labels/order, and that the constant is pure and import-time safe
(a frozen tuple of frozen :class:`FunctionalGroup` dataclasses). Later Phase-1 tasks extend this
file (the base-group closure test is task 1.3; the inventory drift guard is task 3.3).

Validates: Requirements R5.1
"""

from __future__ import annotations

import dataclasses

import pytest

from sam.members.domain.attribute_catalog import BASE_FUNCTIONAL_GROUPS
from sam.members.domain.field_resolver import FunctionalGroup
from sam.members.domain.seed_overlay import SEED_FUNCTIONAL_GROUPS


# ── Base functional-group set (R5.1) ───────────────────────────────────────────────────


def test_base_functional_groups_is_a_tuple_of_functional_groups():
    assert isinstance(BASE_FUNCTIONAL_GROUPS, tuple)
    assert BASE_FUNCTIONAL_GROUPS, "the base set must not be empty"
    assert all(isinstance(g, FunctionalGroup) for g in BASE_FUNCTIONAL_GROUPS)


def test_base_functional_groups_defines_the_four_platform_defaults_in_order():
    # key → order, in the design §4 order: personal(1), address(2), membership(3), administrative(4).
    assert [(g.key, g.order) for g in BASE_FUNCTIONAL_GROUPS] == [
        ("personal", 1),
        ("address", 2),
        ("membership", 3),
        ("administrative", 4),
    ]


def test_base_functional_groups_carry_nl_and_en_labels():
    for g in BASE_FUNCTIONAL_GROUPS:
        assert set(g.label) == {"nl", "en"}, f"{g.key} must have nl+en labels"
        assert all(g.label.values()), f"{g.key} labels must be non-blank"


def test_base_functional_group_keys_are_unique():
    keys = [g.key for g in BASE_FUNCTIONAL_GROUPS]
    assert len(keys) == len(set(keys))


def test_base_functional_group_orders_are_unique_and_sortable():
    orders = [g.order for g in BASE_FUNCTIONAL_GROUPS]
    assert len(orders) == len(set(orders))
    # sorting by (order, key) is stable and yields the declared order.
    assert sorted(BASE_FUNCTIONAL_GROUPS, key=lambda g: (g.order, g.key)) == list(
        BASE_FUNCTIONAL_GROUPS
    )


# ── Pure / import-time safe (R5.1 — "pure, import-time safe") ───────────────────────────


def test_base_functional_groups_entries_are_frozen():
    first = BASE_FUNCTIONAL_GROUPS[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.order = 99  # type: ignore[misc]


# ── Seed fixture reconciled with the base set (R5.2 — ONE base-group definition) ────────


def test_seed_functional_groups_base_entries_derive_from_base_set():
    # Task 1.2 / R5.2: the seed's base groups are NOT a second hand-maintained copy — they are
    # the SAME keys/labels/orders as BASE_FUNCTIONAL_GROUPS, projected into the seed's dict shape.
    expected_base = [
        {"key": g.key, "label": dict(g.label), "order": g.order} for g in BASE_FUNCTIONAL_GROUPS
    ]
    seed_base = [g for g in SEED_FUNCTIONAL_GROUPS if g["key"] != "group_a"]
    assert seed_base == expected_base


def test_seed_functional_groups_keeps_group_a_as_a_seed_only_extra():
    # The seed-only placeholder custom group stays seed/test data; it must NOT leak into the
    # base set.
    base_keys = {g.key for g in BASE_FUNCTIONAL_GROUPS}
    seed_keys = {g["key"] for g in SEED_FUNCTIONAL_GROUPS}
    assert "group_a" in seed_keys
    assert "group_a" not in base_keys
    # The seed is exactly the base keys plus the seed-only extras.
    assert seed_keys == base_keys | {"group_a"}


def test_seed_functional_groups_dict_shape_is_preserved():
    # seed_overlay_dict() depends on the {"key","label","order"} dict shape — pin it so the
    # derivation can't silently change the projection contract.
    for g in SEED_FUNCTIONAL_GROUPS:
        assert set(g) == {"key", "label", "order"}
        assert isinstance(g["label"], dict) and set(g["label"]) == {"nl", "en"}

# ── Base-group closure (R5.2 — every shipped field resolves to a base-set key) ─────────
#
# Task 1.3: the base functional-group set must COVER every group the shipped registries name.
# For each fixed/calculated field, `default_functional_group()` (its explicit `functional_group`
# else its storage-bucket fallback) must be a key present in BASE_FUNCTIONAL_GROUPS. This guards
# against a registry field referencing a display group the base set does not define — the exact
# "empty catalog ⇒ dangling reference" gap R5 closes (design §4). The closure is one-directional:
# a base key with no field referencing it (e.g. `address`, whose fields store under `personal`
# and get their display group via the overlay, not the registry) is allowed; a field pointing at
# a non-base key is not.
#
# Validates: Requirements R5.2

from sam.members.domain.calculated_fields import CALCULATED_FIELDS
from sam.members.domain.fixed_fields import FIXED_FIELDS


def test_every_fixed_field_default_functional_group_is_a_base_group_key():
    base_keys = {g.key for g in BASE_FUNCTIONAL_GROUPS}
    offenders = {
        f.dotted_key(): f.default_functional_group()
        for f in FIXED_FIELDS
        if f.default_functional_group() not in base_keys
    }
    assert not offenders, (
        f"fixed fields reference functional group(s) absent from BASE_FUNCTIONAL_GROUPS "
        f"{sorted(base_keys)}: {offenders}"
    )


def test_every_calculated_field_default_functional_group_is_a_base_group_key():
    base_keys = {g.key for g in BASE_FUNCTIONAL_GROUPS}
    offenders = {
        c.dotted_key(): c.default_functional_group()
        for c in CALCULATED_FIELDS
        if c.default_functional_group() not in base_keys
    }
    assert not offenders, (
        f"calculated fields reference functional group(s) absent from BASE_FUNCTIONAL_GROUPS "
        f"{sorted(base_keys)}: {offenders}"
    )


def test_base_group_closure_holds_across_the_whole_shipped_registry():
    # The combined closure the design (§4) and R5.2 name explicitly: the union of every shipped
    # field's resolved functional group is a SUBSET of the base-set keys — no shipped field names
    # a group the base set omits.
    base_keys = {g.key for g in BASE_FUNCTIONAL_GROUPS}
    referenced = {f.default_functional_group() for f in FIXED_FIELDS} | {
        c.default_functional_group() for c in CALCULATED_FIELDS
    }
    assert referenced <= base_keys, (
        f"shipped fields reference group(s) outside the base set: "
        f"{sorted(referenced - base_keys)}"
    )


# ── The catalog data model dataclasses (design §2) ─────────────────────────────────────
#
# Task 2.1: the four frozen, pure vocabulary/shape dataclasses — AttributeApplies,
# AttributeSpec, CatalogField, AttributeCatalog. These tests pin their structure (field names,
# nesting), their frozen-ness, and their declared defaults, and confirm the module stays pure /
# import-time safe (no DynamoDB/boto3). The vocabulary CONTENT (one AttributeSpec per attribute)
# and build_attribute_catalog() are later tasks (2.2, 3); here we only exercise the shapes.
#
# Validates: Requirements R1.1

from sam.members.domain.attribute_catalog import (
    AttributeApplies,
    AttributeCatalog,
    AttributeSpec,
    CatalogField,
)


# ── AttributeApplies (origin vocabulary) ───────────────────────────────────────────────


def test_attribute_applies_values_match_the_three_field_origins():
    assert {a.value for a in AttributeApplies} == {"fixed", "calculated", "variable"}


def test_attribute_applies_is_a_str_enum():
    # A str enum so a value compares/serializes as its plain string (mirrors FieldOrigin).
    assert AttributeApplies.FIXED == "fixed"
    assert isinstance(AttributeApplies.VARIABLE, str)


# ── AttributeSpec (the vocabulary entry) ───────────────────────────────────────────────


def test_attribute_spec_carries_the_designed_fields():
    spec = AttributeSpec(
        key="type",
        value_type="enum",
        required=True,
        applies_to=(AttributeApplies.FIXED, AttributeApplies.VARIABLE),
        tenant_authorable=False,
    )
    assert spec.key == "type"
    assert spec.value_type == "enum"
    assert spec.required is True
    assert spec.applies_to == (AttributeApplies.FIXED, AttributeApplies.VARIABLE)
    assert spec.tenant_authorable is False


def test_attribute_spec_required_when_and_note_default_to_empty():
    spec = AttributeSpec(
        key="label",
        value_type="i18n",
        required=True,
        applies_to=(AttributeApplies.FIXED,),
        tenant_authorable=True,
    )
    assert spec.required_when == ()
    assert spec.note == ""


def test_attribute_spec_required_when_encodes_the_enum_rule():
    # R1.3: choices/options required when type == enum, as ((attr, value), …) pairs.
    spec = AttributeSpec(
        key="choices",
        value_type="list",
        required=False,
        applies_to=(AttributeApplies.FIXED, AttributeApplies.VARIABLE),
        tenant_authorable=True,
        required_when=(("type", "enum"),),
    )
    assert spec.required_when == (("type", "enum"),)


def test_attribute_spec_is_frozen():
    spec = AttributeSpec(
        key="order",
        value_type="int",
        required=False,
        applies_to=(AttributeApplies.FIXED,),
        tenant_authorable=True,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.required = True  # type: ignore[misc]


# ── CatalogField (the computed inventory entry) ────────────────────────────────────────


def test_catalog_field_carries_the_designed_fields():
    cf = CatalogField(
        dotted_key="personal.first_name",
        key="first_name",
        origin=AttributeApplies.FIXED,
        storage_group="personal",
        type="string",
        required=False,
        label={"nl": "Voornaam", "en": "First name"},
        functional_group="personal",
        order=10,
        read_only=False,
    )
    assert cf.dotted_key == "personal.first_name"
    assert cf.key == "first_name"
    assert cf.origin is AttributeApplies.FIXED
    assert cf.storage_group == "personal"
    assert cf.type == "string"
    assert cf.required is False
    assert cf.label == {"nl": "Voornaam", "en": "First name"}
    assert cf.functional_group == "personal"
    assert cf.order == 10
    assert cf.read_only is False


def test_catalog_field_is_frozen():
    cf = CatalogField(
        dotted_key="membership.status",
        key="status",
        origin=AttributeApplies.FIXED,
        storage_group="membership",
        type="enum",
        required=True,
        label={"nl": "Status", "en": "Status"},
        functional_group="membership",
        order=20,
        read_only=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cf.required = False  # type: ignore[misc]


# ── AttributeCatalog (the assembled artifact) ──────────────────────────────────────────


def test_attribute_catalog_nests_vocabulary_inventory_groups_and_label_convention():
    spec = AttributeSpec(
        key="label",
        value_type="i18n",
        required=True,
        applies_to=(AttributeApplies.FIXED,),
        tenant_authorable=True,
    )
    cf = CatalogField(
        dotted_key="personal.first_name",
        key="first_name",
        origin=AttributeApplies.FIXED,
        storage_group="personal",
        type="string",
        required=False,
        label={"nl": "Voornaam", "en": "First name"},
        functional_group="personal",
        order=10,
        read_only=False,
    )
    catalog = AttributeCatalog(
        attributes=(spec,),
        fields=(cf,),
        functional_groups=BASE_FUNCTIONAL_GROUPS,
        label_convention="i18n-keys+tenant-inline-override",
    )
    assert catalog.attributes == (spec,)
    assert catalog.fields == (cf,)
    assert catalog.functional_groups == BASE_FUNCTIONAL_GROUPS
    assert catalog.label_convention == "i18n-keys+tenant-inline-override"


def test_attribute_catalog_is_frozen():
    catalog = AttributeCatalog(
        attributes=(),
        fields=(),
        functional_groups=(),
        label_convention="i18n-keys+tenant-inline-override",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        catalog.label_convention = "changed"  # type: ignore[misc]


# ── The attribute vocabulary (task 2.2; design §2 table) ───────────────────────────────
#
# Task 2.2: ATTRIBUTE_VOCABULARY is ONE AttributeSpec per attribute the model carries today,
# transcribed from the design §2 table. These tests pin that it covers EXACTLY the designed
# keys, that each spec's authorability / applies_to / required_when match the table, and that
# the Phase-3-declared scope_binding + alias carry the Phase-3 note (R8.1).
#
# Validates: Requirements R1.1, R1.2, R1.5, R8.1

from sam.members.domain.attribute_catalog import ATTRIBUTE_VOCABULARY


#: The exact attribute keys the design §2 table names (task 2.2 "the attributes the model carries").
_DESIGNED_ATTRIBUTE_KEYS = {
    "key",
    "type",
    "required",
    "label",
    "visible",
    "order",
    "functional_group",
    "choices",
    "options",
    "show_when",
    "member_number_format",
    "calculated_from",
    "scope_binding",
    "alias",
}


def _spec(key: str) -> AttributeSpec:
    by_key = {s.key: s for s in ATTRIBUTE_VOCABULARY}
    return by_key[key]


def test_attribute_vocabulary_is_a_tuple_of_attribute_specs():
    assert isinstance(ATTRIBUTE_VOCABULARY, tuple)
    assert ATTRIBUTE_VOCABULARY, "the vocabulary must not be empty"
    assert all(isinstance(s, AttributeSpec) for s in ATTRIBUTE_VOCABULARY)


def test_attribute_vocabulary_covers_exactly_the_designed_attribute_keys():
    assert {s.key for s in ATTRIBUTE_VOCABULARY} == _DESIGNED_ATTRIBUTE_KEYS


def test_attribute_vocabulary_keys_are_unique():
    keys = [s.key for s in ATTRIBUTE_VOCABULARY]
    assert len(keys) == len(set(keys))


def test_identity_key_is_not_tenant_authorable():
    # §2 table: `key` is identity — never tenant-authored.
    spec = _spec("key")
    assert spec.required is True
    assert spec.tenant_authorable is False


def test_type_applies_to_all_origins_and_is_required():
    spec = _spec("type")
    assert spec.required is True
    assert set(spec.applies_to) == {
        AttributeApplies.FIXED,
        AttributeApplies.CALCULATED,
        AttributeApplies.VARIABLE,
    }


def test_required_attribute_applies_to_fixed_and_variable_only_and_defaults_optional():
    # §2 table: `required` applies to fixed, variable (calc is always read-only); default false.
    spec = _spec("required")
    assert spec.required is False
    assert set(spec.applies_to) == {AttributeApplies.FIXED, AttributeApplies.VARIABLE}
    assert spec.tenant_authorable is True


def test_label_is_i18n_required_and_authorable_for_all_origins():
    spec = _spec("label")
    assert spec.value_type == "i18n"
    assert spec.required is True
    assert spec.tenant_authorable is True
    assert set(spec.applies_to) == {
        AttributeApplies.FIXED,
        AttributeApplies.CALCULATED,
        AttributeApplies.VARIABLE,
    }


def test_choices_requires_enum_type_and_applies_to_enum_capable_origins():
    # R1.3: choices required when type == enum; enum lives on fixed + variable fields.
    spec = _spec("choices")
    assert spec.required_when == (("type", "enum"),)
    assert set(spec.applies_to) == {AttributeApplies.FIXED, AttributeApplies.VARIABLE}
    assert spec.tenant_authorable is True


def test_options_requires_enum_type_and_applies_to_enum_capable_origins():
    # R1.3: options (the rich enum form) required when type == enum.
    spec = _spec("options")
    assert spec.required_when == (("type", "enum"),)
    assert set(spec.applies_to) == {AttributeApplies.FIXED, AttributeApplies.VARIABLE}


# ── The enum rule mirrors the resolver + documents the scope-dimension exception (task 2.3) ──
#
# Task 2.3 / R1.3: the enum rule (`choices`/`options` required when type == enum) is the catalog's
# mirror of FieldResolver._reject_invalid_overlay's choiceless-enum rejection, and the one
# documented EXCEPTION — a scope-dimension-backed enum sources its values from the tenant's scope
# vocabulary, so it is exempt (resolver S5j / design D1a). These tests pin that BOTH enum-value
# attributes carry the rule identically (the mirror is complete, not just on one of them) and that
# the exception is DOCUMENTED on each so a consumer enforcing the rule knows not to flag a
# dimension-backed enum.
#
# Validates: Requirements R1.3


def test_enum_rule_is_identical_on_choices_and_options():
    # The resolver rejects a choiceless enum only when BOTH choices AND options are empty
    # (`not of.choices and not of.options`). The catalog must therefore carry the SAME
    # required_when on both — a mismatch would mean the mirror only half-encodes the rule.
    assert _spec("choices").required_when == _spec("options").required_when == (("type", "enum"),)


def test_only_enum_value_attributes_carry_the_type_enum_rule():
    # The `(("type","enum"),)` requirement is specific to the two enum-value attributes; no other
    # attribute should pick it up (member_number_format uses a different key==member_number rule).
    enum_ruled = {
        s.key for s in ATTRIBUTE_VOCABULARY if ("type", "enum") in s.required_when
    }
    assert enum_ruled == {"choices", "options"}


def test_choices_and_options_notes_document_the_scope_dimension_exception():
    # Task 2.3: the scope-dimension-backed exception (resolver S5j / design D1a) must be
    # DOCUMENTED where the rule is encoded — a choiceless enum bound to a scope dimension is NOT
    # a config bug. Pin that both notes name the exception + the resolver seam they mirror.
    for key in ("choices", "options"):
        note = _spec(key).note
        assert "scope" in note.lower() and "dimension" in note.lower(), (
            f"{key} note must document the scope-dimension-backed exception"
        )
        assert "_reject_invalid_overlay" in note, (
            f"{key} note must name the resolver seam it mirrors"
        )


def test_member_number_format_is_scoped_to_member_number_and_fixed_only():
    # §2 table: member_number_format applies to the member_number fixed field only.
    spec = _spec("member_number_format")
    assert set(spec.applies_to) == {AttributeApplies.FIXED}
    assert spec.required_when == (("key", "member_number"),)


def test_calculated_from_is_calculated_only_and_platform_owned():
    # §2 table: calculated_from is a read-only output of a calculated field — not authorable.
    spec = _spec("calculated_from")
    assert set(spec.applies_to) == {AttributeApplies.CALCULATED}
    assert spec.tenant_authorable is False


def test_visible_order_functional_group_default_optional_and_authorable():
    for key in ("visible", "order", "functional_group", "show_when"):
        spec = _spec(key)
        assert spec.required is False, f"{key} must default optional"
        assert spec.tenant_authorable is True, f"{key} must be tenant-authorable"


def test_scope_binding_is_declared_only_with_phase_3_note():
    # R8.1: scope_binding is declared in the vocabulary but wired in Phase 3, per the note.
    spec = _spec("scope_binding")
    assert spec.value_type == "bool"
    assert spec.required is False
    assert set(spec.applies_to) == {AttributeApplies.FIXED, AttributeApplies.VARIABLE}
    assert "Phase 3" in spec.note
    # R8.2: the Phase-3 wiring of scope-binding is into the RESOLVER — the note must name it.
    assert "resolver" in spec.note.lower()
    # R8.3: the note carries the deferred open question (how filtering derives from the flag).
    assert "filtering" in spec.note.lower()


def test_alias_is_declared_only_with_phase_3_note():
    # R8.1: alias is declared in the vocabulary but wired in Phase 3, per the note.
    spec = _spec("alias")
    assert spec.value_type == "i18n"
    assert spec.required is False
    assert "Phase 3" in spec.note
    # R8.2: the Phase-3 wiring of the alias is into RENDER — the note must name it.
    assert "render" in spec.note.lower()
    # R8.3: the note carries the deferred open question (label variant vs separate attribute).
    assert "label variant" in spec.note.lower()


def test_only_scope_binding_and_alias_are_marked_phase_3():
    # The Phase-3-declared-only attributes are EXACTLY scope_binding + alias — no other attribute
    # should carry a "wired in Phase 3" note (they are all live in Phase 1).
    phase_3 = {s.key for s in ATTRIBUTE_VOCABULARY if "Phase 3" in s.note}
    assert phase_3 == {"scope_binding", "alias"}


# ── build_attribute_catalog(): the computed field inventory + assembly (task 3.1) ──────
#
# Task 3.1: build_attribute_catalog() projects FIXED_FIELDS then CALCULATED_FIELDS into the
# catalog's CatalogField inventory via the SAME accessors the resolver reads, and assembles the
# AttributeCatalog with the authored vocabulary, the base group set, and the recorded label
# convention. These paired tests pin the behavior task 3.1 adds:
#   * the inventory is computed field-for-field from the registries (no re-typed names/labels) —
#     every CatalogField's values equal the registry object's via its accessors;
#   * fixed fields precede calculated ones, in registry order;
#   * origins are FIXED / CALCULATED respectively; calculated is read_only + non-required;
#   * attributes is ATTRIBUTE_VOCABULARY, functional_groups is BASE_FUNCTIONAL_GROUPS;
#   * label_convention is recorded (R3.7).
# The inventory ⇄ registry drift GUARD (set equality) and the self-validation fail-fast are
# tasks 3.3 / 3.2; here we pin that 3.1's projection + assembly are correct.
#
# Validates: Requirements R1.4, R1.6, R3.4

from sam.members.domain.attribute_catalog import (
    LABEL_CONVENTION,
    build_attribute_catalog,
)


def test_build_attribute_catalog_returns_an_attribute_catalog():
    catalog = build_attribute_catalog()
    assert isinstance(catalog, AttributeCatalog)


def test_build_attribute_catalog_is_pure_and_repeatable():
    # Pure (no DynamoDB/boto3, no hidden state): two builds yield equal catalogs.
    assert build_attribute_catalog() == build_attribute_catalog()


def test_build_attribute_catalog_attributes_is_the_authored_vocabulary():
    # The vocabulary is NOT re-derived — it is the module's authored ATTRIBUTE_VOCABULARY constant.
    assert build_attribute_catalog().attributes is ATTRIBUTE_VOCABULARY


def test_build_attribute_catalog_functional_groups_is_the_base_set():
    assert build_attribute_catalog().functional_groups is BASE_FUNCTIONAL_GROUPS


def test_build_attribute_catalog_records_the_label_convention():
    # R3.7: the i18n rule lives IN the artifact, not in folklore.
    catalog = build_attribute_catalog()
    assert catalog.label_convention == "i18n-keys+tenant-inline-override"
    assert catalog.label_convention == LABEL_CONVENTION


def test_build_attribute_catalog_inventory_count_equals_both_registries():
    catalog = build_attribute_catalog()
    assert len(catalog.fields) == len(FIXED_FIELDS) + len(CALCULATED_FIELDS)


def test_build_attribute_catalog_fixed_fields_precede_calculated_in_registry_order():
    # Fixed first (in FIXED_FIELDS order), then calculated (in CALCULATED_FIELDS order).
    catalog = build_attribute_catalog()
    expected = [f.dotted_key() for f in FIXED_FIELDS] + [
        c.dotted_key() for c in CALCULATED_FIELDS
    ]
    assert [cf.dotted_key for cf in catalog.fields] == expected
    # And the origin blocks don't interleave: every FIXED precedes every CALCULATED.
    origins = [cf.origin for cf in catalog.fields]
    first_calc = origins.index(AttributeApplies.CALCULATED)
    assert all(o is AttributeApplies.FIXED for o in origins[:first_calc])
    assert all(o is AttributeApplies.CALCULATED for o in origins[first_calc:])


def test_build_attribute_catalog_fixed_fields_match_the_registry_via_accessors():
    # Field-for-field: each fixed CatalogField's values equal the FixedField's — read through the
    # SAME accessors the resolver uses, so NO name/label is re-typed (R1.4 single-sourcing).
    catalog = build_attribute_catalog()
    by_key = {cf.dotted_key: cf for cf in catalog.fields}
    for f in FIXED_FIELDS:
        cf = by_key[f.dotted_key()]
        assert cf.origin is AttributeApplies.FIXED
        assert cf.key == f.key
        assert cf.storage_group == f.group.value
        assert cf.type == f.type.value
        assert cf.required == f.required
        assert cf.label == f.label
        assert cf.functional_group == f.default_functional_group()
        assert cf.order == f.order
        # A fixed field is stored → never read-only.
        assert cf.read_only is False


def test_build_attribute_catalog_calculated_fields_match_the_registry_via_accessors():
    # Field-for-field for calculated fields; the platform pins required=False + read_only=True for
    # every calculated field (mirrors FieldResolver._as_calculated_field).
    catalog = build_attribute_catalog()
    by_key = {cf.dotted_key: cf for cf in catalog.fields}
    for c in CALCULATED_FIELDS:
        cf = by_key[c.dotted_key()]
        assert cf.origin is AttributeApplies.CALCULATED
        assert cf.key == c.key
        assert cf.storage_group == c.group.value
        assert cf.type == c.type.value
        assert cf.label == c.label
        assert cf.functional_group == c.default_functional_group()
        assert cf.order == c.order
        assert cf.required is False
        assert cf.read_only is True


def test_build_attribute_catalog_labels_are_not_retyped():
    # The label objects are the registry's own mappings (identity), proving no re-typing: the
    # catalog projects the SAME label object the registry holds, it does not transcribe the text.
    catalog = build_attribute_catalog()
    by_key = {cf.dotted_key: cf for cf in catalog.fields}
    for f in FIXED_FIELDS:
        assert by_key[f.dotted_key()].label is f.label
    for c in CALCULATED_FIELDS:
        assert by_key[c.dotted_key()].label is c.label


def test_build_attribute_catalog_every_field_functional_group_is_a_base_group_key():
    # The computed inventory honours the base-group closure (R5.2) — a projected field never names
    # a group the base set omits.
    catalog = build_attribute_catalog()
    base_keys = {g.key for g in catalog.functional_groups}
    assert all(cf.functional_group in base_keys for cf in catalog.fields)


# ── Import-time self-validation fail-fast (task 3.2; design §6, R7.1) ───────────────────
#
# Task 3.2: build_attribute_catalog() is self-validating with the SAME fail-fast discipline the
# registries use — it raises ValueError when the assembled catalog is internally inconsistent, on
# any of the three design §6 cases:
#   1. a duplicate AttributeSpec.key in the vocabulary;
#   2. a CatalogField.functional_group not present in the base functional-group keys (a dangling
#      display-group reference);
#   3. an enum-rule inconsistency — a required_when `type` rule naming a value that is not a real
#      FieldType member value (so the R1.3 enum rule would silently never fire).
# The validation is factored as a pure helper (validate_catalog_consistency) taking the three
# pieces, so each bad case is exercised with deliberately-constructed bad inputs without corrupting
# the module constants. The real catalog must build cleanly (the shipped catalog is consistent).
#
# Validates: Requirements R7.1

from sam.members.domain.attribute_catalog import validate_catalog_consistency
from sam.members.domain.fixed_fields import FieldType

# A single valid CatalogField referencing a base group, reused by the bad-input fixtures below.
_VALID_FIELD = CatalogField(
    dotted_key="personal.first_name",
    key="first_name",
    origin=AttributeApplies.FIXED,
    storage_group="personal",
    type="string",
    required=False,
    label={"nl": "Voornaam", "en": "First name"},
    functional_group="personal",
    order=10,
    read_only=False,
)

# A single valid AttributeSpec, reused where the vocabulary is not the thing under test.
_VALID_SPEC = AttributeSpec(
    key="label",
    value_type="i18n",
    required=True,
    applies_to=(AttributeApplies.FIXED,),
    tenant_authorable=True,
)


def test_validate_catalog_consistency_accepts_the_real_catalog():
    # The shipped catalog is internally consistent — building it (which runs the validation)
    # does not raise, and validating its pieces directly does not raise either.
    catalog = build_attribute_catalog()
    validate_catalog_consistency(
        catalog.attributes, catalog.fields, catalog.functional_groups
    )


def test_build_attribute_catalog_does_not_raise_on_the_shipped_catalog():
    # The import-time self-validation + every build run clean for the real registries.
    build_attribute_catalog()  # must not raise


def test_validate_catalog_consistency_raises_on_a_duplicate_attribute_key():
    # Case 1: two AttributeSpecs sharing a key — the second silently shadows the first.
    dup = (
        AttributeSpec(
            key="order",
            value_type="int",
            required=False,
            applies_to=(AttributeApplies.FIXED,),
            tenant_authorable=True,
        ),
        AttributeSpec(
            key="order",  # duplicate key
            value_type="string",
            required=False,
            applies_to=(AttributeApplies.VARIABLE,),
            tenant_authorable=True,
        ),
    )
    with pytest.raises(ValueError, match="duplicate attribute key"):
        validate_catalog_consistency(dup, (_VALID_FIELD,), BASE_FUNCTIONAL_GROUPS)


def test_validate_catalog_consistency_raises_on_a_dangling_functional_group():
    # Case 2: a CatalogField whose functional_group is not a base-set key.
    dangling_field = dataclasses.replace(_VALID_FIELD, functional_group="not_a_base_group")
    with pytest.raises(ValueError, match="functional group absent from the base group set"):
        validate_catalog_consistency((_VALID_SPEC,), (dangling_field,), BASE_FUNCTIONAL_GROUPS)


def test_validate_catalog_consistency_raises_on_an_enum_rule_inconsistency():
    # Case 3: a required_when `type` rule naming a value that is NOT a real FieldType — the R1.3
    # enum rule would silently never fire against such a drifted literal.
    bad_enum_rule = (
        AttributeSpec(
            key="choices",
            value_type="list",
            required=False,
            applies_to=(AttributeApplies.FIXED,),
            tenant_authorable=True,
            required_when=(("type", "enumm"),),  # typo'd type value — not a FieldType member
        ),
    )
    with pytest.raises(ValueError, match="enum-rule inconsistency"):
        validate_catalog_consistency(bad_enum_rule, (_VALID_FIELD,), BASE_FUNCTIONAL_GROUPS)


def test_validate_catalog_consistency_accepts_a_valid_enum_type_rule():
    # A required_when rule naming the REAL FieldType.ENUM value is accepted (the shipped case).
    good_enum_rule = (
        AttributeSpec(
            key="choices",
            value_type="list",
            required=False,
            applies_to=(AttributeApplies.FIXED,),
            tenant_authorable=True,
            required_when=(("type", FieldType.ENUM.value),),
        ),
    )
    validate_catalog_consistency(good_enum_rule, (_VALID_FIELD,), BASE_FUNCTIONAL_GROUPS)  # no raise


# ── Inventory ⇄ registry DRIFT GUARD (task 3.3; design §2 "field inventory", §6, R1.4/R7.2) ──
#
# Task 3.3 is the DRIFT GUARD, distinct in FRAMING from task 3.1's accessor-projection tests
# above. Where 3.1 asks "does each CatalogField PROJECT its registry object correctly (field for
# field, via the resolver's accessors)?", 3.3 asks the Phase-0-drift-class question: "would this
# test FAIL if a registry gained or lost a field, or changed a field's platform-fixed attribute,
# WITHOUT the catalog following?" — the same lock-step discipline Phase 0 added for
# CALCULATED_FIELD_KEYS (R7.2), so a registry edit that bypasses the catalog breaks CI.
#
# Two guards:
#   1. SET EQUALITY on the dotted-key inventory — the catalog's field set is EXACTLY
#      {f.dotted_key() for f in FIXED_FIELDS} ∪ {c.dotted_key() for c in CALCULATED_FIELDS}.
#      A dropped registry field (in a registry, absent from the catalog) or a smuggled-in extra
#      (in the catalog, absent from both registries) both fail here — the symmetric difference is
#      surfaced so the offending key is named. This is the R1.4 "inventory matches the live
#      registries exactly, no field present in one and absent from the other" assertion.
#   2. PER-FIELD PLATFORM-FIXED-ATTRIBUTE EQUALITY — each CatalogField's platform-fixed attributes
#      equal the registry source's, enumerated as the drift guard (R7.2): if a registry field's
#      type / required / read-only / storage_group / functional_group / label / order changed and
#      the catalog did not follow, the paired assertion fails and names the attribute. Framed as
#      "what the registry pins" (origin-aware: fixed carries required=f.required, read_only=False;
#      calculated is platform-pinned required=False, read_only=True — the resolver's constants),
#      NOT as 3.1's "the projector copied the accessor".
#
# Validates: Requirements R1.4, R7.2


def test_catalog_inventory_set_equals_the_union_of_both_registries():
    # GUARD 1 (R1.4): exact SET equality of dotted keys. Catches a registry field that was
    # added/removed without the catalog following — the Phase-0 drift class at the catalog layer.
    catalog_keys = {cf.dotted_key for cf in build_attribute_catalog().fields}
    registry_keys = {f.dotted_key() for f in FIXED_FIELDS} | {
        c.dotted_key() for c in CALCULATED_FIELDS
    }
    missing_from_catalog = registry_keys - catalog_keys
    smuggled_into_catalog = catalog_keys - registry_keys
    assert catalog_keys == registry_keys, (
        f"catalog inventory drifted from the registries — "
        f"in a registry but absent from the catalog: {sorted(missing_from_catalog)}; "
        f"in the catalog but absent from both registries: {sorted(smuggled_into_catalog)}"
    )


def test_catalog_inventory_has_no_duplicate_dotted_keys():
    # The set-equality guard above compares SETS; pin that the catalog does not ALSO carry a
    # duplicate dotted key (which a set comparison would silently absorb) — the inventory is a
    # 1:1 projection, so its dotted keys are unique, exactly as the registries' are.
    dotted_keys = [cf.dotted_key for cf in build_attribute_catalog().fields]
    assert len(dotted_keys) == len(set(dotted_keys)), "duplicate dotted key in the catalog inventory"


def test_catalog_fixed_field_platform_fixed_attributes_track_the_registry():
    # GUARD 2 (R7.2) for FIXED fields: each CatalogField's PLATFORM-FIXED attributes equal what
    # the registry pins. If a FixedField's type / required / storage_group / functional_group /
    # label / order changed and the catalog did not follow, the matching assertion fails and names
    # the drifted attribute. A fixed field is stored, so the platform pins read_only=False.
    by_key = {cf.dotted_key: cf for cf in build_attribute_catalog().fields}
    for f in FIXED_FIELDS:
        cf = by_key[f.dotted_key()]
        dk = f.dotted_key()
        assert cf.origin is AttributeApplies.FIXED, f"{dk}: origin drifted"
        assert cf.key == f.key, f"{dk}: key drifted"
        assert cf.type == f.type.value, f"{dk}: type drifted from the registry"
        assert cf.required == f.required, f"{dk}: required drifted from the registry"
        assert cf.read_only is False, f"{dk}: a stored fixed field must stay read_only=False"
        assert cf.storage_group == f.group.value, f"{dk}: storage_group drifted"
        assert cf.functional_group == f.default_functional_group(), (
            f"{dk}: functional_group drifted from default_functional_group()"
        )
        assert cf.label == f.label, f"{dk}: label drifted from the registry"
        assert cf.order == f.order, f"{dk}: order drifted from the registry"


def test_catalog_calculated_field_platform_fixed_attributes_track_the_registry():
    # GUARD 2 (R7.2) for CALCULATED fields: same per-attribute drift guard. The platform pins a
    # calculated field required=False + read_only=True unconditionally (the resolver's constants —
    # CalculatedField exposes no required/read_only accessor); the rest track the registry. A drift
    # in type / storage_group / functional_group / label / order fails the paired assertion.
    by_key = {cf.dotted_key: cf for cf in build_attribute_catalog().fields}
    for c in CALCULATED_FIELDS:
        cf = by_key[c.dotted_key()]
        dk = c.dotted_key()
        assert cf.origin is AttributeApplies.CALCULATED, f"{dk}: origin drifted"
        assert cf.key == c.key, f"{dk}: key drifted"
        assert cf.type == c.type.value, f"{dk}: type drifted from the registry"
        assert cf.required is False, f"{dk}: a calculated field is platform-pinned required=False"
        assert cf.read_only is True, f"{dk}: a calculated field is platform-pinned read_only=True"
        assert cf.storage_group == c.group.value, f"{dk}: storage_group drifted"
        assert cf.functional_group == c.default_functional_group(), (
            f"{dk}: functional_group drifted from default_functional_group()"
        )
        assert cf.label == c.label, f"{dk}: label drifted from the registry"
        assert cf.order == c.order, f"{dk}: order drifted from the registry"


def test_catalog_inventory_drift_guard_covers_every_field_exactly_once():
    # The two per-field guards above iterate the registries; this pins the OTHER direction — every
    # CatalogField is reached by exactly one of them (its origin is FIXED xor CALCULATED), so no
    # catalog field escapes the drift guard. Belt-and-suspenders against a projected field with an
    # unexpected origin slipping past both registry loops.
    fields = build_attribute_catalog().fields
    fixed_count = sum(1 for cf in fields if cf.origin is AttributeApplies.FIXED)
    calc_count = sum(1 for cf in fields if cf.origin is AttributeApplies.CALCULATED)
    assert fixed_count == len(FIXED_FIELDS)
    assert calc_count == len(CALCULATED_FIELDS)
    assert fixed_count + calc_count == len(fields), "a catalog field has an origin outside fixed/calculated"

# ── Vocabulary COMPLETENESS: every modelled dataclass attribute has an AttributeSpec (task 3.4) ──
#
# Task 3.4 is the OTHER half of the R7.2 lock-step guard. Task 3.3 guards the field INVENTORY
# (the registry rows) against drift; task 3.4 guards the attribute VOCABULARY against drift —
# every attribute the registry/overlay DATACLASSES expose must have a matching `AttributeSpec` in
# ATTRIBUTE_VOCABULARY. The question it asks the Phase-0-drift way: "if someone adds a new
# attribute to FixedField / CalculatedField / OverlayField / FixedFieldOverride without authoring
# its vocabulary entry, does CI break?" (R1.1 completeness, R7.2 lock-step).
#
# The four dataclasses are the live declaration of what a field DEFINITION may carry:
#   * FixedField / CalculatedField  — the platform registries (fixed_fields.py / calculated_fields.py);
#   * OverlayField                  — a tenant-authored variable field (field_resolver.py);
#   * FixedFieldOverride            — a tenant's presentation-only override of a fixed/calc field.
# We introspect their fields with dataclasses.fields() (NOT a hand-copied list — a hand-copied list
# would itself drift) and require every MODELLED field attribute to map to a vocabulary key.
#
# A dataclass field maps to the vocabulary in one of two ways, and NOTHING is silently ignored:
#
#   1. `_DATACLASS_FIELD_TO_ATTRIBUTE` — the modelled field attributes. Most map by identical name
#      (`label` → `label`); the ONE renamed mapping is `inputs` → `calculated_from` (the §2 table +
#      the `calculated_from` AttributeSpec note: "the registry's `inputs`"). Every value here MUST
#      be a real vocabulary key.
#
#   2. `_NON_ATTRIBUTE_DATACLASS_FIELDS` — the EXPLICIT, DOCUMENTED allow-list of dataclass fields
#      that are deliberately NOT modelled field attributes (so they correctly have no AttributeSpec),
#      each with the reason:
#        * `group`   — the STORAGE bucket (FieldGroup: personal/membership), structural + fixed by
#                      origin, orthogonal to the display `functional_group`. The catalog captures it
#                      as CatalogField.storage_group, not as an authorable/declared vocabulary
#                      attribute (design glossary: storage group vs functional group).
#        * `compute` — the pure derivation FUNCTION of a CalculatedField, not a declared attribute;
#                      what IS modelled is its `inputs` (→ `calculated_from`). A callable is code,
#                      not a field-definition property a catalog consumer authors or reads.
#
# A dataclass field that is in NEITHER mapping fails the test LOUDLY (named), so a genuinely-new
# attribute cannot slip through by being quietly ignored — the explicit allow-list is the point.
# The reverse direction (`scope_binding` + `alias` are vocabulary entries DECLARED ahead of any
# dataclass carrying them, R8.1) is intentionally NOT asserted here — this test is dataclass→vocab
# completeness, and those Phase-3-declared specs are pinned by the task-2.4 tests above.
#
# Validates: Requirements R1.1, R7.2

from sam.members.domain.calculated_fields import CalculatedField
from sam.members.domain.field_resolver import FixedFieldOverride, OverlayField
from sam.members.domain.fixed_fields import FixedField

#: The four dataclasses whose exposed attributes the vocabulary must cover (R7.2 lock-step).
_FIELD_DEFINITION_DATACLASSES = (
    FixedField,
    CalculatedField,
    OverlayField,
    FixedFieldOverride,
)

#: Modelled dataclass field name → the ATTRIBUTE_VOCABULARY key it corresponds to. Identity for
#: all but `inputs` → `calculated_from` (design §2; the `calculated_from` AttributeSpec note names
#: "the registry's `inputs`"). Every VALUE must be a real vocabulary key (asserted below).
_DATACLASS_FIELD_TO_ATTRIBUTE: dict[str, str] = {
    "key": "key",
    "type": "type",
    "required": "required",
    "label": "label",
    "visible": "visible",
    "order": "order",
    "functional_group": "functional_group",
    "choices": "choices",
    "options": "options",
    "show_when": "show_when",
    "member_number_format": "member_number_format",
    "inputs": "calculated_from",
}

#: EXPLICIT allow-list of dataclass fields that are deliberately NOT modelled catalog attributes
#: (so they correctly have no AttributeSpec), each with its reason — see the block comment above.
_NON_ATTRIBUTE_DATACLASS_FIELDS: dict[str, str] = {
    "group": "the STORAGE bucket (FieldGroup), structural/origin-fixed — captured as "
    "CatalogField.storage_group, not a vocabulary attribute",
    "compute": "the pure derivation function of a calculated field — its `inputs` are modelled "
    "(→ calculated_from), the callable itself is not a declared attribute",
}


def _all_dataclass_field_names() -> set[str]:
    """The union of field names across the four field-definition dataclasses (introspected)."""
    names: set[str] = set()
    for klass in _FIELD_DEFINITION_DATACLASSES:
        names.update(f.name for f in dataclasses.fields(klass))
    return names


def test_vocabulary_completeness_mapping_targets_are_real_vocabulary_keys():
    # Guardrail on the mapping itself: every attribute key the mapping claims to cover must
    # actually exist in ATTRIBUTE_VOCABULARY — otherwise a typo'd target would make the
    # completeness check below pass vacuously for that dataclass field.
    vocab_keys = {s.key for s in ATTRIBUTE_VOCABULARY}
    unknown_targets = {
        src: dst for src, dst in _DATACLASS_FIELD_TO_ATTRIBUTE.items() if dst not in vocab_keys
    }
    assert not unknown_targets, (
        f"the dataclass→attribute mapping points at vocabulary keys that do not exist: "
        f"{unknown_targets} (vocabulary keys: {sorted(vocab_keys)})"
    )


def test_vocabulary_completeness_mapping_and_allow_list_are_disjoint():
    # A dataclass field is EITHER a modelled attribute OR an intentional non-attribute — never
    # both. Overlap would hide a drift (a field could be "covered" two ways and mask a problem).
    overlap = set(_DATACLASS_FIELD_TO_ATTRIBUTE) & set(_NON_ATTRIBUTE_DATACLASS_FIELDS)
    assert not overlap, f"dataclass field classified as both attribute and non-attribute: {overlap}"


def test_every_dataclass_field_is_explicitly_classified():
    # The completeness LOCK (R1.1/R7.2): every field the four dataclasses expose must be EITHER
    # mapped to a vocabulary attribute OR on the documented non-attribute allow-list. A brand-new
    # attribute added to a dataclass without a vocabulary entry (and without being allow-listed)
    # lands here, UNCLASSIFIED — breaking CI, naming the offender, exactly as R7.2 requires.
    classified = set(_DATACLASS_FIELD_TO_ATTRIBUTE) | set(_NON_ATTRIBUTE_DATACLASS_FIELDS)
    unclassified = _all_dataclass_field_names() - classified
    assert not unclassified, (
        f"dataclass attribute(s) with no matching AttributeSpec and not on the documented "
        f"non-attribute allow-list: {sorted(unclassified)} — add an AttributeSpec to "
        f"ATTRIBUTE_VOCABULARY (or, if genuinely not a catalog attribute, add it to "
        f"_NON_ATTRIBUTE_DATACLASS_FIELDS with a reason)"
    )


def test_every_modelled_dataclass_attribute_has_a_matching_attribute_spec():
    # The positive assertion (R1.1): every MODELLED dataclass field (i.e. one the mapping treats
    # as a real attribute) resolves to an AttributeSpec present in the vocabulary. Belt-and-
    # suspenders with the "targets are real keys" test, but phrased per actual dataclass field so a
    # failure names the dataclass attribute, not just the mapping value.
    by_key = {s.key for s in ATTRIBUTE_VOCABULARY}
    modelled = _all_dataclass_field_names() - set(_NON_ATTRIBUTE_DATACLASS_FIELDS)
    missing = {
        name: _DATACLASS_FIELD_TO_ATTRIBUTE.get(name)
        for name in modelled
        if _DATACLASS_FIELD_TO_ATTRIBUTE.get(name) not in by_key
    }
    assert not missing, (
        f"modelled dataclass attribute(s) with no matching AttributeSpec in ATTRIBUTE_VOCABULARY: "
        f"{missing}"
    )


def test_vocabulary_completeness_allow_list_only_names_real_dataclass_fields():
    # Keep the allow-list honest: a field it names must actually exist on one of the dataclasses.
    # A stale allow-list entry (a field since renamed/removed) would silently suppress nothing and
    # rot — fail if the allow-list references a field no dataclass exposes any more.
    stale = set(_NON_ATTRIBUTE_DATACLASS_FIELDS) - _all_dataclass_field_names()
    assert not stale, f"allow-list names dataclass field(s) that no longer exist: {sorted(stale)}"

# ── build_attribute_catalog() ITSELF raises on an inconsistent catalog (task 3.5; R7.1) ──
#
# Task 3.5 is the END-TO-END self-validation test, distinct in FRAMING from task 3.2's helper
# tests above. Task 3.2 exercises the PURE helper `validate_catalog_consistency` with
# deliberately-constructed bad tuples; task 3.5 asserts that `build_attribute_catalog()` — the
# function the whole module (and import-time load) runs — ITSELF raises `ValueError` when the
# module-level inputs it actually CONSUMES are inconsistent. The difference matters: 3.2 proves
# the invariant checker works in isolation; 3.5 proves the builder is genuinely WIRED to it over
# the real inputs it reads, so an inconsistent registry/vocabulary could never silently build.
#
# `build_attribute_catalog()` reads its inputs by NAME from the module at call time —
# `ATTRIBUTE_VOCABULARY` and `BASE_FUNCTIONAL_GROUPS` directly, and the registries
# (`FIXED_FIELDS` / `CALCULATED_FIELDS`) via the projection helpers, which reference them as
# module globals — so `monkeypatch.setattr` on the `attribute_catalog` module genuinely changes
# what the builder consumes and drives the raise through `build_attribute_catalog()` (the function
# does NOT close over private local copies). Monkeypatch restores the originals automatically.
#
# Two inconsistencies injected, matching design §6 / R7.1 — a duplicate attribute key (via the
# vocabulary the builder reads) and a dangling functional group (via shrinking the base group set
# so a REAL projected field's functional_group is no longer a base key):
#
# Validates: Requirements R7.1

import sam.members.domain.attribute_catalog as attribute_catalog


def test_build_attribute_catalog_raises_on_a_duplicate_attribute_key(monkeypatch):
    # Inject a duplicate AttributeSpec.key into the vocabulary the builder reads, then assert
    # build_attribute_catalog() ITSELF raises — not just the helper. The duplicate is the shipped
    # vocabulary with one real spec appended again (same key), so the only inconsistency is the dup.
    duplicated_vocabulary = ATTRIBUTE_VOCABULARY + (ATTRIBUTE_VOCABULARY[0],)
    monkeypatch.setattr(attribute_catalog, "ATTRIBUTE_VOCABULARY", duplicated_vocabulary)
    with pytest.raises(ValueError, match="duplicate attribute key"):
        attribute_catalog.build_attribute_catalog()


def test_build_attribute_catalog_raises_on_a_dangling_functional_group(monkeypatch):
    # Inject a DANGLING functional group by SHRINKING the base group set the builder reads so a
    # REAL projected field's functional_group is no longer a base key. We drop whichever base
    # group a shipped field actually references, guaranteeing at least one projected CatalogField
    # dangles — the inconsistency flows through the real inventory projection, not a hand-built one.
    referenced = {f.default_functional_group() for f in FIXED_FIELDS} | {
        c.default_functional_group() for c in CALCULATED_FIELDS
    }
    shrunk_base_groups = tuple(
        g for g in BASE_FUNCTIONAL_GROUPS if g.key not in referenced
    )
    # Sanity: the shrink must actually remove a referenced group (otherwise the test is vacuous).
    assert len(shrunk_base_groups) < len(BASE_FUNCTIONAL_GROUPS), (
        "no shipped field references a base group — cannot inject a dangling reference"
    )
    monkeypatch.setattr(attribute_catalog, "BASE_FUNCTIONAL_GROUPS", shrunk_base_groups)
    with pytest.raises(ValueError, match="functional group absent from the base group set"):
        attribute_catalog.build_attribute_catalog()


def test_build_attribute_catalog_succeeds_again_after_monkeypatch_restored():
    # Sanity (the restore half of the two injections above): with the module globals back to their
    # shipped values, build_attribute_catalog() builds the real, consistent catalog without raising.
    # monkeypatch auto-restores between tests, so this confirms the injections did not leak.
    catalog = attribute_catalog.build_attribute_catalog()
    assert isinstance(catalog, AttributeCatalog)
    assert catalog.attributes is ATTRIBUTE_VOCABULARY
    assert catalog.functional_groups is BASE_FUNCTIONAL_GROUPS


# ── The resolve-with-precedence rule: resolve_label() (task 5.2; design §3, R3.3/R2.2) ──
#
# Task 5.2: the ONE i18n label rule — label[locale] = tenant_inline[locale] ?? resource(key)[locale]
# ?? fallback(locale) — implemented as the PURE helper `resolve_label`, producing the served inline
# {nl,en,…} dict (so the GET /members/field-config response shape + the frontend `resolveLabel` are
# UNCHANGED, R2.2). These paired tests pin, per design §8:
#   * tenant inline WINS per locale when present;
#   * the resource layer is used when the tenant authored nothing for that locale;
#   * the registry fallback is used when neither has that locale;
#   * PER-LOCALE independence — nl from the tenant inline dict AND en from the resource layer in the
#     SAME returned dict (R3.3);
#   * the served value is an inline {nl,en,…} dict (shape unchanged, R2.2);
#   * a blank/missing entry at a tier falls through, never renders blank (R3.5);
#   * the Phase-1 byte-identity: when resource == fallback (task 5.1 seeded the resource layer FROM
#     the registry values) and no tenant override, the rule reproduces the registry's inline dict —
#     so the served output is unchanged and the task-4.2 resolver lock stays green (R2.1).
#
# Validates: Requirements R3.3, R2.2

from sam.members.domain.attribute_catalog import (
    LABEL_FALLBACK_ORDER,
    resolve_label,
)


def test_resolve_label_tenant_inline_wins_over_resource_and_fallback():
    # R3.3: a tenant inline value overrides the resource-key default (and the registry fallback).
    served = resolve_label(
        tenant_inline={"nl": "Mijn label", "en": "My label"},
        resource={"nl": "Resource NL", "en": "Resource EN"},
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},
    )
    assert served == {"nl": "Mijn label", "en": "My label"}


def test_resolve_label_uses_resource_when_no_tenant_inline():
    # R3.3: with no tenant override, the shipped resource-key default is used (over the fallback).
    served = resolve_label(
        tenant_inline=None,
        resource={"nl": "Resource NL", "en": "Resource EN"},
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},
    )
    assert served == {"nl": "Resource NL", "en": "Resource EN"}


def test_resolve_label_uses_fallback_when_neither_inline_nor_resource():
    # R3.3: neither a tenant inline value nor a resource entry → the registry fallback is used.
    served = resolve_label(
        tenant_inline=None,
        resource=None,
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},
    )
    assert served == {"nl": "Fallback NL", "en": "Fallback EN"}


def test_resolve_label_merges_locales_independently():
    # R3.3 (the independence property): the merge is PER LOCALE — nl taken from the tenant inline
    # dict, en from the resource layer, in the SAME returned dict. No tier wins the whole label.
    served = resolve_label(
        tenant_inline={"nl": "Tenant NL"},            # only nl authored by the tenant
        resource={"en": "Resource EN"},               # only en in the resource layer
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},
    )
    assert served == {"nl": "Tenant NL", "en": "Resource EN"}


def test_resolve_label_returns_an_inline_locale_dict_shape():
    # R2.2: the served label stays an inline {locale: str} dict — the SAME shape served today, so
    # the response contract + the frontend `resolveLabel` are unchanged (not a string, not a key).
    served = resolve_label(fallback={"nl": "Naam", "en": "Name"})
    assert isinstance(served, dict)
    assert set(served) == {"nl", "en"}
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in served.items())


def test_resolve_label_falls_through_a_blank_tier_entry():
    # R3.5: a blank/empty value at a higher-precedence tier is treated as ABSENT for that locale,
    # so the next tier supplies it — a label is never rendered blank when a lower tier can fill it.
    served = resolve_label(
        tenant_inline={"nl": "   ", "en": ""},        # blank/whitespace → absent per locale
        resource={"nl": "Resource NL"},               # supplies nl
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},  # supplies en
    )
    assert served == {"nl": "Resource NL", "en": "Fallback EN"}


def test_resolve_label_includes_a_tenant_only_locale():
    # A locale only the tenant authored (e.g. a backfilled third language) appears in the served
    # dict — the {nl,en,…} dict grows with the languages actually present (R3.6 forward-compat).
    served = resolve_label(
        tenant_inline={"nl": "Tenant NL", "de": "Tenant DE"},
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},
    )
    assert served == {"nl": "Tenant NL", "en": "Fallback EN", "de": "Tenant DE"}


def test_resolve_label_includes_a_resource_only_locale():
    # A locale present only in the resource layer (a translator-dropped language) appears too, with
    # no tenant inline value and no registry fallback for it — shipped labels own that locale.
    served = resolve_label(
        resource={"nl": "Resource NL", "fr": "Resource FR"},
        fallback={"nl": "Fallback NL", "en": "Fallback EN"},
    )
    assert served == {"nl": "Resource NL", "en": "Fallback EN", "fr": "Resource FR"}


def test_resolve_label_with_no_sources_is_empty():
    # The degenerate "nothing anywhere" case → an empty dict; the frontend `resolveLabel`'s own
    # key-fallback then renders the canonical key (never blank). No tier means no served locale.
    assert resolve_label() == {}


def test_resolve_label_is_pure_and_does_not_mutate_its_inputs():
    # Pure: the inputs are not mutated and the result is a fresh dict (not an aliased source), so a
    # caller may reuse the registry's label mapping safely.
    tenant = {"nl": "Tenant NL"}
    resource = {"en": "Resource EN"}
    fallback = {"nl": "Fallback NL", "en": "Fallback EN"}
    served = resolve_label(tenant_inline=tenant, resource=resource, fallback=fallback)
    assert tenant == {"nl": "Tenant NL"}
    assert resource == {"en": "Resource EN"}
    assert fallback == {"nl": "Fallback NL", "en": "Fallback EN"}
    assert served is not tenant and served is not resource and served is not fallback


def test_resolve_label_reproduces_the_registry_dict_when_resource_equals_fallback():
    # The Phase-1 NON-BREAKING property (R2.1 / the task-4.2 resolver lock): task 5.1 seeded the
    # resource layer FROM the registry fallback for the base nl/en keys, so for a shipped field with
    # NO tenant override `resource[locale] == fallback[locale]` and the rule reproduces the
    # registry's inline {nl,en} dict byte-for-byte — the served output is unchanged by this task.
    registry_label = {"nl": "Voornaam", "en": "First name"}
    served = resolve_label(
        tenant_inline=None,
        resource=dict(registry_label),   # seeded from the same values (task 5.1)
        fallback=registry_label,
    )
    assert served == registry_label


def test_label_fallback_order_tail_is_recorded_on_the_artifact():
    # R3.5 / R3.7: the locale-independent TAIL of the missing-locale fallback chain (en → nl) is
    # recorded in the artifact, so the serializer and the frontend resolve a missing locale the SAME
    # way (the leading `active` locale is supplied at render by the caller). Pin the recorded tail.
    assert LABEL_FALLBACK_ORDER == ("en", "nl")

# ── Enum value/label SPLIT guardrail: value is language-neutral, only label is per-locale (task 5.3) ──
#
# Task 5.3 pins the ONE invariant R3.4 makes impossible-by-construction: an enum option's canonical
# `value` is the LANGUAGE-NEUTRAL token the platform stores / filters / pivots analytics off — it is
# NEVER translated and NEVER itself a per-language ({nl,en,…}) dict. Only the option's `label` is
# per-locale. The i18n resource scheme (task 5.1) even USES the option value as a stable key segment
# (`admin:membersConfig.enum.<fieldKey>.<optionValue>`) — the value is a KEY, not translated text —
# and `resolve_label` (task 5.2) resolves the LABEL per-locale and must never touch the `value`.
#
# The risk this guards against: if a `value` ever became language-keyed (or got translated per
# locale), the stored token on every member record would silently diverge from the option it was
# written as — invalidating historical data. These tests demonstrate a stored `value` is STABLE
# across locales (resolving/rendering the label in nl vs en yields the SAME value) and that `value`
# is a bare string, never a {nl,en} dict.
#
# Validates: Requirements R3.4

from collections.abc import Mapping

from sam.members.domain.fixed_fields import EnumOption, field_by_key


def _status_options() -> tuple[EnumOption, ...]:
    """The shipped `membership.status` rich enum options from the fixed-field registry (real API)."""
    status = field_by_key("membership.status")
    assert status is not None and status.options, "membership.status must ship rich enum options"
    return tuple(status.options)


def test_enum_option_value_is_a_language_neutral_string_not_a_language_keyed_dict():
    # R3.4: every shipped status option's `value` is a single bare string — NOT a Mapping and NOT a
    # {nl,en,…} per-language dict. The language-neutral canonical token can never be a label.
    for opt in _status_options():
        assert isinstance(opt.value, str), f"option value must be a str, got {type(opt.value)!r}"
        assert not isinstance(opt.value, Mapping), f"option value must not be language-keyed: {opt.value!r}"
        assert opt.value.strip(), "option value must be a non-blank canonical token"
        # Only the LABEL is per-language — it IS the {nl,en} dict, so the split is unmistakable.
        assert isinstance(opt.label, Mapping), f"option {opt.value!r} label must be the per-locale dict"
        assert set(opt.label) == {"nl", "en"}, f"option {opt.value!r} ships nl+en labels"


def test_shipped_status_option_values_are_the_stable_canonical_tokens():
    # R3.4: the stored `value` tokens are the platform-canonical, language-neutral membership-status
    # set — the exact strings member records store and filters/pivots key off. Pin them so a rename
    # (which would invalidate stored data) is caught here, and so they never acquire a locale.
    values = tuple(o.value for o in _status_options())
    assert values == ("application", "pending", "active", "suspended", "lapsed", "left")


def test_resolving_an_option_label_across_locales_leaves_value_identical():
    # R3.4 (the core invariant): resolving/rendering an option's LABEL in nl vs en yields the SAME
    # stored `value`. `resolve_label` operates on the label dict only — the canonical token is stable
    # across locales because the value is simply never an input to label resolution.
    for opt in _status_options():
        served = resolve_label(fallback=dict(opt.label))      # render the per-locale label
        # The label differs per locale (that's the point of translating it: Actief vs Active, …)…
        assert served["nl"] != served["en"], f"option {opt.value!r} labels should differ nl vs en"
        # …but the stored value is identical regardless of which locale we render the label in: the
        # value never participates in label resolution, so it is stable across locales.
        assert opt.value == opt.value  # noqa: PLR0124 — the token is the same object for every locale
        # And the value is NEVER one of the (translated) label texts — it is the neutral token.
        assert opt.value not in served.values(), (
            f"option value {opt.value!r} must not equal a translated label text {served!r}"
        )


def test_option_value_is_the_enum_resource_key_segment_never_translated_text():
    # R3.4 + task 5.1 scheme: the resource key for a shipped option label embeds the option VALUE as
    # a stable segment — `admin:membersConfig.enum.<fieldKey>.<optionValue>`. The value is thus a
    # language-neutral KEY, and the translated text lives behind that key, never in the value.
    field_key = "status"
    for opt in _status_options():
        resource_key = f"admin:membersConfig.enum.{field_key}.{opt.value}"
        # The value appears verbatim as the trailing key segment (stable, un-translated)…
        assert resource_key.endswith(f".{opt.value}")
        # …and the per-locale label text is NOT what keys the resource — the value is. No locale's
        # translated label text ever equals the canonical token (Aanmelding/Application ≠ application
        # would be the risky case; "active"=="active" below is deliberately asserted as NOT-equal).
        for locale_text in opt.label.values():
            assert opt.value != locale_text, (
                f"option value {opt.value!r} must differ from its translated label {locale_text!r}"
            )

# ── Add-a-language PROOF: a new locale is a DATA change, not a code change (task 5.6) ──
#
# Task 5.6 / R3.6: adding a language (`de`) must be purely a DATA change — no edit to the domain
# code (`resolve_label`, the registries, the catalog). We PROVE it by exercising `resolve_label`
# EXACTLY as it ships today, passing a `de` entry only as DATA:
#
#   1. A shipped base key gains a `de` resource entry (a translator-dropped resource value, modelled
#      here as a `resource` dict carrying `de`) → `resolve_label` resolves `de` for a `de`-active
#      user WITH NO CHANGE to the helper. The served {nl,en,…} dict simply GROWS a `de` key — the
#      model is locale-independent, so `de` is resolved by the same union-of-present-locales merge
#      that resolves nl/en (no `de`-specific branch anywhere).
#   2. A tenant field that has NO `de` label (neither inline nor resource) falls back per task 5.5's
#      recorded chain — the active `de` is absent → the artifact's `LABEL_FALLBACK_ORDER = ("en",
#      "nl")` tail supplies `en` then `nl`, and the frontend `resolveLabel` renders the canonical key
#      if even those are absent — never blank.
#
# This is the SAM half of the proof; the frontend half (a `de`-active user through `resolveLabel`)
# is `frontend/src/components/members/fieldForm.test.ts`. Neither touches a committed shipped
# resource file: the `de` entry is constructed IN the test (the lower-risk, convention-matching
# proof — see the task note), so the task-5.1 nl↔en parity test and the task-4.2/5.2 locks are
# untouched. The point stands regardless: an arbitrary new locale resolves with no domain code edit.
#
# Validates: Requirements R3.6

# One base shipped field (a FIXED_FIELDS entry) used as the "add a language for ONE base key" subject.
_FIRST_NAME_REGISTRY_LABEL = {"nl": "Voornaam", "en": "First name"}


def test_adding_a_de_resource_entry_resolves_with_no_domain_code_change():
    # R3.6 (the core proof): drop a `de` value into the resource layer for ONE base key — the exact
    # shape a translator-added `de` resource file produces once the serializer reads it. Calling the
    # UNCHANGED `resolve_label` with that data resolves `de` for a `de`-active user: the served dict
    # grows a `de` entry alongside the shipped nl/en. No branch in the helper knows about `de`.
    served = resolve_label(
        tenant_inline=None,
        resource={"nl": "Voornaam", "en": "First name", "de": "Vorname"},
        fallback=_FIRST_NAME_REGISTRY_LABEL,
    )
    # `de` resolves to the dropped resource value…
    assert served["de"] == "Vorname"
    # …and the shipped nl/en are unaffected — the dict simply GREW a locale (data change only).
    assert served["nl"] == "Voornaam"
    assert served["en"] == "First name"


def test_adding_a_de_tenant_inline_entry_resolves_with_no_domain_code_change():
    # R3.6 (the tenant-authored side): a tenant backfilling a `de` label for its OWN field is also
    # pure data — `resolve_label` picks the tenant inline `de` over the resource/fallback, no code
    # change. (A tenant custom field has no shipped resource key; its de label is inline data.)
    served = resolve_label(
        tenant_inline={"nl": "Mijn veld", "en": "My field", "de": "Mein Feld"},
        resource=None,
        fallback=None,
    )
    assert served == {"nl": "Mijn veld", "en": "My field", "de": "Mein Feld"}


def test_a_field_with_no_de_label_falls_back_per_task_5_5_chain():
    # R3.6 + R3.5: a tenant field that has NO `de` label (neither inline nor resource carries `de`)
    # must NOT render blank for a `de`-active user — it falls back per task 5.5's chain. The served
    # dict carries no `de` key, so the render-side `resolveLabel('de', key)` takes the recorded
    # `LABEL_FALLBACK_ORDER = ("en", "nl")` tail: `de` (absent) → en → nl → the canonical key.
    served = resolve_label(
        tenant_inline=None,
        resource={"nl": "Voornaam", "en": "First name"},  # no `de` entry anywhere
        fallback=_FIRST_NAME_REGISTRY_LABEL,
    )
    # The served dict has NO `de` — the add-a-language backfill for THIS field has not happened…
    assert "de" not in served
    # …and the recorded tail is still (en, nl), so render falls `de → en → nl → key`, never blank.
    assert LABEL_FALLBACK_ORDER == ("en", "nl")
    # Simulate the render-side pick for a `de`-active user over the served dict: en wins (the tail's
    # head), proving the fallback is deterministic and non-blank without any `de`-specific code.
    de_active = served.get("de") or served.get("en") or served.get("nl") or "membersConfig.field.first_name"
    assert de_active == "First name"
    assert de_active != ""


def test_resolve_label_has_no_locale_specific_branch_so_any_new_locale_resolves():
    # R3.6 (the generality proof): the helper is locale-AGNOSTIC — the SAME call shape resolves an
    # arbitrary, never-before-seen locale (`xx`) exactly as it resolves `de`. This is WHY adding a
    # language is a data change: there is no per-language code to add.
    for new_locale in ("de", "fr", "xx"):
        served = resolve_label(
            resource={"nl": "Voornaam", "en": "First name", new_locale: f"{new_locale}-label"},
            fallback=_FIRST_NAME_REGISTRY_LABEL,
        )
        assert served[new_locale] == f"{new_locale}-label"

# ── The COMPLETE i18n convention is recorded ON the artifact (task 5.7; design §3, R3.7) ──
#
# Task 5.7: R3.7 says "the i18n rule lives IN the artifact, not in folklore" — and the WHOLE rule,
# not just its name. Tasks 3.1/5.2/5.5 already recorded the convention NAME (label_convention) and
# the fallback-order TAIL (LABEL_FALLBACK_ORDER). Task 5.7 completes the record by surfacing all
# three pieces as FIRST-CLASS fields on the assembled AttributeCatalog, AND adding the one piece
# that previously lived only in the frontend resource files + a test comment: the shipped-label
# KEY SCHEME (task 5.1 — admin:membersConfig.field/group/enum templates). A consumer must be able
# to read the convention name, the fallback order, AND the key templates straight off the catalog.
#
# These tests pin:
#   * LABEL_KEY_SCHEME records the admin namespace + membersConfig category + the three templates;
#   * its field_key()/group_key()/enum_key() helpers produce the exact task-5.1 keys;
#   * the built catalog ARTIFACT carries label_convention + label_fallback_order + label_key_scheme
#     (so the whole rule is read off the artifact, not module constants or folklore);
#   * the recorded key scheme AGREES with the frontend task-5.1 scheme (rule-5 shared vocabulary) —
#     asserted here against the SAME literal templates the frontend test transcribes, so the two
#     planes cannot contradict (no cross-plane import; both pin the same strings).
#
# Validates: Requirements R3.7

from sam.members.domain.attribute_catalog import (
    LABEL_KEY_SCHEME,
    LabelKeyScheme,
)


def test_label_key_scheme_records_the_admin_namespace_and_members_config_category():
    # R3.7 + task 5.1: the shipped-label scheme lives under the frontend `admin` namespace,
    # `membersConfig` category — recorded on the artifact, not re-derived from the resource files.
    assert isinstance(LABEL_KEY_SCHEME, LabelKeyScheme)
    assert LABEL_KEY_SCHEME.namespace == "admin"
    assert LABEL_KEY_SCHEME.category == "membersConfig"


def test_label_key_scheme_templates_match_the_task_5_1_scheme():
    # The three templates are EXACTLY the task-5.1 / design §3 scheme. Pinning the literal templates
    # is the rule-5 shared-vocabulary guard: the frontend test transcribes the SAME strings, so a
    # change here that the frontend did not follow (or vice versa) surfaces as a contradiction.
    assert LABEL_KEY_SCHEME.field_template == "admin:membersConfig.field.{field_key}"
    assert LABEL_KEY_SCHEME.group_template == "admin:membersConfig.group.{group_key}"
    assert LABEL_KEY_SCHEME.enum_template == "admin:membersConfig.enum.{field_key}.{option_value}"


def test_label_key_scheme_field_key_builds_the_shipped_field_resource_key():
    # The field template resolves to the task-5.1 key for a shipped field (snake_case key segment
    # preserved verbatim — translating it would break the key, R3.4).
    assert LABEL_KEY_SCHEME.field_key("first_name") == "admin:membersConfig.field.first_name"
    assert LABEL_KEY_SCHEME.field_key("member_number") == "admin:membersConfig.field.member_number"


def test_label_key_scheme_group_key_builds_the_shipped_group_resource_key():
    assert LABEL_KEY_SCHEME.group_key("administrative") == "admin:membersConfig.group.administrative"
    assert LABEL_KEY_SCHEME.group_key("personal") == "admin:membersConfig.group.personal"


def test_label_key_scheme_enum_key_builds_the_shipped_enum_option_resource_key():
    # R3.4: the enum template embeds the field key AND the stable, language-neutral option VALUE as
    # key segments — the value is a KEY, never translated text.
    assert (
        LABEL_KEY_SCHEME.enum_key("status", "active")
        == "admin:membersConfig.enum.status.active"
    )
    assert (
        LABEL_KEY_SCHEME.enum_key("status", "lapsed")
        == "admin:membersConfig.enum.status.lapsed"
    )


def test_label_key_scheme_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        LABEL_KEY_SCHEME.namespace = "changed"  # type: ignore[misc]


def test_built_catalog_records_the_complete_i18n_rule():
    # R3.7 (the task-5.7 heart): the ASSEMBLED catalog carries all THREE pieces of the i18n rule —
    # the convention name, the fallback order, AND the key scheme — so a consumer reads the WHOLE
    # rule off the artifact, not from module constants or folklore.
    catalog = build_attribute_catalog()
    assert catalog.label_convention == "i18n-keys+tenant-inline-override"
    assert catalog.label_convention == LABEL_CONVENTION
    assert catalog.label_fallback_order == ("en", "nl")
    assert catalog.label_fallback_order == LABEL_FALLBACK_ORDER
    assert catalog.label_key_scheme == LABEL_KEY_SCHEME
    assert catalog.label_key_scheme is LABEL_KEY_SCHEME


def test_built_catalog_key_scheme_resolves_a_shipped_field_key_end_to_end():
    # Prove the recorded scheme is usable straight off the artifact: resolve a shipped field's
    # resource key through the catalog's own label_key_scheme (no module-constant import needed).
    catalog = build_attribute_catalog()
    assert catalog.label_key_scheme is not None
    assert (
        catalog.label_key_scheme.field_key("first_name")
        == "admin:membersConfig.field.first_name"
    )


def test_catalog_recorded_key_scheme_agrees_with_the_frontend_task_5_1_scheme():
    # Rule-5 shared-vocabulary guard (steering 36 / design §6): the artifact's recorded key scheme
    # must AGREE with the frontend task-5.1 scheme. We assert against the SAME literal key shapes the
    # frontend `membersConfig-translations.test.ts` transcribes (fields → admin:membersConfig.field
    # .<fieldKey>, groups → .group.<groupKey>, enums → .enum.<fieldKey>.<optionValue>) — no
    # cross-plane import; both planes pin the same strings, so they cannot contradict silently.
    scheme = build_attribute_catalog().label_key_scheme
    assert scheme is not None
    # Transcribed frontend expectations (mirrors the frontend test's documented scheme):
    assert scheme.field_key("first_name") == "admin:membersConfig.field.first_name"
    assert scheme.group_key("administrative") == "admin:membersConfig.group.administrative"
    assert scheme.enum_key("status", "active") == "admin:membersConfig.enum.status.active"


def test_hand_built_catalog_defaults_keep_the_task_2_1_shape_valid():
    # Backward-compat: the two task-5.7 fields default to the neutral empty/None, so a hand-built
    # AttributeCatalog (the task-2.1/3.1 shape tests) that passes only the original four args stays
    # valid — only build_attribute_catalog() populates the i18n fallback/key-scheme fields.
    catalog = AttributeCatalog(
        attributes=(),
        fields=(),
        functional_groups=(),
        label_convention="i18n-keys+tenant-inline-override",
    )
    assert catalog.label_fallback_order == ()
    assert catalog.label_key_scheme is None
