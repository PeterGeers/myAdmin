"""
S5 Task 5.3 — tests for the Lidmaatschap Beheer catalog **WRITE routes** + the authoritative
``membership_type`` reference validation on member create/update (design C8, R2.4/R1.4).

Two things this task closes, both pinned end-to-end through the thin edge over the SAME faithful
in-memory ``FakeDynamoTable`` + ``DynamoDbMembersRepository`` the repository/write tests use
(real soft-delete + conditional-write behaviour, no mocks):

1. **Catalog WRITE routes** (``members:admin`` gated, C8):
   - ``POST /membership-types`` — create; a duplicate ``type_code`` is a **409** (never a
     silent overwrite of a live type); a malformed body is a **422**.
   - ``PUT /membership-types/{type_code}`` — update; **404** for an absent code.
   - ``DELETE /membership-types/{type_code}`` — **soft-delete** (retire → ``active=false``),
     NOT a hard delete: the entry stays gettable in the management view and only leaves the
     active-only dropdown feed; **404** for an absent code.

2. **Authoritative reference validation** (design C8, closing the loop 5.2 deferred): a member
   ``create``/``update`` validates in the DOMAIN that ``membership.membership_type`` references
   a LIVE (``active=true``) catalog entry for the tenant (the React dropdown is convenience
   only — never trusted). An unknown or retired type → **422**; a live type → OK. An EXISTING
   member that references a since-retired type stays readable AND updatable when the update
   does not change the type (no retroactive invalidation of stored members).

Validates: Requirements R2.4, R1.4 (design C8; Property 1, 2)
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.handler import app
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import (
    MemberValidationError,
    MembershipService,
    MembershipTypeConflict,
    MembershipTypeNotFound,
)
from sam.members.domain.membership_type_catalog import (
    MembershipTypeEntry,
    MembershipTypeValidationError,
)
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks
from sam.members.repository.members_repository import DynamoDbMembersRepository

# The faithful in-memory DynamoDB fake (transactional conditional writes + atomic counter +
# soft-delete-preserving catalog behaviour).
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
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        tenant_hooks=hooks,
    )


# Scope is driven by the caller's verified EMAIL via the PROJECTED grants (design C5), NOT the
# token groups (s5c Phase 0 removed the group-derived scope path). The catalog-write walkthrough
# uses an all-access caller, so grant that email region ["*"]; a Members_CRUD holder with NO
# region grant would deny-by-default (covered by the sibling test_members_write_dispatch tests).
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


def _seed_types(repo, *codes_and_active):
    for code, active in codes_and_active:
        repo.save_membership_type(
            "h-dcn",
            MembershipTypeEntry(
                tenant_id="h-dcn", type_code=code, label={"nl": code, "en": code}, active=active
            ),
        )


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(method, path, *, tenant="h-dcn",
           capabilities=("members:read", "members:write", "members:admin", "members:export"),
           email=_EMAIL_ALL, groups=(), sub="admin-sub", body=None, query=None):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants,
    design C5) — not ``groups`` (s5c Phase 0 removed the group-derived scope path)."""
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


def _valid_member_body(*, region="Noord", member_number=None, status=None, membership_type="erelid"):
    membership = {"membership_type": membership_type, "joined_date": "2024-01-01"}
    if member_number is not None:
        membership["member_number"] = member_number
    if status is not None:
        membership["status"] = status
    # S5d D1/R3.4: scope is a PLAIN member field — h-dcn's `region` dimension binds to the
    # tenant-added `overlay.region` field, a scalar (no retired `scope_values` bucket).
    return {
        "personal": {"first_name": "Alex", "last_name": "de Vries", "email": "alex@example.com"},
        "membership": membership,
        "overlay": {"region": region},
    }


# =====================================================================================
# Catalog WRITE — domain layer (MembershipService)
# =====================================================================================


