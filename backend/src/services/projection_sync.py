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
from services.projection_builder import ProjectionItem, build_projection_items
from services.projection_validator import validate_items

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
    """

    def __init__(self, source: SourceProvider, *, table: Any = None) -> None:
        self._source = source
        self._table = table

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
        2. Build items via the pure T12 builder (empty when the tenant has no
           SAM-backed module enabled -> nothing to project).
        3. **Validate the whole batch first** (T14). A malformed item raises
           :class:`~services.projection_validator.ProjectionValidationError`
           **before any write**, so there is no partial/garbage projection (R5.5).
        4. Conditionally write each valid item: put only when new or the incoming
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
            return SyncResult(administrations=(administration,))

        # Validate the ENTIRE batch before writing anything — atomic per tenant,
        # no partial write on a malformed item (R5.5).
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
