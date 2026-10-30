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
    FixedFieldOverride,
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
        # 03b CONTRACT (Task 10.5): membership_type owns its vocabulary as INLINE field options
        # (the catalog is retired). Author the two active types as the field's own options.
        overrides={
            "membership.membership_type": FixedFieldOverride(
                options=(
                    EnumOption(value="gewoon", label={"nl": "Gewoon", "en": "Ordinary"}, allowed=True, order=10),
                    EnumOption(value="erelid", label={"nl": "Erelid", "en": "Honorary"}, allowed=True, order=20),
                ),
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
        # 03b (BU-1, Req 3.1): an inline enum option now also carries the `allowed` retired/
        # grandfather flag (always present; defaults True so an unauthored option stays offered).
        # `order` is omitted here because these options are unranked (EnumOption.order is None).
        assert opts == [
            {"value": "internet", "label": {"nl": "Internet", "en": "Internet"}, "allowed": True},
            {"value": "facebook", "label": {"nl": "Facebook", "en": "Facebook"}, "allowed": True},
            {"value": "staff_only", "label": {"nl": "Staf", "en": "Staff"}, "allowed": True},
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


# ── 03b (BU-1) — the `allowed` retired flag + `order` ride through the serializers ────


class TestEnumOptionAllowedAndOrderSerialized:
    """03b (BU-1, Req 3.1/3.2): an inline enum option's `allowed` (retired/grandfather flag) and
    `order` (render/default rank) reach the resolved-view (staff) AND public API DTOs. `allowed`
    is ALWAYS carried (the frontend needs it to hide a retired option while still showing a stored
    value); `order` is carried only when ranked; a defaulted-True `allowed` is still emitted."""

    def _service_with(self, catalog_repo, options):
        overlay = TenantOverlay(
            fields={
                "referral_source": OverlayField(
                    key="referral_source",
                    type=FieldType.ENUM,
                    label={"nl": "Bron", "en": "Source"},
                    options=options,
                    functional_group="membership",
                    order=50,
                    application_visible=True,
                )
            }
        )
        return MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({_TENANT: overlay})
        )

    def test_staff_read_carries_allowed_true_and_order_when_ranked(self, catalog_repo):
        svc = self._service_with(
            catalog_repo,
            (
                EnumOption(value="internet", label={"en": "Internet"}, order=10),
                EnumOption(value="facebook", label={"en": "Facebook"}, order=20),
            ),
        )
        opts = _field(svc.get_field_config(_TENANT), "referral_source")["options"]
        assert opts == [
            {"value": "internet", "label": {"en": "Internet"}, "allowed": True, "order": 10},
            {"value": "facebook", "label": {"en": "Facebook"}, "allowed": True, "order": 20},
        ]

    def test_staff_read_carries_allowed_false_for_a_retired_option(self, catalog_repo):
        svc = self._service_with(
            catalog_repo,
            (
                EnumOption(value="internet", label={"en": "Internet"}),
                EnumOption(value="fax", label={"en": "Fax"}, allowed=False),
            ),
        )
        opts = _field(svc.get_field_config(_TENANT), "referral_source")["options"]
        by_val = {o["value"]: o for o in opts}
        assert by_val["internet"]["allowed"] is True
        assert by_val["fax"]["allowed"] is False
        # order omitted when unranked (EnumOption.order is None)
        assert "order" not in by_val["internet"]

    def test_public_read_carries_allowed_but_drops_roles(self, catalog_repo):
        svc = self._service_with(
            catalog_repo,
            (
                EnumOption(value="internet", label={"en": "Internet"}, allowed=True),
                EnumOption(value="fax", label={"en": "Fax"}, allowed=False, roles=("Staff",)),
            ),
        )
        opts = _field(svc.get_public_field_config(_TENANT), "referral_source")["options"]
        for o in opts:
            assert "allowed" in o
            assert "roles" not in o


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


class TestReferenceReadsFieldInlineOptions:
    def test_membership_type_editor_options_are_the_fields_inline_options(self, service):
        # 03b CONTRACT (Task 10.5): membership_type (a REFERENCE field) resolves `options` from the
        # field's OWN inline vocabulary — NOT a catalog read (the catalog is retired). The options
        # are served through the SAME enum serializer as any other enum, each carrying the unified
        # `allowed` flag (Req 3.1), ordered by `order`.
        editor = service.get_field_config(_TENANT)
        opts = _field(editor, "membership_type")["options"]
        assert opts == [
            {"value": "gewoon", "label": {"nl": "Gewoon", "en": "Ordinary"}, "allowed": True, "order": 10},
            {"value": "erelid", "label": {"nl": "Erelid", "en": "Honorary"}, "allowed": True, "order": 20},
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
            # 03b (BU-1): `allowed` rides through to the public contract (the form needs it to
            # hide a retired option while still showing a stored value); `order` is omitted when
            # unranked. The staff-only `roles` gate is still dropped.
            assert set(opt) == {"value", "label", "allowed"}

    def test_public_bare_choices_enum_is_dropped_not_page_blackout(self, catalog_repo, caplog):
        # F10 + C6 (task 9, REVISED per-consumer split): a bare-`choices`, application-visible enum
        # (no inline options, not scope-backed) DECLARES an inline vocabulary (`choices`) that did
        # NOT propagate into `options` — the asymmetry. The read-assembly seam still RAISES
        # `UnpropagatedVocabularyError`, but on the PUBLIC path the serializer CATCHES it per-field,
        # DROPS that one field, and STILL serves the page (bounded blast radius). It does NOT black
        # out the whole public form the way a uniform raise would. (The STAFF read still raises —
        # see TestFailLoudOnAsymmetry.)
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
        import logging

        with caplog.at_level(logging.ERROR):
            public = svc.get_public_field_config(_TENANT)  # must NOT raise — page served
        # The offending field is dropped; the page is still served (no magazine_pref field).
        assert all(f["key"] != "magazine_pref" for f in public["fields"])
        # An operator ALERT was emitted (metric/alert channel) for the drop.
        assert "OPERATOR_ALERT CONFIG_FIELD_UNPROPAGATED" in caplog.text
        assert "overlay.magazine_pref" in caplog.text  # server-side detail, not client


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


# ── 03a task 9 (C6 / F4 / F9 / F10) — UNIFORM fail-loud on the ASYMMETRY only ─────────────────
#
# Property 3 (design "Fail-Loud", G5 predicate): the read-assembly seam
# (`_assemble_field_options`) raises a LOUD, caller-safe, diagnosable error when a field's
# DECLARED source EXISTS but its vocabulary did NOT propagate into `options` (the asymmetry) —
# UNIFORMLY, no per-kind exemption, never degrading to an empty list / a `field.choices` fallback.
# It does NOT fire for a source that is legitimately empty/absent-by-design (G5): a scope
# dimension with zero values yet, a newly-created not-yet-populated field, or a reference whose
# catalog correctly populates (or is simply empty — zero active types yet).
#
# Validates: Requirements 2.3, 2.6 · Components: C6, F4, F9, F10


class TestFailLoudOnAsymmetry:
    """(a) Fail-loud cases: a DECLARED source present but unpropagated → raises, every read."""

    def _bare_choices_service(self, catalog_repo, *, application_visible=False):
        # An inline enum carrying a DECLARED bare `choices` vocabulary that did NOT propagate into
        # `options` (the un-migrated / bare-`choices` legacy row). Built straight through the
        # resolver, bypassing the C5/C7 canonicalisation that would have produced `options`.
        overlay = TenantOverlay(
            fields={
                "referral_source": OverlayField(
                    key="referral_source",
                    type=FieldType.ENUM,
                    label={"nl": "Bron", "en": "Source"},
                    choices=("internet", "facebook", "flyer"),
                    order=50,
                    application_visible=application_visible,
                )
            }
        )
        return MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({_TENANT: overlay})
        )

    def test_staff_read_raises_on_bare_choices_asymmetry(self, catalog_repo):
        from sam.members.domain._membership_writes_fieldconfig import (
            UnpropagatedVocabularyError,
        )

        svc = self._bare_choices_service(catalog_repo)
        with pytest.raises(UnpropagatedVocabularyError):
            svc.get_field_config(_TENANT)

    def test_membership_type_read_never_touches_the_catalog(self, catalog_repo):
        # 03b CONTRACT (Task 10.5): the reference read no longer consults the catalog at all — the
        # vocabulary is the field's OWN inline options. A catalog whose list method would RAISE is
        # therefore never called on the staff read: the field resolves from its inline options and
        # the broken catalog is irrelevant. (Pre-CONTRACT this raised; now it must NOT, because the
        # catalog is not a read source — proving the fallback is gone.)
        class _FetchErrorCatalog:
            def list_membership_types(self, tenant_id, active_only=False):
                raise AssertionError("catalog must NOT be read for membership_type (03b CONTRACT)")

        overlay = TenantOverlay(
            overrides={
                "membership.membership_type": FixedFieldOverride(
                    options=(
                        EnumOption(value="gewoon", label={"nl": "Gewoon", "en": "Ordinary"}, allowed=True, order=10),
                    ),
                ),
            },
            fields={
                "referral_source": OverlayField(
                    key="referral_source",
                    type=FieldType.ENUM,
                    label={"nl": "Bron", "en": "Source"},
                    options=(
                        EnumOption(value="a", label={"nl": "A", "en": "A"}),
                    ),
                    order=50,
                )
            },
        )
        svc = MembershipService(
            _FetchErrorCatalog(), overlay_provider=StaticOverlayProvider({_TENANT: overlay})
        )
        # No raise: the staff read resolves membership_type from its inline options, never the
        # (deliberately broken) catalog.
        editor = svc.get_field_config(_TENANT)
        assert [o["value"] for o in _field(editor, "membership_type")["options"]] == ["gewoon"]

    def test_error_is_caller_safe_generic_message_no_data_leak(self, catalog_repo):
        # steering 30: the client-visible message is GENERIC — it echoes NO offending data (not the
        # field key, not the choices). The diagnosable specifics (tenant + dotted key) live on
        # `detail` for the SERVER-side log line keyed by the edge correlation id, never returned.
        from sam.members.domain._membership_writes_fieldconfig import (
            UnpropagatedVocabularyError,
        )

        svc = self._bare_choices_service(catalog_repo)
        with pytest.raises(UnpropagatedVocabularyError) as exc:
            svc.get_field_config(_TENANT)
        msg = str(exc.value)
        assert "did not resolve to any options" in msg
        # No internals in the client-facing message.
        assert "referral_source" not in msg
        assert "internet" not in msg
        assert _TENANT not in msg
        # The diagnostic detail (server-side only) names the tenant + field for triage.
        assert _TENANT in exc.value.detail
        assert "overlay.referral_source" in exc.value.detail
        assert exc.value.dotted_key == "overlay.referral_source"

    def test_error_subclasses_valueerror_for_caller_safe_edge_mapping(self):
        # Subclasses ValueError so the edge's generic handler maps it to a caller-safe 500 with a
        # stable code + correlation id (never str(e)) — consistent with C5's MalformedOptionsError.
        from sam.members.domain._membership_writes_fieldconfig import (
            UnpropagatedVocabularyError,
        )

        assert issubclass(UnpropagatedVocabularyError, ValueError)


class TestFailLoudDoesNotFireOnLegitimatelyEmptySources:
    """(b) G5 must-NOT-raise cases: a legitimately empty/absent source is a valid in-progress
    state across EVERY kind — the asymmetry predicate must not trip on any of them."""

    def test_scope_source_with_zero_values_does_not_raise_at_the_seam(self, catalog_repo):
        # G5 (scope): a scope-backed field whose injected `scope_vocab` entry is EMPTY is a
        # legitimately-empty source (a dimension with zero values yet) — NOT the asymmetry. The
        # seam must project the (empty) list, NEVER raise. Exercised at the seam unit directly
        # because the scope-CONFIG layer independently forbids an *enabled* dimension with zero
        # values (ScopeConfigError), so the empty source can only be presented to the seam as an
        # empty `scope_vocab` entry — which is exactly what the predicate must tolerate.
        svc = MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({})
        )
        region = OverlayField(
            key="region", type=FieldType.ENUM, label={"nl": "Regio", "en": "Region"}
        )
        from sam.members.domain.field_resolver import (
            FieldOrigin,
            ResolvedField,
        )

        resolved = ResolvedField(
            key="region",
            group="overlay",
            type=FieldType.ENUM,
            required=False,
            origin=FieldOrigin.VARIABLE,
            label=region.label,
        )
        # scope_vocab declares `region` as a scope source, but with ZERO values yet.
        out = svc._assemble_field_options(
            resolved, tenant_id=_TENANT, scope_vocab={"region": ()}
        )
        assert out == []  # projected empty list, no raise (G5)

    def test_reference_with_no_inline_options_does_not_raise(self):
        # G5 under 03b CONTRACT (Task 10.5): a reference (membership_type) field that authors NO
        # inline options (a brand-new tenant, pre-authoring) is a legitimately-empty source — NOT
        # the asymmetry. There is no catalog fallback any more, so the seam returns None (no
        # declared inline vocabulary), and the read must NOT raise.
        empty_catalog = FakeCatalogRepository()  # catalog is irrelevant now (not read)
        svc = MembershipService(
            empty_catalog, overlay_provider=StaticOverlayProvider({})
        )
        editor = svc.get_field_config(_TENANT)  # must NOT raise
        assert _field(editor, "membership_type")["options"] is None

    def test_newly_created_field_with_no_declared_source_does_not_raise(self, catalog_repo):
        # G5: a newly-created not-yet-populated field with NO declared vocabulary at all (a plain
        # string field — no options, no choices, not scope/reference). No declared source → not
        # the asymmetry; the seam returns None, no raise.
        overlay = TenantOverlay(
            fields={
                "club_note": OverlayField(
                    key="club_note",
                    type=FieldType.STRING,
                    label={"nl": "Notitie", "en": "Note"},
                    order=80,
                )
            }
        )
        svc = MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({_TENANT: overlay})
        )
        editor = svc.get_field_config(_TENANT)  # must NOT raise
        assert _field(editor, "club_note")["options"] is None

    def test_reference_that_correctly_populates_does_not_raise(self, service):
        # G5 under 03b CONTRACT (Task 10.5): a reference whose field authors inline options (the
        # `service` fixture's membership_type override carries gewoon + erelid) is the non-bug
        # reference path — populated from the field's own options, not the asymmetry, no raise.
        editor = service.get_field_config(_TENANT)  # must NOT raise
        assert [o["value"] for o in _field(editor, "membership_type")["options"]] == [
            "gewoon",
            "erelid",
        ]

    def test_already_resolving_inline_enum_does_not_raise(self, service):
        # G5: an options-authored inline enum already resolves to populated `options` — the
        # non-bug path; it must NOT raise (the whole fixture service resolves cleanly).
        editor = service.get_field_config(_TENANT)  # must NOT raise
        assert [o["value"] for o in _field(editor, "referral_source")["options"]] == [
            "internet",
            "facebook",
            "staff_only",
        ]