class TestCatalogWriteDomain:
    def test_create_persists_and_returns_management_shape(self, service, repo):
        out = service.create_membership_type(
            "h-dcn", {"type_code": "erelid", "label": {"nl": "Erelid", "en": "Honorary"}, "order": 10}
        )
        assert out == {
            "type_code": "erelid",
            "label": {"nl": "Erelid", "en": "Honorary"},
            "active": True,
            "order": 10,
        }
        # Genuinely persisted in the tenant partition.
        assert repo.get_membership_type("h-dcn", "erelid").label["nl"] == "Erelid"

    def test_create_ignores_body_tenant_id(self, service, repo):
        # Verify-before-trust: a body tenant_id can never redirect the write (Property 2).
        service.create_membership_type(
            "h-dcn", {"type_code": "x", "label": {"nl": "X"}, "tenant_id": "evil"}
        )
        assert repo.get_membership_type("h-dcn", "x") is not None
        assert repo.get_membership_type("evil", "x") is None

    def test_create_duplicate_code_raises_conflict(self, service, repo):
        _seed_types(repo, ("erelid", True))
        with pytest.raises(MembershipTypeConflict):
            service.create_membership_type("h-dcn", {"type_code": "erelid", "label": {"nl": "E"}})

    def test_create_malformed_body_raises_validation_error(self, service):
        # Blank code + missing nl label → the entity validation fails loudly (a 422 at the edge).
        with pytest.raises(MembershipTypeValidationError):
            service.create_membership_type("h-dcn", {"type_code": "", "label": {}})

    def test_update_merges_and_persists(self, service, repo):
        _seed_types(repo, ("erelid", True))
        out = service.update_membership_type(
            "h-dcn", "erelid", {"label": {"nl": "Erelid+", "en": "Honorary"}, "order": 99}
        )
        assert out["label"]["nl"] == "Erelid+"
        assert out["order"] == 99
        assert repo.get_membership_type("h-dcn", "erelid").order == 99

    def test_update_absent_code_raises_not_found(self, service):
        with pytest.raises(MembershipTypeNotFound):
            service.update_membership_type("h-dcn", "ghost", {"label": {"nl": "x"}})

    def test_deactivate_soft_deletes_not_hard(self, service, repo):
        _seed_types(repo, ("erelid", True))
        out = service.deactivate_membership_type("h-dcn", "erelid")
        assert out["active"] is False
        # NOT hard-deleted: still gettable in the management view.
        stored = repo.get_membership_type("h-dcn", "erelid")
        assert stored is not None and stored.active is False

    def test_deactivate_absent_code_raises_not_found(self, service):
        with pytest.raises(MembershipTypeNotFound):
            service.deactivate_membership_type("h-dcn", "ghost")

    def test_deactivate_excludes_from_active_feed_but_keeps_in_management(self, service, repo):
        _seed_types(repo, ("erelid", True), ("donateur", True))
        service.deactivate_membership_type("h-dcn", "donateur")
        active_codes = {e["value"] for e in service._active_membership_type_options("h-dcn")}
        assert active_codes == {"erelid"}  # retired type left the dropdown feed
        mgmt_codes = {e["type_code"] for e in service.list_membership_types("h-dcn")}
        assert mgmt_codes == {"erelid", "donateur"}  # but stays in the management view


# =====================================================================================
# Catalog WRITE — edge dispatch (routes → handler → domain → repo)
# =====================================================================================


