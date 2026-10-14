"""
Editor-schema ⇄ catalog conformance (Flask/MySQL plane).

Validates: Requirements R7.2, R7.3

Phase 1 — Catalog Backbone, task 6.1. This is the Flask-plane half of the
steering-`36` rule-5 "guard a shared vocabulary with a test" pattern (design §6):
the Flask authoring editor's field-def schema (``backend/src/config/members_parameters.json``)
and the SAM-domain attribute catalog (``sam/members/domain/attribute_catalog.ATTRIBUTE_VOCABULARY``)
must agree on WHICH attributes a tenant may author — but the two planes are
separately packaged and MUST NOT import each other (steering 30/31/36). So, exactly
like ``services/members_config_validation.py`` transcribes the SAM field-key set,
and like the frontend ``membersConfig-translations.test.ts`` transcribes the shipped
label vocabulary, this test:

  1. READS + parses ``members_parameters.json`` (the live editor schema), and
  2. TRANSCRIBES — does NOT import — the catalog's TENANT-AUTHORABLE attribute keys
     (the ``AttributeSpec.key``s where ``tenant_authorable=True``), and
  3. ASSERTS the editor's field-def ATTRIBUTE keys ⊆ the authorable catalog set
     (R7.3), so the editor can never expose an attribute the catalog does not
     sanction as tenant-authorable (R7.2 drift guard).

The transcribed constant below MUST stay in lock-step with
``sam/members/domain/attribute_catalog.ATTRIBUTE_VOCABULARY``: if a vocabulary entry
flips its ``tenant_authorable`` flag or a new authorable attribute is added, update
``AUTHORABLE_CATALOG_ATTRIBUTES`` here IN THE SAME CHANGE (Change-With-Tests
contract, steering 30/36). A mismatch fails this test rather than drifting silently.

Pure Flask-plane test: it reads JSON and compares transcribed sets — no DB, no AWS,
no cross-plane import.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locally-transcribed view of the catalog's TENANT-AUTHORABLE attribute keys.
#
# Mirrors sam/members/domain/attribute_catalog.ATTRIBUTE_VOCABULARY — do NOT
# import sam.* (the Flask plane cannot import the SAM package; steering 30/31/36).
# Keep in lock-step with ATTRIBUTE_VOCABULARY: an attribute is listed here iff its
# AttributeSpec declares tenant_authorable=True.
#
# As of Phase-1 task 2.2, the authorable attributes are:
#   type, required, label, visible, order, functional_group, choices, options,
#   show_when, member_number_format, scope_binding, alias
# The NON-authorable (platform-fixed / identity) attributes are deliberately
# excluded: `key` (field identity, never tenant-authored) and `calculated_from`
# (a read-only, platform-owned output attribute).
# ---------------------------------------------------------------------------
AUTHORABLE_CATALOG_ATTRIBUTES: frozenset[str] = frozenset(
    {
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
        "scope_binding",
        "alias",
    }
)

# ---------------------------------------------------------------------------
# Editor-key → catalog-attribute mapping.
#
# The editor schema speaks per-locale, flat label inputs (label_en / label_nl)
# and a structural identity `key`; the catalog speaks a single i18n `label`
# attribute and treats `key` as identity (NOT an authorable attribute). This map
# translates each editor field-def attribute key to the catalog attribute it
# corresponds to, so the subset comparison is apples-to-apples:
#
#   label_en, label_nl → label      (the per-locale fold INPUTS for the single
#                                     `label` authorable attribute — task 5.4's
#                                     fold_field_overlay_labels assembles the two
#                                     editor inputs into the stored {nl,en,…} dict)
#   type              → type
#   required          → required
#   visible           → visible
#   order             → order
#   functional_group  → functional_group
#   choices           → choices
#   scope             → scope_binding (Phase 3 step 9, task 2.1 — the per-field
#                                     `scope` object attribute is the WIRING of
#                                     the already-declared `scope_binding` catalog
#                                     AttributeSpec; mapped by the renamed key,
#                                     mirroring the dataclass→vocabulary map in
#                                     sam/tests/test_attribute_catalog.py)
#
# `key` is handled separately below: it is the field/group IDENTITY the tenant
# names (the map key under which a field def is stored), NOT an attribute the
# catalog governs as tenant-authorable (in the vocabulary `key` is
# tenant_authorable=False — identity). It is therefore EXCLUDED from the
# "authorable attribute" comparison with that documented rationale, rather than
# treated as a conformance violation.
# ---------------------------------------------------------------------------
EDITOR_KEY_TO_CATALOG_ATTRIBUTE: dict[str, str] = {
    "label_en": "label",
    "label_nl": "label",
    "type": "type",
    "required": "required",
    "visible": "visible",
    "order": "order",
    "functional_group": "functional_group",
    "choices": "choices",
    # Phase 3 step 9 (task 2.1): the per-field `scope` object attribute is the WIRING of the
    # already-declared `scope_binding` catalog AttributeSpec — mapped by the renamed key
    # `scope` → `scope_binding` (mirroring the dataclass→vocabulary map in
    # sam/tests/test_attribute_catalog.py), so the new editor attribute is CLASSIFIED
    # rather than surfacing as an un-sanctioned drift.
    "scope": "scope_binding",
}

#: Editor keys that are structural IDENTITY, not a tenant-authorable field
#: attribute — excluded from the subset comparison with documented rationale.
#: `key` names the field/group (its map key / identity); it maps to the catalog's
#: `key` attribute which is tenant_authorable=False (identity, never authored as a
#: settable attribute).
EDITOR_IDENTITY_KEYS: frozenset[str] = frozenset({"key"})


# ---------------------------------------------------------------------------
# Load the live editor schema.
# ---------------------------------------------------------------------------


def _members_parameters_path() -> Path:
    """Absolute path to the live editor schema JSON (src/config/members_parameters.json)."""
    # tests/unit/<this file> → backend/ → src/config/members_parameters.json
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "src" / "config" / "members_parameters.json"


def _load_editor_schema() -> list[dict]:
    """Read + parse the editor schema JSON (the Flask authoring field-def source)."""
    with _members_parameters_path().open(encoding="utf-8") as fh:
        return json.load(fh)


def _field_overlay_param(schema: list[dict]) -> dict:
    """The members.field_overlay parameter definition — the member field-config editor."""
    for param in schema:
        if isinstance(param, dict) and param.get("key") == "field_overlay":
            return param
    raise AssertionError("members_parameters.json has no 'field_overlay' parameter")


def _child_by_key(parent: dict, key: str) -> dict:
    """Return the object_fields child of `parent` whose key == `key`."""
    for child in parent.get("object_fields", []):
        if isinstance(child, dict) and child.get("key") == key:
            return child
    raise AssertionError(f"field_overlay has no object_fields child {key!r}")


def _entry_attribute_keys(entries: list[dict]) -> set[str]:
    """Collect each per-attribute editor key from a list of field-def/object entries."""
    keys: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("key"), str):
            keys.add(entry["key"])
    return keys


def _editor_field_def_attribute_keys() -> set[str]:
    """The union of per-attribute editor keys the field_overlay editor declares.

    Across the three field-def surfaces of members.field_overlay:
      - functional_groups.object_fields  (the display-group catalog entries)
      - fields.field_def                 (added variable field definitions)
      - fixed_overrides.field_def        (presentation overrides of fixed/calc fields)

    Each entry's `key` is a per-attribute editor key (e.g. type, label_en, required,
    functional_group, choices, order, visible, key). The `analytics` block under
    field_overlay is NOT a field-def surface (it is tenant analytics semantics, not
    per-field attributes) and is intentionally excluded.
    """
    overlay = _field_overlay_param(_load_editor_schema())

    functional_groups = _child_by_key(overlay, "functional_groups")
    fields = _child_by_key(overlay, "fields")
    fixed_overrides = _child_by_key(overlay, "fixed_overrides")

    keys: set[str] = set()
    keys |= _entry_attribute_keys(functional_groups.get("object_fields", []))
    keys |= _entry_attribute_keys(fields.get("field_def", []))
    keys |= _entry_attribute_keys(fixed_overrides.get("field_def", []))
    return keys


def _mapped_authorable_editor_attributes() -> tuple[set[str], set[str]]:
    """Return (mapped_catalog_attrs, unmapped_editor_keys) for the editor field-defs.

    Each editor attribute key is translated to its catalog attribute via
    EDITOR_KEY_TO_CATALOG_ATTRIBUTE; identity keys (EDITOR_IDENTITY_KEYS) are dropped
    with documented rationale. Any editor key that is neither mapped nor a known
    identity key is returned as `unmapped` so the test fails LOUDLY (a new editor
    attribute with no catalog correspondence must be deliberately classified, never
    silently ignored).
    """
    editor_keys = _editor_field_def_attribute_keys()
    mapped: set[str] = set()
    unmapped: set[str] = set()
    for key in editor_keys:
        if key in EDITOR_IDENTITY_KEYS:
            continue
        catalog_attr = EDITOR_KEY_TO_CATALOG_ATTRIBUTE.get(key)
        if catalog_attr is None:
            unmapped.add(key)
        else:
            mapped.add(catalog_attr)
    return mapped, unmapped


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_editor_field_def_keys_every_key_is_classified_mapped_or_identity():
    """Every editor field-def attribute key is a known catalog attribute or identity.

    Guards the mapping itself: a new per-attribute editor key that is neither mapped
    to a catalog attribute nor a documented identity key must be surfaced (classified
    deliberately), not silently dropped from the subset comparison.
    """
    _mapped, unmapped = _mapped_authorable_editor_attributes()
    assert not unmapped, (
        "editor field-def attribute key(s) with no catalog mapping and not a known "
        f"identity key: {sorted(unmapped)} — classify each (map to a catalog "
        "attribute or add to EDITOR_IDENTITY_KEYS with a rationale)"
    )


def test_editor_field_def_attributes_subset_of_authorable_catalog_attributes():
    """Every tenant-settable editor attribute ⊆ the catalog's tenant_authorable set (R7.3).

    The core conformance claim: the editor can never expose an attribute the catalog
    does not sanction as tenant-authorable (R7.2). Fails with the offending editor-
    mapped catalog attribute(s) named.
    """
    mapped, _unmapped = _mapped_authorable_editor_attributes()
    offending = mapped - AUTHORABLE_CATALOG_ATTRIBUTES
    assert not offending, (
        "editor exposes attribute(s) the catalog does NOT mark tenant_authorable "
        f"(conformance violation): {sorted(offending)} — the editor field-def must "
        "only surface attributes with AttributeSpec.tenant_authorable=True"
    )


def test_editor_field_def_contains_expected_core_attributes():
    """Sanity: the editor actually surfaces the expected core authorable attributes.

    A guard against a vacuous pass (e.g. the schema parse silently yielding an empty
    set would make the subset assertion trivially true). Confirms the editor really
    declares the known tenant-authorable attributes.
    """
    mapped, _unmapped = _mapped_authorable_editor_attributes()
    expected_core = {
        "label",
        "type",
        "required",
        "visible",
        "order",
        "functional_group",
        "choices",
    }
    missing = expected_core - mapped
    assert not missing, (
        f"editor field-def is missing expected authorable attribute(s): {sorted(missing)}"
    )


def test_authorable_catalog_attributes_are_nonempty_and_well_formed():
    """The transcribed authorable set is a non-empty frozenset of plain string keys.

    Cheap guard that the transcription constant itself did not degrade to empty
    (which would make the subset check vacuously pass).
    """
    assert isinstance(AUTHORABLE_CATALOG_ATTRIBUTES, frozenset)
    assert AUTHORABLE_CATALOG_ATTRIBUTES, "authorable catalog attribute set is empty"
    assert all(
        isinstance(k, str) and k for k in AUTHORABLE_CATALOG_ATTRIBUTES
    )