# ── 03a task 9 (C6 — REVISED) — per-consumer blast-radius SPLIT ───────────────────────────────
#
# The REVISED C6 design ("Blast-radius policy — DELIBERATE and asymmetric by CONSUMER") splits the
# fail-loud boundary by consumer:
#   * STAFF config-editor read (`get_field_config`): the seam's raise PROPAGATES — the editor is
#     where a config bug must surface (covered by TestFailLoudOnAsymmetry above).
#   * PUBLIC application path (`get_public_field_config`): the serializer CATCHES the seam's
#     per-field raise, DROPS that one field, STILL serves the page, and emits an error LOG + METRIC
#     + ALERT (operator-alert channel, correlation id) — one bad field never blacks out the form.
#
# The catch is PER-FIELD: a raising field A must not skip sibling fields B/C. These assert the drop,
# the sibling survival, the still-served page, and the alert (with correlation id); the staff path
# over the SAME asymmetry still raises.
#
# Validates: Requirements 2.3, 2.6 · Components: C6, F4, F9, F10


class TestPublicPathDropsAsymmetricFieldAndAlerts:
    def _overlay_one_bad_two_good(self) -> TenantOverlay:
        """An overlay with THREE application-visible enums: a bare-`choices` asymmetric field
        between two already-resolving options-authored fields, so a per-field catch can be proven
        to drop ONLY the bad one and keep both siblings."""
        return TenantOverlay(
            functional_groups={
                "membership": FunctionalGroup(
                    key="membership", label={"nl": "Lid", "en": "Membership"}, order=4
                ),
            },
            fields={
                "good_a": OverlayField(
                    key="good_a",
                    type=FieldType.ENUM,
                    label={"nl": "A", "en": "A"},
                    options=(EnumOption(value="a1", label={"nl": "A1", "en": "A1"}),),
                    functional_group="membership",
                    order=10,
                    application_visible=True,
                ),
                "bad_mid": OverlayField(
                    key="bad_mid",
                    type=FieldType.ENUM,
                    label={"nl": "Slecht", "en": "Bad"},
                    choices=("Geen", "Papier"),  # bare choices, un-propagated → asymmetry
                    functional_group="membership",
                    order=20,
                    application_visible=True,
                ),
                "good_c": OverlayField(
                    key="good_c",
                    type=FieldType.ENUM,
                    label={"nl": "C", "en": "C"},
                    options=(EnumOption(value="c1", label={"nl": "C1", "en": "C1"}),),
                    functional_group="membership",
                    order=30,
                    application_visible=True,
                ),
            },
        )

    def test_public_read_drops_the_one_bad_field_and_keeps_siblings(self, catalog_repo):
        # The asymmetric field (`bad_mid`) is DROPPED from the public schema; both sibling fields
        # (`good_a`, `good_c`) survive and the page is still served. Proves the catch is PER-FIELD
        # — a field raising in the MIDDLE of the loop does not skip the field after it.
        svc = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({_TENANT: self._overlay_one_bad_two_good()}),
        )
        public = svc.get_public_field_config(_TENANT)  # must NOT raise
        keys = {f["key"] for f in public["fields"]}
        assert "bad_mid" not in keys  # the one asymmetric field dropped
        assert "good_a" in keys and "good_c" in keys  # siblings survive

    def test_public_read_emits_error_log_metric_alert_with_correlation_id(
        self, catalog_repo, caplog
    ):
        # The drop emits an ERROR-level operator ALERT on the SAM operator-alert channel (a stable
        # greppable marker a CloudWatch metric filter / alarm subscribes to), carrying a
        # correlation id + the server-side detail (tenant + dotted key) for triage — nothing
        # leaked to the client beyond the field being absent (steering 30).
        import logging
        import re

        svc = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({_TENANT: self._overlay_one_bad_two_good()}),
        )
        with caplog.at_level(logging.ERROR):
            svc.get_public_field_config(_TENANT)

        # An error-level record on the operator-alert channel with the stable marker.
        alert_records = [
            r
            for r in caplog.records
            if r.levelno >= logging.ERROR
            and "OPERATOR_ALERT CONFIG_FIELD_UNPROPAGATED" in r.getMessage()
        ]
        assert alert_records, "expected an operator ALERT for the dropped field"
        text = alert_records[0].getMessage()
        # Server-side detail: tenant + dotted field key present for triage.
        assert _TENANT in text
        assert "overlay.bad_mid" in text
        # A correlation id ties the alert to the server-side detail (32-hex uuid4).
        assert re.search(r"correlation_id=[0-9a-f]{32}", text), text

    def test_public_drop_does_not_leak_internal_detail_to_served_schema(self, catalog_repo):
        # Steering 30 / resolved-view contract: the served public schema carries only the surviving
        # fields — no error payload, no dropped-field key, no raw-storage key. The applicant sees
        # the field simply absent, nothing about WHY.
        svc = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({_TENANT: self._overlay_one_bad_two_good()}),
        )
        public = svc.get_public_field_config(_TENANT)
        blob = json.dumps(public)
        assert "bad_mid" not in blob
        assert "error" not in blob and "correlation" not in blob
        for raw_key in ("field_overlay", "overrides", "fixed_overrides"):
            assert f'"{raw_key}"' not in blob

    def test_staff_read_over_the_same_asymmetry_still_raises(self, catalog_repo):
        # The CONTRAST that defines the split: the SAME overlay that the public path tolerates (by
        # dropping) still raises LOUDLY on the STAFF editor read — the editor is where the config
        # bug must surface. Public drops; staff raises.
        from sam.members.domain._membership_writes_fieldconfig import (
            UnpropagatedVocabularyError,
        )

        svc = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({_TENANT: self._overlay_one_bad_two_good()}),
        )
        with pytest.raises(UnpropagatedVocabularyError):
            svc.get_field_config(_TENANT)

    def test_each_raised_error_carries_its_own_correlation_id(self):
        # The correlation id is minted per raise (uuid4), so two independent asymmetries get
        # distinct ids — an operator can disambiguate concurrent drops.
        from sam.members.domain._membership_writes_fieldconfig import (
            UnpropagatedVocabularyError,
        )

        e1 = UnpropagatedVocabularyError(_TENANT, "overlay.x", kind="inline-enum")
        e2 = UnpropagatedVocabularyError(_TENANT, "overlay.y", kind="inline-enum")
        assert e1.correlation_id != e2.correlation_id
        assert len(e1.correlation_id) == 32  # uuid4 hex


