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

    def test_create_stamps_origin_user_and_created_by(self, service, repo):
        # R11.2/R11.3: a created set is origin 'user' and carries the caller's sub as
        # created_by (attribution only). The domain takes created_by explicitly.
        out = service.create_analytics_set(
            "h-dcn",
            {"name": "Mine", "kind": "count", "definition": _count_definition()},
            created_by="sub-123",
        )
        assert out["origin"] == "user"
        assert out["created_by"] == "sub-123"

    def test_update_preserves_origin_and_created_by(self, service, repo):
        created = service.create_analytics_set(
            "h-dcn",
            {"name": "Mine", "kind": "count", "definition": _count_definition()},
            created_by="author-sub",
        )
        updated = service.update_analytics_set(
            "h-dcn", created["set_id"], {"name": "Renamed"}
        )
        # Original author attribution survives an edit by anyone (R11.3).
        assert updated["created_by"] == "author-sub"
        assert updated["origin"] == "user"

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

    def test_create_stamps_created_by_from_the_token_sub(self, repo):
        # End-to-end: created_by is taken from the VERIFIED token sub (ctx.sub), never the body
        # (R11.1/R11.3 — the owner is the authenticated principal, not a body value).
        resp = app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                sub="webmaster-sub",
                body={
                    "name": "By webmaster",
                    "kind": "count",
                    "definition": _count_definition(),
                    "created_by": "spoofed",  # body attempt is ignored
                },
            )
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["created_by"] == "webmaster-sub"
        assert data["origin"] == "user"

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


# =====================================================================================
# Capability gates (R11.3) — any-of: export OR write to create; write OR admin to edit/delete
# =====================================================================================


class TestAnalyticsSetCapabilityGates:
    """The analytics-set surface is NOT admin-only (R11.3). Create = export OR write;
    edit/delete = write OR admin; reads = members:read. A caller holding ANY accepted
    capability passes; a caller holding none is 403."""

    def _create_as(self, caps):
        return app.handler(
            _event(
                "POST",
                "/members/analytics-sets",
                capabilities=caps,
                body={"name": "S", "kind": "count", "definition": _count_definition()},
            )
        )

    # ── create: export OR write ──────────────────────────────────────────────────────
    def test_export_only_user_can_create(self):
        # An EXPORT-only user (no write) can create a set (R11.3).
        resp = self._create_as(("members:read", "members:export"))
        assert resp["statusCode"] == 200

    def test_write_only_user_can_create(self):
        resp = self._create_as(("members:read", "members:write"))
        assert resp["statusCode"] == 200

    def test_read_only_user_cannot_create(self):
        # Neither export nor write → 403 (not a silent allow).
        resp = self._create_as(("members:read",))
        assert resp["statusCode"] == 403

    # ── delete: write OR admin ───────────────────────────────────────────────────────
    def _seed_set(self):
        created = _data(self._create_as(("members:read", "members:write")))
        return created["set_id"]

    def test_write_user_can_delete(self):
        set_id = self._seed_set()
        resp = app.handler(
            _event(
                "DELETE",
                f"/members/analytics-sets/{set_id}",
                capabilities=("members:read", "members:write"),
            )
        )
        assert resp["statusCode"] == 200

    def test_admin_user_can_delete(self):
        set_id = self._seed_set()
        resp = app.handler(
            _event(
                "DELETE",
                f"/members/analytics-sets/{set_id}",
                capabilities=("members:read", "members:admin"),
            )
        )
        assert resp["statusCode"] == 200

    def test_export_only_user_cannot_delete(self):
        # Export lets you CREATE but NOT delete a shared set (delete = write OR admin).
        set_id = self._seed_set()
        resp = app.handler(
            _event(
                "DELETE",
                f"/members/analytics-sets/{set_id}",
                capabilities=("members:read", "members:export"),
            )
        )
        assert resp["statusCode"] == 403

    def test_update_requires_write_or_admin(self):
        set_id = self._seed_set()
        # export-only → 403
        assert (
            app.handler(
                _event(
                    "PUT",
                    f"/members/analytics-sets/{set_id}",
                    capabilities=("members:read", "members:export"),
                    body={"name": "renamed"},
                )
            )["statusCode"]
            == 403
        )
        # write → 200
        assert (
            app.handler(
                _event(
                    "PUT",
                    f"/members/analytics-sets/{set_id}",
                    capabilities=("members:read", "members:write"),
                    body={"name": "renamed"},
                )
            )["statusCode"]
            == 200
        )

    # ── reads: members:read ──────────────────────────────────────────────────────────
    def test_list_requires_only_read(self):
        resp = app.handler(
            _event("GET", "/members/analytics-sets", capabilities=("members:read",))
        )
        assert resp["statusCode"] == 200


