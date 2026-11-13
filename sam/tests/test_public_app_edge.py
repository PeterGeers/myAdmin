"""
Member-application spec task 1.1 — tests for the **public (unauthenticated) intake** edge.

These pin the observable contract of the new ``handler/public_app.py`` entrypoint (D27,
requirements R1/R1a/R2/R10): the SAM members plane's first token-less HTTP edge. Task 1.1 is
the entrypoint + its abuse guards + the delegation SEAM — the slug resolver (1.2), route wiring
(1.3), and the ``create_application`` / ``get_public_field_config`` domain (Phase 2 / Phase 4)
are later tasks, so the seam resolves to an honest 501 here. What this file pins:

- **No auth (D27, R1.1):** a public route is reachable with NO token and NO authorizer context,
  and the entrypoint NEVER calls ``_authenticate_and_authorize`` (the ONE hard difference from
  ``app.handler``) — asserted both behaviourally (no token → not a 401/403) and structurally
  (the function is not referenced in the module source).
- **Abuse guards (R10.2 / R1a.4):** a tripped honeypot, an oversized body, and a malformed body
  each return a NEUTRAL 400 ``errors.api.badRequest`` BEFORE any delegation — the caller is never
  told which guard tripped.
- **Non-probeable 404 (R1a.4):** an unknown / forged path returns 404 ``errors.api.notFound``,
  deliberately indistinguishable from "no such endpoint".
- **Recognised route, pending behaviour (task 1.1 state):** a well-formed GET field-config /
  POST applications reaches the (empty) seam → honest 501 ``errors.api.notImplemented``.
- **R1a envelope + CORS (R10.3):** every response (success AND error) carries the shared
  ``{success, …}`` JSON envelope with its ``Access-Control-Allow-Origin`` restricted to the
  configured form origin(s) — an allow-listed Origin is echoed, a foreign / unset Origin is
  fail-closed (no ``*``).

Validates: Requirements R1.1, R1a.1, R1a.4, R2 (carrier-not-trusted edge), R10.2, R10.3
"""

from __future__ import annotations

import json

import pytest

from sam.members.handler import public_app, public_guards


# ── Fake slug reader (task 1.4 — the `_slugs/{slug}` marker store behind the Protocol) ──
#
# Task 1.4 swapped the public edge's reverse-lookup reader from the `PUBLIC_TENANT_SLUG_MAP`
# env projection (`EnvTenantSlugReader`) to the `_slugs/{slug}` bucket marker
# (`S3SlugMarkerStore`, OQ4). The resolver (`TenantDirectory`) and the edge handler are
# UNCHANGED — they still depend only on the `TenantSlugReader` Protocol (`resolve_slug`). So
# the edge tests drive the SAME observable behaviour (non-probeable 404 / recognised-route 501)
# through a fake reader injected the way the suite already injects `MembersProjectionReader`:
# by monkeypatching the name `public_app.S3SlugMarkerStore` to a factory returning this fake.
# No real AWS / S3 is touched; the marker store's own S3 mechanics are covered by
# `test_slug_marker_store.py`.


from sam.members.repository.slug_marker_store import SlugMarker


class _FakeSlugReader:
    """A fake `S3SlugMarkerStore` standing in for the real store at the edge (no env, no S3).

    `_tenant_directory()` constructs `S3SlugMarkerStore()` for the POST (`TenantDirectory`) path,
    and task 3.1's `_resolve_sam_form_tenant()` constructs it for the GET (`resolve` marker-body)
    path. Patching the module name to a factory returning this fake lets a test seed BOTH:

    - `resolve_slug(slug) -> tenant_id | None` — the legacy `TenantSlugReader` the POST path's
      `TenantDirectory` consumes (keyed on the ALREADY-normalized trim+case-fold slug);
    - `resolve(slug) -> SlugMarker | None` — the structured D-SLUG marker BODY the task-3.1 GET
      read routes from (`owner_plane`/`kind`/`tenant_id`), so a cross-plane / cross-kind / missing
      marker returns None (the one non-probeable not-found).

    Both are fail-safe (a missing slug → None), so verify-before-trust / non-probeable 404 holds.
    """

    def __init__(
        self,
        by_slug: dict[str, str] | None = None,
        *,
        markers: dict[str, SlugMarker] | None = None,
    ):
        self._by_slug = dict(by_slug or {})
        self._markers = dict(markers or {})

    def resolve_slug(self, slug: str) -> str | None:
        if not isinstance(slug, str) or not slug:
            return None
        return self._by_slug.get(slug)

    def resolve(self, slug: str) -> SlugMarker | None:
        # The resolver passes the RAW slug segment to `resolve` (the store normalizes internally);
        # the fake keys on the lower-cased slug so a seeded `h-dcn` marker resolves `h-dcn`.
        if not isinstance(slug, str) or not slug:
            return None
        return self._markers.get(slug.strip().lower())


def _sam_form_marker(tenant_id: str) -> SlugMarker:
    """A published SAM application-form marker body for `tenant_id` (the task-3.1 happy path)."""
    return SlugMarker(
        owner_plane="sam",
        kind="application_form",
        tenant_id=tenant_id,
        resource_ref="config#fields",
    )


# ── SEC-2 (task 4.2) — a FAKE authoritative validator mimicking the engine's raise-before-persist ──
#
# The REAL per-field validation (email-is-email, enum within the published application subset,
# required present, GDPR consent) lives in the membership engine
# (`MembershipService.create_application` → raises `MemberValidationError` before `save_member`).
# These edge tests do NOT re-prove the engine's rule battery (that is task 4.5 + the engine's own
# tests, steering 39: don't re-prove the engine's internals at the edge). They prove the EDGE's
# 422-mapping + no-write contract. So the fake service needs ONE deterministic way to look invalid
# so the `MemberValidationError` path fires — an obviously-bad sentinel email is enough, plus a
# `__INVALID__` escape hatch for a test that wants a multi-field failure without caring which rule.
#
# The returned map is `{dotted_field_key: FieldError}` — EXACTLY the real
# `MemberValidationError(errors)` shape (`sam/members/domain/_membership_errors.py`), so the edge's
# `_field_errors_array(exc.errors)` flattens it into the RFC 9457 per-field `errors` array the SPA
# localizes, with no bespoke shim.

#: A sentinel body value that always looks invalid to the fake validator (a submit a test uses to
#: deterministically drive the authoritative 422 path without depending on a real rule's wording).
_INVALID_SENTINEL = "__INVALID__"


def _body_validation_errors(body: dict) -> dict:
    """Return a `{field_key: FieldError}` map for an invalid submit, else `{}` (SEC-2).

    Mimics the engine's authoritative pass ENOUGH to exercise the edge's 422 mapping:
      * an `email` (under `fields`, where the SPA posts, or top-level) that is not an email →
        `errors.validation.invalidFormat` on `personal.email`;
      * the `_INVALID_SENTINEL` anywhere in `fields` → a generic field error, for a test that
        just wants a deliberate validation failure.
    Anything else is valid (`{}`), so the existing happy-path / SEC-3 tests (which post a real
    `a@b.nl`) still fall through to the persist-and-return path unchanged.
    """
    from sam.members.domain.error_codes import FieldError

    fields = body.get("fields") if isinstance(body, dict) else None
    fields = fields if isinstance(fields, dict) else {}
    errors: dict[str, FieldError] = {}

    email = fields.get("email", body.get("email") if isinstance(body, dict) else None)
    if isinstance(email, str) and email and "@" not in email:
        errors["personal.email"] = FieldError(
            code="errors.validation.invalidFormat",
            detail="email must be a valid email address",
        )
    if _INVALID_SENTINEL in fields.values() or (
        isinstance(body, dict) and body.get(_INVALID_SENTINEL) is not None
    ):
        errors.setdefault(
            "personal.last_name",
            FieldError(
                code="errors.validation.required", detail="last name is required"
            ),
        )
    return errors


