"""
S5 Task 3.3 — tests for the resolved **field-config** endpoint (design C3 + C8, R2.3/R2.4).

These pin the read the presentation-only frontend renders: the domain layer is authoritative
(verify-before-trust — the frontend holds NO rules), so the endpoint returns

- the resolved field config = fixed base ⊕ per-tenant overlay (design C3), and
- the ``membership_type`` field's ``options`` = the tenant's **ACTIVE** Lidmaatschap Beheer
  catalog entries (design C8), ordered by ``(order, type_code)``, soft-deleted excluded.

Two layers are covered:

1. **Domain** — :meth:`MembershipService.get_field_config` composes the resolver + the
   ``active_only=True`` catalog read and injects the active entries as the ``membership_type``
   options; the shape is JSON-friendly (enums flattened to strings).
2. **Edge dispatch** — a granted + authorized ``GET /members/field-config`` returns **200**
   with that config (not the old 501 stub), tenant-scoped by the verified ``tenant_id``.

A tiny in-memory fake :class:`MembersRepository` + a :class:`StaticOverlayProvider` back the
service (no boto3, no AWS), mirroring the fake-repo pattern in the sibling read tests.

Validates: Requirements R2.3, R2.4
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldOrigin,
    FieldResolver,
    FieldScope,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption, FieldFormat, FieldType
from sam.members.domain.membership_service import (
    MEMBERSHIP_TYPE_FIELD_KEY,
    MembershipService,
)
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.handler import app

# ---------------------------------------------------------------------------
# In-memory fake repository (catalog surface only — the service depends on the Protocol)
# ---------------------------------------------------------------------------


class FakeCatalogRepository:
    """Minimal in-memory :class:`MembersRepository` exposing the catalog read used here.

    Stores catalog entries keyed by ``tenant_id`` so a read cannot cross tenants (the same
    structural isolation the real repository enforces). ``list_membership_types`` mirrors the
    real contract: ``active_only=True`` drops soft-deleted entries; results are ordered by
    ``(order, type_code)``.
    """

    def __init__(self):
        self.catalog: dict[str, list[MembershipTypeEntry]] = {}

    def add_type(self, tenant_id: str, entry: MembershipTypeEntry) -> None:
        self.catalog.setdefault(tenant_id, []).append(entry)

    def list_membership_types(self, tenant_id, *, active_only=False):
        entries = list(self.catalog.get(tenant_id, []))
        if active_only:
            entries = [e for e in entries if e.active]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    # -- unused-by-this-read Protocol members (raise if touched) -----------
    def get_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_members(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def delete_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def get_membership(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_memberships(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_member_payments(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def get_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def deactivate_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


def _entry(tenant, code, *, label=None, active=True, order=0):
    return MembershipTypeEntry(
        tenant_id=tenant,
        type_code=code,
        label=label or {"nl": code.title(), "en": code.title()},
        active=active,
        order=order,
    )


@pytest.fixture()
def repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    # Deliberately out of order + one soft-deleted to pin ordering + exclusion.
    r.add_type(
        "h-dcn",
        _entry("h-dcn", "donateur", label={"nl": "Donateur", "en": "Donor"}, order=20),
    )
    r.add_type(
        "h-dcn",
        _entry("h-dcn", "erelid", label={"nl": "Erelid", "en": "Honorary"}, order=10),
    )
    r.add_type(
        "h-dcn",
        _entry("h-dcn", "sponsor", label={"nl": "Sponsor", "en": "Sponsor"}, order=30),
    )
    r.add_type(
        "h-dcn",
        _entry(
            "h-dcn", "retired", label={"nl": "Oud", "en": "Old"}, active=False, order=5
        ),
    )
    # A different tenant — must be structurally invisible to h-dcn's config.
    r.add_type("other", _entry("other", "member", order=10))
    return r


# ---------------------------------------------------------------------------
# Domain — MembershipService.get_field_config
# ---------------------------------------------------------------------------


class TestGetFieldConfigDomain:
    def test_includes_fixed_base_fields_grouped(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        assert config["tenant_id"] == "h-dcn"
        # personal + membership fixed groups are present (fixed base, design C3).
        assert "personal" in config["by_group"]
        assert "membership" in config["by_group"]
        # Every fixed field is present with origin=fixed.
        keys = {(f["group"], f["key"]) for f in config["fields"]}
        assert ("personal", "first_name") in keys
        assert ("membership", "member_number") in keys
        assert ("membership", "membership_type") in keys

    def test_membership_type_options_are_active_catalog_entries_ordered(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        mt = next(
            f
            for f in config["fields"]
            if f["group"] == "membership" and f["key"] == "membership_type"
        )
        # It is a REFERENCE field carrying the active catalog entries as its options.
        assert mt["type"] == FieldType.REFERENCE.value
        assert [o["value"] for o in mt["options"]] == ["erelid", "donateur", "sponsor"]
        # i18n labels ride along for presentation.
        assert mt["options"][0]["label"] == {"nl": "Erelid", "en": "Honorary"}

    def test_soft_deleted_types_are_excluded_from_options(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        values = {o["value"] for o in config["membership_type_options"]}
        assert "retired" not in values

    def test_standalone_membership_type_options_match_the_field_options(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        mt = next(f for f in config["fields"] if f["key"] == "membership_type")
        assert config["membership_type_options"] == mt["options"]

    def test_membership_type_field_key_constant_matches(self):
        assert MEMBERSHIP_TYPE_FIELD_KEY == "membership.membership_type"

    def test_config_is_tenant_scoped(self, repo):
        # 'other' tenant's types never leak into h-dcn's config, and vice-versa.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        h = service.get_field_config("h-dcn")
        other = service.get_field_config("other")
        assert {o["value"] for o in h["membership_type_options"]} == {
            "erelid",
            "donateur",
            "sponsor",
        }
        assert {o["value"] for o in other["membership_type_options"]} == {"member"}

    def test_overlay_variable_fields_appear_in_config(self, repo):
        # A tenant overlay (design C3) adds a variable "club detail" field → origin=variable.
        overlay = TenantOverlay(
            fields={
                "motor_type": OverlayField(
                    key="motor_type",
                    type=FieldType.STRING,
                    label={"nl": "Motor", "en": "Motorcycle"},
                    order=10,
                )
            }
        )
        service = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay})
        )
        config = service.get_field_config("h-dcn")

        overlay_fields = [
            f for f in config["fields"] if f["origin"] == FieldOrigin.VARIABLE.value
        ]
        assert [f["key"] for f in overlay_fields] == ["motor_type"]
        assert "overlay" in config["by_group"]

    def test_empty_overlay_resolves_to_fixed_base_plus_calculated(self, repo):
        # With no overlay, the resolved config = the fixed base ⊕ the platform CALCULATED
        # (derived, read-only) fields — no VARIABLE (tenant overlay) fields (task 1.3).
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        origins = {f["origin"] for f in config["fields"]}
        assert origins == {FieldOrigin.FIXED.value, FieldOrigin.CALCULATED.value}
        assert not any(
            f["origin"] == FieldOrigin.VARIABLE.value for f in config["fields"]
        )

    def test_config_is_json_serializable(self, repo):
        # The edge json.dumps the result — no enums/dataclasses may leak through.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        json.dumps(config)  # must not raise

    def test_status_enum_field_carries_its_choices_as_options(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        status = next(f for f in config["fields"] if f["key"] == "status")
        # S5c task 4.4: the status Fixed enum now surfaces RICH options ({value,label,roles?})
        # so the modals can render bilingual labels (R4.11) — not a bare value list.
        option_values = {o["value"] for o in status["options"]}
        assert "active" in option_values
        active = next(o for o in status["options"] if o["value"] == "active")
        assert active["label"] == {"nl": "Actief", "en": "Active"}

    def test_tenant_with_no_catalog_has_empty_options(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("unknown-tenant")
        assert config["membership_type_options"] == []
        # ...but the fixed base fields are still resolved.
        assert any(f["key"] == "membership_type" for f in config["fields"])


class TestGetFieldConfigServesApplicationAttributes:
    """spec 11 — the staff field-config read serves the four per-field APPLICATION attributes.

    Regression guard for the Application Form Builder save→reseed bug: the builder authors
    `application_visible` / `application_required` / `application_choices` / `format` onto
    `config#fields`, then reads them BACK through `get_field_config` to re-seed its toggles after
    a save. `_serialize_field` previously DROPPED them (resolved onto `ResolvedField`, used by the
    public read/create path, but never serialized to the staff read), so every field reseeded OFF
    after a save even though the write persisted. These pin that the staff serializer emits them.
    """

    def test_overlay_application_attributes_round_trip_on_the_staff_read(self, repo):
        overlay = TenantOverlay(
            fields={
                "magazine_pref": OverlayField(
                    key="magazine_pref",
                    type=FieldType.ENUM,
                    label={"nl": "Clubblad", "en": "Magazine"},
                    choices=("Geen", "Papier", "Digitaal"),
                    order=20,
                    application_visible=True,
                    application_required=True,
                    application_choices=("Papier", "Digitaal"),
                    format=FieldFormat(checker="EMAIL", params={"strict": True}),
                )
            }
        )
        service = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay})
        )
        config = service.get_field_config("h-dcn")

        field = next(f for f in config["fields"] if f["key"] == "magazine_pref")
        assert field["application_visible"] is True
        assert field["application_required"] is True
        assert field["application_choices"] == ["Papier", "Digitaal"]
        assert field["format"] == {"checker": "EMAIL", "params": {"strict": True}}

    def test_unauthored_field_defaults_are_served_not_omitted(self, repo):
        # A field that authors NONE of the four attributes still carries them at their safe
        # defaults so the builder reseeds a coherent OFF state (never `undefined`-vs-false drift).
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        f = next(iter(config["fields"]))
        assert f["application_visible"] is False
        assert f["application_required"] is False
        assert f["application_choices"] is None
        assert f["format"] is None

    def test_application_attributes_are_json_serializable(self, repo):
        overlay = TenantOverlay(
            fields={
                "motor_type": OverlayField(
                    key="motor_type",
                    type=FieldType.STRING,
                    label={"nl": "Motor", "en": "Motorcycle"},
                    application_visible=True,
                    format=FieldFormat(checker="IBAN"),
                )
            }
        )
        service = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay})
        )
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


# ---------------------------------------------------------------------------
# Edge dispatch — GET /members/field-config
# ---------------------------------------------------------------------------


@pytest.fixture()
def inject_service(monkeypatch, repo):
    overlay = TenantOverlay(
        fields={
            "motor_type": OverlayField(
                key="motor_type", type=FieldType.STRING, label={"nl": "Motor"}, order=10
            )
        }
    )
    service = MembershipService(
        repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay})
    )
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    return service


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read",),
    groups=("Regio_All",),
    sub="admin-sub",
):
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": None,
        "body": None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "cognito:groups": list(groups),
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


def test_field_config_route_returns_200_not_501(inject_service):
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    data = _data(resp)
    assert data["tenant_id"] == "h-dcn"


def test_field_config_route_carries_active_membership_type_options(inject_service):
    resp = app.handler(_event("GET", "/members/field-config"))
    data = _data(resp)
    values = [o["value"] for o in data["membership_type_options"]]
    assert values == ["erelid", "donateur", "sponsor"]
    assert "retired" not in values


def test_field_config_route_reflects_the_tenant_overlay(inject_service):
    resp = app.handler(_event("GET", "/members/field-config"))
    data = _data(resp)
    assert any(
        f["key"] == "motor_type" and f["origin"] == "variable" for f in data["fields"]
    )


def test_field_config_route_resolves_before_get_member(inject_service):
    # /members/field-config must not be swallowed by /members/{member_id}.
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    assert "fields" in _data(resp)


def test_field_config_route_requires_auth():
    # No verified claims → 401 (the task-3.0 gate still applies to this route).
    resp = app.handler(
        {"httpMethod": "GET", "path": "/members/field-config", "headers": {}}
    )
    assert resp["statusCode"] in (401, 403)


# ---------------------------------------------------------------------------
# S5c Task 3.2 — view contexts exposed on the field-config payload (design C-VIEW, R5.1)
#
# The tenant's view contexts land as a sibling top-level ``view_contexts`` field on the
# field-config response. Empty-is-valid: a tenant that authored none surfaces EXACTLY ONE
# default context (over all visible fields), never a crash and never an empty list.
#
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------

# Phase 2 step (c) (task 4.1/4.2): the server stopped SERIALIZING `view_contexts`. The former
# `TestGetFieldConfigViewContextsDomain` domain cases and the two edge-dispatch cases that
# round-tripped authored/default contexts were removed with the surface they covered — the
# response no longer carries a `view_contexts` key and the service no longer accepts a
# `view_contexts_provider`. (The `view_contexts` param/projection/domain modules themselves are
# deleted in step (d), tasks 4.3/4.4.)


# ---------------------------------------------------------------------------
# retire-members-status-lifecycle-engine (design C2 / §F) — the field-config payload
# NO LONGER carries a `lifecycle` block. The membership lifecycle state engine was
# retired: `status` is now a plain, tenant-driven OPEN enum edited as an ordinary field
# (via the member edit modal), so there is no transition graph to project and the SPA
# offers no transition targets. The former `TestGetFieldConfigLifecycleDomain` domain
# cases and the two edge-dispatch cases that round-tripped the declared/None lifecycle
# block were removed with the surface they covered. These replacement cases pin the
# OMISSION — the payload is otherwise identical (the fixed/overlay/analytics cases are
# unchanged, and `status` still surfaces its seed options, pinned in
# `test_status_enum_field_carries_its_choices_as_options` above).
# ---------------------------------------------------------------------------


class TestGetFieldConfigOmitsLifecycle:
    def test_served_config_has_no_lifecycle_key(self, repo):
        # The served field-config payload no longer carries a `lifecycle` key (the engine
        # is retired; status is a plain open enum).
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        assert "lifecycle" not in config

    def test_config_without_lifecycle_is_json_serializable(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


def test_field_config_route_omits_the_lifecycle_key(inject_service):
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    assert "lifecycle" not in _data(resp)


# ---------------------------------------------------------------------------
# members-analytics-role-removal Step B (task 2.1) — the served field-config payload
# OMITS the `analytics` role-config key.
#
# The analytics role-config slice (jubilee_rule / field_roles / address_mapping) is removed:
# the SAM writer no longer serializes it and no longer carries an `analytics` key on the
# served field-config payload. The former `TestGetFieldConfigAnalyticsDomain` domain cases
# and the two edge-dispatch cases that round-tripped the authored/None analytics block were
# removed with the surface they covered. These replacement cases pin the omission — the
# payload is otherwise identical (the surrounding fixed/overlay/lifecycle/mail cases above
# are unchanged). (The SAM domain classes AnalyticsConfig/AnalyticsRole/JubileeRule/
# AddressMapping are removed later in Step C, task 3.)
# ---------------------------------------------------------------------------


class TestGetFieldConfigOmitsAnalytics:
    def test_served_config_has_no_analytics_key(self, repo):
        # The served field-config payload no longer carries an `analytics` role-config key.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        assert "analytics" not in config

    def test_config_without_analytics_is_json_serializable(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


def test_field_config_route_omits_the_analytics_key(inject_service):
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    assert "analytics" not in _data(resp)


# ---------------------------------------------------------------------------
# application-form-builder (spec 11) Task 1.3 — the served field-config payload carries
# the PLATFORM-DEFINED set of field-format checker tokens (S4/R3.3). Serving the set from
# the SAM `field_formats` registry keeps the Application Form Builder's format dropdown in
# lockstep with the platform registry (no hand-maintained client-side mirror that can drift).
#
# Validates: Requirements R3.3
# ---------------------------------------------------------------------------


class TestGetFieldConfigServesFormatTokens:
    def test_served_config_carries_the_registry_tokens(self, repo):
        from sam.members.domain import field_formats

        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        # The set is served verbatim from the registry (EMAIL, IBAN today), sorted for a
        # stable order; it stays in lockstep with the platform registry by construction.
        assert config["field_format_tokens"] == sorted(field_formats.known_tokens())
        assert "EMAIL" in config["field_format_tokens"]
        assert "IBAN" in config["field_format_tokens"]

    def test_format_tokens_are_a_sorted_list_of_strings(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        tokens = service.get_field_config("h-dcn")["field_format_tokens"]
        assert isinstance(tokens, list)
        assert all(isinstance(t, str) for t in tokens)
        assert tokens == sorted(tokens)

    def test_format_tokens_present_even_for_an_unconfigured_tenant(self, repo):
        # The token set is platform-defined, not tenant data — an un-authored tenant still
        # gets the full registry (empty-is-valid: never a crash, never an empty omission).
        from sam.members.domain import field_formats

        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("unknown-tenant")
        assert config["field_format_tokens"] == sorted(field_formats.known_tokens())

    def test_config_with_format_tokens_is_json_serializable(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


def test_field_config_route_carries_the_format_tokens(inject_service):
    from sam.members.domain import field_formats

    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    data = _data(resp)
    assert data["field_format_tokens"] == sorted(field_formats.known_tokens())


class TestGetFieldConfigDoesNotSurfaceRawOverlay:
    """spec 03 task 5.3 (steering 39 guard) — the staff field-config read serves ONLY the Flat_View.

    Reversal of the earlier spec-11 "serve the raw overlay" behaviour: serving the raw stored
    `config#fields` shape (`field_overlay` / `overrides` / `fixed_overrides` / dotted
    `{group}.{key}` keys) to the frontend was the root cause of the partial-overlay-overwrites-
    full-record drift (`.kiro/specs/Members/root-cause-analysis.md`). Under the Change-Op model
    (spec 03, design C3 / R2.3 / R3, steering 39) the raw storage shape MUST NOT cross the
    repository boundary into an API response.

    The authoring editors now seed from the Flat_View (`fields` / `by_group` / `functional_groups`,
    each resolved field carrying its four application attributes) and WRITE by domain identity
    (Change-Ops) — they never receive or reconstruct a storage key. The raw reader
    (`get_raw_fields_overlay`) stays an INTERNAL helper used only by the Change-Op CRUD service's
    validate-and-place step.
    """

    #: The raw-shape keys steering 39 forbids in an API response.
    _RAW_SHAPE_KEYS = ("field_overlay", "overrides", "fixed_overrides")

    class _RawProvider:
        """An overlay provider exposing the raw-overlay read (like the production reader).

        Even when the provider CAN serve the raw shape, `get_field_config` must not surface it —
        the guard is on the response, not on the provider's capabilities.
        """

        def __init__(self, overlay):
            self._overlay = overlay

        def get_overlay(
            self, tenant_id
        ):  # resolver seam — empty typed overlay is fine here
            from sam.members.domain.field_resolver import TenantOverlay

            return TenantOverlay()

        def get_raw_fields_overlay(self, tenant_id):
            return self._overlay

    def test_field_overlay_is_not_surfaced_even_when_the_provider_exposes_it(self, repo):
        """steering 39 guard: no raw-shape key crosses the boundary, even with a raw-capable provider."""
        overlay = {
            "fields": {
                "motor_type": {
                    "key": "motor_type",
                    "type": "string",
                    "application_visible": True,
                }
            },
            "fixed_overrides": {"personal.city": {"order": 3}},
            "functional_groups": [{"key": "address", "order": 1}],
        }
        service = MembershipService(repo, overlay_provider=self._RawProvider(overlay))
        config = service.get_field_config("h-dcn")
        for raw_key in self._RAW_SHAPE_KEYS:
            assert raw_key not in config, (
                f"get_field_config leaked the raw-shape key {raw_key!r} into its response "
                "— steering 39 forbids the raw storage shape crossing the repository boundary"
            )
        # No dotted `{group}.{key}` top-level key leaked either.
        assert not any("." in k for k in config), (
            f"get_field_config leaked a dotted storage key: {sorted(config)}"
        )

    def test_field_overlay_is_not_surfaced_when_provider_lacks_the_raw_read(self, repo):
        """A provider WITHOUT the raw read must also yield a response free of raw-shape keys."""
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        for raw_key in self._RAW_SHAPE_KEYS:
            assert raw_key not in config

    def test_flat_view_is_complete_for_the_authoring_editors(self, repo):
        """The Flat_View carries everything the builder needs — so retiring `field_overlay` loses nothing.

        Each resolved field (served under `fields`) carries the four application attributes
        (`application_visible`, `application_required`, `application_choices`, `format`) plus its
        definition attributes — the exact data the Application Form Builder previously re-seeded from
        the raw `field_overlay`. Confirms the design claim that the Flat_View is sufficient (C3).
        """
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        # The Flat_View surfaces the UI needs are present.
        assert "fields" in config and config["fields"], "Flat_View `fields` is empty"
        assert "by_group" in config
        assert "functional_groups" in config

        # Every served field carries the four application attributes (the builder's re-seed source).
        for field_payload in config["fields"]:
            for app_attr in (
                "application_visible",
                "application_required",
                "application_choices",
                "format",
            ):
                assert app_attr in field_payload, (
                    f"field {field_payload.get('key')!r} is missing {app_attr!r} in the Flat_View "
                    "— the builder could not re-seed its on-form controls without the raw overlay"
                )
            # And the definition attributes the configurator edits.
            for def_attr in (
                "key",
                "group",
                "type",
                "label",
                "visible",
                "order",
                "functional_group",
            ):
                assert def_attr in field_payload

    def test_field_config_is_json_serializable_without_the_overlay(self, repo):
        service = MembershipService(
            repo,
            overlay_provider=self._RawProvider(
                {"fields": {}, "fixed_overrides": {}, "functional_groups": []}
            ),
        )
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


# ---------------------------------------------------------------------------
# 03a task 4 (C4 / F8 / F9) — the read-assembly seam populates ONE canonical `options`
# uniformly; the staff `_serialize_field` serializer consumes that single `options` with NO
# per-kind branch and NO `field.choices` fallback, and the pure resolver stays catalog-free.
#
# Validates: Requirements 2.1, 2.6 · Components: C4, F8, F9
# ---------------------------------------------------------------------------


def _scope_service(repo, *, dim_values=("noord", "zuid")):
    """A service whose `region` overlay enum is backed by a tenant scope dimension (no inline
    options) — so its `options` can ONLY come from the injected scope_vocab at the seam."""
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
            "h-dcn": [
                ScopeDimension(
                    key="region",
                    field="region",
                    enabled=True,
                    values=dim_values,
                )
            ]
        }
    )
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({"h-dcn": overlay}),
        scope_config_provider=scope,
    )


class TestReadAssemblySeamPopulatesOptionsUniformly:
    def test_reference_options_come_from_the_active_catalog_at_the_seam(self, repo):
        # reference (membership_type): the ONE `options` is the injected active catalog — the
        # F8 reference population, now done in the uniform seam pass (not a one-off merge).
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        mt = next(f for f in config["fields"] if f["key"] == "membership_type")
        assert [o["value"] for o in mt["options"]] == ["erelid", "donateur", "sponsor"]

    def test_inline_enum_options_are_the_rich_resolved_options(self, repo):
        # inline enum (status): the ONE `options` is the field's own rich {value,label} options.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        status = next(f for f in config["fields"] if f["key"] == "status")
        active = next(o for o in status["options"] if o["value"] == "active")
        assert active["label"] == {"nl": "Actief", "en": "Active"}

    def test_scope_backed_options_come_from_the_injected_scope_vocab(self, repo):
        # scope-backed (region): the field declares NO inline options — its `options` can only be
        # the scope dimension's values, projected to rich options AT THE SEAM (not from the pure
        # resolver, not from `field.choices`). This is the uniform scope population.
        service = _scope_service(repo, dim_values=("noord", "zuid", "oost"))
        config = service.get_field_config("h-dcn")
        region = next(f for f in config["fields"] if f["key"] == "region")
        assert [o["value"] for o in region["options"]] == ["noord", "zuid", "oost"]
        # Rich option shape (value + label), uniform with every other kind.
        assert all("value" in o and "label" in o for o in region["options"])

    def test_bare_choices_enum_no_longer_falls_back_to_choices(self, repo):
        # F9: the staff serializer drops the `elif field.choices is not None` fallback. A bare-
        # `choices` overlay enum (built directly through the resolver, bypassing the C5/C7
        # canonicalisation) has NO inline `options` and is NOT scope-backed, so the seam resolves
        # NO canonical source and the served `options` is None — the deliberate new behavior. Such
        # a declared-but-unpropagated source is the ASYMMETRY task 9 (C6) strengthens into a loud
        # error at this same seam; until then it degrades to None rather than list(field.choices).
        overlay = TenantOverlay(
            fields={
                "magazine_pref": OverlayField(
                    key="magazine_pref",
                    type=FieldType.ENUM,
                    label={"nl": "Clubblad", "en": "Magazine"},
                    choices=("Geen", "Papier", "Digitaal"),
                    order=20,
                )
            }
        )
        service = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay})
        )
        config = service.get_field_config("h-dcn")
        mag = next(f for f in config["fields"] if f["key"] == "magazine_pref")
        assert mag["options"] is None

    def test_non_selectable_field_has_no_options(self, repo):
        # A plain string field declares no selectable source → options is None (unchanged).
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        first_name = next(f for f in config["fields"] if f["key"] == "first_name")
        assert first_name["options"] is None


class TestResolverStaysCatalogFree:
    """C4: the uniform population lives at the read-assembly seam — the pure FieldResolver is
    NOT given catalog/DB access and does not read the catalog. Asserted, not modified."""

    def test_resolver_is_constructed_with_only_the_overlay_provider(self):
        resolver = FieldResolver(StaticOverlayProvider({}))
        # No catalog / repository / scope-config attribute is attached to the resolver — its sole
        # dependency is the overlay provider (scope arrives as an injected `scope_vocab` arg).
        assert resolver._provider is not None
        assert not hasattr(resolver, "_repo")
        assert not hasattr(resolver, "_catalog")
        assert not hasattr(resolver, "_active_membership_type_options")

    def test_resolver_resolve_takes_no_catalog_and_leaves_membership_type_options_empty(self):
        # Resolving WITHOUT any catalog yields a membership_type field whose inline resolved
        # options are empty — the active catalog is attached LATER, at the seam, not here. This
        # pins that reference options are a seam concern, never a resolver catalog read.
        resolver = FieldResolver(StaticOverlayProvider({}))
        config = resolver.resolve("h-dcn")
        mt = config.field(MEMBERSHIP_TYPE_FIELD_KEY)
        assert mt is not None
        assert not mt.options  # resolver attaches no catalog vocabulary
