"""Governance projection — the ``config#scope`` row builder (C2, R1.1/R1.2/R2.1).

INTERNAL helper module of :mod:`services._projection_config_builders` — extracted from it
(code-quality file-length split, 2026-10-28) with **zero behaviour change**. Owns the
scope-dimension mapping + the scope-as-field-attribute derivation and :func:`build_config_scope_row`.
Re-exported from the facade :mod:`services._projection_config_builders` (and from
:mod:`services.projection_sync`), so the public import surface is unchanged.

One-directional discipline (Property 1): the builder issues **zero** MySQL writes and does
**not** write the projection itself — it only READS via ``ParameterService`` (read-only
``get_param``) and RETURNS the item for the sole writer (:class:`services.projection_sync.ProjectionSync`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services import projection_schema as schema
from services._projection_config_common import (
    _FIELD_OVERLAY_PARAM_KEY,
    _MEMBERS_PARAM_NAMESPACE,
    _config_row_version,
    _enum_values_from_field,
)
from services.projection_builder import ProjectionItem

#: The fields a single projected dimension entry carries — the exact shape
#: ``ScopeDimension`` consumes (design.md "New governance projection rows",
#: ``config#scope``). Each is mapped from the authored parameter dict with a
#: safe default so a partial authoring never yields a malformed dimension.
_DIMENSION_DEFAULTS: dict[str, Any] = {
    "key": None,
    "field": None,
    "label": dict,
    "enabled": True,
    "values": list,
    "required_for": list,
}


def _map_scope_dimension(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one authored dimension dict to the ``config#scope`` dimension shape.

    Pure mapping of a single tenant-authored dimension parameter entry into the
    exact field set ``ScopeDimension`` consumes (``key``, ``field``, ``label``,
    ``enabled``, ``values``, ``required_for``). The s5d clean break (R2.2/R8.1)
    dropped the ``Regio_*`` role encoding: the ``all_wildcard`` role-name and the
    ``multi_valued`` flag are GONE — scope is sourced from ``user_tenant_scope``,
    not decoded from a role name, and the all-access sentinel lives on the GRANT
    side as ``["*"]`` (see :data:`WILDCARD_VALUE`). Unknown extra keys in the
    authored dict are dropped (the row carries only the shape the domain reads);
    absent fields fall back to a safe default so a partially authored dimension
    still yields a well-formed entry rather than raising.
    """
    dimension: dict[str, Any] = {}
    for field_name, default in _DIMENSION_DEFAULTS.items():
        if field_name in raw and raw[field_name] is not None:
            dimension[field_name] = raw[field_name]
        else:
            dimension[field_name] = default() if callable(default) else default
    return dimension


#: Phase 3 step 9 (R2.1/R2.3/R2.4/R2.5) — the field-attribute key under which a
#: ``members.field_overlay`` field expresses that it is a SCOPE AXIS. Authoring moves
#: from the standalone ``members.scope_dimensions`` list onto the field itself: a field
#: (a fixed field via ``fixed_overrides``, or an added variable field via ``fields``)
#: carries a ``scope`` sub-object ``{enabled, required_for?, label?}`` — single-vocabulary
#: (R3.4): the dimension ``values`` are DERIVED from the field's own enum values
#: (``options[].value`` / ``choices``), NOT a separate ``scope.values`` (legacy fallback only).
#: The dimension ``key`` and the bound ``field`` BOTH derive from the field's own key, so a
#: field is a scope axis bound to itself — exactly how every current dimension already
#: binds (``ScopeDimension.field`` defaults to its ``key``). The builder DERIVES the
#: ``config#scope`` row from these attributes, keeping the PROJECTED row — and therefore
#: the ``ScopeConfig`` the resolver consumes — SEMANTICALLY EQUIVALENT (Property 2). The
#: resolver (``handler/app.py``) and the ``scopegrant#`` grants are untouched (R2.3/R2.4).
_FIELD_SCOPE_ATTR = "scope"


