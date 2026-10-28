"""03a Property 2 — PRESERVATION baseline for the read-assembly seam (observation-first).

Spec `Members/03a - enum-vocab-roundtrip-and-no-silent-fallbacks`, task 2.

These are the PRESERVATION cases (design "Property 2", "Preservation Checking", bugfix R3.1–R3.3):
for an input where the bug condition does NOT hold, the fixed system must produce the SAME result
as the original. Per the observation-first methodology they were written by RUNNING the UNFIXED
seam (`MembershipService.get_field_config` / `get_public_field_config` — the one read-assembly
seam in `_membership_writes_fieldconfig.py`) and asserting the OBSERVED current outputs. They MUST
PASS on unfixed code — they capture the baseline the C1–C6 fix must preserve. They are NOT
hypothetical post-fix assertions.

What is pinned (all observed on UNFIXED code):

  * R3.1 — an `options`-authored selectable field already resolves to populated `options` and
    renders IDENTICALLY (same value order, same i18n labels) in the editor read (`get_field_config`)
    and the member-form read (`get_public_field_config`). This is the NON-bug path (editor and
    member form already agree), so the fix must leave it untouched.
  * R3.2 — `application_choices` (the public-form SUBSET) is a DIFFERENT concept and is unchanged:
    the editor read carries the authored subset verbatim, and the public read FILTERS `options`
    down to that subset (staff-only value excluded). Only the subset's vocabulary SOURCE is
    tightened by the fix; the subset projection itself is preserved.
  * R3.2 (reference) — `membership_type` resolves `options` from the live active catalog; that
    catalog feed is the non-bug reference path (design "not a bug (3)").
  * scope DISPLAY surface — the editor `scope` attribute is `{enabled, required_for}` with NO
    `values` sub-key (scope ACCESS state; the single-vocabulary rule). The fix touches only the
    DISPLAY vocabulary derivation, never this access-state surface.
  * R3.3 — spec-03 Change-Op guarantees via the one read path (the resolved-view contract: the
    editor read exposes the flat `fields` list keyed by bare `key`, never a raw-storage key).

NB the scope-backed field's `FieldScope.values == ()` divergence (observed here on unfixed code)
is a BUG condition (`isBugCondition`: scope.values != [o.value for o in options]), NOT a
preservation case — it is deliberately NOT asserted as a baseline to keep; the C5/F7 fix changes
it. These tests pin only the aspects that are already correct and must stay correct.

Validates: Requirements 3.1, 3.2, 3.3
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldScope,
    FunctionalGroup,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption, FieldType
from sam.members.domain.membership_service import MembershipService

# Reuse the field-config endpoint test's in-memory fake catalog repo (no boto3).
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

_TENANT = "preserve-tenant"


# ── Fixtures / overlay builders ────────────────────────────────────────────────────────


@pytest.fixture()
def catalog_repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    r.add_type(_TENANT, _entry(_TENANT, "gewoon", label={"nl": "Gewoon", "en": "Ordinary"}, order=10))
    r.add_type(_TENANT, _entry(_TENANT, "erelid", label={"nl": "Erelid", "en": "Honorary"}, order=20))
    return r


def _options_authored_overlay() -> TenantOverlay:
    """A tenant overlay with an `options`-authored, application-visible enum carrying an
    `application_choices` SUBSET, plus a scope-backed enum field with inline options.

    This is the NON-bug baseline: both fields already resolve to populated `options`.
    """
    return TenantOverlay(
        functional_groups={
            "membership": FunctionalGroup(
                key="membership", label={"nl": "Lid", "en": "Membership"}, order=4
            ),
        },
        fields={
            "referral_source": OverlayField(
                key="referral_source",
                type=FieldType.ENUM,
                required=False,
                label={"nl": "Bron", "en": "Source"},
                options=(
                    EnumOption(value="internet", label={"nl": "Internet", "en": "Internet"}),
                    EnumOption(value="facebook", label={"nl": "Facebook", "en": "Facebook"}),
                    EnumOption(value="staff_only", label={"nl": "Staf", "en": "Staff"}),
                ),
                functional_group="membership",
                order=50,
                application_visible=True,
                application_required=False,
                application_choices=("internet", "facebook"),
            ),
            "team": OverlayField(
                key="team",
                type=FieldType.ENUM,
                required=False,
                label={"nl": "Team", "en": "Team"},
                options=(
                    EnumOption(value="a", label={"nl": "A", "en": "A"}),
                    EnumOption(value="b", label={"nl": "B", "en": "B"}),
                ),
                functional_group="membership",
                order=60,
                scope=FieldScope(enabled=True, required_for=("Members_CRUD",)),
            ),
        },
    )


@pytest.fixture()
def service(catalog_repo) -> MembershipService:
    return MembershipService(
        catalog_repo,
        overlay_provider=StaticOverlayProvider({_TENANT: _options_authored_overlay()}),
    )


def _field(config: dict, key: str) -> dict:
    return next(f for f in config["fields"] if f["key"] == key)


# ── R3.1 — options-authored field renders identically in both reads ───────────────────


class TestOptionsAuthoredRendersIdenticallyInBothReads:
    def test_editor_read_carries_full_rich_options_in_order(self, service):
        # OBSERVED on unfixed code: the editor read surfaces the full authored vocabulary as rich
        # {value,label} options, in authored order, with both locales.
        editor = service.get_field_config(_TENANT)
        opts = _field(editor, "referral_source")["options"]
        assert opts == [
            {"value": "internet", "label": {"nl": "Internet", "en": "Internet"}},
            {"value": "facebook", "label": {"nl": "Facebook", "en": "Facebook"}},
            {"value": "staff_only", "label": {"nl": "Staf", "en": "Staff"}},
        ]

    def test_both_reads_agree_on_the_exposed_option_values(self, service):
        # R3.1: an already-resolving options-authored field does NOT hit the asymmetry — both
        # reads agree. The public read is the SUBSET of the editor read's values (R3.2 filter);
        # every public value is one the editor exposes, in the same order. (Observed baseline:
        # editor = [internet, facebook, staff_only]; public = [internet, facebook].)
        editor = service.get_field_config(_TENANT)
        public = service.get_public_field_config(_TENANT)

        editor_vals = [o["value"] for o in _field(editor, "referral_source")["options"]]
        public_vals = [o["value"] for o in _field(public, "referral_source")["options"]]

        assert editor_vals == ["internet", "facebook", "staff_only"]
        assert public_vals == ["internet", "facebook"]
        # The public values are an ordered subset of the editor values (reads agree on vocabulary).
        assert public_vals == [v for v in editor_vals if v in set(public_vals)]

    def test_both_reads_agree_on_labels_for_shared_values(self, service):
        # For a value exposed in BOTH reads, the label is identical (same source vocabulary).
        editor = service.get_field_config(_TENANT)
        public = service.get_public_field_config(_TENANT)
        editor_by_val = {o["value"]: o["label"] for o in _field(editor, "referral_source")["options"]}
        public_by_val = {o["value"]: o["label"] for o in _field(public, "referral_source")["options"]}
        for val in public_by_val:
            assert public_by_val[val] == editor_by_val[val]


# ── R3.2 — application_choices (public-form SUBSET) is a separate, unchanged concept ──


class TestApplicationChoicesSubsetUnchanged:
    def test_editor_read_carries_the_authored_subset_verbatim(self, service):
        # OBSERVED: the editor read echoes the authored application_choices subset unchanged.
        editor = service.get_field_config(_TENANT)
        assert _field(editor, "referral_source")["application_choices"] == ["internet", "facebook"]

    def test_public_read_filters_options_down_to_the_subset(self, service):
        # OBSERVED: the public read FILTERS the field's options to the declared subset — the
        # staff-only value is excluded from the public form (R3.2: different concept, preserved).
        public = service.get_public_field_config(_TENANT)
        vals = [o["value"] for o in _field(public, "referral_source")["options"]]
        assert vals == ["internet", "facebook"]
        assert "staff_only" not in vals

    def test_public_required_flag_is_the_application_required_not_staff_required(self, service):
        # OBSERVED: the public field's `required` reflects application_required (False here),
        # not the staff `required`. Preserved — the subset/public concept is distinct.
        public = service.get_public_field_config(_TENANT)
        assert _field(public, "referral_source")["required"] is False


# ── R3.2 (reference) — membership_type resolves from the live active catalog ──────────


class TestReferenceCatalogReadUnchanged:
    def test_membership_type_editor_options_are_the_active_catalog(self, service):
        # OBSERVED: membership_type (a REFERENCE field) resolves `options` from the active
        # catalog, ordered by (order, type_code), each entry {value,label,order}. This is the
        # non-bug reference path (design "not a bug (3)") and must be preserved.
        editor = service.get_field_config(_TENANT)
        opts = _field(editor, "membership_type")["options"]
        assert opts == [
            {"value": "gewoon", "label": {"nl": "Gewoon", "en": "Ordinary"}, "order": 10},
            {"value": "erelid", "label": {"nl": "Erelid", "en": "Honorary"}, "order": 20},
        ]


# ── scope DISPLAY surface — the editor `scope` attr is {enabled, required_for}, no values ─


class TestScopeAccessStateSurfaceUnchanged:
    def test_editor_scope_attribute_is_enabled_required_for_only(self, service):
        # OBSERVED: the editor read surfaces the scope axis as {enabled, required_for} with NO
        # `values` sub-key (scope values ARE the field's enum values; single vocabulary). The
        # 03a fix touches the DISPLAY vocabulary derivation only, never this access-state surface.
        editor = service.get_field_config(_TENANT)
        team = _field(editor, "team")
        assert team["scope"] == {"enabled": True, "required_for": ["Members_CRUD"]}
        assert "values" not in team["scope"]

    def test_scope_backed_field_options_are_the_inline_authored_vocabulary(self, service):
        # OBSERVED: the scope-backed field's served `options` are its inline authored options.
        editor = service.get_field_config(_TENANT)
        assert [o["value"] for o in _field(editor, "team")["options"]] == ["a", "b"]


# ── R3.3 — spec-03 Change-Op / resolved-view contract preserved (no raw-storage key) ──


class TestResolvedViewContractPreserved:
    def test_editor_read_exposes_no_raw_storage_shape_key(self, service):
        # R3.3 / steering 39: the read-assembly seam serves a RESOLVED domain view — the raw
        # stored overlay shape never crosses the boundary. No field_overlay / overrides /
        # fixed_overrides / dotted {group}.{key} key appears in the response.
        editor = service.get_field_config(_TENANT)
        blob = json.dumps(editor)
        for raw_key in ("field_overlay", "overrides", "fixed_overrides"):
            assert f'"{raw_key}"' not in blob
        # Fields are keyed by the BARE key, never a dotted {group}.{key}.
        for f in editor["fields"]:
            assert "." not in f["key"]

    def test_editor_read_is_json_serializable(self, service):
        json.dumps(service.get_field_config(_TENANT))  # must not raise


# ── PBT — preservation over arbitrary already-resolving options-authored enums ────────
#
# Property 2 (design "Preservation Checking", PBT recommended): generate already-resolving
# selectable fields (options-authored enums) + an application_choices subset, observe the current
# UNFIXED output, and assert the invariant that already holds — both reads agree on the exposed
# vocabulary and the public read is exactly the declared subset of the editor read. This captures
# the baseline the fix must preserve across the whole non-bug input space, not just one fixture.
#
# Validates: Requirements 3.1, 3.2

_VALUE = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8).filter(
    lambda s: s.strip() != ""
)


@st.composite
def _options_authored_enum_with_subset(draw):
    """An options-authored enum: 2..5 unique values, a non-empty application_choices subset
    that is a proper (order-preserving) subset of the authored values."""
    values = draw(st.lists(_VALUE, min_size=2, max_size=5, unique=True))
    # A subset: pick a non-empty subset of the values, keeping authored order.
    mask = draw(st.lists(st.booleans(), min_size=len(values), max_size=len(values)))
    subset = [v for v, keep in zip(values, mask) if keep]
    if not subset:  # ensure non-empty
        subset = [values[0]]
    return values, tuple(subset)


@settings(max_examples=100)
@given(spec=_options_authored_enum_with_subset())
def test_property_options_authored_preservation(spec):
    """Property 2 preservation: for an already-resolving options-authored enum with a subset,
    the editor read exposes the full authored values (in order) and the public read exposes
    EXACTLY the declared subset (order-preserving) — both reads agree on vocabulary. Observed
    to hold on UNFIXED code; the fix must preserve it.

    Validates: Requirements 3.1, 3.2
    """
    values, subset = spec
    overlay = TenantOverlay(
        functional_groups={
            "membership": FunctionalGroup(
                key="membership", label={"nl": "Lid", "en": "Membership"}, order=4
            ),
        },
        fields={
            "referral_source": OverlayField(
                key="referral_source",
                type=FieldType.ENUM,
                required=False,
                label={"nl": "Bron", "en": "Source"},
                options=tuple(
                    EnumOption(value=v, label={"nl": v, "en": v}) for v in values
                ),
                functional_group="membership",
                order=50,
                application_visible=True,
                application_required=False,
                application_choices=subset,
            ),
        },
    )
    service = MembershipService(
        FakeCatalogRepository(), overlay_provider=StaticOverlayProvider({_TENANT: overlay})
    )

    editor = service.get_field_config(_TENANT)
    public = service.get_public_field_config(_TENANT)

    editor_vals = [o["value"] for o in _field(editor, "referral_source")["options"]]
    public_vals = [o["value"] for o in _field(public, "referral_source")["options"]]

    # Editor exposes the full authored vocabulary, in authored order (already resolving).
    assert editor_vals == list(values)
    # Public exposes EXACTLY the declared subset, order-preserving (R3.2 filter, preserved).
    assert public_vals == list(subset)
    # Both reads agree on vocabulary: every public value is an editor value.
    assert set(public_vals) <= set(editor_vals)
    # The editor echoes the authored subset verbatim (separate-concept, unchanged).
    assert _field(editor, "referral_source")["application_choices"] == list(subset)


# ── 03a task 4 (C4 / F10) — the PUBLIC serializer consumes the seam's ONE `options`, applies ──
# ── ONLY the R3.2 subset FILTER, and drops the `field.choices` fallback. ──────────────────────
#
# These are deliberate NEW-behavior assertions (not preservation): the public read
# (`_public_field_options`) now serializes the single canonical `options` the read-assembly seam
# populated, uniformly for every kind, with the public-subset filter as the only projection and
# no `field.choices` fallback (F10). The R3.2 subset filter itself is PRESERVED.
#
# Validates: Requirements 2.1, 2.6, 3.2 · Components: C4, F10


class TestPublicReadConsumesSeamOptionsWithSubsetFilter:
    def test_public_subset_filter_is_preserved_and_applied_to_the_seam_options(self, service):
        # R3.2 preserved: the public read FILTERS the seam's full vocabulary down to the declared
        # application_choices — staff_only excluded — exactly as before, now off the ONE `options`.
        public = service.get_public_field_config(_TENANT)
        vals = [o["value"] for o in _field(public, "referral_source")["options"]]
        assert vals == ["internet", "facebook"]
        assert "staff_only" not in vals

    def test_public_options_drop_the_staff_only_roles_gate(self, service):
        # The public projection drops the staff-only `roles` key but is otherwise the SAME
        # vocabulary the staff serializer emits (one assembly point, one shape minus roles).
        public = service.get_public_field_config(_TENANT)
        for opt in _field(public, "referral_source")["options"]:
            assert "roles" not in opt
            assert set(opt) == {"value", "label"}

    def test_public_bare_choices_enum_has_no_options_no_fallback(self, catalog_repo):
        # F10: a bare-`choices`, application-visible enum (no inline options, not scope-backed)
        # resolves NO canonical seam source, so the public read serves options=None rather than
        # falling back to the bare `field.choices` list. (Declared-but-unpropagated → the
        # asymmetry task 9/C6 raises on at the seam.)
        overlay = TenantOverlay(
            fields={
                "magazine_pref": OverlayField(
                    key="magazine_pref",
                    type=FieldType.ENUM,
                    label={"nl": "Clubblad", "en": "Magazine"},
                    choices=("Geen", "Papier", "Digitaal"),
                    order=20,
                    application_visible=True,
                )
            }
        )
        svc = MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({_TENANT: overlay})
        )
        public = svc.get_public_field_config(_TENANT)
        mag = _field(public, "magazine_pref")
        assert mag["options"] is None


class TestScopeBackedFieldPopulatedFromScopeVocabAtSeam:
    """C4: a scope-dimension-backed enum (no inline options) gets its ONE `options` from the
    injected scope_vocab at the seam — the same single population path as every other kind."""

    def test_scope_backed_options_are_the_dimension_values(self, catalog_repo):
        from sam.members.domain.scope_dimensions import (
            ScopeDimension,
            StaticScopeConfigProvider,
        )

        overlay = TenantOverlay(
            fields={
                "region": OverlayField(
                    key="region",
                    type=FieldType.ENUM,
                    label={"nl": "Regio", "en": "Region"},
                    order=70,
                )
            }
        )
        scope = StaticScopeConfigProvider(
            {
                _TENANT: [
                    ScopeDimension(
                        key="region", field="region", enabled=True, values=("noord", "zuid")
                    )
                ]
            }
        )
        svc = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({_TENANT: overlay}),
            scope_config_provider=scope,
        )
        editor = svc.get_field_config(_TENANT)
        region = _field(editor, "region")
        assert [o["value"] for o in region["options"]] == ["noord", "zuid"]
        assert all("value" in o and "label" in o for o in region["options"])