class _FakeApplicationService:
    """A stand-in for `ApplicationService` the task-3.1 GET read calls (no DynamoDB engine).

    `public_app._application_service()` constructs `ApplicationService(...)`; monkeypatching the
    module name `public_app.ApplicationService` to a factory returning this fake exercises the
    REAL edge wiring (marker resolve → service call → whitelist body → CORS) without the
    membership engine / projection reader. `get_public_field_config` returns a WHITELISTED schema
    for a send-ready tenant, or raises `ApplicationNotAvailable` for a not-ready one (the
    publication gate) so the edge's SEC-5 non-probeable-404 mapping can be asserted.
    """

    def __init__(self, *, ready_tenants: dict[str, dict] | None = None):
        # tenant_id -> the (already-whitelisted) schema dict the real service would return.
        self._ready = dict(ready_tenants or {})
        # Task 4.1 — capture the LAST `create_application` call so a test can prove SEC-3: the
        # write was scoped to the MARKER-RESOLVED tenant, never a body value. `None` until called.
        self.create_called_with: dict | None = None
        # Task 4.2 (SEC-2) — did `create_application` actually PERSIST a record? The real engine
        # raises `MemberValidationError` BEFORE `save_member`, so a validation failure writes
        # NOTHING. This flag is set True ONLY on the path that reaches the (mimicked) persist, so a
        # test can prove the edge's 422 path performed NO write (`persisted is False`).
        self.persisted = False

    def get_public_field_config(self, tenant_id: str) -> dict:
        from sam.members.domain.application_readiness import ApplicationNotAvailable

        if tenant_id not in self._ready:
            # Not send-ready / unpublished → the neutral readiness refusal the edge maps to a
            # non-probeable 404 (SEC-5). Mirrors the real service's gate.
            raise ApplicationNotAvailable()
        return self._ready[tenant_id]

    def create_application(
        self,
        tenant_id: str,
        body: dict,
        session_key: str,
        locale: str | None = None,
        consent: dict | None = None,
    ) -> dict:
        """Stand in for `ApplicationService.create_application` the task-4.1 POST write calls.

        CAPTURES every argument on the instance (`create_called_with`) — above all the
        `tenant_id`, so a test can assert the write was SCOPED to the marker-resolved tenant and
        NOT to any `tenant_id` forged into the request body (SEC-3, steering 39). A tenant that is
        not send-ready (absent from `ready_tenants`) raises `ApplicationNotAvailable`, mirroring
        the GET fake's unready signal and the real service's submit-side readiness re-check (R9.4)
        — the edge maps that to the SAME non-probeable 404 (SEC-5), with NO record returned.

        On a ready tenant it returns a representative created `Member` — the real
        `create_application` returns `Member = Mapping[str, Any]`
        (`sam/members/repository/members_repository.py`), a plain JSON-serializable record with the
        server-stamped `tenant_id` / `member_id` and a forced `membership.status == "application"`
        (`sam/members/domain/_membership_writes_application.py`). The public edge wraps it in
        `_PublicResult(record, tenant_id=...)` and the shared `_http._response` serializes it into
        the `{success: True, data: <record>}` envelope, so this dict round-trips cleanly.

        Task 4.2 (SEC-2) — the authoritative server-side validation contract. The REAL membership
        engine (`MembershipService.create_application`) validates the submission in the domain and
        raises `MemberValidationError` BEFORE `save_member`, so a validation failure persists
        NOTHING. This fake mimics that raise-before-persist contract: it detects an invalid body
        (see `_body_validation_errors`), and if any field fails it raises a REAL
        `MemberValidationError` carrying a `{field_key: FieldError}` map — exactly the shape the
        edge reads via `exc.errors` / `_field_errors_array` — WITHOUT ever setting `persisted`. The
        edge maps that to a 422 `errors.validation.failed` with the per-field `errors` array. A
        VALID body falls through to the (mimicked) persist and returns the created record. The
        per-field RULE battery (bad email vs out-of-subset enum vs missing required …) belongs to
        the authoritative engine's own tests / task 4.5; this fake only needs to exercise the
        edge's 422-mapping + no-write contract, so a single obviously-bad sentinel suffices.
        """
        from sam.members.domain.application_readiness import ApplicationNotAvailable

        self.create_called_with = {
            "tenant_id": tenant_id,
            "body": body,
            "session_key": session_key,
            "locale": locale,
            "consent": consent,
        }
        if tenant_id not in self._ready:
            # Submit-side readiness re-check (R9.4): a not-send-ready tenant's submit is refused
            # with NO record — the edge maps it to the non-probeable 404 (SEC-5).
            raise ApplicationNotAvailable()
        # SEC-2 — authoritative validation runs BEFORE the write. If the body is invalid, raise
        # the REAL `MemberValidationError` (raise-before-persist) so NOTHING is written and the
        # edge maps the deliberate refusal to a 422 with the per-field `errors` array.
        errors = _body_validation_errors(body)
        if errors:
            from sam.members.domain._membership_errors import MemberValidationError

            raise MemberValidationError(errors)
        # The service stamps the AUTHORITATIVE tenant (never the body's) — mirror that so the
        # returned record carries the marker-resolved tenant, not any forged body value.
        self.persisted = True
        return {
            "tenant_id": tenant_id,
            "member_id": "member-0001",
            "membership": {"status": "application"},
            "personal": {"email": "a@b.nl"},
        }


# ── Helpers ───────────────────────────────────────────────────────────────────────────


def _proxy_event(
    method: str,
    path: str,
    *,
    body=None,
    headers: dict | None = None,
    is_base64: bool = False,
) -> dict:
    """An API Gateway proxy event for the public edge — NO authorizer context (token-less)."""
    if body is not None and not isinstance(body, str):
        body = json.dumps(body)
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "queryStringParameters": None,
        "body": body,
        "isBase64Encoded": is_base64,
    }


_FIELD_CONFIG = "/public/members/h-dcn/field-config"
_APPLICATIONS = "/public/members/h-dcn/applications"


#: The allow-list the autouse fixture seeds into the (faked) marker-store reader. `h-dcn` is the
#: slug used by _FIELD_CONFIG / _APPLICATIONS; `form-slug` exercises per-tenant isolation. Both map
#: to a canonical tenant_id distinct from the slug (the resolved tenant_id, not the slug, is what
#: CORS / the service key on — verify-before-trust).
_SEEDED_SLUGS = {"h-dcn": "h-dcn-tenant", "form-slug": "form-tenant"}

#: The structured D-SLUG markers the task-3.1 GET read routes from (resolve-by-BODY, Property 2).
#: Both seeded slugs are published SAM application-form pages owned by their canonical tenant.
_SEEDED_MARKERS = {
    "h-dcn": _sam_form_marker("h-dcn-tenant"),
    "form-slug": _sam_form_marker("form-tenant"),
}


#: The minimal WHITELISTED schema the faked ApplicationService returns for a send-ready tenant —
#: the shape `get_public_field_config` produces (fields + functional_groups + locales + notice),
#: never a raw record shape (steering 39). Both seeded tenants are send-ready (published).
def _whitelisted_schema(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "fields": [
            {
                "key": "email",
                "type": "email",
                "label": {"nl": "E-mail", "en": "Email"},
                "functional_group": "contact",
                "order": 10,
                "required": True,
            }
        ],
        "functional_groups": [
            {"key": "contact", "label": {"nl": "Contact", "en": "Contact"}, "order": 10}
        ],
        "locales": ["nl", "en"],
        "notice": {"version": 1},
    }


_READY_TENANTS = {
    "h-dcn-tenant": _whitelisted_schema("h-dcn-tenant"),
    "form-tenant": _whitelisted_schema("form-tenant"),
}


@pytest.fixture(autouse=True)
def _allow_form_origin(monkeypatch):
    """Configure the public-form CORS allow-list AND the slug→tenant reader (R10.3, R7/R2).

    The edge is fail-closed on CORS: with no ``PUBLIC_FORM_ALLOWED_ORIGINS`` it sets no
    ``Access-Control-Allow-Origin``. Most assertions here send a matching ``Origin``, so install
    a known allow-list; the fail-closed case sets its own env explicitly.

    Task 1.4 swapped the slug resolver's backing reader to the ``_slugs/{slug}`` bucket marker
    (``S3SlugMarkerStore``, OQ4) behind the UNCHANGED ``TenantSlugReader`` Protocol. The edge
    still resolves ``{slug}`` → ``tenant_id`` against that reader BEFORE reaching the pending
    service seam. Inject a fake reader (no env, no S3) seeded with the ``h-dcn`` slug used
    throughout so a recognised, allow-listed route reaches the pending-service 501; the
    unknown-slug cases rely on the seeded map NOT containing their slug to assert the
    non-probeable 404, and the empty-reader case installs its own factory.
    """
    monkeypatch.setenv(
        public_app.ALLOWED_ORIGINS_ENV,
        "https://aanmelden.jabaki.nl,https://form.example",
    )
    # Swap the backing reader `_tenant_directory()` constructs to a seeded fake — the task-1.4
    # localized swap behind the Protocol. The resolver/edge code is unchanged; only the backing
    # store differs from the real `S3SlugMarkerStore()` (whose S3 mechanics are tested elsewhere).
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(_SEEDED_SLUGS, markers=_SEEDED_MARKERS),
    )
    # Task 3.1: the GET read path builds its service via `public_app._application_service()`.
    # Patch that composition root to return a fake over the seeded send-ready tenants so the GET
    # read returns the whitelisted schema (200) WITHOUT the membership engine / projection reader;
    # a tenant absent from `_READY_TENANTS` raises the readiness refusal (→ non-probeable 404).
    monkeypatch.setattr(
        public_app,
        "_application_service",
        lambda: _FakeApplicationService(ready_tenants=_READY_TENANTS),
    )


def _body(resp: dict) -> dict:
    return json.loads(resp["body"])


# ── No auth (D27, R1.1) ────────────────────────────────────────────────────────────────


def test_public_route_is_reachable_with_no_token():
    # A well-formed public GET with NO Authorization header and NO authorizer context is NOT
    # a 401/403 — the public edge does not authenticate (D27). Task 3.1 LANDS the GET read, so a
    # published, send-ready slug now returns the whitelisted schema (200), never an auth rejection.
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 200
    assert resp["statusCode"] not in (401, 403)


def test_public_post_is_reachable_with_no_token():
    # A well-formed public POST with NO Authorization header and NO authorizer context is NOT a
    # 401/403 — the public edge does not authenticate (D27). Task 4.1 LANDS the submit write, so a
    # published, send-ready slug now returns the R1a success envelope (200), never an auth rejection.
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 200
    assert resp["statusCode"] not in (401, 403)
    assert _body(resp)["success"] is True


def test_entrypoint_never_calls_authenticate_and_authorize():
    # The ONE hard D27 difference from app.handler: the public entrypoint must never run the
    # verified-auth edge. Structural guard over the AST (not raw source — the docstring may
    # name the function in prose): no identifier/attribute `_authenticate_and_authorize` is
    # referenced anywhere in the module's CODE, and the auth toolkit is not imported.
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(public_app))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "_authenticate_and_authorize" not in (names | attrs)
    # Belt-and-suspenders: the verified-auth toolkit is not even imported here.
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "get_verified_claims" not in imported
    assert "has_capability" not in imported


