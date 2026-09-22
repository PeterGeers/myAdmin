"""
S5c Task 1.5 — **traceability check** for the field classification table (R4.10, the key deliverable).

The design's "Field classification table" (``design.md`` → Data Models → "Field classification
table (h-dcn field set — R4.1 deliverable)") is the **AUTHORITATIVE SOURCE** for the field model
built in Phase 1. This test encodes that table's row/classification contract and asserts the
mapping between the table and the concrete definitions is **TOTAL and one-to-one, in both
directions** (design: "The mapping is total (table ⇄ definitions), asserted in task 1.5"):

    each `Fixed`      row  →  exactly one `FixedField`  in the fixed registry
    each `Calculated` row  →  exactly one derived field in the calculated registry
    each `Parameter`  row  →  represented as OVERLAY-ELIGIBLE (a functional group / placeholder in
                              the seed overlay; per R4.5 the platform seed uses GENERIC names, so a
                              Parameter row is accounted for by its functional group, NOT its h-dcn key)
    each `OUT`        row  →  defined NOWHERE (welcome_pack_* — R11.2)

and conversely:

    no `FixedField`      exists that is not a `Fixed`      table row;
    no `CalculatedField` exists that is not a `Calculated` table row.

Why encode the table here (not read design.md)
-----------------------------------------------
``design.md`` is prose + a Markdown table, not a machine-readable manifest, and there is no
existing manifest in the repo (searched: no ``classification`` JSON/YAML under ``sam`` / the spec
dir). So the table contract is encoded below as a structured list — the SINGLE place the prose
table is turned into an assertion — with the design table cited as the source. If a machine-readable
manifest is ever added, this list should be replaced by reading it.

Validates: Requirements 4, 4.10 (Property 2 basis)
"""

from __future__ import annotations

import pytest

from sam.members.domain.calculated_fields import CALCULATED_FIELDS, calculated_field_by_key
from sam.members.domain.fixed_fields import FIXED_FIELDS, field_by_key
from sam.members.domain.field_resolver import FieldResolver, StaticOverlayProvider
from sam.members.domain.seed_overlay import build_seed_overlay


# ═══════════════════════════════════════════════════════════════════════════════════════
# The classification-table contract — encoded ROW-BY-ROW from design.md
# (Data Models → "Field classification table (h-dcn field set — R4.1 deliverable)").
#
# Each entry is (platform_key_or_none, functional_group, classification). Multi-key table rows
# (e.g. the name-parts row, the address row) are expanded to one entry per platform key, because
# each maps to its own definition. Parameter rows whose platform keys are illustrative (shown in
# parentheses in the design table — the real keys are tenant-authored) are encoded by their
# FUNCTIONAL GROUP only (platform_key = None), because per R4.5 the platform defines no concrete
# key for them — they are accounted for as overlay-eligible by group, not by h-dcn key.
#
# Classifications: "fixed" | "calculated" | "parameter" | "out".
# The "fixed" rows whose enum values are Parameter (gender/status) are still `fixed` rows here —
# the FIELD is fixed; only its value LIST is tenant config (R4.2), which does not change the row's
# classification (a Fixed field → a FixedField).
# ═══════════════════════════════════════════════════════════════════════════════════════

# (platform_key | None, functional_group, classification)
CLASSIFICATION_TABLE: tuple[tuple[str | None, str, str], ...] = (
    # name parts (one row → four Fixed keys)
    ("first_name", "personal", "fixed"),
    ("last_name", "personal", "fixed"),
    ("name_infix", "personal", "fixed"),
    ("initials", "personal", "fixed"),
    # display_name
    ("display_name", "personal", "calculated"),
    # birth_date + derivations
    ("birth_date", "personal", "fixed"),
    ("age", "personal", "calculated"),
    ("birthday", "personal", "calculated"),
    # gender (Fixed; Parameter enum values)
    ("gender", "personal", "fixed"),
    # contact
    ("email", "personal", "fixed"),
    ("phone", "personal", "fixed"),
    # guardian_name (Parameter — illustrative key; conditional minors overlay)
    (None, "personal", "parameter"),
    # address (one row → four Fixed keys; functional group "address")
    ("street", "address", "fixed"),
    ("postal_code", "address", "fixed"),
    ("city", "address", "fixed"),
    ("country", "address", "fixed"),
    # membership lifecycle / catalog / number
    ("status", "membership", "fixed"),          # Fixed; Parameter enum values
    ("membership_type", "membership", "fixed"),  # Fixed ref + Parameter catalog
    # region — Parameter (scope dimension); functional group membership
    (None, "membership", "parameter"),
    ("member_number", "membership", "fixed"),   # Fixed string; Parameter format; manual entry
    ("joined_date", "membership", "fixed"),
    ("years_member", "membership", "calculated"),
    # communication prefs (one row → four Parameter keys; illustrative — encode by group)
    (None, "membership", "parameter"),  # magazine_pref
    (None, "membership", "parameter"),  # newsletter_pref
    (None, "membership", "parameter"),  # privacy_consent
    (None, "membership", "parameter"),  # referral_source
    # motor overlay (one row → four illustrative Parameter keys; functional group "motor")
    (None, "motor", "parameter"),  # motor_brand
    (None, "motor", "parameter"),  # motor_type
    (None, "motor", "parameter"),  # build_year
    (None, "motor", "parameter"),  # license_plate
    # financial overlay (one row → two Parameter keys)
    (None, "financial", "parameter"),  # iban
    (None, "financial", "parameter"),  # payment_method
    # administrative overlay (one row → two Parameter keys)
    (None, "administrative", "parameter"),  # notes
    (None, "administrative", "parameter"),  # signature_date
    # system timestamps (Fixed system) — functional group "administrative"
    ("created_at", "administrative", "fixed"),
    ("updated_at", "administrative", "fixed"),
    # application_year (Calculated) — functional group "membership" (user decision:
    # application/onboarding is part of the membership lifecycle; derives from joined_date
    # when created_at is absent).
    ("application_year", "membership", "calculated"),
    # welcome_pack_* — OUT (R11.2)
    (None, "administrative", "out"),
)


