"""
Tests for the member analytics-set CRUD routes (F-012), end-to-end through the thin edge over
the SAME faithful in-memory ``FakeDynamoTable`` + ``DynamoDbMembersRepository`` + real
``MembershipService`` the catalog write tests use (no mocks).

What this closes:

1. **Analytics-set CRUD routes** (``members:read`` reads, ``members:write`` create/update/
   delete):
   - ``POST /members/analytics-sets`` — create; returns the serialized set with a
     server-generated ``set_id``; a blank name is a **422**.
   - ``GET /members/analytics-sets`` — list the tenant's sets.
   - ``GET /members/analytics-sets/{set_id}`` — one set; **404** for an absent id.
   - ``PUT /members/analytics-sets/{set_id}`` — update; bumps ``updated_at``; **404** absent.
   - ``DELETE /members/analytics-sets/{set_id}`` — hard delete; a subsequent get is **404**.

2. **The F-011 regression** (the whole point): a LIST set with EMPTY ``group_columns`` AND
   EMPTY ``aggregate_measures`` creates successfully (200) and persists — proving empty
   group/measures is first-class in the module store.

Validates: finding F-011, F-012.
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

from sam.members.domain.analytics_set import AnalyticsSetValidationError
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import (
    AnalyticsSetNotFound,
    MembershipService,
)
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.handler import app
from sam.members.repository.members_repository import DynamoDbMembersRepository
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks

# The faithful in-memory DynamoDB fake.
from sam.tests.test_members_repository import FakeDynamoTable

# ── Service wired like production: real repo over the fake table + h-dcn config/hooks ──


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


@pytest.fixture()
def hooks() -> TenantHookRegistry:
    return register_hdcn_hooks(TenantHookRegistry())


@pytest.fixture()
def service(repo, hooks) -> MembershipService:
    return MembershipService(
        repo,
        lifecycle_provider=StaticLifecycleConfigProvider(
            {"h-dcn": HDCN_LIFECYCLE_CONFIG}
        ),
        tenant_hooks=hooks,
    )


# Scope is driven by the caller's verified EMAIL via the PROJECTED grants (design C5). The
# analytics-set routes are not scope-partitioned, but reads/writes still require a granted
# capability; an all-access caller is used throughout.
_EMAIL_ALL = "all@h-dcn.test"  # all-access → region ["*"]

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
}


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, service):
    from sam.tests.conftest import FakeScopeGrantsReader

    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read", "members:write", "members:admin", "members:export"),
    email=_EMAIL_ALL,
    groups=(),
    sub="admin-sub",
    body=None,
    query=None,
):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants)."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "cognito:groups": list(groups),
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


def _count_definition():
    return {
        "data_source": "members",
        "group_columns": ["membership_type"],
        "aggregate_measures": [{"function": "COUNT", "column": "*"}],
        "filters": {},
        "column_pivot": None,
        "column_nest_levels": [],
        "display_mode": "flat",
        "include_rollup": False,
    }


def _list_definition():
    """A filtered-LIST definition: EMPTY group_columns AND EMPTY aggregate_measures (F-011)."""
    return {
        "data_source": "members",
        "group_columns": [],
        "aggregate_measures": [],
        "filters": {"clubblad": "Papier"},
        "column_pivot": None,
        "column_nest_levels": [],
        "display_mode": "flat",
        "include_rollup": False,
    }


# =====================================================================================
# Analytics-set CRUD — domain layer (MembershipService)
# =====================================================================================


class TestAnalyticsSetDomain:
    def test_create_persists_and_returns_serialized_shape(self, service, repo):
        out = service.create_analytics_set(
            "h-dcn",
            {
                "name": "Count per type",
                "kind": "count",
                "definition": _count_definition(),
            },
        )
        assert out["name"] == "Count per type"
        assert out["kind"] == "count"
        assert out["definition"]["data_source"] == "members"
        assert out["set_id"]  # server-generated
        assert out["created_at"] and out["updated_at"]
        # Genuinely persisted in the tenant partition.
        assert repo.get_analytics_set("h-dcn", out["set_id"]) is not None

    def test_create_list_set_with_empty_group_and_measures(self, service, repo):
        # F-011 at the domain level: empty group_columns AND empty aggregate_measures is valid.
        out = service.create_analytics_set(
            "h-dcn",
            {
                "name": "Paper clubblad",
                "kind": "list",
                "definition": _list_definition(),
            },
        )
        assert out["kind"] == "list"
        assert out["definition"]["group_columns"] == []
        assert out["definition"]["aggregate_measures"] == []
        assert repo.get_analytics_set("h-dcn", out["set_id"]) is not None

    def test_create_ignores_body_tenant_and_set_id(self, service, repo):
        out = service.create_analytics_set(
            "h-dcn",
            {
                "name": "N",
                "kind": "count",
                "definition": _count_definition(),
                "tenant_id": "evil",
                "set_id": "client-chosen",
            },
        )
        assert out["set_id"] != "client-chosen"  # server-generated, body ignored
        assert repo.get_analytics_set("evil", out["set_id"]) is None

    def test_create_blank_name_raises_validation_error(self, service):
        with pytest.raises(AnalyticsSetValidationError):
            service.create_analytics_set(
                "h-dcn",
                {"name": "  ", "kind": "count", "definition": _count_definition()},
            )

    def test_update_absent_raises_not_found(self, service):
        with pytest.raises(AnalyticsSetNotFound):
            service.update_analytics_set("h-dcn", "ghost", {"name": "x"})

    def test_delete_absent_raises_not_found(self, service):
        with pytest.raises(AnalyticsSetNotFound):
            service.delete_analytics_set("h-dcn", "ghost")


# =====================================================================================
# Analytics-set CRUD — edge dispatch (routes → handler → domain → repo)
# =====================================================================================


class TestAnalyticsSetEdge:
    def test_create_list_set_empty_group_and_measures_returns_200_and_persists(
        self, repo
    ):
        # THE F-011 REGRESSION, end-to-end: a filtered-list set with empty group_columns AND
        # empty aggregate_measures must succeed and persist (empty group/measures first-class).
        resp = app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                body={
                    "name": "Paper clubblad",
                    "kind": "list",
                    "definition": _list_definition(),
                },
            )
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["kind"] == "list"
        assert data["definition"]["group_columns"] == []
        assert data["definition"]["aggregate_measures"] == []
        assert repo.get_analytics_set("h-dcn", data["set_id"]) is not None

    def test_create_count_set_returns_200(self, repo):
        resp = app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                body={
                    "name": "Count per type",
                    "kind": "count",
                    "definition": _count_definition(),
                },
            )
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["kind"] == "count"

    def test_list_returns_the_tenants_sets(self, repo):
        app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                body={"name": "A", "kind": "count", "definition": _count_definition()},
            )
        )
        app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                body={"name": "B", "kind": "list", "definition": _list_definition()},
            )
        )
        resp = app.handler(_event("GET", "/members/analytics-sets"))
        assert resp["statusCode"] == 200
        names = sorted(s["name"] for s in _data(resp))
        assert names == ["A", "B"]

    def test_get_by_id_returns_200(self, repo):
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "A",
                        "kind": "count",
                        "definition": _count_definition(),
                    },
                )
            )
        )
        resp = app.handler(
            _event("GET", f"/members/analytics-sets/{created['set_id']}")
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["name"] == "A"

    def test_get_absent_returns_404(self):
        resp = app.handler(_event("GET", "/members/analytics-sets/ghost"))
        assert resp["statusCode"] == 404

    def test_update_changes_name_and_definition_and_bumps_updated_at(self, repo):
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "A",
                        "kind": "count",
                        "definition": _count_definition(),
                    },
                )
            )
        )
        set_id = created["set_id"]
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}",
                body={"name": "A renamed", "definition": _list_definition()},
            )
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["name"] == "A renamed"
        assert data["definition"]["filters"] == {"clubblad": "Papier"}
        # created_at preserved; updated_at bumped (>= created_at, and present).
        assert data["created_at"] == created["created_at"]
        assert data["updated_at"] >= created["updated_at"]

    def test_update_absent_returns_404(self):
        resp = app.handler(
            _event("PUT", "/members/analytics-sets/ghost", body={"name": "x"})
        )
        assert resp["statusCode"] == 404

    def test_delete_removes_it_subsequent_get_404(self, repo):
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "A",
                        "kind": "count",
                        "definition": _count_definition(),
                    },
                )
            )
        )
        set_id = created["set_id"]
        resp = app.handler(_event("DELETE", f"/members/analytics-sets/{set_id}"))
        assert resp["statusCode"] == 200
        # Gone — a subsequent get is 404.
        assert (
            app.handler(_event("GET", f"/members/analytics-sets/{set_id}"))[
                "statusCode"
            ]
            == 404
        )
        assert repo.get_analytics_set("h-dcn", set_id) is None

    def test_delete_absent_returns_404(self):
        resp = app.handler(_event("DELETE", "/members/analytics-sets/ghost"))
        assert resp["statusCode"] == 404

    def test_create_blank_name_returns_422(self):
        resp = app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                body={"name": "  ", "kind": "count", "definition": _count_definition()},
            )
        )
        assert resp["statusCode"] == 422
        fields = {e["field"] for e in json.loads(resp["body"])["errors"]}
        assert "name" in fields

    def test_routes_require_auth(self):
        resp = app.handler(
            {"httpMethod": "GET", "path": "/members/analytics-sets", "headers": {}}
        )
        assert resp["statusCode"] in (401, 403)

    def test_analytics_set_route_not_shadowed_by_member_route(self, repo):
        # The literal /members/analytics-sets must resolve to the analytics-set create, NOT be
        # swallowed by /members/{member_id}. A successful 200 create proves the ordering.
        resp = app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                body={
                    "name": "ordered",
                    "kind": "count",
                    "definition": _count_definition(),
                },
            )
        )
        assert resp["statusCode"] == 200
