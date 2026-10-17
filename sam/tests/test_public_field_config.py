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
from sam.members.domain.fixed_fields import FieldFormat, FieldType
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
      its full choices (``s``, ``m``, ``l``, ``xl``), conditionally shown (``show_when``).
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
                choices=("s", "m", "l", "xl"),
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
        # shirt_size full choices are s/m/l/xl; the subset is m/l only (R4a.2).
        assert fields["shirt_size"]["options"] == ["m", "l"]

    def test_membership_type_exposes_only_the_subset_of_active_catalog(self, service):
        fields = _by_key(service.get_public_field_config(TENANT)["fields"])
        values = [o["value"] for o in fields["membership_type"]["options"]]
        # catalog has gewoon + erelid active; the application subset is gewoon only.
        assert values == ["gewoon"]

    def test_field_with_no_subset_exposes_full_choices(self, service):
        # Re-configure nickname-less overlay: an enum WITHOUT a subset exposes its full set.
        repo = _ApplicationRepo()
        repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
        overlay = TenantOverlay(
            fields={
                "colour": OverlayField(
                    key="colour",
                    type=FieldType.ENUM,
                    label={"nl": "Kleur", "en": "Colour"},
                    choices=("red", "green", "blue"),
                    application_visible=True,
                    # no application_choices → full set (back-compatible, R4a.2)
                ),
            }
        )
        svc = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({TENANT: overlay})
        )
        fields = _by_key(svc.get_public_field_config(TENANT)["fields"])
        assert fields["colour"]["options"] == ["red", "green", "blue"]

    def test_subset_with_an_entry_not_in_choices_fails_loud(self):
        # A subset entry not in the field's choices is a config bug (R4a.4) — fail-fast.
        repo = _ApplicationRepo()
        overlay = TenantOverlay(
            fields={
                "colour": OverlayField(
                    key="colour",
                    type=FieldType.ENUM,
                    label={"nl": "Kleur", "en": "Colour"},
                    choices=("red", "green"),
                    application_visible=True,
                    application_choices=("red", "purple"),  # purple ∉ choices
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
