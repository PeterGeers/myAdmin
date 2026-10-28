"""
application-app task 4.1 — tests for the PUBLIC field-config read (seam a/c, R5.1–R5.3).

``MembershipService.get_public_field_config(tenant_id)`` (and its thin
:class:`~sam.members.domain.application_service.ApplicationService` facade) is the read side of
the public intake: the config-driven schema the public form fetches BEFORE submit. These pin the
behaviours task 4.1 adds:

1. **Only application-SELECTED fields are exposed (R5.1/R5.2).** ONLY fields the tenant marked
   ``application_visible`` appear; an unselected staff-only / membership field never leaks into
   the public schema, even though it is in the resolved config.
2. **Each exposed field carries the renderer contract (R5.3).** ``key`` / ``group`` / ``type`` /
   ``label{nl,en}`` / ``functional_group`` / ``order``, the **application-required** flag as
   ``required`` (NOT the staff ``required``), ``show_when`` when present, the ``format`` token
   (``{checker, params}``), and the enum options.
3. **The enum application SUBSET is applied (R4a.2).** A field that declares
   ``application_choices`` exposes ONLY the subset; ``membership_type`` exposes only the subset of
   ACTIVE catalog entries; a field with no subset exposes its full choice set (back-compatible).
4. **The 200 body shape (design §3.1).** ``{tenant_id, fields:[...], locales:["nl","en"],
   notice:{version}}`` — the data the public edge wraps in the R1a 200 envelope.

Staff-only attributes (``visible`` / ``origin`` / ``provenance`` / ``scope`` /
``member_number_format``) are deliberately NOT in the public schema.

The field config is supplied via a ``StaticOverlayProvider`` that marks specific fields onto the
public form (``application_visible`` via a fixed-field override / an overlay field); the repo is
the in-memory fake catalog repo reused from the field-config endpoint tests.

Validates: Requirements R5.1, R5.2, R5.3, R4a.2, R4b.6, R7.1
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.domain.application_service import ApplicationService
from sam.members.domain.consent_notice import StaticConsentNoticeProvider
from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption, FieldFormat, FieldType
from sam.members.domain.membership_service import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MembershipService,
)

# Reuse the in-memory fake catalog repo + entry factory from the field-config endpoint tests.
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

TENANT = "h-dcn"


def _overlay_public_form() -> TenantOverlay:
    """An overlay putting a mix of fields on the PUBLIC form via ``application_visible``.

    - ``personal.first_name`` → fixed override, on the form, application-required, EMAIL-less
      plain string.
    - ``personal.email`` → fixed override, on the form, with a ``FieldFormat`` EMAIL validator.
    - ``membership.membership_type`` → on the form with an application SUBSET (only ``gewoon``).
    - an overlay enum ``shirt_size`` → on the form with an application SUBSET (``m``, ``l``) of
      its full canonical ``options`` (``s``, ``m``, ``l``, ``xl``), conditionally shown
      (``show_when``). Authored as rich ``options`` — the ONE canonical vocabulary every
      selectable field carries post-03a (bare ``choices`` is retired, F9/F10).
    - an overlay string ``nickname`` → on the form, optional.
    - ``personal.last_name`` → NOT application-selected (must be ABSENT from the public schema).
    """
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(
                application_visible=True, application_required=True
            ),
            "personal.email": FixedFieldOverride(
                application_visible=True,
                application_required=True,
                format=FieldFormat(checker="EMAIL"),
            ),
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                application_required=True,
                application_choices=("gewoon",),
            ),
            # last_name intentionally NOT application_visible → never exposed.
        },
        fields={
            "shirt_size": OverlayField(
                key="shirt_size",
                type=FieldType.ENUM,
                label={"nl": "Maat", "en": "Size"},
                options=tuple(
                    EnumOption(value=v, label={"nl": v.upper(), "en": v.upper()})
                    for v in ("s", "m", "l", "xl")
                ),
                application_visible=True,
                application_choices=("m", "l"),
                show_when={"membership.membership_type": "gewoon"},
            ),
            "nickname": OverlayField(
                key="nickname",
                type=FieldType.STRING,
                label={"nl": "Bijnaam", "en": "Nickname"},
                application_visible=True,
            ),
        },
    )


@pytest.fixture()
def service() -> MembershipService:
    repo = _ApplicationRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    repo.add_type(TENANT, _entry(TENANT, "erelid", order=20))
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()}),
        consent_notice_provider=StaticConsentNoticeProvider({TENANT: "v3"}),
    )


class _ApplicationRepo(FakeCatalogRepository):
    """The fake catalog repo (read-only catalog surface) — all this read needs."""


def _by_key(fields: list[dict]) -> dict[str, dict]:
    return {f["key"]: f for f in fields}


# ── 1. only application-selected fields are exposed ───────────────────────────────────


class TestOnlySelectedFieldsExposed:
    def test_unselected_field_is_absent_from_public_schema(self, service):
        schema = service.get_public_field_config(TENANT)
        keys = {f["key"] for f in schema["fields"]}
        # last_name is in the resolved config but NOT application_visible → must not leak (R5.2).
        assert "last_name" not in keys

    def test_every_exposed_field_is_application_visible(self, service):
        schema = service.get_public_field_config(TENANT)
        exposed = {f["key"] for f in schema["fields"]}
        assert exposed == {"first_name", "email", "membership_type", "shirt_size", "nickname"}

    def test_full_resolved_config_has_more_fields_than_the_public_schema(self, service):
        # The public schema is a strict narrowing of the staff field config (R5.2).
        public = service.get_public_field_config(TENANT)["fields"]
        staff = service.get_field_config(TENANT)["fields"]
        assert len(public) < len(staff)


# ── 2. the per-field renderer contract (R5.3) ─────────────────────────────────────────


class TestFieldContract:
    def test_required_is_the_application_required_flag_not_staff_required(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        # first_name is application-required on the form (R4b.6) even though the platform
        # fixed field is optional — the public `required` reflects the FORM flag.
        assert fields["first_name"]["required"] is True
        # nickname is application-selected but NOT application-required → optional on the form.
        assert fields["nickname"]["required"] is False

    def test_label_group_order_type_are_carried(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        nickname = fields["nickname"]
        assert nickname["label"] == {"nl": "Bijnaam", "en": "Nickname"}
        assert nickname["group"] == "overlay"
        assert nickname["type"] == "string"
        assert "order" in nickname and isinstance(nickname["order"], int)
        assert "functional_group" in nickname

    def test_show_when_is_carried_when_present_and_absent_otherwise(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        assert fields["shirt_size"]["show_when"] == {"membership.membership_type": "gewoon"}
        assert "show_when" not in fields["nickname"]

    def test_format_token_is_carried(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        assert fields["email"]["format"] == {"checker": "EMAIL", "params": {}}
        # a field with no validator carries no `format` key.
        assert "format" not in fields["nickname"]

    def test_staff_only_attributes_are_not_exposed(self, service):
        # The public contract must not leak internal field state (R5.2).
        for f in service.get_public_field_config(TENANT)["fields"]:
            for leaked in ("visible", "origin", "provenance", "scope", "member_number_format"):
                assert leaked not in f


# ── 3. the enum application SUBSET is applied ─────────────────────────────────────────


class TestApplicationSubset:
    def test_overlay_enum_exposes_only_the_subset(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        # shirt_size full vocabulary is s/m/l/xl; the subset FILTER narrows the seam's ONE
        # canonical `options` to m/l only (R4a.2/R3.2). Post-03a (F10) the public output is the
        # uniform rich {value,label} shape for EVERY kind — not a bare value list. The subset
        # FILTER is preserved; only the bare-`choices` fallback is retired.
        assert fields["shirt_size"]["options"] == [
            {"value": "m", "label": {"nl": "M", "en": "M"}},
            {"value": "l", "label": {"nl": "L", "en": "L"}},
        ]

    def test_membership_type_exposes_only_the_subset_of_active_catalog(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        values = [o["value"] for o in fields["membership_type"]["options"]]
        # catalog has gewoon + erelid active; the application subset is gewoon only.
        assert values == ["gewoon"]

    def test_field_with_no_subset_exposes_full_choices(self, service):
        # An enum WITHOUT a subset exposes its full canonical vocabulary (back-compatible, R4a.2).
        # Authored as rich `options` (the post-03a canonical source); the public read serves the
        # uniform {value,label} shape for the whole set.
        repo = _ApplicationRepo()
        repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
        overlay = TenantOverlay(
            fields={
                "colour": OverlayField(
                    key="colour",
                    type=FieldType.ENUM,
                    label={"nl": "Kleur", "en": "Colour"},
                    options=tuple(
                        EnumOption(value=v, label={"nl": v, "en": v})
                        for v in ("red", "green", "blue")
                    ),
                    application_visible=True,
                    # no application_choices → full set (back-compatible, R4a.2)
                ),
            }
        )
        svc = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
        )
        fields = _by_key(svc.get_public_field_config(TENANT)["fields"])
        assert [o["value"] for o in fields["colour"]["options"]] == ["red", "green", "blue"]

    def test_subset_with_an_entry_not_in_choices_fails_loud(self):
        # A subset entry not in the field's canonical options is a config bug (R4a.4) — fail-fast.
        # The subset ⊆ vocabulary guard is PRESERVED; it now runs against the seam's ONE `options`.
        repo = _ApplicationRepo()
        overlay = TenantOverlay(
            fields={
                "colour": OverlayField(
                    key="colour",
                    type=FieldType.ENUM,
                    label={"nl": "Kleur", "en": "Colour"},
                    options=(
                        EnumOption(value="red", label={"nl": "red", "en": "red"}),
                        EnumOption(value="green", label={"nl": "green", "en": "green"}),
                    ),
                    application_visible=True,
                    application_choices=("red", "purple"),  # purple ∉ options
                ),
            }
        )
        svc = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
        )
        with pytest.raises(OverlayError):
            svc.get_public_field_config(TENANT)


# ── 4. the 200 body shape ─────────────────────────────────────────────────────────────


class TestBodyShape:
    def test_body_carries_tenant_fields_locales_notice(self, service):
        schema = service.get_public_field_config(TENANT)
        assert schema["tenant_id"] == TENANT
        assert isinstance(schema["fields"], list)
        assert schema["locales"] == ["nl", "en"]
        # the tenant's CURRENT consent-notice version is surfaced (D26/R12.1a).
        assert schema["notice"] == {"version": "v3"}

    def test_notice_version_is_none_when_tenant_authored_none(self):
        repo = _ApplicationRepo()
        repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
        svc = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()})
        )
        schema = svc.get_public_field_config(TENANT)
        assert schema["notice"] == {"version": None}


# ── 4b. REFERENCE (membership_type) subset validates against the LIVE catalog ─────────
#
# Spec 03 Phase 3 task 3.3 (R5.3/R5.4; design C4 REFERENCE). `membership_type` is a REFERENCE
# field: its resolved "choices" are the tenant's LIVE active catalog, NOT a static `field.choices`
# list. So its application subset must be validated against the catalog, and a DANGLING subset
# entry (a referenced type code no longer / not in the catalog) must FAIL LOUD on the public read
# — never be silently dropped from the exposed options. This is the public-read half of the single
# shared `application_choices` authority; the submit half (`validate_application_choice` /
# `_membership_type_subset_error` + the R11 live-catalog reference check) is pinned in
# `test_create_application_membership_type.py`. Together they prove read and submit AGREE: what the
# form offers and what submit accepts cannot drift (R5.4).


def _overlay_membership_type_subset(subset: tuple[str, ...]) -> TenantOverlay:
    """Put `membership_type` on the public form with the given application subset (public-safe codes)."""
    return TenantOverlay(
        overrides={
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                application_required=True,
                application_choices=subset,
            ),
        },
        fields={},
    )


def _service_with_catalog(overlay: TenantOverlay, *active_codes: str) -> MembershipService:
    repo = _ApplicationRepo()
    for order, code in enumerate(active_codes, start=1):
        repo.add_type(TENANT, _entry(TENANT, code, order=order * 10))
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
    )


class TestMembershipTypeReferenceSubsetAgainstLiveCatalog:
    def test_subset_filters_the_public_options_to_the_live_catalog_subset(self):
        # Baseline: a subset that IS a subset of the live catalog exposes exactly those entries,
        # in the declared public-safe set (R5.3 — the form offers only the public-safe types).
        # The public schema emits the BARE key (`membership_type`), not the dotted storage key.
        svc = _service_with_catalog(
            _overlay_membership_type_subset(("gewoon",)), "gewoon", "erelid"
        )
        fields = _by_key(svc.get_public_field_config(TENANT)["fields"])
        values = [o["value"] for o in fields["membership_type"]["options"]]
        assert values == ["gewoon"]

    def test_dangling_reference_fails_loud_not_silently_dropped(self):
        # THE invariant (R5.3): a subset entry whose code is NOT in the tenant's live active
        # catalog is a DANGLING reference. The public read must fail loud (OverlayError), NOT
        # silently drop the entry and serve a short list — a silent drop is exactly the
        # partial-corruption class this spec exists to prevent (root-cause-analysis).
        svc = _service_with_catalog(
            _overlay_membership_type_subset(("gewoon", "ghost")),  # ghost ∉ catalog
            "gewoon",
            "erelid",
        )
        with pytest.raises(OverlayError) as exc:
            svc.get_public_field_config(TENANT)
        # The failure names the dangling entry + the field (keyed by the dotted storage key).
        # Post-03a (F10) the fail-loud boundary is UNIFORM across kinds: it validates the subset
        # against the seam's ONE canonical `options` (for membership_type, the live active
        # catalog), so the message speaks of the field's resolved options rather than a
        # kind-specific `catalog` wording — the dangling reference still fails loud, never a
        # silent drop (the invariant this test guards).
        reason = exc.value.reasons[MEMBERSHIP_TYPE_FIELD_KEY]
        assert "ghost" in reason
        assert "options" in reason.lower()

    def test_dangling_reference_against_an_empty_catalog_also_fails_loud(self):
        # A referenced type against an EMPTY catalog is still a dangling reference — fail loud,
        # never serve an empty dropdown as if the config were valid.
        svc = _service_with_catalog(_overlay_membership_type_subset(("gewoon",)))
        with pytest.raises(OverlayError):
            svc.get_public_field_config(TENANT)

    def test_read_and_submit_use_the_same_authority_no_drift(self):
        # R5.4 — one shared authority for the public read and the submit validator, so the form
        # offer and the accepted set cannot drift. A subset that is a valid subset of the live
        # catalog is exposed by the read; and a submitted value in that same exposed set is what
        # submit accepts. We prove the READ side here against a known-good subset: the exposed
        # option VALUES are exactly the subset the submit side gates against
        # (`_membership_type_subset_error` rejects anything outside this same set — pinned in
        # test_create_application_membership_type.py::TestExposedNonSubsetRejected).
        svc = _service_with_catalog(
            _overlay_membership_type_subset(("gewoon",)), "gewoon", "erelid"
        )
        fields = _by_key(svc.get_public_field_config(TENANT)["fields"])
        exposed = {o["value"] for o in fields["membership_type"]["options"]}
        # `erelid` is a valid, active STAFF type but is withheld from the form — the public read
        # does not offer it, and the submit validator rejects it for the same reason (same subset).
        assert exposed == {"gewoon"}
        assert "erelid" not in exposed

    def test_dangling_reference_fails_loud_on_read_AND_is_refused_at_submit(self):
        # R5.3/R5.4 end-to-end INVARIANT, both halves in one test: a DANGLING `membership_type`
        # subset entry (a code not in the tenant's live active catalog) must FAIL LOUD on the
        # public READ (OverlayError, never a silent drop) AND that same dangling value must be
        # REFUSED at SUBMIT (MemberValidationError, the authoritative R11 live-catalog reference
        # check) — never silently accepted. This pins locally that the public read and the submit
        # validator share ONE authority and cannot drift: a reference the catalog does not back is
        # a loud failure on BOTH sides, not a short list on one and an accepted value on the other.
        #
        # Write-capable repo + submit helpers are imported here (not module-top) to avoid clashing
        # with this read-only file's `_ApplicationRepo` (a catalog-only fake); the read half still
        # uses the read-only service built by `_service_with_catalog`.
        from sam.members.domain._membership_errors import MemberValidationError
        from sam.members.domain.error_codes import MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
        from sam.tests.test_create_application_membership_type import (
            _create,
            _identity_body,
            _overlay_membership_type_exposed,
            _service,
        )

        # READ half: a visible field whose subset references `ghost` (∉ the live catalog) fails
        # loud on the public read, naming the dangling entry against the catalog (REFERENCE).
        read_svc = _service_with_catalog(
            _overlay_membership_type_subset(("gewoon", "ghost")),  # ghost ∉ catalog
            "gewoon",
            "erelid",
        )
        with pytest.raises(OverlayError) as read_exc:
            read_svc.get_public_field_config(TENANT)
        assert "ghost" in read_exc.value.reasons[MEMBERSHIP_TYPE_FIELD_KEY]

        # SUBMIT half: the SAME dangling code, admitted by the field's subset, is still refused by
        # the authoritative live-catalog reference check — the subset gate never lets an off-catalog
        # value through (the read's loud failure and the submit's refusal agree on one authority).
        submit_svc = _service(
            _overlay_membership_type_exposed(subset=("ghost",)),
            catalog=[_entry(TENANT, "gewoon", order=10), _entry(TENANT, "erelid", order=20)],
        )
        with pytest.raises(MemberValidationError) as submit_exc:
            _create(
                submit_svc,
                _identity_body(**{"membership.membership_type": "ghost"}),
                session_key="s1",
            )
        assert (
            submit_exc.value.errors[MEMBERSHIP_TYPE_FIELD_KEY].code
            == MEMBERSHIP_TYPE_UNKNOWN_REFERENCE
        )


# ── 5. the ApplicationService facade delegates verbatim ───────────────────────────────


class TestApplicationServiceFacade:
    def test_facade_returns_the_same_schema_as_the_engine(self, service):
        # The facade gates form load on readiness (task 4.2); supply a send-ready provider so it
        # passes through to the SAME schema the (un-gated) engine read returns.
        facade = ApplicationService(
            service,
            mail_readiness_provider=StaticMailReadinessProvider(
                {TENANT: (True, "h-dcn.nl")}
            ),
        )
        assert facade.get_public_field_config(TENANT) == service.get_public_field_config(TENANT)
