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

from sam.members.handler import public_app


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


@pytest.fixture(autouse=True)
def _allow_form_origin(monkeypatch):
    """Configure the public-form CORS allow-list AND the slug→tenant projection (R10.3, D19/R2).

    The edge is fail-closed on CORS: with no ``PUBLIC_FORM_ALLOWED_ORIGINS`` it sets no
    ``Access-Control-Allow-Origin``. Most assertions here send a matching ``Origin``, so install
    a known allow-list; the fail-closed case sets its own env explicitly.

    Task 1.3 also wires the slug resolver into the delegation seam, so a recognised route now
    resolves ``{slug}`` → ``tenant_id`` against the ``PUBLIC_TENANT_SLUG_MAP`` allow-list BEFORE
    reaching the pending service seam. Seed the ``h-dcn`` slug used throughout so a recognised,
    allow-listed route reaches the pending-service 501; the unknown-slug cases install their own
    (or no) mapping to assert the non-probeable 404.
    """
    monkeypatch.setenv(
        public_app.ALLOWED_ORIGINS_ENV, "https://aanmelden.jabaki.nl,https://form.example"
    )
    # Seed the thin slug→tenant_id projection the edge resolves against (D19/R2). `h-dcn` is the
    # slug used by _FIELD_CONFIG / _APPLICATIONS below, so it maps to a canonical tenant_id.
    monkeypatch.setenv("PUBLIC_TENANT_SLUG_MAP", "h-dcn:h-dcn-tenant,form-slug:form-tenant")


def _body(resp: dict) -> dict:
    return json.loads(resp["body"])


# ── No auth (D27, R1.1) ────────────────────────────────────────────────────────────────


def test_public_route_is_reachable_with_no_token():
    # A well-formed public GET with NO Authorization header and NO authorizer context is NOT
    # a 401/403 — the public edge does not authenticate (D27). Task 1.1's seam is pending, so
    # it resolves to 501 (route exists, behaviour pending), never an auth rejection.
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 501
    assert resp["statusCode"] not in (401, 403)


def test_public_post_is_reachable_with_no_token():
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={"fields": {"email": "a@b.nl"}})
    )
    assert resp["statusCode"] == 501
    assert resp["statusCode"] not in (401, 403)


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
    # must NOT 400 (it falls through to the pending-seam 501).
    event = _proxy_event(
        "POST", _APPLICATIONS, body={"fields": {public_app.HONEYPOT_FIELD: "   "}}
    )
    assert public_app.handler(event)["statusCode"] == 501


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
    assert public_app.handler(_proxy_event("POST", _FIELD_CONFIG, body={}))["statusCode"] == 404
    assert public_app.handler(_proxy_event("GET", _APPLICATIONS))["statusCode"] == 404


# ── Recognised route, pending behaviour (task 1.1 seam) ───────────────────────────────


def test_recognised_routes_reach_pending_seam_501():
    for method, path, body in (
        ("GET", _FIELD_CONFIG, None),
        ("POST", _APPLICATIONS, {"fields": {"email": "a@b.nl"}}),
    ):
        resp = public_app.handler(_proxy_event(method, path, body=body))
        assert resp["statusCode"] == 501, (method, path)
        assert _body(resp)["code"] == "errors.api.notImplemented"


def test_trailing_slash_is_tolerated_on_recognition():
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG + "/"))
    assert resp["statusCode"] == 501


# ── Slug resolution wired into the delegation seam (task 1.3 — D19/R2/R1a.4) ──────────


def test_allow_listed_slug_reaches_the_pending_service_seam_501():
    # A recognised route whose slug IS on the allow-list resolves to a tenant and reaches the
    # (still-pending Phase 2/4) service seam → honest 501. (The slug map is seeded by the fixture.)
    for method, path, body in (
        ("GET", _FIELD_CONFIG, None),
        ("POST", _APPLICATIONS, {"fields": {"email": "a@b.nl"}}),
    ):
        resp = public_app.handler(_proxy_event(method, path, body=body))
        assert resp["statusCode"] == 501, (method, path)
        assert _body(resp)["code"] == "errors.api.notImplemented"


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
    # Fail-safe: with no projection seeded, EVERY slug is not-found — never a guessed tenant.
    monkeypatch.delenv("PUBLIC_TENANT_SLUG_MAP", raising=False)
    resp = public_app.handler(_proxy_event("GET", _FIELD_CONFIG))
    assert resp["statusCode"] == 404
    assert _body(resp)["code"] == "errors.api.notFound"


def test_slug_resolution_is_case_insensitive_at_the_edge(monkeypatch):
    # The resolver normalizes (trim + case-fold), so an upper-cased slug on the path still resolves
    # to the same tenant and reaches the pending-service 501 (D19 — the slug is a DNS host label).
    monkeypatch.setenv("PUBLIC_TENANT_SLUG_MAP", "hdcn:h-dcn-tenant")
    resp = public_app.handler(
        _proxy_event("GET", "/public/members/HDCN/field-config")
    )
    assert resp["statusCode"] == 501


def test_abuse_guard_runs_before_slug_resolution():
    # A tripped honeypot is rejected at the edge (400) BEFORE any tenant resolution — even for an
    # allow-listed slug, a flood never reaches the resolver/service (R10.2).
    resp = public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body={public_app.HONEYPOT_FIELD: "bot"})
    )
    assert resp["statusCode"] == 400
    assert _body(resp)["code"] == "errors.api.badRequest"


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
    assert resp["headers"]["Access-Control-Allow-Origin"] == "https://aanmelden.jabaki.nl"
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
    assert resp["headers"]["Access-Control-Allow-Origin"] == "https://aanmelden.jabaki.nl"
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