# ── Abuse guards (R10.2 / R1a.4) — neutral 400 before any delegation ──────────────────


def test_honeypot_populated_returns_neutral_400():
    event = _proxy_event(
        "POST",
        _APPLICATIONS,
        body={"fields": {"email": "a@b.nl", public_app.HONEYPOT_FIELD: "i-am-a-bot"}},
    )
    resp = public_app.handler(event)
    assert resp["statusCode"] == 400
    assert _body(resp)["code"] == "errors.api.badRequest"


def test_honeypot_at_top_level_also_trips():
    event = _proxy_event(
        "POST", _APPLICATIONS, body={public_app.HONEYPOT_FIELD: "x", "fields": {}}
    )
    assert public_app.handler(event)["statusCode"] == 400


def test_blank_honeypot_is_not_a_trip():
    # A real browser leaves the hidden field empty — a blank honeypot is the accepted case and
    # must NOT 400 (task 4.1: it falls through to the landed submit write → 200, not a rejection).
    event = _proxy_event(
        "POST", _APPLICATIONS, body={"fields": {public_app.HONEYPOT_FIELD: "   "}}
    )
    assert public_app.handler(event)["statusCode"] == 200


def test_oversized_payload_returns_neutral_400(monkeypatch):
    monkeypatch.setenv("PUBLIC_MAX_PAYLOAD_BYTES", "64")
    big = "x" * 200
    event = _proxy_event("POST", _APPLICATIONS, body={"fields": {"note": big}})
    resp = public_app.handler(event)
    assert resp["statusCode"] == 400
    assert _body(resp)["code"] == "errors.api.badRequest"


def test_malformed_body_on_post_returns_neutral_400():
    # A body that is not a JSON object (a raw string that failed to parse) is malformed for the
    # public POST, which always expects an object → neutral 400.
    event = _proxy_event("POST", _APPLICATIONS, body="not-json-at-all")
    resp = public_app.handler(event)
    assert resp["statusCode"] == 400
    assert _body(resp)["code"] == "errors.api.badRequest"


def test_abuse_guard_message_does_not_reveal_which_control_tripped():
    # The caller-facing body for a honeypot trip and an oversized body must be identical
    # (R1a.4) — the trap is not discoverable from the response.
    honeypot = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={public_app.HONEYPOT_FIELD: "bot"})
    )
    malformed = public_app.handler(_proxy_event("POST", _APPLICATIONS, body="x"))
    assert honeypot["statusCode"] == malformed["statusCode"] == 400
    assert _body(honeypot) == _body(malformed)


# ── Non-probeable 404 (R1a.4) ──────────────────────────────────────────────────────────


def test_unknown_path_returns_non_probeable_404():
    resp = public_app.handler(_proxy_event("GET", "/public/members/h-dcn/secrets"))
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_non_public_prefix_returns_404():
    # A path outside the /public/members/ namespace is not recognised → 404 (never reaches
    # the seam, never a 501 that would advertise the route shape).
    resp = public_app.handler(_proxy_event("POST", "/members", body={"fields": {}}))
    assert resp["statusCode"] == 404


def test_wrong_method_on_public_path_returns_404():
    # POST to field-config / GET to applications are not recognised routes → 404.
    assert (
        public_app.handler(_proxy_event("POST", _FIELD_CONFIG, body={}))["statusCode"]
        == 404
    )
    assert public_app.handler(_proxy_event("GET", _APPLICATIONS))["statusCode"] == 404


# ── Recognised route, pending behaviour (task 1.1 seam) ───────────────────────────────


def test_post_submit_route_lands_the_write_and_returns_the_success_envelope():
    # Task 4.1 LANDS the submit write (`create_application`): a recognised, resolved POST to a
    # published SAM application-form slug WRITES the applicant record and returns the R1a success
    # envelope (200) — no longer the pending-service 501. The served `data` is the created record
    # the service returned (server-stamped tenant + `member_id`, forced status=application).
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 200
    body = _body(resp)
    assert body["success"] is True
    # The created record carries the MARKER-RESOLVED tenant (not a slug, not a body value).
    assert body["data"]["tenant_id"] == "h-dcn-tenant"
    assert body["data"]["membership"]["status"] == "application"


# ── Task 4.2 — SEC-2 server-side input validation: the EDGE 422-mapping + no-write contract ──
#
# Task 4.1 landed the happy-path submit write (above). Task 4.2 adds SEC-2: the authoritative
# per-field validation runs in the membership engine (`MembershipService.create_application`) and
# raises `MemberValidationError` BEFORE `save_member`, so a validation failure persists NOTHING.
# The public edge (`public_app.handler`) catches that deliberate, caller-safe refusal and maps it
# to a 422 `errors.validation.failed` carrying the RFC 9457 per-field `errors` array — exactly as
# the authenticated edge does — never swallowing it into the generic 500.
#
# These pin the EDGE surface of SEC-2 (the half this task owns):
#   * a submit that fails validation → 422 `errors.validation.failed` + a per-field `errors` array;
#   * NO record is written on a validation failure (the fake's `persisted` stays False; the edge
#     never returns a 200 success envelope);
#   * the oversized-payload cap still returns the neutral 400 — already covered by
#     `test_oversized_payload_returns_neutral_400` (SEC-2's size-cap half, via `_guard_abuse`);
#   * a VALID submit still returns the 200 success envelope (the 4.1 happy path is not regressed).
# The per-field RULE battery at the AUTHORITATIVE layer (bad email vs out-of-subset enum vs
# missing required vs unexpected field) is task 4.5 + the engine's own tests (steering 39: don't
# re-prove the engine's internals at the edge).


def test_submit_failing_validation_returns_422_with_per_field_errors_array(monkeypatch):
    # SEC-2 (R10.9): a resolved, published submit whose body fails the authoritative server-side
    # validation makes the engine raise `MemberValidationError` BEFORE the write. The edge maps it
    # to a 422 `errors.validation.failed` carrying the RFC 9457 per-field `errors` array the SPA
    # localizes — never the generic 500 and never a 200. A single captured fake lets us ALSO prove
    # no write happened (next test); here we pin the 422 + the per-field array shape.
    fake = _FakeApplicationService(ready_tenants=_READY_TENANTS)
    monkeypatch.setattr(public_app, "_application_service", lambda: fake)

    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "not-an-email"}})
    )
    assert resp["statusCode"] == 422
    body = _body(resp)
    assert body["success"] is False
    assert body["code"] == "errors.validation.failed"
    # RFC 9457 per-field array: a list of `{field, code, detail}` entries the SPA localizes.
    errors = body["errors"]
    assert isinstance(errors, list) and len(errors) >= 1
    entry = errors[0]
    assert entry["field"] == "email"
    assert entry["code"] == "errors.validation.invalidFormat"
    assert isinstance(entry["detail"], str) and entry["detail"]


def test_submit_failing_validation_writes_no_record(monkeypatch):
    # SEC-2 raise-BEFORE-persist (R10.9): on a validation failure the engine raises before
    # `save_member`, so NO applicant record lands. The fake mirrors that — `persisted` stays False
    # because the raise happens before the (mimicked) persist. The edge must NOT return a 200
    # success envelope on this path. (`create_called_with` IS set — the call reached the service —
    # but nothing was written.)
    fake = _FakeApplicationService(ready_tenants=_READY_TENANTS)
    monkeypatch.setattr(public_app, "_application_service", lambda: fake)

    resp = public_app.handler(
        _proxy_event(
            "POST",
            _APPLICATIONS,
            body={"fields": {"email": "nope", _INVALID_SENTINEL: _INVALID_SENTINEL}},
        )
    )
    assert resp["statusCode"] == 422
    # The service was reached but it raised before persisting — nothing was written.
    assert fake.create_called_with is not None
    assert fake.persisted is False
    # The edge did NOT emit a 200 success envelope on the validation-failure path.
    assert _body(resp)["success"] is False


def test_valid_submit_still_returns_the_200_success_envelope(monkeypatch):
    # Regression (task 4.1 happy path survives SEC-2): a VALID submit still passes validation,
    # persists, and returns the 200 success envelope — the validation layer rejects ONLY invalid
    # bodies, it does not break the valid path.
    fake = _FakeApplicationService(ready_tenants=_READY_TENANTS)
    monkeypatch.setattr(public_app, "_application_service", lambda: fake)

    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 200
    assert _body(resp)["success"] is True
    assert fake.persisted is True


def test_get_read_route_returns_whitelisted_schema_200():
    # Task 3.1 LANDS the GET read: a published SAM application-form slug returns the whitelisted
    # schema (200) via the reused `get_public_field_config` — no longer a pending 501.
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 200
    assert _body(resp)["success"] is True


def test_trailing_slash_is_tolerated_on_recognition():
    # GET read tolerates a trailing slash on recognition → still lands the 200 schema.
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG + "/"))
    assert resp["statusCode"] == 200


# ── Slug resolution wired into the delegation seam (task 1.3 — D19/R2/R1a.4) ──────────


