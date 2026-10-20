"""Governance projection — tenant-level ``config#*`` row builders (extracted from
``projection_sync`` for cohesion).

The pure, read-only builders that shape a tenant's authored ``members.*`` tenant-scope
parameters into the ``config#scope`` / ``config#fields`` / ``config#mail`` projection
rows the SAM/Lambda module plane reads (S5b design.md C2). They are
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

#: The single tenant-scope parameter key that holds the tenant-level default
#: rows-per-page for the Members table (``members.default_page_size``, Phase 2
#: step (a)). A single scalar DEFAULT — not a stored view object (``38`` rule 3) —
#: carried onto the EXISTING ``config#fields`` row (NOT a new ``config#views`` row)
#: so the SAM reader can surface it on the field-config response alongside the
#: overlay. Read here read-only (Property 1); a per-user preference overrides it at
#: render and an unset value falls back to the platform table-toolkit default.
_DEFAULT_PAGE_SIZE_PARAM_KEY = "default_page_size"

#: The single tenant-scope parameter key that holds the per-tenant "mail-enabled /
#: SES-certified" onboarding gate flag as a boolean (pivot-output-actions R0,
#: task 0.4). Authored by the tenant-admin module (``members.mail_enabled``, same
#: ``/api/tenant-admin/parameters`` surface as ``scope_dimensions`` etc.); read
#: here and shaped into the ``config#mail`` row's ``mail_enabled`` attribute — the
#: shape the SAM-plane projection reader (``projection_config_reader.is_mail_enabled``)
#: consumes. This builder only READS whatever value exists (Property 1,
#: one-directional).
_MAIL_ENABLED_PARAM_KEY = "mail_enabled"

#: The tenant's own mail domain (e.g. ``h-dcn.nl``), authored at onboarding as the
#: ``members.mail_domain`` param (task 0.1 schema) and projected into ``config#mail``.
#: The Members send path composes the envelope From as
#: ``<mail_local_part|noreply>@<mail_domain>`` — the domain is NEVER projected as a
#: literal address. Read-only here (Property 1).
_MAIL_DOMAIN_PARAM_KEY = "mail_domain"

#: The From local-part (e.g. ``info``, ``onderhoud``), authored as the optional
#: ``members.mail_local_part`` param. DEFAULT ``"noreply"`` when unset/blank — the
#: SAME default the SAM reader (``get_mail_local_part``) applies, kept in sync here.
_MAIL_LOCAL_PART_PARAM_KEY = "mail_local_part"

#: The onboarding-recorded SES-verified flag (``members.mail_certified``, design
#: "Option B"). The pre-send certification check reads this projected boolean and
#: fails CLOSED when it is absent/False (R5.2/Property 4) — same discipline as
#: ``mail_enabled``.
_MAIL_CERTIFIED_PARAM_KEY = "mail_certified"

#: The OPTIONAL tenant-authored Reply-To default for SCHEDULED / unattended sends
#: (``members.mail_reply_to_default``, spec 02 Task 5.1). A scheduled send has no invoking
#: user, so its Reply-To is this authored address, falling back to the composed From when it
#: is absent (an interactive send instead uses the invoking user's verified email at runtime).
#: Projected onto ``config#mail`` ONLY when authored as a non-blank string.
_MAIL_REPLY_TO_DEFAULT_PARAM_KEY = "mail_reply_to_default"

#: The default From local-part projected when a tenant has authored no (or a blank)
#: ``members.mail_local_part``. MUST match the SAM reader's ``_DEFAULT_MAIL_LOCAL_PART``
#: so builder and reader agree on the composed-From local-part.
_MAIL_LOCAL_PART_DEFAULT = "noreply"

#: Member Application Form (application-app D9a/R8.3a, task 8.2) — the OPTIONAL,
#: tenant-config-gated "scope-matched copy" toggle, authored as the boolean
#: ``members.application_scope_copy`` param and projected onto the SAME ``config#mail``
#: row the sender config rides (design §7). When True AND the applicant selected a scope
#: value on the form, the staff notification SHALL ALSO copy the ``Members_CRUD`` users
#: scoped to that value (ADDING to the all-scope recipients, never replacing — D9a). The
#: application Reply-To param is DROPPED (D24 — Reply-To is the all-scope ``Members_CRUD``
#: set, not configured). Fail-closed: only an explicit boolean ``True`` enables the copy;
#: any other/absent value projects ``False`` (the D9 all-scope-only default).
_APPLICATION_SCOPE_COPY_PARAM_KEY = "application_scope_copy"

#: Member Application Form (application-app D26/R12.1a/R12.1c, task 8.2) — the per-tenant,
#: bilingual, VERSIONED consent/privacy notice, authored as the
#: ``members.application_consent_notice`` param and projected onto the SAME ``config#mail``
#: row. Each tenant authors its OWN notice text ``{nl, en}`` with a STABLE ``version`` id per
#: revision (D26): the public field-config read (R5) serves the current text + version to the
#: form, and a stored consent references the exact version accepted (a later revision never
#: retroactively changes an existing record's recorded version). Projected ONLY when
#: well-formed (a non-blank ``version`` AND at least one non-blank locale text); otherwise the
#: attribute is OMITTED so an un-authored tenant projects a back-compatible row (the platform
#: MAY seed a default notice elsewhere — R12.1c / steering 38).
_APPLICATION_CONSENT_NOTICE_PARAM_KEY = "application_consent_notice"

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


def _enum_values_from_field(spec: Mapping[str, Any]) -> list[str] | None:
    """Extract a field's ENUM VALUES — the single scope vocabulary (R3.4).

    The single-vocabulary rule (R3.2/R3.4): a scope-axis field's dimension values ARE the
    field's own enum values. They are read from the field's enum vocabulary, in priority
    order:

    - rich ``options`` — a list of ``{value, label?, roles?}`` dicts (or bare strings): the
      per-option ``value`` (or the bare string) is the vocabulary;
    - a bare ``choices`` string list.

    Returns the ordered, de-duplicated list of non-blank string values, or ``None`` when the
    field declares no usable enum vocabulary (not an enum / value-less) — the caller treats
    ``None`` as "no enum vocabulary", which is a validation error at save for an ENABLED
    scope axis (R3.4).
    """

    def _collect_values(raw: Any) -> list[str] | None:
        if not isinstance(raw, (list, tuple)):
            return None
        values: list[str] = []
        seen: set[str] = set()
        for entry in raw:
            if isinstance(entry, Mapping):
                value = entry.get("value")
            else:
                value = entry
            if not isinstance(value, str) or not value.strip():
                continue
            if value in seen:
                continue
            seen.add(value)
            values.append(value)
        return values or None

    # Rich `options` first (the canonical enum vocabulary), then bare `choices`.
    return _collect_values(spec.get("options")) or _collect_values(spec.get("choices"))


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


def _config_row_version(
    tenant: Mapping[str, Any],
    parameter_service: Any,
    tenant_id: str,
    param_keys: Sequence[str],
) -> Any:
    """Version a ``config#*`` row off its SOURCE param(s), not just the tenant row.

    THE VERSION-BUMP TRAP FIX (impact-analysis §0.3 / Phase 0 step 2). The
    ``config#*`` rows are written under the sync's VERSION-GUARDED conditional put
    (``_supersedes`` / the ``#v < :incoming`` condition), which writes only when the
    incoming ``version`` STRICTLY supersedes the stored one. Deriving that version
    from the TENANT row alone (:func:`_scope_config_version`) is the bug: editing a
    ``members.*`` param (e.g. ``field_overlay``) does NOT bump the tenant row, so the
    projected row keeps the same version, the conditional put SKIPS it, and the edit
    never reaches DynamoDB (``written=0 skipped=N`` — the #6/#7/#8 "config won't save"
    symptom). The historic workaround was to hand-bump ``tenants.updated_at``.

    FIX — version off the PARAM's own ``updated_at`` (``parameters`` table,
    ``ON UPDATE CURRENT_TIMESTAMP``) when it is present, exactly as
    :func:`services._projection_scopegrant._scopegrant_version` already does for
    per-user grants (same freshness mechanism, same monotonic ISO-8601 ordering via
    :func:`_normalize_version`):

    - (a) **advances on a param edit** — the edited param's ``updated_at`` moves
      forward, so the new version strictly supersedes the stored one and the put
      writes (the edit propagates — the trap is gone);
    - (b) **is stable on an unchanged re-sync** — an untouched param reproduces the
      SAME ``updated_at`` → same version → the conditional put is a no-op (idempotence
      preserved, no version churn, R5.6);
    - (c) **fits the existing plumbing** — ``_normalize_version`` renders the
      ``datetime`` to an ISO-8601 string that sorts lexicographically in chronological
      order, a valid monotonic version for BOTH the write conditional put and the
      read-side staleness check.

    When a row is driven by MORE THAN ONE param (``config#mail`` reads four keys), the
    MAX param revision wins so an edit to ANY of them bumps the row. Param revisions
    are compared only against each other (all ISO-8601 strings — safely ordered); the
    tenant-row version is used ONLY as the fallback when NO param in ``param_keys`` has
    a per-param revision (an un-authored row, or a source — e.g. a test fixture — that
    exposes no ``get_param_revision``). This mirrors ``_scopegrant_version``: never mix
    a param ISO timestamp and an int tenant ``version`` in one comparison.

    One-directional discipline (Property 1): only READS — ``get_param_revision`` issues
    a plain SELECT; this helper never writes MySQL.
    """
    revisions: list[Any] = []
    getter = getattr(parameter_service, "get_param_revision", None)
    if callable(getter):
        for key in param_keys:
            revision = getter(_MEMBERS_PARAM_NAMESPACE, key, tenant=tenant_id)
            if revision is not None:
                revisions.append(_normalize_version(revision))
    if revisions:
        return max(revisions)
    return _scope_config_version(tenant)


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


# --- R0 config#mail builder (pivot-output-actions R0, design §6.3, task 0.4) --


def _resolve_application_consent_notice(raw: Any) -> dict[str, Any] | None:
    """Shape an authored ``members.application_consent_notice`` value for ``config#mail``.

    The per-tenant, bilingual, VERSIONED consent notice (application-app D26/R12.1a/R12.1c,
    task 8.2). Returns the projected shape ``{"version": <str>, "text": {<locale>: <str>, …}}``
    when the authored value is well-formed, else ``None`` so the ``config#mail`` row OMITS the
    attribute (an un-authored / malformed notice is simply absent — a back-compatible row for a
    tenant not using the application form; the platform MAY seed a default elsewhere, R12.1c).

    Well-formed (projected) requires BOTH:

    - a STABLE ``version`` id — a non-blank string (the stable per-revision id a stored consent
      references so a later revision never retroactively changes an existing record, R12.1a);
      a non-string version is coerced to its ``str`` only when it is a non-blank scalar id
      (int/str), never fabricated;
    - at least ONE non-blank locale text under ``text`` (the bilingual ``{nl, en}`` body, R12.1c).

    Degrades gracefully on projected config data (never raises): a non-mapping value, a blank /
    absent version, or an empty/blank ``text`` all collapse to ``None``. Only non-blank string
    locale texts survive into the projected ``text`` map (a blank/non-string entry is dropped),
    so the served notice body is always ``{str: str}``. The authoring-plane validator (task 8.3
    companion) rejects a malformed notice at Save; this is the symmetric read-side guard so a
    stray stored value never projects a broken notice.
    """
    if not isinstance(raw, Mapping):
        return None

    raw_version = raw.get("version")
    if isinstance(raw_version, bool):
        return None
    if isinstance(raw_version, str):
        version = raw_version.strip()
    elif isinstance(raw_version, int):
        version = str(raw_version)
    else:
        version = ""
    if not version:
        return None

    raw_text = raw.get("text")
    if not isinstance(raw_text, Mapping):
        return None
    text: dict[str, str] = {}
    for locale, body in raw_text.items():
        if (
            isinstance(locale, str)
            and locale.strip()
            and isinstance(body, str)
            and body.strip()
        ):
            text[locale] = body
    if not text:
        return None

    return {"version": version, "text": text}


def build_config_mail_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#mail`` projection item (R0 + R4/R5).

    Reads the tenant's per-tenant mail parameters from the tenant-scope parameter
    system (``ParameterService.get_param`` on the ``members`` namespace) and shapes
    them into the SINGLE ``config#mail`` row — the shape the SAM-plane projection
    reader (``projection_config_reader``: ``is_mail_enabled`` / ``get_mail_domain`` /
    ``get_mail_local_part`` / ``is_mail_certified``) consumes. The Members edge reads
    this projected row at request time to decide whether to offer the mail output
    actions and to resolve the per-tenant sender (R1–R5); it NEVER queries MySQL
    (ADR 0005/0006).

    The four projected attributes (design "Data Models", task 0.2):

    - ``mail_enabled`` (bool) — the onboarding "cleared to send" gate (R0).
    - ``mail_domain`` (str, optional) — the tenant's own mail domain (e.g.
      ``h-dcn.nl``); the send path composes From = ``<local_part>@<domain>``. The
      domain is NEVER projected as a literal address. Projected ONLY when authored as
      a non-empty string; omitted otherwise (there is no safe default for a domain —
      a guessed host would send from a foreign domain, the ``jabaki.nl`` regression,
      R4.2 — so the reader resolves an absent domain to ``None`` and refuses the send).
    - ``mail_local_part`` (str) — the From local-part (e.g. ``info``); DEFAULT
      ``"noreply"`` when unset/blank, matching the SAM reader's default so builder and
      reader compose the SAME From.
    - ``mail_certified`` (bool) — the onboarding-recorded SES-verified flag ("Option
      B"); the pre-send check reads it and fails CLOSED when absent/False (R5.2).

    Two Member Application Form attributes ride this SAME row (application-app task 8.2;
    the application Reply-To param is DROPPED — D24):

    - ``application_scope_copy`` (bool, D9a) — the OPTIONAL tenant-gated "scope-matched
      copy" toggle; fail-closed ``False`` (only an explicit ``True`` enables the copy), so
      an un-authored tenant keeps the D9 all-scope-only recipients.
    - ``consent_notice`` ({version, text:{nl,en}}, D26) — the per-tenant, VERSIONED,
      bilingual consent/privacy notice; OMITTED when un-authored/malformed (a tenant not
      using the application form projects a back-compatible row).

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope rows read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    sibling ``config#scope`` / ``config#fields`` builders.

    Fail-closed defaults (R0/R4/R5): a tenant that has authored no parameter — or a
    malformed value — yields a safe, non-permissive row. ``mail_enabled`` and
    ``mail_certified`` collapse to ``False`` for any non-boolean-``True`` value (only
    an explicit ``True`` opens either gate; the absence NEVER opens it);
    ``mail_local_part`` collapses to ``"noreply"``; ``mail_domain`` is omitted when
    absent/blank (no guessed host). Returning the row (rather than ``None``) keeps the
    projection self-describing — a present-but-disabled gate is distinct from "not yet
    projected".

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.

    Returns:
        The ``config#mail`` :class:`ProjectionItem` for this tenant. ``None`` is
        never returned for a present tenant — an un-configured tenant still gets a
        well-formed, fail-closed row.

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
    raw_domain = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_DOMAIN_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_local_part = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_LOCAL_PART_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_certified = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_CERTIFIED_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_reply_to_default = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_REPLY_TO_DEFAULT_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_scope_copy = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _APPLICATION_SCOPE_COPY_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_consent_notice = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _APPLICATION_CONSENT_NOTICE_PARAM_KEY,
        tenant=tenant_id,
    )

    # Fail-closed: only an explicit boolean ``True`` opens a gate. Any other value —
    # absent (None), a stray string, a number — collapses to False, so a
    # malformed/absent gate can never silently permit sending (R0/R5.2/Property 4).
    mail_enabled = raw_flag is True
    mail_certified = raw_certified is True

    # D9a scope-copy toggle: fail-closed like the gate flags — only an explicit boolean
    # ``True`` enables the optional scope-matched copy; any other/absent value projects
    # ``False`` (the D9 all-scope-only default), so a malformed value never silently
    # fans the notification out to scope-limited recipients.
    application_scope_copy = raw_scope_copy is True

    # Local-part: optional with a generic default. A non-string/blank value falls back
    # to ``noreply`` so a From is always composable from a usable domain.
    if isinstance(raw_local_part, str) and raw_local_part:
        mail_local_part = raw_local_part
    else:
        mail_local_part = _MAIL_LOCAL_PART_DEFAULT

    attributes: dict[str, Any] = {
        "mail_enabled": mail_enabled,
        "mail_local_part": mail_local_part,
        "mail_certified": mail_certified,
        # Member Application Form (D9a): the scope-copy toggle always rides the row as a
        # fail-closed boolean (present-but-False is distinct from "not projected"), the
        # SAME discipline as the mail gate flags.
        "application_scope_copy": application_scope_copy,
    }

    # Domain: NO safe default (a guessed host = a foreign-sender leak, R4.2). Project
    # it ONLY when authored as a non-empty string; otherwise omit it so the reader
    # resolves ``None`` and the pre-send resolver refuses the send (fail-closed).
    if isinstance(raw_domain, str) and raw_domain:
        attributes["mail_domain"] = raw_domain

    # Reply-To default (Task 5.1): the SCHEDULED/unattended-send Reply-To. Project ONLY when
    # authored as a non-blank string; omit otherwise so the send path falls back to the From
    # address (an interactive send uses the invoking user's verified email at runtime instead).
    if isinstance(raw_reply_to_default, str) and raw_reply_to_default.strip():
        attributes["mail_reply_to_default"] = raw_reply_to_default

    # Member Application Form (D26): the versioned bilingual consent notice is projected
    # ONLY when well-formed (non-blank version + at least one locale text); otherwise it
    # is OMITTED so a tenant that authored none projects a back-compatible row (the public
    # field-config read then serves no tenant notice, falling back to a platform seed if any).
    consent_notice = _resolve_application_consent_notice(raw_consent_notice)
    if consent_notice is not None:
        attributes["consent_notice"] = consent_notice

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_MAIL
        ),
        # config#mail is driven by SEVEN params — the four mail params + the NEW
        # mail_reply_to_default (Task 5.1) + the two Member Application Form params (the D9a
        # scope-copy toggle + the D26 consent notice) that ride this row — so an edit to ANY
        # must bump the row (version-bump trap fix): the version is the max of their per-param
        # revisions, falling back to the tenant row only when none is authored.
        version=_config_row_version(
            tenant,
            parameter_service,
            tenant_id,
            (
                _MAIL_ENABLED_PARAM_KEY,
                _MAIL_DOMAIN_PARAM_KEY,
                _MAIL_LOCAL_PART_PARAM_KEY,
                _MAIL_CERTIFIED_PARAM_KEY,
                _MAIL_REPLY_TO_DEFAULT_PARAM_KEY,
                _APPLICATION_SCOPE_COPY_PARAM_KEY,
                _APPLICATION_CONSENT_NOTICE_PARAM_KEY,
            ),
        ),
        attributes=attributes,
    )


__all__ = [
    "_APPLICATION_CONSENT_NOTICE_PARAM_KEY",
    "_APPLICATION_SCOPE_COPY_PARAM_KEY",
    "_DEFAULT_PAGE_SIZE_PARAM_KEY",
    "_DIMENSION_DEFAULTS",
    "_FIELD_OVERLAY_PARAM_KEY",
    "_FIELD_SCOPE_ATTR",
    "_FIXED_OVERRIDE_FIELDS",
    "_FUNCTIONAL_GROUP_FIELDS",
    "_MAIL_CERTIFIED_PARAM_KEY",
    "_MAIL_DOMAIN_PARAM_KEY",
    "_MAIL_ENABLED_PARAM_KEY",
    "_MAIL_LOCAL_PART_DEFAULT",
    "_MAIL_LOCAL_PART_PARAM_KEY",
    "_MAIL_REPLY_TO_DEFAULT_PARAM_KEY",
    "_MEMBERS_PARAM_NAMESPACE",
    "_OVERLAY_FIELD_DEFAULTS",
    "_SCOPE_DIMENSIONS_PARAM_KEY",
    "_SCOPE_VERSION_FIELDS",
    "_config_row_version",
    "_enum_values_from_field",
    "_map_fixed_override",
    "_map_functional_group",
    "_map_overlay_field",
    "_map_scope_dimension",
    "_resolve_application_consent_notice",
    "_resolve_default_page_size",
    "_scope_config_version",
    "_scope_dimension_from_field",
    "_scope_dimensions_from_overlay",
    "build_config_fields_row",
    "build_config_mail_row",
    "build_config_scope_row",
]