class TestAnyOfCapabilityHelpers:
    """Unit-level cover for the edge's any-of capability resolution (12.2)."""

    def test_route_required_capabilities_prefers_any_of(self):
        from sam.members.handler.routes import HttpMethod, RouteGroup, RouteSpec

        spec = RouteSpec(
            name="x",
            method=HttpMethod.POST,
            path="/x",
            group=RouteGroup.ANALYTICS,
            capability=None,
            capabilities_any=("members:export", "members:write"),
            self_service=False,
            summary="",
        )
        assert app._route_required_capabilities(spec) == (
            "members:export",
            "members:write",
        )

    def test_route_required_capabilities_single(self):
        from sam.members.handler.routes import HttpMethod, RouteGroup, RouteSpec

        spec = RouteSpec(
            name="y",
            method=HttpMethod.GET,
            path="/y",
            group=RouteGroup.ANALYTICS,
            capability="members:read",
            self_service=False,
            summary="",
        )
        assert app._route_required_capabilities(spec) == ("members:read",)

    def test_any_capability_granted_passes_on_any_true(self):
        claims = {"custom:entitlements": _entitlement("h-dcn", ["members:export"])}
        assert (
            app._any_capability_granted(
                claims, "h-dcn", ("members:export", "members:write")
            )
            is True
        )

    def test_any_capability_granted_false_when_none_held(self):
        claims = {"custom:entitlements": _entitlement("h-dcn", ["members:read"])}
        assert (
            app._any_capability_granted(
                claims, "h-dcn", ("members:export", "members:write")
            )
            is False
        )


# =====================================================================================
# Preferred list (R11.2 layer 2) — per-user, keyed by the verified sub (user ≠ member)
# =====================================================================================


class TestPreferredListDomain:
    def test_get_is_empty_when_unset(self, service):
        out = service.get_preferred_list("h-dcn", "sub-1")
        assert out["sub"] == "sub-1"
        assert out["refs"] == []

    def test_save_then_get_round_trips_refs(self, service, repo):
        service.save_preferred_list(
            "h-dcn", "sub-1", {"refs": ["preset:jubilees", "set:abc123"]}
        )
        out = service.get_preferred_list("h-dcn", "sub-1")
        assert out["refs"] == ["preset:jubilees", "set:abc123"]
        assert out["updated_at"]

    def test_save_replaces_the_whole_list(self, service):
        service.save_preferred_list("h-dcn", "sub-1", {"refs": ["preset:a", "set:b"]})
        service.save_preferred_list("h-dcn", "sub-1", {"refs": ["preset:c"]})
        assert service.get_preferred_list("h-dcn", "sub-1")["refs"] == ["preset:c"]

    def test_save_drops_blank_and_non_string_refs(self, service):
        service.save_preferred_list(
            "h-dcn", "sub-1", {"refs": ["preset:a", "", "  ", 42, None, "set:b"]}
        )
        assert service.get_preferred_list("h-dcn", "sub-1")["refs"] == [
            "preset:a",
            "set:b",
        ]

    def test_empty_refs_is_valid_clears_preferences(self, service):
        service.save_preferred_list("h-dcn", "sub-1", {"refs": ["preset:a"]})
        service.save_preferred_list("h-dcn", "sub-1", {"refs": []})
        assert service.get_preferred_list("h-dcn", "sub-1")["refs"] == []

    def test_lists_are_isolated_per_user(self, service):
        service.save_preferred_list("h-dcn", "sub-1", {"refs": ["preset:one"]})
        service.save_preferred_list("h-dcn", "sub-2", {"refs": ["preset:two"]})
        assert service.get_preferred_list("h-dcn", "sub-1")["refs"] == ["preset:one"]
        assert service.get_preferred_list("h-dcn", "sub-2")["refs"] == ["preset:two"]


