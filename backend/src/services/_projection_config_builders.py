"""Governance projection — tenant-level ``config#*`` row builders (extracted from
``projection_sync`` for cohesion).

The pure, read-only builders that shape a tenant's authored ``members.*`` tenant-scope
parameters into the ``config#scope`` / ``config#fields`` / ``config#views`` projection
rows the SAM/Lambda module plane reads (S5b design.md C2 / S5c C-VIEW). They are
re-exported from :mod:`services.projection_sync`; its public import surface is unchanged.

One-directional discipline (Property 1): every builder here issues **zero** MySQL writes
and does **not** write the projection itself — it only READS via ``ParameterService``
(read-only ``get_param``) and RETURNS the item for the sole writer
(:class:`services.projection_sync.ProjectionSync`). This is a pure structural split
(code-quality M2) with zero behaviour change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services import projection_schema as schema
from services.projection_builder import (
    ProjectionItem,
    _normalize_version,
)

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

#: The single tenant-scope parameter key that holds the per-tenant "mail-enabled /
#: SES-certified" onboarding gate flag as a boolean (pivot-output-actions R0,
#: task 0.4). Authored by the tenant-admin module (``members.mail_enabled``, same
#: ``/api/tenant-admin/parameters`` surface as ``scope_dimensions`` etc.); read
#: here and shaped into the ``config#mail`` row's ``mail_enabled`` attribute — the
#: shape the SAM-plane projection reader (``projection_config_reader.is_mail_enabled``)
#: consumes. This builder only READS whatever value exists (Property 1,
#: one-directional).
_MAIL_ENABLED_PARAM_KEY = "mail_enabled"

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


# --- R0 config#mail builder (pivot-output-actions R0, design §6.3, task 0.4) --


def build_config_mail_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#mail`` projection item (R0, design §6.3).

    Reads the tenant's per-tenant "mail-enabled / SES-certified" onboarding gate
    flag from the tenant-scope parameter system (``ParameterService.get_param`` on
    the ``members`` namespace, key ``mail_enabled``) and shapes it into the
    ``config#mail`` row's single ``mail_enabled`` boolean attribute — the shape the
    SAM-plane projection reader (``MembersProjectionReader.is_mail_enabled``)
    consumes. The Members edge reads this projected row at request time to decide
    whether to offer the mail output actions (R1–R5); it NEVER queries MySQL
    (ADR 0005/0006).

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope row read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    sibling ``config#scope`` / ``config#fields`` / ``config#views`` builders.

    Fail-closed default (R0): a tenant that has authored no ``members.mail_enabled``
    parameter — or a malformed (non-boolean) value — yields a row with
    ``mail_enabled`` = ``False``. A tenant is cleared to send only by an explicit,
    well-formed ``True`` flag; the absence of the gate NEVER opens it. Returning the
    row (rather than ``None``) keeps the projection self-describing — a present-but-
    disabled gate is distinct from "not yet projected".

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.

    Returns:
        The ``config#mail`` :class:`ProjectionItem` for this tenant. ``None`` is
        never returned for a present tenant — an un-configured tenant still gets a
        well-formed ``mail_enabled`` = ``False`` row (fail-closed).

    Raises:
        ValueError: The tenant is missing its ``administration``/``tenant_id`` key.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )

    raw_flag = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_ENABLED_PARAM_KEY,
        tenant=tenant_id,
    )

    # Fail-closed: only an explicit boolean ``True`` enables the gate. Any other
    # value — absent (None), a stray string, a number — collapses to False, so a
    # malformed/absent gate can never silently permit sending.
    mail_enabled = raw_flag is True

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_MAIL
        ),
        version=_scope_config_version(tenant),
        attributes={"mail_enabled": mail_enabled},
    )


__all__ = [
    "_DIMENSION_DEFAULTS",
    "_FIELD_OVERLAY_PARAM_KEY",
    "_FIXED_OVERRIDE_FIELDS",
    "_FUNCTIONAL_GROUP_FIELDS",
    "_MAIL_ENABLED_PARAM_KEY",
    "_MEMBERS_PARAM_NAMESPACE",
    "_OVERLAY_FIELD_DEFAULTS",
    "_SCOPE_DIMENSIONS_PARAM_KEY",
    "_SCOPE_VERSION_FIELDS",
    "_VIEW_CONTEXTS_PARAM_KEY",
    "_VIEW_CONTEXT_DEFAULTS",
    "_map_fixed_override",
    "_map_functional_group",
    "_map_overlay_field",
    "_map_scope_dimension",
    "_map_view_context",
    "_scope_config_version",
    "build_config_fields_row",
    "build_config_mail_row",
    "build_config_scope_row",
    "build_config_views_row",
]
