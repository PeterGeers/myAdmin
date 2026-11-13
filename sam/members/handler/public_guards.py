"""CORS + payload/abuse guards for the public form edge.
Part of public_app (task 8).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from sam.members.handler._http import (
    ParsedRequest,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader

logger = logging.getLogger(__name__)

from ._public_shared import (
    _DEFAULT_FORM_APEX,
    ALLOWED_ORIGINS_ENV,
    APEX_ENV,
    HONEYPOT_FIELD,
    MAX_PAYLOAD_BYTES,
    PublicAbuseRejected,
)


def _allowed_origins() -> list[str]:
    """The STATIC (stack-wide) public-form origin allow-list (R10.3), resolved at call time.

    Reads :data:`ALLOWED_ORIGINS_ENV` (comma-separated), trims blanks, and de-duplicates while
    preserving order. Resolved per request (not import-time) so a stack param / a test
    ``monkeypatch.setenv`` is honoured without reloading the module. Empty / unset → an empty
    list = fail-closed (no cross-origin client permitted at the stack level), never a wildcard.

    This is the stack-wide baseline (e.g. the canonical ``aanmelden.jabaki.nl`` form host). A
    tenant may additionally publish its OWN embed origin(s) via ``application_embed_origins`` on
    ``config#mail`` (task 5.1); those are resolved PER TENANT by :func:`_tenant_embed_origins` and
    unioned with this baseline by :func:`_apply_cors_origin` — the SAME tenant-authored list that
    feeds the CloudFront form's ``frame-ancestors`` (task 5.2), so the two enforcement points
    cannot drift. The union stays fail-closed: an unset env AND an unconfigured tenant → ``[]``.
    """
    raw = os.environ.get(ALLOWED_ORIGINS_ENV, "") or ""
    seen: dict[str, None] = {}
    for part in raw.split(","):
        origin = part.strip()
        if origin and origin not in seen:
            seen[origin] = None
    return list(seen)


def _tenant_embed_origins(tenant_id: str | None) -> list[str]:
    """The PER-TENANT embed-origin allow-list for ``tenant_id`` from ``config#mail`` (R5.2, D27).

    Reads the tenant-authored ``application_embed_origins`` list off the projected ``config#mail``
    row via the SAME read-only governance-projection reader the rest of the public edge uses
    (:class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`,
    ``get_application_embed_origins`` — trim + de-dupe, empty-is-valid). This is the SAM public
    API half of the ONE tenant-authored list (task 5.3): an origin on it is echoed into
    ``Access-Control-Allow-Origin`` for THAT tenant's public routes, so the tenant's own embedding
    site may call the public field-config / submit endpoints cross-origin.

    Resolved ONLY for a route that has already resolved to an allow-listed tenant (the recognised
    field-config / submit routes) — never for the non-probeable 404 branches, so an unknown-slug
    404 and an unknown-path 404 keep the SAME (static-only) CORS header and remain indistinguishable
    (R2.3/R1a.4). A blank/absent ``tenant_id`` → ``[]``.

    **Fail-safe — never raises.** The CORS decision must not crash a public response, so ANY error
    resolving the projection (a missing table env, a DynamoDB error, a malformed row) degrades to
    ``[]`` = the tenant permits no extra cross-origin embed (the static baseline still applies).
    """
    if not tenant_id:
        return []
    try:
        return MembersProjectionReader().get_application_embed_origins(tenant_id)
    except Exception:  # pragma: no cover — defensive: CORS never crashes a response
        logger.warning(
            "Public intake: failed to resolve embed origins for tenant %r; "
            "falling back to the static CORS allow-list only",
            tenant_id,
        )
        return []


def _form_apex() -> str | None:
    """The per-env PUBLIC-PAGES apex the published form is served on (R5.1), resolved at call time.

    Reads :data:`APEX_ENV` and trims it; an UNSET var resolves to the canonical
    :data:`_DEFAULT_FORM_APEX` (``jabaki.nl`` — the SAME apex ``application_publish`` bakes into the
    served canonical URL, so the CORS slug-host and the served host cannot drift). An explicitly
    BLANK override resolves to ``None`` so the slug-host union member is SKIPPED — a missing apex
    NEVER raises and NEVER widens the allow-list (CORS stays fail-closed); it only declines to add
    the one slug-host member. Resolved per request (not import-time) so a stack param / a test
    ``monkeypatch.setenv`` is honoured without reloading the module (mirrors :func:`_allowed_origins`).
    """
    raw = os.environ.get(APEX_ENV)
    if raw is None:
        return _DEFAULT_FORM_APEX
    apex = raw.strip()
    return apex or None


def _resolved_slug_host(resolved_slug: str | None) -> str | None:
    """The published form's OWN origin ``https://{resolved_slug}.{apex}`` for CORS Option B (R5.1).

    The TIGHTEST CORS match (design Round 2 "CORS Option B"): the form's OWN host for the slug the
    route ALREADY resolved from the ``_slugs/{slug}`` marker for THIS request (verify-before-trust —
    never a raw/client value). Returns ``None`` — so NO slug-host member is unioned into the
    allow-list — when there is no resolved slug (e.g. the non-probeable 404 branches, where no slug
    resolved) OR when the apex is unset/blank (:func:`_form_apex`). Both cases keep CORS fail-closed:
    a request is admitted by the slug host ONLY when a real resolved slug AND a configured apex
    compose the form's own origin — never a broad ``*.{apex}`` wildcard, never a foreign host.
    """
    if not isinstance(resolved_slug, str) or not resolved_slug.strip():
        return None
    apex = _form_apex()
    if not apex:
        return None
    return f"https://{resolved_slug.strip()}.{apex}"


def _apply_cors_origin(
    response: dict,
    request: ParsedRequest,
    *,
    tenant_id: str | None = None,
    resolved_slug: str | None = None,
) -> dict:
    """Restrict the response's ``Access-Control-Allow-Origin`` to the form origin(s) (R10.3/R5.2).

    The shared :func:`_http._response` sets ``Access-Control-Allow-Origin: *`` (correct for the
    token-gated authenticated edge). A public POST must NOT be callable cross-origin from any
    site, so this REPLACES that one header per the allow-list, leaving the rest of the shared
    envelope (and the authenticated edge) untouched. The allow-list is the UNION of:

    - the STATIC stack-wide baseline (:func:`_allowed_origins`, e.g. the canonical form host);
    - the PER-TENANT ``application_embed_origins`` (:func:`_tenant_embed_origins`) — supplied ONLY
      when the route resolved to an allow-listed ``tenant_id`` (task 5.3). On the non-probeable
      404 branches ``tenant_id`` is ``None``, so those responses carry the static baseline ONLY
      and an unknown-slug / unknown-path 404 stay indistinguishable (R2.3/R1a.4); and
    - CORS Option B (task 7.1, R5.1/R5.5): the form's OWN resolved slug host
      ``https://{resolved_slug}.{apex}`` (:func:`_resolved_slug_host`) — supplied ONLY when the
      route has resolved the slug to its tenant for THIS request (never a raw/client value), so the
      published per-tenant host ``{slug}.{apex}`` the form is served on can read its own submit
      response. This is the TIGHTEST widening: a single exact host, computed from the per-env apex
      (:func:`_form_apex`), NEVER a broad ``*.{apex}`` wildcard — so no foreign ``*.{apex}`` site is
      admitted. On the non-probeable 404 branches ``resolved_slug`` is ``None`` (nothing resolved),
      so no slug-host member is added and those responses stay indistinguishable.

    Decision (fail-closed, never ``*``):

    - the request's ``Origin`` is in the union → echo exactly that origin (and ``Vary: Origin``
      so a shared cache does not serve the wrong origin's header);
    - the request has no ``Origin`` (a non-browser / same-origin caller) → drop the header
      entirely rather than leave a stale ``*`` (a non-browser client does not enforce CORS);
    - the ``Origin`` is not in the union, or the union is empty → drop the header, so a browser
      on a foreign origin blocks the read (fail-closed, no ``*``).

    CORS is applied to EVERY response — success AND error — so a browser can read the body in
    all cases (R1a.1/R10.3); this helper is the single place that decides the origin header.
    """
    headers = dict(response.get("headers") or {})
    origin = _request_origin(request)
    allowed = _allowed_origins() + _tenant_embed_origins(tenant_id)
    # CORS Option B (task 7.1): union the form's OWN resolved slug host when the route resolved a
    # slug for THIS request (and the apex is configured). ``None`` (no resolved slug / no apex) adds
    # nothing — the union stays the static baseline ∪ tenant embed origins (fail-closed).
    slug_host = _resolved_slug_host(resolved_slug)
    if slug_host and slug_host not in allowed:
        allowed = allowed + [slug_host]
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
