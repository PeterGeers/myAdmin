"""
S5 Task 3.2 — tests for the Members handler **READ-route dispatch** (design C1 read → C2/C6).

These pin the wiring the thin handler now performs for the READ routes: once a request is
authenticated + authorized (task 3.0) and its scope is resolved (task 3.1), the edge
delegates to the generic membership engine (C2), threads the router's path params
(``{member_id}`` / ``{membership_id}``) + the requester ``sub`` + the route's
``self_service`` flag, and shapes the domain result into an HTTP response:

- a granted + scoped READ request returns **200** with the scope-narrowed data (not 501);
- a wildcard (admin) caller sees the tenant's data; a scoped caller sees only their subset;
- a deny (empty scope) list returns 200 with an empty list (never tenant-wide);
- ``get_member`` for an out-of-scope / missing member returns **404** (no existence leak);
- self-service (``/members/me``, own ``{member_id}``) returns the caller's own record;
- the WRITE routes are still **501** (Step 5).

The domain service is exercised over an in-memory fake repository injected at the edge (via
``app._get_membership_service``), so these are true edge→domain→repo dispatch tests without
boto3 / AWS. Auth is supplied as verified API-GW-authorizer claims (the task-3.0 gate).

Validates: Requirements R1.2, R3.1, R3.3, R6.1
"""

from __future__ import annotations

import json

import pytest

from sam.members.handler import app
from sam.members.domain.membership_service import MembershipService


# ── Fake repository + injected service ─────────────────────────────────────────────────


class FakeMembersRepository:
    """Minimal in-memory repository for edge-dispatch tests (read surface only)."""

    def __init__(self):
        self.members = {}
        self.memberships = {}
        self.payments = {}

    def add_member(self, tenant_id, member):
        self.members[(tenant_id, member["member_id"])] = dict(member)

    def add_membership(self, tenant_id, member_id, membership):
        self.memberships[(tenant_id, member_id, membership["membership_id"])] = dict(membership)

    def add_payment(self, tenant_id, member_id, payment):
        self.payments.setdefault((tenant_id, member_id), []).append(dict(payment))

    def get_member(self, tenant_id, member_id):
        return self.members.get((tenant_id, member_id))

    def list_members(self, tenant_id, *, filters=None, scope_filter=None):
        return [dict(m) for (t, _mid), m in self.members.items() if t == tenant_id]

    def get_membership(self, tenant_id, member_id, membership_id):
        return self.memberships.get((tenant_id, member_id, membership_id))

    def list_memberships(self, tenant_id, member_id):
        return [
            dict(ms)
            for (t, mid, _msid), ms in self.memberships.items()
            if t == tenant_id and mid == member_id
        ]

    def list_member_payments(self, tenant_id, member_id):
        return [dict(p) for p in self.payments.get((tenant_id, member_id), [])]


def _member(member_id, *, region=None, sub=None, contact=None):
    rec = {
        "member_id": member_id,
        "personal": {"name": member_id, "contact": contact or f"{member_id}@x.com"},
        "membership": {"member_number": member_id, "status": "active"},
    }
    if region is not None:
        rec["scope_values"] = {"region": [region]}
    if sub is not None:
        rec["sub"] = sub
    return rec


@pytest.fixture()
def repo():
    r = FakeMembersRepository()
    r.add_member("h-dcn", _member("M-1", region="Noord", sub="sub-noord"))
    r.add_member("h-dcn", _member("M-2", region="Zuid", sub="sub-zuid"))
    r.add_membership("h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"})
    r.add_payment("h-dcn", "M-1", {"payment_id": "P-1", "amount": 42})
    return r


# ── Projected scope grants (S5b task 8.3, design C5) ──────────────────────────────────
#
# The caller's scope now comes from the PROJECTED ``scopegrant#`` rows (design C5), NOT the
# token groups. Each test caller is identified by an EMAIL, and the edge reads that email's
# grants for the gating dimension (``region``). We map the S5 scope intents to projected
# grants keyed by email: all-access → ``["*"]``, a region → that subset, and a
# ``required_for`` caller with NO grant is simply ABSENT (deny-by-default).

