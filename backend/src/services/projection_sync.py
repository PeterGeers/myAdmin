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

Internal layout (code-quality split M2 — a pure structural refactor, no behaviour
change). This module is the **stable facade**: its full public import surface
(``ProjectionSync`` / ``SyncResult`` / ``TenantSource`` / ``SourceProvider`` /
``DatabaseSourceProvider`` / ``build_config_scope_row`` / ``build_config_fields_row`` /
``build_config_views_row`` / ``build_scopegrant_rows`` / ``_supersedes`` /
``_SCOPEGRANT_MODULE`` …) is preserved and re-exported here. The pure, read-only
builders and the source seam live in cohesive sub-modules:

- :mod:`services._projection_config_builders` — the tenant-level ``config#*`` row
  builders (``config#scope`` / ``config#fields`` / ``config#views``) + their maps
  and the shared ``_scope_config_version``.
- :mod:`services._projection_scopegrant` — the per-user ``scopegrant#…`` builder
  (``build_scopegrant_rows`` + its freshness/parse helpers + ``_SCOPEGRANT_MODULE``).
- :mod:`services._projection_source` — the read-only MySQL source seam
  (``TenantSource`` / ``SourceProvider`` / ``DatabaseSourceProvider``).

The **sole-writer orchestrator** — :class:`ProjectionSync`, its ``SyncResult``, the
version/diff/apply helpers (``_supersedes`` / ``_conditional_put`` /
``_reconcile_scopegrants``) — stays HERE: it is the one component that WRITES, and it
composes the builders + source seam above.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services import projection_schema as schema

# ── Pure tenant-level config#* row builders ──────────────────────────────────────────
# (The config-only maps/constants + the shared ``_scope_config_version`` live in the
# sub-module and are consumed by the builders there; only the three public ``build_*``
# functions are part of this facade's import surface.)
from services._projection_config_builders import (
    build_config_fields_row,
    build_config_scope_row,
    build_config_views_row,
)

# ── Pure per-user scopegrant#… builder (+ the module token the route layer references) ─
from services._projection_scopegrant import (
    _SCOPEGRANT_MODULE,
    WILDCARD_VALUE,
    build_scopegrant_rows,
)

# ── Read-only source seam (TenantSource / SourceProvider / DatabaseSourceProvider) ───
from services._projection_source import (
    DatabaseSourceProvider,
    SourceProvider,
    TenantSource,
)
from services.projection_builder import (
    ProjectionItem,
    build_projection_items,
)
from services.projection_validator import validate_items

logger = logging.getLogger(__name__)


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

            self._parameter_service = ParameterService(DatabaseManager())
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


__all__ = [
    "WILDCARD_VALUE",
    "_SCOPEGRANT_MODULE",
    # Sole-writer orchestrator (defined here); read-only source seam, config#* row
    # builders, and the per-user scopegrant#… builder (re-exported from sub-modules).
    "DatabaseSourceProvider",
    "ProjectionSync",
    "SourceProvider",
    "SyncResult",
    "TenantSource",
    "_supersedes",
    "build_config_fields_row",
    "build_config_scope_row",
    "build_config_views_row",
    "build_scopegrant_rows",
]
