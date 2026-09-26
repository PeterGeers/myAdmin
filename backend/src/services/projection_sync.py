"""One-directional MySQL->DynamoDB governance projection sync (design.md D3, T16).

S3 (`s3-claims-and-projection`) copies the **tenant-level** governance subset
forward into a DynamoDB projection the SAM/Lambda module plane reads. This module
is the ``ProjectionSync`` named in design.md D3 "Components and interfaces" — the
**sole writer** of the projection table.

What the sync does (design.md D3):

1. **Reads** the relevant governance rows from MySQL (``tenants`` /
   ``tenant_modules`` / ``user_tenant_roles``) scoped by ``administration`` — via
   the injected :class:`SourceProvider`. **Read-only**: the sync issues **ZERO**
   MySQL writes (R5.1, R5.2, R5.9). MySQL remains the sole writer of record.
2. **Builds** projection items from those rows via the pure T12
   :func:`services.projection_builder.build_projection_items`.
3. **Validates** every item via the T14
   :func:`services.projection_validator.validate_items` before any write — a
   malformed item aborts the tenant's sync with **no partial write** (R5.5).
4. **Writes** (put) each item to DynamoDB with a **conditional, versioned** write:
   it writes only when the item is new *or* its ``version`` is strictly greater
   than the stored ``version`` (R5.6). Re-running against an unchanged source is a
   **no-op** — no new writes, no version churn (idempotence).

**Sole writer + one-directional guardrail (R5.1, R5.2, R5.9).** The sync writes
**only** the projection table; nothing else writes it; a module *reads* it and
never writes back. Two-way writes are forbidden (split-brain / cross-tenant
hazard). This module therefore never calls a MySQL write path and never exposes
one.

**Dependency injection (testability).** The sync depends on two narrow seams so
the T17/T18/T22 property tests (and the example tests below) can drive it with
in-memory fakes and never touch real AWS / MySQL:

- a :class:`SourceProvider` — reads the source rows for an ``administration``.
  The default (:class:`DatabaseSourceProvider`) reads MySQL read-only through
  ``DatabaseManager`` with parameterized ``%s`` queries (workspace
  database-patterns). Tests pass an in-memory fake.
- a *table writer* — anything exposing DynamoDB's ``get_item`` / ``put_item``
  (a boto3 ``Table`` in production; an in-memory fake in tests). Resolved lazily
  from :func:`services.projection_schema.get_projection_table_resource` (fail-fast
  env, R4.1) only when not injected, so importing this module never forces AWS
  config.

**Versioning strategy (R5.6).** The conditional write is expressed two ways that
must agree:

- The sync reads the stored item's ``version`` (``get_item``) and decides in
  Python whether the incoming ``version`` supersedes it. This is the logic the
  property tests exercise against an in-memory fake with no boto3 condition
  engine.
- The ``put_item`` also carries a DynamoDB ``ConditionExpression``
  (``attribute_not_exists(version) OR version < :incoming``) so that against a
  *real* concurrent store the write is still guarded at the datastore level. A
  fake table may ignore the expression; a real table enforces it. On a real
  ``ConditionalCheckFailedException`` the write is treated as a benign no-op
  (another writer already advanced the version), preserving idempotence.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from services import projection_schema as schema
from services.projection_builder import (
    ProjectionItem,
    _normalize_version,
    build_projection_items,
)
from services.projection_validator import validate_items
from services.scope_canon import scope_canon

logger = logging.getLogger(__name__)

# --- C2 config#scope builder (S5b design.md C2, R1.1/R1.2) -----------------

#: Parameter namespace that carries the Members module's tenant-scope config
#: data (S5b design.md C2). Tenant Admin authors these via
#: ``ParameterService.set_param(scope="tenant", namespace="members", ...)``
#: (``/api/tenant-admin/parameters``); the ``members.*`` namespace is gated to
#: the active MEMBERS module (``parameter_schema.py``). The builder only READS
#: these — it never writes MySQL (Property 1, one-directional).
_MEMBERS_PARAM_NAMESPACE = "members"

#: The single tenant-scope parameter key that holds the scope-dimension
#: definitions as a JSON list, one entry per dimension. Authored by Tenant Admin
#: (region values Noord/Zuid/Oost/West etc.); read here and mapped 1:1 to the
#: ``config#scope`` row's ``dimensions`` shape that
#: ``sam/members/domain/scope_dimensions.py`` ``ScopeDimension`` consumes.
_SCOPE_DIMENSIONS_PARAM_KEY = "scope_dimensions"

#: The single tenant-scope parameter key that holds the Members field-config
#: overlay as a JSON object with two members-authored maps — ``fields`` (the
#: variable overlay: added "club detail" fields) and ``overrides`` (presentation
#: overrides of fixed fields). Authored by Tenant Admin (same
#: ``/api/tenant-admin/parameters`` surface as ``scope_dimensions``); read here
#: and mapped 1:1 to the ``config#fields`` row's ``fields``/``overrides`` shape
#: that ``sam/members/domain/field_resolver.py`` ``TenantOverlay`` consumes
#: (``TenantOverlay.fields`` = added ``OverlayField``s keyed by canonical key;
#: ``TenantOverlay.overrides`` = ``FixedFieldOverride``s keyed by canonical dotted
#: key ``group.field``). The ``members.*`` namespace declaration/gating to the
#: active MEMBERS module is a later ``[H]`` task (11.x, ``parameter_schema.py``);
#: this builder only READS whatever value exists (Property 1, one-directional).
_FIELD_OVERLAY_PARAM_KEY = "field_overlay"

#: The single tenant-scope parameter key that holds the Members view-context
#: definitions as a JSON list, one entry per context. Authored by Tenant Admin
#: (``members.view_contexts``, S5c Phase 2); read here and shaped into the
#: sibling ``config#views`` row's ``contexts`` list — the shape the SAM-plane
#: view-contexts reader (``projection_config_reader.get_view_contexts``) consumes
#: (``key`` / ``label`` / ``permission_roles`` / ``columns`` /
#: ``filterable_columns`` / ``default_sort`` / ``page_size``). This builder only
#: READS whatever value exists (Property 1, one-directional).
_VIEW_CONTEXTS_PARAM_KEY = "view_contexts"

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


def build_config_scope_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#scope`` projection item (S5b C2, R1.1/R1.2).

    Reads the tenant's Members scope-dimension definitions from the tenant-scope
    parameter system (``ParameterService.get_param`` on the ``members`` namespace,
    key ``scope_dimensions``) and shapes them into the ``config#scope`` row's
    ``dimensions`` list — the shape ``sam/members/domain/scope_dimensions.py``
    ``ScopeDimension`` consumes (``key``, ``field``, ``label``, ``enabled``,
    ``values``, ``required_for``). The ``Regio_*`` role encoding is removed (s5d
    clean break, R2.2/R8.1) — no ``all_wildcard``/``multi_valued``.

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope rows read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    pure ``tenant``/``module``/``role`` builders in ``projection_builder.py``.

    Empty-is-valid (R1.6): a tenant that has authored no ``members.scope_dimensions``
    parameter yields a row with an empty ``dimensions`` list — the reader then
    resolves it to a tenant-wide config, never an error. Returning the row (rather
    than ``None``) keeps the projection self-describing; an empty list is the
    tenant-wide collapse.

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

    raw_dimensions = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _SCOPE_DIMENSIONS_PARAM_KEY,
        tenant=tenant_id,
    )

    dimensions: list[dict[str, Any]] = []
    if isinstance(raw_dimensions, Sequence) and not isinstance(raw_dimensions, str):
        for entry in raw_dimensions:
            if isinstance(entry, Mapping):
                dimensions.append(_map_scope_dimension(entry))

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_SCOPE
        ),
        version=_scope_config_version(tenant),
        attributes={"dimensions": dimensions},
    )


# Version fields the builder reads off the tenant row for the config#scope item,
# in priority order — mirrors projection_builder._VERSION_FIELDS. A row with none
# gets a deterministic 0 so the item is well-formed and re-sync is idempotent.
_SCOPE_VERSION_FIELDS = ("version", "updated_at", "revision", "modified_at")


def _scope_config_version(tenant: Mapping[str, Any]) -> Any:
    """Return the first present, non-null version field on the tenant row, else 0.

    Deterministic (no clock read) so a re-sync on unchanged input reproduces the
    same version — preserving the sync's idempotent/versioned write (R5.6). The
    tenant row's revision is used because ``config#scope`` is tenant-level; a more
    precise per-parameter version can supersede it once the trigger (task 6.x)
    threads a param-change revision through.
    """
    for name in _SCOPE_VERSION_FIELDS:
        value = tenant.get(name)
        if value is not None:
            return _normalize_version(value)
    return 0


# --- C2 config#fields builder (S5b design.md C2, R1.3) ---------------------

#: The fields a single projected variable-overlay entry carries — the exact set
#: ``sam/members/domain/field_resolver.py`` ``OverlayField`` consumes (``key``,
#: ``type``, ``required``, ``label``, ``choices``, ``visible``, ``order``). Each
#: is mapped from the authored parameter dict with a safe default so a partially
#: authored field still yields a well-formed overlay entry rather than raising.
_OVERLAY_FIELD_DEFAULTS: dict[str, Any] = {
    "key": None,
    "type": "string",
    "required": False,
    "label": dict,
    "choices": None,
    "visible": True,
    "order": 0,
    # R4.9: an added field carries its own display group (references the functional_groups
    # catalog). Without this the field falls back to the storage bucket (overlay) and can
    # never be sectioned by function. `options` (rich enum {value,label,roles}) and
    # `show_when` (conditional visibility) are likewise carried when authored.
    "functional_group": None,
    "options": None,
    "show_when": None,
}

#: The fields a single projected fixed-field override entry carries — the exact
#: set ``FixedFieldOverride`` consumes (``label``, ``visible``, ``required``,
#: ``order``, ``functional_group``). A ``None``/absent value means "leave the
#: fixed base as-is", so only the keys the tenant actually authored are carried
#: onto the row (the override is presentation-only and additive). ``functional_group``
#: is the R4.9 display-group reassignment (``config#fields.overrides[dotted].functional_group``
#: → ``FixedFieldOverride.functional_group`` → resolved onto the field).
_FIXED_OVERRIDE_FIELDS = ("label", "visible", "required", "order", "functional_group")

#: The fields a single projected functional-group catalog entry carries — the exact
#: set ``FunctionalGroup`` consumes (``key``, ``label`` i18n ``{nl,en}``, ``order``).
#: This is the tenant's DISPLAY-group catalog (R4.9), orthogonal to the storage bucket:
#: every field's ``functional_group`` must reference one of these ``key``s. The catalog
#: MUST be projected onto ``config#fields`` so the reader
#: (``MembersProjectionReader.get_overlay`` → ``TenantOverlay.functional_groups``) and the
#: resolver can section fields by function rather than by storage bucket.
_FUNCTIONAL_GROUP_FIELDS = ("key", "label", "order")


def _map_overlay_field(name: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one authored variable-overlay field dict to the ``config#fields`` shape.

    Pure mapping of a single tenant-authored overlay field into the exact field
    set ``OverlayField`` consumes (``key``, ``type``, ``required``, ``label``,
    ``choices``, ``visible``, ``order``). Unknown extra keys are dropped (the row
    carries only the shape the domain reads); absent fields fall back to a safe
    default so a partially authored field still yields a well-formed entry rather
    than raising. ``key`` defaults to the map key ``name`` when not explicitly
    authored (``OverlayField`` treats ``of.key or name`` the same way).
    """
    overlay_field: dict[str, Any] = {}
    for field_name, default in _OVERLAY_FIELD_DEFAULTS.items():
        if field_name in raw and raw[field_name] is not None:
            overlay_field[field_name] = raw[field_name]
        else:
            overlay_field[field_name] = default() if callable(default) else default
    if not overlay_field["key"]:
        overlay_field["key"] = name
    return overlay_field


