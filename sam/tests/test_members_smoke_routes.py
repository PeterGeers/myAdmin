"""
S5b Task 14.2 — **in-process route smoke test** for the Members module edge.

Task 14.2 as written asks to "smoke-test routes via curl with a test-pool token" against a
running ``sam local start-api``. That live-HTTP form is NOT reproducible in this environment:
the local API validates REAL Cognito tokens and this session cannot mint a validly-signed
bearer token from the shell, and long-running-server curl loops are disallowed here. So 14.2
is implemented as a **reproducible, in-process handler smoke test** that invokes the Members
Lambda handler directly (``sam.members.handler.app.handler(event)``) with crafted API-Gateway
proxy events, using the SAME test seams the existing Members tests use
(``sam/tests/conftest.py``, ``test_members_read_dispatch.py``, ``test_membership_type_catalog_read_routes.py``).
This gives the same route / scope / CORS coverage the curl smoke would, deterministically and
without AWS — the module edge behaviour is identical whether the event arrives over HTTP or in
process (the handler receives the same API-GW proxy dict either way).

Coverage (mirrors the task's REQUIRED smoke list):

1. ``GET /members`` (scoped list) → 200, ``{"data": [...]}`` envelope + CORS headers present.
2. Scope filtering (Property 4 / R2.4-2.6, deny-by-default): all-access grant → all members;
   a region-scoped grant → only that region; NO grant for the gating dimension → empty list.
3. ``GET /membership-types`` (catalog) → 200, tenant catalog + envelope + CORS.
4. ``POST /members/search`` (filtered list route, ``list_members_filtered``) → 200 + envelope
   + CORS.
5. CORS (R10.10): asserted on the 200 happy paths AND on an unauthenticated 401 error
   envelope — the module edge emits ``_CORS_HEADERS`` on every response incl. errors.
6. Tenant isolation smoke (Property 5): the fake repo captures the ``tenant_id`` it is queried
   for, and the smoke asserts only the verified tenant's partition is read (never a
   client-supplied header/body tenant).

The scope is driven through the projected-grant seam (``_SCOPE_GRANTS_READER_OVERRIDE`` via
the shared ``FakeScopeGrantsReader``) + the config-provider seam installed by conftest — NOT
AWS. The membership service runs over an in-memory fake repository injected at
``app._get_membership_service`` (the same seam the sibling read/catalog tests use).

Validates: Requirements R7.4, R10.10 (and Properties 4, 5 at the edge).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.handler import app
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.tests.conftest import FakeScopeGrantsReader


# ── Fake repository (member + catalog surface) with tenant-query capture ───────────────


class FakeMembersAndCatalogRepository:
    """In-memory repo exposing the member-list + catalog-list reads this smoke exercises.

    Members and catalog entries are keyed by ``tenant_id`` — a read cannot cross tenants (the
    same structural isolation the real repository enforces, Property 1). ``list_members``
    records every ``tenant_id`` it is queried for in ``queried_tenants`` so the smoke can
    assert tenant isolation (Property 5): only the verified tenant's partition is ever read.
    """

    def __init__(self):
        self.members: dict[tuple[str, str], dict] = {}
        self.catalog: dict[str, list[MembershipTypeEntry]] = {}
        self.queried_tenants: list[str] = []

    # -- members --------------------------------------------------------------
    def add_member(self, tenant_id, member):
        self.members[(tenant_id, member["member_id"])] = dict(member)

    def get_member(self, tenant_id, member_id):
        return self.members.get((tenant_id, member_id))

    def list_members(self, tenant_id, *, filters=None, scope_filter=None):
        self.queried_tenants.append(tenant_id)
        return [dict(m) for (t, _mid), m in self.members.items() if t == tenant_id]

    # -- catalog --------------------------------------------------------------
    def add_type(self, tenant_id, entry):
        self.catalog.setdefault(tenant_id, []).append(entry)

    def list_membership_types(self, tenant_id, *, active_only=False):
        entries = list(self.catalog.get(tenant_id, []))
        if active_only:
            entries = [e for e in entries if e.active]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_membership_type(self, tenant_id, type_code):
        for entry in self.catalog.get(tenant_id, []):
            if entry.type_code == type_code:
                return entry
        return None

    # -- unused-by-this-smoke Protocol members (raise if touched) -------------
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

    def save_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def deactivate_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


# ── Seeds ──────────────────────────────────────────────────────────────────────────────


def _member(member_id, *, region):
    return {
        "member_id": member_id,
        "personal": {"name": member_id, "contact": f"{member_id}@h-dcn.test"},
        "membership": {"member_number": member_id, "status": "active"},
        # S5d D1: scope is a plain member field now — h-dcn's `region` dimension binds to the
        # tenant-added `overlay.region` field (NOT the retired `scope_values` bucket).
        "overlay": {"region": region},
    }


def _type(code, *, label, active=True, order=0):
    return MembershipTypeEntry(
        tenant_id="h-dcn",
        type_code=code,
        label=label,
        active=active,
        order=order,
    )


# The three projected-grant intents (keyed by the caller's verified email), design C5.
_EMAIL_ALL = "all@h-dcn.test"        # all-access → region ["*"]
_EMAIL_NOORD = "noord@h-dcn.test"    # scoped to Noord
_EMAIL_NOGRANT = "nogrant@h-dcn.test"  # holds the capability but NO region grant → deny

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
    ("h-dcn", _EMAIL_NOORD): {"region": ["North"]},
    # _EMAIL_NOGRANT deliberately absent → deny-by-default (R2.6).
}


@pytest.fixture()
def repo():
    r = FakeMembersAndCatalogRepository()
    # Members across two regions so scope filtering is observable.
    r.add_member("h-dcn", _member("M-1", region="North"))
    r.add_member("h-dcn", _member("M-2", region="South"))
    r.add_member("h-dcn", _member("M-3", region="North"))
    # Membership-type catalog (a couple of active types + one retired).
    r.add_type("h-dcn", _type("regulier", label={"nl": "Regulier", "en": "Regular"}, order=10))
    r.add_type("h-dcn", _type("erelid", label={"nl": "Erelid", "en": "Honorary"}, order=20))
    r.add_type("h-dcn", _type("oud", label={"nl": "Oud", "en": "Old"}, active=False, order=30))
    return r


@pytest.fixture(autouse=True)
def inject(monkeypatch, repo):
    """Inject the MembershipService over the fake repo + the projected scope grants."""
    service = MembershipService(repo)
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── Event builder (verified API-GW-authorizer proxy event, v1 REST shape) ──────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read",),
    email=_EMAIL_ALL,
    sub="admin-sub",
    body=None,
    query=None,
):
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
                    "cognito:groups": [],
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


# ── Assertion helpers ──────────────────────────────────────────────────────────────────

_CORS_ORIGIN = "Access-Control-Allow-Origin"
_CORS_HEADERS = "Access-Control-Allow-Headers"
_CORS_METHODS = "Access-Control-Allow-Methods"


def _assert_cors(resp):
    """R10.10: every response carries the module edge's CORS headers."""
    headers = resp["headers"]
    assert headers[_CORS_ORIGIN] == "*"
    assert _CORS_HEADERS in headers
    assert _CORS_METHODS in headers


