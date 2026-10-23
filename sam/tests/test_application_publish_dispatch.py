"""
Spec 12 Task 2.1 — the application-form PUBLISH route + readiness-gate SCAFFOLD (design §C4 / R5).

These pin the observable security + routing + readiness contract of the EXPLICIT publish action
(OQ1 = option 1) end-to-end through the thin Members Lambda edge (``sam/members/handler/app.py`` +
``_dispatch.py`` + ``routes.py``), and the readiness gate at the domain level — WITHOUT touching
live AWS. Per the task-2.1 "scaffold, handler dormant" scope the live S3 render/write + CloudFront
invalidation is task 2.2: the route + readiness gate are REAL and tested here; the ONLY dormant
part is the live write, which the publish seam defers via ``PublishPipelineNotWired``.

What each part of the task maps to here (design §C4 / R5.4 / D15 / spec 11 R6):

- **members:admin + self_service=False gate (R5.1):** a non-admin caller is rejected (403) and the
  publish service is NEVER reached (no readiness check, no write).
- **tenant_id from the verified token, never the body (R2):** the service is handed the VERIFIED
  tenant; a rogue body tenant can never redirect the publish target.
- **Readiness refusals (R5.4):** missing slug / missing certified sender / no on-form field each
  REFUSE with a clear, admin-facing 409 carrying the TYPED reason, and NO write is attempted.
- **READY tenant reaches the publish seam (scaffold):** a tenant that passes all three
  preconditions reaches the (dormant) live-write seam — asserted here as the task-2.2
  not-yet-wired 501, NOT a live S3 write. Task 2.2 swaps the stub for the real pipeline and flips
  this to assert the artifact.
- **Readiness is REUSED, not duplicated:** the certified-sender precondition is the authoritative
  ``is_send_ready`` predicate (certified flag AND a projected domain) — the SAME gate the submit
  edge uses — and the on-form-field precondition counts ``get_public_field_config``'s filtered
  ``fields`` (the single filter authority), so publish and submit never drift.

Reuses the ``h-dcn`` tenant id (the spec 11 / spec 12 real-data tenant) for the fixtures.

Validates: Requirements 5.1, 5.4 (spec 12); D15 / spec 11 R6 readiness
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

from sam.members.domain.application_publish import (
    ApplicationPublishService,
    PublishNotReady,
    PublishNotReadyReason,
    PublishPipelineNotWired,
)
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app

_TENANT = "h-dcn"


# ── In-memory seams for the publish service (no boto3, no DynamoDB) ───────────────────


class FakeSlugReader:
    """In-memory ``FormSlugReader`` — returns a configured slug (or ``None`` = no slug)."""

    def __init__(self, slug):
        self._slug = slug

    def get_form_slug(self, tenant_id):
        return self._slug


class FakeFieldConfigReader:
    """In-memory ``PublicFieldConfigReader`` — returns a schema with ``n`` on-form fields.

    Mirrors ``get_public_field_config``'s 200 contract: ``fields`` is the ALREADY-filtered
    on-form list (only ``application_visible`` fields), so the publish gate counts it directly.
    """

    def __init__(self, on_form_field_count):
        self._n = on_form_field_count

    def get_public_field_config(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "fields": [{"key": f"f{i}"} for i in range(self._n)],
            "locales": ["nl", "en"],
            "notice": {"version": None},
        }


def _service(
    *, slug="hdcn-application-form", certified=True, domain="h-dcn.nl", fields=1
):
    """Build a publish service over fully in-memory seams.

    Defaults describe a fully-READY tenant (slug + certified sender + 1 on-form field). Each test
    knocks out ONE precondition to exercise its refusal. ``certified``/``domain`` feed the SAME
    fail-closed ``StaticMailReadinessProvider`` the submit readiness gate uses, so the publish
    "certified sender" check is the authoritative ``is_send_ready`` predicate, not a re-impl.
    """
    readiness = StaticMailReadinessProvider({_TENANT: (certified, domain)})
    return ApplicationPublishService(
        slug_reader=FakeSlugReader(slug),
        readiness_provider=readiness,
        field_config_reader=FakeFieldConfigReader(fields),
    )


# ── Domain-level readiness gate (R5.4 / D15) ──────────────────────────────────────────


def test_publish_ready_tenant_reaches_the_dormant_live_write_seam():
    # A fully-ready tenant (slug + certified sender + >=1 on-form field) PASSES the readiness gate
    # and reaches the publish seam. In the task-2.1 scaffold the live S3 write is task 2.2, so the
    # seam raises PublishPipelineNotWired carrying the resolved slug. (Task 2.2 replaces this with
    # the real render/write/invalidation and this test flips to assert the artifact.)
    svc = _service()
    with pytest.raises(PublishPipelineNotWired) as exc:
        svc.publish(_TENANT)
    assert exc.value.slug == "hdcn-application-form"


def test_publish_refuses_when_no_slug_and_attempts_no_write():
    # No stored slug → the admin has not authored a public address yet. Refuse with the typed
    # NO_SLUG reason BEFORE reaching the (dormant) write seam.
    svc = _service(slug=None)
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_SLUG


def test_publish_refuses_when_blank_slug():
    # A blank/whitespace slug is "no public address yet" too.
    svc = _service(slug="   ")
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_SLUG


def test_publish_refuses_when_sender_not_certified():
    # Slug present but the tenant's mail is not certified → no usable sender → refuse NO_CERTIFIED_SENDER.
    svc = _service(certified=False)
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_CERTIFIED_SENDER


def test_publish_refuses_when_certified_but_no_domain():
    # The authoritative is_send_ready predicate needs BOTH the certified flag AND a projected
    # domain. Certified-but-no-domain is NOT send-ready → the same NO_CERTIFIED_SENDER refusal.
    svc = _service(certified=True, domain=None)
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_CERTIFIED_SENDER


def test_publish_refuses_when_no_on_form_field():
    # Slug + certified sender present but ZERO fields on the form → never emit a fieldless
    # artifact → refuse NO_ON_FORM_FIELD.
    svc = _service(fields=0)
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_ON_FORM_FIELD


def test_publish_readiness_checks_slug_first_then_sender_then_field():
    # Fixed precedence (slug → sender → field) so the admin is told the FIRST thing to fix. With
    # ALL three missing, the refusal is NO_SLUG.
    svc = _service(slug=None, certified=False, fields=0)
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_SLUG


# ── Edge end-to-end: auth gate + dispatch wiring + status mapping ─────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: list(capabilities)}})


def _event(
    *,
    tenant=_TENANT,
    capabilities=("members:admin",),
    sub="admin-sub",
    email="admin@h-dcn.test",
    body=None,
    with_auth=True,
):
    """A verified API-GW-authorizer ``POST /members/application-form/publish`` event."""
    event = {
        "httpMethod": "POST",
        "path": "/members/application-form/publish",
        "headers": {},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
    }
    if with_auth:
        event["requestContext"] = {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "custom:entitlements": _entitlement(tenant, capabilities),
                }
            }
        }
    return event


def _envelope(resp):
    return json.loads(resp["body"])


class _SpyPublishService:
    """Records publish() calls + returns a configured outcome (or raises a configured error)."""

    def __init__(self, *, raises=None, result=None):
        self.calls = []
        self._raises = raises
        self._result = result if result is not None else {"success": True}

    def publish(self, tenant_id):
        self.calls.append(tenant_id)
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture()
def spy():
    return _SpyPublishService()


@pytest.fixture(autouse=True)
def inject_publish_service(monkeypatch, spy):
    """Wire the EDGE's publish seam to the spy (the dispatch resolves through this accessor)."""
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: spy)
    return spy


