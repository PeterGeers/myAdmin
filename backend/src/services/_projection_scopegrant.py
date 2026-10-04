"""Governance projection — per-user ``scopegrant#<email>#<dimension>`` builder
(extracted from ``projection_sync`` for cohesion).

The read-only builder that sources each user's scope from the MySQL
``user_tenant_scope`` table and shapes it into the per-user ``scopegrant#…`` projection
rows the SAM/Lambda module plane reads (S5b design.md C2, R2.1/R2.2). Re-exported from
:mod:`services.projection_sync`; its public import surface is unchanged.

One-directional discipline (Property 1): the builder issues **zero** MySQL writes and
does **not** write the projection itself — it only READS the scope rows it is handed and
the dimension params via ``ParameterService`` (read-only) and RETURNS the items for the
sole writer (:class:`services.projection_sync.ProjectionSync`). Pure structural split
(code-quality M2) with zero behaviour change.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from services import projection_schema as schema
from services._projection_config_builders import (
    _MEMBERS_PARAM_NAMESPACE,
    _SCOPE_DIMENSIONS_PARAM_KEY,
    _scope_config_version,
)
from services.projection_builder import (
    ProjectionItem,
    _normalize_version,
)
from services.scope_canon import scope_canon

logger = logging.getLogger(__name__)

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


__all__ = [
    "WILDCARD_VALUE",
    "_SCOPEGRANT_MODULE",
    "_SCOPEGRANT_VERSION_FIELDS",
    "_parse_scopes",
    "_scopegrant_version",
    "build_scopegrant_rows",
]
