"""Scope-vocabulary resolver — the single Flask-side read seam for scope dimensions.

**Option B (Members/02 mirror retirement).** Three Flask-side readers used to
resolve the tenant's scope vocabulary from a frontend-written DERIVED MIRROR,
``members.scope_dimensions`` in MySQL:

1. the grant-validation service (:mod:`services.user_tenant_scope_service`),
2. the scope picker API (``routes.tenant_admin_scope.get_scope_dimensions``),
3. the ``scopegrant#<email>#<dimension>`` projection builder
   (:mod:`services._projection_scopegrant`).

That mirror was a second authoring door for config the module plane already owns,
and a cross-plane write the frontend had to sequence by hand (SAM ``config#scope``
first, Flask mirror second, with a retry path for the mirror leg alone). This
module retires it: the vocabulary is read from ``config#scope`` — the
module-plane-owned projection row whose authoritative author is the SAM write path
(``PUT /members/config/scope``, Members/02 Req 11.1/11.2) — through the existing
read-only :class:`services.projection_reader.ProjectionReader`.

Read semantics are unchanged from the retired param read:

- **Empty-is-valid.** An absent row, an absent/non-list ``dimensions`` attribute,
  or an empty list resolves to ``[]``. Every caller already treats that as
  tenant-wide / deny-by-default — never a hardcoded placeholder scope model
  (ONBOARDING D16).
- **A read FAILURE propagates.** A projection that cannot be read is surfaced to
  the caller (the picker maps it to a 5xx; the sync run fails loudly), never
  silently substituted with a placeholder (ONBOARDING D16).

**Staleness (the deliberate trade).** The projection is one-directional and
eventually consistent, so a just-authored change becomes visible after
``sync delay + read TTL`` rather than synchronously. Option B accepts that:
ONE authoritative writer with bounded, documented staleness beats two writers
that had to be kept in step by hand. The authoring path fires ``enqueue_sync``
(and the Tenant-Admin surface offers an explicit "Re-sync now"), so the window
is short and recoverable.

**One-directional discipline (Property 1).** This module only READS. It exposes
no write surface and never writes MySQL or the projection.

Requirements: Members/02 R22.3/R22.4 (retired), R11.1/R11.2
Reference: .kiro/specs/Common/Tenant/admin-surface-registry/design.md (Option B)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from services import projection_schema as schema

logger = logging.getLogger(__name__)

#: The projected row carrying the scope vocabulary: ``config#scope``. Built via
#: the schema's sole sort-key assembler so this read cannot drift from the write.
SCOPE_CONFIG_SORT_KEY = schema.build_sort_key(
    schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_SCOPE
)

#: The attribute on the ``config#scope`` row holding the dimension definitions —
#: the shape ``sam/members/domain/scope_dimensions.py`` ``ScopeDimension`` consumes
#: (``key``, ``field``, ``label``, ``enabled``, ``values``, ``required_for``).
DIMENSIONS_ATTR = "dimensions"


def load_scope_dimensions(
    tenant_id: str, *, reader: Any = None
) -> list[dict[str, Any]]:
    """Return ``config#scope``'s dimension definitions for ``tenant_id``.

    Reads the tenant's own partition only (the partition key *is* the tenancy
    boundary — a foreign tenant's row is structurally unaddressable) via the
    read-only :class:`ProjectionReader`.

    Args:
        tenant_id: The verified tenant / ``administration`` (partition key).
            Must be non-empty — a blank tenant is a cross-tenant hazard.
        reader: Optional pre-built ``ProjectionReader`` (injected in tests, or
            shared when a caller issues several reads in one request). Resolved
            lazily to a default reader only when omitted, so importing this
            module never forces AWS config.

    Returns:
        The dimension entries, in declared order. ``[]`` when the row is absent,
        carries no ``dimensions`` list, or the list is empty (empty-is-valid —
        callers collapse that to tenant-wide / deny-by-default). Entries that are
        not objects or carry no ``key`` are dropped, matching every caller's own
        filter.

    Raises:
        ValueError: ``tenant_id`` is empty.
    """
    if not tenant_id:
        raise ValueError(
            "tenant_id must be non-empty — a blank tenant scope is a "
            "cross-tenant hazard (steering 31)"
        )

    if reader is None:
        from services.projection_reader import ProjectionReader

        reader = ProjectionReader()

    item = reader.get_item(tenant_id, SCOPE_CONFIG_SORT_KEY)
    if not isinstance(item, Mapping):
        logger.debug(
            "scope_vocabulary: no config#scope row for tenant %r — empty vocabulary",
            tenant_id,
        )
        return []

    raw_dimensions = item.get(DIMENSIONS_ATTR)
    if isinstance(raw_dimensions, str) or not isinstance(raw_dimensions, Sequence):
        return []

    return [
        dict(entry)
        for entry in raw_dimensions
        if isinstance(entry, Mapping) and entry.get("key")
    ]


def dimension_index(
    dimensions: Sequence[Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Index dimension definitions for validation/lookup, enabled dimensions only.

    A DISABLED dimension is omitted, so a grant naming it is rejected as unknown
    and the ``scopegrant#`` builder emits no row for it — the tenant-wide no-op
    both callers already implement.

    Args:
        dimensions: The ``config#scope`` dimension entries, as returned by
            :func:`load_scope_dimensions` (or read from that row).

    Returns:
        A map ``dimension_key -> entry`` where each entry carries
        ``canon_to_value`` (``{canonical_form: declared_value}``),
        ``declared_order`` (the authoring order, also exposed as ``values``), and
        ``field`` (the bound member field key, or ``None``).

        The canonical form comes from the shared
        :func:`services.scope_canon.scope_canon`, so authoring validation and the
        projection builder compare values on ONE convention (R9.6).
    """
    from services.scope_canon import scope_canon

    index: dict[str, dict[str, Any]] = {}
    for dimension in dimensions or ():
        if not isinstance(dimension, Mapping):
            continue
        key = dimension.get("key")
        if not key:
            continue
        if not dimension.get("enabled", True):
            continue

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

        index[key] = {
            "canon_to_value": canon_to_value,
            "declared_order": declared_order,
            "values": list(declared_order),
            "field": dimension.get("field") or None,
        }
    return index
