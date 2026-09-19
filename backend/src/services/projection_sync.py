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

#: The fields a single projected dimension entry carries — the exact shape
#: ``ScopeDimension`` consumes (design.md "New governance projection rows",
#: ``config#scope``). Each is mapped from the authored parameter dict with a
#: safe default so a partial authoring never yields a malformed dimension.
_DIMENSION_DEFAULTS: dict[str, Any] = {
    "key": None,
    "label": dict,
    "enabled": True,
    "multi_valued": False,
    "values": list,
    "all_wildcard": None,
    "required_for": list,
}


def _map_scope_dimension(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one authored dimension dict to the ``config#scope`` dimension shape.

    Pure mapping of a single tenant-authored dimension parameter entry into the
    exact field set ``ScopeDimension`` consumes (``key``, ``label``, ``enabled``,
    ``multi_valued``, ``values``, ``all_wildcard``, ``required_for``). Unknown
    extra keys in the authored dict are dropped (the row carries only the shape
    the domain reads); absent fields fall back to a safe default so a partially
    authored dimension still yields a well-formed entry rather than raising.
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
    ``ScopeDimension`` consumes (``key``, ``label``, ``enabled``, ``multi_valued``,
    ``values``, ``all_wildcard``, ``required_for``).

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
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"),
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
}

#: The fields a single projected fixed-field override entry carries — the exact
#: set ``FixedFieldOverride`` consumes (``label``, ``visible``, ``required``,
#: ``order``). A ``None`` value means "leave the fixed base as-is", so the
#: defaults here are ``None`` (the override is presentation-only and additive);
#: only the keys the tenant actually authored are carried onto the row.
_FIXED_OVERRIDE_FIELDS = ("label", "visible", "required", "order")


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
    (``label``/``visible``/``required``/``order``) are carried onto the row; an
    unauthored aspect is simply absent (``FixedFieldOverride`` reads a missing
    attribute as "leave the fixed base as-is"). Unknown extra keys are dropped.
    """
    override: dict[str, Any] = {}
    for field_name in _FIXED_OVERRIDE_FIELDS:
        if field_name in raw and raw[field_name] is not None:
            override[field_name] = raw[field_name]
    return override


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
    if isinstance(raw_overlay, Mapping):
        raw_fields = raw_overlay.get("fields")
        if isinstance(raw_fields, Mapping):
            for name, entry in raw_fields.items():
                if isinstance(entry, Mapping):
                    fields[name] = _map_overlay_field(name, entry)

        raw_overrides = raw_overlay.get("overrides")
        if isinstance(raw_overrides, Mapping):
            for dotted_key, entry in raw_overrides.items():
                if isinstance(entry, Mapping):
                    overrides[dotted_key] = _map_fixed_override(entry)

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        version=_scope_config_version(tenant),
        attributes={"fields": fields, "overrides": overrides},
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
    """

    tenant: Mapping[str, Any]
    tenant_modules: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    user_tenant_roles: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


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
        return TenantSource(
            tenant=tenant_rows[0],
            tenant_modules=list(module_rows or ()),
            user_tenant_roles=list(role_rows or ()),
        )


