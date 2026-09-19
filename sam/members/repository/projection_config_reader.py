"""
S5b Task 8.1 — the Members module **projection config reader** (design C4).

A read-only, ``boto3``-backed consumer of the S3/S5b governance projection that feeds the
S5 Members domain seams with **real projected data**. It mirrors
:mod:`sam.pretokengen.projection_governance_reader` exactly — one DynamoDB ``Query`` per
tenant partition, a per-invocation cache so a partition is read at most once, fail-fast
table resolution via :mod:`services.projection_schema`, and *empty-is-valid* everywhere —
but reconstructs the **S5b** projected rows (``config#scope`` / ``config#fields`` /
``scopegrant#<email>#<dimension>``) into the storage-agnostic domain shapes the UNCHANGED
domain consumes.

Why this exists (design C4)
---------------------------
The S5 domain (``scope_dimensions`` / ``field_resolver`` / ``scope_access``) is deliberately
storage-agnostic: it depends on two ``Protocol`` seams —
:class:`sam.members.domain.scope_dimensions.ScopeConfigProvider` and
:class:`sam.members.domain.field_resolver.TenantOverlayProvider` — never on where the config
lives. S5 shipped in-memory ``Static*`` providers as the reference. This reader is the
SAM-plane concrete provider that replaces them (task 8.2 wires it into cold start): it reads
the projection the S5b builders (tasks 5.1/5.2/5.3) populate and returns exactly the domain
dataclasses those seams expect, so it can be handed straight to ``FieldResolver`` /
``resolve_scope_access`` (duck-typed to the Protocols). It **reads only** — it never writes
MySQL or the projection.

Layering
--------
SAM-plane **infrastructure adapter**: it depends on ``boto3`` + the projection schema and
produces the domain shapes. The domain never imports it (dependency inversion — the arrow
points inward, exactly like ``FieldConfigMixin`` → ``parameter_service`` in the Flask plane).

Projected row shapes consumed (built by tasks 5.1/5.2/5.3)
----------------------------------------------------------
- ``config#scope``: ``dimensions`` = list of dicts (``key``/``label``/``enabled``/
  ``multi_valued``/``values``/``all_wildcard``/``required_for``) → mapped 1:1 onto
  :class:`ScopeDimension`; the whole row → :class:`ScopeConfig`. A **missing row** →
  ``ScopeConfig(tenant_id, dimensions=())`` (tenant-wide), never an error (R1.6).
- ``config#fields``: ``fields`` = ``{name: {key,type,required,label,choices,visible,order}}``
  and ``overrides`` = ``{dotted: {label?,visible?,required?,order?}}`` →
  :class:`TenantOverlay`. The projected ``type`` is a *string*; it is converted to
  :class:`FieldType` (unknown/missing → :data:`FieldType.STRING`). A ``FixedFieldOverride``
  only carries the aspects actually present (a missing aspect stays ``None`` → "leave the
  base as-is"). A **missing row** → ``TenantOverlay()`` (fixed base only), never an error
  (R1.7).
- ``scopegrant#<email>#<dimension>``: ``dimension`` (str), ``values`` (list[str], or
  ``["*"]`` for all-access). :meth:`get_scope_grants` returns ``{dimension: values}`` for the
  **caller's** rows only — filtered by the email segment of the SK, mirroring how
  ``ProjectionGovernanceReader.get_user_roles_by_tenant`` filters ``role#<email>#<role>`` rows
  by ``id_parts[0] == email``. A missing grant is simply **absent** from the map (the edge
  then applies deny-by-default via ``required_for`` — R2.6).

Config + fail-fast (R4.1)
-------------------------
The table name is resolved from ``GOVERNANCE_PROJECTION_TABLE`` via the S3 fail-fast client
(:func:`services.projection_schema.get_projection_table_resource`) — missing/blank throws,
no dangerous default, resolved lazily on first real Query. In production the Lambda's IAM
role grants read on the projection table; ``AWS_ENDPOINT_URL_DYNAMODB`` is left UNSET (real
AWS) and only set for local testing against the T0 ``dynamodb-local`` container.
"""

from __future__ import annotations

from typing import Optional

from services import projection_schema as schema

from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    OverlayField,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.scope_dimensions import ScopeConfig, ScopeDimension

__all__ = ["MembersProjectionReader"]

#: The two ``config#<id>`` rows the reader consumes (design C4 / task 4.1 tokens).
_CONFIG_ID_SCOPE = "scope"
_CONFIG_ID_FIELDS = "fields"


