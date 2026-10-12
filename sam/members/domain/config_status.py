"""
Phase 0 step 3 (Members config redesign impact-analysis §2 / risk #6) — the **config
delivered/loaded status seam**.

The ``members.*`` config is authored on the Flask/MySQL plane and projected one-directionally
into ``governance_projection`` as the ``config#scope`` / ``config#fields`` / ``config#views`` /
``config#mail`` rows (steering 36, ADR 0005/0006). Until now the Members plane read those rows
but never exposed *which version it is serving*, so a stale or never-delivered config was
invisible: a Tenant Admin edits a param and has no way to see whether that edit has been
projected (delivered) and is what the module reads (loaded).

This module owns only the **seam** — the ``Protocol`` the domain depends on plus a static
reference provider — so the service that surfaces the status (``get_field_config``) stays
storage-agnostic and tenant-agnostic, exactly mirroring :mod:`sam.members.domain.mail_gate` /
:mod:`sam.members.domain.view_contexts`. The SAM-plane concrete provider is the DynamoDB-backed
projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
``get_config_status`` already satisfies this ``Protocol`` by duck-typing); tests pass a static
one.

Empty-is-valid
--------------
A tenant with no provider wired, or no projected rows, resolves to every config id mapping to
``None`` ("not yet delivered") — never a raise. This mirrors the reader
(:meth:`MembersProjectionReader.get_config_status`); the static provider and the default mirror
it so tests and production agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ConfigStatusProvider",
    "StaticConfigStatusProvider",
]


@runtime_checkable
class ConfigStatusProvider(Protocol):
    """Read-only provider of a tenant's projected ``config#*`` delivered/loaded status.

    Mirrors :class:`sam.members.domain.mail_gate.MailGateProvider` /
    :class:`sam.members.domain.view_contexts.ViewContextsProvider`: the domain depends on this
    ``Protocol``, never on where the projection lives. The SAM-plane concrete provider is the
    DynamoDB-backed projection reader (``get_config_status`` satisfies this by duck-typing);
    tests pass a static one.
    """

    def get_config_status(self, tenant_id: str) -> Mapping[str, Any]:
        """Return ``{config_id: version|None}`` for the tenant's projected config rows."""
        ...


class StaticConfigStatusProvider:
    """In-memory :class:`ConfigStatusProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: {config_id: version}}`` map. A tenant with no entry resolves to a
    status of all-``None`` (every config id "not yet delivered"), matching the DynamoDB-backed
    reader's empty-is-valid behaviour so tests and production agree. The default (no map) is the
    empty provider: every tenant reports every config id as un-delivered.
    """

    #: The config ids the status always reports (the four projected ``config#*`` rows), so a
    #: tenant with no entry still yields a complete, explicit all-``None`` status rather than an
    #: empty dict — the SPA can always render a row per config id.
    _CONFIG_IDS = ("scope", "fields", "views", "mail")

    def __init__(
        self, status_by_tenant: Mapping[str, Mapping[str, Any]] | None = None
    ) -> None:
        self._status_by_tenant = {
            tenant: dict(status) for tenant, status in (status_by_tenant or {}).items()
        }

    def get_config_status(self, tenant_id: str) -> dict[str, Any]:
        authored = self._status_by_tenant.get(tenant_id, {})
        return {cid: authored.get(cid) for cid in self._CONFIG_IDS}
