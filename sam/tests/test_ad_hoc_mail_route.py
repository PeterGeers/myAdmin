"""
SAM pytest for the AD-HOC send ROUTE (``POST /members/mail/send``, mail-spec task 2.1) — the
THIN stateless edge that is the SIBLING of the saved-set ``POST .../deliver`` route.

Where ``test_ad_hoc_mail_send.py`` exercises the SERVICE (``send_ad_hoc``) over its ports, THIS
file exercises the ROUTE end-to-end through the thin edge: route table → router → handler →
authn + authz → ``_parse_ad_hoc_body`` → ``get_execute_and_deliver_service().send_ad_hoc(...)``
→ ``AcceptedResult`` (202). The deliver seam is pointed at a service over a FAKE mail queue that
CAPTURES jobs, so no AWS/SQS is touched. What is pinned (design "two thin routes, ONE shared
send service"):

- No token → 401; a caller WITHOUT ``members:export`` → 403; WITH it → 202 (same gate as
  the saved-set deliver route).
- A ``per_recipient`` ad-hoc body → one job per mailable row (202); a ``to_fixed`` body → one
  job to the fixed list (202). The From = the tenant's ``noreply@<domain>`` and Reply-To = the
  verified user are stamped on every job (R2/R4).
- A NOT-CERTIFIED tenant → 422 ``errors.mail.notCertified`` with the typed reason and NO
  enqueue (no substitute sender — R4.2/R5.2).
- A MALFORMED body (unknown mode / to_fixed with no recipients) → 422 ``errors.mail.adHocInvalid``
  and NO enqueue.
- The literal ``/members/mail/send`` route is not shadowed by ``/members/{member_id}``.

Validates: Requirements R2, R8.1
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

from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.handler import app
from sam.members.repository.members_repository import DynamoDbMembersRepository
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks
from sam.tests.test_members_repository import FakeDynamoTable

_EMAIL_ALL = "all@h-dcn.test"  # all-access → region ["*"]
_HDCN_GRANTS = {("h-dcn", _EMAIL_ALL): {"region": ["*"]}}
_PATH = "/members/mail/send"


# ── Service wired like production: real repo over the fake table + h-dcn config/hooks ──


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


@pytest.fixture()
def service(repo) -> MembershipService:
    return MembershipService(
        repo,
        lifecycle_provider=StaticLifecycleConfigProvider(
            {"h-dcn": HDCN_LIFECYCLE_CONFIG}
        ),
        tenant_hooks=register_hdcn_hooks(TenantHookRegistry()),
    )


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, service):
    from sam.tests.conftest import FakeScopeGrantsReader

    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── fakes for the shared send service (no SQS, no boto3) ────────────────────────────────


class _FakeMailQueue:
    """An in-memory MailQueue that CAPTURES every enqueued MailJob — no SQS, no boto3."""

    def __init__(self):
        self.jobs = []

    def enqueue(self, job):
        self.jobs.append(job)


class _CertifiedMailConfig:
    """A static MailConfigReader modelling a CERTIFIED tenant (``certified=False`` → refusal)."""

    def __init__(self, *, certified=True, domain="h-dcn.nl"):
        self._certified = certified
        self._domain = domain

    def is_mail_enabled(self, tenant_id):
        return bool(tenant_id)

    def is_mail_certified(self, tenant_id):
        return bool(tenant_id) and self._certified

    def get_mail_domain(self, tenant_id):
        return self._domain if tenant_id else None

    def get_mail_local_part(self, tenant_id):
        return "noreply"


@pytest.fixture()
def mail_queue():
    return _FakeMailQueue()


@pytest.fixture(autouse=True)
def inject_send_service(monkeypatch, repo, mail_queue):
    """Point the send dispatch seam at a service over the fake queue + a CERTIFIED resolver.

    The ad-hoc route delegates to ``get_execute_and_deliver_service().send_ad_hoc(...)`` — the
    SAME seam the saved-set deliver route uses. The service here runs over the fake queue (never
    SQS) and a certified-by-default resolver (the happy path); a dedicated test re-points the
    seam at an un-certified resolver for the refusal branch.
    """
    from sam.members.domain.execute_and_deliver import ExecuteAndDeliverService
    from sam.members.domain.mail_sender_resolver import MailSenderResolver
    from sam.members.handler import _dispatch as dispatch_mod

    send_service = ExecuteAndDeliverService(
        repo,
        None,  # the PivotRunner is unused on the ad-hoc path (rows ride on the body)
        mail_queue,
        MailSenderResolver(_CertifiedMailConfig()),
    )
    monkeypatch.setattr(
        dispatch_mod, "get_execute_and_deliver_service", lambda: send_service
    )
    return send_service


# ── event helper (verified API-GW-authorizer claims) ───────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    *,
    tenant="h-dcn",
    capabilities=("members:read", "members:export"),
    email=_EMAIL_ALL,
    sub="admin-sub",
    body=None,
):
    return {
        "httpMethod": "POST",
        "path": _PATH,
        "headers": {},
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


def _member(first_name, email):
    return {
        "member_id": first_name.lower(),
        "first_name": first_name,
        "personal": {"email": email, "first_name": first_name},
        "membership_type": "lid",
    }


def _per_recipient_body():
    return {
        "mode": "per_recipient",
        "template_id": "tpl-1",
        "result_rows": [
            _member("Ava", "ava@example.com"),
            _member("Ben", "ben@example.com"),
        ],
    }


def _to_fixed_body():
    return {
        "mode": "to_fixed",
        "recipients": ["agent@example.com", "office@example.com"],
        "attachment": "csv",
        "result_rows": [_member("Ava", "ava@example.com")],
    }


# ── authn / authz (the gate — same as the saved-set deliver route) ──────────────────────


class TestAdHocRouteAuth:
    def test_no_token_returns_401(self):
        event = {"httpMethod": "POST", "path": _PATH, "headers": {}}
        resp = app.handler(event)
        assert resp["statusCode"] == 401

    def test_without_export_capability_is_403(self, mail_queue):
        resp = app.handler(
            _event(
                capabilities=("members:read", "members:write", "members:admin"),
                body=_per_recipient_body(),
            )
        )
        assert resp["statusCode"] == 403
        assert mail_queue.jobs == []  # a denied request never reaches the send service

    def test_with_export_capability_is_accepted(self, mail_queue):
        resp = app.handler(
            _event(capabilities=("members:read", "members:export"), body=_to_fixed_body())
        )
        assert resp["statusCode"] == 202
        assert len(mail_queue.jobs) == 1


# ── happy path: both fan-out modes enqueue + 202 ────────────────────────────────────────


class TestAdHocRouteEnqueue:
    def test_per_recipient_returns_202_and_enqueues_one_job_per_row(self, mail_queue):
        resp = app.handler(_event(body=_per_recipient_body()))

        assert resp["statusCode"] == 202
        data = _data(resp)
        assert data["mode"] == "per_recipient"
        assert data["enqueued"] == 2
        assert len(data["job_ids"]) == 2
        assert len(mail_queue.jobs) == 2
        assert sorted(r for job in mail_queue.jobs for r in job.recipients) == [
            "ava@example.com",
            "ben@example.com",
        ]

    def test_to_fixed_returns_202_and_enqueues_exactly_one_job(self, mail_queue):
        resp = app.handler(_event(body=_to_fixed_body()))

        assert resp["statusCode"] == 202
        data = _data(resp)
        assert data["mode"] == "to_fixed"
        assert data["enqueued"] == 1
        assert len(mail_queue.jobs) == 1
        job = mail_queue.jobs[0]
        assert job.recipients == ("agent@example.com", "office@example.com")
        assert job.attachment == {"kind": "csv", "label_options": None}

    def test_stamps_resolved_from_and_verified_reply_to_on_every_job(self, mail_queue):
        # The edge stamps the AUTHORITATIVE tenant From (noreply@<domain>) + the verified user
        # email as Reply-To from the JWT claim — never a body value (verify-before-trust).
        resp = app.handler(_event(body=_per_recipient_body()))

        assert resp["statusCode"] == 202
        assert len(mail_queue.jobs) == 2
        for job in mail_queue.jobs:
            assert job.from_address == "noreply@h-dcn.nl"
            assert job.reply_to == _EMAIL_ALL
            assert job.tenant_id == "h-dcn"


# ── not-certified: 422 errors.mail.notCertified, no enqueue ─────────────────────────────


class TestAdHocRouteNotCertified:
    def test_not_certified_tenant_returns_422_and_enqueues_nothing(
        self, monkeypatch, repo, mail_queue
    ):
        from sam.members.domain.execute_and_deliver import ExecuteAndDeliverService
        from sam.members.domain.mail_sender_resolver import MailSenderResolver
        from sam.members.handler import _dispatch as dispatch_mod

        uncertified = ExecuteAndDeliverService(
            repo,
            None,
            mail_queue,
            MailSenderResolver(_CertifiedMailConfig(certified=False)),
        )
        monkeypatch.setattr(
            dispatch_mod, "get_execute_and_deliver_service", lambda: uncertified
        )

        resp = app.handler(_event(body=_per_recipient_body()))

        assert resp["statusCode"] == 422
        body = json.loads(resp["body"])
        assert body["code"] == "errors.mail.notCertified"
        assert body["reason"] == "not_certified"  # the TYPED machine reason
        assert mail_queue.jobs == []  # nothing enqueued, no substitute sender


# ── malformed body: 422 errors.mail.adHocInvalid, no enqueue ────────────────────────────


class TestAdHocRouteMalformedBody:
    def test_unknown_mode_returns_422_adhoc_invalid(self, mail_queue):
        resp = app.handler(
            _event(body={"mode": "broadcast", "result_rows": [_member("Ava", "a@x.io")]})
        )
        assert resp["statusCode"] == 422
        assert json.loads(resp["body"])["code"] == "errors.mail.adHocInvalid"
        assert mail_queue.jobs == []

    def test_to_fixed_with_no_recipients_returns_422_adhoc_invalid(self, mail_queue):
        resp = app.handler(
            _event(
                body={
                    "mode": "to_fixed",
                    "recipients": [],
                    "attachment": "csv",
                    "result_rows": [_member("Ava", "a@x.io")],
                }
            )
        )
        assert resp["statusCode"] == 422
        assert json.loads(resp["body"])["code"] == "errors.mail.adHocInvalid"
        assert mail_queue.jobs == []

    def test_empty_body_returns_422_adhoc_invalid(self, mail_queue):
        # An absent body → mode None → the service's "unknown delivery mode" refusal (422),
        # the honest "the compose is malformed" answer rather than a silent no-op.
        resp = app.handler(_event(body=None))
        assert resp["statusCode"] == 422
        assert json.loads(resp["body"])["code"] == "errors.mail.adHocInvalid"
        assert mail_queue.jobs == []


# ── routing: the literal /members/mail/send is not shadowed by /members/{member_id} ─────


def test_route_not_shadowed_by_member_id_route(mail_queue):
    # A valid 202 (not a 404/501 from a member route) proves the literal /mail/send resolves
    # to the ad-hoc send route, not to /members/{member_id} with member_id="mail".
    resp = app.handler(_event(body=_to_fixed_body()))
    assert resp["statusCode"] == 202