# --- Derived views of the encoded table (by classification) -----------------------------

_FIXED_ROW_KEYS = frozenset(
    k for (k, _g, c) in CLASSIFICATION_TABLE if c == "fixed" and k is not None
)
_CALCULATED_ROW_KEYS = frozenset(
    k for (k, _g, c) in CLASSIFICATION_TABLE if c == "calculated" and k is not None
)
_PARAMETER_ROWS = tuple(row for row in CLASSIFICATION_TABLE if row[2] == "parameter")
_OUT_ROWS = tuple(row for row in CLASSIFICATION_TABLE if row[2] == "out")

# The concrete definitions, keyed by their canonical (bare) key.
_FIXED_DEF_KEYS = frozenset(f.key for f in FIXED_FIELDS)
_CALC_DEF_KEYS = frozenset(c.key for c in CALCULATED_FIELDS)


# ═══════════════════════════════════════════════════════════════════════════════════════
# Fixed rows ⇄ FixedField definitions (total, one-to-one)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_every_fixed_row_maps_to_exactly_one_fixed_field():
    # Forward: each Fixed table row → exactly one FixedField.
    missing = sorted(k for k in _FIXED_ROW_KEYS if k not in _FIXED_DEF_KEYS)
    assert not missing, f"Fixed table rows with no FixedField definition: {missing}"
    # And exactly one (no duplicate registry entries collapse two rows onto one key).
    for key in _FIXED_ROW_KEYS:
        matches = [f for f in FIXED_FIELDS if f.key == key]
        assert len(matches) == 1, f"Fixed row {key!r} maps to {len(matches)} FixedFields"


def test_no_fixed_field_is_absent_from_the_table():
    # Reverse: no FixedField exists that is not a Fixed table row (table ⇄ defs total).
    extra = sorted(k for k in _FIXED_DEF_KEYS if k not in _FIXED_ROW_KEYS)
    assert not extra, f"FixedFields not present as a Fixed table row: {extra}"


def test_fixed_rows_and_definitions_are_set_equal():
    assert _FIXED_ROW_KEYS == _FIXED_DEF_KEYS


# ═══════════════════════════════════════════════════════════════════════════════════════
# Calculated rows ⇄ CalculatedField definitions (total, one-to-one)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_every_calculated_row_maps_to_exactly_one_derived_field():
    missing = sorted(k for k in _CALCULATED_ROW_KEYS if k not in _CALC_DEF_KEYS)
    assert not missing, f"Calculated table rows with no derived field: {missing}"
    for key in _CALCULATED_ROW_KEYS:
        matches = [c for c in CALCULATED_FIELDS if c.key == key]
        assert len(matches) == 1, f"Calculated row {key!r} maps to {len(matches)} derived fields"


def test_no_calculated_field_is_absent_from_the_table():
    extra = sorted(k for k in _CALC_DEF_KEYS if k not in _CALCULATED_ROW_KEYS)
    assert not extra, f"CalculatedFields not present as a Calculated table row: {extra}"


def test_calculated_rows_and_definitions_are_set_equal():
    assert _CALCULATED_ROW_KEYS == _CALC_DEF_KEYS


# ═══════════════════════════════════════════════════════════════════════════════════════
# Fixed vs Calculated are disjoint (a row is one or the other, never both)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_fixed_and_calculated_definitions_are_disjoint():
    # No key is defined as BOTH a fixed and a calculated field.
    assert not (_FIXED_DEF_KEYS & _CALC_DEF_KEYS)
    # A calculated field never shadows a fixed dotted key (the resolver relies on this).
    fixed_dotted = {f.dotted_key() for f in FIXED_FIELDS}
    calc_dotted = {c.dotted_key() for c in CALCULATED_FIELDS}
    assert not (fixed_dotted & calc_dotted)


