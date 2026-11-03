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
    FORM_OWNER_KIND,
    FORM_OWNER_PLANE,
    FORM_RESOURCE_REF,
    PUBLIC_API_BASE_ENV_VAR,
    ApplicationPublishService,
    PublishNotReady,
    PublishNotReadyReason,
    PublishPipelineNotWired,
    PublishSlugConflict,
    PublishSlugRejected,
)
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app
from sam.members.repository.slug_marker_store import SlugMarker

_TENANT = "h-dcn"

#: The publish-time public API base baked into the artifact (bugfix `bugfix-published-form-submit`
#: Task 3.1). The render step resolves `PUBLIC_API_BASE_URL` fail-fast (no silent default), so every
#: ready-tenant publish path here must have it set — this autouse fixture supplies a representative
#: value. The dedicated fail-fast test (`test_publish_fails_fast_when_public_api_base_env_missing`)
#: UN-sets it to pin the no-default behaviour.
_PUBLIC_API_BASE = "https://api.jabaki.nl"


@pytest.fixture(autouse=True)
def _set_public_api_base_env(monkeypatch):
    """Set the publish-time `PUBLIC_API_BASE_URL` for every test (bugfix Task 3.1).

    Change-with-tests (steering 34/39): the publish render step now resolves the public API base
    from this env var fail-fast (no silent default). A ready-tenant publish therefore requires it
    to be set — this fixture supplies a representative base so the existing readiness / claim /
    live-write assertions still exercise their intended paths. Tests that pin the fail-fast raise
    un-set it locally via monkeypatch.
    """
    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, _PUBLIC_API_BASE)


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
    # A fully-ready tenant (slug + certified sender + >=1 on-form field) PASSES the readiness gate,
    # RENDERS the artifact (spec 14 Task 2.2), and reaches the publish seam. The LIVE S3 write is
    # still dormant (spec 14 Task 8/9), so the seam raises PublishPipelineNotWired carrying the
    # resolved slug. (The gated live-write task replaces this with the real write + invalidation
    # and this test flips to assert the written artifact.)
    svc = _service()
    with pytest.raises(PublishPipelineNotWired) as exc:
        svc.publish(_TENANT)
    assert exc.value.slug == "hdcn-application-form"


def test_publish_ready_tenant_renders_the_shell_via_page_shell_before_the_dormant_seam():
    # Spec 14 Task 2.2 (change-with-tests): a READY tenant's publish now WIRES the shell render
    # through the shared `page_shell` BEFORE the dormant live-write seam. Assert the service
    # composed a full <!DOCTYPE html> document (the page_shell scaffold) and stashed it on
    # `_rendered_html` — i.e. the SAM form renders its shell via page_shell (R7.1), even though
    # the live S3 write stays gated (the seam still raises). Output PARITY against a fixture is
    # the separate task 2.3; here we pin only that the render path runs and uses the shared shell.
    svc = _service()
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    rendered = svc._rendered_html
    # page_shell scaffold markers (the shared, plane-neutral shell owns these):
    assert rendered.startswith("<!DOCTYPE html>")
    assert "<head>" in rendered and "<style>" in rendered and "<body>" in rendered
    # the applicant form body the SAM producer composed from get_public_field_config:
    assert 'class="application-form"' in rendered
    assert 'name="f0"' in rendered  # the one on-form field from the fake config
    # canonical head_meta wired from the slug (SEO scaffold through page_shell):
    # Pin the slug-derived URL AS the canonical href (the full page_shell tag), not as a
    # bare substring — asserting the whole tag is stricter (it must appear as the canonical
    # link, not merely somewhere in the blob) and avoids the incomplete-URL-sanitization
    # pattern a bare `in <url>` membership check trips (CodeQL py/incomplete-url-substring-sanitization).
    assert (
        '<link rel="canonical" href="https://hdcn-application-form.jabaki.nl/" />'
        in rendered
    )


def test_publish_unready_tenant_renders_nothing():
    # The readiness gate runs BEFORE the render: an unready tenant (no slug) refuses with
    # PublishNotReady and NO artifact is rendered (`_rendered_html` never set).
    svc = _service(slug=None)
    with pytest.raises(PublishNotReady):
        svc.publish(_TENANT)
    assert not hasattr(svc, "_rendered_html")


# ── bugfix bugfix-published-form-submit Task 3.1 — publish-time public API base (fail-fast) ──


