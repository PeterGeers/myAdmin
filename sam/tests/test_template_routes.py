"""
Tests for the stored mail-template CRUD routes (R2, pivot-output-actions task 2.3), end to
end through the thin edge over the SAME faithful in-memory ``FakeDynamoTable`` +
``DynamoDbMembersRepository`` (the metadata store) + the shipped ``InMemoryTemplateBodyStore``
(the body store) the sibling analytics-set routes use — no mocks.

What this closes:

1. **Template CRUD routes** (gate: ``members:export`` OR ``members:write``, design §3):
   - ``POST /members/templates`` — create; returns the serialized template with a
     server-generated ``template_id``; a blank name / no usable language is a **422**.
   - ``GET /members/templates`` — list the tenant's templates (metadata only, no body).
   - ``GET /members/templates/{template_id}`` — one template; **404** for an absent id.
   - ``PUT /members/templates/{template_id}`` — update; bumps ``updated_at``; **404** absent.
   - ``DELETE /members/templates/{template_id}`` — delete; a subsequent get is **404**.

2. **API response & error standard v1.0** (steering 37): success ``{success:true, data}``;
   a 422 carries ``{success:false, error, code, errors:[{field, code, detail}]}``; a 404
   carries ``{success:false, error, code}``.

3. **Route ordering** — the literal ``/members/templates`` must resolve to the template
   create, NOT be swallowed by ``/members/{member_id}``.

4. **Tenancy** — ``tenant_id`` is authoritative from the verified token (never the body);
   a template created under one tenant is invisible to another.

Validates: Requirements R2
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
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.template_service import (
    InMemoryTemplateBodyStore,
    TemplateService,
)
from sam.members.handler import app
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.repository.members_repository import DynamoDbMembersRepository

# The faithful in-memory DynamoDB fake (shared with the sibling route suites).
from sam.tests.test_members_repository import FakeDynamoTable

# ── Service wired like production: real repo (metadata store) + in-memory body store ──


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


@pytest.fixture()
def body_store() -> InMemoryTemplateBodyStore:
    return InMemoryTemplateBodyStore()


@pytest.fixture()
def template_service(repo, body_store) -> TemplateService:
    # The real repository's four *_template methods structurally satisfy the service's
    # TemplateMetadataStore port; the in-memory body store stands in for S3 (no AWS).
    return TemplateService(repo, body_store)


# Scope: the template routes are gated by an any-of capability (export OR write) and are NOT
# scope-partitioned, but a granted capability still consults the projected grants. An
# all-access caller is used throughout (mirrors the analytics-set suite).
_EMAIL_ALL = "all@h-dcn.test"

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
}


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, template_service):
    from sam.tests.conftest import FakeScopeGrantsReader

    # Patch the template-service accessor (lives on the dispatch module, re-exported on app)
    # so the edge dispatches to our fake-backed service — never AWS.
    monkeypatch.setattr(dispatch_mod, "get_template_service", lambda: template_service)
    monkeypatch.setattr(app, "get_template_service", lambda: template_service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return template_service


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read", "members:write", "members:export"),
    email=_EMAIL_ALL,
    sub="admin-sub",
    body=None,
    headers=None,
):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants)."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "cognito:groups": [],
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


def _body(resp):
    return json.loads(resp["body"])


def _create_payload(name="Welcome clubblad"):
    return {
        "name": name,
        "languages": {
            "nl": {
                "subject": "Dag {{first_name}}",
                "body_html": "<p>Beste {{first_name}}, type {{membership_type}}.</p>",
            },
            "en": {
                "subject": "Hi {{first_name}}",
                "body_html": "<p>Dear {{first_name}}, type {{membership_type}}.</p>",
            },
        },
    }


def _create(**event_kwargs):
    payload = event_kwargs.pop("body", _create_payload())
    return app.handler(
        _event("POST", "/members/templates", body=payload, **event_kwargs)
    )


# =====================================================================================
# CRUD happy paths — routes → handler → service → repo (metadata) + body store
# =====================================================================================


class TestTemplateRoutesCrud:
    def test_create_returns_200_with_server_generated_id_and_metadata(self, repo):
        resp = _create()
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["name"] == "Welcome clubblad"
        assert data["origin"] == "user"
        assert data["template_id"]  # server-generated
        assert data["created_at"] and data["updated_at"]
        # Merge fields auto-discovered from the body text (union across languages).
        assert set(data["merge_fields"]) == {"first_name", "membership_type"}
        # Metadata persisted in the tenant partition; body text NOT inline on the response.
        assert "body_html" not in json.dumps(data)
        assert repo.get_template("h-dcn", data["template_id"]) is not None

    def test_create_stamps_created_by_from_the_token_sub(self):
        resp = _create(sub="webmaster-sub")
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["created_by"] == "webmaster-sub"

    def test_create_ignores_body_tenant_and_template_id(self, repo):
        payload = _create_payload()
        payload["tenant_id"] = "evil"
        payload["template_id"] = "client-chosen"
        resp = _create(body=payload)
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["template_id"] != "client-chosen"  # server-generated, body ignored
        assert repo.get_template("evil", data["template_id"]) is None

    def test_list_returns_the_tenants_templates(self):
        _create(body=_create_payload("A"))
        _create(body=_create_payload("B"))
        resp = app.handler(_event("GET", "/members/templates"))
        assert resp["statusCode"] == 200
        names = sorted(t["name"] for t in _data(resp))
        assert names == ["A", "B"]

    def test_get_by_id_returns_200(self):
        created = _data(_create(body=_create_payload("One")))
        resp = app.handler(
            _event("GET", f"/members/templates/{created['template_id']}")
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["name"] == "One"

    def test_get_absent_returns_404(self):
        resp = app.handler(_event("GET", "/members/templates/ghost"))
        assert resp["statusCode"] == 404

    def test_update_changes_name_and_bumps_updated_at(self):
        created = _data(_create(body=_create_payload("Before")))
        template_id = created["template_id"]
        resp = app.handler(
            _event(
                "PUT",
                f"/members/templates/{template_id}",
                body={"name": "After"},
            )
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["name"] == "After"
        assert data["created_at"] == created["created_at"]  # preserved
        assert data["updated_at"] >= created["updated_at"]  # bumped

    def test_update_absent_returns_404(self):
        resp = app.handler(
            _event("PUT", "/members/templates/ghost", body={"name": "x"})
        )
        assert resp["statusCode"] == 404

    def test_delete_removes_it_subsequent_get_404(self, repo):
        created = _data(_create())
        template_id = created["template_id"]
        resp = app.handler(_event("DELETE", f"/members/templates/{template_id}"))
        assert resp["statusCode"] == 200
        assert (
            app.handler(_event("GET", f"/members/templates/{template_id}"))[
                "statusCode"
            ]
            == 404
        )
        assert repo.get_template("h-dcn", template_id) is None

    def test_delete_absent_returns_404(self):
        resp = app.handler(_event("DELETE", "/members/templates/ghost"))
        assert resp["statusCode"] == 404


# =====================================================================================
# 422 validation + API error-standard shape (steering 37, v1.0)
# =====================================================================================


class TestTemplateRoutesErrorStandard:
    def test_create_blank_name_returns_422_with_field_error(self):
        payload = _create_payload()
        payload["name"] = "   "
        resp = _create(body=payload)
        assert resp["statusCode"] == 422
        body = _body(resp)
        assert body["success"] is False
        assert body["code"] == "errors.validation.failed"
        fields = {e["field"] for e in body["errors"]}
        assert "name" in fields
        # Each entry carries the machine code + human detail (RFC 9457 shape).
        name_entry = next(e for e in body["errors"] if e["field"] == "name")
        assert name_entry["code"] == "errors.template.name"
        assert name_entry["detail"]

    def test_create_no_usable_language_returns_422(self):
        # A template with no language is unsendable → 422 on the `languages` field.
        resp = _create(body={"name": "Empty", "languages": {}})
        assert resp["statusCode"] == 422
        fields = {e["field"] for e in _body(resp)["errors"]}
        assert "languages" in fields

    def test_success_envelope_shape(self):
        resp = _create()
        body = _body(resp)
        assert body["success"] is True
        assert "data" in body
        # No error keys leak into a success envelope.
        assert "error" not in body and "errors" not in body

    def test_not_found_envelope_shape(self):
        resp = app.handler(_event("GET", "/members/templates/ghost"))
        body = _body(resp)
        assert body["success"] is False
        assert body["error"]
        assert body["code"] == "errors.api.notFound"


# =====================================================================================
# Routing, auth, capability gates
# =====================================================================================


class TestTemplateRoutesWiring:
    def test_template_route_not_shadowed_by_member_route(self):
        # The literal /members/templates must resolve to the template create, NOT be swallowed
        # by /members/{member_id}. A successful 200 create proves the declaration ordering.
        resp = _create()
        assert resp["statusCode"] == 200

    def test_routes_require_auth(self):
        resp = app.handler(
            {"httpMethod": "GET", "path": "/members/templates", "headers": {}}
        )
        assert resp["statusCode"] in (401, 403)

    def test_export_only_user_can_manage_templates(self):
        # Design §3: the gate is export OR write — an export-only user passes.
        resp = _create(capabilities=("members:read", "members:export"))
        assert resp["statusCode"] == 200

    def test_write_only_user_can_manage_templates(self):
        resp = _create(capabilities=("members:read", "members:write"))
        assert resp["statusCode"] == 200

    def test_read_only_user_cannot_manage_templates(self):
        # Neither export nor write → 403 (not a silent allow).
        resp = _create(capabilities=("members:read",))
        assert resp["statusCode"] == 403

    def test_read_only_user_cannot_list_templates(self):
        # The LIST route carries the same export-OR-write gate (design §3), so read-only → 403.
        resp = app.handler(
            _event("GET", "/members/templates", capabilities=("members:read",))
        )
        assert resp["statusCode"] == 403


# =====================================================================================
# Tenancy — tenant_id is authoritative; a template is invisible across tenants
# =====================================================================================


class TestTemplateRoutesTenancy:
    def test_template_is_isolated_per_tenant(self, repo):
        # Create under h-dcn.
        created = _data(_create())
        template_id = created["template_id"]
        # A caller in a DIFFERENT tenant (its own entitlement) cannot see it → 404.
        other_grants_email = "all@other.test"
        from sam.tests.conftest import FakeScopeGrantsReader

        # The other tenant needs its own all-access grant for the capability to resolve.
        import sam.members.handler.app as members_app

        members_app._SCOPE_GRANTS_READER_OVERRIDE = FakeScopeGrantsReader(
            {
                ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
                ("other", other_grants_email): {"region": ["*"]},
            }
        )
        resp = app.handler(
            _event(
                "GET",
                f"/members/templates/{template_id}",
                tenant="other",
                email=other_grants_email,
            )
        )
        assert resp["statusCode"] == 404
        # Still present for h-dcn in the store.
        assert repo.get_template("h-dcn", template_id) is not None
