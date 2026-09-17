"""Unit tests for the S3 tenant-scoped projection reader (T19, R5.4/R5.8/R5.9).

Covers design.md D3 "Read side (module plane)" + "Cache invalidation on the read
side": ``ProjectionReader`` reads the projection for ONE ``tenant_id`` only
(partition key + IAM ``LeadingKeys`` defense-in-depth), caches reads with a TTL,
refreshes a cached read when the projection's ``version`` advances, and exposes
NO write surface (a module reads the projection, never writes it or MySQL).

These are concrete example tests using an **in-memory fake** for the DynamoDB
table seam (no real AWS): a ``FakeTable`` implementing ``get_item`` / ``query``
scoped by the partition key. The exhaustive property-based coverage (Property 3
tenant isolation, Property 6 convergence) lands in T20/T22; these pin the
behaviour with specific scenarios.

Feature: s3-claims-and-projection
"""

import pytest

from services import projection_schema as schema
from services.projection_reader import (
    DEFAULT_CACHE_TTL_SECONDS,
    ProjectionReader,
)


# --- in-memory fake table ---------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (read side).

    Stores items keyed by (tenant_id, sk) and implements the two read methods the
    reader uses:

    - ``get_item(Key=...)`` returns the single item for that primary key.
    - ``query(KeyConditionExpression=...)`` returns ONLY the items whose partition
      key matches the equality condition — the same tenant-scoping a real table +
      IAM ``LeadingKeys`` enforces. The fake extracts the requested tenant from the
      boto3 ``Key(...).eq(...)`` condition so cross-tenant items are never
      returned.

    Records ``get_item`` calls so tests can assert the version-check re-read
    behaviour of the cache.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.get_calls: list[dict] = []

    def put(self, item: dict) -> None:
        """Test helper — seed an item (NOT part of the reader's surface)."""
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def get_item(self, Key):
        self.get_calls.append(dict(Key))
        item = self.store.get(
            (Key[schema.PARTITION_KEY_ATTR], Key[schema.SORT_KEY_ATTR])
        )
        return {"Item": dict(item)} if item is not None else {}

    def query(self, KeyConditionExpression=None):
        # The reader always queries by partition-key equality. Extract the tenant
        # value from the boto3 condition object and return only that partition.
        tenant_id = _tenant_from_condition(KeyConditionExpression)
        items = [
            dict(v) for k, v in self.store.items() if k[0] == tenant_id
        ]
        return {"Items": items}


def _tenant_from_condition(condition):
    """Extract the partition-key value from a boto3 Key(...).eq(...) condition.

    boto3's ``Equals`` condition exposes its operands via ``get_expression()``;
    values[1] is the compared value. This mirrors what a real DynamoDB Query does
    (scope to one partition) so the fake cannot leak cross-tenant items.
    """
    expr = condition.get_expression()
    return expr["values"][1]


# --- helpers ----------------------------------------------------------------


_TENANT_SK = schema.build_sort_key(schema.RECORD_TYPE_TENANT)
_MODULE_SK = schema.build_sort_key(schema.RECORD_TYPE_MODULE, "members")


def _item(tenant_id, sort_key, version, **attrs):
    item = dict(attrs)
    item[schema.PARTITION_KEY_ATTR] = tenant_id
    item[schema.SORT_KEY_ATTR] = sort_key
    item[schema.VERSION_ATTR] = version
    return item


