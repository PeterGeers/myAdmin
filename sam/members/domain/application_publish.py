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
- the **publish seam**: once ready, the service hands off to the live render/write/invalidation
  pipeline. That pipeline (the S3 ``{slug}/index.html`` + ``form.json`` write and the
  CloudFront invalidation, R5.1/R5.2/R5.5) is **task 2.2** and is **DORMANT** here: the seam
  raises :class:`PublishPipelineNotWired` so a READY tenant reaches the seam (fully testable)
  but the live write cannot fire until task 2.2 fills it in — AND the owner-run hosting
  migration (task 0.1) cuts the bucket over to nonprofit (R6.4). Task 2.2 swaps the stub for the
  real pipeline and flips the READY test to assert the artifact.

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

from collections.abc import Mapping
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.application_readiness import (
    MailReadinessProvider,
    is_send_ready,
)

__all__ = [
    "FormSlugReader",
    "PublicFieldConfigReader",
    "PublishNotReady",
    "PublishNotReadyReason",
    "PublishPipelineNotWired",
    "ApplicationPublishService",
]


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


class PublishPipelineNotWired(NotImplementedError):
    """The live render/write/invalidation pipeline is not wired yet — task 2.2 (dormant seam).

    Raised by the publish seam once a tenant has PASSED the readiness gate, in the task-2.1
    scaffold. The route + the readiness gate are REAL and tested; the ONLY dormant part is the
    live S3 ``{slug}/index.html`` + ``form.json`` write and the CloudFront invalidation (R5.1/
    R5.2/R5.5), which is task 2.2 and is additionally gated on the owner-run hosting migration
    (task 0.1, R6.4). Task 2.2 replaces the stub seam with the real pipeline and flips the READY
    test to assert the written artifact. The edge maps this to a 501 (the publish route resolved
    and the tenant is ready, but the behaviour is not built yet) carrying a caller-safe
    "publish pipeline not yet wired (migration-gated)" message — never a 500, never ``str(e)``.
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
    """

    def __init__(
        self,
        slug_reader: FormSlugReader,
        readiness_provider: MailReadinessProvider,
        field_config_reader: PublicFieldConfigReader,
    ) -> None:
        self._slug_reader = slug_reader
        self._readiness = readiness_provider
        self._field_config = field_config_reader

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

    def publish(self, tenant_id: str) -> dict[str, Any]:
        """Publish the tenant's application form (readiness-gated; live write is task 2.2).

        Runs the readiness gate (:meth:`_require_ready`) FIRST — a not-ready tenant raises
        :class:`PublishNotReady` (the typed, admin-facing refusal) and NOTHING is written
        (R5.4). A READY tenant reaches the publish seam, which in the task-2.1 scaffold raises
        :class:`PublishPipelineNotWired` (the live S3 render/write + CloudFront invalidation is
        task 2.2, additionally gated on the owner-run hosting migration, task 0.1 / R6.4).

        Task 2.2 replaces the dormant seam below with the real pipeline and returns the
        :class:`MembersApplicationPublishResult`-shaped dict the frontend caller expects
        (``success``, ``slug``, ``published_version``, ``published_at``). For task 2.1 the
        readiness-refusal paths and the "reaches the ready seam" path are the fully-testable
        behaviour.

        Args:
            tenant_id: The verified, admin-gated tenant (never a client/body value — R2).

        Returns:
            On success (once task 2.2 lands): the publish result dict. In the scaffold, a READY
            tenant never returns — it raises :class:`PublishPipelineNotWired` from the seam.

        Raises:
            PublishNotReady: a readiness precondition (slug / certified sender / on-form field) is
                missing — NO write attempted, typed admin-facing reason.
            PublishPipelineNotWired: the tenant is READY but the live write pipeline is task 2.2
                (dormant seam) — the route + gate are real, only the live write is pending.
        """
        slug = self._require_ready(tenant_id)
        # ── DORMANT seam (task 2.2) ───────────────────────────────────────────────────
        # The tenant is READY. Task 2.2 fills this in: render config#fields/config#mail through
        # get_public_field_config into the self-contained, responsive, postMessage-resize HTML
        # (R5.2/R5.5), write `{slug}/index.html` [+ `{slug}/form.json`] to
        # `myadmin-public-pages-{env}` via boto3 (with the form-vs-landing root-`landing.json`
        # backstop, D6), invalidate the `*.jabaki.nl` distribution for `/{slug}*`, bump
        # `published_version`/`published_at` on config#fields, and return the result dict. Until
        # then the seam raises — the route + readiness gate are REAL and tested; ONLY this live
        # write is dormant (and additionally gated on the hosting migration, task 0.1 / R6.4).
        raise PublishPipelineNotWired(slug)