class TestPreferredListEdge:
    def test_get_empty_returns_200_with_empty_refs(self):
        resp = app.handler(
            _event("GET", "/members/analytics-sets/preferred", sub="webmaster-sub")
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["sub"] == "webmaster-sub"
        assert data["refs"] == []

    def test_put_then_get_round_trips_for_the_same_sub(self):
        put = app.handler(
            _event(
                "PUT",
                "/members/analytics-sets/preferred",
                sub="sub-x",
                body={"refs": ["preset:jubilees", "set:deadbeef"]},
            )
        )
        assert put["statusCode"] == 200
        got = app.handler(
            _event("GET", "/members/analytics-sets/preferred", sub="sub-x")
        )
        assert _data(got)["refs"] == ["preset:jubilees", "set:deadbeef"]

    def test_preferred_list_is_private_per_user(self):
        app.handler(
            _event(
                "PUT",
                "/members/analytics-sets/preferred",
                sub="sub-a",
                body={"refs": ["preset:mine"]},
            )
        )
        # A DIFFERENT user's GET must not see sub-a's list (keyed by the verified sub).
        other = app.handler(
            _event("GET", "/members/analytics-sets/preferred", sub="sub-b")
        )
        assert _data(other)["refs"] == []

    def test_preferred_literal_wins_over_set_id_route(self):
        # GET /members/analytics-sets/preferred must resolve to the preferred-list route, NOT
        # be swallowed by GET /members/analytics-sets/{set_id} (declaration order). A 200 with
        # a `refs` key (not an analytics-set shape / 404) proves the literal won.
        resp = app.handler(
            _event("GET", "/members/analytics-sets/preferred", sub="sub-q")
        )
        assert resp["statusCode"] == 200
        assert "refs" in _data(resp)

    def test_put_gate_export_or_write(self):
        # Export-only can save a preferred list (R11.3 — same gate as create).
        assert (
            app.handler(
                _event(
                    "PUT",
                    "/members/analytics-sets/preferred",
                    sub="s1",
                    capabilities=("members:read", "members:export"),
                    body={"refs": ["preset:a"]},
                )
            )["statusCode"]
            == 200
        )
        # Read-only cannot.
        assert (
            app.handler(
                _event(
                    "PUT",
                    "/members/analytics-sets/preferred",
                    sub="s1",
                    capabilities=("members:read",),
                    body={"refs": ["preset:a"]},
                )
            )["statusCode"]
            == 403
        )

    def test_get_requires_only_read(self):
        resp = app.handler(
            _event(
                "GET",
                "/members/analytics-sets/preferred",
                sub="s1",
                capabilities=("members:read",),
            )
        )
        assert resp["statusCode"] == 200


# =====================================================================================
# Column preferences (session-columns R6) — per-user, keyed by the verified sub
# (user ≠ member). Mirrors the preferred-list suites: gating, sub-from-edge,
# empty-when-unset, cross-tenant / cross-user isolation, non-candidate cleaning.
# =====================================================================================

# Real candidate field keys of the default (no-overlay) h-dcn field config — the bare
# ``key`` of a VISIBLE resolved field (what the chooser stores). A key not among the
# tenant's candidates (R6.5) is dropped server-side.
_CANDIDATE_A = "email"
_CANDIDATE_B = "first_name"
_CANDIDATE_C = "status"
_NON_CANDIDATE = "__not_a_field__"


class TestColumnPreferencesDomain:
    def test_get_is_empty_when_unset(self, service):
        out = service.get_column_preferences("h-dcn", "sub-1")
        assert out["sub"] == "sub-1"
        assert out["columns"] == []

    def test_save_then_get_round_trips_columns(self, service, repo):
        service.save_column_preferences(
            "h-dcn", "sub-1", {"columns": [_CANDIDATE_A, _CANDIDATE_B]}
        )
        out = service.get_column_preferences("h-dcn", "sub-1")
        assert out["columns"] == [_CANDIDATE_A, _CANDIDATE_B]
        assert out["updated_at"]

    def test_save_replaces_the_whole_list(self, service):
        service.save_column_preferences(
            "h-dcn", "sub-1", {"columns": [_CANDIDATE_A, _CANDIDATE_B]}
        )
        service.save_column_preferences("h-dcn", "sub-1", {"columns": [_CANDIDATE_C]})
        assert service.get_column_preferences("h-dcn", "sub-1")["columns"] == [
            _CANDIDATE_C
        ]

    def test_save_drops_blank_and_non_string_keys(self, service):
        service.save_column_preferences(
            "h-dcn",
            "sub-1",
            {"columns": [_CANDIDATE_A, "", "  ", 42, None, _CANDIDATE_B]},
        )
        assert service.get_column_preferences("h-dcn", "sub-1")["columns"] == [
            _CANDIDATE_A,
            _CANDIDATE_B,
        ]

    def test_save_drops_duplicate_keys_preserving_order(self, service):
        # First occurrence wins; order preserved (R6.5 de-dupe).
        service.save_column_preferences(
            "h-dcn",
            "sub-1",
            {"columns": [_CANDIDATE_A, _CANDIDATE_B, _CANDIDATE_A, _CANDIDATE_B]},
        )
        assert service.get_column_preferences("h-dcn", "sub-1")["columns"] == [
            _CANDIDATE_A,
            _CANDIDATE_B,
        ]

    def test_save_drops_non_candidate_keys(self, service):
        # A key that is not a candidate field of the tenant's resolved config is dropped
        # server-side (R6.5), the write still succeeds with the cleaned list.
        service.save_column_preferences(
            "h-dcn", "sub-1", {"columns": [_CANDIDATE_A, _NON_CANDIDATE, _CANDIDATE_B]}
        )
        assert service.get_column_preferences("h-dcn", "sub-1")["columns"] == [
            _CANDIDATE_A,
            _CANDIDATE_B,
        ]

    def test_empty_columns_is_valid_clears_preferences(self, service):
        service.save_column_preferences("h-dcn", "sub-1", {"columns": [_CANDIDATE_A]})
        service.save_column_preferences("h-dcn", "sub-1", {"columns": []})
        assert service.get_column_preferences("h-dcn", "sub-1")["columns"] == []

    def test_preferences_are_isolated_per_user(self, service):
        service.save_column_preferences("h-dcn", "sub-1", {"columns": [_CANDIDATE_A]})
        service.save_column_preferences("h-dcn", "sub-2", {"columns": [_CANDIDATE_B]})
        assert service.get_column_preferences("h-dcn", "sub-1")["columns"] == [
            _CANDIDATE_A
        ]
        assert service.get_column_preferences("h-dcn", "sub-2")["columns"] == [
            _CANDIDATE_B
        ]


class TestColumnPreferencesScopeDimensionOverlay:
    """Regression: a tenant whose overlay has a SCOPE-DIMENSION-BACKED choiceless enum
    (h-dcn ``region``) must be able to save column preferences. Previously the save path's
    ``_candidate_column_keys`` resolved the field config WITHOUT the scope vocabulary, so the
    resolver rejected ``overlay.region`` ("an enum variable field must declare choices/options")
    → unhandled ``OverlayError`` → 500. The fix passes ``_scope_vocab`` to ``resolve`` exactly
    as ``get_field_config`` / the write validator do.
    """

    @pytest.fixture()
    def scope_overlay_service(self, repo, hooks) -> MembershipService:
        from sam.members.domain.field_resolver import (
            OverlayField,
            StaticOverlayProvider,
            TenantOverlay,
        )
        from sam.members.domain.fixed_fields import FieldType
        from sam.members.domain.scope_dimensions import (
            ScopeDimension,
            StaticScopeConfigProvider,
        )

        # An overlay enum field 'region' with NO inline choices — exactly h-dcn's
        # scope-dimension-backed dropdown. Legitimate ONLY because the scope config
        # below supplies its vocabulary (design D1a).
        overlay = TenantOverlay(
            fields={
                "region": OverlayField(
                    key="region",
                    type=FieldType.ENUM,
                    label={"nl": "Regio", "en": "Region"},
                ),
            },
        )
        # StaticScopeConfigProvider takes {tenant_id: [dimensions]} (it materializes the
        # ScopeConfig itself). The enabled 'region' dimension binds to the 'region' field
        # and declares the vocabulary that sources the overlay enum's choices.
        region_dimensions = (
            ScopeDimension(
                key="region",
                field="region",
                label={"nl": "Regio", "en": "Region"},
                enabled=True,
                values=("Noord", "Zuid", "Oost", "West"),
            ),
        )
        return MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({"h-dcn": overlay}),
            lifecycle_provider=StaticLifecycleConfigProvider(
                {"h-dcn": HDCN_LIFECYCLE_CONFIG}
            ),
            tenant_hooks=hooks,
            scope_config_provider=StaticScopeConfigProvider(
                {"h-dcn": region_dimensions}
            ),
        )

    def test_save_succeeds_with_scope_dimension_backed_enum_overlay(
        self, scope_overlay_service
    ):
        # The dimension-backed 'region' resolves as a candidate (its choices sourced from the
        # scope vocab), so saving it does NOT raise OverlayError (the former 500).
        scope_overlay_service.save_column_preferences(
            "h-dcn", "sub-1", {"columns": ["region", _CANDIDATE_A]}
        )
        out = scope_overlay_service.get_column_preferences("h-dcn", "sub-1")
        assert out["columns"] == ["region", _CANDIDATE_A]

    def test_candidate_keys_include_the_dimension_backed_region(
        self, scope_overlay_service
    ):
        # 'region' is a candidate column key (resolve succeeded with the scope vocab); a
        # non-candidate is still dropped, proving the candidate filter ran (not bypassed).
        scope_overlay_service.save_column_preferences(
            "h-dcn", "sub-1", {"columns": ["region", _NON_CANDIDATE]}
        )
        assert scope_overlay_service.get_column_preferences("h-dcn", "sub-1")[
            "columns"
        ] == ["region"]