class _Clock:
    """Deterministic clock for TTL tests (no sleeping)."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# --- reads only own tenant's items (R5.4) -----------------------------------


def test_query_tenant_returns_only_own_tenant_items():
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1, display_name="A"))
    table.put(_item("TenantA", _MODULE_SK, 1, is_active=True))
    table.put(_item("TenantB", _TENANT_SK, 1, display_name="B"))

    reader = ProjectionReader(table=table)

    items = reader.query_tenant("TenantA")

    tenants_returned = {i[schema.PARTITION_KEY_ATTR] for i in items}
    assert tenants_returned == {"TenantA"}
    assert len(items) == 2


def test_get_item_reads_own_tenant_item():
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1, display_name="A Ltd"))
    reader = ProjectionReader(table=table)

    item = reader.get_item("TenantA", _TENANT_SK)

    assert item is not None
    assert item["display_name"] == "A Ltd"
    assert item[schema.PARTITION_KEY_ATTR] == "TenantA"


def test_get_item_absent_returns_none():
    table = FakeTable()
    reader = ProjectionReader(table=table)
    assert reader.get_item("TenantA", _TENANT_SK) is None


# --- a cross-tenant key is not addressable from tenant T's scope (R5.4) -----


def test_cross_tenant_key_not_addressable_via_query():
    """Tenant B's items never appear in a query scoped to Tenant A."""
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1))
    table.put(_item("TenantB", _TENANT_SK, 1))
    table.put(_item("TenantB", _MODULE_SK, 1))

    reader = ProjectionReader(table=table)

    a_items = reader.query_tenant("TenantA")
    assert all(i[schema.PARTITION_KEY_ATTR] == "TenantA" for i in a_items)
    assert not any(i[schema.PARTITION_KEY_ATTR] == "TenantB" for i in a_items)


def test_get_item_cannot_reach_other_tenants_item_under_own_scope():
    """Requesting TenantB's sort key under TenantA's scope yields nothing.

    The primary key is (tenant_id, sort_key); asking for TenantA + a sort key
    that only exists under TenantB returns None — the other tenant's item is
    unaddressable from TenantA's scope (R5.4).
    """
    table = FakeTable()
    only_b_sk = schema.build_sort_key(schema.RECORD_TYPE_MODULE, "webshop")
    table.put(_item("TenantB", only_b_sk, 1, is_active=True))

    reader = ProjectionReader(table=table)

    # From TenantA's scope, the key (TenantA, only_b_sk) does not exist.
    assert reader.get_item("TenantA", only_b_sk) is None
    # It IS addressable under TenantB's own scope.
    assert reader.get_item("TenantB", only_b_sk) is not None


def test_query_tenant_rejects_blank_tenant():
    reader = ProjectionReader(table=FakeTable())
    with pytest.raises(ValueError):
        reader.query_tenant("")


def test_get_item_rejects_blank_scope():
    reader = ProjectionReader(table=FakeTable())
    with pytest.raises(ValueError):
        reader.get_item("", _TENANT_SK)
    with pytest.raises(ValueError):
        reader.get_item("TenantA", "")


# --- caching: a hit within TTL does not re-read unnecessarily ---------------


def test_get_item_caches_within_ttl_without_refresh():
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1))
    clock = _Clock()
    reader = ProjectionReader(table=table, clock=clock)

    reader.get_item("TenantA", _TENANT_SK)  # miss -> read
    first_reads = len(table.get_calls)

    # refresh=False: a cached hit returns without any further table read.
    cached = reader.get_item("TenantA", _TENANT_SK, refresh=False)
    assert cached is not None
    assert len(table.get_calls) == first_reads  # no extra read


# --- a newer version refreshes the cached read (R5.8) -----------------------


def test_newer_version_refreshes_cached_read():
    table = FakeTable()
    table.put(_item("TenantA", _MODULE_SK, 1, is_active=True))
    clock = _Clock()
    reader = ProjectionReader(table=table, clock=clock)

    first = reader.get_item("TenantA", _MODULE_SK)
    assert first[schema.VERSION_ATTR] == 1
    assert first["is_active"] is True

    # Projection advances (sync wrote a newer version with a changed attr).
    table.put(_item("TenantA", _MODULE_SK, 2, is_active=False))

    # Within TTL, but the version is newer -> cache invalidated + refreshed.
    refreshed = reader.get_item("TenantA", _MODULE_SK)
    assert refreshed[schema.VERSION_ATTR] == 2
    assert refreshed["is_active"] is False