def test_allow_listed_post_slug_writes_scoped_to_the_marker_resolved_tenant(
    monkeypatch,
):
    # Task 4.1 / SEC-3 (cross-tenant write safety, steering 39): a recognised POST whose slug IS on
    # the allow-list resolves its tenant from the `_slugs/{slug}` MARKER BODY and calls
    # `create_application` SCOPED to THAT marker-resolved tenant — NEVER a `tenant_id` the client
    # forged into the request body. Patch `_application_service` to a SINGLE captured fake (the
    # autouse fixture builds a fresh one per call, so a shared instance is needed to read back the
    # captured args), POST a body carrying a FORGED `tenant_id`, and assert the write was scoped to
    # `h-dcn-tenant` (the marker tenant for the `h-dcn` slug), ignoring the body value.
    fake = _FakeApplicationService(ready_tenants=_READY_TENANTS)
    monkeypatch.setattr(public_app, "_application_service", lambda: fake)

    resp = public_app.handler(
        _proxy_event(
            "POST",
            _APPLICATIONS,
            body={"tenant_id": "attacker-tenant", "fields": {"email": "a@b.nl"}},
        )
    )
    assert resp["statusCode"] == 200
    assert _body(resp)["success"] is True
    # The write happened, and it was scoped to the MARKER-RESOLVED tenant — the forged body value
    # was ignored (the service strips it; the edge never passes a body tenant).
    assert fake.create_called_with is not None
    assert fake.create_called_with["tenant_id"] == "h-dcn-tenant"
    assert fake.create_called_with["tenant_id"] != "attacker-tenant"


def test_foreign_slug_post_never_calls_create_application(monkeypatch):
    # SEC-3 / SEC-5: a POST whose slug marker names a DIFFERENT plane (a Flask-owned landing page)
    # resolved at the SAM edge is a clean non-match — decided from the marker BODY, never the slug
    # string. It must return the non-probeable 404 AND perform NO write: `create_application` is
    # NEVER called, so a foreign/cross-plane slug can never land a record in an arbitrary partition.
    flask_marker = SlugMarker(
        owner_plane="flask", kind="landing", tenant_id="h-dcn-tenant", resource_ref="x"
    )
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(markers={"h-dcn": flask_marker}),
    )
    fake = _FakeApplicationService(ready_tenants=_READY_TENANTS)
    monkeypatch.setattr(public_app, "_application_service", lambda: fake)

    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"
    # No write performed — the non-match was decided before any service call.
    assert fake.create_called_with is None


# ── Task 4.5 — submit-path battery gap-fills at the EDGE (SEC-3 cross-kind, missing-IAM 500) ──
#
# The bulk of task 4.5 lands against the REAL engine in `test_create_application.py`
# (`TestSubmitBatteryRealEngine` — SEC-3 routing, SEC-2 bad-type/unexpected-field, SEC-10 admin
# re-display). These two close the EDGE-only gaps the real-engine file cannot assert:
#   * the POST path rejects a cross-KIND marker (a SAM-owned webshop page, not an application
#     form) the SAME non-probeable 404 way it rejects a cross-PLANE marker (foreign-slug test
#     above) — resolve-by-body-not-name on the submit path, with NO write (Property 2/3, SEC-3);
#   * a write that FAILS the way a missing-IAM `PutItem` would (the repo/service raises an
#     AccessDenied-like error) is SURFACED as a bodied 500 `errors.api.serverError` — never an
#     empty 502, never a leak of the underlying error, never a hang or a silent success (R10.10 /
#     the handler's last-except contract).


def test_cross_kind_marker_post_never_calls_create_application(monkeypatch):
    # SEC-3 / Property 2 (submit path): a POST whose slug marker is SAM-owned but a DIFFERENT kind
    # (a webshop page, not an application form) is a clean non-match decided from the marker BODY
    # — the submit never writes an applicant record against a non-form page. Same non-probeable
    # 404 as the cross-plane case, and `create_application` is NEVER called. (The cross-kind GET
    # case is covered by `test_get_cross_kind_marker_is_non_probeable_404`; this is its POST twin.)
    webshop_marker = SlugMarker(
        owner_plane="sam", kind="webshop", tenant_id="h-dcn-tenant", resource_ref="x"
    )
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(markers={"h-dcn": webshop_marker}),
    )
    fake = _FakeApplicationService(ready_tenants=_READY_TENANTS)
    monkeypatch.setattr(public_app, "_application_service", lambda: fake)

    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"
    # No write performed — the cross-kind non-match was decided before any service call.
    assert fake.create_called_with is None


def test_missing_iam_put_item_failure_is_surfaced_as_bodied_500(monkeypatch):
    # R10.10 / handler last-except contract: if the submit write fails the way it would if the
    # Lambda role LACKED `dynamodb:PutItem` on the applications table (an AccessDenied-like error
    # bubbling out of the repository's save), the public edge must SURFACE it as a BODIED 500
    # `errors.api.serverError` — never an empty 502 the SPA can only render as "Failed to fetch",
    # never a leak of the underlying AWS error text/PII, never a hang or a silent success. Simulate
    # the denied IAM by a fake service whose `create_application` raises an AccessDenied-like error.
    class _DeniedWriteService(_FakeApplicationService):
        def create_application(self, *a, **k):  # the write the denied role would fail
            # Mimic the botocore ClientError an `AccessDeniedException` surfaces as — an
            # UNANTICIPATED error (not a deliberate, caller-safe `MemberValidationError` /
            # `ApplicationNotAvailable`), so it must fall through to the generic bodied 500.
            raise RuntimeError(
                "AccessDeniedException: User is not authorized to perform dynamodb:PutItem"
            )

    monkeypatch.setattr(
        public_app,
        "_application_service",
        lambda: _DeniedWriteService(ready_tenants=_READY_TENANTS),
    )
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    # Surfaced as a bodied 500 with the stable, generic code — not a 2xx, not an empty body.
    assert resp["statusCode"] == 500
    body = _body(resp)
    assert body["success"] is False
    assert body["code"] == "errors.api.serverError"
    # The underlying AWS error text / IAM detail is NEVER echoed to the unauthenticated caller.
    serialized = json.dumps(body)
    assert "AccessDenied" not in serialized
    assert "dynamodb:PutItem" not in serialized
    assert "PutItem" not in serialized


def test_published_get_slug_resolves_via_marker_body_and_returns_schema():
    # Task 3.1 (R5.1–R5.3, Property 2/4): a recognised GET whose slug marker BODY says
    # owner_plane=sam + kind=application_form resolves to its tenant (resolve-by-BODY, NOT a scan)
    # and returns that tenant's whitelisted schema (200). The `data` is the resolved view — no raw
    # record shape (no `overrides`/`field_overlay`/dotted keys), steering 39.
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 200
    data = _body(resp)["data"]
    assert (
        data["tenant_id"] == "h-dcn-tenant"
    )  # the RESOLVED tenant from the marker body
    assert [f["key"] for f in data["fields"]] == ["email"]
    # Belt-and-suspenders: the resolved view carries no raw-shape key (SEC-1 / steering 39).
    raw_shape_keys = {"overrides", "field_overlay", "fixed_overrides"}
    assert raw_shape_keys.isdisjoint(data.keys())
    for field in data["fields"]:
        assert raw_shape_keys.isdisjoint(field.keys())
        assert not any("." in k for k in field.keys())


# ── Task 3.1 — public GET {slug} read: marker-body resolve + publication gate (R5, R10) ──
#
# These pin the task-3.1 wiring behaviours beyond the happy path: resolve-by-BODY (never by
# parsing the slug; cross-plane / cross-kind → non-probeable 404, Property 2/3); the publication
# gate (a resolved-but-not-send-ready tenant → a 404 INDISTINGUISHABLE from an unknown slug,
# SEC-5 / Property 5); and no table scan (Property 4). The exhaustive SEC-1/SEC-5 assertions are
# task 3.3 — these are the paired coverage THIS wiring needs.


def test_get_read_resolution_is_a_keyed_get_object_never_a_scan(monkeypatch):
    # Property 4 (R5.3 / SEC-6): slug resolution on the public read is an O(1) keyed `resolve`
    # (a `get_object` on `_slugs/{slug}`), NEVER a `.scan()`. A fake store that FAILS LOUD if
    # anyone calls `.scan()` proves the edge never reaches for the h-dcn table-scan anti-pattern.
    class _ScanIsForbidden(_FakeSlugReader):
        def scan(self, *a, **k):  # pragma: no cover - must never be called
            raise AssertionError(
                "public read must resolve by keyed get_object, never scan"
            )

    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _ScanIsForbidden(markers=_SEEDED_MARKERS),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 200


def test_post_submit_resolution_is_a_keyed_get_object_never_a_scan(monkeypatch):
    # Property 4 (R5.5 / R10.6 / SEC-6) — task 10.2: the public SUBMIT path resolves its tenant
    # through the SAME scan-free O(1) marker `resolve` (`_resolve_sam_form_tenant` → a keyed
    # `get_object` on `_slugs/{slug}`) the GET read uses, NEVER a `.scan()`. This closes the
    # DoS-amplification gap on BOTH public routes: a `POST {random-slug}` flood costs one keyed
    # lookup each (which misses → the non-probeable 404), it can never fan out into a table scan
    # or exhaust the datastore. A fake store that FAILS LOUD on `.scan()` proves the submit edge
    # never reaches for the h-dcn table-scan anti-pattern.
    class _ScanIsForbidden(_FakeSlugReader):
        def scan(self, *a, **k):  # pragma: no cover - must never be called
            raise AssertionError(
                "public submit must resolve by keyed get_object, never scan"
            )

    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _ScanIsForbidden(markers=_SEEDED_MARKERS),
    )
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 200
    assert _body(resp)["success"] is True