def test_publish_fails_fast_when_public_api_base_env_missing(monkeypatch):
    # bugfix Task 3.1 / R2.6: the public API base is resolved from `PUBLIC_API_BASE_URL` with NO
    # silent default (the GOVERNANCE_PROJECTION_TABLE fail-fast model). A READY tenant whose
    # publish-time env var is unset must FAIL LOUDLY at the render step rather than bake the wrong
    # backend into the artifact. (The `DynamoDBConfigError` from the shared `require_env` helper is
    # the fail-fast raise; importing it lazily keeps this the ONLY place the test names it.)
    from services.dynamodb_client import DynamoDBConfigError

    monkeypatch.delenv(PUBLIC_API_BASE_ENV_VAR, raising=False)
    svc = _service()  # fully ready — reaches the render step
    with pytest.raises(DynamoDBConfigError):
        svc.publish(_TENANT)
    # Fail-fast at the render resolution: no artifact was baked with a wrong/absent base.
    assert not hasattr(svc, "_rendered_html")


def test_publish_blank_public_api_base_env_also_fails_fast(monkeypatch):
    # A blank/whitespace value is treated as missing too (no silent default) — the shared
    # `require_env` rejects unset AND blank identically.
    from services.dynamodb_client import DynamoDBConfigError

    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, "   ")
    svc = _service()
    with pytest.raises(DynamoDBConfigError):
        svc.publish(_TENANT)


def test_publish_threads_slug_and_resolved_api_base_into_the_render(monkeypatch):
    # bugfix Task 3.1: the publish step resolves the base from the env var and threads BOTH the
    # resolved base AND the slug into `render_application_form_page`, so a LATER task's submit
    # script can target `POST {base}/public/members/{slug}/applications`. Assert the renderer is
    # called with the resolved base + slug (the carry-through), without asserting any emitted
    # submit markup yet (that is Task 3.2).
    import sam.members.domain.application_publish as publish_mod

    real_render = publish_mod.render_application_form_page
    captured = {}

    def _spy_render(config, **kwargs):
        captured.update(kwargs)
        # Delegate to the real renderer so `_rendered_html` is still a valid document.
        return real_render(config, **kwargs)

    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, "https://api.example.test")
    monkeypatch.setattr(publish_mod, "render_application_form_page", _spy_render)
    svc = _service(slug="hdcn-application-form")
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    assert captured.get("slug") == "hdcn-application-form"
    assert captured.get("public_api_base") == "https://api.example.test"


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


# ════════════════════════════════════════════════════════════════════════════════════
# spec 14 Task 8.1 — the publish flow CLAIMS its slug (live write still dormant) [R3, R4]
#
# Change-with-tests (steering 34/39): wiring the slug CLAIM into the publish flow is a
# behavioral change, so its paired coverage lands here. These pin the 8.1 contract:
#
#   * publish CLAIMS the slug via the shared `_slugs/{slug}` marker for the owning tenant,
#     with the owner BODY {owner_plane=sam, kind=application_form, tenant_id, resource_ref=
#     config#fields};
#   * a same-owner re-publish is IDEMPOTENT (succeeds, no SlugTaken, marker left in place);
#   * a FOREIGN-owned slug is NOT clobbered → PublishSlugConflict (caller-safe), no write;
#   * format/reserved + SEC-4 prefix ownership run BEFORE the claim → PublishSlugRejected;
#   * the ORDERING is readiness → render → format → SEC-4 prefix → claim → dormant seam;
#   * the LIVE write stays DORMANT (PublishPipelineNotWired still fires after a successful
#     claim; no real S3 artifact put).
#
# Proven against the REAL claim semantics: the real `S3SlugMarkerStore` over a
# conditional-honouring in-memory fake S3 client (the established sibling pattern), NEVER a
# mock that trivially returns success. The BROAD paired battery is task 8.2 — these cover
# only 8.1's own wiring and intentionally do not duplicate it.
#
# Validates: Requirements R3.1, R3.2, R4.4, R4.5 (spec 14)
# ════════════════════════════════════════════════════════════════════════════════════

import io as _io

from sam.members.repository.slug_marker_store import (
    S3SlugMarkerStore,
    SlugTaken,
)

_CLAIM_BUCKET = "myadmin-public-pages-test"


class _FakeClientError(Exception):
    """Stand-in for botocore's ClientError with the structured ``.response`` shape the store reads."""

    def __init__(self, code, status, message="boom"):
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }
        super().__init__(f"{code}: {message}")