class MembersProjectionReader:
    """Read-only Members config/grant reader backed by the governance projection (C4).

    Implements the S5 domain seams by duck-typing:

    - :meth:`get_scope_config` → :class:`ScopeConfigProvider`
      (``sam.members.domain.scope_dimensions``);
    - :meth:`get_overlay` → :class:`TenantOverlayProvider`
      (``sam.members.domain.field_resolver``);
    - :meth:`get_scope_grants` → the caller's projected scope grants (consumed by the edge's
      ``resolve_scope_access`` wiring, task 8.3).

    Mirrors :class:`sam.pretokengen.projection_governance_reader.ProjectionGovernanceReader`:
    one ``Query`` per tenant partition, a per-invocation ``_partition_cache`` so a partition
    is read at most once, and *empty-is-valid* (a missing/empty partition or row is never an
    error — only a missing table env fails fast, at the first real Query).

    Args:
        table: A boto3 DynamoDB Table (or a fake exposing ``query``). Defaults to the
            fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`). Injectable so
            tests use an in-memory fake / local dynamodb-local.
    """

    def __init__(self, table=None):
        self._table = table
        # Per-invocation cache: tenant_id -> list of that partition's items, so a tenant's
        # partition is Queried at most once per invocation.
        self._partition_cache: dict[str, list[dict]] = {}

    @property
    def table(self):
        """The projection table, resolved lazily + fail-fast on first use (R4.1)."""
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    def _query_partition(self, tenant_id: str) -> list[dict]:
        """Return all projected items for ``tenant_id`` (cached, read-only).

        One DynamoDB ``Query`` on the partition key. A missing/empty partition returns ``[]``
        (empty is valid). boto3 is imported lazily so the module imports cleanly where boto3's
        condition types aren't needed (a fake table in tests can bypass this by pre-seeding
        the cache).
        """
        if not tenant_id:
            return []
        if tenant_id in self._partition_cache:
            return self._partition_cache[tenant_id]

        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key(schema.PARTITION_KEY_ATTR).eq(tenant_id)
        )
        items = list(response.get("Items", []) or [])
        self._partition_cache[tenant_id] = items
        return items

    @staticmethod
    def _classify(item: dict) -> tuple[str, tuple[str, ...]]:
        """Return ``(record_type, id_parts)`` for a projected item's sort key.

        A missing/blank sort key classifies as ``("", ())`` so it is simply skipped by the
        callers (never a raise) — empty is valid.
        """
        sk = item.get(schema.SORT_KEY_ATTR, "")
        return schema.split_sort_key(sk) if sk else ("", ())

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
            self._build_dimension(raw) for raw in raw_dimensions if isinstance(raw, dict)
        )
        return ScopeConfig(tenant_id=tenant_id, dimensions=dimensions)

    @staticmethod
    def _build_dimension(raw: dict) -> ScopeDimension:
        """Map a projected dimension dict onto a :class:`ScopeDimension` (1:1)."""
        return ScopeDimension(
            key=raw.get("key", ""),
            label=dict(raw.get("label") or {}),
            enabled=bool(raw.get("enabled", True)),
            multi_valued=bool(raw.get("multi_valued", False)),
            values=tuple(raw.get("values") or ()),
            all_wildcard=raw.get("all_wildcard"),
            required_for=tuple(raw.get("required_for") or ()),
        )

    # ── TenantOverlayProvider ──────────────────────────────────────────────────────────

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        """Return the tenant's :class:`TenantOverlay` from the ``config#fields`` row (R1.5/R1.7).

        Reads the tenant partition, finds the ``config#fields`` row, and rebuilds its
        ``fields`` / ``overrides`` maps into :class:`OverlayField` / :class:`FixedFieldOverride`
        objects. A **missing** row → ``TenantOverlay()`` (fixed base only), never an error
        (R1.7).

        Args:
            tenant_id: The tenant (partition key) whose field overlay to resolve.

        Returns:
            The tenant's :class:`TenantOverlay` (empty when unconfigured).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_FIELDS)
        if row is None:
            return TenantOverlay()

        raw_fields = row.get("fields") or {}
        raw_overrides = row.get("overrides") or {}
        fields = {
            name: self._build_overlay_field(name, spec)
            for name, spec in raw_fields.items()
            if isinstance(spec, dict)
        }
        overrides = {
            dotted: self._build_override(spec)
            for dotted, spec in raw_overrides.items()
            if isinstance(spec, dict)
        }
        return TenantOverlay(fields=fields, overrides=overrides)

    @staticmethod
    def _to_field_type(value) -> FieldType:
        """Convert a projected ``type`` string to :class:`FieldType`.

        Unknown/missing values default to :data:`FieldType.STRING` — a projected type token is
        config data, not user input, so a stray value degrades gracefully rather than raising.
        """
        if isinstance(value, FieldType):
            return value
        try:
            return FieldType(value)
        except (ValueError, TypeError):
            return FieldType.STRING

    @classmethod
    def _build_overlay_field(cls, name: str, spec: dict) -> OverlayField:
        """Map a projected variable-field spec onto an :class:`OverlayField`."""
        choices = spec.get("choices")
        return OverlayField(
            key=spec.get("key") or name,
            type=cls._to_field_type(spec.get("type")),
            required=bool(spec.get("required", False)),
            label=dict(spec.get("label") or {}),
            choices=tuple(choices) if choices is not None else None,
            visible=bool(spec.get("visible", True)),
            order=int(spec.get("order", 0) or 0),
        )

    @staticmethod
    def _build_override(spec: dict) -> FixedFieldOverride:
        """Map a projected fixed-field override onto a :class:`FixedFieldOverride`.

        Only the aspects actually present are passed through; a missing aspect stays ``None``
        so the resolver leaves the base value as-is (design C4 override semantics).
        """
        label = spec.get("label")
        visible = spec.get("visible")
        required = spec.get("required")
        order = spec.get("order")
        return FixedFieldOverride(
            label=dict(label) if isinstance(label, dict) else None,
            visible=bool(visible) if visible is not None else None,
            required=bool(required) if required is not None else None,
            order=int(order) if order is not None else None,
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

    # ── internals ──────────────────────────────────────────────────────────────────────

    def _find_config_row(self, tenant_id: str, config_id: str) -> Optional[dict]:
        """Return the ``config#<config_id>`` row for ``tenant_id``, or ``None`` if absent.

        A missing row is valid (the caller collapses it to the empty/tenant-wide default);
        this never raises on missing/empty data.
        """
        for item in self._query_partition(tenant_id):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_CONFIG:
                continue
            if id_parts and id_parts[0] == config_id:
                return item
        return None
