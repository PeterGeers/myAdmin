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

**Write decision (R1.2/R1.3/R1.5/R5.6).** The write is decided in Python, not by a
datastore compare-and-set:

- The sync reads the FULL stored item (``get_item``) and writes iff the item is new,
  its SEMANTIC CONTENT differs from the stored row (content-driven, R1.2/R1.3 — this
  heals a stale row wedged at the current version), OR its ``version`` strictly
  supersedes the stored one (an additional trigger that keeps the S3 monotonic-version
  contract: a real version bump is picked up, a stale lower version never clobbers,
  R5.6/R5.8). An unchanged source is a no-op (idempotent). This is the logic the
  property tests exercise against an in-memory fake.
- The ``put_item`` carries **NO** DynamoDB ``ConditionExpression`` (design.md A3 option
  (a), decided in task 3.2): the single-process Flask monolith drains its projection
  queue SERIALLY (``projection_sync_trigger``), so there is no concurrent second writer
  of a given key to race — a datastore guard buys nothing and would only risk
  re-wedging a row by rejecting a real content change at an equal/lower version. The
  rare genuine race resolves last-writer-wins and self-corrects on the next (content-
  driven) sync. Benign no-op handling is retained defensively: a
  ``ConditionalCheckFailedException`` surfaced by any table wrapper is still treated as
  a no-op rather than a crash, preserving idempotence.

Internal layout (code-quality split M2 — a pure structural refactor, no behaviour
change). This module is the **stable facade**: its full public import surface
(``ProjectionSync`` / ``SyncResult`` / ``TenantSource`` / ``SourceProvider`` /
``DatabaseSourceProvider`` / ``build_config_scope_row`` / ``build_config_fields_row`` /
``build_config_mail_row`` / ``build_scopegrant_rows`` /
``_supersedes`` / ``_SCOPEGRANT_MODULE`` …) is preserved and re-exported here. The pure, read-only
builders and the source seam live in cohesive sub-modules:

