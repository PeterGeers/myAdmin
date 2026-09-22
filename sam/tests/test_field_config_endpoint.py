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
        assert ("personal", "first_name") in keys
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

    def test_empty_overlay_resolves_to_fixed_base_plus_calculated(self, repo):
        # With no overlay, the resolved config = the fixed base ⊕ the platform CALCULATED
        # (derived, read-only) fields — no VARIABLE (tenant overlay) fields (task 1.3).
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        origins = {f["origin"] for f in config["fields"]}
        assert origins == {FieldOrigin.FIXED.value, FieldOrigin.CALCULATED.value}
        assert not any(f["origin"] == FieldOrigin.VARIABLE.value for f in config["fields"])

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


# ---------------------------------------------------------------------------
# S5c Task 3.2 — view contexts exposed on the field-config payload (design C-VIEW, R5.1)
#
# The tenant's view contexts land as a sibling top-level ``view_contexts`` field on the
# field-config response. Empty-is-valid: a tenant that authored none surfaces EXACTLY ONE
# default context (over all visible fields), never a crash and never an empty list.
#
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------

from sam.members.domain.view_contexts import (
    DEFAULT_CONTEXT_KEY,
    StaticViewContextsProvider,
    ViewContext,
)


def _financial_context():
    return ViewContext(
        key="financial",
        label={"nl": "Financieel", "en": "Financial"},
        permission_roles=("Penningmeester",),
        columns=("member_number", "iban", "payment_method"),
        filterable_columns=("payment_method",),
        default_sort={"field": "member_number", "direction": "asc"},
        page_size=25,
    )


class TestGetFieldConfigViewContextsDomain:
    def test_view_contexts_populated_case_round_trips_authored_contexts(self, repo):
        provider = StaticViewContextsProvider({"h-dcn": [_financial_context()]})
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            view_contexts_provider=provider,
        )
        config = service.get_field_config("h-dcn")

        assert [vc["key"] for vc in config["view_contexts"]] == ["financial"]
        vc = config["view_contexts"][0]
        assert vc["label"] == {"nl": "Financieel", "en": "Financial"}
        assert vc["permission_roles"] == ["Penningmeester"]
        assert vc["columns"] == ["member_number", "iban", "payment_method"]
        assert vc["filterable_columns"] == ["payment_method"]
        assert vc["default_sort"] == {"field": "member_number", "direction": "asc"}
        assert vc["page_size"] == 25
        assert vc["is_default"] is False

    def test_view_contexts_empty_case_returns_exactly_one_default_context(self, repo):
        # A tenant that authored NO contexts → exactly one default context (empty-is-valid).
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            view_contexts_provider=StaticViewContextsProvider({}),
        )
        config = service.get_field_config("h-dcn")

        assert len(config["view_contexts"]) == 1
        default = config["view_contexts"][0]
        assert default["key"] == DEFAULT_CONTEXT_KEY
        assert default["is_default"] is True
        # The default context references no field keys ("all visible fields" sentinel).
        assert default["columns"] == []
        assert default["filterable_columns"] == []

    def test_view_contexts_default_when_no_provider_injected(self, repo):
        # A service built without a view-contexts provider still surfaces one default context.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        assert len(config["view_contexts"]) == 1
        assert config["view_contexts"][0]["key"] == DEFAULT_CONTEXT_KEY

    def test_view_contexts_are_json_serializable(self, repo):
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            view_contexts_provider=StaticViewContextsProvider({"h-dcn": [_financial_context()]}),
        )
        config = service.get_field_config("h-dcn")
        json.dumps(config)  # must not raise (labels + primitives are pure JSON)

    def test_view_contexts_are_tenant_scoped(self, repo):
        provider = StaticViewContextsProvider({"h-dcn": [_financial_context()]})
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            view_contexts_provider=provider,
        )
        h = service.get_field_config("h-dcn")
        other = service.get_field_config("other")
        assert [vc["key"] for vc in h["view_contexts"]] == ["financial"]
        # 'other' authored none → its own single default, never h-dcn's context.
        assert [vc["key"] for vc in other["view_contexts"]] == [DEFAULT_CONTEXT_KEY]


# ---------------------------------------------------------------------------
# S5c Task 3.2 — edge dispatch: GET /members/field-config carries view_contexts
# ---------------------------------------------------------------------------


@pytest.fixture()
def inject_service_with_contexts(monkeypatch, repo):
    service = MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({}),
        view_contexts_provider=StaticViewContextsProvider({"h-dcn": [_financial_context()]}),
    )
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    return service


def test_field_config_route_carries_authored_view_contexts(inject_service_with_contexts):
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    data = _data(resp)
    assert [vc["key"] for vc in data["view_contexts"]] == ["financial"]
    assert data["view_contexts"][0]["label"] == {"nl": "Financieel", "en": "Financial"}