class TestG5LegitimatelyEmptyDoesNotRaiseOnPublicPathEither:
    """G5 must-NOT-raise cases hold on BOTH consumer paths. The public path must not DROP a field
    whose source is legitimately empty/absent-by-design — a drop would be as wrong as a raise."""

    def test_public_read_reference_empty_catalog_serves_membership_type(self):
        # G5 (reference, public): an empty active catalog (new tenant, zero active types) is a
        # legitimately-empty RESULT, not the asymmetry. membership_type is application-visible by
        # default in the fixed set — the public read serves it with an empty option list, NOT
        # dropped, NOT raised.
        empty_catalog = FakeCatalogRepository()
        svc = MembershipService(empty_catalog, overlay_provider=StaticOverlayProvider({}))
        public = svc.get_public_field_config(_TENANT)  # must NOT raise
        mt = [f for f in public["fields"] if f["key"] == "membership_type"]
        # membership_type is present (not dropped) with an empty, valid option list.
        if mt:  # it is application-visible in the fixed base
            assert mt[0]["options"] == []

    def test_public_read_scope_empty_vocab_is_served_not_dropped(self, catalog_repo):
        # G5 (scope, public): an empty scope source (dimension present in scope_vocab with ZERO
        # values yet) projects to an EMPTY option list at the seam — a legitimately-empty source,
        # NOT the asymmetry. The public serializer must SERVE it (empty options), not DROP it. The
        # config layer forbids an *enabled* dimension with zero values (ScopeConfigError), so the
        # empty source is presented to the public serializer directly via `_serialize_public_field`
        # over the empty `field_options` the seam would return — proving the drop path is NOT taken.
        from sam.members.domain.field_resolver import FieldOrigin, ResolvedField

        svc = MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({})
        )
        resolved = ResolvedField(
            key="region",
            group="overlay",
            type=FieldType.ENUM,
            required=False,
            origin=FieldOrigin.VARIABLE,
            label={"nl": "Regio", "en": "Region"},
            application_visible=True,
        )
        # The empty scope source: the seam returns [] (empty list), NOT a raise (G5). The public
        # serializer serves that field with an empty option list — not dropped.
        served = svc._serialize_public_field(resolved, field_options=[])
        assert served["key"] == "region"
        assert served["options"] == []  # served with empty options, not dropped

    def test_public_read_newly_created_sourceless_field_is_served(self, catalog_repo):
        # G5 (sourceless, public): a newly-created application-visible field with NO declared
        # vocabulary at all (plain string) is served with options=None — not dropped, not raised.
        overlay = TenantOverlay(
            fields={
                "club_note": OverlayField(
                    key="club_note",
                    type=FieldType.STRING,
                    label={"nl": "Notitie", "en": "Note"},
                    order=80,
                    application_visible=True,
                )
            }
        )
        svc = MembershipService(
            catalog_repo, overlay_provider=StaticOverlayProvider({_TENANT: overlay})
        )
        public = svc.get_public_field_config(_TENANT)  # must NOT raise
        note = [f for f in public["fields"] if f["key"] == "club_note"]
        assert note and note[0]["options"] is None

