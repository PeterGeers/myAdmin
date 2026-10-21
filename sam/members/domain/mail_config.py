"""
spec 02 task 7.1 fix — the **mail-config seam** (the typed Mail authoring read).

The typed Mail function (``MembersMailConfigEditor``) must LOAD its initial values from the
SAME authoritative source it WRITES to — the SAM-owned ``config#mail`` row — not from the
legacy MySQL ``members.*`` params. ``mail_reply_to_default`` is SAM-only net-new (spec task
5.1 — it has no MySQL row at all) and the other mail params' MySQL rows are being retired
(5.5/5.8), so reading the authoring form from MySQL is the wrong source: a saved value reads
back blank. ``get_field_config`` therefore surfaces the full reader-shaped ``config#mail``
body on the ``GET /members/field-config`` response as ``mail_config`` so the form reads exactly
what was written (writer/reader cannot drift).

This module owns only the **seam** — the ``Protocol`` the domain depends on plus a static
reference provider — so the service that surfaces the body (``get_field_config``) stays
storage-agnostic and tenant-agnostic, exactly mirroring :mod:`sam.members.domain.mail_gate` /
:mod:`sam.members.domain.default_page_size`. The SAM-plane concrete provider is the
DynamoDB-backed projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
``get_mail_config`` already satisfies this ``Protocol`` by duck-typing); tests pass a static one.

``mail_enabled`` keeps its OWN :class:`sam.members.domain.mail_gate.MailGateProvider` seam for
the pivot output-actions gate (a separate consumer, R0/R1); this mail-config seam is the
authoring read. Both ultimately read the same ``config#mail`` row via the reader.

Empty-is-valid / fail-closed
----------------------------
A tenant with no provider wired or no ``config#mail`` row resolves to the fail-closed minimal
body (``mail_enabled``/``mail_certified`` ``False``, ``mail_local_part`` ``"noreply"``, no
``mail_domain`` / ``mail_reply_to_default`` / ``consent_notice``) — never a raise. This is the
same discipline the reader enforces (:meth:`MembersProjectionReader.get_mail_config`); the
static provider and the default mirror it so tests and production agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "MailConfigProvider",
    "StaticMailConfigProvider",
    "fail_closed_mail_config",
]


def fail_closed_mail_config() -> dict[str, Any]:
    """Return the fail-closed minimal ``config#mail`` body (un-authored / no row).

    The same safe defaults :meth:`MembersProjectionReader.get_mail_config` yields for a missing
    row: mail not enabled, not certified, ``noreply`` local-part, and no optional attributes.
    A NEW dict each call so a caller can never mutate a shared default.
    """
    return {
        "mail_enabled": False,
        "mail_local_part": "noreply",
        "mail_certified": False,
    }


@runtime_checkable
class MailConfigProvider(Protocol):
    """Read-only provider of a tenant's full ``config#mail`` body (the mail-config seam).

    Mirrors :class:`sam.members.domain.mail_gate.MailGateProvider`: the domain depends on this
    ``Protocol``, never on where the body lives. The SAM-plane concrete provider is the
    DynamoDB-backed projection reader (``get_mail_config`` satisfies this by duck-typing); tests
    pass a static one.
    """

    def get_mail_config(self, tenant_id: str) -> dict[str, Any]:
        """Return the reader-shaped ``config#mail`` body (fail-closed minimal body when unset)."""
        ...


class StaticMailConfigProvider:
    """In-memory :class:`MailConfigProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: body}`` map. A tenant with no entry resolves to the fail-closed
    minimal body (:func:`fail_closed_mail_config`), matching the DynamoDB-backed reader's
    behaviour so tests and production agree. The default (no map) is the empty provider: every
    tenant resolves to the fail-closed body — mail config reads as un-authored until projected.
    """

    def __init__(self, config_by_tenant: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._config_by_tenant = {k: dict(v) for k, v in dict(config_by_tenant or {}).items()}

    def get_mail_config(self, tenant_id: str) -> dict[str, Any]:
        entry = self._config_by_tenant.get(tenant_id)
        if entry is None:
            return fail_closed_mail_config()
        return dict(entry)