def test_unknown_slug_get_burst_resolves_by_one_keyed_lookup_and_is_not_amplified(
    monkeypatch,
):
    # Task 10.3 (R10.2 / R10.6 / SEC-6) — the application-level half of "a burst of unknown-slug
    # GETs is rate-limited, NOT AMPLIFIED". The RATE-LIMITED half is the API Gateway stage throttle
    # (a live/edge behaviour, proven as the stack contract in
    # `test_public_api_hardening_stack_contract.py`; the live 429-on-exceed is the 9.4 runbook, not
    # a unit test). The NOT-AMPLIFIED half is proven HERE: a flood of *unknown* slugs each costs
    # exactly ONE keyed `resolve` (a `get_object` miss on `_slugs/{slug}`) → the non-probeable 404,
    # and NEVER a `.scan()`. This consolidates the two existing proofs into the one assertion the
    # verification item names: it uses an UNKNOWN slug (distinct from
    # `test_get_read_resolution_is_a_keyed_get_object_never_a_scan`, which seeds a KNOWN slug and
    # returns 200) AND asserts the non-probeable 404, so the "miss path" of a random-slug flood is
    # shown to be a single keyed lookup that never fans out into a table scan.
    #
    # A store that FAILS LOUD on `.scan()` AND COUNTS `resolve` calls proves both: an N-request
    # burst makes exactly N keyed lookups (one per request, O(1) each) and zero scans, so cost is
    # bounded linear-per-request and cannot amplify into a datastore-exhausting fan-out.
    resolve_calls: list[str] = []

    class _CountingScanForbidden(_FakeSlugReader):
        def resolve(self, slug):  # record each keyed lookup
            resolve_calls.append(slug)
            return super().resolve(slug)

        def resolve_slug(self, slug):  # the POST-path reader, kept consistent
            resolve_calls.append(slug)
            return super().resolve_slug(slug)

        def scan(self, *a, **k):  # pragma: no cover - must never be called
            raise AssertionError(
                "an unknown-slug GET must resolve by one keyed get_object, never scan"
            )

    # Seed NO markers: every slug in the burst is unknown (the real random-slug flood case).
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _CountingScanForbidden(markers={}),
    )

    burst = [f"no-such-tenant-{i}" for i in range(5)]
    for slug in burst:
        resp = public_app.handler(
            _proxy_event("GET", f"/public/members/{slug}/field-config")
        )
        # Each unknown-slug GET is the SAME non-probeable 404 — no enumeration oracle, no error leak.
        assert resp["statusCode"] == 404, slug
        assert _body(resp)["code"] == "errors.api.notFound", slug

    # NOT AMPLIFIED: exactly ONE keyed lookup per request (linear, O(1) each) — never a scan, never
    # a fan-out. `.scan()` would have raised; the count proves no hidden extra lookups per request.
    assert len(resolve_calls) == len(burst)


def test_get_cross_plane_marker_is_non_probeable_404(monkeypatch):
    # Property 2/3 (R5.3 / steering 35 rule 5a): a slug whose marker BODY names a DIFFERENT plane
    # (a Flask-owned landing page) resolved at the SAM edge is a clean non-match — decided from
    # the body, never by parsing the slug — so the SAM edge never reads another plane's data and
    # returns the SAME non-probeable 404 an unknown slug returns.
    flask_marker = SlugMarker(
        owner_plane="flask", kind="landing", tenant_id="h-dcn-tenant", resource_ref="x"
    )
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(markers={"h-dcn": flask_marker}),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_get_cross_kind_marker_is_non_probeable_404(monkeypatch):
    # Property 2 (R5.3): a SAM-owned marker of a DIFFERENT kind (a webshop, not the application
    # form) resolved on the field-config read is a non-match — the read never serves a wrong-kind
    # body as a form schema. Same non-probeable 404.
    webshop_marker = SlugMarker(
        owner_plane="sam", kind="webshop", tenant_id="h-dcn-tenant", resource_ref="x"
    )
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(markers={"h-dcn": webshop_marker}),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_get_unpublished_tenant_returns_non_probeable_404(monkeypatch):
    # Publication gate (R5.3 / SEC-5 / Property 5): a slug that resolves to a SAM application-form
    # tenant which is NOT send-ready / published raises the service's readiness refusal — on the
    # PUBLIC read the edge maps that to a NON-PROBEABLE 404, never a 409 that would confirm the
    # page exists. The fake service treats a tenant absent from `_READY_TENANTS` as not-ready.
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(
            markers={"h-dcn": _sam_form_marker("not-ready-tenant")}
        ),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_get_unpublished_404_is_indistinguishable_from_unknown_slug_404(monkeypatch):
    # SEC-5 (enumeration-safe) — the whole point: an UNPUBLISHED-but-existing tenant and a
    # genuinely UNKNOWN slug return the SAME status + body on the public read, so a caller cannot
    # tell "exists but unpublished" from "does not exist". (CORS is Origin-dependent and asserted
    # elsewhere; here both requests carry the same Origin so the bodies/status match.)
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(
            markers={"published-but-unready": _sam_form_marker("not-ready-tenant")}
        ),
    )
    unpublished = public_app.handler(
        _proxy_event("GET", "/public/members/published-but-unready/field-config")
    )
    unknown = public_app.handler(
        _proxy_event("GET", "/public/members/no-such-slug/field-config")
    )
    assert unpublished["statusCode"] == unknown["statusCode"] == 404
    assert _body(unpublished) == _body(unknown)


def test_get_read_never_calls_create_application(monkeypatch):
    # The GET read path is READ-ONLY: it calls `get_public_field_config` and NEVER
    # `create_application` (the submit write, Task 4). A fake service whose write blows up proves
    # the read path does not touch it.
    class _ReadOnlyService(_FakeApplicationService):
        def create_application(
            self, *a, **k
        ):  # pragma: no cover - must never be called
            raise AssertionError("the GET read must never call create_application")

    monkeypatch.setattr(
        public_app,
        "_application_service",
        lambda: _ReadOnlyService(ready_tenants=_READY_TENANTS),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 200


def test_unknown_slug_returns_non_probeable_404():
    # A well-formed, recognised route whose slug is NOT on the allow-list → 404 errors.api.notFound
    # (verify-before-trust, R2.3) — the record never lands in an arbitrary partition.
    resp = public_app.handler(
        _proxy_event("GET", "/public/members/not-a-tenant/field-config")
    )
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_unknown_slug_404_is_indistinguishable_from_unknown_path_404():
    # The whole point of the non-probeable 404 (R2.3/R1a.4): a real-but-unknown tenant slug and a
    # genuinely non-existent endpoint return the SAME status + body, so the allow-list cannot be
    # probed for valid tenant slugs (no enumeration oracle).
    unknown_slug = public_app.handler(
        _proxy_event("GET", "/public/members/not-a-tenant/field-config")
    )
    unknown_path = public_app.handler(
        _proxy_event("GET", "/public/members/h-dcn/no-such-action")
    )
    assert unknown_slug["statusCode"] == unknown_path["statusCode"] == 404
    assert _body(unknown_slug) == _body(unknown_path)


def test_empty_slug_map_makes_every_slug_non_probeable_404(monkeypatch):
    # Fail-safe: with an EMPTY reader (no markers), EVERY slug is not-found — never a guessed
    # tenant. The reader returns None for everything, so the edge returns the non-probeable 404.
    monkeypatch.setattr(
        public_app, "S3SlugMarkerStore", lambda *a, **k: _FakeSlugReader({})
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_get_slug_resolution_is_case_insensitive_at_the_edge(monkeypatch):
    # An upper-cased slug on the GET read path still resolves to the same tenant (D19 — the slug
    # is a DNS host label, case-insensitive) and returns the 200 schema. The marker is keyed on
    # the lower-cased slug, proving case-folding happens before the marker lookup.
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(
            markers={"hdcn": _sam_form_marker("h-dcn-tenant")}
        ),
    )
    resp = public_app.handler(_proxy_event("GET", "/public/members/HDCN/field-config"))
    assert resp["statusCode"] == 200
    assert _body(resp)["data"]["tenant_id"] == "h-dcn-tenant"


def test_abuse_guard_runs_before_slug_resolution():
    # A tripped honeypot is rejected at the edge (400) BEFORE any tenant resolution — even for an
    # allow-listed slug, a flood never reaches the resolver/service (R10.2).
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={public_app.HONEYPOT_FIELD: "bot"})
    )
    assert resp["statusCode"] == 400
    assert _body(resp)["code"] == "errors.api.badRequest"


# ── Task 1.4 — reverse reader swapped to the `_slugs/{slug}` bucket marker (OQ4, R7.1/R7.2) ──
#
# The reverse-lookup MECHANISM is now the `S3SlugMarkerStore` (`_slugs/{slug}` marker, OQ4),
# NOT the old `PUBLIC_TENANT_SLUG_MAP` env projection. The swap is a LOCALIZED change behind the
# UNCHANGED `TenantSlugReader` Protocol (design D5/C5): the resolver and the edge handler are
# unchanged in logic and verify-before-trust / non-probeable 404 is preserved. These pin the swap
# itself — the edge binds the resolver to the marker store, and the real store is a Protocol-shaped
# `TenantSlugReader` — WITHOUT re-asserting the slug outcomes already covered above.


