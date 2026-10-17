"""
Member-application spec task 1.1 — the **public (unauthenticated) intake** Lambda entrypoint.

This is the SAM members plane's FIRST token-less HTTP edge (D27, requirements R1/R1a/R2/R10),
a deliberate, fenced exception to ADR 0007's "deny without a verified token" invariant. It is
wired to a SEPARATE public ``AWS::Serverless::Api`` with NO ``DefaultAuthorizer`` (its own
stage / throttle / usage plan / invoke URL, task 1.3 + 7.1) and routed to THIS entrypoint —
the authenticated members API (``handler/app.py``) and its ``handler()`` are untouched, the
cleanest blast-radius isolation for the plane's first unauthenticated surface.

Thin by design (steering 35), EXACTLY like ``app.handler``/``scheduler_app.handler`` — this
entrypoint's whole job is the handler-layer adapter concerns:

    parse → abuse guards (honeypot · payload cap · CORS) → resolve-tenant-from-slug →
    delegate to the application service → shape the HTTP response

and nothing else. No business rule, no field resolution, no DynamoDB call lives here.

**The one hard difference from ``app.handler`` (the point of D27): this entrypoint NEVER calls
``_authenticate_and_authorize``.** There is no token, no tenant-from-claims, no capability /
scope gate — authority does not apply to a public applicant. The tenant is instead carried as
a PATH SLUG resolved against an allow-list (verify-before-trust, R2 — task 1.2's
``domain/tenant_directory`` fills that seam), never trusted raw.

Reuse, not reinvention (R1a). The success / error / field-error envelope is the EXISTING SAM
members one — :func:`sam.members.handler._http._response`, ``_error``, ``_field_errors_array``,
``_parse_request``, ``_json_default`` — so the public form reuses ONE response + error renderer
and every response (including errors) carries CORS headers and a well-formed JSON body and
serializes ``Decimal`` via ``_json_default``. The ONLY envelope difference is the
``Access-Control-Allow-Origin`` header: the authenticated edge answers ``*`` (token-gated), but
a public POST must restrict CORS to the known form origin(s) (R10.3/R10.4), so this module
post-processes that one header against an allow-list (:func:`_apply_cors_origin`) while leaving
the shared ``_http`` envelope — and the authenticated edge — unchanged.

Task 1.3 (this change) wires the delegation seam's FIRST step and the routes/API it sits behind:

- the two public routes (``GET …/field-config``, ``POST …/applications``) are registered on a
  SEPARATE public ``AWS::Serverless::Api`` (``MembersPublicApi``) in ``template.yaml`` with NO
  ``DefaultAuthorizer`` (D27) and CORS restricted to the form origin(s) (R10.4), pointed at THIS
  ``public_app.handler`` entrypoint (the detailed least-privilege IAM + API Gateway throttle /
  usage plan are task 7.1, not here);
- slug → ``tenant_id`` resolution is wired into :func:`_dispatch_public`: the Task-1.2
  ``domain/tenant_directory`` resolver, injected with the Task-1.3 concrete
  ``repository/tenant_slug_reader`` (the thin env-projection of the landing slug map, D19), so a
  forged/unknown slug becomes a non-probeable 404 and an allow-listed slug carries its canonical
  ``tenant_id`` forward (verify-before-trust, R2).

Still pending (later same-plane tasks, intentionally NOT built here): the two service calls behind
the resolved tenant — ``ApplicationService.get_public_field_config`` (Phase 4) and
``create_application`` (Phase 2). Until those land, a recognised public path whose slug RESOLVES
to an allow-listed tenant reaches the (still-pending) service seam and resolves to an honest
**501 Not Implemented** (``route exists, behaviour pending``) — mirroring how ``app.handler`` maps
:class:`~sam.members.handler._dispatch.RouteNotImplemented`. An UNRECOGNISED path — OR a recognised
path whose slug does NOT resolve to an allow-listed tenant — returns **404** ``errors.api.notFound``,
deliberately indistinguishable from "no such endpoint" so neither the surface nor the tenant
allow-list can be probed (R2.3/R1a.4). The abuse guards (honeypot / payload cap / malformed body)
return **400** ``errors.api.badRequest`` BEFORE any delegation (R10.2/R1a.4).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from sam.members.domain.tenant_directory import TenantDirectory, TenantResolution
from sam.members.handler._http import (
    ParsedRequest,
    _error,
    _field_errors_array,  # noqa: F401 (surface compat: the delegation/validation seam shapes 422 with it)
    _parse_request,
    _response,
)
from sam.members.repository.tenant_slug_reader import EnvTenantSlugReader

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

__all__ = [
    "HONEYPOT_FIELD",
    "MAX_PAYLOAD_BYTES",
    "PublicAbuseRejected",
    "PublicRouteNotImplemented",
    "PublicTenantNotFound",
    "handler",
]


# ── Abuse-guard configuration (R10.2) ─────────────────────────────────────────────────

#: The honeypot field name. A real applicant's browser never fills it (it is visually hidden
#: on the form, task 9.x); a naive spam bot that fills every input trips it. A submission whose
#: ``fields`` (or top-level body) carries a NON-BLANK value under this key is rejected as spam
#: with a neutral 400 BEFORE any tenant resolution or write (R10.2) — the bot is never told WHY
#: (the 400 is the same neutral ``errors.api.badRequest`` as a malformed/oversized body) so the
#: trap is not trivially discoverable. A blank / absent honeypot is the normal, accepted case.
HONEYPOT_FIELD = "website"

#: The hard payload-size cap in bytes (R10.2). A public POST must not let an unauthenticated
#: caller stream an arbitrarily large body into the Lambda (memory / cost abuse), so a raw body
#: whose byte length exceeds this is rejected with a neutral 400 BEFORE parsing / delegation. An
#: application form is small (a few dozen fields), so 64 KiB is generous head-room while still
#: bounding abuse; the value is overridable per environment via ``PUBLIC_MAX_PAYLOAD_BYTES`` for
#: a tenant with an unusually large field set, resolved at call time (:func:`_max_payload_bytes`)
#: so a test / a stack param can tune it without a redeploy of this code.
MAX_PAYLOAD_BYTES = 64 * 1024

#: The env var the separate public API's stack sets (task 1.3 / 7.1) with the comma-separated
#: allow-list of the public form's origin(s) for the CORS ``Access-Control-Allow-Origin`` header
#: (R10.3/R10.4). Unset / empty → no cross-origin browser client is permitted (fail-closed: the
#: header is simply not set, so a browser blocks the read) rather than silently echoing ``*`` —
#: the public write must not be callable from any origin.
ALLOWED_ORIGINS_ENV = "PUBLIC_FORM_ALLOWED_ORIGINS"


class PublicAbuseRejected(Exception):
    """A request tripped an abuse guard (honeypot / payload cap) — mapped to a neutral 400.

    Raised by :func:`_guard_abuse` BEFORE any tenant resolution or write, so a scripted flood
    is turned away at the edge (R10.2). The message is for the CloudWatch log only; the client
    gets the SAME neutral ``errors.api.badRequest`` 400 a malformed body gets — the guard never
    tells the caller WHICH control tripped (a honeypot that announced itself is trivial to
    defeat, R1a.4).
    """


class PublicTenantNotFound(Exception):
    """The path slug did not resolve to an allow-listed tenant → non-probeable 404 (R2.3/R1a.4).

    Raised by :func:`_dispatch_public` when the Task-1.2 :class:`TenantDirectory` resolver returns
    a not-found outcome for the request's slug (unknown / forged / blank / oversized — all uniform
    by construction, so this carries no signal). :func:`handler` maps it to the SAME
    ``404 errors.api.notFound`` an UNRECOGNISED path returns, so a real-but-unknown slug is
    deliberately indistinguishable from "no such endpoint" — the allow-list cannot be probed for
    valid tenant slugs (no enumeration oracle, R2.3/R1a.4).
    """


class PublicRouteNotImplemented(Exception):
    """A recognised public route whose domain behaviour is not built yet → honest 501.

    The delegation seam (:func:`_dispatch_public`) raises this until the later same-phase tasks
    land (slug resolver 1.2, route wiring 1.3, ``get_public_field_config`` Phase 4,
    ``create_application`` Phase 2). It maps to ``501 Not Implemented`` ("route exists, behaviour
    pending"), mirroring how :class:`sam.members.handler._dispatch.RouteNotImplemented` is mapped
    by ``app.handler`` — an honest answer, never a silent 200 or a 404 that would hide the route.
    """


# ── CORS (R10.3) — restrict the one Access-Control-Allow-Origin header ────────────────


def _allowed_origins() -> list[str]:
    """The configured public-form origin allow-list (R10.3), resolved at call time.

    Reads :data:`ALLOWED_ORIGINS_ENV` (comma-separated), trims blanks, and de-duplicates while
    preserving order. Resolved per request (not import-time) so a stack param / a test
    ``monkeypatch.setenv`` is honoured without reloading the module. Empty / unset → an empty
    list = fail-closed (no cross-origin client permitted), never a wildcard.
    """
    raw = os.environ.get(ALLOWED_ORIGINS_ENV, "") or ""
    seen: dict[str, None] = {}
    for part in raw.split(","):
        origin = part.strip()
        if origin and origin not in seen:
            seen[origin] = None
    return list(seen)


def _apply_cors_origin(response: dict, request: ParsedRequest) -> dict:
    """Restrict the response's ``Access-Control-Allow-Origin`` to the form origin(s) (R10.3).

    The shared :func:`_http._response` sets ``Access-Control-Allow-Origin: *`` (correct for the
    token-gated authenticated edge). A public POST must NOT be callable cross-origin from any
    site, so this REPLACES that one header per the allow-list (:func:`_allowed_origins`), leaving
    the rest of the shared envelope (and the authenticated edge) untouched:

    - the request's ``Origin`` is in the allow-list → echo exactly that origin (and
      ``Vary: Origin`` so a shared cache does not serve the wrong origin's header);
    - the request has no ``Origin`` (a non-browser / same-origin caller) → drop the header
      entirely rather than leave a stale ``*`` (a non-browser client does not enforce CORS);
    - the ``Origin`` is not allow-listed, or the allow-list is empty → drop the header, so a
      browser on a foreign origin blocks the read (fail-closed, no ``*``).

    CORS is applied to EVERY response — success AND error — so a browser can read the body in
    all cases (R1a.1/R10.3); this helper is the single place that decides the origin header.
    """
    headers = dict(response.get("headers") or {})
    origin = _request_origin(request)
    allowed = _allowed_origins()
    if origin and origin in allowed:
        headers["Access-Control-Allow-Origin"] = origin
        # A shared cache must key on Origin so it never serves origin A its cached
        # Access-Control-Allow-Origin: B (which B's browser would then reject).
        existing_vary = headers.get("Vary")
        headers["Vary"] = f"{existing_vary}, Origin" if existing_vary else "Origin"
    else:
        # No origin, foreign origin, or an empty allow-list → fail-closed: never echo `*` on
        # the public edge. Drop the header the shared envelope set.
        headers.pop("Access-Control-Allow-Origin", None)
    response["headers"] = headers
    return response


def _request_origin(request: ParsedRequest) -> str | None:
    """The request's ``Origin`` header value, case-insensitive on the header NAME, or ``None``.

    API Gateway REST v1 preserves the client header casing (``Origin``); HTTP API v2 lowercases
    to ``origin`` — so match the name case-insensitively (mirroring
    ``app._requested_tenant_from_request``). A list value (multi-valued header) takes the first
    entry; a blank value reads as ``None``.
    """
    for name, value in (request.headers or {}).items():
        if isinstance(name, str) and name.lower() == "origin":
            if isinstance(value, list):
                value = value[0] if value else None
            if isinstance(value, str):
                v = value.strip()
                return v or None
    return None


# ── Abuse guards (R10.2) — run BEFORE any tenant resolution / write ───────────────────


def _max_payload_bytes() -> int:
    """The active payload cap (R10.2), resolved at call time from the env override else default.

    Reads :data:`MAX_PAYLOAD_BYTES` unless ``PUBLIC_MAX_PAYLOAD_BYTES`` is set to a positive int
    (a stack param / a test may tune it); a blank / non-int / non-positive override falls back to
    the default rather than disabling the cap (fail-safe — a public write is never uncapped).
    """
    raw = os.environ.get("PUBLIC_MAX_PAYLOAD_BYTES")
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return MAX_PAYLOAD_BYTES


def _raw_body_byte_length(event: Mapping[str, Any]) -> int:
    """The RAW request body size in bytes, before JSON parsing (R10.2 payload cap).

    Measured on the raw API Gateway ``body`` string (UTF-8) so an oversized body is rejected
    WITHOUT first being fully parsed into Python objects (the parse is the expensive step we are
    guarding against). A base64-encoded body (``isBase64Encoded``) is measured on its decoded
    length. A missing / non-string body is zero (nothing to cap).
    """
    body = event.get("body")
    if not isinstance(body, str) or not body:
        return 0
    if event.get("isBase64Encoded"):
        import base64

        try:
            return len(base64.b64decode(body, validate=False))
        except (ValueError, TypeError):
            # Undecodable "base64" — measure the raw string; the parse step rejects it anyway.
            return len(body.encode("utf-8"))
    return len(body.encode("utf-8"))


def _honeypot_tripped(body: Any) -> bool:
    """True when the honeypot field carries a NON-BLANK value (R10.2) — a spam-bot tell.

    Checks the :data:`HONEYPOT_FIELD` key both at the top level of the parsed body and inside a
    nested ``fields`` object (the form posts its values under ``fields``, design §3.2), so the
    trap holds wherever a naive bot drops the value. A blank string / absent key is the normal,
    accepted case (a real browser leaves the hidden field empty). A non-mapping body is not a
    honeypot trip (it fails the malformed-body check instead).
    """
    if not isinstance(body, Mapping):
        return False
    for container in (body, body.get("fields")):
        if isinstance(container, Mapping):
            value = container.get(HONEYPOT_FIELD)
            if isinstance(value, str) and value.strip():
                return True
            if value not in (None, "", {}, []) and not isinstance(value, str):
                # A bot that posted a non-string truthy value (number / object) still trips.
                return True
    return False


def _guard_abuse(event: Mapping[str, Any], request: ParsedRequest) -> None:
    """Run the pre-write abuse guards (R10.2); raise :class:`PublicAbuseRejected` on any trip.

    Order (cheapest first): payload cap on the raw body, then malformed-body, then honeypot.
    All three raise the SAME :class:`PublicAbuseRejected` so the edge answers ONE neutral 400 —
    the caller is never told which control tripped (R1a.4). Runs BEFORE tenant resolution and
    before any delegation, so a flood is turned away at the edge without touching the domain.
    """
    cap = _max_payload_bytes()
    size = _raw_body_byte_length(event)
    if size > cap:
        raise PublicAbuseRejected(f"payload too large ({size} > {cap} bytes)")

    # A JSON body is parsed by `_parse_request` into a mapping; a body that stayed a raw string
    # (undecodable JSON) or is otherwise not an object is malformed for the public endpoints,
    # which always expect a JSON object. A GET (field-config) carries no body — that is fine.
    body = request.body
    if request.method == "POST" and not isinstance(body, Mapping):
        raise PublicAbuseRejected("request body is not a JSON object")

    if _honeypot_tripped(body):
        raise PublicAbuseRejected("honeypot field populated")


# ── Public route recognition + slug extraction (routes wired on MembersPublicApi, task 1.3) ──


#: The path prefix both public routes share. The slug is the single segment BETWEEN this prefix
#: and the trailing action segment (``field-config`` / ``applications``) — see :func:`_slug_from_path`.
_PUBLIC_PREFIX = "/public/members/"


def _is_public_route(request: ParsedRequest) -> bool:
    """True when ``(method, path)`` looks like one of the two public intake routes.

    The two public routes (design §3) are ``GET /public/members/{slug}/field-config`` and
    ``POST /public/members/{slug}/applications``. Task 1.3 registers them on the separate public
    API (``MembersPublicApi`` in ``template.yaml``); this entrypoint still recognises a path
    structurally so an unknown path 404s non-probeably (R1a.4) BEFORE the delegation seam. Matched
    on the ``/public/members/`` prefix + method + trailing segment, slug-agnostic — the slug is
    resolved to a ``tenant_id`` in :func:`_dispatch_public` (via the Task-1.2 resolver), not here.
    """
    path = (request.path or "").rstrip("/")
    if not path.startswith(_PUBLIC_PREFIX):
        return False
    if request.method == "GET" and path.endswith("/field-config"):
        return True
    if request.method == "POST" and path.endswith("/applications"):
        return True
    return False


def _slug_from_path(request: ParsedRequest) -> str:
    """Extract the raw tenant slug segment from a recognised public path (R2.1).

    The public routes carry the tenant as the single path segment between the shared
    ``/public/members/`` prefix and the trailing action (``field-config`` / ``applications``):
    ``/public/members/{slug}/field-config``. This returns that ``{slug}`` segment RAW (un-trimmed,
    un-case-folded) — normalization + the allow-list decision belong to :class:`TenantDirectory`
    (Task 1.2), which is the single place verify-before-trust is enforced. A path that somehow
    carries no slug segment yields ``""``, which the resolver treats as the uniform not-found.

    Only called AFTER :func:`_is_public_route` has confirmed the shape, so the prefix + a trailing
    action segment are guaranteed present.
    """
    path = (request.path or "").rstrip("/")
    remainder = path[len(_PUBLIC_PREFIX):] if path.startswith(_PUBLIC_PREFIX) else ""
    # remainder == "{slug}/{action}"; the slug is everything before the last "/".
    slug, _, _action = remainder.rpartition("/")
    return slug


# ── Delegation seam: slug→tenant wired here (task 1.3); service calls pending (Phase 2 / 4) ──


def _tenant_directory() -> TenantDirectory:
    """Build the slug→``tenant_id`` resolver wired to the SAM-plane concrete reader (task 1.3).

    Injects the concrete :class:`~sam.members.repository.tenant_slug_reader.EnvTenantSlugReader`
    (the thin env-projection of the landing slug map, D19) into the storage-agnostic Task-1.2
    :class:`TenantDirectory`. Constructed per request — the reader resolves its backing projection
    at call time, so a stack param / a test ``monkeypatch.setenv`` is honoured without any module
    reload. This is the single place the public edge binds the resolver to its backing store;
    swapping the store (env projection → DynamoDB row / KVS read) is a change behind the reader
    seam only, never here.
    """
    return TenantDirectory(EnvTenantSlugReader())


def _dispatch_public(request: ParsedRequest) -> Any:
    """Delegate a recognised public route to the domain — resolving the tenant slug first (task 1.3).

    This is the single downward seam from the thin public edge to the application domain. Task 1.3
    wires the FIRST step of it — resolve the path slug → ``tenant_id`` against the allow-list
    (verify-before-trust, R2) via the Task-1.2 :class:`TenantDirectory` — so a forged/unknown slug
    is turned into a non-probeable 404 HERE (:class:`PublicTenantNotFound`, mapped by
    :func:`handler`) rather than reaching the (still-pending) service layer. The slug is trusted
    for NOTHING: it only SELECTS among allow-listed tenants, and the resolved ``tenant_id`` becomes
    the ONLY source of the record's tenant (R2.2/R2.4) when the service lands.

    The service calls behind this are later same-plane tasks and are intentionally NOT built here:

    - ``GET …/field-config`` → ``ApplicationService.get_public_field_config(tenant_id)``
      (Phase 4 — readiness gate + filtered schema);
    - ``POST …/applications`` → ``ApplicationService.create_application(tenant_id, …)`` (Phase 2).

    Until those land, a slug that DID resolve to a real tenant raises
    :class:`PublicRouteNotImplemented` → an honest 501 ("route exists, behaviour pending"). So this
    task's wiring is fully exercised: an allow-listed slug reaches the pending-service 501, an
    unknown slug gets the non-probeable 404 — both without ever calling
    ``_authenticate_and_authorize`` (D27).
    """
    resolution: TenantResolution = _tenant_directory().resolve(_slug_from_path(request))
    if not resolution.ok:
        # Unknown / forged / blank / oversized slug — uniform not-found (R2.3). Raise the
        # non-probeable 404 the handler maps identically to an unrecognised path (R1a.4).
        raise PublicTenantNotFound(_slug_from_path(request))

    # Slug resolved to an allow-listed tenant (resolution.tenant_id) — the service layer that
    # consumes it is Phase 2 / Phase 4, so the behaviour is still pending. 501, not a silent 200.
    raise PublicRouteNotImplemented(f"{request.method} {request.path}")


# ── Lambda entry point (the public, token-less edge — D27) ────────────────────────────


def handler(event: Mapping[str, Any], context: Any = None) -> dict:
    """API Gateway proxy entry point for the SAM members **public application intake** (D27).

    Flow (thin adapter — NO auth): parse → abuse guards (honeypot · payload cap · CORS) →
    recognise the public route → delegate to the application domain → shape the HTTP response.
    **This entrypoint never calls ``_authenticate_and_authorize``** — authority does not apply to
    a public applicant; the tenant is carried as a path slug resolved against an allow-list
    (verify-before-trust, R2) behind the delegation seam, never from a token or a trusted body.

    Status map (R1a):
      * recognised route + allow-listed slug, service pending (Phase 2/4) → **501** ``errors.api.notImplemented``;
      * unknown / forged path OR unknown / forged tenant slug → **404** ``errors.api.notFound``
        (non-probeable — a real-but-unknown slug is indistinguishable from "no such endpoint",
        R2.3/R1a.4);
      * honeypot / oversized / malformed body → **400** ``errors.api.badRequest`` (R10.2);
      * an unanticipated error → a BODIED **500** ``errors.api.serverError`` (never an empty 502).

    Every response — success AND error — carries the shared ``_http`` envelope (``success`` flag
    + JSON body + ``Decimal`` serialization) with its ``Access-Control-Allow-Origin`` restricted
    to the configured form origin(s) (R10.3) via :func:`_apply_cors_origin`.
    """
    request = _parse_request(event)

    # 1) Abuse guards FIRST (R10.2) — a flood is turned away before any tenant resolution/write.
    try:
        _guard_abuse(event or {}, request)
    except PublicAbuseRejected as exc:
        # Neutral 400 — the caller is never told WHICH guard tripped (R1a.4). Log the reason.
        logger.info("Public intake rejected a request at the abuse guard: %s", exc)
        return _apply_cors_origin(
            _error(400, "Bad request", code="errors.api.badRequest"), request
        )

    # 2) Recognise the public route. An unknown path is a 404 deliberately indistinguishable
    #    from "no such endpoint" so the public surface cannot be probed (R1a.4).
    if not _is_public_route(request):
        return _apply_cors_origin(
            _error(404, "Not found", code="errors.api.notFound"), request
        )

    # 3) Delegate to the application domain (the slug resolver + service seam, tasks 1.2 / 1.3 /
    #    Phase 2 / Phase 4). Shape the response; CORS is applied to EVERY branch (R10.3).
    try:
        result = _dispatch_public(request)
    except PublicTenantNotFound:
        # The slug did not resolve to an allow-listed tenant → the SAME non-probeable 404 an
        # unrecognised path returns, so a real-but-unknown slug cannot be told from "no such
        # endpoint" (R2.3/R1a.4). Log the (already non-probeable) miss server-side only.
        logger.info(
            "Public intake slug for '%s %s' did not resolve to an allow-listed tenant",
            request.method,
            request.path,
        )
        return _apply_cors_origin(
            _error(404, "Not found", code="errors.api.notFound"), request
        )
    except PublicRouteNotImplemented:
        logger.info(
            "Public intake route '%s %s' recognised but not implemented yet",
            request.method,
            request.path,
        )
        return _apply_cors_origin(
            _error(501, "Not implemented", code="errors.api.notImplemented"), request
        )
    except Exception:
        # Any UNANTICIPATED error becomes a BODIED 500 — never an empty 502 the SPA can only
        # render as "Failed to fetch". The traceback is logged SERVER-side; the client gets only
        # a stable code + generic message, no internals/PII. MUST stay the LAST except.
        request_id = getattr(context, "aws_request_id", None)
        logger.exception(
            "Unhandled error in public intake for '%s %s' (request_id=%s)",
            request.method,
            request.path,
            request_id,
        )
        return _apply_cors_origin(
            _error(500, "Internal error", code="errors.api.serverError"), request
        )

    # A completed read/write result → 200 with the shared envelope. (The 202 for an accepted
    # submission is shaped by the create_application path in Phase 2, which returns the
    # AcceptedResult the service layer marks; task 1.1's seam never reaches a success body.)
    return _apply_cors_origin(_response(200, {"data": result}), request)