def test_field_config_route_returns_one_default_context_when_none_authored(inject_service):
    # inject_service wires a service with NO view-contexts provider → one default context.
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    data = _data(resp)
    assert len(data["view_contexts"]) == 1
    assert data["view_contexts"][0]["key"] == DEFAULT_CONTEXT_KEY
    assert data["view_contexts"][0]["is_default"] is True


# ---------------------------------------------------------------------------
# S5c Task 4.6 — the module's declared lifecycle exposed on the field-config payload
# (design C2 / C-SURFACE, R5.7). The single + bulk transition modals read their
# candidate target states from this block ONLY (never a hardcoded status list):
#
#   - a tenant WITH a configured lifecycle → the declarative transition graph is
#     projected as `allowed_transitions` ({fromState: [toState, ...]}) + `initial_state`
#     + `allowed_states`, and the `context.approved`-guarded edges are surfaced in
#     `requires_approval` (deliberately limited — only what the module already models);
#   - a tenant with NO configured lifecycle → `lifecycle` is `None`, so the SPA offers
#     NO transition targets (deny-by-default at the UI). The module stays authoritative
#     regardless (it re-validates every transition and answers 409 with reasons).
#
# Validates: Requirements 5.7
# ---------------------------------------------------------------------------

from sam.members.domain.fixed_fields import MembershipStatus as _MS
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)


class TestGetFieldConfigLifecycleDomain:
    def test_lifecycle_absent_when_no_provider_injected(self, repo):
        # Deliberately limited + deny-by-default: a service built without a lifecycle
        # provider surfaces `lifecycle: None`, so the SPA offers no transition targets.
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")
        assert config["lifecycle"] is None

    def test_lifecycle_none_for_tenant_without_configured_lifecycle(self, repo):
        # The provider knows h-dcn only → any OTHER tenant gets `lifecycle: None`.
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        )
        config = service.get_field_config("other")
        assert config["lifecycle"] is None

    def test_lifecycle_projects_the_declared_transition_graph(self, repo):
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        )
        lifecycle = service.get_field_config("h-dcn")["lifecycle"]

        assert lifecycle is not None
        # The state vocabulary + initial state come straight from the module config.
        assert lifecycle["allowed_states"] == [
            "application", "pending", "active", "suspended", "lapsed", "left",
        ]
        assert lifecycle["initial_state"] == "application"

        # `allowed_transitions` is the {fromState: [toState, ...]} map the single modal
        # reads for a member's current state (and the bulk modal unions). It carries
        # EXACTLY the module's declared edges — never a hardcoded status list.
        at = lifecycle["allowed_transitions"]
        assert at["application"] == ["pending"]
        assert at["pending"] == ["active", "left"]
        assert set(at["active"]) == {"suspended", "lapsed", "left"}
        # A terminal state declares no outgoing edges → it is not a key (no targets).
        assert "left" not in at

    def test_lifecycle_requires_approval_derived_from_context_guard(self, repo):
        # The only `context.approved`-guarded edge in h-dcn's graph is application->pending;
        # it surfaces in `requires_approval` so the modal renders the approval checkbox.
        # Derived from the guard DATA — never a hardcoded edge list.
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        )
        lifecycle = service.get_field_config("h-dcn")["lifecycle"]
        assert lifecycle["requires_approval"] == ["application->pending"]

    def test_lifecycle_targets_match_the_engines_allowed_to_states(self, repo):
        # The projected candidate targets for each state agree with what the engine itself
        # would permit at the graph level (the UI list is a faithful convenience view of
        # the authoritative graph — server stays authoritative on guards).
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        )
        at = service.get_field_config("h-dcn")["lifecycle"]["allowed_transitions"]
        for state in _MS:
            engine_targets = [
                t.value for t in HDCN_LIFECYCLE_CONFIG.allowed_to_states(state)
            ]
            if engine_targets:
                assert at[state.value] == engine_targets
            else:
                assert state.value not in at

    def test_lifecycle_block_is_json_serializable(self, repo):
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        )
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


# ---------------------------------------------------------------------------
# S5c Task 4.6 — edge dispatch: GET /members/field-config carries the lifecycle block
# ---------------------------------------------------------------------------


@pytest.fixture()
def inject_service_with_lifecycle(monkeypatch, repo):
    service = MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({}),
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
    )
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    return service


def test_field_config_route_carries_the_declared_lifecycle(inject_service_with_lifecycle):
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    data = _data(resp)
    assert data["lifecycle"] is not None
    assert data["lifecycle"]["allowed_transitions"]["pending"] == ["active", "left"]
    assert data["lifecycle"]["requires_approval"] == ["application->pending"]


def test_field_config_route_lifecycle_none_without_provider(inject_service):
    # inject_service wires a service with NO lifecycle provider → deny-by-default at the UI.
    resp = app.handler(_event("GET", "/members/field-config"))
    assert resp["statusCode"] == 200
    assert _data(resp)["lifecycle"] is None
