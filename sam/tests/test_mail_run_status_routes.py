"""
SAM pytest for the SEND-RUN STATUS read ROUTES (``GET /members/mail-runs[/{run_id}]``,
mail-spec task 3.2) — the THIN pull-model status/history surface (R9.2/R9.3/R9.6).

Where ``test_mail_run_status_repository.py`` exercises the tenant-pinned REPOSITORY methods and
``test_mail_run_status.py`` the SERVICE scope rule in isolation, THIS file exercises the ROUTES
end-to-end through the thin edge: route table → router → handler → authn + authz → dispatch →
:class:`MailRunStatusService` over a FAKE repo → the JSON the screen renders. No AWS is touched
(the status-service seam is pointed at a service over an in-memory fake store).

What is pinned (design "Components and Interfaces" / Property 3):

- LIST returns the tenant's runs; a plain user sees ONLY their OWN (``triggered_by == sub``),
  a Tenant_Admin (holds ``members:admin``) sees ALL the tenant's runs (R9.3).
- SINGLE run returns the tally + its FAILURE drill-down (R9.2); the same scope applies — a user
  drilling into ANOTHER user's run is 404 (no probe), an admin into any tenant run is 200.
- A truly absent run is 404 for everyone.
- Gating: no token → 401; a caller WITHOUT ``members:export`` → 403; WITH it → 200.
- TENANCY: a second tenant's runs are never returned (Property 3) — the repo pins ``tenant_id``.
- The literal ``/members/mail-runs`` route is not shadowed by ``/members/{member_id}`` (nor by
  the ``mail`` literal of ``/members/mail/send``).

Validates: Requirements 9.2, 9.3, 9.6; design Property 3.
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

from sam.members.domain.mail_run_status import MailRunStatusService
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app

_EMAIL_ALL = "all@h-dcn.test"  # all-access → region ["*"] (scope grant for the export gate)
_HDCN_GRANTS = {("h-dcn", _EMAIL_ALL): {"region": ["*"]}}

_SUB_USER = "user-sub-1"
_SUB_OTHER = "user-sub-2"
_SUB_ADMIN = "admin-sub"


# ── An in-memory mail-run store (the MailRunStore seam the service reads) ────────────────


class FakeMailRunStore:
    """In-memory, tenant-pinned stand-in for the repo's task-3.1 mail-run read methods.

    Keyed by ``(tenant_id, run_id)`` so a run only ever matches within its own tenant — the
    isolation the real table + ``LeadingKeys`` enforce (Property 3). Satisfies the
    :class:`~sam.members.domain.mail_run_status.MailRunStore` seam by duck-typing.
    """

    def __init__(self):
        self.runs: dict[tuple, dict] = {}
        self.failures: dict[tuple, list] = {}

    def add_run(self, tenant_id, run_id, *, triggered_by, created_at, **tally):
        self.runs[(tenant_id, run_id)] = {
            "run_id": run_id,
            "triggered_by": triggered_by,
            "created_at": created_at,
            "tenant_id": tenant_id,
            "sk": f"mailrun#{run_id}",
            "ttl": 1234567890,
            **tally,
        }

    def add_failure(self, tenant_id, run_id, **entry):
        self.failures.setdefault((tenant_id, run_id), []).append(
            {
                "tenant_id": tenant_id,
                "sk": f"mailrecipient#{run_id}#0",
                "ttl": 1,
                "run_id": run_id,
                **entry,
            }
        )

    # The MailRunStore seam (tenant-pinned).
    def list_mail_runs(self, tenant_id):
        runs = [dict(v) for (t, _r), v in self.runs.items() if t == tenant_id]
        runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return runs

    def get_mail_run(self, tenant_id, run_id):
        item = self.runs.get((tenant_id, run_id))
        return dict(item) if item is not None else None

    def list_mail_run_failures(self, tenant_id, run_id):
        return [dict(f) for f in self.failures.get((tenant_id, run_id), [])]

    def delete_mail_run(self, tenant_id, run_id):
        # Tenant-pinned manual delete — purge the tally AND its FAILURE sub-records (R9.6).
        self.runs.pop((tenant_id, run_id), None)
        self.failures.pop((tenant_id, run_id), None)


@pytest.fixture()
def store() -> FakeMailRunStore:
    s = FakeMailRunStore()
    # Two of the caller's OWN runs + one OTHER user's run, all in h-dcn.
    s.add_run(
        "h-dcn", "run-own-1",
        triggered_by=_SUB_USER, created_at="2026-01-01T10:00:00Z",
        mode="per_recipient", status="completed", recipient_count=200, sent=198, failed=2,
    )
    s.add_run(
        "h-dcn", "run-own-2",
        triggered_by=_SUB_USER, created_at="2026-01-02T10:00:00Z",
        mode="to_fixed", status="completed", recipient_count=1, sent=1, failed=0,
    )
    s.add_run(
        "h-dcn", "run-other",
        triggered_by=_SUB_OTHER, created_at="2026-01-03T10:00:00Z",
        mode="per_recipient", status="sending", recipient_count=10, sent=5, failed=0,
    )
    # The caller's own run has two FAILURE sub-records (the drill-down).
    s.add_failure(
        "h-dcn", "run-own-1",
        address="bounce@example.com", status="failed", reason="MessageRejected",
    )
    s.add_failure(
        "h-dcn", "run-own-1",
        address="nope@example.com", status="failed", reason="MailFromDomainNotVerified",
    )
    # A SECOND tenant's run — must never be visible to an h-dcn caller (Property 3).
    s.add_run(
        "other-tenant", "run-foreign",
        triggered_by=_SUB_USER, created_at="2026-01-04T10:00:00Z",
        mode="to_fixed", status="completed", recipient_count=1, sent=1, failed=0,
    )
    return s


@pytest.fixture(autouse=True)
def inject_status_service(monkeypatch, store):
    """Point the status-read seam at a MailRunStatusService over the fake store (no AWS).

    Both mail-run routes resolve the service via ``get_mail_run_status_service()``; patching it
    here injects a service over the in-memory store. Also installs the all-access scope grant so
    the ``members:export`` gate's scope resolution does not deny (mirrors the ad-hoc route test).
    """
    from sam.tests.conftest import FakeScopeGrantsReader

    service = MailRunStatusService(store)
    monkeypatch.setattr(
        dispatch_mod, "get_mail_run_status_service", lambda: service
    )
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── event helper (verified API-GW-authorizer claims) ───────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    path,
    *,
    method="GET",
    tenant="h-dcn",
    capabilities=("members:read", "members:export"),
    email=_EMAIL_ALL,
    sub=_SUB_USER,
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
                    "email": email,
                    "cognito:groups": [],
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


# ── authn / authz (the gate — same members:export as the send routes) ───────────────────


class TestMailRunRouteAuth:
    def test_no_token_returns_401(self):
        resp = app.handler({"httpMethod": "GET", "path": "/members/mail-runs", "headers": {}})
        assert resp["statusCode"] == 401

    def test_without_export_capability_is_403(self):
        resp = app.handler(
            _event("/members/mail-runs", capabilities=("members:read", "members:write"))
        )
        assert resp["statusCode"] == 403

    def test_with_export_capability_is_200(self):
        resp = app.handler(_event("/members/mail-runs"))
        assert resp["statusCode"] == 200


# ── LIST scoping (R9.3): plain user sees own; admin sees all ────────────────────────────


class TestMailRunListScoping:
    def test_plain_user_sees_only_their_own_runs(self):
        resp = app.handler(_event("/members/mail-runs", sub=_SUB_USER))
        assert resp["statusCode"] == 200
        runs = _data(resp)
        ids = {r["run_id"] for r in runs}
        assert ids == {"run-own-1", "run-own-2"}  # NOT run-other
        # newest-first ordering is preserved from the repo.
        assert [r["run_id"] for r in runs] == ["run-own-2", "run-own-1"]

    def test_other_user_sees_only_their_own(self):
        resp = app.handler(_event("/members/mail-runs", sub=_SUB_OTHER))
        assert resp["statusCode"] == 200
        ids = {r["run_id"] for r in _data(resp)}
        assert ids == {"run-other"}

    def test_tenant_admin_sees_all_the_tenants_runs(self):
        resp = app.handler(
            _event(
                "/members/mail-runs",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp["statusCode"] == 200
        ids = {r["run_id"] for r in _data(resp)}
        assert ids == {"run-own-1", "run-own-2", "run-other"}

    def test_list_strips_storage_plumbing_keys(self):
        resp = app.handler(_event("/members/mail-runs"))
        for run in _data(resp):
            assert "tenant_id" not in run
            assert "sk" not in run
            assert "ttl" not in run
            # the status fields the screen needs survive
            assert {"run_id", "status", "sent", "failed", "recipient_count"} <= set(run)


# ── SINGLE run: tally + failure drill-down, scoped ──────────────────────────────────────


class TestMailRunDrilldown:
    def test_own_run_returns_tally_and_failures(self):
        resp = app.handler(_event("/members/mail-runs/run-own-1", sub=_SUB_USER))
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["run"]["run_id"] == "run-own-1"
        assert data["run"]["sent"] == 198
        assert data["run"]["failed"] == 2
        addrs = sorted(f["address"] for f in data["failures"])
        assert addrs == ["bounce@example.com", "nope@example.com"]
        # failure sub-records are shaped (plumbing stripped, reason surfaced).
        for f in data["failures"]:
            assert "sk" not in f and "ttl" not in f and "tenant_id" not in f
            assert "reason" in f

    def test_run_with_no_failures_returns_empty_failures(self):
        resp = app.handler(_event("/members/mail-runs/run-own-2", sub=_SUB_USER))
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["run"]["run_id"] == "run-own-2"
        assert data["failures"] == []

    def test_user_drilling_into_another_users_run_is_404(self):
        # run-other exists in the tenant but was triggered by _SUB_OTHER — a plain user gets a
        # 404 (no probe), indistinguishable from a truly-absent run.
        resp = app.handler(_event("/members/mail-runs/run-other", sub=_SUB_USER))
        assert resp["statusCode"] == 404

    def test_admin_can_drill_into_any_tenant_run(self):
        resp = app.handler(
            _event(
                "/members/mail-runs/run-other",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["run"]["run_id"] == "run-other"

    def test_absent_run_is_404_for_everyone(self):
        resp = app.handler(_event("/members/mail-runs/no-such-run", sub=_SUB_USER))
        assert resp["statusCode"] == 404
        resp_admin = app.handler(
            _event(
                "/members/mail-runs/no-such-run",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp_admin["statusCode"] == 404


# ── TENANCY (Property 3): a second tenant's runs are never visible ──────────────────────


class TestMailRunTenancy:
    def test_admin_list_never_includes_another_tenants_runs(self):
        resp = app.handler(
            _event(
                "/members/mail-runs",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        ids = {r["run_id"] for r in _data(resp)}
        assert "run-foreign" not in ids  # lives in other-tenant (Property 3)

    def test_cannot_drill_into_a_foreign_tenant_run(self):
        # run-foreign exists only in other-tenant; an h-dcn admin cannot see it (the repo pins
        # tenant_id, so the lookup in h-dcn finds nothing) → 404.
        resp = app.handler(
            _event(
                "/members/mail-runs/run-foreign",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp["statusCode"] == 404


# ── routing: the literal /members/mail-runs is not shadowed ─────────────────────────────


def test_route_not_shadowed_by_member_id_route():
    # A valid 200 (not a 404/501 from a member route) proves /members/mail-runs resolves to the
    # list route, not to /members/{member_id} with member_id="mail-runs".
    resp = app.handler(_event("/members/mail-runs"))
    assert resp["statusCode"] == 200


# ── DELETE /members/mail-runs/{run_id} — manual-delete retention (R9.6, task 3.3) ───────


class TestMailRunDeleteAuth:
    def test_no_token_returns_401(self):
        resp = app.handler(
            {"httpMethod": "DELETE", "path": "/members/mail-runs/run-own-1", "headers": {}}
        )
        assert resp["statusCode"] == 401

    def test_without_export_capability_is_403(self):
        resp = app.handler(
            _event(
                "/members/mail-runs/run-own-1",
                method="DELETE",
                capabilities=("members:read", "members:write"),
            )
        )
        assert resp["statusCode"] == 403


class TestMailRunDeleteScoping:
    def test_user_deletes_own_run(self, store):
        resp = app.handler(
            _event("/members/mail-runs/run-own-1", method="DELETE", sub=_SUB_USER)
        )
        assert resp["statusCode"] == 200
        # The tally AND its FAILURE sub-records are purged, tenant-pinned (R9.6).
        assert store.get_mail_run("h-dcn", "run-own-1") is None
        assert store.list_mail_run_failures("h-dcn", "run-own-1") == []

    def test_user_deleting_another_users_run_is_404_and_leaves_it(self, store):
        # run-other was triggered by _SUB_OTHER → a plain user gets a 404 (no probe) and the run
        # survives (deliberately indistinguishable from a truly-absent run).
        resp = app.handler(
            _event("/members/mail-runs/run-other", method="DELETE", sub=_SUB_USER)
        )
        assert resp["statusCode"] == 404
        assert store.get_mail_run("h-dcn", "run-other") is not None

    def test_admin_can_delete_another_users_run(self, store):
        resp = app.handler(
            _event(
                "/members/mail-runs/run-other",
                method="DELETE",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp["statusCode"] == 200
        assert store.get_mail_run("h-dcn", "run-other") is None

    def test_absent_run_is_404_for_everyone(self, store):
        resp = app.handler(
            _event("/members/mail-runs/no-such-run", method="DELETE", sub=_SUB_USER)
        )
        assert resp["statusCode"] == 404
        resp_admin = app.handler(
            _event(
                "/members/mail-runs/no-such-run",
                method="DELETE",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp_admin["statusCode"] == 404


class TestMailRunDeleteTenancy:
    def test_admin_cannot_delete_a_foreign_tenant_run(self, store):
        # run-foreign lives only in other-tenant; an h-dcn admin's delete pins tenant_id=h-dcn,
        # finds nothing → 404, and the foreign run is untouched (Property 3).
        resp = app.handler(
            _event(
                "/members/mail-runs/run-foreign",
                method="DELETE",
                capabilities=("members:read", "members:export", "members:admin"),
                sub=_SUB_ADMIN,
            )
        )
        assert resp["statusCode"] == 404
        assert store.get_mail_run("other-tenant", "run-foreign") is not None