def test_handler_no_token_returns_401_and_never_publishes(spy):
    resp = app.handler(_event(with_auth=False))
    assert resp["statusCode"] == 401
    assert spy.calls == []  # auth failed before dispatch


def test_handler_non_admin_returns_403_and_never_publishes(spy):
    # A verified caller holding members:write (NOT members:admin) → the route's members:admin gate
    # denies with 403, and the publish service is NEVER reached (no readiness check, no write).
    resp = app.handler(
        _event(capabilities=("members:write", "members:read", "members:export"))
    )
    assert resp["statusCode"] == 403
    assert spy.calls == []


def test_handler_tenant_not_in_entitlement_returns_403(spy):
    # The token entitles a DIFFERENT tenant with no admin for the active one → 403, no publish.
    resp = app.handler(_event(tenant="other-tenant", capabilities=("members:read",)))
    assert resp["statusCode"] == 403
    assert spy.calls == []


def test_handler_admin_dispatches_with_verified_tenant_not_body(monkeypatch):
    # members:admin caller → the route dispatches to the publish service with the VERIFIED tenant
    # (never the body). The spy returns a ready-ish result so we assert the dispatch + tenant only.
    spy = _SpyPublishService(result={"success": True, "slug": "hdcn-application-form"})
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: spy)
    resp = app.handler(_event(body={"tenant_id": "evil-tenant"}))
    assert resp["statusCode"] == 200
    assert spy.calls == [_TENANT]  # verified tenant, not the rogue body value