def _map_fixed_override(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one authored fixed-field override dict to the ``config#fields`` shape.

    Presentation-only + additive: only the aspects the tenant actually authored
    (``label``/``visible``/``required``/``order``/``functional_group``) are carried
    onto the row; an unauthored aspect is simply absent (``FixedFieldOverride`` reads
    a missing attribute as "leave the fixed base as-is"). ``functional_group`` (R4.9)
    reassigns the field's display group — it MUST be carried through so an authored
    fixed/calculated-field group reassignment reaches the resolved field. Unknown
    extra keys are dropped.
    """
    override: dict[str, Any] = {}
    for field_name in _FIXED_OVERRIDE_FIELDS:
        if field_name in raw and raw[field_name] is not None:
            override[field_name] = raw[field_name]
    return override


def _map_functional_group(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one authored functional-group catalog entry to the ``config#fields`` shape.

    Pure mapping of a single tenant-authored functional group into the exact field set
    ``FunctionalGroup`` consumes (``key``, ``label`` ``{nl,en}``, ``order``) — the R4.9
    DISPLAY-group catalog, orthogonal to the storage bucket. Only ``key``/``label``/``order``
    are carried (unknown extra keys dropped); an absent ``label`` falls back to ``{}`` and an
    absent/non-int ``order`` to ``0`` so a partially authored entry still yields a well-formed
    row rather than raising. The reader's ``_build_functional_group`` consumes exactly this.
    """
    group: dict[str, Any] = {}
    key = raw.get("key")
    group["key"] = str(key) if key else ""
    label = raw.get("label")
    group["label"] = dict(label) if isinstance(label, Mapping) else {}
    order = raw.get("order")
    group["order"] = (
        order if isinstance(order, int) and not isinstance(order, bool) else 0
    )
    return group


def build_config_fields_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#fields`` projection item (S5b C2, R1.3).

    Reads the tenant's Members field-config overlay from the tenant-scope
    parameter system (``ParameterService.get_param`` on the ``members`` namespace,
    key ``field_overlay``) and shapes it into the ``config#fields`` row's two maps
    — ``fields`` (the variable overlay: added "club detail" fields) and
    ``overrides`` (presentation overrides of fixed fields) — the shape
    ``sam/members/domain/field_resolver.py`` ``TenantOverlay`` consumes
    (``TenantOverlay.fields`` = ``OverlayField``s keyed by canonical key;
    ``TenantOverlay.overrides`` = ``FixedFieldOverride``s keyed by canonical dotted
    key ``group.field``).

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope rows read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    pure ``tenant``/``module``/``role``/``config#scope`` builders.

    Empty-is-valid (R1.7): a tenant that has authored no ``members.field_overlay``
    parameter — or a malformed one — yields a row with empty ``fields`` and
    ``overrides`` maps. ``TenantOverlay`` then resolves that to exactly the fixed
    base, never an error. Returning the row (rather than ``None``) keeps the
    projection self-describing; the empty maps are the fixed-base collapse.

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.

    Returns:
        The ``config#fields`` :class:`ProjectionItem` for this tenant. ``None`` is
        never returned for a present tenant — an un-configured tenant still gets a
        well-formed empty-``fields``/empty-``overrides`` row.

    Raises:
        ValueError: The tenant is missing its ``administration``/``tenant_id`` key.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )

    raw_overlay = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _FIELD_OVERLAY_PARAM_KEY,
        tenant=tenant_id,
    )

    fields: dict[str, dict[str, Any]] = {}
    overrides: dict[str, dict[str, Any]] = {}
    functional_groups: list[dict[str, Any]] = []
    if isinstance(raw_overlay, Mapping):
        raw_fields = raw_overlay.get("fields")
        if isinstance(raw_fields, Mapping):
            for name, entry in raw_fields.items():
                if isinstance(entry, Mapping):
                    fields[name] = _map_overlay_field(name, entry)

        # The AUTHORED/validated key is ``fixed_overrides`` (design Data Models,
        # ``members_parameters.json``, ``members_config_validation.validate_field_overlay``).
        # Honor it as canonical; fall back to a legacy ``overrides`` key only if an
        # older overlay still carries one. The PROJECTED attribute stays ``overrides``
        # (the ``config#fields`` row shape + ``TenantOverlay.overrides`` consumer are
        # unchanged) — only the SOURCE key read from the authored overlay changes.
        raw_overrides = raw_overlay.get("fixed_overrides")
        if not isinstance(raw_overrides, Mapping):
            raw_overrides = raw_overlay.get("overrides")
        if isinstance(raw_overrides, Mapping):
            for dotted_key, entry in raw_overrides.items():
                if isinstance(entry, Mapping):
                    overrides[dotted_key] = _map_fixed_override(entry)

        # R4.9: carry the tenant's functional-group (display) catalog onto the row so the
        # reader (``TenantOverlay.functional_groups``) + resolver can section fields by
        # FUNCTION, not by storage bucket. Malformed entries (non-mapping / no ``key``) are
        # skipped (empty-is-valid); an unauthored catalog yields an empty list (base defaults).
        raw_groups = raw_overlay.get("functional_groups")
        if isinstance(raw_groups, (list, tuple)):
            for entry in raw_groups:
                if isinstance(entry, Mapping) and entry.get("key"):
                    functional_groups.append(_map_functional_group(entry))

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
        ),
        version=_scope_config_version(tenant),
        attributes={
            "fields": fields,
            "overrides": overrides,
            "functional_groups": functional_groups,
        },
    )


