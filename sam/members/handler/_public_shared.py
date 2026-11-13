"""Constants, result and exception types shared by the public edge.
Part of public_app (task 8).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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

    __slots__ = ("data", "resolved_slug", "tenant_id")

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
