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
the shared ``_http`` envelope — and the authenticated edge — unchanged. That allow-list is the
union of a STATIC stack-wide baseline (:func:`_allowed_origins`) and, for a route that resolved to
an allow-listed tenant, that tenant's OWN ``application_embed_origins`` authored on ``config#mail``
(:func:`_tenant_embed_origins`, task 5.3) — the SAME per-tenant list that drives the CloudFront
form's ``frame-ancestors``, so the two embed-enforcement points cannot drift.

Task 1.3 (this change) wires the delegation seam's FIRST step and the routes/API it sits behind:

- the two public routes (``GET …/field-config``, ``POST …/applications``) are registered on a
  SEPARATE public ``AWS::Serverless::Api`` (``MembersPublicApi``) in ``template.yaml`` with NO
  ``DefaultAuthorizer`` (D27) and CORS restricted to the form origin(s) (R10.4), pointed at THIS
  ``public_app.handler`` entrypoint (the detailed least-privilege IAM + API Gateway throttle /
  usage plan are task 7.1, not here);
- slug → ``tenant_id`` resolution is wired into :func:`_dispatch_public`: the Task-1.2
  ``domain/tenant_directory`` resolver, injected (task 1.4) with the concrete
  ``repository/slug_marker_store`` ``S3SlugMarkerStore`` — the ``_slugs/{slug}`` bucket-marker
  reverse reader resolved by OQ4 (a scan-free ``get_object``, NOT a config/env scan) — behind the
  UNCHANGED ``TenantSlugReader`` Protocol, so a forged/unknown slug becomes a non-probeable 404 and
  an allow-listed slug carries its canonical ``tenant_id`` forward (verify-before-trust, R2).

Task 3.1 (this change) LANDS the public READ path ``GET …/field-config`` — the public ``GET {slug}``
of the public-pages platform (spec 14, R5.1–R5.3 / R10.1 / R10.5, design D-SLUG / C2). It resolves
the slug from the ``_slugs/{slug}`` marker BODY (a scan-free O(1) ``get_object`` — never the h-dcn
table-scan anti-pattern; routing decided from ``owner_plane``/``kind`` in the body, never by parsing
the slug) to a published SAM ``application_form`` tenant, then returns the applicant schema via the
REUSED :meth:`ApplicationService.get_public_field_config` — the EXPLICIT whitelist (R5.2 / SEC-1),
with the service's readiness/publication gate mapped to a non-probeable 404 so "unpublished" is
INDISTINGUISHABLE from "unknown" (SEC-5, enumeration-safe). A missing / cross-plane / cross-kind
marker is the SAME non-probeable 404 (Property 2/3/5).

Task 4.1 (this change) LANDS the public WRITE path ``POST …/applications`` — the public ``POST {slug}``
submit (spec 14, R5.5 / R3.2 / R10.2 / R10.3 / R10.9 / R10.10, design C2 / SEC-3). It resolves the
slug from the SAME ``_slugs/{slug}`` marker BODY the GET read uses (:func:`_resolve_sam_form_tenant` —
a scan-free O(1) ``get_object``, routed from ``owner_plane``/``kind``, never by parsing the slug and
NEVER from a client value) to a published SAM ``application_form`` tenant, then writes the applicant
record via the REUSED :meth:`ApplicationService.create_application` SCOPED to that marker-resolved
``tenant_id`` (SEC-3: cross-tenant write safety — the service strips any forged body ``tenant_id``
and stamps the resolved one, so the record lands in the MEMBERS module's own ``tenant_id``-partitioned
store). A missing / cross-plane / cross-kind marker — OR the service's readiness refusal — is the
SAME non-probeable 404 the GET path returns (SEC-5, enumeration-safe), with NO write performed. The
deep input validation (SEC-2), applicant-PII minimization (SEC-9) and stored-XSS neutralization
(SEC-10) are later sub-tasks (4.2–4.5); this sub-task is the happy-path wiring + SEC-3 tenant-from-marker.

An UNRECOGNISED path — OR a
recognised path whose slug does NOT resolve — returns **404** ``errors.api.notFound``, deliberately
indistinguishable from "no such endpoint" so neither the surface nor the tenant allow-list can be
probed (R2.3/R1a.4). The abuse guards (honeypot / payload cap / malformed body) return **400**
``errors.api.badRequest`` BEFORE any delegation (R10.2/R1a.4).
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping
from typing import Any