_EMAIL_ALL = "all@h-dcn.test"       # all-access → region ["*"]
_EMAIL_NOORD = "noord@h-dcn.test"   # scoped to Noord
_EMAIL_ZUID = "zuid@h-dcn.test"     # scoped to Zuid
_EMAIL_NOGRANT = "nogrant@h-dcn.test"  # holds Members_CRUD but NO region grant → deny

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
    ("h-dcn", _EMAIL_NOORD): {"region": ["Noord"]},
    ("h-dcn", _EMAIL_ZUID): {"region": ["Zuid"]},
    # _EMAIL_NOGRANT deliberately absent → deny-by-default (R2.6).
}


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, repo):
    """Inject a MembershipService over the fake repo + the projected scope grants (task 8.3)."""
    from sam.tests.conftest import FakeScopeGrantsReader

    service = MembershipService(repo)
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── Auth helpers (verified API-GW-authorizer claims — the task-3.0 gate) ────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read", "members:export"),
    email=_EMAIL_ALL,
    groups=(),
    sub="admin-sub",
    body=None,
):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants,
    design C5), not ``groups`` — ``groups`` is kept only so token-role claims stay realistic.
    """
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": None,
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


# ── list_members ────────────────────────────────────────────────────────────────────


def test_list_members_wildcard_returns_all_and_not_501():
    # All-access projected grant (region ["*"]) → sees the whole tenant. 200 (not 501).
    resp = app.handler(_event("GET", "/members", email=_EMAIL_ALL))
    assert resp["statusCode"] == 200
    ids = sorted(m["member_id"] for m in _data(resp))
    assert ids == ["M-1", "M-2"]


def test_list_members_scoped_returns_only_the_subset():
    # Projected grant region ["Noord"] → scoped to Noord → only M-1 is visible.
    resp = app.handler(_event("GET", "/members", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert [m["member_id"] for m in _data(resp)] == ["M-1"]


def test_list_members_deny_scope_returns_empty_list():
    # A required_for capability (Members_CRUD) held with NO projected region grant → the grant
    # is ABSENT → deny → empty list (never tenant-wide) — Property 4 / R2.6.
    resp = app.handler(_event("GET", "/members", email=_EMAIL_NOGRANT, groups=("Members_CRUD",)))
    assert resp["statusCode"] == 200
    assert _data(resp) == []


def test_list_members_filtered_via_post_search():
    resp = app.handler(
        _event("POST", "/members/search", email=_EMAIL_ALL, body={"status": "active"})
    )
    assert resp["statusCode"] == 200
    assert sorted(m["member_id"] for m in _data(resp)) == ["M-1", "M-2"]


# ── export_members ──────────────────────────────────────────────────────────────────


def test_export_members_scoped():
    resp = app.handler(_event("GET", "/members/export", email=_EMAIL_ZUID))
    assert resp["statusCode"] == 200
    assert [m["member_id"] for m in _data(resp)] == ["M-2"]


# ── get_member ──────────────────────────────────────────────────────────────────────


def test_get_member_in_scope_returns_the_member():
    resp = app.handler(_event("GET", "/members/M-1", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert _data(resp)["member_id"] == "M-1"


def test_get_member_out_of_scope_returns_404():
    # Scoped to Noord, asking for the Zuid member → indistinguishable 404 (no existence leak).
    resp = app.handler(_event("GET", "/members/M-2", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 404


def test_get_member_missing_returns_404():
    resp = app.handler(_event("GET", "/members/nope", email=_EMAIL_ALL))
    assert resp["statusCode"] == 404


def test_get_member_self_service_reads_own_record_without_scope():
    # Caller has NO region grant (deny scope) but owns M-2 via sub → self-service allows it.
    resp = app.handler(
        _event("GET", "/members/M-2", email=_EMAIL_NOGRANT, groups=("Members_CRUD",), sub="sub-zuid")
    )
    assert resp["statusCode"] == 200
    assert _data(resp)["member_id"] == "M-2"


# ── get_self ──────────────────────────────────────────────────────────────────────────


def test_get_self_returns_own_record():
    # /members/me has no capability (pure self-service); tenant context still from entitlement.
    resp = app.handler(
        _event("GET", "/members/me", capabilities=("members:read",), sub="sub-noord")
    )
    assert resp["statusCode"] == 200
    assert _data(resp)["member_id"] == "M-1"


def test_get_self_unknown_sub_returns_404():
    resp = app.handler(
        _event("GET", "/members/me", capabilities=("members:read",), sub="nobody")
    )
    assert resp["statusCode"] == 404


# ── membership + payment reads ─────────────────────────────────────────────────────────


def test_list_memberships_for_visible_member():
    resp = app.handler(
        _event("GET", "/members/M-1/memberships", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 200
    assert [m["membership_id"] for m in _data(resp)] == ["MS-1"]


def test_get_membership_for_visible_member():
    resp = app.handler(
        _event("GET", "/members/M-1/memberships/MS-1", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 200
    assert _data(resp)["status"] == "active"


def test_get_membership_out_of_scope_member_returns_404():
    resp = app.handler(
        _event("GET", "/members/M-2/memberships/MS-1", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 404


def test_get_member_payments_for_visible_member():
    resp = app.handler(
        _event("GET", "/members/M-1/payments", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 200
    assert [p["amount"] for p in _data(resp)] == [42]


def test_get_member_payments_out_of_scope_returns_404():
    resp = app.handler(
        _event("GET", "/members/M-2/payments", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 404


# ── path params reach the domain (threaded through RequestContext) ─────────────────────


def test_path_params_are_threaded_to_the_domain(monkeypatch):
    captured = {}

    class _Spy:
        def get_membership(self, tenant_id, member_id, membership_id, allowed_scopes, **kw):
            captured.update(
                tenant_id=tenant_id, member_id=member_id, membership_id=membership_id
            )
            return {"ok": True}

    monkeypatch.setattr(app, "_get_membership_service", lambda: _Spy())
    resp = app.handler(
        _event("GET", "/members/M-7/memberships/MS-42", email=_EMAIL_ALL)
    )
    assert resp["statusCode"] == 200
    assert captured == {"tenant_id": "h-dcn", "member_id": "M-7", "membership_id": "MS-42"}


# ── WRITE routes are now wired (Step 5 / task 5.2) — full coverage in test_members_write_dispatch ──


def test_write_route_now_dispatches_to_the_domain(monkeypatch):
    # The WRITE routes are no longer the 501 stub — they dispatch to the domain write path.
    # (End-to-end write behaviour is pinned in test_members_write_dispatch.py.)
    captured = {}

    class _Spy:
        def create_member(self, tenant_id, body, allowed_scopes, **kw):
            captured.update(tenant_id=tenant_id, body=dict(body), scopes=list(allowed_scopes))
            return {"member_id": "M-new", **dict(body)}

    monkeypatch.setattr(app, "_get_membership_service", lambda: _Spy())
    resp = app.handler(
        _event(
            "POST",
            "/members",
            capabilities=("members:write",),
            email=_EMAIL_ALL,
            body={"personal": {"name": "x"}},
        )
    )
    assert resp["statusCode"] == 200
    assert captured["tenant_id"] == "h-dcn"
    assert captured["scopes"] == ["*"]
