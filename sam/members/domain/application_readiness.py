"""
Member Application Form task 4.2 — the **tenant-readiness gate** (design §2.1/§2.2 seam a/c).

A tenant may accept applications ONLY when it is **mail-send-ready**: its projected
``config#mail`` row must be ``mail_certified`` AND carry a ``mail_domain``. The application form
triggers emails (staff notification + applicant confirmation, R8/R8a), and a public applicant can
NEVER be left silently un-notifiable (D15) — so an un-ready tenant simply "is not accepting
applications yet". Both public entry points enforce this ONE predicate:

- the public field-config read (``get_public_field_config``, task 4.1) gates FORM LOAD on it
  (R5.4) — an un-ready tenant's form must not open;
- the submit (``create_application``, task 2.2) RE-CHECKS it (R9.4 defense-in-depth — a client
  could POST without ever loading the form) and REFUSES with NO record written.

The two must AGREE, so both consult the same :func:`is_send_ready` predicate over the same seam.

Why its own module
------------------
This owns only the **seam + the predicate + the neutral refusal**, exactly mirroring
:mod:`sam.members.domain.mail_gate` and :mod:`sam.members.domain.consent_notice`: the public
service (:class:`sam.members.domain.application_service.ApplicationService`) depends on the
:class:`MailReadinessProvider` ``Protocol``, never on where the mail config lives. The SAM-plane
concrete provider is the DynamoDB-backed projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
``is_mail_certified`` / ``get_mail_domain`` already satisfy this ``Protocol`` by duck-typing — the
SAME two accessors :class:`sam.members.domain.mail_sender_resolver.MailConfigReader` reads); tests
pass a static one.

Fail-closed (D15)
-----------------
Readiness opens ONLY when BOTH the certified flag is a projected ``True`` AND a non-blank domain
is projected. A tenant with no provider wired, no ``config#mail`` row, a non-``True``
``mail_certified``, or an absent/blank ``mail_domain`` is NOT ready — the gate refuses. This is
the SAME fail-closed discipline the reader (:meth:`MembersProjectionReader.is_mail_certified` /
``get_mail_domain``) and the send-path resolver
(:class:`sam.members.domain.mail_sender_resolver.MailSenderResolver`) enforce, so the form gate,
the submit re-check, and the eventual send all agree on "send-ready".

Neutral signal (D15/R5.4)
-------------------------
:class:`ApplicationNotAvailable` carries ONLY the stable ``code`` the edge maps to a neutral
**409** — it NEVER names ``mail_domain`` / ``mail_certified``, never distinguishes not-certified
from no-domain, and never hints "certify your domain". A tenant's mail posture is not probeable
from the public surface: "not accepting applications yet" is the whole story the applicant sees.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from sam.members.domain.error_codes import APPLICATION_NOT_AVAILABLE

__all__ = [
    "ApplicationNotAvailable",
    "MailReadinessProvider",
    "StaticMailReadinessProvider",
    "is_send_ready",
]


@runtime_checkable
class MailReadinessProvider(Protocol):
    """Read-only provider of the two projected mail-config facts readiness needs (the gate seam).

    Mirrors :class:`sam.members.domain.mail_gate.MailGateProvider` — the domain depends on this
    ``Protocol``, never on where the ``config#mail`` row lives. It is the exact pair of accessors
    :class:`sam.members.domain.mail_sender_resolver.MailConfigReader` already declares, so the
    SAM-plane concrete provider is the SAME DynamoDB-backed projection reader
    (:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
    ``is_mail_certified`` / ``get_mail_domain`` satisfy this by duck-typing); tests pass a static
    one. Both methods are fail-closed / empty-is-valid on missing data (a missing ``config#mail``
    row → ``False`` certified / ``None`` domain), so the predicate inherits fail-closed for free.
    """

    def is_mail_certified(self, tenant_id: str) -> bool:
        """Return the projected ``mail_certified`` gate (fail-closed → ``False``)."""
        ...

    def get_mail_domain(self, tenant_id: str) -> str | None:
        """Return the tenant's projected ``mail_domain``, or ``None`` when absent/unusable."""
        ...


