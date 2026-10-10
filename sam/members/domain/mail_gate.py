"""
pivot-output-actions R0 / R1 (task 1.3) — the **mail-enabled gate seam** (design §6.3).

A per-tenant "mail-enabled / SES-certified" flag records whether a tenant is cleared to
send mail (R0). It is OWNED by the tenant-admin module (Flask writes it to MySQL
``parameters``), projected one-directionally into ``governance_projection`` as the
``config#mail`` row, and READ on the Members plane via the projection reader — a Lambda
never queries MySQL at request time (ADR 0005/0006, steering 36). The mail output actions
(R1–R5) are OFFERED only when the flag is set.

This module owns only the **seam** — the ``Protocol`` the domain depends on plus a
static reference provider — so the service that surfaces the flag (``get_field_config``)
stays storage-agnostic and tenant-agnostic, exactly mirroring
:mod:`sam.members.domain.view_contexts` / :mod:`sam.members.domain.scope_dimensions`. The
SAM-plane concrete provider is the DynamoDB-backed projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
``is_mail_enabled`` already satisfies this ``Protocol`` by duck-typing); tests pass a
static one.

Fail-closed (R0)
----------------
The gate opens ONLY on an explicit projected ``True``. A tenant with no provider wired, no
``config#mail`` row, or a missing/non-``True`` flag resolves to ``False`` — the absence of
the projection never permits sending. This is the same discipline the reader enforces
(:meth:`MembersProjectionReader.is_mail_enabled`); the static provider and the default
mirror it so tests and production agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

__all__ = [
    "MailGateProvider",
    "StaticMailGateProvider",
]


@runtime_checkable
class MailGateProvider(Protocol):
    """Read-only provider of a tenant's mail-enabled gate flag (the mail-gate seam).

    Mirrors :class:`sam.members.domain.view_contexts.ViewContextsProvider` /
    :class:`sam.members.domain.scope_dimensions.ScopeConfigProvider`: the domain depends on
    this ``Protocol``, never on where the flag lives. The SAM-plane concrete provider is the
    DynamoDB-backed projection reader (``is_mail_enabled`` satisfies this by duck-typing);
    tests pass a static one.
    """

    def is_mail_enabled(self, tenant_id: str) -> bool:
        """Return whether the tenant is cleared to send mail (fail-closed → ``False``)."""
        ...


class StaticMailGateProvider:
    """In-memory :class:`MailGateProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: enabled}`` map. A tenant with no entry resolves to ``False``
    (fail-closed, R0), matching the DynamoDB-backed reader's behavior so tests and
    production agree. The default (no map) is the empty, fail-closed provider: every tenant
    resolves to ``False`` — mail is not offered until the flag is explicitly projected.
    """

    def __init__(self, enabled_by_tenant: Mapping[str, bool] | None = None) -> None:
        self._enabled_by_tenant = dict(enabled_by_tenant or {})

    def is_mail_enabled(self, tenant_id: str) -> bool:
        return self._enabled_by_tenant.get(tenant_id) is True