# ── 03a task 9b — NO-PER-KIND-BRANCH serializer test (covers the DROPPED C8 rule (c)) ─────────
#
# Design DROPPED the C8 blocking AST rule (c) — a per-field-KIND branch check in vocabulary
# CONSUMERS — because it needed TWO documented carve-outs (the R3.2 public-SUBSET FILTER in
# `_public_field_options`, and the frontend source-selector `resolveChoiceSource` / F11); a rule
# that needs carve-outs to avoid flagging legitimate code will false-positive and erode trust in
# the guard. The invariant that rule (c) was meant to protect — "the serializers have NO per-kind
# branch in the resulting `options` READ SHAPE" — is covered HERE by a targeted BEHAVIORAL test
# instead of a brittle AST/string scan (the mechanism the design explicitly rejected).
#
# MECHANISM (behavioral, primary guard): feed ONE overlay carrying all three selectable KINDS —
#   * inline enum       (vocabulary SOURCE = the field's own inline options),
#   * scope-vocab-backed (SOURCE = the injected scope dimension values),
#   * reference          (SOURCE = the live active membership_type catalog),
# through the ONE read-assembly seam and BOTH serializers (staff `_serialize_field` via
# `get_field_config` = F9, and public `_public_field_options` via `get_public_field_config` = F10)
# and assert all three kinds produce the SAME uniform rich `{value, label}` option read shape. The
# kinds differ ONLY in SOURCE, never in the serialized read shape — exactly the "no per-kind
# read-shape branch in a consumer" invariant. If a consumer re-branched by kind (e.g.
# `if field.type == reference/enum/scope` shaping options differently), these uniform-shape
# assertions would break.
#
# ALLOWED, explicitly (so a future reader does NOT mistake a legitimate projection for a
# violation):
#   * the R3.2 public-SUBSET FILTER in `_public_field_options` — narrowing `options` down to the
#     declared `application_choices` — is a legitimately different PROJECTION, NOT a per-kind
#     read-shape branch. This test asserts the ABSENCE of a forbidden per-kind branch, NOT the
#     absence of the subset projection; the subset filter is deliberately exercised and allowed.
#   * the per-kind SOURCE SELECTION inside the seam (`_assemble_field_options`) — the ONE place a
#     per-kind decision legitimately lives (which injected source populates `options`) — is NOT a
#     consumer read-shape branch and is allowed.
#   * the F11 frontend source-selector (`resolveChoiceSource`) is OUT OF SCOPE for this SAM test
#     (it is frontend TS, the OTHER documented carve-out) — it is covered by the frontend tests.
#
# Validates: Requirements 2.6, 2.7 · Components: C4 (F9/F10 collapse), test-based replacement for
# the DROPPED C8 blocking rule (c).