class _ConditionalFakeS3:
    """In-memory S3 client that HONOURS ``If-None-Match: *`` + get/delete (sibling test pattern).

    Real conditional-PUT semantics (a second PUT on an existing key → 412 PreconditionFailed) so
    the real ``S3SlugMarkerStore.claim`` exercises its actual idempotent/clobber logic — not a
    mock that returns success regardless. No boto3, no AWS.
    """

    def __init__(self):
        self.objects = {}
        self.put_calls = []

    def put_object(
        self, *, Bucket, Key, Body, ContentType=None, Metadata=None, IfNoneMatch=None
    ):
        self.put_calls.append({"Key": Key, "IfNoneMatch": IfNoneMatch})
        key = (Bucket, Key)
        if IfNoneMatch == "*" and key in self.objects:
            raise _FakeClientError("PreconditionFailed", 412, "object exists")
        self.objects[key] = {
            "body": Body
            if isinstance(Body, (bytes, bytearray))
            else str(Body).encode("utf-8"),
            "meta": dict(Metadata or {}),
        }
        return {}

    def get_object(self, *, Bucket, Key):
        key = (Bucket, Key)
        if key not in self.objects:
            raise _FakeClientError("NoSuchKey", 404, "missing")
        obj = self.objects[key]
        return {"Body": _io.BytesIO(obj["body"]), "Metadata": dict(obj["meta"])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}


class FakePrefixReader:
    """In-memory ``PublicPrefixReader`` — returns a configured prefix (or ``None`` = no prefix)."""

    def __init__(self, prefix):
        self._prefix = prefix

    def get_public_prefix(self, tenant_id):
        return self._prefix


def _claim_service(
    *,
    slug="h-dcn-aanmelden",
    certified=True,
    domain="h-dcn.nl",
    fields=1,
    prefix="h-dcn",
    store=None,
):
    """A publish service WIRED with a real ``S3SlugMarkerStore`` (over a conditional fake) + prefix.

    Unlike the task-2.1 ``_service`` (no store → claim is a no-op), this is the Task-8.1 shape:
    the claim step is active. The default slug ``h-dcn-aanmelden`` is well-formed AND sits under
    the default ``h-dcn`` prefix, so a fully-ready tenant claims cleanly then hits the dormant seam.
    """
    readiness = StaticMailReadinessProvider({_TENANT: (certified, domain)})
    marker_store = (
        store
        if store is not None
        else S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_CLAIM_BUCKET)
    )
    svc = ApplicationPublishService(
        slug_reader=FakeSlugReader(slug),
        readiness_provider=readiness,
        field_config_reader=FakeFieldConfigReader(fields),
        slug_marker_store=marker_store,
        prefix_reader=FakePrefixReader(prefix),
    )
    return svc, marker_store


def test_publish_claims_the_slug_for_the_owning_tenant_then_hits_dormant_seam():
    # A ready tenant renders, then CLAIMS the `_slugs/{slug}` marker with the form owner body, and
    # reaches the still-dormant live-write seam (claim != live artifact write).
    svc, store = _claim_service()
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    marker = store.resolve("h-dcn-aanmelden")
    assert marker is not None
    assert marker.owner_plane == FORM_OWNER_PLANE == "sam"
    assert marker.kind == FORM_OWNER_KIND == "application_form"
    assert marker.tenant_id == _TENANT
    assert marker.resource_ref == FORM_RESOURCE_REF == "config#fields"


def test_publish_same_owner_republish_is_idempotent_no_conflict():
    # Re-publishing the SAME slug by the SAME owner must SUCCEED idempotently (claim matches the
    # existing body) — no PublishSlugConflict. Both publishes reach only the dormant seam.
    svc, store = _claim_service()
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)  # first publish claims it
    # Second publish over the SAME store — the marker already exists for THIS owner.
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)  # idempotent re-claim, NOT a conflict
    # Still exactly one marker, still owned by this tenant (never clobbered/duplicated).
    assert store.resolve("h-dcn-aanmelden").tenant_id == _TENANT


def test_publish_does_not_clobber_a_foreign_owned_slug():
    # The slug is ALREADY owned by a FOREIGN owner (different plane/kind/tenant). Publish must
    # REFUSE with the caller-safe PublishSlugConflict and NEVER overwrite the foreign marker, and
    # must NOT reach the live-write seam (no write on a conflict).
    shared = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_CLAIM_BUCKET)
    # Pre-seed a foreign claim on the slug this tenant wants.
    shared.claim(
        "h-dcn-aanmelden",
        SlugMarker(
            owner_plane="flask",
            kind="webshop",
            tenant_id="other-tenant",
            resource_ref="shop#1",
        ),
    )
    svc, store = _claim_service(store=shared)
    with pytest.raises(PublishSlugConflict) as exc:
        svc.publish(_TENANT)
    assert exc.value.slug == "h-dcn-aanmelden"
    # The FOREIGN marker survives untouched (clobber backstop, decided from the body).
    marker = store.resolve("h-dcn-aanmelden")
    assert (marker.owner_plane, marker.kind, marker.tenant_id) == (
        "flask",
        "webshop",
        "other-tenant",
    )