def test_same_version_keeps_cached_read():
    table = FakeTable()
    table.put(_item("TenantA", _MODULE_SK, 5, is_active=True))
    clock = _Clock()
    reader = ProjectionReader(table=table, clock=clock)

    reader.get_item("TenantA", _MODULE_SK)

    # Sneak a different attr into the store WITHOUT bumping the version. Since the
    # version is unchanged, the reader must keep serving the cached value (R5.8:
    # invalidation keys off the version marker).
    table.put(_item("TenantA", _MODULE_SK, 5, is_active=False))

    still_cached = reader.get_item("TenantA", _MODULE_SK)
    assert still_cached["is_active"] is True  # cached (version unchanged)


def test_cache_expires_after_ttl():
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1, display_name="old"))
    clock = _Clock()
    reader = ProjectionReader(
        table=table, clock=clock, cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS
    )

    reader.get_item("TenantA", _TENANT_SK, refresh=False)

    # Change the stored item (same version) and advance past the TTL. TTL expiry
    # alone must force a re-read even without a version comparison — staleness is
    # bounded by the TTL, never unbounded.
    table.put(_item("TenantA", _TENANT_SK, 1, display_name="new"))
    clock.advance(DEFAULT_CACHE_TTL_SECONDS + 1)

    refreshed = reader.get_item("TenantA", _TENANT_SK, refresh=False)
    assert refreshed["display_name"] == "new"


# --- explicit invalidation (mirrors role_cache.invalidate_cache) ------------


def test_invalidate_forces_reread():
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1, display_name="old"))
    clock = _Clock()
    reader = ProjectionReader(table=table, clock=clock)

    reader.get_item("TenantA", _TENANT_SK, refresh=False)
    table.put(_item("TenantA", _TENANT_SK, 1, display_name="new"))

    reader.invalidate("TenantA", _TENANT_SK)

    assert reader.get_item("TenantA", _TENANT_SK, refresh=False)["display_name"] == "new"


def test_invalidate_tenant_clears_only_that_tenant():
    table = FakeTable()
    table.put(_item("TenantA", _TENANT_SK, 1))
    table.put(_item("TenantB", _TENANT_SK, 1))
    reader = ProjectionReader(table=table)

    reader.get_item("TenantA", _TENANT_SK, refresh=False)
    reader.get_item("TenantB", _TENANT_SK, refresh=False)

    reader.invalidate_tenant("TenantA")

    # TenantA re-reads (cleared); TenantB still cached — assert via call counts.
    before = len(table.get_calls)
    reader.get_item("TenantB", _TENANT_SK, refresh=False)  # cached, no read
    assert len(table.get_calls) == before
    reader.get_item("TenantA", _TENANT_SK, refresh=False)  # cleared, re-reads
    assert len(table.get_calls) == before + 1


# --- reader has NO write surface (R5.9) -------------------------------------


def test_reader_has_no_write_surface():
    """Structural guardrail: the reader exposes no method that writes."""
    write_ish = {
        "put",
        "put_item",
        "write",
        "delete",
        "delete_item",
        "update",
        "update_item",
        "save",
        "commit",
    }
    method_names = {n.lower() for n in dir(ProjectionReader) if not n.startswith("_")}
    assert not (method_names & write_ish), (
        f"ProjectionReader must be read-only (R5.9); found write-ish methods: "
        f"{method_names & write_ish}"
    )


def test_reader_never_calls_table_write_methods():
    """The reader must never invoke put_item/delete_item on the table (R5.9)."""

    class RecordingTable(FakeTable):
        def __init__(self):
            super().__init__()
            self.writes: list[str] = []

        def put_item(self, *a, **k):  # pragma: no cover - must not be called
            self.writes.append("put_item")

        def delete_item(self, *a, **k):  # pragma: no cover - must not be called
            self.writes.append("delete_item")

    table = RecordingTable()
    table.put(_item("TenantA", _TENANT_SK, 1))
    reader = ProjectionReader(table=table)

    reader.query_tenant("TenantA")
    reader.get_item("TenantA", _TENANT_SK)
    reader.get_item("TenantA", _MODULE_SK)

    assert table.writes == []