def test_edge_binds_the_resolver_to_the_marker_store_reader():
    # The public edge constructs its resolver from `S3SlugMarkerStore` (the OQ4 reverse reader),
    # NOT the retired `EnvTenantSlugReader`. Asserted STRUCTURALLY over the module source (AST) so
    # the autouse fixture's runtime monkeypatch of the name does not mask the real import: the swap
    # is in the committed code, not just a test shim.
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(public_app))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    # The marker store is imported and the retired env reader is not — the swap is live in source.
    assert "S3SlugMarkerStore" in imported
    assert "EnvTenantSlugReader" not in imported
    # `_tenant_directory()` constructs the marker store (the one wiring site). The CALL expression
    # must be the marker store — assert on the AST call target, not the docstring prose (which
    # names the retired `EnvTenantSlugReader` to explain the swap).
    wiring = ast.parse(inspect.getsource(public_app._tenant_directory))
    called = {
        node.func.id
        for node in ast.walk(wiring)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "S3SlugMarkerStore" in called
    assert "EnvTenantSlugReader" not in called


def test_marker_store_satisfies_the_unchanged_tenant_slug_reader_protocol():
    # The swap is behind the Protocol: the real `S3SlugMarkerStore` is a `TenantSlugReader` by
    # duck-typing, so `TenantDirectory` (UNCHANGED) accepts it without any resolver/edge change.
    from sam.members.domain.tenant_directory import TenantSlugReader
    from sam.members.repository.slug_marker_store import S3SlugMarkerStore

    # Build with injected bucket (no env, no AWS) just to construct the instance for the check.
    store = S3SlugMarkerStore(client=object(), bucket="myadmin-public-pages-test")
    assert isinstance(store, TenantSlugReader)


def test_forged_blank_and_oversized_slugs_are_non_probeable_404_through_the_new_reader():
    # Verify-before-trust / non-probeable (R7.2) is preserved end-to-end through the swapped
    # reader: a forged slug, a blank slug segment, and an oversized (> MAX_SLUG_LENGTH) slug all
    # collapse to the SAME 404 `errors.api.notFound` the allow-listed-but-unknown case returns.
    from sam.members.domain.tenant_directory import MAX_SLUG_LENGTH

    oversized = "a" * (MAX_SLUG_LENGTH + 1)
    for slug in ("not-a-tenant", "%20", oversized):
        resp = public_app.handler(
            _proxy_event("GET", f"/public/members/{slug}/field-config")
        )
        assert resp["statusCode"] == 404, slug
        assert _body(resp)["code"] == "errors.api.notFound", slug


# ── R1a envelope + CORS (R10.3) ────────────────────────────────────────────────────────


def test_every_response_carries_the_success_envelope_and_json_body():
    # Success-range flag derives from the status (R1a.1): a 4xx/5xx error carries success=false
    # and a well-formed JSON body with Content-Type application/json.
    resp = public_app.handler(_proxy_event("GET", "/public/members/x/unknown"))
    assert resp["headers"]["Content-Type"] == "application/json"
    assert _body(resp)["success"] is False


def test_allowlisted_origin_is_echoed_not_wildcard():
    event = _proxy_event(
        "GET", _FIELD_CONFIG, headers={"Origin": "https://aanmelden.jabaki.nl"}
    )
    resp = public_app.handler(event)
    assert (
        resp["headers"]["Access-Control-Allow-Origin"] == "https://aanmelden.jabaki.nl"
    )
    assert resp["headers"]["Access-Control-Allow-Origin"] != "*"
    assert "Origin" in resp["headers"].get("Vary", "")


def test_cors_header_present_on_error_responses_too():
    # CORS must be on EVERY response incl. errors so the browser can read the body (R1a.1).
    event = _proxy_event(
        "POST",
        _APPLICATIONS,
        body={public_app.HONEYPOT_FIELD: "bot"},
        headers={"Origin": "https://form.example"},
    )
    resp = public_app.handler(event)
    assert resp["statusCode"] == 400
    assert resp["headers"]["Access-Control-Allow-Origin"] == "https://form.example"


def test_foreign_origin_is_fail_closed_no_wildcard():
    event = _proxy_event(
        "GET", _FIELD_CONFIG, headers={"Origin": "https://evil.example"}
    )
    resp = public_app.handler(event)
    assert "Access-Control-Allow-Origin" not in resp["headers"]


def test_no_configured_allowlist_is_fail_closed(monkeypatch):
    # With no PUBLIC_FORM_ALLOWED_ORIGINS, no origin is permitted — never a bare `*` on the
    # public edge (R10.3/R10.4).
    monkeypatch.delenv(public_app.ALLOWED_ORIGINS_ENV, raising=False)
    event = _proxy_event(
        "GET", _FIELD_CONFIG, headers={"Origin": "https://aanmelden.jabaki.nl"}
    )
    resp = public_app.handler(event)
    assert "Access-Control-Allow-Origin" not in resp["headers"]


# ── Task 1.4 audit — gap-fill assertions ──────────────────────────────────────────────
#
# The task-1.4 contract (R14.1b public route reachable with no token; R14.8 unknown slug →
# 404 indistinguishable from no-endpoint; R14.12 partial honeypot/oversized/malformed → 400;
# CORS on success AND error) is already pinned above. These three close the remaining gaps an
# audit surfaced — each exercises a branch of ``public_app`` the suite above did not yet assert:
#   1. CORS is echoed on the non-probeable 404 (above it is only asserted on the 400 abuse path);
#   2. the unknown-slug and unknown-path 404s are indistinguishable INCLUDING their CORS headers,
#      not just their JSON body — otherwise a browser could tell a real-but-unknown tenant from a
#      genuinely-absent endpoint by the presence/absence of Access-Control-Allow-Origin (R14.8);
#   3. the oversized-payload 400 also trips for a base64-encoded body (the `_raw_body_byte_length`
#      decode branch — R14.12 oversized → 400 regardless of transfer encoding).


def test_cors_header_echoed_on_non_probeable_404():
    # R14.8 + R14.12 (CORS on error): the non-probeable 404 for an unknown slug must still carry
    # the restricted Access-Control-Allow-Origin for an allow-listed Origin, so the browser can
    # read the (neutral) 404 body — CORS is on EVERY response, including the not-found path.
    resp = public_app.handler(
        _proxy_event(
            "GET",
            "/public/members/not-a-tenant/field-config",
            headers={"Origin": "https://aanmelden.jabaki.nl"},
        )
    )
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"
    assert (
        resp["headers"]["Access-Control-Allow-Origin"] == "https://aanmelden.jabaki.nl"
    )
    assert resp["headers"]["Access-Control-Allow-Origin"] != "*"


def test_unknown_slug_and_unknown_path_404_are_indistinguishable_including_cors_headers():
    # R14.8: "indistinguishable from no-endpoint" has to hold for what a browser can OBSERVE —
    # not only the JSON body (asserted above) but the CORS header too. If the unknown-slug 404
    # echoed an origin the unknown-path 404 did not (or vice-versa), the allow-list would leak
    # through the header. Both are driven with the same allow-listed Origin and must match on
    # status, body, AND the Access-Control-Allow-Origin header.
    origin = {"Origin": "https://aanmelden.jabaki.nl"}
    unknown_slug = public_app.handler(
        _proxy_event("GET", "/public/members/not-a-tenant/field-config", headers=origin)
    )
    unknown_path = public_app.handler(
        _proxy_event("GET", "/public/members/h-dcn/no-such-action", headers=origin)
    )
    assert unknown_slug["statusCode"] == unknown_path["statusCode"] == 404
    assert _body(unknown_slug) == _body(unknown_path)
    assert (
        unknown_slug["headers"].get("Access-Control-Allow-Origin")
        == unknown_path["headers"].get("Access-Control-Allow-Origin")
        == "https://aanmelden.jabaki.nl"
    )


def test_oversized_base64_encoded_payload_returns_neutral_400(monkeypatch):
    # R14.12 (oversized → 400): the payload cap measures the DECODED size of a base64-encoded
    # body, so an oversized submission cannot slip past the guard by base64-encoding it.
    import base64

    monkeypatch.setenv("PUBLIC_MAX_PAYLOAD_BYTES", "64")
    raw = json.dumps({"fields": {"note": "x" * 200}}).encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    event = _proxy_event("POST", _APPLICATIONS, body=encoded, is_base64=True)
    resp = public_app.handler(event)
    assert resp["statusCode"] == 400
    assert _body(resp)["code"] == "errors.api.badRequest"


# ── Per-tenant embed-origin CORS reflection (application-form-builder task 5.3/5.4 — R5.2) ──
#
# The ONE tenant-authored `application_embed_origins` list (authored onto `config#mail`, task 5.1)
# feeds the SAM public API CORS: for a route that resolves to an allow-listed tenant, an Origin on
# THAT tenant's list is echoed into `Access-Control-Allow-Origin` IN ADDITION to the static
# stack-wide baseline (`PUBLIC_FORM_ALLOWED_ORIGINS`). These pin:
#   * a tenant-configured origin (NOT in the static baseline) IS reflected on that tenant's route;
#   * an un-configured tenant / a disallowed origin is NOT reflected (fail-closed, no `*`);
#   * the per-tenant list is honoured on the recognised-route 501 (service pending);
#   * a projection read error degrades to the static baseline only (CORS never crashes a response).
#
# The slug→tenant reader (the `_slugs/{slug}` marker store faked by the autouse fixture, OQ4) resolves the
# `h-dcn` slug on `_FIELD_CONFIG`/`_APPLICATIONS` to tenant_id `h-dcn-tenant`, so these fakes key
# on that resolved tenant_id — never the raw slug (verify-before-trust: CORS reads the RESOLVED
# tenant's authored list).

_TENANT_EMBED_ORIGIN = "https://members.h-dcn.nl"


class _FakeEmbedOriginReader:
    """A stand-in for ``MembersProjectionReader`` that returns a canned per-tenant origin list.

    ``public_app._tenant_embed_origins`` constructs ``MembersProjectionReader()`` and calls
    ``get_application_embed_origins(tenant_id)``; monkeypatching the name to this fake avoids any
    DynamoDB/projection dependency while exercising the real CORS union logic. Keyed on the
    RESOLVED tenant_id so a tenant not in the map returns ``[]`` (un-configured = standalone).
    """

    def __init__(self, by_tenant: dict[str, list[str]] | None = None):
        self._by_tenant = by_tenant or {}

    def get_application_embed_origins(self, tenant_id: str) -> list[str]:
        return list(self._by_tenant.get(tenant_id, []))


def test_tenant_configured_embed_origin_is_reflected_in_cors(monkeypatch):
    # R5.2: an Origin that is NOT in the static stack-wide baseline but IS on the resolved
    # tenant's `application_embed_origins` is echoed back — the tenant's own embedding site may
    # call the public endpoints cross-origin. (`h-dcn` slug → `h-dcn-tenant` via the fixture.)
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader(
            {"h-dcn-tenant": [_TENANT_EMBED_ORIGIN]}
        ),
    )
    event = _proxy_event("GET", _FIELD_CONFIG, headers={"Origin": _TENANT_EMBED_ORIGIN})
    resp = public_app.handler(event)
    assert resp["statusCode"] == 200  # task 3.1: the GET read returns the schema
    assert resp["headers"]["Access-Control-Allow-Origin"] == _TENANT_EMBED_ORIGIN
    assert resp["headers"]["Access-Control-Allow-Origin"] != "*"
    assert "Origin" in resp["headers"].get("Vary", "")