class StaticMailReadinessProvider:
    """In-memory :class:`MailReadinessProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: (certified, domain)}`` map. A tenant with no entry resolves to
    ``(False, None)`` — NOT ready (fail-closed, D15) — matching the DynamoDB-backed reader so
    tests and production agree. The default (no map) is the empty, fail-closed provider: every
    tenant is un-ready until its certified flag + domain are explicitly projected.

    Args:
        config_by_tenant: ``{tenant_id: (mail_certified, mail_domain)}``. ``mail_certified`` is
            coerced to the fail-closed ``is`` ``True`` discipline; ``mail_domain`` is ``None`` /
            a string.
    """

    def __init__(
        self,
        config_by_tenant: Mapping[str, tuple[bool, str | None]] | None = None,
    ) -> None:
        self._config_by_tenant = dict(config_by_tenant or {})

    def is_mail_certified(self, tenant_id: str) -> bool:
        certified, _domain = self._config_by_tenant.get(tenant_id, (False, None))
        # Fail-closed: only an explicit True certifies (mirrors the reader's `is True`).
        return certified is True

    def get_mail_domain(self, tenant_id: str) -> str | None:
        _certified, domain = self._config_by_tenant.get(tenant_id, (False, None))
        if not isinstance(domain, str) or not domain.strip():
            return None
        return domain


def is_send_ready(provider: MailReadinessProvider, tenant_id: str) -> bool:
    """Return whether ``tenant_id`` is mail-send-ready (certified AND domain present) — the gate.

    The ONE readiness predicate both public entry points share (R5.4 form load + R9.4 submit
    re-check), so the form read and the submit can never disagree on "send-ready". A tenant is
    ready IFF BOTH hold (D15):

    1. ``mail_certified`` is a projected ``True`` (the onboarding SES-verified gate — fail-closed,
       a missing/non-``True`` flag is NOT ready), AND
    2. a non-blank ``mail_domain`` is projected (else no ``From`` is composable at all — NEVER a
       guessed/foreign host, the ``jabaki.nl`` regression guard, R4.2).

    Fail-closed on every missing fact: a tenant with no provider wired, no ``config#mail`` row, or
    either fact absent/blank is NOT ready. This is the exact pair the send-path resolver
    (:class:`sam.members.domain.mail_sender_resolver.MailSenderResolver`) gates on, so a tenant the
    form opens for is one the eventual send can actually use.

    Args:
        provider: The readiness seam (the projection reader in production, a static one in tests).
        tenant_id: The verified, slug-resolved tenant (never a client value, R2).

    Returns:
        ``True`` iff the tenant is certified AND has a projected non-blank domain.
    """
    if not provider.is_mail_certified(tenant_id):
        return False
    domain = provider.get_mail_domain(tenant_id)
    return bool(domain and domain.strip())


class ApplicationNotAvailable(Exception):
    """The tenant is NOT accepting applications yet → the NEUTRAL 409 (D15/R5.4/R9.4).

    Raised by the readiness gate on BOTH public entry points when :func:`is_send_ready` is
    ``False`` — the form read refuses to open (R5.4) and the submit refuses with NO record
    written (R9.4). The edge maps it to a **409** carrying :data:`code` on the R1a envelope — a
    request-level signal, NOT a per-field :class:`FieldError`, and distinct from the 404
    (unknown/forged slug) and the 422 (validation).

    DELIBERATELY NEUTRAL (D15): it carries ONLY the stable, mail-config-free ``code``
    (:data:`~sam.members.domain.error_codes.APPLICATION_NOT_AVAILABLE`). It NEVER names
    ``mail_domain`` / ``mail_certified``, never says which fact is missing, and never hints
    "certify your domain" — a tenant's mail posture must not be probeable from the public surface.
    The ``message`` is a generic English fallback for a client that cannot resolve the code; it
    too leaks nothing.
    """

    #: The stable machine/i18n code the edge renders — the single neutral readiness signal.
    code: str = APPLICATION_NOT_AVAILABLE

    def __init__(self, message: str = "applications are not available for this tenant yet"):
        super().__init__(message)