class TestColumnPreferencesEdge:
    def test_get_empty_returns_200_with_empty_columns(self):
        resp = app.handler(
            _event("GET", "/members/column-preferences", sub="webmaster-sub")
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["sub"] == "webmaster-sub"
        assert data["columns"] == []

    def test_put_then_get_round_trips_for_the_same_sub(self):
        put = app.handler(
            _event(
                "PUT",
                "/members/column-preferences",
                sub="sub-x",
                body={"columns": [_CANDIDATE_A, _CANDIDATE_B]},
            )
        )
        assert put["statusCode"] == 200
        got = app.handler(_event("GET", "/members/column-preferences", sub="sub-x"))
        assert _data(got)["columns"] == [_CANDIDATE_A, _CANDIDATE_B]

    def test_put_owner_is_the_verified_sub_not_a_body_value(self):
        # The stored/returned owner is ctx.sub (the verified edge principal), NEVER a
        # client-supplied sub in the body (R6.3 — sub-from-edge).
        put = app.handler(
            _event(
                "PUT",
                "/members/column-preferences",
                sub="verified-sub",
                body={"columns": [_CANDIDATE_A], "sub": "spoofed-sub"},
            )
        )
        assert put["statusCode"] == 200
        assert _data(put)["sub"] == "verified-sub"
        # The spoofed sub owns nothing.
        other = app.handler(
            _event("GET", "/members/column-preferences", sub="spoofed-sub")
        )
        assert _data(other)["columns"] == []

    def test_put_drops_non_candidate_keys_end_to_end(self):
        put = app.handler(
            _event(
                "PUT",
                "/members/column-preferences",
                sub="sub-nc",
                body={"columns": [_CANDIDATE_A, _NON_CANDIDATE, _CANDIDATE_A]},
            )
        )
        assert put["statusCode"] == 200
        # Non-candidate dropped + duplicate de-duped (R6.5).
        assert _data(put)["columns"] == [_CANDIDATE_A]

    def test_column_preferences_are_private_per_user(self):
        app.handler(
            _event(
                "PUT",
                "/members/column-preferences",
                sub="sub-a",
                body={"columns": [_CANDIDATE_A]},
            )
        )
        # A DIFFERENT user's GET must not see sub-a's list (keyed by the verified sub).
        other = app.handler(
            _event("GET", "/members/column-preferences", sub="sub-b")
        )
        assert _data(other)["columns"] == []

    def test_column_preferences_are_isolated_per_tenant(self, monkeypatch):
        # A write under h-dcn must not surface for a DIFFERENT tenant (PK pinned to tenant_id).
        from sam.tests.conftest import FakeScopeGrantsReader

        app.handler(
            _event(
                "PUT",
                "/members/column-preferences",
                sub="sub-t",
                body={"columns": [_CANDIDATE_A]},
            )
        )
        # Point the scope reader at a second tenant and query it with the same sub.
        monkeypatch.setattr(
            app,
            "_SCOPE_GRANTS_READER_OVERRIDE",
            FakeScopeGrantsReader({("other-tenant", _EMAIL_ALL): {"region": ["*"]}}),
        )
        other = app.handler(
            _event("GET", "/members/column-preferences", tenant="other-tenant", sub="sub-t")
        )
        assert _data(other)["columns"] == []

    def test_literal_wins_over_member_id_route(self):
        # GET /members/column-preferences must resolve to the column-preferences route, NOT be
        # swallowed by GET /members/{member_id} (declaration order). A 200 with a `columns` key
        # (not a member shape / 404) proves the literal won.
        resp = app.handler(
            _event("GET", "/members/column-preferences", sub="sub-q")
        )
        assert resp["statusCode"] == 200
        assert "columns" in _data(resp)

    def test_put_gate_export_or_write(self):
        # Export-only can save column preferences (R6.3 — export OR write).
        assert (
            app.handler(
                _event(
                    "PUT",
                    "/members/column-preferences",
                    sub="s1",
                    capabilities=("members:read", "members:export"),
                    body={"columns": [_CANDIDATE_A]},
                )
            )["statusCode"]
            == 200
        )
        # Write-only can too.
        assert (
            app.handler(
                _event(
                    "PUT",
                    "/members/column-preferences",
                    sub="s1",
                    capabilities=("members:read", "members:write"),
                    body={"columns": [_CANDIDATE_A]},
                )
            )["statusCode"]
            == 200
        )
        # Read-only is refused the PUT.
        assert (
            app.handler(
                _event(
                    "PUT",
                    "/members/column-preferences",
                    sub="s1",
                    capabilities=("members:read",),
                    body={"columns": [_CANDIDATE_A]},
                )
            )["statusCode"]
            == 403
        )

    def test_get_requires_only_read(self):
        resp = app.handler(
            _event(
                "GET",
                "/members/column-preferences",
                sub="s1",
                capabilities=("members:read",),
            )
        )
        assert resp["statusCode"] == 200


# =====================================================================================
# Delivery block — set / clear on a saved set (R3, pivot-output-actions task 3.3)
#
# PUT/DELETE /members/analytics-sets/{set_id}/delivery store / clear the optional stored
# "what to do with the result" block on an EXISTING set (design §2.1/§3). Gate: members:export
# + existing scope — a stored delivery can send only what the user could already export, so NO
# new permission and NO audit-on-save (R3). The entity's validate() (task 3.1) enforces the
# mode rules; a bad block is a 422 surfacing the FieldError array; an unknown set is a 404.
#
# Validates: Requirements R3.
# =====================================================================================


def _delivery_to_fixed():
    """A valid ``to_fixed`` delivery block: a fixed recipient list + a csv attachment."""
    return {
        "mode": "to_fixed",
        "template_id": None,
        "attachment": "csv",
        "recipients": ["agent@example.com", "office@example.com"],
        "label_options": None,
    }


def _delivery_per_recipient():
    """A valid ``per_recipient`` delivery block: a template, no stored recipients (merge)."""
    return {
        "mode": "per_recipient",
        "template_id": "template#welcome",
        "attachment": None,
        "recipients": [],
        "label_options": None,
    }


class TestAnalyticsSetDeliveryDomain:
    """Service-layer set/clear of the delivery block (MembershipService over the real repo)."""

    def _seed(self, service):
        return service.create_analytics_set(
            "h-dcn",
            {"name": "S", "kind": "count", "definition": _count_definition()},
        )["set_id"]

    def test_set_to_fixed_stores_the_block_and_round_trips(self, service, repo):
        set_id = self._seed(service)
        out = service.set_analytics_set_delivery(
            "h-dcn", set_id, _delivery_to_fixed()
        )
        assert out["delivery"]["mode"] == "to_fixed"
        assert out["delivery"]["recipients"] == [
            "agent@example.com",
            "office@example.com",
        ]
        # Genuinely persisted + round-trips through the repository (to_item/from_item).
        reloaded = repo.get_analytics_set("h-dcn", set_id)
        assert reloaded.delivery["mode"] == "to_fixed"
        assert reloaded.delivery["recipients"] == [
            "agent@example.com",
            "office@example.com",
        ]

    def test_set_per_recipient_stores_template_and_no_recipients(self, service, repo):
        set_id = self._seed(service)
        out = service.set_analytics_set_delivery(
            "h-dcn", set_id, _delivery_per_recipient()
        )
        assert out["delivery"]["mode"] == "per_recipient"
        assert out["delivery"]["template_id"] == "template#welcome"
        assert out["delivery"]["recipients"] == []

    def test_set_preserves_definition_origin_created_by_and_bumps_updated_at(
        self, service
    ):
        created = service.create_analytics_set(
            "h-dcn",
            {"name": "S", "kind": "count", "definition": _count_definition()},
            created_by="author-sub",
        )
        set_id = created["set_id"]
        out = service.set_analytics_set_delivery(
            "h-dcn", set_id, _delivery_to_fixed()
        )
        # The pivot config + attribution + origin survive a delivery set; updated_at bumps.
        assert out["definition"]["data_source"] == "members"
        assert out["created_by"] == "author-sub"
        assert out["origin"] == "user"
        assert out["created_at"] == created["created_at"]
        assert out["updated_at"] >= created["updated_at"]

    def test_set_invalid_to_fixed_without_recipients_raises(self, service):
        set_id = self._seed(service)
        with pytest.raises(AnalyticsSetValidationError) as exc:
            service.set_analytics_set_delivery(
                "h-dcn", set_id, {"mode": "to_fixed", "recipients": []}
            )
        assert "delivery" in exc.value.errors

    def test_set_invalid_per_recipient_with_recipients_raises(self, service):
        set_id = self._seed(service)
        with pytest.raises(AnalyticsSetValidationError) as exc:
            service.set_analytics_set_delivery(
                "h-dcn",
                set_id,
                {"mode": "per_recipient", "recipients": ["a@example.com"]},
            )
        assert "delivery" in exc.value.errors

    def test_set_absent_set_raises_not_found(self, service):
        with pytest.raises(AnalyticsSetNotFound):
            service.set_analytics_set_delivery("h-dcn", "ghost", _delivery_to_fixed())

    def test_clear_sets_delivery_back_to_none(self, service, repo):
        set_id = self._seed(service)
        service.set_analytics_set_delivery("h-dcn", set_id, _delivery_to_fixed())
        out = service.clear_analytics_set_delivery("h-dcn", set_id)
        assert out["delivery"] is None
        assert repo.get_analytics_set("h-dcn", set_id).delivery is None

    def test_clear_absent_set_raises_not_found(self, service):
        with pytest.raises(AnalyticsSetNotFound):
            service.clear_analytics_set_delivery("h-dcn", "ghost")


class TestAnalyticsSetDeliveryEdge:
    """End-to-end set/clear through the thin edge (routes → handler → domain → repo)."""

    def _seed(self):
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "S",
                        "kind": "count",
                        "definition": _count_definition(),
                    },
                )
            )
        )
        return created["set_id"]

    def test_put_to_fixed_stores_the_block_returns_200(self, repo):
        set_id = self._seed()
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                body=_delivery_to_fixed(),
            )
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["delivery"]["mode"] == "to_fixed"
        assert data["delivery"]["recipients"] == [
            "agent@example.com",
            "office@example.com",
        ]
        assert repo.get_analytics_set("h-dcn", set_id).delivery is not None

    def test_put_per_recipient_stores_the_block_returns_200(self):
        set_id = self._seed()
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                body=_delivery_per_recipient(),
            )
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["delivery"]["mode"] == "per_recipient"

    def test_put_invalid_block_returns_422_with_delivery_field(self):
        # A to_fixed delivery with no recipients is an invalid block → 422, surfacing the
        # entity's FieldError array (the field is "delivery").
        set_id = self._seed()
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                body={"mode": "to_fixed", "recipients": []},
            )
        )
        assert resp["statusCode"] == 422
        fields = {e["field"] for e in json.loads(resp["body"])["errors"]}
        assert "delivery" in fields

    def test_put_absent_set_returns_404(self):
        resp = app.handler(
            _event(
                "PUT",
                "/members/analytics-sets/ghost/delivery",
                body=_delivery_to_fixed(),
            )
        )
        assert resp["statusCode"] == 404

    def test_delete_clears_the_block_returns_200(self, repo):
        set_id = self._seed()
        app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                body=_delivery_to_fixed(),
            )
        )
        resp = app.handler(
            _event("DELETE", f"/members/analytics-sets/{set_id}/delivery")
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["delivery"] is None
        assert repo.get_analytics_set("h-dcn", set_id).delivery is None

    def test_delete_absent_set_returns_404(self):
        resp = app.handler(
            _event("DELETE", "/members/analytics-sets/ghost/delivery")
        )
        assert resp["statusCode"] == 404

    def test_delivery_route_not_shadowed_by_set_id_route(self):
        # The literal /{set_id}/delivery sub-path must resolve to the delivery route (an extra
        # segment past /{set_id}); a 200 PUT proves it is not swallowed by the set CRUD routes.
        set_id = self._seed()
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                body=_delivery_to_fixed(),
            )
        )
        assert resp["statusCode"] == 200

    def test_routes_require_auth(self):
        resp = app.handler(
            {
                "httpMethod": "PUT",
                "path": "/members/analytics-sets/x/delivery",
                "headers": {},
            }
        )
        assert resp["statusCode"] in (401, 403)