from sam.members.domain._membership_errors import MemberValidationError
from sam.members.domain.application_readiness import ApplicationNotAvailable
from sam.members.domain.application_service import ApplicationService
from sam.members.domain.tenant_directory import TenantDirectory
from sam.members.handler._http import (
    ParsedRequest,
    _error,
    _field_errors_array,  # SEC-2 (task 4.2): shapes the deliberate validation 422 per-field array
    _parse_request,
    _response,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader
from sam.members.repository.slug_marker_store import S3SlugMarkerStore, SlugMarker

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

__all__ = [
    "HONEYPOT_FIELD",
    "MAX_PAYLOAD_BYTES",
    "PUBLIC_OWNER_PLANE",
    "PUBLIC_PAGE_KIND",
    "PublicAbuseRejected",
    "PublicRouteNotImplemented",
    "PublicTenantNotFound",
    "handler",
]


# ── Owner-plane / kind the public read path serves (D-SLUG, Property 2 / R4.2) ────────

#: The ONLY ``owner_plane`` the SAM public read path serves. Ownership/kind/tenant are decided by
#: READING the ``_slugs/{slug}`` marker BODY (Property 2, D-SLUG) — never by parsing the slug
#: string — so a slug whose marker names a DIFFERENT plane (a future Flask-owned landing page, say)
#: resolved at the SAM edge is a clean, non-probeable MISMATCH (treated identically to a missing
#: slug, R5.3/SEC-5), not a leak and not a cross-plane read (steering 35 rule 5a / Property 3).
PUBLIC_OWNER_PLANE = "sam"

#: The ONLY ``kind`` the public ``GET {slug}`` field-config read serves today — the application
#: form (C2, the first producer). ``kind`` is an OPEN set platform-wide (``webshop`` /
#: ``event_calendar`` / … are expected future kinds, R3.5), but THIS read path returns the
#: applicant schema, so a marker of any OTHER kind resolved here is a non-match (non-probeable
#: 404), exactly like a cross-plane marker — never a wrong-kind body served as a form schema.
PUBLIC_PAGE_KIND = "application_form"


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

#: The env var carrying the per-env PUBLIC-PAGES APEX the published application form is served on
#: (task 7.1 / R5.1). The published artifact for a slug lives at ``https://{slug}.{apex}`` — the
#: CloudFront public-pages distribution maps ``{slug}.{apex}`` to the served ``{slug}/`` prefix
#: (``application_publish``/``public_page_artifact_store`` write the canonical ``{slug}.jabaki.nl``
#: URL). CORS Option B (R5.1/5.5) admits that form's OWN resolved slug host — computed from the
#: apex HERE, never a hardcode and NEVER a broad ``*.{apex}`` wildcard. The canonical public-pages
#: apex is ``jabaki.nl`` (the SAME value ``application_publish`` bakes into the canonical URL), so
#: that is the resolved default; a stack/test may override it per env via this var. An explicitly
#: BLANK override resolves to NO apex, so the slug-host union member is simply SKIPPED (CORS stays
#: fail-closed — a missing apex never raises and never widens the allow-list, it only declines to
#: add the one slug-host member).
APEX_ENV = "PUBLIC_FORM_APEX"

#: The canonical public-pages apex the published form is served on when :data:`APEX_ENV` is unset.
#: Mirrors the apex ``application_publish`` already bakes into the canonical ``{slug}.jabaki.nl``
#: URL, so the CORS slug-host and the served host cannot drift.
_DEFAULT_FORM_APEX = "jabaki.nl"


class _PublicResult:
    """A completed public read/write result + the RESOLVED tenant (for the 200's per-tenant CORS).

    :func:`_dispatch_public` returns this on a success so :func:`handler` can both shape the
    ``{data}`` body AND apply the resolved tenant's ``application_embed_origins`` CORS allow-list
    (task 5.3) to the 200 — exactly as the recognised-route 501 already does via
    :attr:`PublicRouteNotImplemented.tenant_id`. The tenant is the slug-resolved, verified one
    (verify-before-trust) — never a client value.
    """

    __slots__ = ("data", "tenant_id", "resolved_slug")

    def __init__(
        self,
        data: Any,
        *,
        tenant_id: str | None = None,
        resolved_slug: str | None = None,
    ):
        self.data = data
        self.tenant_id = tenant_id
        # The slug the route resolved to this tenant for THIS request (CORS Option B, task 7.1) —
        # so the 200 admits the form's OWN host `https://{resolved_slug}.{apex}`.
        self.resolved_slug = resolved_slug


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

    It carries the RESOLVED ``tenant_id`` (the slug already resolved to an allow-listed tenant
    before this was raised) so :func:`handler` can apply that tenant's per-tenant embed-origin
    CORS allow-list (task 5.3) to the 501 response — the recognised route's CORS already honours
    the tenant's ``application_embed_origins`` even while the service behind it is pending.
    """

    def __init__(
        self,
        message: str = "",
        *,
        tenant_id: str | None = None,
        resolved_slug: str | None = None,
    ):
        super().__init__(message)
        self.tenant_id = tenant_id
        # The slug the route resolved to this tenant (CORS Option B, task 7.1) so even the 501
        # honours the form's OWN slug host, consistent with the 200.
        self.resolved_slug = resolved_slug


# ── CORS (R10.3) — restrict the one Access-Control-Allow-Origin header ────────────────


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
    remainder = path[len(_PUBLIC_PREFIX) :] if path.startswith(_PUBLIC_PREFIX) else ""
    # remainder == "{slug}/{action}"; the slug is everything before the last "/".
    slug, _, _action = remainder.rpartition("/")
    return slug


# ── Delegation seam: slug→tenant wired here (task 1.3); service calls pending (Phase 2 / 4) ──


def _tenant_directory() -> TenantDirectory:
    """Build the slug→``tenant_id`` resolver wired to the SAM-plane concrete reader (task 1.4).

    Injects the concrete :class:`~sam.members.repository.slug_marker_store.S3SlugMarkerStore`
    (the ``_slugs/{slug}`` bucket-marker reverse reader resolved by OQ4 — a scan-free
    ``get_object`` on the shared public-pages bucket) into the storage-agnostic Task-1.2
    :class:`TenantDirectory`. The marker store satisfies the UNCHANGED
    :class:`~sam.members.domain.tenant_directory.TenantSlugReader` Protocol by duck-typing
    (``resolve_slug(slug) -> str | None``), so this is a localized swap of the backing reader
    behind the seam (design D5/C5) — the resolver and the edge handler are UNCHANGED in logic
    and verify-before-trust / non-probeable 404 behaviour is preserved (R7.1/R7.2).

    Task 1.4 replaces the former ``EnvTenantSlugReader`` (the thin ``PUBLIC_TENANT_SLUG_MAP``
    env projection) IN PLACE: the reverse-lookup MECHANISM is now the bucket marker, not a
    config/env scan. Task 7.1 then REMOVED ``PUBLIC_TENANT_SLUG_MAP`` from
    ``template.yaml``/``samconfig.toml`` entirely (swap first, delete second) — the slug is
    DATA on ``config#fields`` + the ``_slugs/{slug}`` marker, so no param/env var backs it.

    Constructed per request — ``S3SlugMarkerStore`` resolves its S3 client + bucket LAZILY +
    fail-fast from ``LANDING_PAGES_BUCKET`` on first use, so import touches no AWS and a test can
    inject a fake store by monkeypatching :data:`S3SlugMarkerStore` on this module (mirroring the
    ``MembersProjectionReader`` injection seam). This is the single place the public edge binds
    the resolver to its backing store; swapping the store again is a change behind the reader
    seam only, never a ripple through the resolver or its callers.
    """
    return TenantDirectory(S3SlugMarkerStore())


def _application_service() -> ApplicationService:
    """Build the public-intake :class:`ApplicationService` wired to the SAM-plane concretes (task 3.1).

    The single composition root for the public READ path (mirroring :func:`_tenant_directory`).
    It wires the public-intake facade over:

    - the production :class:`~sam.members.domain.membership_service.MembershipService` (via
      ``app._get_membership_service``), the ONE authoritative engine whose
      ``get_public_field_config`` applies the EXPLICIT applicant whitelist (R5.2 / SEC-1) — reused,
      never re-derived here; and
    - the DynamoDB-backed :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`
      as the ``mail_readiness_provider`` (it satisfies the
      :class:`~sam.members.domain.application_readiness.MailReadinessProvider` Protocol by
      duck-typing — the SAME reader the publish/send path uses), so the readiness/publication gate
      (D15/R5.4) agrees across the form read, the submit, and the eventual send.

    Imported lazily inside the function (not at module top) so importing this edge touches no AWS
    and the auth-only tests stay offline — the repository/engine resolve their real table lazily +
    fail-fast on first use. Tests inject a fake by monkeypatching :data:`ApplicationService` (or
    the names this constructs) on this module, mirroring the other injection seams here.
    """
    from sam.members.handler.app import _get_membership_service

    return ApplicationService(
        _get_membership_service(),
        mail_readiness_provider=MembersProjectionReader(),
    )


def _resolve_sam_form_tenant(slug: str) -> str | None:
    """Resolve ``slug`` to its owning ``tenant_id`` IFF it is a published SAM application-form page.

    The task-3.1 public-read resolution (D-SLUG / Property 2 / Property 4): a SINGLE scan-free,
    O(1) keyed ``get_object`` on the ``_slugs/{slug}`` marker via
    :meth:`~sam.members.repository.slug_marker_store.S3SlugMarkerStore.resolve` — NEVER a
    ``.scan()`` (the h-dcn anti-pattern the design explicitly rejects). Ownership/kind/tenant are
    decided by READING the marker BODY, never by parsing the slug string.

    Returns the ``tenant_id`` ONLY when the marker exists AND its body names THIS plane+kind
    (``owner_plane == sam`` AND ``kind == application_form``) with a non-blank ``tenant_id``.
    Every other case — a missing marker (slug never claimed / unpublished), a cross-plane marker
    (a Flask-owned landing page), a cross-kind marker (a webshop/event page), or a malformed body
    with no usable tenant — returns ``None`` so the edge raises the ONE non-probeable 404 (R5.3 /
    SEC-5, indistinguishable from "no such slug"; Property 3 — the SAM edge never reads another
    plane's data). A blank/reserved slug is handled inside ``resolve`` (returns ``None`` without
    touching S3).
    """
    marker: SlugMarker | None = S3SlugMarkerStore().resolve(slug)
    if marker is None:
        return None
    # Route from the BODY (Property 2): a cross-plane / cross-kind marker is a clean non-match,
    # never a cross-plane read and never served as this kind's schema.
    if marker.owner_plane != PUBLIC_OWNER_PLANE or marker.kind != PUBLIC_PAGE_KIND:
        return None
    tenant_id = marker.tenant_id
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        return None
    return tenant_id.strip()


# ── SEC-1 fail-closed edge guard: no raw record shape may cross the public boundary ──


#: Raw-storage-shape keys that MUST NEVER appear in a public response (steering 39 / SEC-1). The
#: resolved-view contract keeps the physical two-map/dotted-key layout (``fields`` vs ``overrides``
#: vs ``fixed_overrides``, dotted ``{group}.{key}``) INSIDE the repository; a public response
#: carries only the RESOLVED view. The authority (``get_public_field_config``) already builds that
#: resolved view by constructing an explicit, named key set — it never copies the raw item — so
#: nothing raw can ride along by construction. This set names the exact keys the access guard
#: (``scripts/check_sam_service_access.py``) also forbids, so the two enforcement points agree.
_RAW_SHAPE_KEYS = frozenset({"field_overlay", "overrides", "fixed_overrides"})


def _assert_fail_closed_public_schema(schema: Any) -> Any:
    """SEC-1 defense-in-depth: assert the resolved public schema leaks NO raw/physical shape.

    The applicant schema is an ALLOWLIST authored upstream in
    :meth:`MembershipService.get_public_field_config`: a field is exposed ONLY when the tenant
    explicitly marked it ``application_visible`` (default ``False`` → an unknown / newly-added
    field defaults HIDDEN, fail-closed), and each exposed field is projected into an EXPLICIT,
    named key set (``key``/``type``/``label``/``functional_group``/``order``/``required``/
    ``show_when``/``options``/``format``) — never a copy of the raw item, so no secret VALUE and no
    physical-layout key can ride along. A secret can therefore surface at most as a boolean
    existence flag, never its value.

    This guard is the LAST trust boundary (the public edge) re-checking that invariant rather than
    blindly trusting the upstream view: if a future change to the authority ever regressed to
    leaking a raw-shape key (``field_overlay`` / ``overrides`` / ``fixed_overrides``) or a dotted
    ``{group}.{key}`` key — at the schema top level OR inside any field — this FAILS CLOSED by
    raising, so the regression surfaces as a bodied 500 server-side instead of silently
    over-exposing tenant data on an unauthenticated endpoint. It mirrors the committed access guard
    (``scripts/check_sam_service_access.py``) and the boundary test, moving the same rule to
    runtime on the one surface with no authentication in front of it.

    Returns ``schema`` unchanged on success (so it is a transparent pass-through at the call site).
    """
    if isinstance(schema, Mapping):
        _reject_raw_shape_keys(schema.keys())
        for field in schema.get("fields") or ():
            if isinstance(field, Mapping):
                _reject_raw_shape_keys(field.keys())
    return schema


def _reject_raw_shape_keys(keys: Any) -> None:
    """Raise if any key is a forbidden raw-shape key or a dotted ``{group}.{key}`` key (SEC-1)."""
    for key in keys:
        if not isinstance(key, str):
            continue
        if key in _RAW_SHAPE_KEYS or "." in key:
            # A raw-shape / dotted physical key reached the public boundary — fail closed. The
            # message is server-log-only (the edge maps the raised error to a neutral bodied 500,
            # never echoing the offending key to the unauthenticated caller).
            raise ValueError(
                f"public schema carried a forbidden raw-shape key {key!r} (SEC-1 / steering 39)"
            )


# ── Submit-request sourcing (task 4.1) — the NON-TRUSTED values the submit write needs ──
#
# The POST submit carries three non-field inputs the write needs beside the resolved tenant and
# the applicant ``body``. NONE of them confers tenant or identity (steering 39: the tenant comes
# ONLY from the verified marker, never the request body); they are read from the request in a
# non-trusted way and the authoritative service owns their meaning:
#
#   * ``session_key`` — a per-submission idempotency/de-dup value (R3a). The FIRST submit of a
#     session CREATES; a same-key resend (a correction, a double-click) UPDATES that same record.
#     A client that supplies one gets resend-coalescing; one that supplies none gets a fresh,
#     server-minted uuid4 (so every submit lands, never silently coalesced to another's record).
#   * ``locale`` — the applicant's preferred locale; the service owns normalization + fallback.
#   * ``consent`` — the applicant's affirmative acceptance of the tenant's versioned notice; the
#     service REQUIRES it (a submit without it is a hard reject) and stamps a server-authoritative
#     consent record (version/timestamp/locale resolved server-side, never client-trusted).

#: The body keys the submit reads its session value / locale from. Accept both the camelCase the
#: SPA form posts and the snake_case the domain uses, so the edge is tolerant of either client.
_SESSION_KEY_BODY_KEYS = ("session_key", "sessionKey", "session_id", "sessionId")
_LOCALE_BODY_KEYS = ("locale", "lang")


def _submission_session_key(body: Mapping[str, Any]) -> str:
    """The per-submission de-dup ``session_key`` for ``create_application`` (R3a), NON-TRUSTED.

    Read from the request body (one of :data:`_SESSION_KEY_BODY_KEYS`) so a resend within one
    fill-in session coalesces onto the SAME record; a server-minted ``uuid4`` is used when the
    client sends none (a fresh session), so a submission is NEVER silently lost or coalesced onto
    an unrelated record. The value is a de-dup token ONLY — it carries no tenant and no identity
    (the tenant is the verified, marker-resolved one; the ``member_id`` is server-minted), so
    trusting it for de-dup grants a caller no cross-tenant or cross-record reach.
    """
    if isinstance(body, Mapping):
        for key in _SESSION_KEY_BODY_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return uuid.uuid4().hex


def _submission_locale(body: Mapping[str, Any]) -> str | None:
    """The applicant's requested locale off the body, or ``None`` (the service owns fallback)."""
    if isinstance(body, Mapping):
        for key in _LOCALE_BODY_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _submission_consent(body: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The applicant's consent object off the body, or ``None`` (the service REQUIRES/validates it).

    Passed through verbatim for the service to gate on (affirmative consent is mandatory — a
    submit without it is rejected) and to stamp server-authoritatively; the edge neither trusts
    nor interprets its contents.
    """
    if isinstance(body, Mapping):
        consent = body.get("consent")
        if isinstance(consent, Mapping):
            return consent
    return None


def _public_field_key(engine_key: Any) -> str:
    """Map an engine error key to the BARE key the published form names its control by.

    The engine keys errors by physical identity (``personal.last_name``, ``membership.membership_type``,
    ``overlay.region``); the public field config emits the bare ``key`` (``last_name`` ...) and the
    form's controls carry that name. Steering 39: no dotted ``{group}.{key}`` crosses the public
    boundary. The bare key IS the last dotted segment (the group / ``overlay`` prefix is the
    physical placement), so this is derived from the key alone: no extra read, no boto3. A key
    with no dot (``consent``) is returned unchanged. For an unrecognised shape the last segment is
    still used, so a message is never dropped.
    """
    key = str(engine_key)
    return key.rsplit(".", 1)[-1] or key


def _public_field_errors_array(errors: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The shared per-field ``errors`` array with ``field`` rewritten to the bare public key.

    Entry shape is unchanged (``{field, code, detail, params?}``). When two engine keys collapse
    to the same bare key, the FIRST entry wins (no duplicates).
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in _field_errors_array(errors):
        bare = _public_field_key(entry.get("field"))
        if bare in seen:
            continue
        seen.add(bare)
        out.append({**entry, "field": bare})
    return out


def _dispatch_public(
    request: ParsedRequest, resolved: dict[str, str] | None = None
) -> Any:
    """Delegate a recognised public route to the domain — resolving the slug from the marker first.

    This is the single downward seam from the thin public edge to the application domain.

    **``GET …/field-config`` — the public read path (task 3.1, R5.1–R5.3 / R10.1 / R10.5).** The
    slug is resolved from the ``_slugs/{slug}`` marker BODY (:func:`_resolve_sam_form_tenant` — an
    O(1) keyed ``get_object``, NEVER a scan, Property 4) to a published SAM ``application_form``
    tenant. A missing / cross-plane / cross-kind marker → :class:`PublicTenantNotFound` (the
    non-probeable 404, Property 2/3/5). On a match, the applicant schema is returned via the REUSED
    :meth:`ApplicationService.get_public_field_config` — the EXPLICIT whitelist (SEC-1); no field
    list is re-derived here and no raw record shape crosses the boundary (steering 39). The
    service's own readiness/publication gate
    (:class:`~sam.members.domain.application_readiness.ApplicationNotAvailable`) is caught and
    turned into the SAME non-probeable 404 — on the PUBLIC read, "exists but not yet accepting
    applications" must be INDISTINGUISHABLE from "unknown slug" (SEC-5, enumeration-safe), never a
    409 that would reveal the page exists.

    **``POST …/applications`` — the submit write (task 4.1, R5.5 / R3.2 / SEC-3).** The tenant is
    resolved from the SAME marker BODY the GET read uses (:func:`_resolve_sam_form_tenant`) — a
    scan-free O(1) ``get_object`` routed from ``owner_plane``/``kind``, NEVER a value from the
    request body and NEVER a second resolution mechanism. A missing / cross-plane / cross-kind
    marker → :class:`PublicTenantNotFound` (the SAME non-probeable 404 the GET path raises, R5.3 /
    SEC-5, Property 2/3) with NO write performed. On a resolved, published SAM ``application_form``
    tenant the applicant record is written via the REUSED
    :meth:`ApplicationService.create_application`, SCOPED to that marker-resolved ``tenant_id`` —
    the service strips any forged body ``tenant_id`` and stamps the resolved one, so the record
    lands in the MEMBERS module's own ``tenant_id``-partitioned store (steering 39). The service's
    readiness re-check (:class:`~sam.members.domain.application_readiness.ApplicationNotAvailable`)
    is caught and mapped to the SAME non-probeable 404 (SEC-5) — "not accepting applications yet"
    is indistinguishable from "unknown slug", never a 409. The deep input validation (SEC-2),
    applicant-PII minimization (SEC-9) and stored-XSS neutralization (SEC-10) are tasks 4.2–4.5.

    The whole seam runs WITHOUT ever calling ``_authenticate_and_authorize`` (D27) — the public
    edge never authenticates.
    """
    slug = _slug_from_path(request)
    # Per-request holder (a LOCAL dict owned by `handler`, never module state — Lambda reuse): once
    # the slug resolves to a tenant it is recorded here BEFORE the service runs, so the handler's
    # 422/500 branches can admit the form's OWN slug host in CORS (Round 3, R9.1) even though the
    # service raised. Left empty when resolution fails → those branches add nothing (fail-closed).
    if resolved is None:
        resolved = {}

    # ── GET …/field-config: the public read path (task 3.1) ──────────────────────────
    if request.method == "GET":
        tenant_id = _resolve_sam_form_tenant(slug)
        if tenant_id is None:
            # No marker / cross-plane / cross-kind → non-probeable 404 (R5.3, Property 2/3/5).
            raise PublicTenantNotFound(slug)
        resolved.update(tenant_id=tenant_id, resolved_slug=slug)
        try:
            # REUSE the one filter authority — the EXPLICIT applicant whitelist (R5.2 / SEC-1).
            # The authority is the allowlist (``application_visible`` gate, default HIDDEN) and
            # builds an explicit named-key resolved view; this edge re-asserts fail-closed that no
            # raw/physical shape leaked before it crosses the unauthenticated boundary (SEC-1 /
            # steering 39) — a regression there fails closed as a bodied 500, never over-exposure.
            schema = _assert_fail_closed_public_schema(
                _application_service().get_public_field_config(tenant_id)
            )
            # Carry the resolved tenant AND the resolved slug so the 200's CORS honours the
            # tenant's embed origins (task 5.3) AND the form's OWN slug host (CORS Option B,
            # task 7.1) — the published `{slug}.{apex}` host can read its own field-config.
            return _PublicResult(schema, tenant_id=tenant_id, resolved_slug=slug)
        except ApplicationNotAvailable as exc:
            # Publication gate (R5.3 / SEC-5): a resolved-but-not-send-ready tenant is NOT
            # accepting applications yet — on the PUBLIC read this must be INDISTINGUISHABLE from
            # an unknown slug, so map the readiness refusal to the SAME non-probeable 404, never a
            # 409 that would confirm the page exists (enumeration-safe). The neutral server-side
            # reason is logged; the client sees only the uniform not-found.
            #
            # SEC-5 timing-insensitivity reasoning. The unpublished path does ONE extra bounded
            # step the unknown path does not — the readiness provider lookup inside
            # ``get_public_field_config`` (a single O(1) keyed projection read), which runs BEFORE
            # the schema is resolved and raises here. The unknown / cross-plane / cross-kind paths
            # stop one step earlier (after the single ``_slugs/{slug}`` marker ``resolve``). Both
            # paths are therefore a small, constant number of O(1) keyed reads against the SAME
            # backing stores (no ``.scan()``, Property 4 / SEC-6) — the only difference is at most
            # one additional keyed read on the "exists" branch. That is below the practically
            # observable threshold over the network (the Lambda cold/warm variance and API-Gateway
            # jitter dwarf a single keyed read), so there is no usable timing ORACLE distinguishing
            # "exists but unpublished" from "does not exist". Full constant-time is not required
            # (design SEC-5: "no *practically observable* oracle"); the status + body are made
            # BYTE-IDENTICAL (both map to the one ``_error(404, …notFound)`` below), which is the
            # control that actually closes the enumeration channel.
            logger.info(
                "Public field-config for slug '%s' resolved to a tenant that is not accepting "
                "applications yet; returning the non-probeable 404 (%s)",
                slug,
                exc.code,
            )
            raise PublicTenantNotFound(slug) from exc

    # ── POST …/applications: the submit write (task 4.1, R5.5 / R3.2 / SEC-3) ────────
    # SEC-3 (cross-tenant write safety): the tenant is resolved ONLY from the marker BODY — the
    # SAME resolve-by-body the GET read uses (:func:`_resolve_sam_form_tenant`), NOT a second
    # resolution mechanism and NEVER a value from the request body. A missing / cross-plane
    # (``owner_plane != sam``) / cross-kind (``kind != application_form``) marker resolves to
    # ``None`` → the SAME non-probeable 404 the GET path raises (R5.3 / SEC-5, Property 2/3) with
    # NO write performed, so a foreign/cross-plane slug can never reach an arbitrary partition and
    # the surface cannot be probed.
    tenant_id = _resolve_sam_form_tenant(slug)
    if tenant_id is None:
        raise PublicTenantNotFound(slug)
    resolved.update(tenant_id=tenant_id, resolved_slug=slug)

    # The write is SCOPED to the marker-resolved ``tenant_id`` (steering 39: the tenant comes from
    # the verified marker, never the request body) — the service strips any body ``tenant_id`` and
    # stamps this one authoritatively, so the applicant record lands in the MEMBERS module's own
    # ``tenant_id``-partitioned store via its own Lambda/repository. ``session_key`` is a
    # per-submission idempotency/de-dup value: the FIRST submit of a session creates, a same-key
    # resend UPDATES that record (R3a). It is sourced from the request in a NON-TRUSTED way
    # (:func:`_submission_session_key`) — it confers no tenant and no identity — falling back to a
    # server-minted uuid4 when the client sends none. ``locale`` / ``consent`` ride through from
    # the body (the service owns their authoritative normalization / affirmative-consent gate).
    body = request.body if isinstance(request.body, Mapping) else {}
    try:
        record = _application_service().create_application(
            tenant_id,
            body,
            _submission_session_key(body),
            locale=_submission_locale(body),
            consent=_submission_consent(body),
        )
    except ApplicationNotAvailable as exc:
        # Readiness gate re-check (R9.4 defense-in-depth): a resolved-but-not-send-ready tenant
        # refuses the submit with NO record written. On the PUBLIC surface this must be
        # INDISTINGUISHABLE from an unknown slug (SEC-5, enumeration-safe) — map it to the SAME
        # non-probeable 404 the GET read uses, never a 409 that would confirm the page exists.
        logger.info(
            "Public submit for slug '%s' resolved to a tenant not accepting applications yet; "
            "returning the non-probeable 404 (%s)",
            slug,
            exc.code,
        )
        raise PublicTenantNotFound(slug) from exc

    # Carry the resolved tenant AND the resolved slug so the 200's CORS honours the tenant's
    # authored embed origins (task 5.3) AND the form's OWN slug host (CORS Option B, task 7.1) —
    # the published `{slug}.{apex}` host can read its own submit response.
    return _PublicResult(record, tenant_id=tenant_id, resolved_slug=slug)


# ── Lambda entry point (the public, token-less edge — D27) ────────────────────────────


def _is_public_preflight_route(request: ParsedRequest) -> bool:
    """True for an ``OPTIONS`` on one of the two public route shapes (slug-agnostic)."""
    if request.method != "OPTIONS":
        return False
    path = (request.path or "").rstrip("/")
    return path.startswith(_PUBLIC_PREFIX) and path.endswith(
        ("/field-config", "/applications")
    )


def _preflight_response(request: ParsedRequest) -> dict:
    """Answer a CORS preflight per origin (Round 4, R12).

    API Gateway's static ``Cors`` mock cannot echo the per-slug host, so ``OPTIONS`` is routed to
    this Lambda and decided by the SAME :func:`_apply_cors_origin` union (baseline ∪ tenant embed
    origins ∪ the resolved slug host) as the real request. Fail-closed: an unresolved slug, an
    unknown route, a foreign origin, or ANY error during resolution yields a 204 with NO
    ``Access-Control-Allow-Origin`` (never ``*``) and no body detail.
    """
    tenant_id: str | None = None
    resolved_slug: str | None = None
    if _is_public_preflight_route(request):
        slug = _slug_from_path(request)
        try:
            tenant_id = _resolve_sam_form_tenant(slug)
            if tenant_id is not None:
                resolved_slug = slug
        except Exception:
            # No PII / stack in the response; resolution failure simply means no ACAO.
            logger.warning(
                "Public preflight slug resolution failed; answering without ACAO"
            )
            tenant_id = None
            resolved_slug = None
    # Built directly (not via the shared envelope) so no default ``*`` ACAO exists to leak.
    response: dict = {
        "statusCode": 204,
        "headers": {
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        },
        "body": "",
    }
    try:
        response = _apply_cors_origin(
            response, request, tenant_id=tenant_id, resolved_slug=resolved_slug
        )
    except Exception:
        logger.warning("Public preflight CORS decision failed; answering without ACAO")
        response["headers"].pop("Access-Control-Allow-Origin", None)
    response["headers"]["Vary"] = (
        "Origin"  # _apply_cors_origin may have appended a duplicate
    )
    logger.info(
        "Public preflight answered (resolved=%s, allowed=%s)",
        tenant_id is not None,
        "Access-Control-Allow-Origin" in response["headers"],
    )
    return response


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
      * a submit that fails server-side per-field validation (SEC-2, task 4.2 — bad email, an
        out-of-subset enum, a missing required field, missing affirmative consent) → **422**
        ``errors.validation.failed`` with the RFC 9457 per-field ``errors`` array, raised BEFORE
        any write so NO record lands;
      * an unanticipated error → a BODIED **500** ``errors.api.serverError`` (never an empty 502).

    Every response — success AND error — carries the shared ``_http`` envelope (``success`` flag
    + JSON body + ``Decimal`` serialization) with its ``Access-Control-Allow-Origin`` restricted
    to the configured form origin(s) (R10.3) via :func:`_apply_cors_origin`.
    """
    request = _parse_request(event)

    # 0) CORS preflight (Round 4): decided per origin BEFORE the body-based abuse guards (a
    #    preflight carries no body) and before the public-route check (OPTIONS is not a route).
    if request.method == "OPTIONS":
        return _preflight_response(request)

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
    resolved: dict[str, str] = {}
    try:
        result = _dispatch_public(request, resolved)
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
    except PublicRouteNotImplemented as exc:
        logger.info(
            "Public intake route '%s %s' recognised but not implemented yet",
            request.method,
            request.path,
        )
        # The slug resolved to an allow-listed tenant → honour that tenant's embed-origin CORS
        # allow-list on the 501 (task 5.3), so a tenant's own embedding site can read the body.
        return _apply_cors_origin(
            _error(501, "Not implemented", code="errors.api.notImplemented"),
            request,
            tenant_id=exc.tenant_id,
            resolved_slug=exc.resolved_slug,
        )
    except MemberValidationError as exc:
        # SEC-2 (task 4.2): the submit failed the authoritative server-side per-field validation
        # that `ApplicationService.create_application` runs BEFORE the write (email-is-email,
        # enum within the published application subset, required present, and the GDPR consent
        # gate — all collected into ONE `MemberValidationError` by the membership engine, which
        # raises it BEFORE `save_member`, so NO record is written and NOTHING is enqueued on any
        # validation failure). This is a DELIBERATELY-raised, caller-safe rejection (not a caught
        # internal exception), so — exactly like the authenticated edge (`app.handler`) — it is
        # mapped to a 422 carrying the per-field errors as the RFC 9457 `errors` array the SPA
        # localizes, NOT swallowed into the generic 500 below. The edge adds NO second, drifting
        # validator: the one authoritative engine owns every rule; this only shapes its refusal.
        logger.info(
            "Public submit for '%s %s' rejected by server-side validation (%d field error(s)); "
            "no record written",
            request.method,
            request.path,
            len(exc.errors),
        )
        return _apply_cors_origin(
            _error(
                422,
                "Validation failed",
                code="errors.validation.failed",
                errors=_public_field_errors_array(exc.errors),
            ),
            request,
            tenant_id=resolved.get("tenant_id"),
            resolved_slug=resolved.get("resolved_slug"),
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
            _error(500, "Internal error", code="errors.api.serverError"),
            request,
            tenant_id=resolved.get("tenant_id"),
            resolved_slug=resolved.get("resolved_slug"),
        )

    # A completed read/write result → 200 with the shared envelope. The GET field-config read
    # (task 3.1) returns a `_PublicResult` carrying the slug-resolved tenant, so the 200 honours
    # THAT tenant's embed-origin CORS allow-list (task 5.3) exactly as the recognised-route 501
    # does. (The 202 for an accepted submission is shaped by the create_application path in
    # Task 4, which returns the AcceptedResult the service layer marks.)
    if isinstance(result, _PublicResult):
        return _apply_cors_origin(
            _response(200, {"data": result.data}),
            request,
            tenant_id=result.tenant_id,
            resolved_slug=result.resolved_slug,
        )
    return _apply_cors_origin(_response(200, {"data": result}), request)