def test_publish_rejects_a_slug_that_violates_the_sec4_prefix_rule_before_claiming():
    # SEC-4: a well-formed slug that does NOT start with the tenant's own public prefix is rejected
    # BEFORE the claim (no marker written) — this tenant cannot squat another tenant's namespace.
    svc, store = _claim_service(slug="acme-aanmelden", prefix="h-dcn")
    with pytest.raises(PublishSlugRejected):
        svc.publish(_TENANT)
    # Nothing was claimed (the SEC-4 check runs before the atomic claim).
    assert store.resolve("acme-aanmelden") is None


def test_publish_rejects_a_malformed_slug_before_the_prefix_check_and_claim():
    # Format/reserved runs FIRST: a malformed slug (uppercase / illegal chars) is rejected before
    # the prefix rule and before the claim — no marker written.
    svc, store = _claim_service(slug="Bad_Slug!", prefix="h-dcn")
    with pytest.raises(PublishSlugRejected):
        svc.publish(_TENANT)
    assert store.resolve("Bad_Slug!") is None


def test_publish_prefix_less_tenant_cannot_claim_a_new_slug():
    # A tenant with NO projected public prefix cannot assert ownership of a fresh prefixed
    # namespace → a NEW claim is refused (SEC-4), nothing claimed.
    svc, store = _claim_service(slug="h-dcn-aanmelden", prefix=None)
    with pytest.raises(PublishSlugRejected):
        svc.publish(_TENANT)
    assert store.resolve("h-dcn-aanmelden") is None


def test_publish_ordering_readiness_runs_before_the_claim():
    # An UNREADY tenant (no slug) refuses at the readiness gate BEFORE any render or claim — the
    # marker store is never touched.
    fake = _ConditionalFakeS3()
    store = S3SlugMarkerStore(client=fake, bucket=_CLAIM_BUCKET)
    svc, store = _claim_service(slug=None, store=store)
    with pytest.raises(PublishNotReady):
        svc.publish(_TENANT)
    assert not fake.objects  # nothing claimed — readiness gate short-circuits first


def test_publish_claim_runs_after_render_live_write_stays_dormant():
    # A successful claim still leaves the LIVE write dormant: the artifact is rendered (stashed on
    # `_rendered_html`), the slug is claimed, and the seam STILL raises PublishPipelineNotWired —
    # i.e. 8.1 claims + renders, task 9 lifts the dormant write.
    svc, store = _claim_service()
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    assert svc._rendered_html.startswith("<!DOCTYPE html>")  # render ran
    assert store.resolve("h-dcn-aanmelden") is not None  # claim ran
    # The dormant seam fired AFTER both — no live artifact object was written to the bucket (the
    # only object present is the control-plane `_slugs/` marker, never a served `{slug}/index.html`).
    served = [k for (_b, k) in store._client.objects if not k.startswith("_slugs/")]
    assert served == []


# ── Edge status mapping for the Task 8.1 refusals (handler → caller-safe envelopes) ───


def test_handler_slug_conflict_is_a_caller_safe_409(monkeypatch):
    # A foreign-owned slug (clobber backstop) surfaces as a 409 with the typed code and a GENERIC
    # message (no internals / no raw SlugTaken leak).
    spy = _SpyPublishService(raises=PublishSlugConflict("h-dcn-aanmelden"))
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: spy)
    resp = app.handler(_event())
    assert resp["statusCode"] == 409
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.application.publishSlugConflict"
    assert (
        "h-dcn-aanmelden" not in env["error"]
    )  # no slug/internals leaked in the message


def test_handler_slug_rejected_is_a_422_with_caller_safe_detail(monkeypatch):
    # A malformed / prefix-violating slug surfaces as a 422 carrying the validator's caller-safe
    # detail and the typed code.
    spy = _SpyPublishService(
        raises=PublishSlugRejected(
            "slug must start with this tenant's public prefix 'h-dcn'"
        )
    )
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: spy)
    resp = app.handler(_event())
    assert resp["statusCode"] == 422
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.application.publishSlugRejected"


