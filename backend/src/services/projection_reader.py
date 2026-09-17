"""Tenant-scoped, read-only reader for the S3 governance projection (design.md D3, T19).

S3 (`s3-claims-and-projection`) copies the **tenant-level** governance subset
forward into a DynamoDB projection the SAM/Lambda module plane reads. This module
is the **read side (module plane)** named in design.md D3 "Components and
interfaces" — the tenant-level companion to the Flask plane's
:mod:`auth.role_cache` (cached, TTL, invalidate) for tenant-level facts.

What the reader does (design.md D3 "Read side (module plane)" + R5.4/R5.8/R5.9):

1. **Reads one tenant only (R5.4).** Every read is scoped to a single
   ``tenant_id`` — the partition key. A ``query`` reads only that tenant's
   partition; a ``get`` reads a single item by ``(tenant_id, sort_key)``. The
   partition key *is* the tenancy boundary, so an item from another tenant is
   **structurally unaddressable** from tenant ``T``'s scope: you cannot even
   express a read that returns another tenant's item. IAM ``dynamodb:LeadingKeys``
   (see :data:`services.projection_schema.LEADING_KEYS_IAM_POLICY_PLAN`) restricts
   a caller's *credentials* to its own partition as **defense in depth** — the
   correctness guarantee comes from the key design, the IAM condition is a second
   independent layer, matching the S1 Scope seam.

2. **Version-aware caching + invalidation (R5.8).** Reads are cached per
   ``(tenant_id, sort_key)`` with a TTL (mirroring ``role_cache.py``'s 5-minute
   TTL). On every cache hit the reader compares the ``version`` it holds against
   the projection's current ``version``; when the projection's version is
   **strictly greater**, the cached read is invalidated and refreshed. Staleness
   is therefore bounded by ``sync delay (R5.7) + read TTL`` — documented and
   **never unbounded**. A cache entry also expires purely on TTL even if nothing
   asks it to compare versions, so a stale entry cannot live past the TTL.

3. **Never writes (R5.9).** A module *reads* the projection and **never** writes
   it or writes back to MySQL. This class is **structurally read-only**: it
   exposes no ``put`` / ``write`` / ``delete`` method and never calls
   ``put_item`` / ``delete_item`` on the injected table. The one-directional
   guarantee (R5.1/R5.2/R5.9) holds structurally, not by convention.

**Dependency injection (testability).** The reader depends on two narrow seams so
the T20/T22 property tests (and the example tests) can drive it with in-memory
fakes and never touch real AWS:

- a *table reader* — anything exposing DynamoDB's ``get_item`` / ``query`` (a
  boto3 ``Table`` in production; an in-memory fake in tests). Resolved lazily from
  :func:`services.projection_schema.get_projection_table_resource` (fail-fast env,
  R4.1) only when a read is first needed, so importing this module never forces
  AWS config.
- an optional *clock* (``() -> float``) so tests can drive TTL expiry
  deterministically without sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from boto3.dynamodb.conditions import Key

from services import projection_schema as schema

# Default read-side TTL. Mirrors auth/role_cache.py's 5-minute TTL so the
# tenant-level projection cache and the Flask-plane per-tenant role cache share
# one staleness convention. Combined with the sync delay (R5.7) this bounds
# staleness (R5.8) — it is never unbounded.
DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes


@dataclass
class _CacheEntry:
    """One cached projection item read.

    Attributes:
        item: The cached DynamoDB item dict (or ``None`` for a cached "absent").
        version: The ``version`` attribute held at cache time — compared against
            the projection's current version to detect staleness (R5.8).
        cached_at: Monotonic-ish timestamp (from the injected clock) the entry was
            stored, used for TTL expiry.
    """

    item: dict | None
    version: Any
    cached_at: float


def _version_supersedes(current_version: Any, cached_version: Any) -> bool:
    """Return True iff ``current_version`` should invalidate ``cached_version``.

    A newer projection version (strictly greater) invalidates the cached read
    (R5.8). A ``None`` cached version (we cached an absent item) is superseded by
    any present current version. Equal or lower current versions are not newer, so
    the cache stays valid. Comparison uses natural ordering; incomparable types
    raise rather than silently mis-ordering.
    """
    if current_version is None:
        return False
    if cached_version is None:
        return True
    return current_version > cached_version


class ProjectionReader:
    """Tenant-scoped, read-only reader of the governance projection (design.md D3, T19).

    Reads the projection for **one** ``tenant_id`` at a time (partition key +
    IAM ``LeadingKeys`` defense-in-depth), caches reads with a TTL, and refreshes
    a cached read when the projection's ``version`` advances (R5.8). Exposes **no**
    write surface (R5.9): a module reads the projection and never writes it or
    MySQL.

    Args:
        table: A DynamoDB table reader (boto3 ``Table`` or a fake exposing
            ``get_item`` / ``query``). Optional — resolved lazily from the
            fail-fast schema helper when a read is first needed (R4.1).
        cache_ttl_seconds: TTL for cached reads. Bounds staleness together with
            the sync delay (R5.8). Defaults to :data:`DEFAULT_CACHE_TTL_SECONDS`.
        clock: Optional ``() -> float`` time source (injected for deterministic
            TTL testing). Defaults to :func:`time.time`.
    """

    def __init__(
        self,
        *,
        table: Any = None,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._table = table
        self._cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock or time.time
        # Cache keyed by (tenant_id, sort_key) -> _CacheEntry.
        self._cache: dict[tuple[str, str], _CacheEntry] = {}

    @property
    def table(self) -> Any:
        """Return the injected table, else lazily resolve the real one (fail-fast).

        Resolution is deferred so importing/constructing the reader never forces
        DynamoDB env config; only an actual read triggers the fail-fast env
        resolution (R4.1).
        """
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    # --- tenant-scoped reads (R5.4) ----------------------------------------

    def query_tenant(self, tenant_id: str) -> list[dict]:
        """Return every projection item for ``tenant_id`` (that tenant only, R5.4).

        Issues a DynamoDB ``Query`` on the partition key ``tenant_id``. Because
        the partition key is the tenancy boundary, the query is *incapable* of
        returning another tenant's item — cross-tenant reads are structurally
        unaddressable. This read is intentionally **uncached** (it is a
        full-partition scan used for enumeration); per-item reads use
        :meth:`get_item` which is cached + version-aware.

        Args:
            tenant_id: The caller's own tenant / ``administration`` (partition
                key). Must be non-empty — a blank tenant is a cross-tenant hazard.

        Returns:
            The list of item dicts in ``tenant_id``'s partition (possibly empty).

        Raises:
            ValueError: ``tenant_id`` is empty.
        """
        if not tenant_id:
            raise ValueError(
                "tenant_id must be non-empty — a blank tenant scope is a "
                "cross-tenant hazard (R5.4)"
            )
        response = self.table.query(
            KeyConditionExpression=Key(schema.PARTITION_KEY_ATTR).eq(tenant_id)
        )
        items = response.get("Items", []) if isinstance(response, Mapping) else []
        return [dict(item) for item in items]

    def get_item(
        self, tenant_id: str, sort_key: str, *, refresh: bool = True
    ) -> dict | None:
        """Return one projection item for ``(tenant_id, sort_key)``, version-aware cached.

        Reads a single item scoped to ``tenant_id`` (its own partition, R5.4).
        The result is cached per ``(tenant_id, sort_key)`` with the reader's TTL.
        Cache behaviour (R5.8):

        - **Expired (past TTL):** the entry is dropped and the item is re-read.
        - **Fresh + ``refresh=True`` (default):** the reader performs a lightweight
          version check against the projection; if the projection's ``version`` is
          strictly greater than the cached one, the cached read is invalidated and
          refreshed (staleness bounded by sync delay + TTL, never unbounded).
        - **Fresh + ``refresh=False``:** the cached item is returned without a
          version check (a caller explicitly tolerating up-to-TTL staleness).

        Args:
            tenant_id: The caller's own tenant (partition key). Must be non-empty.
            sort_key: The item's sort-key value (see
                :func:`services.projection_schema.build_sort_key`).
            refresh: When True (default), compare versions on a cache hit and
                refresh on a newer projection version (R5.8).

        Returns:
            The item dict, or ``None`` if no such item exists in the tenant's
            partition.

        Raises:
            ValueError: ``tenant_id`` or ``sort_key`` is empty.
        """
        if not tenant_id:
            raise ValueError(
                "tenant_id must be non-empty — a blank tenant scope is a "
                "cross-tenant hazard (R5.4)"
            )
        if not sort_key:
            raise ValueError("sort_key must be non-empty")

        cache_key = (tenant_id, sort_key)
        now = self._clock()
        entry = self._cache.get(cache_key)

        if entry is not None:
            if self._is_expired(entry, now):
                # TTL elapsed: the entry cannot live past the TTL (bounded
                # staleness, R5.8) — drop and re-read.
                self._cache.pop(cache_key, None)
                entry = None
            elif not refresh:
                # Caller tolerates up-to-TTL staleness; skip the version check.
                return entry.item
            else:
                # Fresh entry: compare the held version against the projection's
                # current version. A newer version invalidates/refreshes (R5.8);
                # otherwise the cached read stands.
                current_version = self._read_current_version(tenant_id, sort_key)
                if not _version_supersedes(current_version, entry.version):
                    return entry.item
                self._cache.pop(cache_key, None)
                entry = None

        # Cache miss / invalidated: read the item and (re)cache it.
        item = self._read_item(tenant_id, sort_key)
        version = item.get(schema.VERSION_ATTR) if item is not None else None
        self._cache[cache_key] = _CacheEntry(item=item, version=version, cached_at=now)
        return item

    # --- cache management (R5.8) -------------------------------------------

    def invalidate(self, tenant_id: str, sort_key: str) -> None:
        """Drop the cached read for ``(tenant_id, sort_key)`` (mirrors role_cache).

        A caller that learns a projection item changed can force the next
        :meth:`get_item` to re-read. Absent entry -> no-op.
        """
        self._cache.pop((tenant_id, sort_key), None)

    def invalidate_tenant(self, tenant_id: str) -> None:
        """Drop every cached read for ``tenant_id`` (e.g. after a tenant-wide sync)."""
        for key in [k for k in self._cache if k[0] == tenant_id]:
            self._cache.pop(key, None)

    def clear_cache(self) -> None:
        """Drop the entire read cache."""
        self._cache.clear()

    # --- internals ---------------------------------------------------------

    def _is_expired(self, entry: _CacheEntry, now: float) -> bool:
        """True iff ``entry`` is older than the TTL (bounded staleness, R5.8)."""
        return (now - entry.cached_at) >= self._cache_ttl_seconds

    def _read_item(self, tenant_id: str, sort_key: str) -> dict | None:
        """Read one item by primary key, scoped to ``tenant_id`` (R5.4). Read-only.

        Builds the primary key through :func:`services.projection_schema.build_key`
        so the ``tenant_id`` partition-key is always present — the read cannot be
        expressed against another tenant's partition.
        """
        key = schema.build_key(tenant_id, sort_key)
        response = self.table.get_item(Key=key)
        stored = response.get("Item") if isinstance(response, Mapping) else None
        return dict(stored) if stored else None

    def _read_current_version(self, tenant_id: str, sort_key: str) -> Any:
        """Read just the current ``version`` for the item's key (staleness probe).

        Reads the item (scoped to ``tenant_id``) and returns its ``version``, or
        ``None`` if the item is absent / carries no version. Used by
        :meth:`get_item` to decide whether a cached read is stale (R5.8).
        """
        item = self._read_item(tenant_id, sort_key)
        if item is None:
            return None
        return item.get(schema.VERSION_ATTR)