def test_static_baseline_still_reflected_alongside_tenant_origins(monkeypatch):
    # The per-tenant list AUGMENTS, never replaces, the static baseline: an Origin on the
    # stack-wide `PUBLIC_FORM_ALLOWED_ORIGINS` is still echoed for a tenant that also has its own
    # (distinct) embed origins configured.
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader(
            {"h-dcn-tenant": [_TENANT_EMBED_ORIGIN]}
        ),
    )
    event = _proxy_event(
        "GET", _FIELD_CONFIG, headers={"Origin": "https://aanmelden.jabaki.nl"}
    )
    resp = public_app.handler(event)
    assert (
        resp["headers"]["Access-Control-Allow-Origin"] == "https://aanmelden.jabaki.nl"
    )


def test_unconfigured_tenant_does_not_reflect_a_non_baseline_origin(monkeypatch):
    # An un-configured tenant (no `application_embed_origins`) + an Origin that is NOT on the
    # static baseline → fail-closed: the header is dropped, never a `*`. The reader returns [] for
    # the resolved tenant.
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader({}),  # h-dcn-tenant has no origins
    )
    event = _proxy_event("GET", _FIELD_CONFIG, headers={"Origin": _TENANT_EMBED_ORIGIN})
    resp = public_app.handler(event)
    assert resp["statusCode"] == 200
    assert "Access-Control-Allow-Origin" not in resp["headers"]


def test_origin_allowed_for_one_tenant_is_not_reflected_for_another(monkeypatch):
    # Per-tenant isolation (Property 5): an Origin configured for tenant A is NOT echoed on a
    # DIFFERENT tenant's route. `form-slug` → `form-tenant` (seeded by the fixture) has no origins,
    # so `h-dcn-tenant`'s embed origin is not reflected there.
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader(
            {"h-dcn-tenant": [_TENANT_EMBED_ORIGIN]}
        ),
    )
    event = _proxy_event(
        "GET",
        "/public/members/form-slug/field-config",
        headers={"Origin": _TENANT_EMBED_ORIGIN},
    )
    resp = public_app.handler(event)
    assert (
        resp["statusCode"] == 200
    )  # form-slug → form-tenant (send-ready), schema returned
    assert "Access-Control-Allow-Origin" not in resp["headers"]


def test_tenant_embed_origin_is_not_reflected_on_a_non_probeable_404(monkeypatch):
    # The non-probeable-404 contract (R2.3/R1a.4) is preserved: an UNKNOWN slug never resolves to a
    # tenant, so its 404 carries ONLY the static baseline — it must stay indistinguishable from an
    # unknown-path 404. A tenant's embed origin must NOT leak onto an unknown-slug 404 (there is no
    # resolved tenant to read it from).
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader(
            {"h-dcn-tenant": [_TENANT_EMBED_ORIGIN]}
        ),
    )
    unknown_slug = public_app.handler(
        _proxy_event(
            "GET",
            "/public/members/not-a-tenant/field-config",
            headers={"Origin": _TENANT_EMBED_ORIGIN},
        )
    )
    assert unknown_slug["statusCode"] == 404
    # The tenant origin is NOT on the static baseline and the slug did not resolve → not reflected.
    assert "Access-Control-Allow-Origin" not in unknown_slug["headers"]


@pytest.mark.parametrize(
    "confirmed_origin",
    ["https://sites.google.com", "https://portal.h-dcn.nl"],
)
def test_confirmed_v1_targets_are_reflected_for_the_configured_tenant(
    monkeypatch, confirmed_origin
):
    # R5.2/R9.2: the two CONFIRMED v1 external embed targets — a Google Site
    # (`https://sites.google.com`) and the h-dcn event portal (`https://portal.h-dcn.nl`) — are
    # each reflected into `Access-Control-Allow-Origin` on the resolved tenant's route when that
    # tenant has authored them. Neither is on the static baseline, so this exercises the
    # per-tenant union path with the REAL targets the spec names (not a stand-in origin).
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader(
            {
                "h-dcn-tenant": [
                    "https://sites.google.com",
                    "https://portal.h-dcn.nl",
                ]
            }
        ),
    )
    event = _proxy_event("GET", _FIELD_CONFIG, headers={"Origin": confirmed_origin})
    resp = public_app.handler(event)
    assert resp["statusCode"] == 200  # task 3.1: the GET read returns the schema
    assert resp["headers"]["Access-Control-Allow-Origin"] == confirmed_origin
    assert resp["headers"]["Access-Control-Allow-Origin"] != "*"


def test_confirmed_v1_target_denied_for_an_unconfigured_tenant(monkeypatch):
    # R9.2 "deny others": the h-dcn portal is reflected for the tenant that authored it, but a
    # DIFFERENT tenant (`form-slug` → `form-tenant`, no origins) does NOT reflect it — fail-closed,
    # never a `*`. This is the deny-half of "reflect the configured origins and deny others" with
    # the confirmed target.
    monkeypatch.setattr(
        public_guards,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader(
            {"h-dcn-tenant": ["https://sites.google.com", "https://portal.h-dcn.nl"]}
        ),
    )
    event = _proxy_event(
        "GET",
        "/public/members/form-slug/field-config",
        headers={"Origin": "https://portal.h-dcn.nl"},
    )
    resp = public_app.handler(event)
    assert (
        resp["statusCode"] == 200
    )  # form-slug → form-tenant (send-ready), schema returned
    assert "Access-Control-Allow-Origin" not in resp["headers"]


def test_cors_degrades_to_static_baseline_when_projection_read_errors(monkeypatch):
    # Fail-safe (Property 2 / R4.1 discipline): the CORS decision must never crash a public
    # response. If resolving the per-tenant origins raises (e.g. a projection/table error), the
    # edge degrades to the static baseline only — the response is still well-formed and the static
    # allow-listed Origin is still honoured.
    class _BoomReader:
        def get_application_embed_origins(self, tenant_id):
            raise RuntimeError("projection unavailable")

    monkeypatch.setattr(
        public_guards, "MembersProjectionReader", lambda *a, **k: _BoomReader()
    )
    # A static-baseline Origin is still echoed despite the per-tenant read blowing up.
    static_ok = public_app.handler(
        _proxy_event(
            "GET", _FIELD_CONFIG, headers={"Origin": "https://aanmelden.jabaki.nl"}
        )
    )
    assert static_ok["statusCode"] == 200
    assert (
        static_ok["headers"]["Access-Control-Allow-Origin"]
        == "https://aanmelden.jabaki.nl"
    )
    # A tenant-only Origin is dropped (the per-tenant list could not be read) — fail-closed, no `*`.
    tenant_only = public_app.handler(
        _proxy_event("GET", _FIELD_CONFIG, headers={"Origin": _TENANT_EMBED_ORIGIN})
    )
    assert "Access-Control-Allow-Origin" not in tenant_only["headers"]


