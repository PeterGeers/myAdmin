"""Pure builder for S3 governance projection items (design.md D3, R5.3).

S3 (`s3-claims-and-projection`) copies the **tenant-level** governance subset
forward into a DynamoDB projection the SAM/Lambda module plane reads. This module
is the pure transform at the heart of that sync (the ``ProjectionItem`` builder
named in design.md D3 "Components and interfaces"):

    (tenant, tenant_modules[], user_tenant_roles[]) -> list[ProjectionItem]

**Purity (R5.3, PBT-friendly).** This module performs **no** I/O — no DynamoDB,
no MySQL, no env reads, no clock reads. Given the same inputs it produces the
same output, so the T13 fidelity property test (Property 2) can exercise it over
a large generated input space deterministically. The sync (T16) is responsible
for reading the source rows and writing the items; the validator (T14) checks
them; this module only *shapes* them.

**What is projected (design.md D3 "What is projected (R5.3)").** Only the
tenant-level subset, and only for tenants that have at least one **SAM-backed**
module enabled (``module_registry.module_backing(name) == "sam"``). For such a
tenant the builder emits:

- one ``tenant`` item (tenant existence + tenant-level attributes),
- one ``module#<name>`` item per enabled module (with ``is_active``),
- one ``role#<email>#<role>`` item per ``user_tenant_roles`` grant — the tenant's
  role assignments **as tenant-level reference data**.

**What is NOT projected — that is S4.** The per-user *resolved answer* ("what may
this specific user do right now") belongs in the token (S4), not here. This
builder never resolves a user's effective permissions, never collapses roles into
a decision, and never emits a per-user entitlement item. It only mirrors the
tenant's role-assignment rows as reference data. If a fact belongs in the token,
it is not produced here.

**Key shape reuse (T11).** Every key is built through
:mod:`services.projection_schema` (``PARTITION_KEY_ATTR``, ``SORT_KEY_ATTR``,
``VERSION_ATTR``, ``build_sort_key``, the record-type tokens). This module does
**not** redefine the key shape — the "#"-join convention and attribute names live
solely in the schema module so the builder, validator, sync, and read side cannot
diverge.

**Version (design.md D3 "Versioning + idempotence, R5.6").** Each item carries a
``version`` (the schema's :data:`~services.projection_schema.VERSION_ATTR`)
sourced from the row's revision / ``updated_at``. The builder does not invent a
clock value (that would break purity/idempotence); it reads a version field off
the source row and, absent one, falls back to a deterministic ``0`` so the item is
still well-formed and re-running on unchanged input is a no-op.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from services import projection_schema as schema
from services.module_registry import module_backing

# Candidate source-row fields that carry a monotonic version, in priority order.
# The sync/source may label the revision differently across the three source
# tables; the builder reads whichever is present so it stays decoupled from a
# single column name. A row with none of these gets the deterministic fallback.
_VERSION_FIELDS = ("version", "updated_at", "revision", "modified_at")

# Deterministic version used when a source row carries no version field. A fixed
# value (not a clock read) keeps the builder pure and the sync idempotent (R5.6):
# re-running on unchanged input reproduces the same version, so no version churn.
_DEFAULT_VERSION = 0


@dataclass(frozen=True)
class ProjectionItem:
    """One item destined for the governance projection table (design.md D3).

    Immutable so the builder's output can be freely reused/compared in property
    tests without aliasing surprises. Carries exactly the projection table's
    shape: the tenant partition key, the composite sort key, the projected
    attributes, and a version.

    Attributes:
        tenant_id: Partition-key value (== ``administration``, the tenancy
            boundary, R5.4).
        sort_key: Composite sort-key value (``record_type#id``), built via
            :func:`services.projection_schema.build_sort_key`.
        version: Monotonic per-item version (source revision / ``updated_at``),
            used by the sync's conditional write (R5.6) and read-side staleness
            detection (R5.8).
        attributes: The projected, non-key attributes (e.g. ``is_active``,
            ``role``, tenant fields). Never contains per-user resolved/token-only
            data (that is S4).
    """

    tenant_id: str
    sort_key: str
    version: Any
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def to_dynamodb_item(self) -> dict[str, Any]:
        """Render this item as a flat DynamoDB item dict (key attrs + version + attrs).

        Uses the schema module's canonical attribute names so the physical item
        matches the table shape T11 defined. The key attributes and version take
        precedence over any same-named entry in ``attributes`` (keys are
        authoritative and must not be shadowed).

        Returns:
            A dict with :data:`~services.projection_schema.PARTITION_KEY_ATTR`,
            :data:`~services.projection_schema.SORT_KEY_ATTR`,
            :data:`~services.projection_schema.VERSION_ATTR`, and the projected
            attributes — ready for ``put_item`` once validated (T14) by the sync
            (T16).
        """
        item: dict[str, Any] = dict(self.attributes)
        item[schema.PARTITION_KEY_ATTR] = self.tenant_id
        item[schema.SORT_KEY_ATTR] = self.sort_key
        item[schema.VERSION_ATTR] = self.version
        return item


def _extract_version(row: Mapping[str, Any]) -> Any:
    """Return the first present, non-null version field on a row, else the default.

    Reads (never writes) the row. The lookup order is :data:`_VERSION_FIELDS`;
    a missing/``None`` field is skipped so an ``updated_at`` can backstop a
    missing ``version``. Absent all of them, returns :data:`_DEFAULT_VERSION`
    (deterministic — no clock read), preserving purity and idempotence (R5.6).
    """
    for name in _VERSION_FIELDS:
        value = row.get(name)
        if value is not None:
            return value
    return _DEFAULT_VERSION


def _has_sam_backed_module_enabled(tenant_modules: Sequence[Mapping[str, Any]]) -> bool:
    """True iff at least one enabled module in the list is SAM-backed.

    "Enabled" means the row's ``is_active`` is truthy. Backing is resolved via
    :func:`services.module_registry.module_backing`; an unknown module name
    raises there — the builder does not swallow it, since an unrecognised module
    in the source is a real misconfiguration the sync should surface (R5.5 spirit).
    A ``flask``-backed-only tenant is intentionally excluded: the projection
    exists solely for the SAM/Lambda module plane (design.md D3).
    """
    for module_row in tenant_modules:
        if not module_row.get("is_active"):
            continue
        if module_backing(module_row["module_name"]) == "sam":
            return True
    return False


def _tenant_id_of(tenant: Mapping[str, Any]) -> str:
    """Extract the tenant's ``administration`` (partition-key value), or raise.

    Accepts either ``administration`` (the source-of-record column name) or the
    already-canonical ``tenant_id`` as the key field. A blank/missing value is a
    cross-tenant hazard (R5.4) and raises rather than producing a keyless item.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )
    return tenant_id