# --- Sync result ------------------------------------------------------------


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a sync run (for observability + idempotence assertions).

    Attributes:
        written: Count of items actually written (put) this run.
        skipped: Count of items skipped because the stored version was already
            >= the incoming version (the idempotent/no-op path, R5.6).
        administrations: The ``administration`` values processed.
    """

    written: int = 0
    skipped: int = 0
    administrations: tuple[str, ...] = ()

    @property
    def is_noop(self) -> bool:
        """True iff nothing was written (a fully idempotent re-run)."""
        return self.written == 0


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
        table: A DynamoDB table writer (boto3 ``Table`` or a fake exposing
            ``get_item`` / ``put_item``). Optional — resolved lazily from the
            fail-fast schema helper when a write is first needed (R4.1).
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
        for administration in administrations:
            result = self.sync_administration(administration)
            total_written += result.written
            total_skipped += result.skipped
        return SyncResult(
            written=total_written,
            skipped=total_skipped,
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
           C2 Members rows — ``config#scope``, ``config#fields`` and the per-user
           ``scopegrant#…`` grants — by READING the tenant-scope ``members.*``
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
        items.extend(
            build_scopegrant_rows(source.tenant, source.user_tenant_roles, param_svc)
        )

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
        return SyncResult(
            written=written, skipped=skipped, administrations=(administration,)
        )

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

#: The resolved "all values" sentinel a projected all-access grant carries — the
#: same token ``sam/members/domain/scope_dimensions.WILDCARD`` uses so the module's
#: ``resolve_scope_access`` reads the projected ``["*"]`` grant as tenant-wide.
WILDCARD_VALUE = "*"

#: Separators an ``all_wildcard`` role name may use between its scoped-role prefix
#: and the value token — mirrors ``sam/members/domain/scope_access.py``
#: ``_scoped_role_prefix`` so the decode here agrees exactly with what
#: ``resolve_scope_access`` expects (e.g. ``"Regio_All"`` → prefix ``"Regio_"`` →
#: ``"Regio_Noord"`` decodes to ``"Noord"``). Kept as a module constant so the
#: builder and the domain resolver cannot drift on the prefix convention.
_SCOPED_ROLE_SEPARATORS = ("_", "-", ":", "/")


def _scoped_role_prefix(all_wildcard: Any) -> str | None:
    """Infer the scoped-role prefix from a dimension's ``all_wildcard`` role name.

    Mirrors ``sam/members/domain/scope_access._scoped_role_prefix`` exactly so a
    role name decodes to the same value the module's ``resolve_scope_access`` would
    derive: the prefix is everything up to and including the last separator in the
    wildcard role name (``"Regio_All"`` → ``"Regio_"``). Returns ``None`` when no
    prefix can be inferred (no ``all_wildcard``, or it carries no separator), in
    which case only a bare ``<value>`` role is honoured as a scoped grant.
    """
    if not all_wildcard or not isinstance(all_wildcard, str):
        return None
    for sep in _SCOPED_ROLE_SEPARATORS:
        idx = all_wildcard.rfind(sep)
        if idx != -1:
            return all_wildcard[: idx + 1]
    return None


def _decode_grant_for_dimension(
    dimension: Mapping[str, Any],
    user_roles: set[str],
) -> list[str] | None:
    """Decode one user's roles into the granted values for one dimension, or ``None``.

    The pure role→value decode, matching ``sam/members/domain/scope_access.py``
    resolution order so the projected grant is exactly what the module's
    ``resolve_scope_access`` would resolve (design C5 "the design projects values
    for ``scopegrant#`` … keeps ``resolve_scope_access`` as the deny-by-default
    authority"):

    - **all-access** — the user holds the dimension's ``all_wildcard`` role
      → ``["*"]`` (the wildcard sentinel).
    - **scoped** — the user holds roles decoding to declared ``values`` (bare
      ``<value>`` or prefixed ``<prefix><value>``, prefix inferred from
      ``all_wildcard``) → that subset, in the dimension's declared value order,
      de-duplicated (a multi-valued user's grants form the union).
    - **no grant** — neither → ``None`` (the caller emits **no row** for this
      (user, dimension); the module then applies deny-by-default via
      ``required_for``, R2.6). Deny is the *absence* of a row, never an empty one.

    A disabled dimension, or one without a usable ``key``, yields ``None`` — a
    disabled dimension is a tenant-wide no-op with nothing per-user to grant.
    """
    if not dimension.get("enabled", True):
        return None

    all_wildcard = dimension.get("all_wildcard")
    if all_wildcard and isinstance(all_wildcard, str) and all_wildcard in user_roles:
        return [WILDCARD_VALUE]

    raw_values = dimension.get("values") or ()
    if isinstance(raw_values, str) or not isinstance(raw_values, Sequence):
        raw_values = ()

    prefix = _scoped_role_prefix(all_wildcard)
    granted: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        if not isinstance(value, str) or value in seen:
            continue
        candidates = {value}
        if prefix is not None:
            candidates.add(f"{prefix}{value}")
        if candidates & user_roles:
            granted.append(value)
            seen.add(value)

    return granted or None


def build_scopegrant_rows(
    tenant: Mapping[str, Any],
    user_tenant_roles: Sequence[Mapping[str, Any]] | None,
    parameter_service: Any,
) -> list[ProjectionItem]:
    """Build the per-user ``scopegrant#<email>#<dimension>`` items (S5b C2, R2.1/R2.2).

    Decodes each user's per-tenant Members role assignments (MySQL
    ``user_tenant_roles`` rows — the ``email``/``role`` shape ``projection_builder``
    already mirrors as ``role#<email>#<role>``) into granted dimension values, using
    the dimension definitions the Tenant Admin authored
    (``members.scope_dimensions``, task 5.1's source). For each (user, dimension)
    with a grant it emits one ``scopegrant#<email>#<dimension>`` item:

    - ``values=["*"]`` when the user holds the dimension's all-access
      (``all_wildcard``) role, or
    - ``values=[<subset>]`` when the user holds subgroup-scoped role(s) decoding to
      declared dimension values (the union subset, in declared order).

    R2.2 — the grant is **derived here** from ``user_tenant_roles`` + the dimension
    values; it is NOT carried on the token nor invented in the module. The role→value
    decode mirrors ``sam/members/domain/scope_access.py`` (prefix inferred from
    ``all_wildcard``; ``all_wildcard`` role → ``["*"]``; ``<prefix><value>``/bare
    ``<value>`` → that value) so the projected grant is exactly what the module's
    ``resolve_scope_access`` would resolve (design C5).

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS the roles it
    is handed and the dimension params via ``ParameterService`` (read-only), and
    RETURNS the items for :class:`ProjectionSync` (the sole writer), mirroring the
    sibling ``config#scope``/``config#fields`` builders.

    Deny-by-default alignment (R2.6): a user with **no** scope-granting role in a
    dimension produces **no** row for that dimension — the module's deny-by-default
    (via ``required_for``) handles the absence. Only actual grants are emitted; a
    malformed role row (missing ``email``, non-mapping) is skipped, never raised.

    Empty-is-valid: a tenant that has authored no ``members.scope_dimensions`` — or
    has no role assignments — yields an empty list (no grants to project), never an
    error.

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        user_tenant_roles: The tenant's ``user_tenant_roles`` rows (``email``,
            ``role``). ``None``/empty → no grants.
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only — supplies the
            ``members.scope_dimensions`` dimension definitions used to decode roles.

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

    # Group each user's assigned role names (skip malformed rows — never raise).
    roles_by_email: dict[str, set[str]] = {}
    for role_row in user_tenant_roles or ():
        if not isinstance(role_row, Mapping):
            continue
        email = role_row.get("email")
        role = role_row.get("role")
        if not email or not role or not isinstance(role, str):
            continue
        roles_by_email.setdefault(email, set()).add(role)

    version = _scope_config_version(tenant)
    items: list[ProjectionItem] = []
    # Deterministic order: by email, then by dimension declaration order, so a
    # re-sync on unchanged input reproduces the same items (idempotence, R5.6).
    for email in sorted(roles_by_email):
        user_roles = roles_by_email[email]
        for dimension in dimensions:
            granted = _decode_grant_for_dimension(dimension, user_roles)
            if granted is None:
                continue
            dimension_key = dimension["key"]
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