- :mod:`services._projection_config_builders` — the tenant-level ``config#*`` row
  builders (``config#scope`` / ``config#fields``) + their maps
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

import json
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
    build_config_mail_row,
    build_config_scope_row,
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


# Bookkeeping attribute names EXCLUDED from the content comparison (R1.5,
# design.md A3 step 2). ``version``/``updated_at`` are volatile recording/ordering
# metadata, NOT semantic payload: a row whose semantic content is unchanged but
# whose version advanced must NOT count as a "content change". The key attributes
# (``tenant_id``/``sk``) are the item's identity, not payload, so they are excluded
# too — the content key is computed per-key, so including them would be redundant
# and would wrongly make two different keys' contents never compare equal.
_CONTENT_EXCLUDED_ATTRS = frozenset(
    {
        schema.PARTITION_KEY_ATTR,
        schema.SORT_KEY_ATTR,
        schema.VERSION_ATTR,
        "updated_at",
    }
)


def _content_key(dynamo_item: Mapping[str, Any]) -> str:
    """Return a canonical, stable content key for a (stored or incoming) item.

    The WRITE DECISION is content-driven (R1.2/R1.3, design.md A3): two items are
    "the same content" iff their SEMANTIC PAYLOAD is equal, independent of the
    volatile ``version``/``updated_at`` bookkeeping (:data:`_CONTENT_EXCLUDED_ATTRS`)
    and of the key attributes (identity, compared separately per-key). The payload
    is canonicalised to a stable JSON string — ``sort_keys=True`` so attribute order
    never matters, ``default=str`` so a ``Decimal`` / ``datetime`` left on a stored
    row (DynamoDB numerics deserialize to ``Decimal``) renders deterministically.
    ``ensure_ascii=False`` keeps unicode payloads (e.g. ``Overleden``) stable rather
    than escaped.

    General (R1.7): computed over the FLAT ``to_dynamodb_item()`` shape, so it
    applies uniformly to ``config#fields`` / ``config#scope`` / ``config#mail`` and
    every base/scopegrant row — not a status/``config#fields`` special case.

    Args:
        dynamo_item: A rendered DynamoDB item dict (incoming
            :meth:`ProjectionItem.to_dynamodb_item` output, or a stored row read
            back via ``get_item``).

    Returns:
        A canonical JSON string of the item's semantic payload (excluding
        bookkeeping + key attrs). Equal strings ⇒ equal content ⇒ skip; different
        strings ⇒ content differs ⇒ write.
    """
    payload = {
        key: value
        for key, value in dynamo_item.items()
        if key not in _CONTENT_EXCLUDED_ATTRS
    }
    return json.dumps(
        payload, sort_keys=True, default=str, ensure_ascii=False, separators=(",", ":")
    )


# NOTE (TASK 3.2, design.md A3 option (a)): the projection write carries NO
# DynamoDB ``ConditionExpression``. The single-process Flask monolith drains its
# projection queue SERIALLY (``projection_sync_trigger``), so there is no concurrent
# second writer of a given key to guard against; the write decision is content-driven
# (``_conditional_put``) and a datastore compare-and-set would only risk re-wedging a
# row (an equal/lower incoming version blocking a real content change). The former
# ``attribute_not_exists(#v) OR #v < :incoming`` guard was therefore removed.

# The parameter namespace carrying the Members tenant-scope config the C2 builders
# read. Mirrors ``_projection_config_builders._MEMBERS_PARAM_NAMESPACE`` (kept local
# so the facade does not import a private name): used to evict this tenant's cached
# members config before a build so the sync reads a non-stale source (R1.1, A2).
_MEMBERS_PARAM_NAMESPACE = "members"


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
           C2 Members rows — ``config#scope``, ``config#fields``,
           ``config#mail`` (pivot-output-actions R0) and the per-user
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
        # BUILD FROM A COHERENT (UNCACHED) SOURCE (R1.1, design.md A2). The sync's
        # ParameterService is a process-wide singleton reused across every run, so a
        # value cached by an earlier run (or a concurrent one) can serialize STALE
        # content while the UNCACHED ``get_param_revision`` stamps a FRESH version —
        # the version/content desync that wedges a row. Drop this service's cached
        # ``members.*`` values for THIS tenant before building, so the builders re-read
        # the current value and the built content always matches its version. No MySQL
        # I/O (read-only cache maintenance) → the one-directional guarantee holds.
        self._invalidate_members_cache(param_svc, administration)
        # config#scope is NO LONGER emitted by ProjectionSync (spec 02 Task 3.7).
        # The SAM write path (MembersConfigWriteRepository via PUT /members/config/scope) is now
        # the AUTHORITATIVE author of the `config#scope` row; the frontend writes it first and
        # mirrors the dimension set into Flask `members.scope_dimensions` (the frontend-mirror
        # model, Req 22/26). ProjectionSync must not co-author `config#scope` (split-ownership,
        # Req 11.1/11.2). `members.scope_dimensions` persists ONLY as the frontend-written mirror
        # the grant validators read (R22.3/22.4) — it is no longer a ProjectionSync source. The
        # `build_config_scope_row` builder itself is KEPT (still imported/exported) because the
        # builder-unit-tests + the round-trip/equivalence tests consume it directly — only the
        # EMISSION from sync_administration is removed here (the builder is deleted by a later
        # end-of-band cleanup task once the scope migration is complete).
        # config#fields is NO LONGER emitted by ProjectionSync (spec 02 Task 1.15).
        # The SAM write path (MembersConfigWriteRepository via PUT /members/config/fields) is
        # now the AUTHORITATIVE author of the `config#fields` row in both TEST and PROD (the
        # per-tenant migration ran + read-back verified). ProjectionSync must not co-author it
        # (split-ownership, Req 11.1/11.2). `members.field_overlay` is SAM-owned; the retired
        # `members.default_page_size` (Req 25) is projected nowhere. The `build_config_fields_row`
        # builder itself is KEPT (still imported/exported) because the one-off migration script
        # (`backend/scripts/migrate_config_fields_to_sam.py`) and the builder-unit-tests consume
        # it directly — only the EMISSION from sync_administration is removed here.
        # R0 (pivot-output-actions, design §6.3): the per-tenant mail-enabled gate.
        # Projected as config#mail so the Members edge reads the flag via the
        # projection reader (no live MySQL at request time); fail-closed to False.
        config_mail = build_config_mail_row(source.tenant, param_svc)
        if config_mail is not None:
            items.append(config_mail)
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

        # Resolve DUPLICATE keys within this batch to their LAST occurrence before
        # the content-driven write (R1.3/R1.6 idempotence). A source can legitimately
        # list two rows that collapse to one projection key with DIFFERENT content
        # (e.g. the same module twice, active + inactive); the final stored state is
        # last-writer-wins, so only the LAST occurrence of a key drives the write.
        # Earlier occurrences are counted as skips (they would be immediately
        # overwritten), which (a) keeps the write decision purely content-driven
        # instead of thrashing between two contents on every re-sync — the old
        # version gate only masked this by skipping equal-version duplicates — and
        # (b) preserves the batch attempt count (written + skipped == len(items)).
        last_index_for_key: dict[tuple[str, str], int] = {}
        for index, item in enumerate(items):
            last_index_for_key[(item.tenant_id, item.sort_key)] = index

        written = 0
        skipped = 0
        for index, item in enumerate(items):
            is_last_for_key = (
                last_index_for_key[(item.tenant_id, item.sort_key)] == index
            )
            if is_last_for_key and self._conditional_put(item):
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

    def _invalidate_members_cache(self, param_svc: Any, administration: str) -> None:
        """Best-effort: drop the param service's cached ``members.*`` for one tenant.

        Called at the start of each tenant's C2 build (R1.1, design.md A2) so the
        ``config#*`` builders read the CURRENT source value rather than a value a
        previous/concurrent sync left cached on the reused ParameterService — the fix
        that keeps a built row's content coherent with its (uncached) version.

        Resolved defensively via ``getattr`` so any read-only param provider that does
        NOT expose the invalidation seam (e.g. a minimal test fake, or a provider whose
        reads are already uncached) is simply skipped — the sync still works, it just
        does not need the eviction. Read-only cache maintenance: no MySQL write, so the
        one-directional guarantee (Property 1) is untouched.
        """
        invalidate = getattr(param_svc, "invalidate_namespace", None)
        if callable(invalidate):
            invalidate(_MEMBERS_PARAM_NAMESPACE, tenant=administration)

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

    def delete_config_views_residue(
        self, administrations: Sequence[str], *, dry_run: bool = True
    ) -> dict[str, int]:
        """Delete stored ``config#views`` PROJECTION residue per tenant (R2.1/R2.6).

        Phase 2 step (d): ``config#views`` (the retired Members ``view_contexts``
        column-layouts) is NO LONGER emitted — the builder was removed and the sync
        never produces the row (``config#views`` would even fail
        :func:`validate_items` now). BUT a stored row written BEFORE retirement is
        ORPHANED: unlike ``scopegrant#…`` rows (swept by
        :meth:`_reconcile_scopegrants`), ``config#*`` rows are UPSERT-ONLY — the
        reconcile is confined to the ``scopegrant#…`` SK space and never deletes a
        ``config#*`` row (see
        ``test_sync_reconcile_never_deletes_non_scopegrant_rows``). So an orphaned
        ``config#views`` row is never swept automatically; this explicit, tenant-scoped
        cleanup removes it.

        Tenant-scoped (Property 1/2, R5.4): each tenant's row is addressed by its own
        partition key (``build_key(administration, 'config#views')``) via ``get_item``
        — the loop never addresses another tenant's partition. Confined to the single
        ``config#views`` SK per tenant: no other record type is read or deleted.

        Idempotent (R2.1): a tenant with no residue contributes 0; a re-run after a
        successful apply finds nothing and deletes 0 — a safe no-op.

        ``dry_run`` is the DEFAULT: a dry run COUNTS the present residue rows and makes
        NO write; pass ``dry_run=False`` to actually ``delete_item`` them. Mirrors the
        ``--dry-run`` contract of the companion MySQL migration
        (``retire_members_view_contexts.py``) — but this touches the DynamoDB projection
        table, not MySQL, so it lives with the sole-writer of that table (here), not in
        a MySQL migration.

        Args:
            administrations: The tenant scopes to clean. No tenant name is hardcoded —
                the caller supplies the tenants from the data (`31` Data Ownership).
            dry_run: When True (default), only count; when False, delete.

        Returns:
            A summary dict ``{"scanned": <rows present>, "deleted": <rows deleted>}``.
            ``deleted`` is 0 on a dry run.
        """
        views_sk = schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_VIEWS
        )
        scanned = 0
        deleted = 0
        for administration in administrations:
            key = schema.build_key(administration, views_sk)
            response = self.table.get_item(Key=key)
            stored = response.get("Item") if isinstance(response, Mapping) else None
            if not stored:
                continue
            scanned += 1
            logger.info(
                "config#views residue present for tenant %r%s",
                administration,
                " (dry run — not deleting)" if dry_run else "",
            )
            if dry_run:
                continue
            self.table.delete_item(Key=key)
            deleted += 1
        logger.info(
            "config#views residue cleanup %s: %d scanned, %d deleted.",
            "DRY RUN" if dry_run else "APPLIED",
            scanned,
            deleted,
        )
        return {"scanned": scanned, "deleted": deleted}

    def _stored_item(self, item: ProjectionItem) -> Mapping[str, Any] | None:
        """Return the FULL currently-stored row for ``item``'s key, or ``None``.

        Reads the projection table (``get_item``) for the item's primary key and
        returns the whole stored item (all attributes), so the content-driven write
        decision (:meth:`_conditional_put`, R1.2/R1.3, design.md A3) can compare the
        stored SEMANTIC PAYLOAD — not just the ``version`` — against the incoming
        row. A missing item yields ``None`` (treated as "absent" → the incoming
        write always lands, healing a never-written key).
        """
        key = schema.build_key(item.tenant_id, item.sort_key)
        response = self.table.get_item(Key=key)
        stored = response.get("Item") if isinstance(response, Mapping) else None
        return stored or None

    def _conditional_put(self, item: ProjectionItem) -> bool:
        """Write ``item`` iff it is new OR its CONTENT differs from the stored row.

        CONTENT-DRIVEN WRITE DECISION (R1.2/R1.3/R1.5/R1.6/R1.7, design.md A3).
        ``version`` is NO LONGER the sole gate — it desynced from content and
        wedged a stale row at the current revision so the old strict-greater gate
        could never heal it. The decision is now:

        1. Read the FULL stored row (:meth:`_stored_item`).
        2. **Write when stored is ABSENT or the semantic CONTENT differs**
           (:func:`_content_key` — the payload canonicalised, excluding
           ``version``/bookkeeping): this HEALS the wedge (content differs at an
           equal version, R1.2/R1.8).
        3. **Skip when content is EQUAL** (idempotent, no churn, R1.3/R1.6) — even
           if the version advanced; a truly-unchanged re-sync writes nothing.
        4. As an ADDITIONAL (not sole) trigger, a strict-greater ``version`` with
           EQUAL content still writes, so version keeps its recording/ordering role
           (R1.5) and the S3 monotonic-version contract (R5.6/R5.8: a real version
           bump is picked up, a stale lower version never clobbers) is preserved.
           The union — ``absent OR content-differs OR version-supersedes`` — is the
           reconciliation: content difference is a NEW reason to write that the old
           version-only gate lacked; it never skips a content change and never
           churns on an unchanged source.

        Datastore concurrency guard (DECIDED in TASK 3.2, design.md A3 option (a)).
        The put carries **NO** ``ConditionExpression``. Task 3.1 left a MIXED stopgap
        — the strict-greater ``#v < :incoming`` guard attached on the version-driven
        path but OMITTED on the content-heal path (so it could not reject a heal). A3
        asked for a coherent final choice between (a) dropping the version condition
        and relying on last-writer-wins, or (b) a content/etag datastore guard. We
        take (a): the condition is dropped ENTIRELY, because the single-process Flask
        monolith drains its projection queue SERIALLY — ``projection_sync_trigger``'s
        in-process ``InMemorySyncQueue`` is drained synchronously, one administration
        at a time, in the same process that enqueued it (see
        ``ProjectionSyncTrigger._drain`` / ``enqueue``). There is no concurrent second
        writer of a given key to race, so a datastore compare-and-set buys nothing and
        would only risk re-introducing the wedge (an equal/lower incoming version
        blocking a real content change). The reconciliation backstop (``sync_all``) is
        likewise serial. For the rare genuine race, last-writer-wins is acceptable and
        self-corrects on the next sync (the write decision is content-driven, so a
        later sync re-detects any divergence and rewrites). ``version``/``updated_at``
        STAY on the row (:meth:`ProjectionItem.to_dynamodb_item`) for recording ("when
        last projected") and for ordering genuinely concurrent writes (R1.5) — they are
        just no longer a datastore write gate.

        Benign no-op handling is RETAINED defensively: should any configured table
        wrapper still surface a ``ConditionalCheckFailedException`` (a real boto3
        ``Table`` can carry a table-level condition, or a test fake may raise one), it
        is treated as a benign no-op (a concurrent writer already advanced the row —
        R5.6), never a crash. Any other error propagates (fail loudly).

        Returns:
            True if the item was written, False if skipped as a content-equal no-op.
        """
        stored = self._stored_item(item)
        dynamo_item = item.to_dynamodb_item()

        version_supersedes = _supersedes(
            item.version, stored.get(schema.VERSION_ATTR) if stored else None
        )
        content_differs = stored is None or _content_key(stored) != _content_key(
            dynamo_item
        )

        # Content-driven gate (R1.2/R1.3): write on absence or a content change;
        # version supersession is an additional trigger (R1.5, S3 R5.6/R5.8) that
        # keeps a pure version bump writing and a stale lower version skipping.
        if not content_differs and not version_supersedes:
            return False

        # Last-writer-wins put: NO datastore ConditionExpression (design.md A3 (a)).
        # The serial in-process drain means there is no concurrent writer to guard
        # against, and the Python content/version decision above is the sole gate —
        # so the datastore write is unconditional, which also means a content-heal at
        # an equal/lower version can never be rejected (the wedge this spec fixes).
        try:
            self.table.put_item(Item=dynamo_item)
        except Exception as exc:
            # Defensive: if some table wrapper still raises a conditional-check
            # failure (benign — a concurrent writer already advanced the row, R5.6),
            # treat it as a no-op rather than crashing the sync. Any other error
            # propagates (fail loudly).
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
    "build_config_mail_row",
    "build_config_scope_row",
    "build_scopegrant_rows",
]
