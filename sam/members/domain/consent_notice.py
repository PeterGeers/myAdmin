"""
Member Application Form D26 / R12.1a / R12.1c (task 2.6) — the **consent-notice seam**.

Each tenant authors its OWN bilingual (``nl``/``en``), VERSIONED consent/privacy notice on the
Flask plane (``members.application_consent_notice``). It is projected one-directionally onto the
``config#mail`` row (task 8.2) and READ on the Members plane via the projection reader — a Lambda
never queries MySQL at request time (ADR 0005/0006, steering 35/36).

``create_application`` (seam b) consumes this seam to STAMP the consent record: the version it
persists is the tenant's CURRENT notice version resolved SERVER-SIDE (:meth:`current_version`),
NEVER the client-supplied ``notice_version`` — so a later notice revision never retroactively
changes what an existing record recorded (R12.1a).

This module owns only the **seam** — the ``Protocol`` the domain depends on plus a static
reference provider — so the write service stays storage-agnostic and tenant-agnostic, exactly
mirroring :mod:`sam.members.domain.mail_gate`. The SAM-plane concrete provider is the
DynamoDB-backed projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
``get_consent_notice_version`` already satisfies this ``Protocol`` by duck-typing); tests pass a
static one.

Empty-is-valid (R12.1c)
-----------------------
A tenant that has authored no well-formed notice resolves to ``None`` (no provider wired, no
``config#mail`` row, or a missing / malformed notice). ``None`` is NOT an error: the notice text
is the tenant's concern (the platform MAY seed a default elsewhere, R12.1c), while the applicant's
AFFIRMATIVE consent is still required and recorded by ``create_application`` regardless — a
``None`` version simply means "no versioned notice to pin". This mirrors the reader's
empty-is-valid discipline (:meth:`MembersProjectionReader.get_consent_notice_version`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

__all__ = [
    "ConsentNoticeProvider",
    "StaticConsentNoticeProvider",
]


@runtime_checkable
class ConsentNoticeProvider(Protocol):
    """Read-only provider of a tenant's CURRENT consent-notice version (the consent seam).

    Mirrors :class:`sam.members.domain.mail_gate.MailGateProvider`: the domain depends on this
    ``Protocol``, never on where the notice lives. The SAM-plane concrete provider is the
    DynamoDB-backed projection reader (``get_consent_notice_version`` satisfies this by
    duck-typing); tests pass a static one.
    """

    def get_consent_notice_version(self, tenant_id: str) -> str | None:
        """Return the tenant's current notice version, or ``None`` when none is authored."""
        ...


class StaticConsentNoticeProvider:
    """In-memory :class:`ConsentNoticeProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: version}`` map. A tenant with no entry resolves to ``None``
    (empty-is-valid, R12.1c), matching the DynamoDB-backed reader so tests and production agree.
    The default (no map) is the empty provider: every tenant resolves to ``None`` — no versioned
    notice to pin, which ``create_application`` records as a ``None`` version while still
    requiring the applicant's affirmative consent.
    """

    def __init__(self, version_by_tenant: Mapping[str, str] | None = None) -> None:
        self._version_by_tenant = dict(version_by_tenant or {})

    def get_consent_notice_version(self, tenant_id: str) -> str | None:
        return self._version_by_tenant.get(tenant_id)