# --- C-VIEW config#views builder (S5c design.md C-VIEW, R5.1) ---------------

#: The fields a single projected view-context entry carries — the exact shape the
#: SAM-plane view-contexts reader consumes and the Phase-2 authoring UI writes
#: (``members.view_contexts``): ``key`` / ``label`` (i18n ``{nl,en}``) /
#: ``permission_roles`` / ``columns`` / ``filterable_columns`` / ``default_sort``
#: (``{field, direction}``) / ``page_size``. Each is mapped from the authored
#: parameter dict with a safe default so a partially authored context still yields
#: a well-formed entry rather than raising (empty-is-valid — the reader collapses a
#: missing/empty list to one default context, so the projection never forces a
#: context the tenant did not author).
_VIEW_CONTEXT_DEFAULTS: dict[str, Any] = {
    "key": None,
    "label": dict,
    "permission_roles": list,
    "columns": list,
    "filterable_columns": list,
    "default_sort": None,
    "page_size": None,
}


def _map_view_context(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one authored view-context dict to the ``config#views`` context shape.

    Pure mapping of a single tenant-authored view context into the exact field set
    the view-contexts reader consumes (``key``, ``label``, ``permission_roles``,
    ``columns``, ``filterable_columns``, ``default_sort``, ``page_size``). Unknown
    extra keys in the authored dict are dropped (the row carries only the shape the
    module reads); absent fields fall back to a safe default so a partially authored
    context still yields a well-formed entry rather than raising.
    """
    context: dict[str, Any] = {}
    for field_name, default in _VIEW_CONTEXT_DEFAULTS.items():
        if field_name in raw and raw[field_name] is not None:
            context[field_name] = raw[field_name]
        else:
            context[field_name] = default() if callable(default) else default
    return context


def build_config_views_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#views`` projection item (S5c C-VIEW, R5.1).

    Reads the tenant's Members view-context definitions from the tenant-scope
    parameter system (``ParameterService.get_param`` on the ``members`` namespace,
    key ``view_contexts``) and shapes them into the **sibling ``config#views``**
    row's ``contexts`` list — the shape the SAM-plane view-contexts reader
    (``sam/members/repository/projection_config_reader.get_view_contexts``)
    consumes (each context = ``key`` / ``label`` / ``permission_roles`` /
    ``columns`` / ``filterable_columns`` / ``default_sort`` / ``page_size``).

    Projection-shape decision (S5c task 3.1, Open Design Item 1 — settled): view
    contexts project as a **sibling ``config#views`` row**, not folded into
    ``config#fields`` — see :data:`services.projection_schema.RECORD_TYPE_CONFIG`
    for the rationale (separation of concern + independent versioning).

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope rows read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    sibling ``config#scope`` / ``config#fields`` builders.

    Empty-is-valid (R5.1): a tenant that has authored no ``members.view_contexts``
    parameter — or a malformed one — yields a row with an empty ``contexts`` list.
    The reader then resolves that to **exactly one default context** over all
    visible fields, never an error. Returning the row (rather than ``None``) keeps
    the projection self-describing; the empty list is the default-context collapse.

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.

    Returns:
        The ``config#views`` :class:`ProjectionItem` for this tenant. ``None`` is
        never returned for a present tenant — an un-configured tenant still gets a
        well-formed empty-``contexts`` row.

    Raises:
        ValueError: The tenant is missing its ``administration``/``tenant_id`` key.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )

    raw_contexts = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _VIEW_CONTEXTS_PARAM_KEY,
        tenant=tenant_id,
    )

    contexts: list[dict[str, Any]] = []
    if isinstance(raw_contexts, Sequence) and not isinstance(raw_contexts, str):
        for entry in raw_contexts:
            if isinstance(entry, Mapping):
                contexts.append(_map_view_context(entry))

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_VIEWS
        ),
        version=_scope_config_version(tenant),
        attributes={"contexts": contexts},
    )


# --- Source-side seam (read-only MySQL) ------------------------------------


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


# --- Sync result ------------------------------------------------------------


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync run (for observability + idempotence assertions).

    Attributes:
        written: Count of items actually written (put) this run.
        skipped: Count of items skipped because the stored version was already
            >= the incoming version (the idempotent/no-op path, R5.6).
        deleted: Count of obsolete ``scopegrant#…`` rows deleted by the ODx4b
            diff-and-delete reconcile (task 3.5) — cleared/downgraded grants whose
            row is no longer in the desired set. Zero on an unchanged re-sync.
        administrations: The ``administration`` values processed.
    """

    written: int = 0
    skipped: int = 0
    deleted: int = 0
    administrations: tuple[str, ...] = ()

    @property
    def is_noop(self) -> bool:
        """True iff nothing was written or deleted (a fully idempotent re-run)."""
        return self.written == 0 and self.deleted == 0


def _supersedes(incoming_version: Any, stored_version: Any) -> bool:
    """Return True iff ``incoming_version`` should overwrite ``stored_version``.

    Monotonic rule (R5.6): write only when there is no stored version, or the
    incoming version is **strictly greater** than the stored one. Equal or lower
    versions are a no-op (idempotent, ordering-tolerant re-delivery). Comparison
    is delegated to the values' natural ordering; incomparable types raise, which
    is preferable to silently mis-ordering versions.
    """
    if stored_version is None:
        return True
    return incoming_version > stored_version


# Placeholder-less condition guard for the real-store write. Written as a raw
# expression string with an expression-attribute-name for the reserved word
# ``version`` and a value placeholder for the incoming version.
_CONDITION_EXPRESSION = "attribute_not_exists(#v) OR #v < :incoming"


class ProjectionSync:
    """Sole writer of the governance projection table (design.md D3, T16).

    Reads governance rows (read-only), builds + validates projection items, and
    conditionally writes them to DynamoDB with monotonic versioning. Issues zero
    MySQL writes. Idempotent: re-running on an unchanged source is a no-op.

    Args:
        source: The read-only :class:`SourceProvider`. Required — inject a
            :class:`DatabaseSourceProvider` in production or a fake in tests.
        table: A DynamoDB table handle (boto3 ``Table`` or a fake exposing
            ``get_item`` / ``put_item`` / ``query`` / ``delete_item``). Optional —
            resolved lazily from the fail-fast schema helper when a write is first
            needed (R4.1). ``query`` + ``delete_item`` back the ODx4b
            diff-and-delete reconcile of obsolete ``scopegrant#…`` rows (task 3.5);
            a real boto3 ``Table`` exposes both.
        parameter_service: A read-only ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``) supplying the tenant-scope
            ``members.*`` config the C2 rows (``config#scope`` / ``config#fields``
            / ``scopegrant#…``) are built from. Optional — resolved lazily from a
            read-only ``ParameterService`` over ``DatabaseManager`` when a C2 row
            is first built (mirrors ``table``: no I/O at import/construct time).
            **Read-only**: only ``get_param`` is ever called, so the sync's
            one-directional guarantee (Property 1, R5.1/R5.2/R5.9) holds — the C2
            builders read the projection's source config and never write MySQL.
    """

    def __init__(
        self,
        source: SourceProvider,
        *,
        table: Any = None,
        parameter_service: Any = None,
    ) -> None:
        self._source = source
        self._table = table
        self._parameter_service = parameter_service

    @property
    def table(self) -> Any:
        """Return the injected table, else lazily resolve the real one (fail-fast).

        Resolution is deferred so importing/constructing the sync never forces
        DynamoDB env config; only an actual write triggers the fail-fast env
        resolution (R4.1).
        """
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    @property
    def parameter_service(self) -> Any:
        """Return the injected ParameterService, else lazily build a read-only one.

        Deferred like :attr:`table`: importing/constructing the sync never opens a
        MySQL connection; the default is only materialised the first time a C2 row
        is built. The default wraps a ``DatabaseManager`` in a ``ParameterService``
        and is used **read-only** (only ``get_param`` is called), so the sync stays
        one-directional (Property 1) — it never writes MySQL through this seam.
        """
        if self._parameter_service is None:
            from database import DatabaseManager
            from services.parameter_service import ParameterService

            self._parameter_service = ParameterService(DatabaseManager(test_mode=False))
        return self._parameter_service

    def sync_all(self) -> SyncResult:
        """Sync every administration the source knows about.

        Returns a combined :class:`SyncResult`. Each tenant is synced
        independently; a malformed tenant aborts *that* tenant loudly (R5.5)
        rather than silently corrupting the whole run.
        """
        administrations = self._source.list_administrations()
        total_written = 0
        total_skipped = 0
        total_deleted = 0
        for administration in administrations:
            result = self.sync_administration(administration)
            total_written += result.written
            total_skipped += result.skipped
            total_deleted += result.deleted
        return SyncResult(
            written=total_written,
            skipped=total_skipped,
            deleted=total_deleted,
            administrations=tuple(administrations),
        )

    def sync_administration(self, administration: str) -> SyncResult:
        """Sync one tenant's projection items (build -> validate -> conditional write).

        Steps:

        1. Read the tenant's source rows (read-only). Absent tenant -> no-op.
        2. Build the base items via the pure T12 builder (empty when the tenant
           has no SAM-backed module enabled -> nothing to project).
        3. **Only when the tenant has something to project** (base items
           non-empty, i.e. the SAM/MEMBERS module is enabled) also build the S5b
           C2 Members rows — ``config#scope``, ``config#fields``, ``config#views``
           (S5c) and the per-user ``scopegrant#…`` grants — by READING the
           tenant-scope ``members.*``
           config through the read-only :attr:`parameter_service`. A non-SAM
           tenant (empty base items) emits **no** C2 rows either, matching the
           existing early-return (nothing to project). One-directional: the C2
           builders only read; zero MySQL writes (Property 1).
        4. **Validate the whole combined batch first** (T14) — base + C2. A
           malformed item raises
           :class:`~services.projection_validator.ProjectionValidationError`
           **before any write**, so there is no partial/garbage projection (R5.5).
        5. Conditionally write each valid item: put only when new or the incoming
           version supersedes the stored version (R5.6). Skip otherwise (no-op).

        Args:
            administration: The tenant scope to sync.

        Returns:
            A :class:`SyncResult` for this tenant.

        Raises:
            ProjectionValidationError: A built item is malformed (aborts before
                any write for this tenant).
        """
        source = self._source.get_tenant_source(administration)
        if source is None:
            return SyncResult(administrations=(administration,))

        items = build_projection_items(
            source.tenant,
            source.tenant_modules,
            source.user_tenant_roles,
        )
        if not items:
            # No SAM-backed module enabled -> nothing to project. Do NOT emit the
            # S5b C2 rows either: they belong only to tenants that project, so a
            # non-SAM tenant writes nothing at all.
            return SyncResult(administrations=(administration,))

        # SAM/MEMBERS tenant -> also emit the S5b C2 rows (design.md C2/C3),
        # reading the tenant-scope members.* config read-only via ParameterService.
        param_svc = self.parameter_service
        config_scope = build_config_scope_row(source.tenant, param_svc)
        if config_scope is not None:
            items.append(config_scope)
        config_fields = build_config_fields_row(source.tenant, param_svc)
        if config_fields is not None:
            items.append(config_fields)
        config_views = build_config_views_row(source.tenant, param_svc)
        if config_views is not None:
            items.append(config_views)
        # The scopegrant rows are the DESIRED per-user grant set for this tenant.
        # Kept in a named list (not just extended into ``items``) so the ODx4b
        # diff-and-delete reconcile below can compute which STORED ``scopegrant#…``
        # rows are no longer desired and delete them.
        scopegrant_items = build_scopegrant_rows(
            source.tenant, source.user_tenant_scope, param_svc
        )
        items.extend(scopegrant_items)

        # Validate the ENTIRE combined batch (base + C2) before writing anything —
        # atomic per tenant, no partial write on a malformed item (R5.5).
        validate_items(items)

        written = 0
        skipped = 0
        for item in items:
            if self._conditional_put(item):
                written += 1
            else:
                skipped += 1

        # FRESHNESS FIX (ODx4b, task 3.5). The version-guarded conditional put
        # above makes ADDS and UPDATES propagate, but it can never DELETE a row.
        # A user whose grant was CLEARED (their scope row is gone) or DOWNGRADED
        # (a dimension dropped) leaves the old ``scopegrant#<email>#<dimension>``
        # row PRESENT in the projection; deny-by-default enforcement then keeps
        # honouring the stale grant — the user keeps seeing members they were
        # unscoped from (SECURITY-relevant staleness). So after writing the
        # DESIRED scopegrant rows, reconcile the tenant's stored ``scopegrant#…``
        # rows to that desired set, deleting the obsolete ones. Confined to the
        # ``scopegrant#…`` SK space this feature owns — no other record type is
        # touched. Delete happens AFTER the puts so a still-desired row is written
        # first and never transiently absent.
        deleted = self._reconcile_scopegrants(administration, scopegrant_items)

        return SyncResult(
            written=written,
            skipped=skipped,
            deleted=deleted,
            administrations=(administration,),
        )

    def _reconcile_scopegrants(
        self, administration: str, desired_items: Sequence[ProjectionItem]
    ) -> int:
        """Delete obsolete ``scopegrant#…`` rows for one tenant (ODx4b, task 3.5).

        Computes the DESIRED set of ``scopegrant#<email>#<dimension>`` sort keys
        (from :func:`build_scopegrant_rows` over the tenant's ``user_tenant_scope``)
        and deletes every STORED ``scopegrant#…`` row whose sort key is NOT in that
        set. This is what makes REMOVALS and DOWNGRADES propagate — a version bump
        alone can only supersede a present row, never delete an orphaned one.

        Tenant-scoped (Property 1/2): the stored rows are read with a ``query`` on
        this tenant's partition (``tenant_id = administration``) filtered to
        ``begins_with(sk, 'scopegrant#')``, so the reconcile never addresses — let
        alone deletes — another tenant's partition. Confined to the ``scopegrant#…``
        SK space: non-scopegrant rows (``tenant``/``module#*``/``role#*``/
        ``config#*``) are never listed and never deleted (they have their own
        lifecycle, out of s5d's scope).

        Idempotent: on an unchanged re-sync the stored set equals the desired set,
        so nothing is deleted; deleting an already-absent row would be a harmless
        no-op regardless.

        Args:
            administration: The tenant scope (partition key) to reconcile.
            desired_items: The DESIRED scopegrant items just built for this tenant.

        Returns:
            The count of obsolete ``scopegrant#…`` rows deleted.
        """
        desired_sks = {item.sort_key for item in desired_items}
        deleted = 0
        for stored_sk in self._list_scopegrant_sort_keys(administration):
            if stored_sk in desired_sks:
                continue
            self.table.delete_item(Key=schema.build_key(administration, stored_sk))
            deleted += 1
        return deleted

    def _list_scopegrant_sort_keys(self, administration: str) -> list[str]:
        """Return the stored ``scopegrant#…`` sort keys for one tenant.

        Queries only THIS tenant's partition (``tenant_id = administration``) with
        a ``begins_with(sk, 'scopegrant#')`` key condition, so the read is
        tenant-scoped (Property 1/2) and confined to the ``scopegrant#…`` SK space
        (no other record type is listed). Paginates via ``LastEvaluatedKey`` so a
        tenant with many grants is fully reconciled.

        Args:
            administration: The tenant scope (partition key) to list.

        Returns:
            The stored ``scopegrant#…`` sort-key values (possibly empty).
        """
        scopegrant_prefix = schema.RECORD_TYPE_SCOPEGRANT + schema.SORT_KEY_SEPARATOR
        query_kwargs: dict[str, Any] = {
            "KeyConditionExpression": ("#pk = :pk AND begins_with(#sk, :sk_prefix)"),
            "ExpressionAttributeNames": {
                "#pk": schema.PARTITION_KEY_ATTR,
                "#sk": schema.SORT_KEY_ATTR,
            },
            "ExpressionAttributeValues": {
                ":pk": administration,
                ":sk_prefix": scopegrant_prefix,
            },
        }
        sort_keys: list[str] = []
        while True:
            response = self.table.query(**query_kwargs)
            if not isinstance(response, Mapping):
                break
            for row in response.get("Items", ()) or ():
                if not isinstance(row, Mapping):
                    continue
                sort_key = row.get(schema.SORT_KEY_ATTR)
                if isinstance(sort_key, str) and sort_key.startswith(scopegrant_prefix):
                    sort_keys.append(sort_key)
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            query_kwargs["ExclusiveStartKey"] = last_key
        return sort_keys

    def _stored_version(self, item: ProjectionItem) -> Any:
        """Return the currently-stored version for ``item``'s key, or ``None``.

        Reads the projection table (``get_item``) for the item's primary key. A
        missing item / missing ``version`` attribute yields ``None`` (treated as
        "no stored version" -> the incoming write supersedes).
        """
        key = schema.build_key(item.tenant_id, item.sort_key)
        response = self.table.get_item(Key=key)
        stored = response.get("Item") if isinstance(response, Mapping) else None
        if not stored:
            return None
        return stored.get(schema.VERSION_ATTR)

    def _conditional_put(self, item: ProjectionItem) -> bool:
        """Write ``item`` iff its version supersedes the stored one (R5.6).

        Returns True if the item was written, False if skipped as a no-op
        (stored version already >= incoming). The put carries a DynamoDB
        ``ConditionExpression`` so a real concurrent store is guarded at the
        datastore level too; a datastore-level conditional failure is treated as
        a benign no-op (another writer advanced the version).
        """
        stored_version = self._stored_version(item)
        if not _supersedes(item.version, stored_version):
            return False

        dynamo_item = item.to_dynamodb_item()
        try:
            self.table.put_item(
                Item=dynamo_item,
                ConditionExpression=_CONDITION_EXPRESSION,
                ExpressionAttributeNames={"#v": schema.VERSION_ATTR},
                ExpressionAttributeValues={":incoming": item.version},
            )
        except Exception as exc:
            # A conditional-check failure means a concurrent writer already
            # advanced the stored version — a benign no-op (idempotence, R5.6),
            # not an error. Any other error propagates (fail loudly).
            if _is_conditional_check_failure(exc):
                return False
            raise
        return True


def _is_conditional_check_failure(exc: BaseException) -> bool:
    """True iff ``exc`` is a DynamoDB conditional-check failure.

    Detected structurally (botocore ``ClientError`` with the
    ``ConditionalCheckFailedException`` error code) without importing botocore at
    module import time, so an in-memory fake that raises a differently-shaped
    error is never mistaken for this benign case.
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return False
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return False
    return error.get("Code") == "ConditionalCheckFailedException"


# --- C2 scopegrant#<email>#<dimension> builder (S5b design.md C2, R2.1/R2.2) ---

#: The all-access sentinel a projected grant carries on the GRANT side — the value
#: that appears in the ``scopes`` JSON (``{ "<dimension>": ["*"] }``) and is projected
#: verbatim into the ``scopegrant#…`` row so the module reads it as tenant-wide. This is
#: a GRANT-side value, NOT role machinery: s5d sources grants from ``user_tenant_scope``
#: (R2.2, clean break — the ``Regio_*`` role-name decode and its ``all_wildcard`` encoding
#: are removed). It is independent of any role name.
WILDCARD_VALUE = "*"


#: The MODULE token s5d projects: the builder filters ``user_tenant_scope`` rows
#: to this module (the s5d slice). Scope dimensions are a MODULE-owned concept
#: (design → Data Models), so a future module (Events/Webshop) runs the SAME loop
#: with its own token + its own ``<module>.scope_dimensions`` — no re-migration.
_SCOPEGRANT_MODULE = "MEMBERS"


#: Row fields a ``user_tenant_scope`` row may carry a per-row freshness signal in,
#: in priority order. ``updated_at`` is the table's ``ON UPDATE CURRENT_TIMESTAMP``
#: column (see the migration): it advances on a genuine grant CHANGE and is stable
#: when the row is untouched — exactly the monotonic-yet-idempotent property ODx4a
#: needs. ``version``/``revision`` backstop it if a future source labels freshness
#: differently. A row with none falls back to the tenant config version (see
#: :func:`_scopegrant_version`).
_SCOPEGRANT_VERSION_FIELDS = ("updated_at", "version", "revision", "modified_at")


def _scopegrant_version(scope_row: Mapping[str, Any], tenant_version: Any) -> Any:
    """Return the per-row version for one ``user_tenant_scope`` grant (ODx4a).

    FRESHNESS FIX (design → "Projection invocation + freshness" FRESHNESS HAZARD,
    ODx4a). The ``scopegrant#…`` rows are written under the sync's VERSION-GUARDED
    conditional put (:func:`_supersedes` / the ``#v < :incoming`` condition), which
    writes only when the incoming ``version`` STRICTLY supersedes the stored one.
    Deriving that version from the TENANT row (``_scope_config_version``) — as the
    sibling ``config#*`` rows do — is wrong for a per-user grant: editing a user's
    scope (e.g. Oost → Oost+Friesland) does NOT bump the tenant version, so the
    conditional put would SKIP the changed row and the projection would stay STALE
    (a security-relevant staleness — the user keeps seeing members they were
    unscoped from).

    APPROACH — per-row ``updated_at`` (chosen over a content-hash/etag). The
    ``user_tenant_scope`` row carries ``updated_at`` (``ON UPDATE CURRENT_TIMESTAMP``
    on the table), which:

    - (a) **advances on a changed grant** — an edited row's ``updated_at`` moves
      forward, so the new version STRICTLY supersedes the stored one and the put
      writes (UPDATE propagates — the bug is fixed);
    - (b) **is stable on an unchanged re-sync** — an untouched row reproduces the
      SAME ``updated_at`` → the same normalized version → the conditional put is a
      no-op (idempotence preserved, no version churn);
    - (c) **fits the existing mechanics** — ``_normalize_version`` renders a
      ``datetime`` to an ISO-8601 string that sorts lexicographically in
      chronological order, so it is a valid MONOTONIC version for BOTH the write
      conditional put (:func:`_supersedes`) AND the read-side staleness detection
      (``projection_reader._version_supersedes``). Those two consumers require a
      strictly-ORDERED version, which a content hash could NOT provide (an edited
      grant's hash may sort LOWER than the stored one → would not supersede, and
      would corrupt read-side staleness ordering). ``updated_at`` is therefore the
      correct fit; a content hash would only satisfy "differs", not "supersedes".

    Fallback: a row without any :data:`_SCOPEGRANT_VERSION_FIELDS` (e.g. a test/
    fixture row, or a driver that omitted the column) falls back to the tenant
    config version, preserving the previous behaviour and keeping the item
    well-formed and re-sync idempotent.

    NOTE (seam for task 3.5 / ODx4b): this version bump makes ADDS and UPDATES
    propagate. A REMOVED/downgraded grant (the SK disappears from the desired set)
    still needs the diff-and-delete-obsolete step (ODx4b, task 3.5) — a conditional
    put alone can never delete an orphaned row.
    """
    for name in _SCOPEGRANT_VERSION_FIELDS:
        value = scope_row.get(name)
        if value is not None:
            return _normalize_version(value)
    return tenant_version


def _parse_scopes(raw: Any) -> Mapping[str, Any] | None:
    """Return the parsed ``scopes`` mapping for a ``user_tenant_scope`` row, or ``None``.

    The ``scopes`` JSON column is carried as-is by the source provider and may arrive
    as a JSON **string** (most MySQL drivers) OR an already-parsed **dict** (some
    drivers deserialize JSON columns). Handle both: a ``str`` is ``json.loads``-ed; a
    ``Mapping`` is used directly. Anything else — an unparseable string, a non-dict
    JSON value (list/number), a ``None`` — yields ``None``, signalling the caller to
    skip that user row (defensive, design → Error Handling: a malformed row logs and
    is skipped, never raises).
    """
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def build_scopegrant_rows(
    tenant: Mapping[str, Any],
    user_tenant_scope: Sequence[Mapping[str, Any]] | None,
    parameter_service: Any,
) -> list[ProjectionItem]:
    """Build the per-user ``scopegrant#<email>#<dimension>`` items (R2.1/R2.3/R2.5).

    Sources each user's scope from the MySQL ``user_tenant_scope`` table (rows
    ``{email, module, scopes}``), NOT from role names — the ``Regio_*`` role encoding
    is removed (R2.2). For the s5d MEMBERS slice, rows are filtered to
    ``module = 'MEMBERS'``; each user row's ``scopes`` JSON
    (``{ "<dimension>": ["<value>", ...] | ["*"] }``) is decoded into one
    ``scopegrant#<email>#<dimension>`` item per dimension with a **non-empty** grant:

    - ``values=["*"]`` when the grant is the all-access sentinel ``["*"]``, or
    - ``values=[<subset>]`` — the granted plain values, validated against the
      dimension's declared ``values`` (canonicalized-equality via ``scope_canon``;
      belt-and-suspenders — primary validation is at authoring, R4.2), emitted in the
      dimension's declared value order.

    Deny-by-default (R2.3): an absent dimension, an empty grant list, or a grant whose
    values all fail validation produces **no** row for that (user, dimension) — the
    module's deny-by-default handles the absence. The projected row SHAPE is UNCHANGED
    (R2.5): ``{dimension, values}`` attributes + a ``version``.

    FRESHNESS (ODx4a, R2.4). Each row's ``version`` is derived PER USER from the
    ``user_tenant_scope`` row's ``updated_at`` (see :func:`_scopegrant_version`),
    NOT from the tenant row. A grant-only change (e.g. Oost → Oost+Friesland) does
    not bump the tenant version, so sourcing the version from the tenant row would
    let the version-guarded conditional put SKIP the changed row (stale, security-
    relevant). ``updated_at`` advances on a changed grant (the new version
    supersedes → the update is written) and is stable on an unchanged re-sync (same
    version → no-op → idempotence preserved). Removals/downgrades (the SK vanishes
    from the desired set) are handled by the diff-and-delete step (ODx4b, task 3.5).

    One-directional discipline (Property 1): this builder issues **zero** MySQL writes
    and does **not** write the projection itself — it only READS the scope rows it is
    handed and the dimension params via ``ParameterService`` (read-only), and RETURNS
    the items for :class:`ProjectionSync` (the sole writer).

    Empty-is-valid: a tenant that has authored no ``members.scope_dimensions`` — or has
    no scope rows — yields an empty list (no grants to project), never an error. A
    malformed ``scopes`` JSON on a user row (not a dict, unparseable) is logged and the
    row is skipped, never raised (design → Error Handling; mirrors the existing
    builders' empty-is-valid tolerance).

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        user_tenant_scope: The tenant's ``user_tenant_scope`` rows (``email``,
            ``module``, ``scopes``, ``updated_at``). ``None``/empty → no grants.
            ``scopes`` may be a JSON string or an already-parsed dict. ``updated_at``
            (the per-row freshness signal) drives the emitted row's ``version``
            (ODx4a); absent → the tenant config version fallback.
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only — supplies the
            ``members.scope_dimensions`` dimension definitions used to validate values.

    Returns:
        The ``scopegrant#<email>#<dimension>`` :class:`ProjectionItem`s — one per
        (user, dimension) with a grant. Empty when nothing is granted.

    Raises:
        ValueError: The tenant is missing its ``administration``/``tenant_id`` key.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )

    raw_dimensions = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _SCOPE_DIMENSIONS_PARAM_KEY,
        tenant=tenant_id,
    )
    dimensions: list[Mapping[str, Any]] = []
    if isinstance(raw_dimensions, Sequence) and not isinstance(raw_dimensions, str):
        for entry in raw_dimensions:
            if isinstance(entry, Mapping) and entry.get("key"):
                dimensions.append(entry)

    if not dimensions:
        return []

    # Index dimensions by key, precomputing each dimension's canonical value map
    # (canonical form -> declared value) so a granted value is validated by
    # canonicalized-equality (belt-and-suspenders, R9.6) and emitted as the declared
    # value in declared order.
    dimension_by_key: dict[str, dict[str, Any]] = {}
    for dimension in dimensions:
        if not dimension.get("enabled", True):
            # A disabled dimension is a tenant-wide no-op — no per-user grant row.
            continue
        key = dimension["key"]
        raw_values = dimension.get("values") or ()
        if isinstance(raw_values, str) or not isinstance(raw_values, Sequence):
            raw_values = ()
        canon_to_value: dict[str, str] = {}
        declared_order: list[str] = []
        for value in raw_values:
            if not isinstance(value, str):
                continue
            declared_order.append(value)
            canon_to_value.setdefault(scope_canon(value), value)
        dimension_by_key[key] = {
            "canon_to_value": canon_to_value,
            "declared_order": declared_order,
        }

    # Collect each user's parsed scopes for the s5d MEMBERS slice (skip non-MEMBERS
    # rows and malformed rows — never raise). A later duplicate row for the same
    # email is merged shallowly (last-writer-wins per dimension); the table's unique
    # key (email, administration, module) makes this a defensive no-op in practice.
    #
    # Also capture each row's per-user FRESHNESS version (ODx4a): the row's
    # ``updated_at`` (or tenant fallback) so an UPDATED grant supersedes the stored
    # scopegrant row. Keyed by email so every dimension row for a user carries the
    # SAME per-user version; on a defensive duplicate the last row's version wins
    # (aligned with the last-writer-wins scope merge).
    tenant_version = _scope_config_version(tenant)
    scopes_by_email: dict[str, dict[str, Any]] = {}
    version_by_email: dict[str, Any] = {}
    for scope_row in user_tenant_scope or ():
        if not isinstance(scope_row, Mapping):
            logger.warning(
                "skipping malformed user_tenant_scope row (not a mapping) for "
                "tenant %s",
                tenant_id,
            )
            continue
        if scope_row.get("module") != _SCOPEGRANT_MODULE:
            continue
        email = scope_row.get("email")
        if not email or not isinstance(email, str):
            continue
        parsed = _parse_scopes(scope_row.get("scopes"))
        if parsed is None:
            logger.warning(
                "skipping user_tenant_scope row with malformed 'scopes' JSON for "
                "email %s in tenant %s",
                email,
                tenant_id,
            )
            continue
        scopes_by_email.setdefault(email, {}).update(parsed)
        version_by_email[email] = _scopegrant_version(scope_row, tenant_version)

    items: list[ProjectionItem] = []
    # Deterministic order: by email, then by dimension declaration order, so a
    # re-sync on unchanged input reproduces the same items (idempotence, R5.6).
    for email in sorted(scopes_by_email):
        scopes = scopes_by_email[email]
        version = version_by_email.get(email, tenant_version)
        for dimension in dimensions:
            dimension_key = dimension["key"]
            meta = dimension_by_key.get(dimension_key)
            if meta is None:
                # Disabled / unusable dimension — no per-user grant row.
                continue
            grant = scopes.get(dimension_key)
            if not isinstance(grant, Sequence) or isinstance(grant, str):
                # Absent dimension / non-list grant -> no row (deny-by-default, R2.3).
                continue
            # All-access sentinel: any ["*"] entry grants the whole dimension.
            if any(isinstance(g, str) and g == WILDCARD_VALUE for g in grant):
                granted = [WILDCARD_VALUE]
            else:
                canon_to_value = meta.get("canon_to_value", {})
                # Validate each granted value against the dimension's declared values
                # by canonicalized-equality (belt-and-suspenders, R9.6); unknown
                # values are dropped. Emit in declared order, de-duplicated.
                granted_declared: set[str] = set()
                for g in grant:
                    if not isinstance(g, str):
                        continue
                    declared = canon_to_value.get(scope_canon(g))
                    if declared is not None:
                        granted_declared.add(declared)
                granted = [
                    value
                    for value in meta.get("declared_order", [])
                    if value in granted_declared
                ]
            if not granted:
                # Empty grant / all values dropped -> no row (deny-by-default, R2.3).
                continue
            items.append(
                ProjectionItem(
                    tenant_id=tenant_id,
                    sort_key=schema.build_sort_key(
                        schema.RECORD_TYPE_SCOPEGRANT, email, dimension_key
                    ),
                    version=version,
                    attributes={"dimension": dimension_key, "values": granted},
                )
            )

    return items