class TestAnalyticsSetDeliveryGate:
    """The export gate (R3): a stored delivery can only send what the user could already
    export, so set/clear require members:export + existing scope — NO new permission."""

    def _seed(self):
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    capabilities=("members:read", "members:export"),
                    body={
                        "name": "S",
                        "kind": "count",
                        "definition": _count_definition(),
                    },
                )
            )
        )
        return created["set_id"]

    def test_export_user_can_set_delivery(self):
        set_id = self._seed()
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                capabilities=("members:read", "members:export"),
                body=_delivery_to_fixed(),
            )
        )
        assert resp["statusCode"] == 200

    def test_export_user_can_clear_delivery(self):
        set_id = self._seed()
        app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                capabilities=("members:read", "members:export"),
                body=_delivery_to_fixed(),
            )
        )
        resp = app.handler(
            _event(
                "DELETE",
                f"/members/analytics-sets/{set_id}/delivery",
                capabilities=("members:read", "members:export"),
            )
        )
        assert resp["statusCode"] == 200

    def test_without_export_is_403_on_put(self):
        # A write-only / read-only caller (no members:export) cannot store a delivery (403) —
        # the gate is export, NOT write/admin. We seed as an export user, then attempt the PUT
        # as a non-export caller.
        set_id = self._seed()
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                capabilities=("members:read", "members:write", "members:admin"),
                body=_delivery_to_fixed(),
            )
        )
        assert resp["statusCode"] == 403

    def test_without_export_is_403_on_delete(self):
        set_id = self._seed()
        app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                capabilities=("members:read", "members:export"),
                body=_delivery_to_fixed(),
            )
        )
        resp = app.handler(
            _event(
                "DELETE",
                f"/members/analytics-sets/{set_id}/delivery",
                capabilities=("members:read", "members:write", "members:admin"),
            )
        )
        assert resp["statusCode"] == 403


