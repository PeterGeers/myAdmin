"""
Member-data invariance across every Phase 2 step — Property 3, Phase 2 task 7.2.

**Property 3: Member data is invariant across every Phase 2 step.**
*For any* tenant's member records, applying any Phase 2 step — the config-default re-home
(``default_page_size``), the view-context surface deletion (what the resolve/field-config
surfacing change touched), and the one-time config-row key migration
(``overrides -> fixed_overrides``) — leaves the member records in ``sam-members`` BYTE-FOR-BYTE
unchanged. Phase 2 touches only the CONFIG/PARAMETER surface, never MEMBER RECORDS.

**Validates: Requirements 8.1, 8.3**

What this property pins (the cross-step member-record invariant at the resolve/surface layer):

- The read/resolve/surface path Phase 2 CHANGED is ``FieldResolver.resolve`` ⊕ the
  ``MembershipService.get_field_config`` surfacing (which dropped the inert ``view_contexts``
  array and re-homed pagination to the ``default_page_size`` scalar), plus the per-field
  surfacing predicate ``evaluate_show_when`` that READS member records. Running an arbitrary
  member record through that path must not mutate the record. We snapshot the record
  (``json.dumps`` with sorted keys) BEFORE, drive it through the affected path, and assert the
  post-serialization is byte-for-byte identical.
- The one-time config-row key migration (``rename_overrides_key``) is the ONLY data migration
  in Phase 2 (R8.2) and it rewrites the stored OVERLAY config JSON only. Its own
  data-preservation + idempotence property lives beside the migration (task 5.2,
  ``backend/tests/unit/test_migrate_overrides_to_fixed_overrides.py``). Property 3 here is the
  COMPLEMENTARY cross-step guarantee: feeding the migration a value that happens to look like a
  member record (or an overlay carrying member-shaped data) never touches the member bytes — the
  migration operates on OVERLAY keys, so a member record passed through it is returned unchanged.

Byte-for-byte is enforced by comparing ``json.dumps(record, sort_keys=True)`` taken before and
after — the exact "serialize before/after and compare" the task calls for. The member records
are generated arbitrarily (nested ``personal`` / ``membership`` / ``overlay`` storage groups
plus flattened top-level scalars — the shape ``_member_value`` searches) so the invariant is
shown universal, not fixture-specific.

DynamoDB / MySQL are never touched: the resolve/surface path runs over an in-memory
``StaticOverlayProvider`` + the read-only fake catalog repo, and the migration function
(``rename_overrides_key``) is the PURE, DB-free transform imported directly.
"""

from __future__ import annotations

import json
import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root (so `sam.members` resolves) + backend/src/migrations (so the pure migration
# transform resolves) on sys.path — mirrors the sibling SAM property tests
# (test_pagination_precedence_props.py adds backend/src the same way).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_MIGRATIONS = os.path.join(_REPO_ROOT, "backend", "src", "migrations")
if _MIGRATIONS not in sys.path:
    sys.path.insert(0, _MIGRATIONS)

from sam.members.domain.default_page_size import StaticDefaultPageSizeProvider
from sam.members.domain.field_resolver import (
    FieldResolver,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
    evaluate_show_when,
)
from sam.members.domain.field_resolver import _RESERVED_KEYS
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.membership_service import MembershipService

# Reuse the field-config test's in-memory fake catalog repo (read-only catalog surface) — the
# same seam the resolved-field-surface + field-config tests use, so no AWS/boto3.
from sam.tests.test_field_config_endpoint import FakeCatalogRepository

# The PURE, DB-free config-row key migration transform (the ONLY Phase 2 data migration, R8.2).
from migrate_overrides_to_fixed_overrides import rename_overrides_key


# ── Generators ──────────────────────────────────────────────────────────────────────────

_TENANT_ID = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=24
).filter(lambda s: s.strip() != "")

# JSON-serializable scalar values a member field might carry (byte-for-byte comparison via
# json.dumps requires JSON-native leaves — the real member records are JSON documents).
_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.text(max_size=24),
)

_FIELD_KEYS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12
).filter(lambda s: s.strip() != "")

_GROUP_MAP = st.dictionaries(_FIELD_KEYS, _SCALARS, max_size=5)


@st.composite
def _member_record(draw) -> dict:
    """An arbitrary member record: nested storage groups + flattened top-level scalars.

    Mirrors the shape ``_member_value`` searches (``personal`` / ``membership`` / ``overlay``
    buckets plus bare top-level keys) and the flattened row shape the frontend sends. Always
    carries a non-empty ``member_id`` (the real repo invariant) so the record is realistic.
    """
    record: dict = {
        "member_id": draw(st.uuids().map(str)),
        "personal": draw(_GROUP_MAP),
        "membership": draw(_GROUP_MAP),
        "overlay": draw(_GROUP_MAP),
    }
    # A membership_type (the common show_when controlling key) so the surfacing predicate has a
    # real value to read on some records.
    if draw(st.booleans()):
        record["membership"]["membership_type"] = draw(
            st.sampled_from(["gewoon", "motor", "erelid", "family"])
        )
    # Some flattened top-level scalars too (the other shape _member_value falls back to).
    for extra in draw(st.lists(_FIELD_KEYS, max_size=4, unique=True)):
        if extra not in record:
            record[extra] = draw(_SCALARS)
    return record