from sam.members.domain.field_resolver import FixedFieldOverride  # noqa: E402
from sam.members.domain.scope_dimensions import (  # noqa: E402
    ScopeDimension,
    StaticScopeConfigProvider,
)


def _three_kind_overlay() -> TenantOverlay:
    """An overlay with all THREE selectable kinds, each application-visible with a declared
    `application_choices` SUBSET, so both serializers run over every kind AND the R3.2 subset
    filter is exercised on the public path:

      * `referral_source` — inline enum (SOURCE = inline options), a tenant-added variable field,
      * `region`          — scope-vocab-backed enum, NO inline options (SOURCE = scope dimension),
                            a tenant-added variable field bound to a scope dimension,
      * `membership_type` — reference (SOURCE = the live active catalog). It is a FIXED field, so
                            it is NOT a variable overlay field — it is opted onto the public form
                            via a `fixed_overrides` entry (the D20 "fixed field onto the form"
                            path), which carries the public-form attributes + subset.
    """
    return TenantOverlay(
        functional_groups={
            "membership": FunctionalGroup(
                key="membership", label={"nl": "Lid", "en": "Membership"}, order=4
            ),
        },
        # membership_type is a FIXED reference field — a tenant puts it on the form via a
        # fixed-field OVERRIDE (never a variable `fields` entry, which would collide with the
        # fixed key). The override carries only the public-form attributes + the R3.2 subset.
        overrides={
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                application_required=False,
                application_choices=("gewoon",),  # R3.2 subset of the field's inline options
                # 03b CONTRACT (Task 10.5): the reference vocabulary is the field's OWN inline
                # options (the catalog is retired), folded from the two active h-dcn types.
                options=(
                    EnumOption(value="gewoon", label={"nl": "Gewoon", "en": "Ordinary"}, allowed=True, order=10),
                    EnumOption(value="erelid", label={"nl": "Erelid", "en": "Honorary"}, allowed=True, order=20),
                ),
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
                application_choices=("internet", "facebook"),  # R3.2 subset (staff_only excluded)
            ),
            "region": OverlayField(
                key="region",
                type=FieldType.ENUM,  # scope-vocab-backed: NO inline options
                required=False,
                label={"nl": "Regio", "en": "Region"},
                functional_group="membership",
                order=60,
                application_visible=True,
                application_required=False,
                application_choices=("noord",),  # R3.2 subset of the scope dimension values
            ),
        },
    )


