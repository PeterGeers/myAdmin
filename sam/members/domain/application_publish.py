"""
Spec 12 Task 2.1 — the application-form **publish service** (design §C4 / R5).

The EXPLICIT publish action (OQ1 = option 1): a ``members:admin``-gated, readiness-gated
``POST /members/application-form/publish`` renders the tenant's current ``config#fields`` /
``config#mail`` into a static, slug-addressed artifact and (task 2.2) writes it to the shared
public-pages bucket + invalidates CloudFront. Saving the draft NEVER republishes — editing and
going-live are distinct steps (R5.1a); the in-browser preview covers "see before commit".

Scaffold vs live (task 2.1 vs 2.2)
----------------------------------
This module owns the parts of publish that are **account-agnostic and testable NOW** (task 2.1):

- the **readiness gate** (R5.4 / spec 10 D15 / spec 11 R6): a form may publish only when it has
  a stored **slug** (R4) AND a **certified sender** (``mail_certified`` + a projected
  ``mail_domain``) AND **≥1 on-form field** (a resolved field with ``application_visible``). Any
  missing precondition REFUSES with a clear, ``members:admin``-facing envelope
  (:class:`PublishNotReady`) and NO write is attempted — never a partial/broken artifact (R5.4);
- the **render step** (spec 14 Task 2.2 — WIRED): once ready, the service RENDERS the
  slug-addressed ``{slug}/index.html`` artifact through the SHARED, plane-neutral page shell
  (:func:`sam.members.domain.application_form_render.render_application_form_page` →
  :func:`sam.shared.page_shell.render_page`), composing the applicant body from
  ``get_public_field_config`` (the single filter authority, reused) and the CSS from
  ``LandingPageStyles`` (the single CSS source) — "the SAM form renders its shell via
  ``page_shell``" (R7.1);
- the **slug-claim step** (spec 14 Task 8.1 — WIRED): once ready and rendered, the service CLAIMS
  the form's slug via the shared ``_slugs/{slug}`` marker store (Task 1) for the owning tenant,
  gated by format/reserved (:func:`sam.members.domain.form_slug.validate_slug_format`) then the
  SEC-4 prefix-ownership rule
  (:func:`sam.members.domain.form_slug.validate_slug_prefix_ownership`). A same-owner re-publish is
  IDEMPOTENT (the claim succeeds silently for a matching body); a FOREIGN-owned slug is NEVER
  clobbered (:class:`SlugTaken` → the caller-safe :class:`PublishSlugConflict`, R4.4). This uses
  only the control-plane marker (an injectable, account-agnostic store), so it runs locally /
  dry-run with an in-memory fake — no real AWS;
- the **publish seam**: the LIVE write/invalidation pipeline (the S3 ``{slug}/index.html`` +
  ``form.json`` write and the CloudFront invalidation, R5.1/R5.2/R5.5) is **DORMANT** here —
  spec 14 Task 9 (live), additionally gated on the owner-run hosting migration (task 0.1) cutting
  the bucket over to nonprofit (R6.4). The seam raises :class:`PublishPipelineNotWired` AFTER the
  render AND the slug claim, so a READY tenant renders the artifact and claims its slug (fully
  testable) but the live write cannot fire until the gated task fills it in.

Why admin-facing refusal detail (NOT the neutral public 409)
------------------------------------------------------------
The PUBLIC readiness refusal
(:class:`sam.members.domain.application_readiness.ApplicationNotAvailable`) is deliberately
NEUTRAL — it names no mail-config fact so an applicant cannot probe a tenant's posture. This
publish surface is the OPPOSITE audience: a verified Tenant_Admin publishing their OWN form.
"Show, don't silently block" (R5.4 / spec 11 R6) — the admin MUST be told WHICH precondition is
missing (no slug / no certified sender / no on-form field) so they can fix it. So this carries a
distinct, admin-facing reason; it is never shown on the public edge.

Storage- and tenant-agnostic (steering 35): the service depends only on small seams — a slug
reader, the shared readiness predicate's provider, and the public field-config read — never on
boto3/HTTP/DynamoDB directly. The tenant is always the verified ``tenant_id`` the edge passes in
(verify-before-trust, R2) — never a client value.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from services.dynamodb_client import require_env

from sam.members.domain.application_form_render import render_application_form_page
from sam.members.domain.application_readiness import (
    MailReadinessProvider,
    is_send_ready,
)
from sam.members.domain.form_slug import (
    validate_slug_format,
    validate_slug_prefix_ownership,
)
from sam.members.repository.slug_marker_store import SlugMarker, SlugTaken

_LOG = logging.getLogger(__name__)

__all__ = [
    "FormSlugReader",
    "LookAndFeelSettingsReader",
    "PublicFieldConfigReader",
    "PublicPrefixReader",
    "PublicPageArtifactWriter",
    "SlugMarkerClaimer",
    "PublishNotReady",
    "PublishNotReadyReason",
    "PublishPipelineNotWired",
    "PublishSlugRejected",
    "PublishSlugConflict",
    "FORM_OWNER_PLANE",
    "FORM_OWNER_KIND",
    "FORM_RESOURCE_REF",
    "PUBLIC_API_BASE_ENV_VAR",
    "resolve_public_api_base",
    "ApplicationPublishService",
]

#: The producer identity this service writes into the ``_slugs/{slug}`` marker BODY (design
#: §C1 / D-SLUG). The application form is a ``sam``-plane producer of ``kind="application_form"``;
#: its ``resource_ref`` back-points at the form's own ``config#fields`` row so the owner can find
#: its data without anyone else knowing the shape. Ownership (idempotent re-publish vs clobber
#: backstop) is decided from THESE body fields, never by parsing the slug string (Property 2).
FORM_OWNER_PLANE = "sam"
FORM_OWNER_KIND = "application_form"
FORM_RESOURCE_REF = "config#fields"

#: The publish-time env var carrying the PUBLIC API base URL baked into the served artifact
#: (bugfix ``bugfix-published-form-submit`` Task 3.1 / R2.6). The published static page cannot
#: read ``VITE_*``, so the submit script's ``fetch`` target
#: (``POST {base}/public/members/{slug}/applications``) must be resolved at PUBLISH time and
#: baked in. Resolved with NO silent default via :func:`resolve_public_api_base` — mirroring the
#: ``GOVERNANCE_PROJECTION_TABLE`` fail-fast model (steering 39): a missing value raises at the
#: first real publish rather than silently targeting the wrong backend per environment.
PUBLIC_API_BASE_ENV_VAR = "PUBLIC_API_BASE_URL"


def resolve_public_api_base() -> str:
    """Resolve the PUBLIC API base URL from the publish-time env var (fail-fast, no default).

    Reads :data:`PUBLIC_API_BASE_ENV_VAR` via the projection layer's
    :func:`services.dynamodb_client.require_env` — the SAME fail-fast resource-resolution helper
    the SAM repositories use (``GOVERNANCE_PROJECTION_TABLE`` model, steering 39). There is NO
    default fallback: a missing/blank value raises :class:`services.dynamodb_client.
    DynamoDBConfigError` at the first real publish, so a mis-configured environment fails loudly
    rather than baking the WRONG backend address into every published artifact. No boto3, no
    plane-crossing — the base is DATA resolved from env at publish time.

    Returns:
        The stripped, non-empty public API base URL (e.g. ``https://api.example.com``) the
        submit script's ``fetch`` targets.

    Raises:
        DynamoDBConfigError: the env var is unset or blank (fail-fast — no silent default).
    """
    return require_env(PUBLIC_API_BASE_ENV_VAR)


@runtime_checkable
class FormSlugReader(Protocol):
    """Read the tenant's stored application-form ``slug`` from ``config#fields`` (forward read).

    Mirrors the Phase-1 forward reader
    :meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_form_slug`
    (design C3): tenant → slug via the normal ``tenant_id``-pinned read. Fail-safe: a tenant with
    no stored slug resolves to ``None`` (the form has no public address yet). The service depends
    on this Protocol, never on where the row lives; the SAM-plane concrete is the projection
    reader (it satisfies this by duck-typing), tests pass a static one.
    """

    def get_form_slug(self, tenant_id: str) -> str | None:
        """Return the tenant's application-form ``slug``, or ``None`` when absent/unusable."""
        ...


@runtime_checkable
class PublicPrefixReader(Protocol):
    """Resolve the AUTHENTICATED tenant's public prefix for the SEC-4 prefix-ownership check.

    Mirrors
    :meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_public_prefix`
    (Task 6.3): tenant → its single short ``public_prefix`` read off its OWN projected ``tenant``
    row (SAM reads its own projection, never calls Flask — ADR 0005). Empty-is-valid: a tenant with
    no projected prefix resolves to ``None`` (the prefix rule then refuses a NEW claim, but a
    grandfathered same-owner re-publish is still allowed). The service depends on this Protocol;
    the SAM-plane concrete is the projection reader (duck-typed), tests pass a static one.
    """

    def get_public_prefix(self, tenant_id: str) -> str | None:
        """Return the tenant's ``public_prefix``, or ``None`` when absent/unusable."""
        ...


@runtime_checkable
class SlugMarkerClaimer(Protocol):
    """Claim / resolve the shared ``_slugs/{slug}`` marker — Task 1's cross-plane slug store.

    The one shared surface (:class:`sam.members.repository.slug_marker_store.S3SlugMarkerStore`)
    that lets the application-form producer atomically claim its slug across planes WITHOUT a
    shared DB (design §C1 / D-SLUG). The service depends only on these two methods:

    - :meth:`claim` writes the structured marker BODY under an ``If-None-Match: *`` precondition;
      it is IDEMPOTENT for a same-owner re-publish (a body matching ``owner_plane`` + ``kind`` +
      ``tenant_id`` succeeds silently) and raises :class:`SlugTaken` for a FOREIGN owner (the
      clobber backstop) — ownership decided from the BODY, never the slug string (Property 2);
    - :meth:`resolve` returns the existing :class:`SlugMarker` (or ``None``), used ONLY to decide
      whether this is the tenant's OWN already-live slug (a grandfathered re-publish that must not
      be blocked by the prefix rule).

    The store's S3 client is injectable + lazy, so tests pass an in-memory fake and no AWS is
    touched (the LIVE write this service performs around the claim stays DORMANT — Task 9).
    """

    def claim(self, slug: str, owner: SlugMarker) -> None:
        """Atomically claim ``_slugs/{slug}`` for ``owner`` (idempotent / clobber backstop)."""
        ...

    def resolve(self, slug: str) -> SlugMarker | None:
        """Return the existing marker for ``_slugs/{slug}``, or ``None`` (fail-safe)."""
        ...


@runtime_checkable
class PublicPageArtifactWriter(Protocol):
    """Write the SERVED ``{slug}/`` artifacts + best-effort invalidate — spec 14 Task 9.1.

    The LIVE-write seam the publish flow lifts the dormant write onto (design §C4 / R5.1/R5.5).
    Distinct from :class:`SlugMarkerClaimer`: the claimer writes the ``_slugs/{slug}``
    control-plane marker; THIS writer writes the SERVED content under the ``{slug}/`` prefix
    (``index.html`` + ``form.json``) that CloudFront maps ``{slug}.jabaki.nl`` to, then performs a
    BEST-EFFORT CloudFront invalidation.

    The service depends only on this Protocol — no boto3 in the domain (steering 35/39). The
    SAM-plane concrete is
    :class:`sam.members.repository.public_page_artifact_store.S3PublicPageArtifactStore` (lazy +
    injectable S3/CloudFront clients); tests pass an in-memory fake, so no real AWS is touched.

    The ``put_object`` writes are the AUTHORITATIVE publish; the invalidation inside this call is
    best-effort / NON-FATAL (the known-deferred permission/ARN gap — Task 9.2). The writer must
    therefore SUCCEED (return normally) even when the invalidation cannot fire, so the publish is
    never failed by a cache-freshness optimisation.
    """

    def publish_artifacts(
        self, slug: str, *, index_html: str, form_json: bytes
    ) -> None:
        """Write ``{slug}/index.html`` + ``{slug}/form.json`` then best-effort invalidate."""
        ...


@runtime_checkable
class PublishStateWriter(Protocol):
    """Persist the publish-state metadata onto the tenant's ``config#fields`` row.

    Production: a thin adapter over :meth:`ConfigFieldsCrudService.set_publish_state` (a single
    version-conditional Change-Op that SETs ONLY ``published_version`` / ``published_at``). OPTIONAL
    on :class:`ApplicationPublishService` — absent, publish behaves exactly as before.
    """

    def record_publish(
        self, tenant_id: str, *, published_version: int, published_at: str
    ) -> None:
        """Persist ``published_version`` / ``published_at`` (raises on a failed write)."""
        ...


@runtime_checkable
class PublicFieldConfigReader(Protocol):
    """Resolve the PUBLIC, applicant-facing field schema for a tenant (the on-form field set).

    The SAME single filtering authority the submit edge uses
    (:meth:`MembershipService.get_public_field_config`, reused via
    :class:`sam.members.domain.application_service.ApplicationService` or the service directly):
    it returns the filtered schema whose ``fields`` list contains ONLY the fields the tenant
    marked ``application_visible``. The publish readiness gate counts that list to enforce the
    "≥1 on-form field" precondition — reusing the one filter, never re-deriving it (R5.2, no
    drift). The service depends on this Protocol; tests pass a static one.
    """

    def get_public_field_config(self, tenant_id: str) -> Mapping[str, Any]:
        """Return the filtered public schema; ``fields`` is the ordered on-form field list."""
        ...


@runtime_checkable
class LookAndFeelSettingsReader(Protocol):
    """Resolve the tenant's SAM-owned application-form presentation VALUES — spec 15 §C4 (Req 5.1).

    The Layer-3 wiring seam that feeds the stored ``Look_And_Feel_Settings`` into the Layer-2 CSS
    generator (``render_page_styles``) at publish time, closing the Req 5 defect where changing a
    look-and-feel setting had no observable effect on the published form. Mirrors the existing
    reader seams in this module (:class:`FormSlugReader` / :class:`PublicPrefixReader` /
    :class:`PublicFieldConfigReader`): tenant → resolved VALUES via the normal ``tenant_id``-pinned
    resolved-view read.

    Returns the resolved presentation VALUES only (the ``look_and_feel`` slice on ``config#fields``
    — DD-2), never generated CSS and never a Flask ``landing_page`` value (Req 2.1): CSS is Layer 2's
    job, and the capability reads exclusively SAM-owned state. Fail-safe / absent-is-valid: a tenant
    with no stored slice (or a missing key within it) resolves to an EMPTY mapping, which Layer 2
    turns into its SAM-owned defaults (Req 3.3 / 4.4 / 5.4) — an absent slice is never an error.

    The service depends on this Protocol, never on where the values live; the SAM-plane concrete is
    the projection reader's resolved-view read (it satisfies this by duck-typing), tests pass a
    static one.
    """

    def get_look_and_feel(self, tenant_id: str) -> Mapping[str, Any]:
        """Return the tenant's resolved presentation VALUES, or ``{}`` when absent (defaults)."""
        ...


class PublishNotReadyReason(str, Enum):
    """The TYPED, admin-facing reason a publish was refused (R5.4 "show, don't block").

    Unlike the neutral public 409, the admin publishing their OWN form is told WHICH precondition
    failed so they can fix it (slug / certified sender / on-form field). The edge renders the
    reason into a caller-safe envelope; the frontend Publish button (task 6.2) maps it to the
    right bilingual "why is Publish disabled" hint.
    """

    #: No stored form slug on ``config#fields`` — the admin has not authored a public address yet.
    NO_SLUG = "no_slug"
    #: No usable certified sender (``mail_certified`` + a projected ``mail_domain``).
    NO_CERTIFIED_SENDER = "no_certified_sender"
    #: No field is on the form (no resolved field has ``application_visible`` true).
    NO_ON_FORM_FIELD = "no_on_form_field"


class PublishNotReady(Exception):
    """A publish was REFUSED because the form is not ready to go live (R5.4 / D15 / spec 11 R6).

    Raised by :meth:`ApplicationPublishService.publish` BEFORE any write when a precondition
    (slug / certified sender / ≥1 on-form field) is missing — so NO partial/broken artifact is
    ever emitted. Carries the TYPED :class:`PublishNotReadyReason` (admin-facing: this surface is
    the verified Tenant_Admin publishing their OWN form, not the probeable public edge) so the
    edge can shape a clear envelope and the frontend can explain exactly what to fix.

    The edge maps this to a readiness-refusal status (409 — the request is well-formed and
    authorized, but the resource is not in a publishable state), matching the SAM error-envelope
    convention (steering 37). Deliberately distinct from a 422 validation error (a malformed
    body) and a 404 (unknown route/resource): a 409 "conflict with the current state" is the
    honest shape for "you cannot publish yet".
    """

    #: The stable machine/i18n code the edge renders (admin-facing readiness refusal).
    code: str = "errors.application.publishNotReady"

    def __init__(self, reason: PublishNotReadyReason, message: str | None = None):
        self.reason = reason
        super().__init__(
            message or f"application form not ready to publish: {reason.value}"
        )


class PublishSlugRejected(Exception):
    """A publish was REFUSED because the slug is malformed/reserved or violates the prefix rule.

    Raised by :meth:`ApplicationPublishService.publish` BEFORE the atomic claim when the stored
    slug fails the shared format/reserved contract
    (:func:`sam.members.domain.form_slug.validate_slug_format`) or the SEC-4 prefix-ownership rule
    (:func:`sam.members.domain.form_slug.validate_slug_prefix_ownership`) — so no marker is claimed
    and no artifact is written for an unownable slug. Carries a caller-safe ``detail`` (the
    validator's own no-internals message) the admin-facing edge surfaces on a 422 validation
    envelope (steering 30/37): the slug on config#fields is malformed or sits outside the tenant's
    own prefix namespace, which the admin must fix. Deliberately distinct from
    :class:`PublishNotReady` (a readiness gap) and :class:`PublishSlugConflict` (a foreign owner).
    """

    #: The stable machine/i18n code the edge renders for a rejected slug.
    code: str = "errors.application.publishSlugRejected"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class PublishSlugConflict(Exception):
    """A publish was REFUSED because the slug is already claimed by a FOREIGN owner (clobber backstop).

    Raised by :meth:`ApplicationPublishService.publish` when the atomic
    :meth:`SlugMarkerClaimer.claim` reports the ``_slugs/{slug}`` marker is owned by a DIFFERENT
    owner (a different plane / kind / tenant — :class:`SlugTaken`). The service NEVER overwrites a
    foreign marker (the clobber backstop, R4.4): it surfaces a caller-safe conflict and performs no
    write. The edge maps this to a 409 ("the slug is taken by someone else") carrying a generic,
    no-internals message — never the raw :class:`SlugTaken` / ``str(e)``. A same-owner re-publish
    never reaches this path (``claim`` is idempotent for a matching body).
    """

    #: The stable machine/i18n code the edge renders for a foreign-owned slug.
    code: str = "errors.application.publishSlugConflict"

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"slug '{slug}' is already claimed by another page")