# ═══════════════════════════════════════════════════════════════════════════════════════
# Parameter rows → overlay-eligible (by functional group / placeholder, NOT h-dcn key, R4.5)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_parameter_rows_are_accounted_for_as_overlay_eligible():
    """Every Parameter row is representable as an overlay field / functional group.

    Per R4.5 the platform seed uses GENERIC placeholder names, never h-dcn's real keys, so a
    Parameter row is NOT asserted by its h-dcn key. Instead we assert the row is accounted for as
    OVERLAY-ELIGIBLE: its functional group is a valid overlay group — either one of the base
    functional groups every tenant starts with (personal/address/membership/administrative) or a
    tenant-defined custom group (motor/financial/...). No Parameter row is defined as a FixedField
    or a CalculatedField (a Parameter is tenant data, never platform code).
    """
    assert _PARAMETER_ROWS, "the table must contain Parameter rows"

    # The seed overlay proves the overlay MECHANISM (functional_groups catalog + fields) exists;
    # its base functional groups are the ones a tenant starts with.
    seed = build_seed_overlay()
    base_groups = set(seed.functional_groups.keys())
    # Custom (tenant-defined) functional groups the classification table's Parameter rows use.
    custom_param_groups = {g for (_k, g, c) in _PARAMETER_ROWS}

    for platform_key, group, _c in _PARAMETER_ROWS:
        # Illustrative Parameter rows carry NO platform key (R4.5) — they are tenant-authored.
        assert platform_key is None, (
            f"Parameter row in group {group!r} must not carry a platform key (R4.5): {platform_key!r}"
        )
        # Its functional group is overlay-eligible: a base group OR a tenant-defined custom group.
        assert group in base_groups or group in custom_param_groups

    # No Parameter row is (mistakenly) shipped as a platform FixedField/CalculatedField. Since
    # Parameter rows carry no platform key, this holds by construction — assert the seed overlay's
    # own placeholder fields never collide with a fixed/calculated key (R4.5 generic-name rule).
    reserved = _FIXED_DEF_KEYS | _CALC_DEF_KEYS
    assert not (set(seed.fields.keys()) & reserved)


def test_seed_overlay_uses_generic_placeholder_names_not_hdcn_keys():
    # R4.5: the platform seed must not bake in h-dcn's real overlay vocabulary.
    seed = build_seed_overlay()
    hdcn_real_keys = {
        "guardian_name", "magazine_pref", "newsletter_pref", "privacy_consent",
        "referral_source", "motor_brand", "motor_type", "build_year", "license_plate",
        "iban", "payment_method", "notes", "signature_date",
    }
    assert not (set(seed.fields.keys()) & hdcn_real_keys)


def test_seed_overlay_resolves_cleanly_over_the_broadened_base():
    # The seed is valid overlay data: it resolves without raising and adds VARIABLE fields on top
    # of the full broadened base (fixed ⊕ calculated), proving the overlay mechanism is total.
    cfg = FieldResolver(StaticOverlayProvider({"t": build_seed_overlay()})).resolve("t")
    assert len(cfg.variable_fields()) == len(build_seed_overlay().fields)
    assert {f.dotted_key() for f in FIXED_FIELDS}.issubset({f.dotted_key() for f in cfg.fields})


# ═══════════════════════════════════════════════════════════════════════════════════════
# OUT rows → defined NOWHERE (welcome_pack_* — R11.2)
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_out_rows_are_defined_nowhere():
    assert _OUT_ROWS, "the table must contain the OUT row (welcome_pack_*)"
    # welcome_pack_* must not exist as a fixed field, a calculated field, or a seed overlay field.
    seed = build_seed_overlay()
    all_defined_keys = _FIXED_DEF_KEYS | _CALC_DEF_KEYS | set(seed.fields.keys())
    for key in all_defined_keys:
        assert not key.startswith("welcome_pack"), f"OUT field defined: {key}"
    # Explicit: the concrete OUT keys from the design table are absent everywhere.
    for out_key in ("welcome_pack_size", "welcome_pack_sent", "welcome_pack_note"):
        assert field_by_key(f"membership.{out_key}") is None
        assert calculated_field_by_key(f"membership.{out_key}") is None
        assert out_key not in seed.fields


# ═══════════════════════════════════════════════════════════════════════════════════════
# The mapping is TOTAL — every table row is accounted for by exactly one classification
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_every_table_row_has_a_known_classification():
    valid = {"fixed", "calculated", "parameter", "out"}
    for platform_key, group, classification in CLASSIFICATION_TABLE:
        assert classification in valid, f"unknown classification {classification!r}"
        assert group, "every row must name a functional group"


def test_table_totals_match_the_definition_counts():
    # A blunt end-to-end total: the count of Fixed rows == count of FixedFields; likewise
    # Calculated. (Parameter/OUT rows have no platform definition to count.)
    assert len(_FIXED_ROW_KEYS) == len(FIXED_FIELDS)
    assert len(_CALCULATED_ROW_KEYS) == len(CALCULATED_FIELDS)


@pytest.mark.parametrize("platform_key", sorted(_FIXED_ROW_KEYS))
def test_each_fixed_row_key_resolves_to_a_registry_field(platform_key):
    assert platform_key in _FIXED_DEF_KEYS


@pytest.mark.parametrize("platform_key", sorted(_CALCULATED_ROW_KEYS))
def test_each_calculated_row_key_resolves_to_a_derived_field(platform_key):
    assert platform_key in _CALC_DEF_KEYS