class TestCatalogWriteEdge:
    def test_create_route_returns_200_and_persists(self, repo):
        resp = app.handler(
            _event("POST", "/membership-types", body={"type_code": "erelid", "label": {"nl": "Erelid"}, "order": 10})
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["type_code"] == "erelid"
        assert repo.get_membership_type("h-dcn", "erelid") is not None

    def test_create_route_duplicate_returns_409(self, repo):
        _seed_types(repo, ("erelid", True))
        resp = app.handler(
            _event("POST", "/membership-types", body={"type_code": "erelid", "label": {"nl": "E"}})
        )
        assert resp["statusCode"] == 409

    def test_create_route_malformed_returns_422(self):
        resp = app.handler(_event("POST", "/membership-types", body={"type_code": "", "label": {}}))
        assert resp["statusCode"] == 422
        # v1.0: errors is an RFC 9457 array of {field, code, detail}.
        fields = {e["field"] for e in json.loads(resp["body"])["errors"]}
        assert "type_code" in fields

    def test_update_route_returns_200(self, repo):
        _seed_types(repo, ("erelid", True))
        resp = app.handler(
            _event("PUT", "/membership-types/erelid", body={"order": 42})
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["order"] == 42

    def test_update_route_absent_returns_404(self):
        resp = app.handler(_event("PUT", "/membership-types/ghost", body={"order": 1}))
        assert resp["statusCode"] == 404

    def test_delete_route_soft_deletes_returns_200(self, repo):
        _seed_types(repo, ("erelid", True))
        resp = app.handler(_event("DELETE", "/membership-types/erelid"))
        assert resp["statusCode"] == 200
        assert _data(resp)["active"] is False
        # Still present (soft-delete), just retired.
        assert repo.get_membership_type("h-dcn", "erelid").active is False

    def test_delete_route_absent_returns_404(self):
        resp = app.handler(_event("DELETE", "/membership-types/ghost"))
        assert resp["statusCode"] == 404

    def test_retired_type_excluded_from_dropdown_feed_but_gettable(self, repo):
        _seed_types(repo, ("erelid", True))
        app.handler(_event("DELETE", "/membership-types/erelid"))
        # Management get still returns it (with active=false).
        got = app.handler(_event("GET", "/membership-types/erelid"))
        assert got["statusCode"] == 200 and _data(got)["active"] is False
        # But the active-only management list excludes it.
        active_list = app.handler(_event("GET", "/membership-types", query={"active_only": "true"}))
        assert all(e["type_code"] != "erelid" for e in _data(active_list))

    def test_write_routes_require_admin_capability(self, repo):
        _seed_types(repo, ("erelid", True))
        # A caller with only members:write (not members:admin) is forbidden on catalog writes.
        for method, path, body in (
            ("POST", "/membership-types", {"type_code": "new", "label": {"nl": "N"}}),
            ("PUT", "/membership-types/erelid", {"order": 1}),
            ("DELETE", "/membership-types/erelid", None),
        ):
            resp = app.handler(
                _event(method, path, capabilities=("members:read", "members:write"), body=body)
            )
            assert resp["statusCode"] == 403, f"{method} {path} should be admin-gated"

    def test_write_routes_require_auth(self):
        resp = app.handler({"httpMethod": "POST", "path": "/membership-types", "headers": {}})
        assert resp["statusCode"] in (401, 403)


# =====================================================================================
# Authoritative membership_type reference validation on member create/update (C8)
# =====================================================================================


class TestMembershipTypeReferenceValidation:
    def test_create_member_with_live_type_ok(self, repo):
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="1001", membership_type="erelid")
        resp = app.handler(_event("POST", "/members", body=body))
        assert resp["statusCode"] == 200
        mid = _data(resp)["member_id"]  # system-minted uuid (create ignores any body id)
        assert repo.get_member("h-dcn", mid) is not None

    def test_create_member_with_unknown_type_returns_422(self, repo):
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="1002", membership_type="does-not-exist")
        body["member_id"] = "M-2"
        resp = app.handler(_event("POST", "/members", body=body))
        assert resp["statusCode"] == 422
        fields = {e["field"] for e in json.loads(resp["body"])["errors"]}
        assert "membership.membership_type" in fields

    def test_create_member_with_retired_type_returns_422(self, repo):
        _seed_types(repo, ("erelid", True), ("retired_type", False))
        body = _valid_member_body(member_number="1003", membership_type="retired_type")
        body["member_id"] = "M-3"
        resp = app.handler(_event("POST", "/members", body=body))
        assert resp["statusCode"] == 422
        fields = {e["field"] for e in json.loads(resp["body"])["errors"]}
        assert "membership.membership_type" in fields

    def test_create_member_unknown_type_is_not_persisted(self, repo):
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="1004", membership_type="bogus")
        body["member_id"] = "M-4"
        app.handler(_event("POST", "/members", body=body))
        assert repo.get_member("h-dcn", "M-4") is None  # rejected before persist

    def test_update_member_change_to_unknown_type_returns_422(self, repo):
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="2001", membership_type="erelid")
        create = app.handler(_event("POST", "/members", body=body))
        assert create["statusCode"] == 200
        mid = _data(create)["member_id"]
        # Patch the type to an unknown code → 422.
        resp = app.handler(
            _event("PUT", f"/members/{mid}", body={"membership": {"membership_type": "nope"}})
        )
        assert resp["statusCode"] == 422

    def test_update_member_change_to_live_type_ok(self, repo):
        _seed_types(repo, ("erelid", True), ("donateur", True))
        body = _valid_member_body(member_number="2002", membership_type="erelid")
        create = app.handler(_event("POST", "/members", body=body))
        mid = _data(create)["member_id"]
        resp = app.handler(
            _event("PUT", f"/members/{mid}", body={"membership": {"membership_type": "donateur"}})
        )
        assert resp["statusCode"] == 200
        assert repo.get_member("h-dcn", mid)["membership"]["membership_type"] == "donateur"

    def test_existing_member_with_since_retired_type_stays_readable(self, repo):
        # Create against a live type, THEN retire the type. The stored member is unchanged and
        # still readable — no retroactive invalidation (C8).
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="3001", membership_type="erelid")
        create = app.handler(_event("POST", "/members", body=body))
        mid = _data(create)["member_id"]
        app.handler(_event("DELETE", "/membership-types/erelid"))  # retire the type
        got = app.handler(_event("GET", f"/members/{mid}"))
        assert got["statusCode"] == 200
        assert _data(got)["membership"]["membership_type"] == "erelid"

    def test_existing_member_with_since_retired_type_updatable_when_not_changing_type(self, repo):
        # An update that does NOT touch membership_type must NOT fail because the stored type
        # was since retired (partial-update friendliness, C8).
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="3002", membership_type="erelid")
        create = app.handler(_event("POST", "/members", body=body))
        mid = _data(create)["member_id"]
        app.handler(_event("DELETE", "/membership-types/erelid"))  # retire the type
        resp = app.handler(
            _event("PUT", f"/members/{mid}", body={"personal": {"first_name": "Renamed"}})
        )
        assert resp["statusCode"] == 200
        assert repo.get_member("h-dcn", mid)["personal"]["first_name"] == "Renamed"

    def test_reference_check_is_tenant_scoped(self, repo):
        # 'erelid' is live for h-dcn only. A member create for h-dcn works; the same type is
        # not implicitly valid for another tenant (each catalog is the tenant's own).
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="4001", membership_type="erelid")
        body["member_id"] = "M-30"
        assert app.handler(_event("POST", "/members", body=body))["statusCode"] == 200

    def test_domain_reference_error_message_names_the_field(self, service, repo):
        _seed_types(repo, ("erelid", True))
        body = _valid_member_body(member_number="5001", membership_type="ghost")
        body["member_id"] = "M-40"
        with pytest.raises(MemberValidationError) as exc:
            service.create_member("h-dcn", body, {"region": ["*"]})
        assert "membership.membership_type" in exc.value.errors
