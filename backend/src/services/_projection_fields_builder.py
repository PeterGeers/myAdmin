"""Governance projection — the ``config#fields`` row builder (C2, R1.3).

INTERNAL helper module of :mod:`services._projection_config_builders` — extracted from it
(code-quality file-length split, 2026-10-28) with **zero behaviour change**. Owns the overlay
field / fixed-override / functional-group mappers, the default-page-size resolver, and
:func:`build_config_fields_row`. Re-exported from the facade
:mod:`services._projection_config_builders` (and the three public ``build_*`` from
:mod:`services.projection_sync`), so the public import surface is unchanged.

One-directional discipline (Property 1): the builder issues **zero** MySQL writes and does
**not** write the projection itself — it only READS via ``ParameterService`` and RETURNS the
item for the sole writer (:class:`services.projection_sync.ProjectionSync`).
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

#: The single tenant-scope parameter key that holds the tenant-level default
#: rows-per-page for the Members table (``members.default_page_size``, Phase 2
#: step (a)). A single scalar DEFAULT — not a stored view object (``38`` rule 3) —
#: carried onto the EXISTING ``config#fields`` row (NOT a new ``config#views`` row)
#: so the SAM reader can surface it on the field-config response alongside the
#: overlay. Read here read-only (Property 1); a per-user preference overrides it at
#: render and an unset value falls back to the platform table-toolkit default.
_DEFAULT_PAGE_SIZE_PARAM_KEY = "default_page_size"

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
    # Phase 3 step 9 (R2.1): a field may declare it is a SCOPE AXIS as a field attribute
    # ({enabled, values, label?, required_for?}). Carried onto config#fields so the SAM read
    # representation expresses scope-binding as a field attribute too; `None` when the field is
    # not a scope axis. The config#scope dimensions are DERIVED from this (semantic equivalence,
    # Property 2) — this attribute is the READ representation, config#scope stays authoritative
    # for the resolver.
    "scope": None,
    # Member Application Form (application-app R4c.1/R4c.2, D20): the four per-field
    # APPLICATION attributes authored in the Flask tenant-admin field config and carried 1:1
    # onto config#fields so the SAM read side (R4/R4a/R4b/R5) can project the public form. Back-
    # compatible defaults for a tenant that authored none (R4c.5): `application_visible` off →
    # the field is NOT on the public form; `application_required` off → optional (never relaxes
    # a platform-required field — that is the SAM resolver's authority); `application_choices`
    # None → the full enum set (no subset); `format` None → no extra FieldFormat checker.
    "application_visible": False,
    "application_required": False,
    "application_choices": None,
    "format": None,
}

#: The fields a single projected fixed-field override entry carries — the exact
#: set ``FixedFieldOverride`` consumes (``label``, ``visible``, ``required``,
#: ``order``, ``functional_group``, plus the enum vocabulary ``options``/``choices``
#: and the ``scope`` attribute). A ``None``/absent value means "leave the fixed base
#: as-is", so only the keys the tenant actually authored are carried onto the row (the
#: override is presentation-only and additive). ``functional_group`` is the R4.9
#: display-group reassignment (``config#fields.overrides[dotted].functional_group`` →
#: ``FixedFieldOverride.functional_group`` → resolved onto the field).
#:
#: I-9 (R5.1): ``options`` (the rich enum vocabulary ``{value,label,roles?}``), its
#: coherent bare ``choices`` list, and ``scope`` ({enabled, required_for}) are ALSO
#: carried, so a tenant's fixed-field enum relabel / scope-axis binding survives
#: projection to ``config#fields`` instead of being silently dropped (defect I-9: the
#: fixed-override builder previously dropped these). Still presentation-only + additive
#: — carrying an authored attribute never WEAKENS a platform invariant; the resolver's
#: rejection semantics stay authoritative (R5.3). ``member_number_format`` is DELIBERATELY
#: NOT carried here — deferred to the follow-up spec (R5.2).
#:
#: Member Application Form (application-app R4c.1/R4c.2, D20): the four per-field APPLICATION
#: attributes — ``application_visible`` / ``application_required`` / ``application_choices`` /
#: ``format`` — are ALSO carried on a fixed-field override, 1:1 the same way as on an overlay
#: field (:data:`_OVERLAY_FIELD_DEFAULTS`), so a tenant can select a FIXED field (e.g.
#: ``membership.membership_type``) onto the public form with its own subset / requiredness /
#: FieldFormat. Additive like the rest of the override: an unauthored attribute is simply
#: absent (``FixedFieldOverride`` reads a missing attribute as "leave the fixed base as-is",
#: the back-compatible default R4c.5), never a forced ``False``/``None`` that would mask the
#: fixed base.
_FIXED_OVERRIDE_FIELDS = (
    "label",
    "visible",
    "required",
    "order",
    "functional_group",
    "options",
    "choices",
    "scope",
    "application_visible",
    "application_required",
    "application_choices",
    "format",
)

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
    ``choices``, ``visible``, ``order``) plus the carried display/scope attributes
    and the four per-field APPLICATION attributes (``application_visible``,
    ``application_required``, ``application_choices``, ``format`` — R4c.1/R4c.2,
    D20). Unknown extra keys are dropped (the row carries only the shape the domain
    reads); absent fields fall back to a safe default so a partially authored field
    still yields a well-formed entry rather than raising — the application attributes
    default to their back-compatible values (``_OVERLAY_FIELD_DEFAULTS``: not on the
    public form, not application-required, full choice set, no FieldFormat). ``key``
    defaults to the map key ``name`` when not explicitly authored (``OverlayField``
    treats ``of.key or name`` the same way).
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
    (``label``/``visible``/``required``/``order``/``functional_group`` plus the enum
    vocabulary ``options``/``choices``, ``scope``, and the four per-field APPLICATION
    attributes ``application_visible``/``application_required``/``application_choices``/
    ``format`` — R4c.1/R4c.2, D20) are carried onto the row; an unauthored aspect is
    simply absent (``FixedFieldOverride`` reads a missing attribute as "leave the fixed
    base as-is" — the back-compatible default, R4c.5). ``functional_group`` (R4.9)
    reassigns the field's display group — it MUST be carried through so an authored
    fixed/calculated-field group reassignment reaches the resolved field. Carrying the
    application attributes lets a tenant select a FIXED field onto the public form with
    its own subset / requiredness / FieldFormat, the same way an overlay field does
    (:func:`_map_overlay_field`). Unknown extra keys are dropped.

    I-9 fix (R5.1): ``options``/``choices`` (the enum vocabulary) and ``scope`` are carried
    so a tenant's fixed-field enum relabel or scope-axis binding survives projection instead
    of being silently dropped. The two enum representations are kept COHERENT: when ``options``
    (the rich ``{value,label,roles?}`` vocabulary) is authored, the bare ``choices`` list is
    DERIVED from it (:func:`_enum_values_from_field`) so the two never disagree — an authored
    ``choices`` is overwritten by the options-derived list rather than left inconsistent. When
    only ``choices`` is authored it is carried verbatim.

    This stays presentation-only + additive — carrying an authored attribute never WEAKENS a
    platform invariant; the resolver's existing rejection semantics stay authoritative (R5.3).
    ``member_number_format`` is DELIBERATELY not carried (deferred, R5.2).
    """
    override: dict[str, Any] = {}
    for field_name in _FIXED_OVERRIDE_FIELDS:
        if field_name in raw and raw[field_name] is not None:
            override[field_name] = raw[field_name]

    # Coherent enum vocabulary (R5.1): when rich `options` are authored, the bare `choices`
    # list MUST be the per-option values in order (single, consistent vocabulary). Derive it
    # from `options` so a stale/absent `choices` can never disagree with the rich options.
    if "options" in override:
        coherent_choices = _enum_values_from_field({"options": override["options"]})
        if coherent_choices is not None:
            override["choices"] = coherent_choices
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

        # The AUTHORED/validated input key is ``fixed_overrides`` (design Data Models,
        # ``members_parameters.json``, ``members_config_validation.validate_field_overlay``).
        # Phase 2 (R6.7) retired the legacy top-level ``overrides`` dual-accept: every stored
        # overlay was migrated to ``fixed_overrides`` first (R6.1, the one-time migration under
        # ``backend/src/migrations/``), so the builder now reads ONLY the canonical input key.
        # The PROJECTED attribute stays ``overrides`` (the ``config#fields`` row shape +
        # ``TenantOverlay.overrides`` consumer are unchanged, R6.8) — only the acceptance of the
        # legacy SOURCE key is dropped.
        raw_overrides = raw_overlay.get("fixed_overrides")
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

    # Phase 2 step (a): the tenant-level default rows-per-page is a scalar DEFAULT
    # (NOT a stored view object, `38` rule 3) carried on this EXISTING config#fields
    # row so the SAM reader can surface it on the field-config response alongside the
    # overlay — no new config#views row. Read from its own `members.default_page_size`
    # param (sibling to `field_overlay`). Only a positive int survives; any other
    # value (absent/None/non-int/<=0) collapses to `None` so an unconfigured or
    # malformed default falls back to the per-user preference / platform toolkit
    # default at render (R2.1/R2.4 — the resolver's positive-int guarantee).
    default_page_size = _resolve_default_page_size(
        parameter_service.get_param(
            _MEMBERS_PARAM_NAMESPACE,
            _DEFAULT_PAGE_SIZE_PARAM_KEY,
            tenant=tenant_id,
        )
    )

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
        ),
        # config#fields is now driven by TWO params — the field overlay AND the
        # default_page_size scalar — so an edit to EITHER must bump the row (the
        # version-bump-trap fix): the version is the max of their per-param revisions,
        # falling back to the tenant row only when neither is authored.
        version=_config_row_version(
            tenant,
            parameter_service,
            tenant_id,
            (_FIELD_OVERLAY_PARAM_KEY, _DEFAULT_PAGE_SIZE_PARAM_KEY),
        ),
        attributes={
            "fields": fields,
            "overrides": overrides,
            "functional_groups": functional_groups,
            "default_page_size": default_page_size,
        },
    )


def _resolve_default_page_size(raw: Any) -> int | None:
    """Coerce an authored ``members.default_page_size`` value to a positive int or ``None``.

    The projected default is a single scalar (Phase 2 step (a)): a **positive integer**
    when the tenant has authored a usable value, else ``None`` so the field-config
    response omits a meaningful default and the renderer falls back to the per-user
    preference then the platform table-toolkit default (R2.1/R2.4). Degrades gracefully
    on projected config data — an absent (``None``), non-int, boolean, or non-positive
    value all collapse to ``None`` rather than raising. The authoring-plane validator
    (task 1.1) already rejects a non-positive value at Save; this is the symmetric
    read-side guard so a stray stored value never projects a zero/negative default.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw if raw > 0 else None
