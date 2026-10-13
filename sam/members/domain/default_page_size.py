"""
Phase 2 step (a) — the **default-page-size seam** (Members config redesign, R2.1).

Phase 2 retires ``view_contexts`` and re-homes its one live default — the per-context
``page_size`` — to a SINGLE tenant-level ``default_page_size`` scalar carried on the
existing ``config#fields`` row (``38`` rule 3: pagination is a *default*, not a stored view
object). ``get_field_config`` surfaces it on the ``GET /members/field-config`` response as
``default_page_size`` so the SPA resolves rows-per-page as
``userPreference ?? default_page_size ?? platformDefault``.

This module owns only the **seam** — the ``Protocol`` the domain depends on plus a static
reference provider — so the service that surfaces the scalar (``get_field_config``) stays
storage-agnostic and tenant-agnostic, exactly mirroring
:mod:`sam.members.domain.mail_gate` /
:mod:`sam.members.domain.scope_dimensions`. The SAM-plane concrete provider is the
DynamoDB-backed projection reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`, whose
``get_default_page_size`` already satisfies this ``Protocol`` by duck-typing); tests pass a
static one.

Empty-is-valid / fail-safe (R2.4)
---------------------------------
A tenant with no provider wired, no ``config#fields`` row, or no authored
``default_page_size`` resolves to ``None`` — the renderer then falls back to the per-user
preference and finally the platform table-toolkit default (today's behaviour when a
``view_context.page_size`` was null). This is the same discipline the reader enforces
(:meth:`MembersProjectionReader.get_default_page_size`); the static provider and the default
mirror it so tests and production agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

__all__ = [
    "DefaultPageSizeProvider",
    "StaticDefaultPageSizeProvider",
]


@runtime_checkable
class DefaultPageSizeProvider(Protocol):
    """Read-only provider of a tenant's default rows-per-page (the default-page-size seam).

    Mirrors :class:`sam.members.domain.mail_gate.MailGateProvider`: the domain depends on
    this ``Protocol``, never on where the scalar lives. The SAM-plane concrete provider is
    the DynamoDB-backed projection reader (``get_default_page_size`` satisfies this by
    duck-typing); tests pass a static one.
    """

    def get_default_page_size(self, tenant_id: str) -> int | None:
        """Return the tenant's default rows-per-page (positive int, or ``None`` when unset)."""
        ...


class StaticDefaultPageSizeProvider:
    """In-memory :class:`DefaultPageSizeProvider` — the tenant-agnostic reference provider.

    Holds a ``{tenant_id: page_size}`` map. A tenant with no entry (or a non-positive /
    non-int / boolean value) resolves to ``None`` (empty-is-valid, R2.4), matching the
    DynamoDB-backed reader's behaviour so tests and production agree. The default (no map) is
    the empty provider: every tenant resolves to ``None`` — the renderer then applies the
    per-user preference and finally the platform default.
    """

    def __init__(self, page_size_by_tenant: Mapping[str, int] | None = None) -> None:
        self._page_size_by_tenant = dict(page_size_by_tenant or {})

    def get_default_page_size(self, tenant_id: str) -> int | None:
        value = self._page_size_by_tenant.get(tenant_id)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if value > 0 else None