class TestAnalyticsSetDeliveryTenantIsolation:
    """Cross-tenant isolation (Property 1): a set created under h-dcn is not reachable for a
    delivery set/clear under a different tenant (the PK is pinned to the verified tenant)."""

    def test_set_delivery_cross_tenant_is_404(self, monkeypatch):
        from sam.tests.conftest import FakeScopeGrantsReader

        # Seed a set under h-dcn (the autouse grants reader covers h-dcn).
        set_id = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "S",
                        "kind": "count",
                        "definition": _count_definition(),
                    },
                )
            )
        )["set_id"]

        # Point the scope reader at a SECOND tenant and attempt the delivery set there with the
        # same set_id — the other tenant's partition has no such set → 404 (no cross-tenant
        # reach, never a 200 that would mutate h-dcn's set).
        monkeypatch.setattr(
            app,
            "_SCOPE_GRANTS_READER_OVERRIDE",
            FakeScopeGrantsReader({("other-tenant", _EMAIL_ALL): {"region": ["*"]}}),
        )
        resp = app.handler(
            _event(
                "PUT",
                f"/members/analytics-sets/{set_id}/delivery",
                tenant="other-tenant",
                body=_delivery_to_fixed(),
            )
        )
        assert resp["statusCode"] == 404


# =====================================================================================
# Deliver — run execute-and-deliver NOW (R4, pivot-output-actions task 4.2)
#
# POST /members/analytics-sets/{set_id}/deliver is the THIN enqueue route: it delegates to
# the standalone ExecuteAndDeliverService (task 4.1), which resolves the set + its stored
# delivery block, re-fetches the tenant's member rows (tenant-pinned — Property 1), runs the
# pivot, and ENQUEUES the send job(s); a worker (task 4.3/4.4) performs the actual SES send.
# The route NEVER blocks on the send — it returns 202 ACCEPTED (enqueued, not done). Gate:
# members:export + existing scope (same as the delivery set/clear — a send dispatches only
# what the user could already export, no new permission).
#
# These exercise the route end-to-end over the SAME real repo + fake table, with the deliver
# seam (dispatch_mod.get_execute_and_deliver_service) pointed at a service over that repo + a
# FAKE mail queue that CAPTURES jobs — so no AWS/SQS is touched. The service method under the
# route is execute_and_deliver(tenant_id, set_id, run_id) -> DeliveryOutcome; the 202 body is
# the flattened outcome receipt (run_id, mode, enqueued, skipped_no_address, job_ids).
# =====================================================================================