def test_handler_real_service_end_to_end_claims_then_501(monkeypatch):
    # End-to-end through the REAL publish service WIRED with a real store (over a conditional fake):
    # a ready tenant claims its slug then reaches the dormant seam → 501. Pins the whole
    # edge→dispatch→service→claim→seam path for 8.1.
    svc, store = _claim_service()
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: svc)
    resp = app.handler(_event())
    assert resp["statusCode"] == 501
    assert _envelope(resp)["code"] == "errors.application.publishNotWired"
    assert (
        store.resolve("h-dcn-aanmelden").tenant_id == _TENANT
    )  # the claim really happened


# ════════════════════════════════════════════════════════════════════════════════════
# spec 14 Task 8.2 — COMPLETES the publish-claims-the-slug battery [R3.1, R3.2, R4.4, R4.5]
#
# Task 8.1 already proved the three headline behaviours against the REAL `S3SlugMarkerStore`
# over the conditional-honouring in-memory fake (NOT a mock):
#   * publish CLAIMS the slug with the correct owner body
#       → test_publish_claims_the_slug_for_the_owning_tenant_then_hits_dormant_seam
#   * same-owner re-publish is IDEMPOTENT (no conflict, owner unchanged)
#       → test_publish_same_owner_republish_is_idempotent_no_conflict
#   * publish WON'T CLOBBER a foreign-owned slug (PublishSlugConflict, foreign marker survives)
#       → test_publish_does_not_clobber_a_foreign_owned_slug
#
# Task 8.2 adds only the two genuinely-missing STRENGTHENING assertions that make the battery
# airtight (NOT duplicates — they pin properties 8.1 left implicit):
#   * idempotent re-publish leaves EXACTLY ONE marker object in the store (no duplicate/second
#     key), and a re-publish re-asserts the full owner body unchanged;
#   * the rejected-clobber foreign marker body is BYTE-UNCHANGED (incl. resource_ref), proving the
#     conflict path never partially overwrote the foreign owner's marker.
#
# Still REAL claim semantics (real store over the conditional fake), never a mock. The LIVE write
# remains DORMANT — 8.2 adds NO live-write test; the live S3 artifact put is task 9.
#
# Validates: Requirements R3.1, R3.2, R4.4, R4.5 (spec 14)
# ════════════════════════════════════════════════════════════════════════════════════


def test_publish_republish_leaves_exactly_one_marker_in_the_store():
    # Idempotency is not just "no conflict": two sequential same-owner publishes must leave the
    # store with EXACTLY ONE `_slugs/{slug}` marker object — never a duplicate / shadow key. Pins
    # the claim is a true upsert-of-one, not an append (R4.5).
    fake = _ConditionalFakeS3()
    store = S3SlugMarkerStore(client=fake, bucket=_CLAIM_BUCKET)
    svc, store = _claim_service(store=store)
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)  # first claim
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)  # idempotent re-claim
    slug_keys = [k for (_b, k) in fake.objects if k.startswith("_slugs/")]
    assert slug_keys == ["_slugs/h-dcn-aanmelden"]  # exactly one marker, no duplicate


def test_publish_republish_re_asserts_the_full_owner_body_unchanged():
    # A same-owner re-publish re-asserts the complete owner body — every field
    # (owner_plane / kind / tenant_id / resource_ref) is still the form-owner identity, unchanged
    # across the idempotent re-claim (never a foreign/partial body slipping in).
    svc, store = _claim_service()
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    marker = store.resolve("h-dcn-aanmelden")
    assert (
        marker.owner_plane,
        marker.kind,
        marker.tenant_id,
        marker.resource_ref,
    ) == (FORM_OWNER_PLANE, FORM_OWNER_KIND, _TENANT, FORM_RESOURCE_REF)


def test_publish_conflict_leaves_the_foreign_marker_body_byte_unchanged():
    # The clobber backstop (R4.4) must leave the foreign marker's FULL body byte-for-byte
    # unchanged — not just the owner-triple, but resource_ref too, and the raw stored bytes. Pins
    # that the rejected publish performed NO partial overwrite of the foreign owner's marker.
    fake = _ConditionalFakeS3()
    shared = S3SlugMarkerStore(client=fake, bucket=_CLAIM_BUCKET)
    foreign = SlugMarker(
        owner_plane="flask",
        kind="webshop",
        tenant_id="other-tenant",
        resource_ref="shop#1",
    )
    shared.claim("h-dcn-aanmelden", foreign)
    before_bytes = fake.objects[(_CLAIM_BUCKET, "_slugs/h-dcn-aanmelden")]["body"]

    svc, store = _claim_service(store=shared)
    with pytest.raises(PublishSlugConflict):
        svc.publish(_TENANT)

    # Raw stored bytes are identical — no partial write happened on the conflict path.
    after_bytes = fake.objects[(_CLAIM_BUCKET, "_slugs/h-dcn-aanmelden")]["body"]
    assert after_bytes == before_bytes
    # And the resolved body is the FULL foreign identity, resource_ref included.
    marker = store.resolve("h-dcn-aanmelden")
    assert (
        marker.owner_plane,
        marker.kind,
        marker.tenant_id,
        marker.resource_ref,
    ) == ("flask", "webshop", "other-tenant", "shop#1")


