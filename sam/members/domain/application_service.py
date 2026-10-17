"""
Member Application Form — the **public intake application service** (design §11a seam a/b/c).

The public (unauthenticated) application form has its OWN thin domain service, named by design
§11a as the surface the public edge (``handler/public_app.py``) delegates to:

- :meth:`ApplicationService.get_public_field_config` (task 4.1, R5.1–R5.3) — the public,
  applicant-facing field schema the form fetches before submit;
- :meth:`ApplicationService.create_application` (task 2.2, R3/R3a/R6/R11/R12) — the public write
  that lands a ``status=application`` member record.

**Why a thin wrapper, not a second engine.** The authoritative public-intake behaviour already
lives on :class:`~sam.members.domain.membership_service.MembershipService` (the ``create_member``
spine, the :class:`~sam.members.domain.field_resolver.FieldResolver`, the subset/format/consent/
locale seams) — a public applicant is just an un-authenticated caller of the SAME engine, trusted
for nothing (design §1 layer ownership: "``ApplicationService`` owns the authoritative rules;
reuses ``MembershipService.create_member`` rather than a second write path", R3.5). So this class
holds NO business logic of its own: it is a NAMED facade over the one engine, giving the public
edge a small, intention-revealing surface (exactly the two public operations) WITHOUT exposing the
full authenticated staff service to the token-less entrypoint. Every rule — the
application-selected filter, the enum subset, the ``FieldFormat`` validator, consent, locale,
tenant isolation — is enforced by the delegate, unchanged.

Storage- and tenant-agnostic (steering 35): it is constructed with (or over) a
``MembershipService`` the edge wired to the DynamoDB-backed repository + projection providers; it
never imports boto3, never touches HTTP, and has no ``if tenant == ...``. The tenant is always the
verified, slug-resolved ``tenant_id`` the public edge passes in (verify-before-trust, R2) — never
a client value.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sam.members.domain.application_readiness import (
    ApplicationNotAvailable,
    MailReadinessProvider,
    StaticMailReadinessProvider,
    is_send_ready,
)

if TYPE_CHECKING:  # type-only — keep the import light, no cycle at runtime
    from sam.members.domain.membership_service import MembershipService
    from sam.members.repository.members_repository import Member

__all__ = ["ApplicationService"]


class ApplicationService:
    """Thin public-intake facade over :class:`MembershipService` (design §11a).

    The public edge resolves the tenant from the path slug (R2) and calls exactly the two public
    operations on this surface; everything authoritative is delegated to the wrapped engine.

    **Tenant-readiness gate (task 4.2 / D15).** This facade additionally OWNS the readiness gate
    that wraps BOTH operations: a tenant may accept applications only when it is mail-send-ready
    (``mail_certified`` + a projected ``mail_domain``). The schema read gates form load on it
    (R5.4) and the submit RE-CHECKS it (R9.4 defense-in-depth), both via :meth:`_require_send_ready`
    over the injected :class:`~sam.members.domain.application_readiness.MailReadinessProvider`
    seam — so the form read and the submit can never disagree, and a not-ready tenant gets the
    SAME neutral 409 (:class:`~sam.members.domain.application_readiness.ApplicationNotAvailable`,
    no mail-config leak) on either path with no record ever written.

    Args:
        membership_service: The wired :class:`MembershipService` (over the DynamoDB repository +
            the overlay / consent-notice / scope providers) that owns the authoritative rules.
            Injected so this facade stays storage-agnostic and testable with an in-memory engine.
        mail_readiness_provider: The tenant-readiness seam (task 4.2 / D15) supplying the two
            projected ``config#mail`` facts the gate needs (``is_mail_certified`` /
            ``get_mail_domain``). The SAM-plane concrete is the SAME DynamoDB-backed projection
            reader the send-path resolver reads (it satisfies
            :class:`~sam.members.domain.application_readiness.MailReadinessProvider` by
            duck-typing); tests pass a static one. Defaults to the empty, FAIL-CLOSED
            :class:`~sam.members.domain.application_readiness.StaticMailReadinessProvider` — a
            facade built without a provider treats EVERY tenant as not-send-ready (no form opens,
            every submit is refused), matching the reader's fail-closed discipline. The tenant is
            only accepting applications once its certified flag + domain are explicitly projected.
    """

    def __init__(
        self,
        membership_service: "MembershipService",
        mail_readiness_provider: MailReadinessProvider | None = None,
    ) -> None:
        self._service = membership_service
        # The readiness gate seam (task 4.2 / D15/R5.4/R9.4). Mirrors the service's mail-gate /
        # consent-notice provider injection: this facade depends only on the
        # MailReadinessProvider Protocol, never on where the config#mail row lives. Defaults to
        # the empty, FAIL-CLOSED StaticMailReadinessProvider so a facade built without one treats
        # every tenant as not-send-ready (the gate refuses), matching the reader/resolver.
        self._readiness: MailReadinessProvider = (
            mail_readiness_provider
            if mail_readiness_provider is not None
            else StaticMailReadinessProvider()
        )

    def _require_send_ready(self, tenant_id: str) -> None:
        """Enforce the tenant-readiness gate, or raise the neutral refusal (task 4.2 / D15).

        The ONE gate both public operations run BEFORE doing their work: resolve the shared
        :func:`~sam.members.domain.application_readiness.is_send_ready` predicate (certified AND a
        projected domain) over the injected seam, and raise
        :class:`~sam.members.domain.application_readiness.ApplicationNotAvailable` (the neutral
        409, no mail-config leak) when the tenant is NOT ready. Calling it from BOTH the read
        (R5.4 — form does not open) and the submit (R9.4 — refuse before any write, no record)
        means the form load and the submit can never disagree on "send-ready".
        """
        if not is_send_ready(self._readiness, tenant_id):
            raise ApplicationNotAvailable()

    def get_public_field_config(self, tenant_id: str) -> dict[str, Any]:
        """Return the PUBLIC application form's field schema for ``tenant_id`` (task 4.1, R5.1–R5.3).

        Delegates verbatim to :meth:`MembershipService.get_public_field_config`: resolve the field
        set via the :class:`FieldResolver`, filter to the application-SELECTED fields
        (``application_visible``), and attach per exposed field the application-required flag
        (``required``), the enum application SUBSET (``options``), the ``format`` token,
        ``show_when``, ``label``, ``functional_group`` and ``order`` — the **200** schema contract
        (design §3.1) the frontend Phase 9 consumes.

        **Readiness gate (task 4.2 / D15/R5.4).** BEFORE resolving the schema, this enforces the
        tenant-readiness gate (:meth:`_require_send_ready`): a tenant with no usable certified
        sender (``mail_certified`` + a projected ``mail_domain``) is NOT accepting applications
        yet, so the form must not open — it raises
        :class:`~sam.members.domain.application_readiness.ApplicationNotAvailable` (the neutral
        409, no mail-config leak) instead of returning a schema. A send-ready tenant passes
        straight through to the delegated schema read. The HTTP shaping (mapping the exception to
        the 409 envelope) is the public edge's concern.
        """
        self._require_send_ready(tenant_id)
        return self._service.get_public_field_config(tenant_id)

    def create_application(
        self,
        tenant_id: str,
        body: Mapping[str, Any],
        session_key: str,
        locale: str | None = None,
        consent: Mapping[str, Any] | None = None,
    ) -> "Member":
        """Land a public applicant's submission as a ``status=application`` member (task 2.2).

        Delegates to :meth:`MembershipService.create_application` — the authoritative create
        spine, trusted for nothing (R3/R3a/R6/R11/R12) — but RE-CHECKS tenant readiness FIRST
        (task 4.2 / D15/R9.4 defense-in-depth). A client could POST without ever loading the form
        (so the read-side gate, R5.4, is not enough): BEFORE any write, this enforces the SAME
        readiness gate (:meth:`_require_send_ready`) and REFUSES a not-send-ready tenant's submit
        with :class:`~sam.members.domain.application_readiness.ApplicationNotAvailable` (the
        neutral 409) — NO record is created and NOTHING is enqueued, because the delegate is never
        reached. The form read (R5.4) and this submit re-check agree: both run the one predicate.
        """
        self._require_send_ready(tenant_id)
        return self._service.create_application(
            tenant_id, body, session_key, locale=locale, consent=consent
        )