def _scope_dimension_from_field(
    field_key: str, scope: Mapping[str, Any], spec: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive one ``config#scope`` dimension from a field's ``scope`` attribute (R3.4).

    The dimension ``key`` and bound ``field`` are the field's own key — a field authored
    as a scope axis binds the dimension to itself (matching the domain default where
    ``ScopeDimension.field`` falls back to its ``key``).

    **Single-vocabulary (R3.2/R3.4):** the dimension ``values`` are DERIVED from the field's
    ENUM VALUES (:func:`_enum_values_from_field` — ``options[].value`` / ``choices``) when the
    scope axis is ENABLED, NOT from ``scope.values``. The field's enum-values editor is the ONE
    vocabulary; marking the field a scope axis references that list. A legacy stored
    ``scope.values`` is honoured as a FALLBACK ONLY — used when the field carries no enum
    vocabulary (a tenant whose authoring predates the single-vocabulary model). The remaining
    dimension aspects (``enabled`` / ``label`` / ``required_for``) come from the ``scope``
    sub-object, defaulted exactly as :func:`_map_scope_dimension` defaults a standalone
    dimension — so a field-authored dimension and the equivalent standalone one project to the
    SAME row (Property 2, semantic equivalence).
    """
    # Single-vocabulary: the enum values ARE the scope values. `scope.values` is a legacy
    # fallback only (honoured when the field carries no enum vocabulary).
    values = _enum_values_from_field(spec)
    if values is None:
        values = scope.get("values")
    raw = {
        "key": field_key,
        "field": field_key,
        "label": scope.get("label"),
        "enabled": scope.get("enabled", True),
        "values": values,
        "required_for": scope.get("required_for"),
    }
    return _map_scope_dimension(raw)


def _scope_dimensions_from_overlay(overlay: Any) -> list[dict[str, Any]]:
    """Derive the ``config#scope`` dimensions from scope attributes on overlay fields (R2.1).

    Scans a ``members.field_overlay`` object for fields that declare a ``scope`` attribute —
    both added variable fields (``fields``) and fixed-field re-presentations
    (``fixed_overrides``) — and maps each onto a dimension dict (keyed by the field's own
    key). Order is deterministic: fixed-override scope axes first (in authored order),
    then variable-field scope axes, de-duplicated by dimension key (first wins), so the
    derived list is stable across re-syncs. A malformed/absent overlay yields ``[]`` — the
    builder then falls back to the standalone ``scope_dimensions`` param (empty-is-valid).
    """
    if not isinstance(overlay, Mapping):
        return []

    dimensions: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def _collect(container: Any) -> None:
        if not isinstance(container, Mapping):
            return
        for name, spec in container.items():
            if not isinstance(spec, Mapping):
                continue
            scope = spec.get(_FIELD_SCOPE_ATTR)
            if not isinstance(scope, Mapping):
                continue
            field_key = spec.get("key") or name
            if not isinstance(field_key, str) or not field_key:
                continue
            # A dotted fixed-override key (e.g. ``personal.region``) binds the dimension to
            # the bare field key — the member-record scope field the resolver reads.
            bare_key = field_key.split(".")[-1]
            if bare_key in seen_keys:
                continue
            seen_keys.add(bare_key)
            # Single-vocabulary (R3.4): the dimension values derive from the field's OWN enum
            # vocabulary (`spec`), not from `scope.values` — so `spec` is threaded through.
            dimensions.append(_scope_dimension_from_field(bare_key, scope, spec))

    # Fixed-override scope axes first (authored order), then variable-field scope axes.
    _collect(overlay.get("fixed_overrides"))
    _collect(overlay.get("fields"))
    return dimensions


def build_config_scope_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#scope`` projection item (S5b C2, R1.1/R1.2).

    Shapes the tenant's scope-dimension definitions into the ``config#scope`` row's
    ``dimensions`` list — the shape ``sam/members/domain/scope_dimensions.py``
    ``ScopeDimension`` consumes (``key``, ``field``, ``label``, ``enabled``,
    ``values``, ``required_for``). The ``Regio_*`` role encoding is removed (s5d
    clean break, R2.2/R8.1) — no ``all_wildcard``/``multi_valued``.

    **Scope-as-field-attribute (Phase 3 step 9, R2.1/R2.5).** The AUTHORING
    representation is a ``scope`` attribute on a ``members.field_overlay`` field
    (``_scope_dimensions_from_overlay``): a field declares that it is a scope axis,
    enabled, with its value vocabulary, instead of a standalone
    ``members.scope_dimensions`` list. The builder DERIVES the ``config#scope``
    ``dimensions`` from those field attributes (``_scope_dimensions_from_overlay``)
    — the SINGLE authoring source (OQ-3 RESOLVED, ODD 3). The legacy standalone
    ``members.scope_dimensions`` fallback was REMOVED (task 3.1): it silently masked
    overlay toggle changes (the dead-toggle defect), so toggling a field's ``scope``
    could appear to do nothing while a stale standalone param kept driving the row.
    With the fallback gone the overlay toggle has real effect. The standalone
    ``members.scope_dimensions`` param is NOT read here anymore and is NOT deleted —
    it persists as the frontend-written DERIVED MIRROR (task 3.1a) that the
    ``scopegrant#`` grants, the grant-validation service, and the picker API keep
    reading UNCHANGED (R2.3/R2.4); those readers are out of scope for this builder.

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope rows read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    pure ``tenant``/``module``/``role`` builders in ``projection_builder.py``.

    Empty-is-valid (R1.6): a tenant whose overlay declares no field scope axis
    yields a row with an empty ``dimensions`` list — the reader then resolves it to a
    tenant-wide config, never an error. Returning the row (rather than ``None``) keeps
    the projection self-describing; an empty list is the tenant-wide collapse.

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.

    Returns:
        The ``config#scope`` :class:`ProjectionItem` for this tenant. ``None`` is
        never returned for a present tenant — an un-configured tenant still gets a
        well-formed empty-dimensions row.

    Raises:
        ValueError: The tenant is missing its ``administration``/``tenant_id`` key.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )

    # Scope-as-field-attribute first (Phase 3 step 9): derive the dimensions from the
    # ``members.field_overlay`` field scope attributes. The overlay is the canonical
    # authoring surface for a tenant migrated to field-attribute scope.
    overlay = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _FIELD_OVERLAY_PARAM_KEY,
        tenant=tenant_id,
    )
    dimensions = _scope_dimensions_from_overlay(overlay)

    # OQ-3 RESOLVED (ODD 3): config#scope is DERIVED SOLELY from the per-field ``scope``
    # attributes on the ``members.field_overlay`` overlay — the single authoring source.
    # The legacy standalone ``members.scope_dimensions`` fallback was REMOVED (task 3.1,
    # the dead-toggle defect fix): a silent fallback masked overlay toggle changes, so
    # toggling a field's ``scope`` could appear to have no effect while a stale standalone
    # param kept driving the row. With the fallback gone the overlay toggle has real
    # effect; an overlay that declares no scope axis yields EMPTY dimensions — a valid,
    # tenant-wide config (R1.6), never an error.
    #
    # The standalone ``members.scope_dimensions`` param is NOT read here anymore, but it is
    # NOT deleted: it persists as the frontend-written DERIVED MIRROR (task 3.1a) that the
    # scopegrant builder, the grant-validation service, and the picker API keep reading
    # UNCHANGED (R2.3/R2.4). Those readers are out of scope for this builder.

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_SCOPE
        ),
        # config#scope derives only from the overlay now, so the row version tracks ONLY
        # the overlay param's revision — a stale standalone ``scope_dimensions`` param can
        # no longer bump the config#scope version (it is no longer a source).
        version=_config_row_version(
            tenant,
            parameter_service,
            tenant_id,
            (_FIELD_OVERLAY_PARAM_KEY,),
        ),
        attributes={"dimensions": dimensions},
    )