# ════════════════════════════════════════════════════════════════════════════════════
# spec 14 Task 9.1 — the publish route LIVE-WIRES the served artifact write + invalidation
# [R3.1, R5.1, R5.4, R5.5, R6.2, R6.3, R10.7, R10.8]
#
# GATED live wiring: the dormant seam (PublishPipelineNotWired after a successful claim) is
# LIFTED into the REAL live write. With a `PublicPageArtifactWriter` injected, a ready
# tenant's publish now:
#
#   * writes `{slug}/index.html` (the rendered artifact) + `{slug}/form.json` (the form
#     schema/config the published shell fetches) under the SERVED `{slug}/` prefix — DISTINCT
#     from the `_slugs/{slug}` control-plane marker;
#   * attempts a CloudFront invalidation for the slug path;
#   * returns the MembersApplicationPublishResult-shaped dict (success, slug,
#     published_version, published_at);
#   * and — CRITICALLY — SUCCEEDS EVEN WHEN the invalidation fails (best-effort / non-fatal;
#     the put_object is authoritative, the invalidation permission/ARN is deferred to Task 9.2).
#
# The claim/clobber/SEC-4 assertions from 8.1/8.2 are UNCHANGED (claim still runs BEFORE the
# write). Proven against injected fakes (a real `S3PublicPageArtifactStore` over an in-memory
# fake S3 + a fake CloudFront client that can be told to raise), NEVER real AWS.
#
# Validates: Requirements R3.1, R5.1, R5.4, R5.5, R6.2, R6.3, R10.7, R10.8 (spec 14)
# ════════════════════════════════════════════════════════════════════════════════════

import json as _json

from sam.members.repository.public_page_artifact_store import (
    FORM_JSON_ARTIFACT_NAME,
    INDEX_ARTIFACT_NAME,
    S3PublicPageArtifactStore,
)

_ARTIFACT_BUCKET = "myadmin-public-pages-nonprofit-506221081911"
_DIST_ID = "E1PUBLICPAGES"


class _ArtifactFakeS3:
    """In-memory S3 that records put_object calls under the SERVED `{slug}/` prefix (no AWS)."""

    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType=None, CacheControl=None):
        self.objects[(Bucket, Key)] = {
            "body": Body
            if isinstance(Body, (bytes, bytearray))
            else str(Body).encode("utf-8"),
            "content_type": ContentType,
        }
        return {}


class _FakeCloudFront:
    """In-memory CloudFront client. Optionally RAISES on create_invalidation (Task 9.2 gap)."""

    def __init__(self, *, raises=False):
        self.calls = []
        self._raises = raises

    def create_invalidation(self, *, DistributionId, InvalidationBatch):
        self.calls.append({"dist": DistributionId, "batch": InvalidationBatch})
        if self._raises:
            # Mimic the known-deferred permission-denied failure (Task 9.2 SEC-8 IAM).
            raise _FakeClientError(
                "AccessDenied", 403, "not authorized: CreateInvalidation"
            )
        return {"Invalidation": {"Id": "I123"}}


def _live_service(
    *,
    slug="h-dcn-aanmelden",
    certified=True,
    domain="h-dcn.nl",
    fields=1,
    prefix="h-dcn",
    marker_store=None,
    artifact_writer=None,
    cloudfront=None,
    published_version=None,
):
    """A publish service WIRED with a real marker store AND a real artifact writer (Task 9.1).

    Both stores run over in-memory fakes (conditional S3 for the marker claim; a served-prefix
    S3 + a fake CloudFront for the artifact write), so the FULL live path runs with no AWS. The
    default slug is well-formed and under the default prefix, so a ready tenant claims then writes.
    """
    readiness = StaticMailReadinessProvider({_TENANT: (certified, domain)})
    marker_store = (
        marker_store
        if marker_store is not None
        else S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_CLAIM_BUCKET)
    )
    if artifact_writer is None:
        artifact_writer = S3PublicPageArtifactStore(
            s3_client=_ArtifactFakeS3(),
            cloudfront_client=cloudfront
            if cloudfront is not None
            else _FakeCloudFront(),
            bucket=_ARTIFACT_BUCKET,
            distribution_id=_DIST_ID,
        )
    field_reader = FakeFieldConfigReader(fields)
    if published_version is not None:
        # Carry a stored published_version so the next-version bump can be asserted.
        base = field_reader.get_public_field_config
        field_reader.get_public_field_config = lambda tid: {  # type: ignore[method-assign]
            **base(tid),
            "published_version": published_version,
        }
    svc = ApplicationPublishService(
        slug_reader=FakeSlugReader(slug),
        readiness_provider=readiness,
        field_config_reader=field_reader,
        slug_marker_store=marker_store,
        prefix_reader=FakePrefixReader(prefix),
        artifact_writer=artifact_writer,
    )
    return svc, marker_store, artifact_writer