# ── Task 3.3 — SEC-1 / SEC-5 completeness battery (public GET {slug} read, R5.1–R5.3/R10.1/R10.5) ──
#
# Task 3.1 LANDED the public read and task 3.2 the SEC-1/SEC-5 edge behaviour; the sections above
# already pin the happy-path whitelist shape (no raw key on the served `data`), marker-body resolve
# (not scan), the publication gate, and the pairwise "unpublished ≡ unknown" / "unknown-slug ≡
# unknown-path" 404s. Task 3.3 CONSOLIDATES the remaining SEC-1 / SEC-5 assertions the battery was
# missing — it does NOT re-add what is above:
#
#   SEC-1 (fail-closed whitelist — the un-asserted gap):
#     T(SEC-1a) the edge guard `_assert_fail_closed_public_schema` is a transparent pass-through for
#               a clean resolved view (no false positive);
#     T(SEC-1b) a schema that regressed to carry a raw-shape key AT THE TOP LEVEL makes the guard
#               FAIL CLOSED → the handler maps the raise to a neutral bodied 500 (never over-exposure);
#     T(SEC-1c) a raw-shape key INSIDE A FIELD also fails closed (the guard checks field keys too);
#     T(SEC-1d) a dotted `{group}.{key}` physical key fails closed (the dotted-key branch);
#     T(SEC-1e) the fail-closed 500 body echoes NEITHER the offending key NOR any field value
#               (no over-exposure on the unauthenticated surface);
#     T(SEC-1f) an un-whitelisted / unknown field the authority did not expose does NOT appear in
#               the served schema (allowlist default-HIDDEN — no un-whitelisted field escapes).
#
#   SEC-5 (enumeration-safe — the consolidated gap):
#     T(SEC-5a) unknown slug, cross-plane marker, cross-kind marker, AND unpublished tenant ALL
#               return a BYTE-IDENTICAL 404 (same status + same body) in ONE battery — no single
#               field distinguishes "does not exist" from "exists but not for you / not yet", so
#               there is no enumeration oracle (T5 resolve-by-body applies: the cross-plane /
#               cross-kind cases are decided from the marker BODY, not the slug string).


# ── SEC-1: the fail-closed edge guard (`_assert_fail_closed_public_schema`) ────────────


def test_assert_fail_closed_public_schema_passes_through_a_clean_resolved_view():
    # T(SEC-1a): the guard is a transparent pass-through for a well-formed resolved view (the shape
    # `get_public_field_config` returns) — it must not raise on the legitimate schema (no false
    # positive) and returns it unchanged for the call site.
    clean = _whitelisted_schema("h-dcn-tenant")
    assert public_app._assert_fail_closed_public_schema(clean) is clean


@pytest.mark.parametrize("raw_key", sorted(public_app._RAW_SHAPE_KEYS))
def test_assert_fail_closed_raises_on_a_top_level_raw_shape_key(raw_key):
    # T(SEC-1b): a schema that regressed to carry a raw/physical-shape key at the TOP LEVEL
    # (`field_overlay` / `overrides` / `fixed_overrides`) must make the guard FAIL CLOSED (raise),
    # so a future authority regression surfaces as a server error, never a silent over-exposure.
    leaky = _whitelisted_schema("h-dcn-tenant")
    leaky[raw_key] = {"personal": {"gender": "secret"}}
    with pytest.raises(ValueError):
        public_app._assert_fail_closed_public_schema(leaky)


@pytest.mark.parametrize("raw_key", sorted(public_app._RAW_SHAPE_KEYS))
def test_assert_fail_closed_raises_on_a_raw_shape_key_inside_a_field(raw_key):
    # T(SEC-1c): the guard also inspects each FIELD's keys — a raw-shape key that leaked onto a
    # field (not just the top level) fails closed too.
    leaky = _whitelisted_schema("h-dcn-tenant")
    leaky["fields"][0][raw_key] = {"x": 1}
    with pytest.raises(ValueError):
        public_app._assert_fail_closed_public_schema(leaky)


def test_assert_fail_closed_raises_on_a_dotted_physical_key():
    # T(SEC-1d): a dotted `{group}.{key}` physical-layout key (the storage shape steering 39 keeps
    # INSIDE the repository) anywhere in the schema fails closed — at the top level AND inside a
    # field — so the physical two-map/dotted-key layout can never cross the public boundary.
    top_dotted = _whitelisted_schema("h-dcn-tenant")
    top_dotted["personal.gender"] = "m"
    with pytest.raises(ValueError):
        public_app._assert_fail_closed_public_schema(top_dotted)

    field_dotted = _whitelisted_schema("h-dcn-tenant")
    field_dotted["fields"][0]["personal.gender"] = "m"
    with pytest.raises(ValueError):
        public_app._assert_fail_closed_public_schema(field_dotted)


def test_fail_closed_schema_regression_surfaces_as_a_neutral_bodied_500(monkeypatch):
    # T(SEC-1b end-to-end): wire a service whose `get_public_field_config` returns a schema that
    # leaked a raw-shape key. The edge guard raises, and `handler` maps that to the generic bodied
    # 500 (`errors.api.serverError`) — NOT a 200 that would over-expose the raw shape on the
    # unauthenticated public surface. Fail-closed end-to-end through the real handler.
    class _LeakyService(_FakeApplicationService):
        def get_public_field_config(self, tenant_id: str) -> dict:
            schema = _whitelisted_schema(tenant_id)
            schema["overrides"] = {"personal": {"gender": "leaked"}}
            return schema

    monkeypatch.setattr(
        public_app,
        "_application_service",
        lambda: _LeakyService(ready_tenants=_READY_TENANTS),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 500
    assert _body(resp)["code"] == "errors.api.serverError"


def test_fail_closed_500_body_does_not_echo_the_offending_key_or_any_value(monkeypatch):
    # T(SEC-1e): the fail-closed 500 must not leak WHAT tripped it. Neither the forbidden raw-shape
    # key name nor the secret value it carried may appear anywhere in the client-facing body — the
    # over-exposure the guard exists to prevent must not be re-created by the error response.
    secret_value = "s3cr3t-overlay-value"

    class _LeakyService(_FakeApplicationService):
        def get_public_field_config(self, tenant_id: str) -> dict:
            schema = _whitelisted_schema(tenant_id)
            schema["field_overlay"] = {"personal": {"gender": secret_value}}
            return schema

    monkeypatch.setattr(
        public_app,
        "_application_service",
        lambda: _LeakyService(ready_tenants=_READY_TENANTS),
    )
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 500
    assert "field_overlay" not in resp["body"]
    assert secret_value not in resp["body"]


def test_un_whitelisted_field_does_not_escape_into_the_public_schema(monkeypatch):
    # T(SEC-1f): the served schema carries ONLY the whitelisted fields the authority exposed — an
    # un-whitelisted / unknown field is absent (allowlist default-HIDDEN, fail-closed R5.2). The
    # authority (`get_public_field_config`) builds an explicit named-key resolved view and never
    # copies a raw item, so a staff-only / newly-added field never rides along to the public edge.
    # Here the fake authority returns exactly what the real service would expose (email only); the
    # assertion is that an un-whitelisted field name (e.g. an internal `secret_api_key`, or a
    # staff-only `internal_note`) never appears — not at the top level and not on any field.
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 200
    data = _body(resp)["data"]
    exposed_field_keys = {f["key"] for f in data["fields"]}
    # The whitelist exposed only the opted-in applicant field(s); nothing un-whitelisted leaked.
    assert exposed_field_keys == {"email"}
    for un_whitelisted in ("secret_api_key", "internal_note", "application_visible"):
        assert un_whitelisted not in data
        assert all(un_whitelisted not in f for f in data["fields"])


# ── SEC-5: unknown / cross-plane / cross-kind / unpublished are ALL byte-identical 404s ──


def test_all_not_found_causes_return_a_byte_identical_404(monkeypatch):
    # T(SEC-5a) — the consolidated enumeration-safety battery (SEC-5): the FOUR distinct not-found
    # causes on the public read must be INDISTINGUISHABLE from one another — same status AND same
    # body — so no single field tells a caller which cause applied (no enumeration oracle). The
    # cross-plane / cross-kind cases are decided from the marker BODY, never the slug string (T5
    # resolve-by-body). All four requests carry the SAME Origin so CORS cannot introduce a spurious
    # difference; the bodies and statuses must match byte-for-byte.
    #
    #   1. unknown slug          — no marker at all
    #   2. cross-plane marker    — body says owner_plane=flask (a Flask-owned landing page)
    #   3. cross-kind marker     — body says kind=webshop (SAM-owned, wrong kind)
    #   4. unpublished tenant    — resolves to a SAM application_form tenant that is NOT send-ready
    markers = {
        "cross-plane": SlugMarker(
            owner_plane="flask",
            kind="landing",
            tenant_id="h-dcn-tenant",
            resource_ref="x",
        ),
        "cross-kind": SlugMarker(
            owner_plane="sam",
            kind="webshop",
            tenant_id="h-dcn-tenant",
            resource_ref="x",
        ),
        "unpublished": _sam_form_marker("not-ready-tenant"),
        # "unknown" is deliberately absent → the reader returns None for it.
    }
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(markers=markers),
    )
    origin = {"Origin": "https://aanmelden.jabaki.nl"}

    def _get(slug: str) -> dict:
        return public_app.handler(
            _proxy_event("GET", f"/public/members/{slug}/field-config", headers=origin)
        )

    responses = {
        "unknown": _get("unknown"),
        "cross-plane": _get("cross-plane"),
        "cross-kind": _get("cross-kind"),
        "unpublished": _get("unpublished"),
    }

    # Every cause is a 404 `errors.api.notFound`, and the FULL bodies are byte-identical across
    # all four — there is no field (code, message, nor any other) that distinguishes them.
    statuses = {name: r["statusCode"] for name, r in responses.items()}
    bodies = {name: r["body"] for name, r in responses.items()}
    assert set(statuses.values()) == {404}, statuses
    distinct_bodies = set(bodies.values())
    assert len(distinct_bodies) == 1, bodies  # byte-identical — no enumeration oracle
    assert _body(responses["unknown"])["code"] == "errors.api.notFound"