class _PassThroughPivot:
    """A fake PivotRunner — returns the re-fetched member rows unchanged (the result rows ARE
    the member rows for both delivery modes; keeps the test focused on the enqueue fan-out)."""

    def run(self, tenant_id, definition, rows):
        return list(rows)


class _FakeMailQueue:
    """An in-memory MailQueue (R4) that CAPTURES every enqueued MailJob — no SQS, no boto3."""

    def __init__(self):
        self.jobs = []

    def enqueue(self, job):
        self.jobs.append(job)


def _member_record(member_id, first_name, email, *, membership_type="erelid"):
    """A persisted member record addressable by a stable id (seeded straight via the repo)."""
    return {
        "tenant_id": "h-dcn",
        "member_id": member_id,
        "personal": {"first_name": first_name, "last_name": "Test", "email": email},
        "membership": {"membership_type": membership_type, "joined_date": "2024-01-01"},
        "overlay": {"region": "North"},
    }


class TestDeliverRouteEdge:
    """End-to-end deliver through the thin edge (route → handler → execute-and-deliver service
    over a FAKE mail queue). The queue capture proves the route enqueued; the 202 proves it is
    accepted-not-done (R4 queued, not synchronous)."""

    @pytest.fixture()
    def mail_queue(self):
        return _FakeMailQueue()

    @pytest.fixture(autouse=True)
    def inject_deliver_service(self, monkeypatch, repo, mail_queue):
        # Point the deliver dispatch seam at a service over the SAME real repo (so a set stored
        # via the CRUD/delivery routes is the one delivered) + the fake queue (never SQS). The
        # repo fixture backs the autouse membership service too, so both see the same table.
        from sam.members.domain.execute_and_deliver import ExecuteAndDeliverService
        from sam.members.handler import _dispatch as dispatch_mod

        deliver_service = ExecuteAndDeliverService(repo, _PassThroughPivot(), mail_queue)
        monkeypatch.setattr(
            dispatch_mod,
            "get_execute_and_deliver_service",
            lambda: deliver_service,
        )
        return deliver_service

    def _seed_set_with_delivery(self, delivery):
        """Create a set then store a delivery block on it via the routes; return its set_id."""
        set_id = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "Clubblad",
                        "kind": "list",
                        "definition": _list_definition(),
                    },
                )
            )
        )["set_id"]
        resp = app.handler(
            _event("PUT", f"/members/analytics-sets/{set_id}/delivery", body=delivery)
        )
        assert resp["statusCode"] == 200
        return set_id

    # ── happy path: 202 ACCEPTED + the fake queue captured the job(s) ────────────────────
    def test_deliver_to_fixed_returns_202_and_enqueues_one_job(self, repo, mail_queue):
        set_id = self._seed_set_with_delivery(_delivery_to_fixed())
        # A couple of members exist (to_fixed sends ONE job regardless of member count).
        repo.save_member("h-dcn", _member_record("m1", "Ava", "ava@example.com"))
        repo.save_member("h-dcn", _member_record("m2", "Ben", "ben@example.com"))

        resp = app.handler(_event("POST", f"/members/analytics-sets/{set_id}/deliver"))

        assert resp["statusCode"] == 202
        data = _data(resp)
        assert data["mode"] == "to_fixed"
        assert data["enqueued"] == 1  # to_fixed → exactly one job
        assert data["job_ids"] and len(data["job_ids"]) == 1
        # The fake queue genuinely captured the job (the route enqueued, never touched SQS).
        assert len(mail_queue.jobs) == 1
        job = mail_queue.jobs[0]
        assert job.mode == "to_fixed"
        assert job.recipients == ("agent@example.com", "office@example.com")

    def test_deliver_per_recipient_enqueues_one_job_per_mailable_member(
        self, repo, mail_queue
    ):
        set_id = self._seed_set_with_delivery(_delivery_per_recipient())
        repo.save_member("h-dcn", _member_record("m1", "Ava", "ava@example.com"))
        repo.save_member("h-dcn", _member_record("m2", "Ben", "ben@example.com"))

        resp = app.handler(_event("POST", f"/members/analytics-sets/{set_id}/deliver"))

        assert resp["statusCode"] == 202
        data = _data(resp)
        assert data["mode"] == "per_recipient"
        assert data["enqueued"] == 2  # one job per member with a resolvable address
        assert len(mail_queue.jobs) == 2
        assert sorted(r for job in mail_queue.jobs for r in job.recipients) == [
            "ava@example.com",
            "ben@example.com",
        ]

    # ── gate: members:export (403 without) ───────────────────────────────────────────────
    def test_deliver_without_export_is_403(self, repo):
        set_id = self._seed_set_with_delivery(_delivery_to_fixed())
        resp = app.handler(
            _event(
                "POST",
                f"/members/analytics-sets/{set_id}/deliver",
                capabilities=("members:read", "members:write", "members:admin"),
            )
        )
        assert resp["statusCode"] == 403

    def test_deliver_with_export_is_allowed(self, repo):
        set_id = self._seed_set_with_delivery(_delivery_to_fixed())
        resp = app.handler(
            _event(
                "POST",
                f"/members/analytics-sets/{set_id}/deliver",
                capabilities=("members:read", "members:export"),
            )
        )
        assert resp["statusCode"] == 202

    # ── 404 unknown set ──────────────────────────────────────────────────────────────────
    def test_deliver_unknown_set_returns_404(self, mail_queue):
        resp = app.handler(_event("POST", "/members/analytics-sets/ghost/deliver"))
        assert resp["statusCode"] == 404
        assert mail_queue.jobs == []  # nothing enqueued for a set that does not exist

    # ── 422 when the set has no delivery block (DeliveryNotConfigured) ────────────────────
    def test_deliver_set_without_delivery_block_returns_422(self, mail_queue):
        # A freshly-created set has NO delivery block → DeliveryNotConfigured → 422 (the set
        # exists, so NOT a 404 — "configure a delivery first").
        set_id = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/analytics-sets",
                    body={
                        "name": "No delivery",
                        "kind": "list",
                        "definition": _list_definition(),
                    },
                )
            )
        )["set_id"]
        resp = app.handler(_event("POST", f"/members/analytics-sets/{set_id}/deliver"))
        assert resp["statusCode"] == 422
        assert json.loads(resp["body"])["code"] == "errors.analyticsset.delivery.notConfigured"
        assert mail_queue.jobs == []  # nothing enqueued when there is nothing to send

    # ── cross-tenant isolation (Property 1) ──────────────────────────────────────────────
    def test_deliver_cross_tenant_is_404(self, monkeypatch, repo, mail_queue):
        from sam.tests.conftest import FakeScopeGrantsReader

        # A set with a delivery block exists under h-dcn.
        set_id = self._seed_set_with_delivery(_delivery_to_fixed())

        # Point the scope reader at a SECOND tenant and deliver the same set_id there — the
        # other tenant's partition has no such set → 404 (no cross-tenant reach), and nothing
        # is enqueued (never a 202 that would mail h-dcn's data for another tenant).
        monkeypatch.setattr(
            app,
            "_SCOPE_GRANTS_READER_OVERRIDE",
            FakeScopeGrantsReader({("other-tenant", _EMAIL_ALL): {"region": ["*"]}}),
        )
        resp = app.handler(
            _event(
                "POST",
                f"/members/analytics-sets/{set_id}/deliver",
                tenant="other-tenant",
            )
        )
        assert resp["statusCode"] == 404
        assert mail_queue.jobs == []
