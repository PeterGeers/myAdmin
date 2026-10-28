"""Scope-config + scope-grant reads for the Members projection config reader (design C4).

INTERNAL helper module of :mod:`sam.members.repository.projection_config_reader` — extracted
from the large reader class (code-quality file-length split, 2026-10-28) with **zero behaviour
change**. :class:`_ScopeReadMixin` is composed into the public ``MembersProjectionReader``; it
relies on the shared read infrastructure from :class:`_config_reader_base._ConfigReaderBase`
(``_find_config_row`` / ``_query_partition`` / ``_classify``) resolved via the composed class'
MRO. Nothing imports this module directly except the reader facade.
"""

from __future__ import annotations

from services import projection_schema as schema

from sam.members.domain.scope_dimensions import ScopeConfig, ScopeDimension

from sam.members.repository._config_reader_base import _CONFIG_ID_SCOPE


class _ScopeReadMixin:
    """The ``ScopeConfigProvider`` + scope-grant reads (R1.4/R1.6/R2.3/R2.6)."""

    # ── ScopeConfigProvider ──────────────────────────────────────────────────────────

    def get_scope_config(self, tenant_id: str) -> ScopeConfig:
        """Return the tenant's :class:`ScopeConfig` from the ``config#scope`` row (R1.4/R1.6).

        Reads the tenant partition, finds the ``config#scope`` row, and rebuilds its
        ``dimensions`` list into :class:`ScopeDimension` objects (mapped 1:1). A **missing**
        row → ``ScopeConfig(tenant_id, dimensions=())`` (tenant-wide), never an error (R1.6).

        Args:
            tenant_id: The tenant (partition key) whose scope config to resolve.

        Returns:
            The tenant's :class:`ScopeConfig` (empty dimensions when unconfigured).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_SCOPE)
        if row is None:
            return ScopeConfig(tenant_id=tenant_id, dimensions=())

        raw_dimensions = row.get("dimensions") or []
        dimensions = tuple(
            self._build_dimension(raw)
            for raw in raw_dimensions
            if isinstance(raw, dict)
        )
        return ScopeConfig(tenant_id=tenant_id, dimensions=dimensions)

    @staticmethod
    def _build_dimension(raw: dict) -> ScopeDimension:
        """Map a projected dimension dict onto a :class:`ScopeDimension` (1:1)."""
        return ScopeDimension(
            key=raw.get("key", ""),
            # `field` binds the dimension to a member field; defaults to the dimension `key`
            # (matching the domain model's back-compat default) when unprojected.
            field=raw.get("field") or raw.get("key"),
            label=dict(raw.get("label") or {}),
            enabled=bool(raw.get("enabled", True)),
            values=tuple(raw.get("values") or ()),
            # s5d clean break (R2.2/R8.1): no `all_wildcard` role-name — a stray projected key
            # is simply ignored; the all-access sentinel lives on the GRANT side as `["*"]`.
            required_for=tuple(raw.get("required_for") or ()),
        )

    # ── Scope grants (consumed by the edge, task 8.3) ──────────────────────────────────

    def get_scope_grants(self, tenant_id: str, email: str) -> dict[str, list[str]]:
        """Return ``{dimension -> [values] | ["*"]}`` for ``email`` in ``tenant_id`` (R2.3).

        Reads the tenant partition and keeps the ``scopegrant#<email>#<dimension>`` rows whose
        email segment equals ``email`` (mirroring the role-filter in
        ``ProjectionGovernanceReader.get_user_roles_by_tenant``). Each kept row contributes
        ``{dimension: values}``, where ``values`` is the granted subset or ``["*"]`` for
        all-access. A dimension with no grant for this caller is simply **absent** from the
        map — the edge then applies deny-by-default via ``required_for`` (R2.6). Never raises
        on missing/empty data.

        Args:
            tenant_id: The tenant (partition key) to read grants from.
            email: The calling user's email (from the verified token).

        Returns:
            ``{dimension: values}`` for the caller's granted dimensions only (possibly empty).
        """
        grants: dict[str, list[str]] = {}
        if not email:
            return grants
        for item in self._query_partition(tenant_id):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_SCOPEGRANT:
                continue
            # scopegrant#<email>#<dimension> — id_parts == (email, dimension). Filter to caller.
            if len(id_parts) < 2 or id_parts[0] != email:
                continue
            # Prefer the explicit 'dimension' attr if present; else the key segment.
            dimension = item.get("dimension") or id_parts[1]
            values = item.get("values") or []
            grants[dimension] = list(values)
        return grants