class PublishPipelineNotWired(NotImplementedError):
    """The live render/write/invalidation pipeline is not wired yet — task 2.2 (dormant seam).

    Raised by the publish seam once a tenant has PASSED the readiness gate AND the artifact has
    been RENDERED (spec 14 Task 2.2 — the render step is now wired). The route, the readiness
    gate, and the shared-shell render are REAL and tested; the ONLY dormant part is the LIVE S3
    ``{slug}/index.html`` + ``form.json`` write and the CloudFront invalidation (R5.1/R5.2/R5.5),
    which is spec 14 Task 8 (claim + dry-run) / Task 9 (live), additionally gated on the owner-run
    hosting migration (task 0.1, R6.4). Those tasks replace the seam with the live write + flip the
    READY test to assert the written artifact. The edge maps this to a 501 (the publish route
    resolved, the tenant is ready, and the artifact is rendered, but the live write is not wired
    yet) carrying a caller-safe "publish pipeline not yet wired (migration-gated)" message — never
    a 500, never ``str(e)``.
    """

    #: The stable machine/i18n code the edge renders for the dormant seam.
    code: str = "errors.application.publishNotWired"

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(
            "application-form publish pipeline not yet wired (migration-gated, task 2.2)"
        )


class ApplicationPublishService:
    """Publish a tenant's application form — readiness gate REAL, live write dormant (task 2.1).

    The route (``POST /members/application-form/publish``) and the readiness gate are the
    testable units delivered by task 2.1; the live render/write/invalidation is task 2.2 and is
    reached only AFTER the readiness gate passes (via the dormant :class:`PublishPipelineNotWired`
    seam). The service holds no business logic of its own beyond composing the three readiness
    preconditions over injected seams — so it stays storage-agnostic and unit-testable with
    in-memory fakes (no boto3, no DynamoDB).

    Args:
        slug_reader: The forward slug reader (tenant → stored ``config#fields`` slug). The
            SAM-plane concrete is the projection reader's ``get_form_slug``; tests pass a static
            one. REQUIRED — a form with no slug is the first readiness refusal.
        readiness_provider: The SAME certified-sender seam the submit readiness gate uses
            (:class:`sam.members.domain.application_readiness.MailReadinessProvider` — the
            projection reader in production). Reused, NOT duplicated: the publish "certified
            sender" precondition is the authoritative :func:`is_send_ready` predicate (certified
            flag AND a projected domain), so publish and submit can never disagree on send-ready.
        field_config_reader: The public field-config read (the single filter authority,
            :meth:`get_public_field_config`). The on-form-field precondition counts the filtered
            ``fields`` list — reusing the one filter, never re-deriving which fields are on the
            form (R5.2, no drift).
        look_and_feel_reader: OPTIONAL Layer-3 wiring seam (spec 15 §C4 / Req 5.1) — the
            :class:`LookAndFeelSettingsReader` that resolves the tenant's SAM-owned presentation
            VALUES so the publish render can feed them through Layer 2 (``render_page_styles``)
            into ``branding=`` on the renderer, closing the Req 5 defect. Matches the optional-seam
            style of ``slug_marker_store`` / ``prefix_reader`` / ``artifact_writer``: absent (the
            default), publish behaves EXACTLY as before — the renderer uses its existing fallback
            defaults — so adding it is backward compatible. The resolve→Layer-2→``branding=`` wiring
            in :meth:`publish` is task 7.2; this param is the seam it will read.
    """

    def __init__(
        self,
        slug_reader: FormSlugReader,
        readiness_provider: MailReadinessProvider,
        field_config_reader: PublicFieldConfigReader,
        slug_marker_store: SlugMarkerClaimer | None = None,
        prefix_reader: PublicPrefixReader | None = None,
        artifact_writer: PublicPageArtifactWriter | None = None,
        publish_state_writer: PublishStateWriter | None = None,
        look_and_feel_reader: LookAndFeelSettingsReader | None = None,
    ) -> None:
        self._slug_reader = slug_reader
        self._readiness = readiness_provider
        self._field_config = field_config_reader
        self._marker_store = slug_marker_store
        self._prefix_reader = prefix_reader
        self._artifact_writer = artifact_writer
        self._publish_state_writer = publish_state_writer
        self._look_and_feel_reader = look_and_feel_reader

    def _require_ready(self, tenant_id: str) -> str:
        """Enforce the publish readiness gate, or raise the typed refusal (R5.4 / D15 / R6).

        The ONE gate publish runs BEFORE any write, in this fixed order (slug → certified sender
        → on-form field) so the admin is told the FIRST thing to fix. Each precondition refuses
        with its typed :class:`PublishNotReadyReason` and NO write is attempted (no broken
        artifact, R5.4). Returns the validated non-blank slug on success (the artifact's address).
        """
        # 1. Stored slug (R4) — the form's public address. "No slug" = the admin has not authored
        #    one yet (the slug precondition is the SAME slug R4 stores on config#fields).
        slug = self._slug_reader.get_form_slug(tenant_id)
        if not slug or not slug.strip():
            raise PublishNotReady(
                PublishNotReadyReason.NO_SLUG,
                "the application form has no public slug yet — author one before publishing",
            )

        # 2. Certified sender — the AUTHORITATIVE shared predicate (certified flag AND a projected
        #    domain), the exact gate the submit readiness check uses. A form that opens must be one
        #    the eventual applicant-confirmation/staff-notification send can actually use (R5.4).
        if not is_send_ready(self._readiness, tenant_id):
            raise PublishNotReady(
                PublishNotReadyReason.NO_CERTIFIED_SENDER,
                "the tenant has no usable certified sender yet — publishing is refused",
            )

        # 3. ≥1 on-form field — resolve the PUBLIC schema through the single filter authority
        #    (get_public_field_config filters to application_visible fields) and require at least
        #    one. An empty form must not be published (R5.4) — never emit a fieldless artifact.
        config = self._field_config.get_public_field_config(tenant_id)
        fields = config.get("fields") if isinstance(config, Mapping) else None
        if not fields:
            raise PublishNotReady(
                PublishNotReadyReason.NO_ON_FORM_FIELD,
                "the application form has no fields on it yet — add at least one before publishing",
            )

        return slug.strip()

    def _claim_slug(self, tenant_id: str, slug: str) -> None:
        """Claim the ``_slugs/{slug}`` marker for the owning tenant (spec 14 Task 8.1 / R3/R4).

        Runs AFTER the readiness gate + render and BEFORE the still-dormant live write, in this
        fixed order (design §C1 / form_slug "Ordering on a claim path"):

        1. **format/reserved** (:func:`validate_slug_format`) — a malformed/reserved slug is
           rejected (:class:`PublishSlugRejected`) before anything else;
        2. **SEC-4 prefix ownership** (:func:`validate_slug_prefix_ownership`) — the slug must sit
           under the AUTHENTICATED tenant's own ``public_prefix`` (resolved via
           :meth:`PublicPrefixReader.get_public_prefix`), closing the squatting hole the
           tenant-agnostic uniqueness gate alone cannot. A re-publish of the tenant's OWN
           already-live slug is a grandfathered same-owner case (``is_grandfathered=True``) and is
           NOT re-validated against the prefix rule (R2.5);
        3. **atomic claim** (:meth:`SlugMarkerClaimer.claim`) — writes the structured owner body
           ``{owner_plane=sam, kind=application_form, tenant_id, resource_ref=config#fields}``. The
           claim is IDEMPOTENT for a same-owner re-publish (a matching body succeeds silently, no
           conflict) and raises :class:`SlugTaken` for a FOREIGN owner, which this method maps to
           the caller-safe :class:`PublishSlugConflict` — the clobber backstop (R4.4): a foreign
           marker is NEVER overwritten.

        Ownership is decided from the marker BODY, never by parsing the slug string (Property 2).
        No live S3 artifact is written here — only the control-plane marker is claimed; the live
        ``{slug}/index.html`` put + CloudFront invalidation stay DORMANT (Task 9).

        The store/prefix seams are injected (lazy + fail-fast in production, in-memory fakes in
        tests) so this runs locally/dry-run with no real AWS. When the store seam is absent (the
        task-2.1 scaffold wiring, before Task 8.1 injects it), the claim is a no-op and publish
        falls straight through to the dormant seam — preserving the pre-8.1 behaviour for callers
        that have not yet wired the store.

        Raises:
            PublishSlugRejected: the slug is malformed/reserved or violates the SEC-4 prefix rule —
                no claim attempted, caller-safe detail.
            PublishSlugConflict: the slug is owned by a FOREIGN owner — no clobber, no write.
        """
        if self._marker_store is None:
            # Scaffold wiring (pre-8.1): no store injected → nothing to claim, fall through to the
            # dormant live-write seam exactly as before. Task 8.1's composition root injects the
            # real store so this branch is not taken in production.
            return

        # 1. Format/reserved FIRST (R4.2) — a malformed slug never reaches the prefix check.
        format_error = validate_slug_format(slug)
        if format_error is not None:
            raise PublishSlugRejected(format_error)

        # Decide grandfathering from the EXISTING marker BODY: a re-publish of the tenant's OWN
        # already-live slug (same owner_plane + kind + tenant_id) is grandfathered — the SEC-4
        # prefix rule applies to NEW claims only and must not force-rename an established slug
        # (R2.5). Ownership is read from the body, never parsed from the slug string (Property 2).
        existing = self._marker_store.resolve(slug)
        is_grandfathered = (
            existing is not None
            and existing.owner_plane == FORM_OWNER_PLANE
            and existing.kind == FORM_OWNER_KIND
            and existing.tenant_id == tenant_id
        )

        # 2. SEC-4 prefix ownership — resolve the AUTHENTICATED tenant's own prefix off its
        #    projected tenant row (never Flask, ADR 0005). A grandfathered same-owner re-publish
        #    short-circuits the rule; a prefix-less tenant's NEW claim is refused by the validator.
        tenant_prefix = (
            self._prefix_reader.get_public_prefix(tenant_id)
            if self._prefix_reader is not None
            else None
        )
        prefix_error = validate_slug_prefix_ownership(
            slug, tenant_prefix, is_grandfathered=is_grandfathered
        )
        if prefix_error is not None:
            raise PublishSlugRejected(prefix_error)

        # 3. Atomic claim — idempotent same-owner re-publish succeeds; a FOREIGN owner raises
        #    SlugTaken, which we surface as the caller-safe clobber-backstop conflict (no write).
        owner = SlugMarker(
            owner_plane=FORM_OWNER_PLANE,
            kind=FORM_OWNER_KIND,
            tenant_id=tenant_id,
            resource_ref=FORM_RESOURCE_REF,
        )
        try:
            self._marker_store.claim(slug, owner)
        except SlugTaken as exc:
            raise PublishSlugConflict(slug) from exc

    def publish(self, tenant_id: str) -> dict[str, Any]:
        """Publish the tenant's application form (readiness-gated; live write wired — Task 9.1).

        Runs the readiness gate (:meth:`_require_ready`) FIRST — a not-ready tenant raises
        :class:`PublishNotReady` (the typed, admin-facing refusal) and NOTHING is rendered or
        written (R5.4). A READY tenant then RENDERS the artifact via the shared page shell (spec 14
        Task 2.2) — resolving the tenant's SAM-owned look-and-feel VALUES through the injected
        :class:`LookAndFeelSettingsReader` (when present) and running them through Layer 2 into
        ``branding=`` on the renderer, so the published form carries the tenant's look-and-feel
        (spec 15 §C4 / Req 5; when no reader is injected the renderer uses its SAM-owned defaults,
        backward compatible) — CLAIMS the ``_slugs/{slug}`` marker (spec 14 Task 8.1), and — when an
        :class:`PublicPageArtifactWriter` is injected (spec 14 Task 9.1) — performs the LIVE write:
        ``put_object`` of ``{slug}/index.html`` + ``{slug}/form.json`` under the served ``{slug}/``
        prefix, then a BEST-EFFORT CloudFront invalidation.

        The ``put_object`` writes are AUTHORITATIVE; the invalidation is non-fatal (the
        known-deferred permission/ARN gap — Task 9.2), so a denied invalidation NEVER fails the
        publish. On success the method returns the
        :class:`MembersApplicationPublishResult`-shaped dict the frontend caller expects
        (``success``, ``slug``, ``published_version``, ``published_at``).

        When NO writer is injected (the pre-9.1 scaffold / dry-run wiring) the live write stays
        DORMANT and the publish seam raises :class:`PublishPipelineNotWired` after a successful
        render + claim — preserving Task 8's claim-and-dry-run behaviour.

        Args:
            tenant_id: The verified, admin-gated tenant (never a client/body value — R2).

        Returns:
            On success (writer injected — Task 9.1): the publish result dict
            (``success``/``slug``/``published_version``/``published_at``). The artifact write is
            authoritative even if the best-effort invalidation is denied.

        Raises:
            DynamoDBConfigError: the publish-time ``PUBLIC_API_BASE_URL`` env var is unset/blank —
                resolved fail-fast at the render step (bugfix Task 3.1 / R2.6, no silent default)
                so a mis-configured environment fails loudly rather than baking the wrong backend
                address into the artifact.
            PublishNotReady: a readiness precondition (slug / certified sender / on-form field) is
                missing — NO render or write attempted, typed admin-facing reason.
            PublishSlugRejected: the slug is malformed/reserved or violates the SEC-4 prefix rule
                (spec 14 Task 8.1) — the artifact is rendered but NO marker is claimed and no write
                is reached.
            PublishSlugConflict: the slug is owned by a FOREIGN owner (clobber backstop, R4.4) — no
                overwrite, no write. A same-owner re-publish is idempotent and never raises this.
            PublishPipelineNotWired: ONLY when NO artifact writer is injected (the pre-9.1 scaffold
                / dry-run wiring) — the tenant is READY, the artifact is RENDERED, the slug is
                CLAIMED, but the live write stays dormant. With a writer injected this is not
                raised; the live write runs and the result dict is returned.
        """
        slug = self._require_ready(tenant_id)

        # ── RENDER step (spec 14 Task 2.2 — WIRED) ─────────────────────────────────────
        # The tenant is READY. Render the slug-addressed `{slug}/index.html` artifact via the
        # SHARED, plane-neutral page shell (`sam.shared.page_shell.render_page`) — the SAM form
        # "renders its shell via page_shell" (R7.1). `render_application_form_page` composes the
        # applicant body from the SAME `get_public_field_config` filter authority (reused, never a
        # second field list) and the CSS from `LandingPageStyles` (the SINGLE CSS source) and hands
        # head_meta + body + css to the shared shell. This is the render-only half of publish; the
        # LIVE S3 put + CloudFront invalidation stay GATED (spec 14 Tasks 8/9, R6.4).
        config = self._field_config.get_public_field_config(tenant_id)
        # Resolve the PUBLIC API base at the FIRST real publish use (fail-fast, no silent default
        # — bugfix Task 3.1 / R2.6). A missing `PUBLIC_API_BASE_URL` raises here rather than baking
        # the wrong backend into the artifact. The resolved base + the slug are threaded into the
        # renderer so a later task's (3.2) submit script can target
        # `POST {public_api_base}/public/members/{slug}/applications` per environment. No boto3 / no
        # plane-crossing — this is DATA resolved from env.
        public_api_base = resolve_public_api_base()

        # ── Look-and-feel resolve → Layer 2 → branding= (spec 15 §C4 / Req 5, task 7.2) ──
        # Close the Req 5 defect: a change to a look-and-feel setting had NO observable effect on
        # the published form because publish rendered WITHOUT branding. When a
        # `LookAndFeelSettingsReader` is injected, resolve the verified tenant's SAM-owned
        # presentation VALUES (the `look_and_feel` slice on `config#fields` — never a Flask value,
        # Req 2.1) and pass them straight into the renderer as `branding=`. The renderer runs
        # Layer 2 (`render_page_styles`) on those values to generate the CSS the published artifact
        # carries (Req 5.1/5.2), so changing a value changes the published styling (Req 5.3). The
        # resolve is tenant-scoped (Req 2.4) — `tenant_id` is the verified value the edge passed
        # in, never a client value.
        #
        # Backward compatible (Req 5.4): when NO reader is injected (the default), `branding` stays
        # `None` and the renderer uses its SAM-owned defaults — identical to the pre-task-7.2
        # behaviour. An absent slice / missing key also resolves to `{}` → the same defaults, so a
        # tenant that never authored look-and-feel publishes exactly as before.
        #
        # Req 5.5 (failure preserves the previous artifact): Layer 2 runs INSIDE this render call,
        # which happens BEFORE the slug claim and the live artifact write below. If Layer 2 fails
        # (an unsupported attribute → `UnsupportedAttributeError`), the exception propagates out of
        # `render_application_form_page` here, so NO artifact is written and the previously
        # published form is left untouched — the publish returns a failure indication by raising.
        branding = (
            self._look_and_feel_reader.get_look_and_feel(tenant_id)
            if self._look_and_feel_reader is not None
            else None
        )

        # ── Logo + header title → renderer (bugfix-published-form-styling Task 6.1 / R2.3, R2.4) ──
        # The published form previously rendered NO tenant logo and NO visible body heading
        # (defect 1.3 / 1.4) because publish passed no header fragment. Resolve the two values-only
        # presentation attributes from the SAME SAM-owned `look_and_feel` slice (`branding`) and
        # pass them to the renderer, which emits an HTML-escaped `<img class="form-logo">` + an
        # `<h1 class="form-title">` at the top of `.application-form` (so the Task-5.1 CSS can theme
        # them). These are DATA read off the resolved slice — a logo is a URL/reference (DD-C1),
        # never CSS or a binary. Absent values (no reader, no slice, or an unset key) resolve to ""
        # and the renderer emits nothing, so the body is byte-identical to today (preservation,
        # bugfix 3.2) — backward compatible with every tenant that never authored them.
        logo = ""
        header_title = ""
        if isinstance(branding, Mapping):
            raw_logo = branding.get("logo")
            if isinstance(raw_logo, str):
                logo = raw_logo
            raw_header_title = branding.get("header_title")
            if isinstance(raw_header_title, str):
                header_title = raw_header_title

        self._rendered_html = render_application_form_page(
            config,
            head_meta={
                "title": slug,
                "canonical": f"https://{slug}.jabaki.nl/",
                "site_name": slug,
            },
            branding=branding,
            logo=logo,
            header_title=header_title,
            slug=slug,
            public_api_base=public_api_base,
        )

        # ── CLAIM step (spec 14 Task 8.1 — WIRED) ──────────────────────────────────────
        # The artifact is rendered; now CLAIM the slug for the owning tenant via the shared
        # `_slugs/{slug}` marker store (Task 1) BEFORE the dormant live write. Ordering inside the
        # claim is format/reserved → SEC-4 prefix ownership → atomic claim (idempotent same-owner
        # re-publish; clobber backstop for a foreign owner). This uses only the control-plane
        # marker — NOT a live served artifact — so it runs locally/dry-run with an injected fake
        # store, no real AWS. A malformed/foreign slug is refused here with a caller-safe error and
        # NO write is reached.
        self._claim_slug(tenant_id, slug)

        # ── LIVE WRITE (spec 14 Task 9.1 — the lifted dormant seam) ────────────────────
        # The slug is claimed; now perform the AUTHORITATIVE live write against the nonprofit
        # bucket/distribution (resolved inside the injected artifact writer from the SAME env vars
        # the landing publish uses — `LANDING_PAGES_BUCKET` + `CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`
        # — so both planes target the SAME hosting-migration-owned resource, never a new one, D7).
        # The writer puts `{slug}/index.html` (the rendered artifact) + `{slug}/form.json` (the
        # form schema/config the published shell fetches) under the SERVED `{slug}/` prefix —
        # DISTINCT from the `_slugs/{slug}` control-plane marker — then attempts a CloudFront
        # invalidation.
        #
        # The put_object(s) are the authoritative publish: the CloudFront invalidation inside the
        # writer is BEST-EFFORT / NON-FATAL and is KNOWN-DEFERRED to Task 9.2 (SEC-8 IAM) — the
        # Railway publish identity currently lacks `cloudfront:CreateInvalidation` and the ARN
        # targets the personal account while the `*.jabaki.nl` distribution is in nonprofit, so an
        # invalidation call fails permission-denied. The writer LOGS and SWALLOWS that failure, so
        # a denied invalidation NEVER fails the publish (the artifact is already written; an UPDATE
        # just appears after the cache TTL ≤ 1h, a NEW page immediately). Task 9.2 makes the
        # invalidation succeed WITHOUT touching this flow.
        #
        # When no writer is injected (the pre-9.1 scaffold / dry-run wiring) the live write stays
        # DORMANT and the seam raises exactly as before — preserving Task 8's claim-and-dry-run
        # behaviour for callers that have not yet wired the writer.
        if self._artifact_writer is None:
            raise PublishPipelineNotWired(slug)

        form_json = self._form_json_artifact(config)
        self._artifact_writer.publish_artifacts(
            slug, index_html=self._rendered_html, form_json=form_json
        )

        # Bump the publish-state metadata the frontend caller reads back (R5). `published_version`
        # advances monotonically; `published_at` is set to now.
        published_version = self._next_published_version(tenant_id)
        published_at = datetime.now(timezone.utc).isoformat()

        # Persist the publish state on `config#fields` (Round 3 Defect 4) via the injected
        # version-conditional Change-Op writer, so the builder's `everPublished` becomes true and
        # the next publish reads version N+1. Runs only AFTER the artifact write succeeded.
        # Failure policy: the artifact IS already live, so a persistence failure must NOT turn the
        # publish into a 500 — we log a warning (no PII: tenant + exception type only) and still
        # return success; the next publish re-attempts the write. No writer wired → unchanged.
        if self._publish_state_writer is not None:
            try:
                self._publish_state_writer.record_publish(
                    tenant_id,
                    published_version=published_version,
                    published_at=published_at,
                )
            except Exception as exc:  # noqa: BLE001 - artifact is live; never fail the publish
                _LOG.warning(
                    "publish state not persisted after a successful artifact write "
                    "(tenant=%s, error=%s)",
                    tenant_id,
                    type(exc).__name__,
                )
        return {
            "success": True,
            "slug": slug,
            "published_version": published_version,
            "published_at": published_at,
        }

    @staticmethod
    def _form_json_artifact(config: Mapping[str, Any]) -> bytes:
        """Serialize the public field-config into the served ``{slug}/form.json`` body.

        ``form.json`` is the form schema/config the published shell fetches to render the applicant
        form client-side. It is the SAME ``get_public_field_config`` view the server already filters
        (the single filter authority, reused — never a second field list), serialized compactly as
        UTF-8 JSON.
        """
        payload = dict(config) if isinstance(config, Mapping) else {}
        # Publish-state is admin metadata (read for `_next_published_version`), not form schema —
        # keep it out of the served public artifact.
        payload.pop("published_version", None)
        payload.pop("published_at", None)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

    def _next_published_version(self, tenant_id: str) -> int:
        """Return the next monotonically-advancing ``published_version`` for the tenant's form.

        Reads the current stored ``published_version`` from the public field-config view (fail-safe:
        an absent/non-int value is treated as 0 — a never-published form) and returns it + 1, so a
        first publish is version 1 and a re-publish advances by one. The persistence of this value
        on ``config#fields`` is owned by the config write path (spec 12 §Data Models); this method
        only computes the authoritative next value the publish result reports.
        """
        try:
            config = self._field_config.get_public_field_config(tenant_id)
        except Exception:  # noqa: BLE001 - version is best-effort metadata, never fail the publish
            return 1
        current = (
            config.get("published_version") if isinstance(config, Mapping) else None
        )
        if isinstance(current, bool) or not isinstance(current, int) or current < 0:
            return 1
        return current + 1
