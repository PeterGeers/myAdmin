"""
S5b Task 8.6 — dedicated tenant-isolation tests for the Members projection reader.

**Property 5: Tenant isolation stays structural**
**Validates: Requirements 2.1, 7.4**

This is the focused, thorough tenant-isolation / one-Query-per-partition coverage for
:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`. Task 8.1's
``test_members_projection_reader.py`` already carries the per-method round-trip tests plus a
first cut of the caching (``test_partition_queried_once_across_all_three_reads``) and a
two-tenant no-bleed check (``test_scope_and_grants_are_partition_scoped_across_tenants``).
This file does NOT duplicate those; it strengthens the *structural* isolation guarantee that
Property 5 makes:

- every read issues exactly ONE DynamoDB ``Query`` per distinct tenant partition, coalescing
  ``get_scope_config`` + ``get_overlay`` + ``get_scope_grants`` on one reader instance
  (per-invocation cache), and a second distinct tenant adds exactly one more Query — never
  more than one Query per distinct partition;
- every ``Query`` is keyed on a partition-key **equality** (``PARTITION_KEY_ATTR .eq``) for
  the caller's own ``tenant_id`` — a cross-tenant read is structurally unaddressable because
  no Query is ever issued without that equality on the caller's tenant;
- no cross-tenant bleed across ALL THREE reader methods (config#scope / config#fields /
  scopegrant), including the email filter: tenant B's user queried under tenant A returns
  ``{}`` (partition scoping AND the email filter both hold), with a fresh reader per tenant
  and the same reader across tenants.

These are EXAMPLE tests (Property 5 is structural — a query-recording ``RecordingFakeTable``
+ explicit assertions), matching how ``test_members_repository.py`` asserts Property 1
isolation with examples. DynamoDB is faked in-memory; no live AWS, no MySQL.
"""