@pytest.mark.parametrize(
    "reason",
    [
        PublishNotReadyReason.NO_SLUG,
        PublishNotReadyReason.NO_CERTIFIED_SENDER,
        PublishNotReadyReason.NO_ON_FORM_FIELD,
    ],
)
def test_handler_readiness_refusal_is_a_clear_409_with_typed_reason(
    monkeypatch, reason
):
    # Each readiness refusal surfaces as a clear, admin-facing 409 carrying the TYPED machine
    # reason (show-don't-block, R5.4) — distinct from a 422 (malformed body) / 404. No write.
    spy = _SpyPublishService(raises=PublishNotReady(reason))
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: spy)
    resp = app.handler(_event())
    assert resp["statusCode"] == 409
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.application.publishNotReady"
    assert env["reason"] == reason.value
    assert spy.calls == [_TENANT]


def test_handler_ready_tenant_reaches_dormant_seam_returns_501_not_500(monkeypatch):
    # A READY tenant reaches the (dormant task-2.2) publish seam → a caller-safe 501, NOT a 500,
    # NOT a live S3 write. This is the scaffold seam task 2.2 swaps for the real pipeline + flips
    # to a 200 artifact assertion.
    spy = _SpyPublishService(raises=PublishPipelineNotWired("hdcn-application-form"))
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: spy)
    resp = app.handler(_event())
    assert resp["statusCode"] == 501
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.application.publishNotWired"


def test_handler_real_service_end_to_end_ready_tenant_is_501(monkeypatch):
    # End-to-end through the REAL publish service (not the spy) over in-memory seams: a fully-ready
    # tenant reaches the dormant seam → 501. Pins the whole edge→dispatch→service→seam path.
    monkeypatch.setattr(
        dispatch_mod, "get_application_publish_service", lambda: _service()
    )
    resp = app.handler(_event())
    assert resp["statusCode"] == 501
    assert _envelope(resp)["code"] == "errors.application.publishNotWired"


def test_handler_real_service_end_to_end_unready_tenant_is_409(monkeypatch):
    # End-to-end through the REAL service: an unready tenant (no slug) → a clear 409 with the typed
    # reason, no write.
    monkeypatch.setattr(
        dispatch_mod, "get_application_publish_service", lambda: _service(slug=None)
    )
    resp = app.handler(_event())
    assert resp["statusCode"] == 409
    env = _envelope(resp)
    assert env["code"] == "errors.application.publishNotReady"
    assert env["reason"] == PublishNotReadyReason.NO_SLUG.value