def _tenant_attributes(tenant: Mapping[str, Any]) -> dict[str, Any]:
    """Project a tenant's non-key attributes for the ``tenant`` record.

    Copies the tenant row's fields except the key/version fields (which are set
    explicitly on the item) so tenant-level attributes modules need travel with
    the item. No per-user or token-only data is present in a ``tenants`` row, so
    nothing here can leak S4 data.
    """
    excluded = {schema.PARTITION_KEY_ATTR, "administration", *_VERSION_FIELDS}
    return {k: v for k, v in tenant.items() if k not in excluded}


def build_projection_items(
    tenant: Mapping[str, Any],
    tenant_modules: Sequence[Mapping[str, Any]] | None = None,
    user_tenant_roles: Sequence[Mapping[str, Any]] | None = None,
) -> list[ProjectionItem]:
    """Build the tenant-level projection items for one tenant (pure, R5.3).

    Pure transform — no I/O, no clock, deterministic. Produces the projection
    items for ``tenant`` **iff** the tenant has at least one SAM-backed module
    enabled; otherwise returns an empty list (the projection serves the module
    plane only, design.md D3). For an eligible tenant it emits:

    - one ``tenant`` item (existence + tenant-level attributes),
    - one ``module#<module_name>`` item per module row (carrying ``is_active``),
    - one ``role#<email>#<role>`` item per ``user_tenant_roles`` grant (tenant
      role-assignment reference data — **not** a per-user resolved answer; that
      is S4).

    Every key is built through :mod:`services.projection_schema` (T11) and every
    item carries a ``version`` read from the source row (deterministic fallback
    when absent) so the sync's idempotent/versioned write (R5.6) works.

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``).
        tenant_modules: The tenant's ``tenant_modules`` rows (``module_name``,
            ``is_active``). Defaults to empty.
        user_tenant_roles: The tenant's ``user_tenant_roles`` rows (``email``,
            ``role``). Defaults to empty.

    Returns:
        The projection items for this tenant, or ``[]`` if it has no SAM-backed
        module enabled.

    Raises:
        ValueError: The tenant is missing its key, or a module row is missing
            ``module_name`` / references an unknown module.
    """
    modules = list(tenant_modules or ())
    roles = list(user_tenant_roles or ())

    # Gate: only tenants with a SAM-backed module enabled are projected (R5.3).
    if not _has_sam_backed_module_enabled(modules):
        return []

    tenant_id = _tenant_id_of(tenant)
    items: list[ProjectionItem] = []

    # 1) The tenant record: existence + tenant-level attributes.
    items.append(
        ProjectionItem(
            tenant_id=tenant_id,
            sort_key=schema.build_sort_key(schema.RECORD_TYPE_TENANT),
            version=_extract_version(tenant),
            attributes=_tenant_attributes(tenant),
        )
    )

    # 2) One item per module the tenant has (SAM or flask — the module list is
    #    tenant-level reference data; the *gate* above is what scopes projection
    #    to SAM-enabled tenants, not per-module filtering).
    for module_row in modules:
        module_name = module_row.get("module_name")
        if not module_name:
            raise ValueError(
                f"tenant_modules row for tenant {tenant_id!r} is missing "
                f"'module_name': {dict(module_row)!r}"
            )
        items.append(
            ProjectionItem(
                tenant_id=tenant_id,
                sort_key=schema.build_sort_key(schema.RECORD_TYPE_MODULE, module_name),
                version=_extract_version(module_row),
                attributes={"is_active": bool(module_row.get("is_active"))},
            )
        )

    # 3) One item per role grant — tenant-level role-assignment reference data.
    #    NOT a per-user resolved answer (that is S4): we mirror the (email, role)
    #    rows verbatim, we do not compute effective permissions.
    for role_row in roles:
        email = role_row.get("email")
        role = role_row.get("role")
        if not email or not role:
            raise ValueError(
                f"user_tenant_roles row for tenant {tenant_id!r} is missing "
                f"'email'/'role': {dict(role_row)!r}"
            )
        items.append(
            ProjectionItem(
                tenant_id=tenant_id,
                sort_key=schema.build_sort_key(schema.RECORD_TYPE_ROLE, email, role),
                version=_extract_version(role_row),
                attributes={"email": email, "role": role},
            )
        )

    return items
