"""Governance projection — read-only source seam (extracted from ``projection_sync``).

The source-side of the one-directional MySQL->DynamoDB sync (design.md D2): the
immutable :class:`TenantSource` snapshot of one tenant's governance rows, the narrow
:class:`SourceProvider` Protocol the sync depends on, and the default
:class:`DatabaseSourceProvider` that reads MySQL **read-only** through ``DatabaseManager``.
Re-exported from :mod:`services.projection_sync`; its public import surface is unchanged.

Read-only guarantee (R5.1/R5.2/R5.9): the provider issues **only** SELECTs — it has no
write method — so the sync's one-directional discipline holds structurally. Pure
structural split (code-quality M2) with zero behaviour change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class TenantSource:
    """The read-only governance rows for one ``administration`` (design.md D2).

    A plain, immutable snapshot of the three source tables scoped to one tenant.
    The sync consumes this and never mutates it — it is the *input* to the pure
    builder, not a writable store.

    Attributes:
        tenant: The ``tenants`` row (carries ``administration``/tenant fields).
        tenant_modules: The tenant's ``tenant_modules`` rows.
        user_tenant_roles: The tenant's ``user_tenant_roles`` rows.
        user_tenant_scope: The tenant's ``user_tenant_scope`` rows — each shaped
            ``{email, module, scopes, updated_at}`` (``scopes`` a JSON column carried
            as-is; it may arrive as a JSON string or already-parsed depending on the
            driver — the ``build_scopegrant_rows`` builder parses it). This is the
            NEW s5d source of the ``scopegrant#…`` grant, replacing the ``Regio_*``
            role decode (R2.1; design → Projection Components items 1–2).
            ``updated_at`` (the table's ``ON UPDATE CURRENT_TIMESTAMP`` column) is the
            per-row freshness signal ODx4a uses so an UPDATED grant supersedes the
            stored projection row (design → freshness FRESHNESS HAZARD; R2.4).
    """

    tenant: Mapping[str, Any]
    tenant_modules: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    user_tenant_roles: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    user_tenant_scope: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


@runtime_checkable
class SourceProvider(Protocol):
    """Read-only provider of governance source rows (the sync's MySQL seam).

    Implementations MUST NOT write MySQL — the projection is one-directional
    (R5.1/R5.2/R5.9). The default implementation reads through ``DatabaseManager``
    with parameterized queries; tests substitute an in-memory fake.
    """

    def get_tenant_source(self, administration: str) -> TenantSource | None:
        """Return the source rows for ``administration``, or ``None`` if absent."""
        ...

    def list_administrations(self) -> list[str]:
        """Return every ``administration`` the sync could project."""
        ...


class DatabaseSourceProvider:
    """`SourceProvider` backed by MySQL through ``DatabaseManager`` (read-only).

    Reads ``tenants`` / ``tenant_modules`` / ``user_tenant_roles`` with
    parameterized ``%s`` queries scoped by ``administration`` (workspace
    database-patterns; tenant-scoped filtering, no cross-tenant reads). Issues
    **only** SELECTs — never a write — so the sync's one-directional guarantee
    (R5.1/R5.2/R5.9) holds structurally: this class has no write method.
    """

    def __init__(self, db: Any) -> None:
        """Args: db: a ``DatabaseManager`` (or anything with ``execute_query``)."""
        self._db = db

    def list_administrations(self) -> list[str]:
        rows = self._db.execute_query(
            "SELECT administration FROM tenants", (), fetch=True
        )
        return [r["administration"] for r in (rows or []) if r.get("administration")]

    def get_tenant_source(self, administration: str) -> TenantSource | None:
        if not administration:
            raise ValueError(
                "administration must be non-empty — a blank tenant scope is a "
                "cross-tenant hazard (R5.4)"
            )

        tenant_rows = self._db.execute_query(
            "SELECT * FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        if not tenant_rows:
            return None

        module_rows = self._db.execute_query(
            "SELECT * FROM tenant_modules WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        role_rows = self._db.execute_query(
            "SELECT email, role FROM user_tenant_roles WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        scope_rows = self._db.execute_query(
            # ``updated_at`` (``ON UPDATE CURRENT_TIMESTAMP`` on the table) is the
            # per-row freshness signal ODx4a uses so a grant CHANGE supersedes the
            # stored scopegrant row (see ``build_scopegrant_rows`` / ``_scopegrant_version``).
            "SELECT email, module, scopes, updated_at FROM user_tenant_scope "
            "WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        return TenantSource(
            tenant=tenant_rows[0],
            tenant_modules=list(module_rows or ()),
            user_tenant_roles=list(role_rows or ()),
            user_tenant_scope=list(scope_rows or ()),
        )


__all__ = [
    "DatabaseSourceProvider",
    "SourceProvider",
    "TenantSource",
]