_OVERLAY_FIELD_NAME = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12
).filter(lambda s: s.strip() != "" and s not in _RESERVED_KEYS)


@st.composite
def _arbitrary_overlay(draw) -> TenantOverlay:
    """A resolver-safe tenant overlay: 0..3 plain STRING overlay fields in the base group.

    Kept simple (the property is about MEMBER-RECORD invariance, not overlay richness); plain
    string fields in the ``membership`` group always validate, so resolution never raises.
    """
    names = draw(st.lists(_OVERLAY_FIELD_NAME, min_size=0, max_size=3, unique=True))
    fields = {
        name: OverlayField(
            key=name,
            type=FieldType.STRING,
            required=False,
            label={"nl": name, "en": name},
            functional_group="membership",
            order=100 + i,
        )
        for i, name in enumerate(names)
    }
    return TenantOverlay(fields=fields)


def _snapshot(record: dict) -> str:
    """Byte-for-byte serialization: canonical JSON (sorted keys) of the member record."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False)


# ── Property 3 — member data is invariant across every Phase 2 step ───────────────────────


@settings(max_examples=150)
@given(
    tenant_id=_TENANT_ID,
    overlay=_arbitrary_overlay(),
    record=_member_record(),
    default_page_size=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
)
def test_property_member_data_invariant_across_phase2_steps(
    tenant_id, overlay, record, default_page_size
):
    """Property 3: a member record survives every Phase 2 step byte-for-byte unchanged.

    Snapshot the record, drive it through (1) the config-default re-home + the view-context
    surface deletion (the ``get_field_config`` surfacing Phase 2 changed) and the field-config
    read/resolve path, (2) the per-field ``show_when`` surfacing predicate that READS the record,
    and (3) the one-time config-row key migration — then assert the serialized record is
    identical before and after.

    **Validates: Requirements 8.1, 8.3**
    """
    before = _snapshot(record)

    overlay_provider = StaticOverlayProvider({tenant_id: overlay})

    # ── Step: the config-default re-home + view-context surface deletion ──────────────────
    # get_field_config now surfaces `default_page_size` and NO `view_contexts` (steps a/c). It
    # resolves config, not member records — but we drive it on the SAME tenant whose records we
    # snapshot to pin the cross-step boundary: surfacing the (changed) field-config touches no
    # member bytes.
    service = MembershipService(
        FakeCatalogRepository(),
        overlay_provider=overlay_provider,
        default_page_size_provider=StaticDefaultPageSizeProvider(
            {tenant_id: default_page_size} if default_page_size is not None else {}
        ),
    )
    config = service.get_field_config(tenant_id)
    # Guard the Phase 2 surface shape so this test fails loudly if the surface regresses: the
    # inert array is gone, pagination is re-homed. (The MEMBER-record invariant is the point;
    # this just pins we are exercising the POST-Phase-2 surface.)
    assert "view_contexts" not in config
    assert "default_page_size" in config
    assert _snapshot(record) == before  # the record is untouched by the surfacing read

    # ── Step: the per-field surfacing predicate reads the member record ───────────────────
    # evaluate_show_when / the resolve path READ the record (dotted + bare keys across the
    # storage groups). Reading must never mutate. Drive every resolved field's show_when and
    # a spread of controlling keys over the record.
    resolved = FieldResolver(overlay_provider).resolve(tenant_id)
    for field in resolved.fields:
        evaluate_show_when(field.show_when, record)
    for controlling in ("membership_type", "membership.membership_type", "personal.gender"):
        evaluate_show_when({controlling: ["motor"]}, record)
    assert _snapshot(record) == before  # the record is untouched by the surfacing reads

    # ── Step: the one-time config-row key migration ───────────────────────────────────────
    # The ONLY Phase 2 data migration (R8.2) rewrites OVERLAY config keys. A member record is
    # not an overlay with a top-level `overrides` key, so the pure transform returns it
    # unchanged — proving the migration never touches member bytes even if mis-fed one.
    migrated = rename_overrides_key(record)
    assert _snapshot(migrated) == before
    assert _snapshot(record) == before  # the input record itself is never mutated in place

    # ── Final: byte-for-byte invariance across the whole Phase 2 sequence ─────────────────
    assert _snapshot(record) == before