def test_publish_live_writes_both_served_artifacts_under_the_slug_prefix():
    # The lifted live write: a ready tenant's publish writes BOTH `{slug}/index.html` and
    # `{slug}/form.json` under the SERVED `{slug}/` prefix — distinct from the `_slugs/` marker.
    s3 = _ArtifactFakeS3()
    writer = S3PublicPageArtifactStore(
        s3_client=s3,
        cloudfront_client=_FakeCloudFront(),
        bucket=_ARTIFACT_BUCKET,
        distribution_id=_DIST_ID,
    )
    svc, marker_store, _ = _live_service(artifact_writer=writer)
    result = svc.publish(_TENANT)
    # Both served artifacts landed under the `{slug}/` prefix.
    assert (_ARTIFACT_BUCKET, f"h-dcn-aanmelden/{INDEX_ARTIFACT_NAME}") in s3.objects
    assert (
        _ARTIFACT_BUCKET,
        f"h-dcn-aanmelden/{FORM_JSON_ARTIFACT_NAME}",
    ) in s3.objects
    # index.html is the rendered page shell; form.json is valid JSON of the public field config.
    index_body = s3.objects[(_ARTIFACT_BUCKET, "h-dcn-aanmelden/index.html")]["body"]
    assert index_body.decode("utf-8").startswith("<!DOCTYPE html>")
    form_body = s3.objects[(_ARTIFACT_BUCKET, "h-dcn-aanmelden/form.json")]["body"]
    parsed = _json.loads(form_body.decode("utf-8"))
    assert parsed["tenant_id"] == _TENANT and isinstance(parsed["fields"], list)
    # The served artifacts are a DIFFERENT key space from the control-plane `_slugs/` marker.
    served_keys = {k for (_b, k) in s3.objects}
    assert not any(k.startswith("_slugs/") for k in served_keys)
    # The slug IS still claimed (the control-plane marker lives in the OTHER store).
    assert marker_store.resolve("h-dcn-aanmelden").tenant_id == _TENANT
    # And the publish returns the result-shaped dict the frontend caller expects.
    assert result["success"] is True
    assert result["slug"] == "h-dcn-aanmelden"
    assert result["published_version"] == 1  # first publish
    assert isinstance(result["published_at"], str) and result["published_at"]


def test_publish_live_write_attempts_the_cloudfront_invalidation_for_the_slug_path():
    # The write is followed by a CloudFront invalidation for the slug's paths (`/{slug}/*`, `/{slug}`).
    cf = _FakeCloudFront()
    svc, _, _ = _live_service(cloudfront=cf)
    svc.publish(_TENANT)
    assert len(cf.calls) == 1
    items = cf.calls[0]["batch"]["Paths"]["Items"]
    assert "/h-dcn-aanmelden/*" in items and "/h-dcn-aanmelden" in items
    assert cf.calls[0]["dist"] == _DIST_ID


def test_publish_SUCCEEDS_even_when_the_invalidation_client_raises():
    # CRITICAL (the known-deferred Task 9.2 gap): a CloudFront invalidation that RAISES
    # permission-denied must NOT fail the publish — the put_object(s) are authoritative, the
    # invalidation is best-effort. The publish returns the success result even though CF raised.
    s3 = _ArtifactFakeS3()
    cf = _FakeCloudFront(raises=True)
    writer = S3PublicPageArtifactStore(
        s3_client=s3,
        cloudfront_client=cf,
        bucket=_ARTIFACT_BUCKET,
        distribution_id=_DIST_ID,
    )
    svc, _, _ = _live_service(artifact_writer=writer)
    result = svc.publish(_TENANT)  # must NOT raise
    assert result["success"] is True
    # The artifacts were still written (authoritative publish happened before the failed invalidate).
    assert (_ARTIFACT_BUCKET, "h-dcn-aanmelden/index.html") in s3.objects
    assert (_ARTIFACT_BUCKET, "h-dcn-aanmelden/form.json") in s3.objects
    # The invalidation WAS attempted (and failed) — best-effort, swallowed.
    assert len(cf.calls) == 1