import os
import sys

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.projection_schema` resolves (mirrors
# test_members_projection_reader.py — the projection schema is the single source of truth for
# the key shape, shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.repository.projection_config_reader import MembersProjectionReader


# ---------------------------------------------------------------------------
# Recording in-memory fake DynamoDB table (read side)
# ---------------------------------------------------------------------------


class RecordingFakeTable:
    """In-memory boto3 DynamoDB Table stand-in that RECORDS every ``query`` call.

    Extends the ``FakeTable`` contract from ``test_members_projection_reader.py`` (store keyed
    by ``(tenant_id, sk)``; ``query`` returns ONLY the partition whose key matches the boto3
    ``Key(...).eq(...)`` condition, so cross-tenant items are never returned) and additionally
    records, for every ``query`` call, the ``(attr, op, value)`` the KeyConditionExpression
    targeted. That lets Property-5 tests assert BOTH the query *count* per partition and that
    every Query is a partition-key EQUALITY on the caller's own ``tenant_id``.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        # Ordered log of every query: (attr_name, operator, tenant_value).
        self.query_log: list[tuple[str, str, str]] = []

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        attr, op, tenant_id = _condition_parts(KeyConditionExpression)
        self.query_log.append((attr, op, tenant_id))
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}

    # -- convenience accessors for assertions --------------------------------

    def query_count_for(self, tenant_id: str) -> int:
        return sum(1 for _, _, t in self.query_log if t == tenant_id)

    @property
    def total_queries(self) -> int:
        return len(self.query_log)

    @property
    def queried_tenants(self) -> list[str]:
        return [t for _, _, t in self.query_log]


def _condition_parts(condition):
    """Return ``(attr_name, operator, value)`` from a boto3 ``Key(attr).eq(value)`` condition.

    boto3's ``Key(a).eq(v).get_expression()`` yields
    ``{"operator": "=", "values": (Key(a), v)}`` — the first value is the attr, the second the
    bound value. We surface the attr NAME (``.name``) so tests assert the equality targets
    ``schema.PARTITION_KEY_ATTR`` specifically.
    """
    expr = condition.get_expression()
    operator = expr["operator"]
    attr_operand, value = expr["values"]
    attr_name = getattr(attr_operand, "name", attr_operand)
    return attr_name, operator, value


# ---------------------------------------------------------------------------
# Seed helpers (canonical schema builders — keys match production)
# ---------------------------------------------------------------------------


def _config_scope_item(tenant_id, dimensions, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"),
        "dimensions": dimensions,
        schema.VERSION_ATTR: version,
    }


def _config_fields_item(tenant_id, fields, overrides, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
        "fields": fields,
        "overrides": overrides,
        schema.VERSION_ATTR: version,
    }


def _scopegrant_item(tenant_id, email, dimension, values, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_SCOPEGRANT, email, dimension
        ),
        "dimension": dimension,
        "values": values,
        schema.VERSION_ATTR: version,
    }


def _dimension(key, values, **overrides):
    base = {
        "key": key,
        "field": key,
        "label": {"en": key.title()},
        "enabled": True,
        "values": list(values),
        "all_wildcard": None,
        "required_for": ["Members_CRUD"],
    }
    base.update(overrides)
    return base


def _fields_variable(key, label):
    return {
        key: {
            "key": key,
            "type": "string",
            "required": False,
            "label": label,
            "choices": None,
            "visible": True,
            "order": 1,
        }
    }


def _seed_two_distinct_tenants(table):
    """Seed tenant A and tenant B with DISTINCT config#scope / config#fields / scopegrant rows.

    Tenant A: a ``region`` dimension (Noord/Zuid) + a variable field ``a_field`` + a Noord
    grant for alice. Tenant B: a DIFFERENT ``chapter`` dimension (X/Y) + a variable field
    ``b_field`` + a grant for bob. No value overlaps between the two partitions, so any bleed
    is unambiguous.
    """
    # Tenant A.
    table.put(_config_scope_item("tenant-a", [_dimension("region", ["Noord", "Zuid"])]))
    table.put(
        _config_fields_item(
            "tenant-a", _fields_variable("a_field", {"en": "A field"}), overrides={}
        )
    )
    table.put(_scopegrant_item("tenant-a", "alice@example.com", "region", ["Noord"]))
    # Tenant B — a different dimension key, different values, a different user.
    table.put(_config_scope_item("tenant-b", [_dimension("chapter", ["X", "Y"])]))
    table.put(
        _config_fields_item(
            "tenant-b", _fields_variable("b_field", {"en": "B field"}), overrides={}
        )
    )
    table.put(_scopegrant_item("tenant-b", "bob@example.com", "chapter", ["X"]))


# ---------------------------------------------------------------------------
# Point 1+2 — exactly ONE Query per distinct partition, keyed on tenant_id
# ---------------------------------------------------------------------------


class TestOneQueryPerPartition:
    def test_three_reads_same_tenant_issue_exactly_one_partition_query(self):
        """config + overlay + grants on ONE reader coalesce to a single Query for the tenant.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()
        table.put(_config_scope_item("tenant-a", [_dimension("region", ["Noord"])]))
        table.put(
            _config_fields_item(
                "tenant-a", _fields_variable("a_field", {"en": "A field"}), overrides={}
            )
        )
        table.put(_scopegrant_item("tenant-a", "alice@example.com", "region", ["Noord"]))

        reader = MembersProjectionReader(table=table)
        reader.get_scope_config("tenant-a")
        reader.get_overlay("tenant-a")
        reader.get_scope_grants("tenant-a", "alice@example.com")

        assert table.query_count_for("tenant-a") == 1
        assert table.total_queries == 1

    def test_second_distinct_tenant_adds_exactly_one_more_query(self):
        """A second tenant on the SAME reader adds exactly one more Query — one per partition.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()
        _seed_two_distinct_tenants(table)

        reader = MembersProjectionReader(table=table)
        # All three reads for A -> 1 Query.
        reader.get_scope_config("tenant-a")
        reader.get_overlay("tenant-a")
        reader.get_scope_grants("tenant-a", "alice@example.com")
        assert table.total_queries == 1

        # All three reads for B -> exactly one MORE Query (distinct partition).
        reader.get_scope_config("tenant-b")
        reader.get_overlay("tenant-b")
        reader.get_scope_grants("tenant-b", "bob@example.com")

        assert table.total_queries == 2
        assert table.query_count_for("tenant-a") == 1
        assert table.query_count_for("tenant-b") == 1

    def test_every_query_is_partition_key_equality_on_caller_tenant(self):
        """No Query is ever issued without a partition-key equality on the caller's tenant.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()
        _seed_two_distinct_tenants(table)

        reader = MembersProjectionReader(table=table)
        reader.get_scope_config("tenant-a")
        reader.get_overlay("tenant-a")
        reader.get_scope_grants("tenant-a", "alice@example.com")
        reader.get_scope_config("tenant-b")

        # Every recorded query targets the PARTITION KEY with an equality on the tenant asked.
        for attr, operator, tenant_value in table.query_log:
            assert attr == schema.PARTITION_KEY_ATTR
            assert operator == "="
            assert tenant_value in {"tenant-a", "tenant-b"}
        # And the tenants queried are exactly the callers' own tenants (no third partition).
        assert table.queried_tenants == ["tenant-a", "tenant-b"]

    def test_empty_partition_returns_defaults_without_a_second_query(self):
        """An absent partition yields empty-is-valid defaults from a single cached Query.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()  # nothing seeded for this tenant
        reader = MembersProjectionReader(table=table)

        config = reader.get_scope_config("ghost")
        overlay = reader.get_overlay("ghost")
        grants = reader.get_scope_grants("ghost", "nobody@example.com")

        assert config.dimensions == ()
        assert dict(overlay.fields) == {}
        assert dict(overlay.overrides) == {}
        assert grants == {}
        # The empty partition is Queried at most once — the cache prevents a re-Query.
        assert table.query_count_for("ghost") == 1
        assert table.total_queries == 1


# ---------------------------------------------------------------------------
# Point 3 — no cross-tenant bleed across ALL THREE reader methods
# ---------------------------------------------------------------------------


class TestNoCrossTenantBleed:
    def test_same_reader_isolates_config_overlay_and_grants_per_tenant(self):
        """One reader reading both tenants returns ONLY each tenant's own rows.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()
        _seed_two_distinct_tenants(table)
        reader = MembersProjectionReader(table=table)

        # Tenant A sees only A's config/overlay/grant.
        a_config = reader.get_scope_config("tenant-a")
        a_overlay = reader.get_overlay("tenant-a")
        a_grants = reader.get_scope_grants("tenant-a", "alice@example.com")
        assert [d.key for d in a_config.dimensions] == ["region"]
        assert tuple(a_config.dimensions[0].values) == ("Noord", "Zuid")
        assert set(a_overlay.fields) == {"a_field"}
        assert a_grants == {"region": ["Noord"]}

        # Tenant B sees only B's config/overlay/grant — none of A's.
        b_config = reader.get_scope_config("tenant-b")
        b_overlay = reader.get_overlay("tenant-b")
        b_grants = reader.get_scope_grants("tenant-b", "bob@example.com")
        assert [d.key for d in b_config.dimensions] == ["chapter"]
        assert tuple(b_config.dimensions[0].values) == ("X", "Y")
        assert set(b_overlay.fields) == {"b_field"}
        assert b_grants == {"chapter": ["X"]}

    def test_fresh_reader_per_tenant_isolates_all_three_methods(self):
        """A fresh reader per tenant reads ONLY that tenant's partition — never the other's.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()
        _seed_two_distinct_tenants(table)

        reader_a = MembersProjectionReader(table=table)
        a_config = reader_a.get_scope_config("tenant-a")
        a_overlay = reader_a.get_overlay("tenant-a")
        a_grants = reader_a.get_scope_grants("tenant-a", "alice@example.com")

        reader_b = MembersProjectionReader(table=table)
        b_config = reader_b.get_scope_config("tenant-b")
        b_overlay = reader_b.get_overlay("tenant-b")
        b_grants = reader_b.get_scope_grants("tenant-b", "bob@example.com")

        # A's reader never saw B's chapter dimension / b_field / chapter grant, and vice-versa.
        assert [d.key for d in a_config.dimensions] == ["region"]
        assert set(a_overlay.fields) == {"a_field"}
        assert a_grants == {"region": ["Noord"]}
        assert [d.key for d in b_config.dimensions] == ["chapter"]
        assert set(b_overlay.fields) == {"b_field"}
        assert b_grants == {"chapter": ["X"]}
        # Each fresh reader queried only its own tenant's partition, once.
        assert table.query_count_for("tenant-a") == 1
        assert table.query_count_for("tenant-b") == 1

    def test_other_tenants_user_queried_under_this_tenant_returns_empty(self):
        """B's user queried under A returns ``{}`` — partition scoping AND the email filter hold.

        Property 5 / Validates: Requirements 2.1, 7.4
        """
        table = RecordingFakeTable()
        _seed_two_distinct_tenants(table)
        reader = MembersProjectionReader(table=table)

        # bob belongs to tenant-b; asking for bob's grants under tenant-a yields nothing:
        # his scopegrant row lives in B's partition (unaddressable from A) AND the email
        # filter would exclude it anyway.
        assert reader.get_scope_grants("tenant-a", "bob@example.com") == {}
        # Symmetrically, alice (tenant-a) has no grant in tenant-b's partition.
        assert reader.get_scope_grants("tenant-b", "alice@example.com") == {}
        # A only ever queried its own partition (and B its own).
        assert table.query_count_for("tenant-a") == 1
        assert table.query_count_for("tenant-b") == 1
