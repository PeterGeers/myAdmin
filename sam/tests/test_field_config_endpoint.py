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

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldOrigin,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import FieldType
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
    r.add_type("h-dcn", _entry("h-dcn", "donateur", label={"nl": "Donateur", "en": "Donor"}, order=20))
    r.add_type("h-dcn", _entry("h-dcn", "erelid", label={"nl": "Erelid", "en": "Honorary"}, order=10))
    r.add_type("h-dcn", _entry("h-dcn", "sponsor", label={"nl": "Sponsor", "en": "Sponsor"}, order=30))
    r.add_type("h-dcn", _entry("h-dcn", "retired", label={"nl": "Oud", "en": "Old"}, active=False, order=5))
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
        assert ("personal", "name") in keys
        assert ("membership", "member_number") in keys
        assert ("membership", "membership_type") in keys

    def test_membership_type_options_are_active_catalog_entries_ordered(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        mt = next(
            f for f in config["fields"] if f["group"] == "membership" and f["key"] == "membership_type"
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
        assert {o["value"] for o in h["membership_type_options"]} == {"erelid", "donateur", "sponsor"}
        assert {o["value"] for o in other["membership_type_options"]} == {"member"}

    def test_overlay_variable_fields_appear_in_config(self, repo):
        # A tenant overlay (design C3) adds a variable "club detail" field → origin=variable.
        overlay = TenantOverlay(
            fields={
                "motor_type": OverlayField(
                    key="motor_type", type=FieldType.STRING, label={"nl": "Motor", "en": "Motorcycle"}, order=10
                )
            }
        )
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay}))
        config = service.get_field_config("h-dcn")

        overlay_fields = [f for f in config["fields"] if f["origin"] == FieldOrigin.VARIABLE.value]
        assert [f["key"] for f in overlay_fields] == ["motor_type"]
        assert "overlay" in config["by_group"]

    def test_empty_overlay_resolves_to_fixed_base_only(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        assert all(f["origin"] == FieldOrigin.FIXED.value for f in config["fields"])

    def test_config_is_json_serializable(self, repo):
        # The edge json.dumps the result — no enums/dataclasses may leak through.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        json.dumps(config)  # must not raise

    def test_status_enum_field_carries_its_choices_as_options(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        status = next(f for f in config["fields"] if f["key"] == "status")
        assert "active" in status["options"]

    def test_tenant_with_no_catalog_has_empty_options(self, repo):
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("unknown-tenant")
        assert config["membership_type_options"] == []
        # ...but the fixed base fields are still resolved.
        assert any(f["key"] == "membership_type" for f in config["fields"])


# ---------------------------------------------------------------------------
# Edge dispatch — GET /members/field-config
# ---------------------------------------------------------------------------


@pytest.fixture()
def inject_service(monkeypatch, repo):
    overlay = TenantOverlay(
        fields={
            "motor_type": OverlayField(key="motor_type", type=FieldType.STRING, label={"nl": "Motor"}, order=10)
        }
    )
    service = MembershipService(repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay}))
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    return service


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(method, path, *, tenant="h-dcn", capabilities=("members:read",), groups=("Regio_All",), sub="admin-sub"):
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
    assert any(f["key"] == "motor_type" and f["origin"] == "variable" for f in data["fields"])


def test_field_config_route_resolves_before_get_member(inject_service):
    # /members/field-config must not be swallowed by /members/{member_id}.
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    assert "fields" in _data(resp)


def test_field_config_route_requires_auth():
    # No verified claims → 401 (the task-3.0 gate still applies to this route).
    resp = app.handler({"httpMethod": "GET", "path": "/members/field-config", "headers": {}})
    assert resp["statusCode"] in (401, 403)