def test_publish_SUCCEEDS_when_no_distribution_is_configured():
    # A blank distribution id (invalidation not configured) is also non-fatal: the artifact write
    # is authoritative and the publish still returns success, with no invalidation attempted.
    s3 = _ArtifactFakeS3()
    cf = _FakeCloudFront()
    writer = S3PublicPageArtifactStore(
        s3_client=s3,
        cloudfront_client=cf,
        bucket=_ARTIFACT_BUCKET,
        distribution_id="",  # not configured
    )
    svc, _, _ = _live_service(artifact_writer=writer)
    result = svc.publish(_TENANT)
    assert result["success"] is True
    assert (_ARTIFACT_BUCKET, "h-dcn-aanmelden/index.html") in s3.objects
    assert cf.calls == []  # never attempted — no distribution configured


def test_publish_live_write_runs_AFTER_the_claim_not_before():
    # Ordering preserved from 8.1: the slug CLAIM runs BEFORE the live write. A FOREIGN-owned slug
    # must still be refused (PublishSlugConflict) and NO served artifact is written.
    fake_s3 = _ArtifactFakeS3()
    shared = S3SlugMarkerStore(client=_ConditionalFakeS3(), bucket=_CLAIM_BUCKET)
    shared.claim(
        "h-dcn-aanmelden",
        SlugMarker(
            owner_plane="flask", kind="webshop", tenant_id="other", resource_ref="x"
        ),
    )
    writer = S3PublicPageArtifactStore(
        s3_client=fake_s3,
        cloudfront_client=_FakeCloudFront(),
        bucket=_ARTIFACT_BUCKET,
        distribution_id=_DIST_ID,
    )
    svc, _, _ = _live_service(marker_store=shared, artifact_writer=writer)
    with pytest.raises(PublishSlugConflict):
        svc.publish(_TENANT)
    assert (
        fake_s3.objects == {}
    )  # no served artifact written — claim refused before the write


def test_publish_live_write_not_reached_when_unready():
    # Readiness still runs FIRST: an unready tenant writes NOTHING (no claim, no served artifact).
    fake_s3 = _ArtifactFakeS3()
    writer = S3PublicPageArtifactStore(
        s3_client=fake_s3,
        cloudfront_client=_FakeCloudFront(),
        bucket=_ARTIFACT_BUCKET,
        distribution_id=_DIST_ID,
    )
    svc, _, _ = _live_service(slug=None, artifact_writer=writer)
    with pytest.raises(PublishNotReady):
        svc.publish(_TENANT)
    assert fake_s3.objects == {}


def test_publish_live_write_advances_published_version_on_republish():
    # published_version advances monotonically: a form with a stored version N republishes to N+1.
    svc, _, _ = _live_service(published_version=4)
    result = svc.publish(_TENANT)
    assert result["published_version"] == 5


def test_publish_without_artifact_writer_stays_dormant():
    # Backward-compat: with NO writer injected (pre-9.1 scaffold / dry-run), the live write stays
    # dormant and the seam still raises PublishPipelineNotWired AFTER a successful claim.
    svc, store = _claim_service()  # no artifact_writer
    with pytest.raises(PublishPipelineNotWired):
        svc.publish(_TENANT)
    assert store.resolve("h-dcn-aanmelden") is not None  # claim still ran


def test_handler_real_live_service_end_to_end_returns_200_result(monkeypatch):
    # End-to-end through the REAL service WIRED with real stores (over fakes): a ready tenant
    # claims, writes both served artifacts, and the edge maps the result dict to a 200.
    svc, marker_store, writer = _live_service()
    monkeypatch.setattr(dispatch_mod, "get_application_publish_service", lambda: svc)
    resp = app.handler(_event())
    assert resp["statusCode"] == 200
    env = _envelope(resp)
    assert env["success"] is True
    # The publish result dict is carried under the standard `data` envelope key.
    data = env["data"]
    assert data["slug"] == "h-dcn-aanmelden"
    assert data["published_version"] == 1
    assert marker_store.resolve("h-dcn-aanmelden").tenant_id == _TENANT
    assert (_ARTIFACT_BUCKET, "h-dcn-aanmelden/index.html") in writer._s3.objects