def _assert_data_envelope(resp):
    """The handler wraps every success as ``{"data": <result>}``."""
    body = json.loads(resp["body"])
    assert "data" in body
    return body["data"]


def _member_ids(resp):
    return sorted(m["member_id"] for m in _assert_data_envelope(resp))


# ── 1. GET /members — scoped-list happy path (200 + envelope + CORS) ───────────────────


def test_get_members_returns_200_with_data_envelope_and_cors():
    resp = app.handler(_event("GET", "/members", email=_EMAIL_ALL))
    assert resp["statusCode"] == 200
    data = _assert_data_envelope(resp)
    assert isinstance(data, list) and len(data) == 3  # all seeded members (all-access)
    _assert_cors(resp)


# ── 2. Scope filtering — Property 4 (deny-by-default) ──────────────────────────────────


def test_get_members_all_access_grant_sees_all():
    resp = app.handler(_event("GET", "/members", email=_EMAIL_ALL))
    assert resp["statusCode"] == 200
    assert _member_ids(resp) == ["M-1", "M-2", "M-3"]


def test_get_members_region_scoped_grant_sees_only_that_region():
    # Projected grant region ["Noord"] → only the Noord members (M-1, M-3), NOT the Zuid one.
    resp = app.handler(_event("GET", "/members", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert _member_ids(resp) == ["M-1", "M-3"]


def test_get_members_no_grant_for_gating_dimension_is_empty_deny_by_default():
    # Holds members:read + a Members_CRUD-style capability but NO projected region grant →
    # deny-by-default → empty list (never tenant-wide) — R2.6 / Property 4.
    resp = app.handler(_event("GET", "/members", email=_EMAIL_NOGRANT))
    assert resp["statusCode"] == 200
    assert _assert_data_envelope(resp) == []
    _assert_cors(resp)


# ── 3. GET /membership-types — catalog (200 + envelope + CORS) ─────────────────────────


def test_get_membership_types_returns_catalog_with_envelope_and_cors():
    resp = app.handler(_event("GET", "/membership-types", email=_EMAIL_ALL))
    assert resp["statusCode"] == 200
    data = _assert_data_envelope(resp)
    codes = [e["type_code"] for e in data]
    # Management default: ALL entries incl. the retired one, ordered by (order, type_code).
    assert codes == ["regulier", "erelid", "oud"]
    _assert_cors(resp)


def test_get_membership_types_active_only_narrows_to_assignable():
    resp = app.handler(
        _event("GET", "/membership-types", email=_EMAIL_ALL, query={"active_only": "true"})
    )
    assert resp["statusCode"] == 200
    codes = [e["type_code"] for e in _assert_data_envelope(resp)]
    assert codes == ["regulier", "erelid"]
    assert "oud" not in codes


# ── 4. POST /members/search — filtered list route (list_members_filtered) ──────────────


def test_post_members_search_returns_200_with_envelope_and_cors():
    resp = app.handler(
        _event("POST", "/members/search", email=_EMAIL_ALL, body={"status": "active"})
    )
    assert resp["statusCode"] == 200
    assert _member_ids(resp) == ["M-1", "M-2", "M-3"]
    _assert_cors(resp)


def test_post_members_search_is_scope_filtered():
    # The filtered-list route is subgroup-filtered by the same projected grant as GET /members.
    resp = app.handler(
        _event("POST", "/members/search", email=_EMAIL_NOORD, body={"status": "active"})
    )
    assert resp["statusCode"] == 200
    assert _member_ids(resp) == ["M-1", "M-3"]


# ── 5. CORS on an error envelope — R10.10 ──────────────────────────────────────────────


def test_cors_headers_present_on_unauthenticated_error():
    # No verified claims → 401 error envelope; the edge still emits CORS (R10.10).
    resp = app.handler({"httpMethod": "GET", "path": "/members", "headers": {}})
    assert resp["statusCode"] == 401
    _assert_cors(resp)


# ── 6. Tenant isolation smoke — Property 5 ─────────────────────────────────────────────


def test_only_the_verified_tenant_partition_is_queried(repo):
    # An X-Tenant header claiming a different tenant must be ignored: the verified entitlement
    # (h-dcn) is the ONLY source of tenant context, so the repo is queried for h-dcn alone.
    event = _event("GET", "/members", email=_EMAIL_ALL)
    event["headers"] = {"X-Tenant": "other-tenant"}
    resp = app.handler(event)
    assert resp["statusCode"] == 200
    assert repo.queried_tenants == ["h-dcn"]