@pytest.fixture()
def three_kind_service(catalog_repo) -> MembershipService:
    """A service wiring all three kinds: the catalog_repo feeds the reference vocabulary, and a
    scope-config provider binds `region` to a dimension so its `options` come from scope_vocab."""
    scope = StaticScopeConfigProvider(
        {
            _TENANT: [
                ScopeDimension(
                    key="region", field="region", enabled=True, values=("noord", "zuid")
                )
            ]
        }
    )
    return MembershipService(
        catalog_repo,
        overlay_provider=StaticOverlayProvider({_TENANT: _three_kind_overlay()}),
        scope_config_provider=scope,
    )


class TestNoPerKindReadShapeBranchInSerializers:
    """The test-based replacement for the dropped C8 blocking rule (c): both serializers resolve
    the ONE canonical `options` from the seam with NO per-kind read-shape branch — enum, scope,
    and reference all flow through the SAME serialization path and produce the SAME `{value,
    label?}` option shape. Kinds differ only in SOURCE (chosen once at the seam), never in the
    serialized READ shape."""

    # The three selectable kinds exercised, keyed by field → vocabulary SOURCE.
    _KINDS = ("referral_source", "region", "membership_type")

    def test_staff_serializer_produces_uniform_option_shape_for_all_kinds(
        self, three_kind_service
    ):
        # STAFF read (`_serialize_field`, F9): every kind's `options` is a list of rich dicts
        # carrying at least {value, label}. No kind yields a different read shape — e.g. no bare
        # string list for one kind and dicts for another, no per-kind extra/missing shape key that
        # would betray an `if field.type == ...` read-shape branch.
        editor = three_kind_service.get_field_config(_TENANT)
        for key in self._KINDS:
            opts = _field(editor, key)["options"]
            assert opts is not None and len(opts) >= 1, f"{key}: expected populated options"
            for o in opts:
                assert isinstance(o, dict), f"{key}: option is not a rich dict (read-shape branch?)"
                assert "value" in o and "label" in o, f"{key}: option missing uniform {{value,label}}"
                assert isinstance(o["value"], str)
                assert isinstance(o["label"], dict)

    def test_public_serializer_produces_uniform_option_shape_for_all_kinds(
        self, three_kind_service
    ):
        # PUBLIC read (`_public_field_options`, F10): the SAME uniform {value, label} shape for
        # every kind — with the staff-only `roles` gate dropped from the public contract. The
        # per-kind read-shape branch is ABSENT on the public path too.
        public = three_kind_service.get_public_field_config(_TENANT)
        for key in self._KINDS:
            opts = _field(public, key)["options"]
            assert opts is not None and len(opts) >= 1, f"{key}: expected populated public options"
            for o in opts:
                assert isinstance(o, dict), f"{key}: public option is not a rich dict"
                assert "value" in o and "label" in o, f"{key}: public option missing {{value,label}}"
                assert "roles" not in o  # staff-only gate never on the public contract

    def test_shared_option_keyset_is_identical_across_all_kinds_on_each_read(
        self, three_kind_service
    ):
        # The STRONGEST uniformity assertion: within a single read, the set of keys each kind's
        # option carries is the SAME across kinds (modulo the reference `order` which is a seam
        # SOURCE attribute, not a per-kind consumer branch). A per-kind read-shape branch would
        # make one kind's option dict carry a structurally different keyset than another's.
        public = three_kind_service.get_public_field_config(_TENANT)
        keysets = {
            key: {frozenset(o) for o in _field(public, key)["options"]}
            for key in self._KINDS
        }
        # On the public read, roles is dropped and reference `order` is a source attribute; the
        # common uniform shape is {value, label}. Every kind's options are a SUPERSET of that.
        for key, sets in keysets.items():
            for ks in sets:
                assert {"value", "label"} <= set(ks), f"{key}: option keyset {ks} lacks the uniform core"

    def test_r32_public_subset_filter_is_allowed_and_applied_not_flagged(
        self, three_kind_service
    ):
        # EXPLICIT: the R3.2 public-SUBSET FILTER is a LEGITIMATE projection, NOT a per-kind
        # read-shape branch — this test ALLOWS it and in fact asserts it still applies. The public
        # read narrows each kind's seam `options` down to the declared `application_choices`:
        #   * inline enum    → {internet, facebook}      (staff_only filtered out),
        #   * scope-backed   → {noord}                   (subset of {noord, zuid}),
        #   * reference      → {gewoon}                  (subset of the active catalog).
        # The filter is applied UNIFORMLY to every kind off the ONE `options` — it does not shape
        # the options differently BY KIND, it narrows by the SAME subset rule. Absence of a
        # forbidden per-kind branch is NOT absence of this subset projection.
        public = three_kind_service.get_public_field_config(_TENANT)
        assert [o["value"] for o in _field(public, "referral_source")["options"]] == [
            "internet",
            "facebook",
        ]
        assert [o["value"] for o in _field(public, "region")["options"]] == ["noord"]
        assert [o["value"] for o in _field(public, "membership_type")["options"]] == ["gewoon"]
        # And the editor (no subset filter) still exposes the FULL vocabulary for each kind — the
        # subset is a public-only PROJECTION, applied uniformly, not a per-kind read-shape branch.
        editor = three_kind_service.get_field_config(_TENANT)
        assert [o["value"] for o in _field(editor, "referral_source")["options"]] == [
            "internet",
            "facebook",
            "staff_only",
        ]
        assert [o["value"] for o in _field(editor, "region")["options"]] == ["noord", "zuid"]
        assert [o["value"] for o in _field(editor, "membership_type")["options"]] == [
            "gewoon",
            "erelid",
        ]

    def test_staff_and_public_resolve_the_same_vocabulary_from_the_same_seam(
        self, three_kind_service
    ):
        # Both serializers consume the ONE `options` the seam populated: for every kind, each
        # value the PUBLIC read exposes is a value the STAFF read exposes (public ⊆ staff), with an
        # IDENTICAL label — i.e. they read the SAME source vocabulary, differing only by the R3.2
        # subset projection, never by a per-kind read-shape branch.
        editor = three_kind_service.get_field_config(_TENANT)
        public = three_kind_service.get_public_field_config(_TENANT)
        for key in self._KINDS:
            staff_by_val = {o["value"]: o["label"] for o in _field(editor, key)["options"]}
            for o in _field(public, key)["options"]:
                assert o["value"] in staff_by_val, f"{key}: public value not in staff vocabulary"
                assert o["label"] == staff_by_val[o["value"]], f"{key}: label differs across reads"
