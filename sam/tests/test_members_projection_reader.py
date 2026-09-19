"""
S5b Task 8.1 — unit tests for the Members module projection config reader.

Covers :class:`sam.members.repository.projection_config_reader.MembersProjectionReader`
— the read-only seam that feeds the S5 domain from the governance projection (design C4):

- ``config#scope``  → :class:`ScopeConfig` round-trip (incl. multiple dimensions);
- a missing ``config#scope`` → tenant-wide empty ``ScopeConfig`` (R1.6);
- ``config#fields`` → :class:`TenantOverlay` (incl. ``FieldType`` conversion + overrides
  carrying only the aspects present) (R1.5);
- a missing ``config#fields`` → empty ``TenantOverlay`` (R1.7);
- ``scopegrant#<email>#<dimension>`` → ``{dimension: values}`` filtered to the caller's
  email, with ``["*"]`` all-access preserved and a missing grant absent from the map (R2.3);
- one ``Query`` per partition (per-invocation cache) + tenant isolation (only the queried
  partition answers, R7.4).

DynamoDB is faked with an in-memory ``FakeTable`` (mirrors
``sam/tests/test_projection_governance_reader.py``): its
``query(KeyConditionExpression=...)`` returns ONLY the seeded items whose partition key
matches the boto3 ``Key(...).eq(...)`` condition, so cross-tenant items are never returned.
No live AWS, no MySQL.
"""

import os
import sys

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.projection_schema` resolves (mirrors
# test_projection_governance_reader.py — the projection schema is the single source of truth
# for the key shape, shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.field_resolver import TenantOverlay
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.scope_dimensions import ScopeConfig
from sam.members.repository.projection_config_reader import MembersProjectionReader


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (read side)
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side only).

    Stores items keyed by (tenant_id, sk). ``query(KeyConditionExpression=...)`` extracts the
    requested tenant from the boto3 ``Key(...).eq(...)`` condition and returns ONLY that
    partition's items (cross-tenant items are never returned). Counts queries per tenant so
    tests can assert the reader's per-invocation cache reads each partition at most once.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.query_counts: dict[str, int] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        tenant_id = _tenant_from_condition(KeyConditionExpression)
        self.query_counts[tenant_id] = self.query_counts.get(tenant_id, 0) + 1
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


def _tenant_from_condition(condition):
    """Extract the partition-key value from a boto3 ``Key(...).eq(...)`` condition."""
    expr = condition.get_expression()
    return expr["values"][1]


# ---------------------------------------------------------------------------
# Seed helpers (use the canonical schema builders so keys match production)
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


def _region_dimension_dict(**overrides):
    base = {
        "key": "region",
        "label": {"nl": "Regio", "en": "Region"},
        "enabled": True,
        "multi_valued": False,
        "values": ["Noord", "Zuid", "Oost", "West"],
        "all_wildcard": "Regio_All",
        "required_for": ["Members_CRUD"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# get_scope_config — config#scope → ScopeConfig round-trip
# ---------------------------------------------------------------------------


class TestGetScopeConfig:
    def test_get_scope_config_single_dimension_round_trips_to_scope_config(self):
        table = FakeTable()
        table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))

        reader = MembersProjectionReader(table=table)
        config = reader.get_scope_config("h-dcn")

        assert isinstance(config, ScopeConfig)
        assert config.tenant_id == "h-dcn"
        assert len(config.dimensions) == 1
        dim = config.dimensions[0]
        assert dim.key == "region"
        assert dim.label == {"nl": "Regio", "en": "Region"}
        assert dim.enabled is True
        assert dim.multi_valued is False
        assert tuple(dim.values) == ("Noord", "Zuid", "Oost", "West")
        assert dim.all_wildcard == "Regio_All"
        assert tuple(dim.required_for) == ("Members_CRUD",)

    def test_get_scope_config_multiple_dimensions_round_trips_all(self):
        table = FakeTable()
        season = {
            "key": "season",
            "label": {"en": "Season"},
            "enabled": True,
            "multi_valued": True,
            "values": ["2023", "2024"],
            "all_wildcard": None,
            "required_for": [],
        }
        table.put(_config_scope_item("multi", [_region_dimension_dict(), season]))

        reader = MembersProjectionReader(table=table)
        config = reader.get_scope_config("multi")

        assert [d.key for d in config.dimensions] == ["region", "season"]
        season_dim = config.dimension("season")
        assert season_dim is not None
        assert season_dim.multi_valued is True
        assert tuple(season_dim.values) == ("2023", "2024")
        assert season_dim.all_wildcard is None

    def test_get_scope_config_missing_row_collapses_to_tenant_wide_empty(self):
        table = FakeTable()  # nothing seeded for this tenant
        reader = MembersProjectionReader(table=table)

        config = reader.get_scope_config("unconfigured")

        assert isinstance(config, ScopeConfig)
        assert config.tenant_id == "unconfigured"
        assert config.dimensions == ()
        assert config.is_tenant_wide() is True

    def test_get_scope_config_disabled_dimension_preserved_as_data(self):
        table = FakeTable()
        table.put(
            _config_scope_item("h-dcn", [_region_dimension_dict(enabled=False, values=[])])
        )

        reader = MembersProjectionReader(table=table)
        config = reader.get_scope_config("h-dcn")

        # A disabled dimension is preserved (a no-op) — the tenant collapses to tenant-wide.
        assert len(config.dimensions) == 1
        assert config.dimensions[0].enabled is False
        assert config.is_tenant_wide() is True


# ---------------------------------------------------------------------------
# get_overlay — config#fields → TenantOverlay
# ---------------------------------------------------------------------------


class TestGetOverlay:
    def test_get_overlay_builds_variable_fields_with_field_type_conversion(self):
        table = FakeTable()
        fields = {
            "motor_type": {
                "key": "motor_type",
                "type": "enum",
                "required": True,
                "label": {"nl": "Motor", "en": "Motorcycle"},
                "choices": ["Sport", "Touring"],
                "visible": True,
                "order": 5,
            },
            "note": {
                "key": "note",
                "type": "string",
                "required": False,
                "label": {},
                "choices": None,
                "visible": True,
                "order": 6,
            },
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert isinstance(overlay, TenantOverlay)
        motor = overlay.fields["motor_type"]
        assert motor.type is FieldType.ENUM  # string "enum" -> FieldType.ENUM
        assert motor.required is True
        assert motor.label == {"nl": "Motor", "en": "Motorcycle"}
        assert tuple(motor.choices) == ("Sport", "Touring")
        assert motor.order == 5
        # choices=None stays None (not an empty tuple).
        assert overlay.fields["note"].choices is None
        assert overlay.fields["note"].type is FieldType.STRING

    def test_get_overlay_unknown_field_type_defaults_to_string(self):
        table = FakeTable()
        fields = {
            "weird": {"key": "weird", "type": "not-a-real-type"},
        }
        table.put(_config_fields_item("h-dcn", fields, overrides={}))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        assert overlay.fields["weird"].type is FieldType.STRING

    def test_get_overlay_override_carries_only_present_aspects(self):
        table = FakeTable()
        overrides = {
            # Only 'label' + 'order' present — 'visible'/'required' must stay None.
            "personal.name": {"label": {"nl": "Volledige naam"}, "order": 1},
            # Only 'visible' present.
            "personal.address": {"visible": False},
        }
        table.put(_config_fields_item("h-dcn", fields={}, overrides=overrides))

        reader = MembersProjectionReader(table=table)
        overlay = reader.get_overlay("h-dcn")

        name_ov = overlay.overrides["personal.name"]
        assert name_ov.label == {"nl": "Volledige naam"}
        assert name_ov.order == 1
        assert name_ov.visible is None  # absent -> leave base as-is
        assert name_ov.required is None

        addr_ov = overlay.overrides["personal.address"]
        assert addr_ov.visible is False
        assert addr_ov.label is None
        assert addr_ov.required is None
        assert addr_ov.order is None

    def test_get_overlay_missing_row_returns_empty_overlay(self):
        table = FakeTable()  # nothing seeded
        reader = MembersProjectionReader(table=table)

        overlay = reader.get_overlay("unconfigured")

        assert isinstance(overlay, TenantOverlay)
        assert dict(overlay.fields) == {}
        assert dict(overlay.overrides) == {}


# ---------------------------------------------------------------------------
# get_scope_grants — scopegrant#<email>#<dimension> filtered to the caller
# ---------------------------------------------------------------------------


class TestGetScopeGrants:
    def test_get_scope_grants_returns_dimension_values_for_the_caller(self):
        table = FakeTable()
        table.put(_scopegrant_item("h-dcn", "user@example.com", "region", ["Noord"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "user@example.com")

        assert grants == {"region": ["Noord"]}

    def test_get_scope_grants_all_access_wildcard_preserved(self):
        table = FakeTable()
        table.put(_scopegrant_item("h-dcn", "admin@example.com", "region", ["*"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "admin@example.com")

        assert grants == {"region": ["*"]}

    def test_get_scope_grants_filtered_to_calling_email(self):
        table = FakeTable()
        table.put(_scopegrant_item("h-dcn", "user@example.com", "region", ["Noord"]))
        # A different user's grant in the SAME partition must be excluded.
        table.put(_scopegrant_item("h-dcn", "other@example.com", "region", ["Zuid"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "user@example.com")

        assert grants == {"region": ["Noord"]}

    def test_get_scope_grants_multiple_dimensions_for_caller(self):
        table = FakeTable()
        table.put(_scopegrant_item("multi", "user@example.com", "region", ["Noord"]))
        table.put(_scopegrant_item("multi", "user@example.com", "season", ["2024"]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("multi", "user@example.com")

        assert grants == {"region": ["Noord"], "season": ["2024"]}

    def test_get_scope_grants_missing_grant_is_absent_from_the_map(self):
        table = FakeTable()  # no scopegrant rows for this caller
        table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))

        reader = MembersProjectionReader(table=table)
        grants = reader.get_scope_grants("h-dcn", "user@example.com")

        # Deny-by-default is the edge's job (via required_for) — the reader just omits it.
        assert grants == {}
        assert "region" not in grants

    def test_get_scope_grants_missing_partition_returns_empty_map(self):
        reader = MembersProjectionReader(table=FakeTable())
        assert reader.get_scope_grants("nope", "user@example.com") == {}


# ---------------------------------------------------------------------------
# Per-invocation cache — a tenant's partition is Queried at most once
# ---------------------------------------------------------------------------


def test_partition_queried_once_across_all_three_reads():
    """scope config + overlay + grants for the same tenant share ONE Query (cache)."""
    table = FakeTable()
    table.put(_config_scope_item("h-dcn", [_region_dimension_dict()]))
    table.put(_config_fields_item("h-dcn", fields={}, overrides={}))
    table.put(_scopegrant_item("h-dcn", "user@example.com", "region", ["Noord"]))

    reader = MembersProjectionReader(table=table)

    reader.get_scope_config("h-dcn")
    reader.get_overlay("h-dcn")
    reader.get_scope_grants("h-dcn", "user@example.com")

    # All three method calls hit h-dcn's partition, but the cache means exactly ONE
    # underlying Query was issued for it.
    assert table.query_counts["h-dcn"] == 1


# ---------------------------------------------------------------------------
# Tenant isolation (R7.4) — each partition answers only for its tenant
# ---------------------------------------------------------------------------


def test_scope_and_grants_are_partition_scoped_across_tenants():
    table = FakeTable()
    # Tenant A: region config + a Noord grant for the user.
    table.put(_config_scope_item("tenant-a", [_region_dimension_dict()]))
    table.put(_scopegrant_item("tenant-a", "user@example.com", "region", ["Noord"]))
    # Tenant B: a DIFFERENT config + a Zuid grant for the same user email.
    table.put(
        _config_scope_item("tenant-b", [_region_dimension_dict(values=["A", "B"])])
    )
    table.put(_scopegrant_item("tenant-b", "user@example.com", "region", ["Zuid"]))

    reader = MembersProjectionReader(table=table)

    a_config = reader.get_scope_config("tenant-a")
    a_grants = reader.get_scope_grants("tenant-a", "user@example.com")
    b_config = reader.get_scope_config("tenant-b")
    b_grants = reader.get_scope_grants("tenant-b", "user@example.com")

    # Each tenant's partition answers ONLY for that tenant — no cross-tenant bleed.
    assert tuple(a_config.dimensions[0].values) == ("Noord", "Zuid", "Oost", "West")
    assert a_grants == {"region": ["Noord"]}
    assert tuple(b_config.dimensions[0].values) == ("A", "B")
    assert b_grants == {"region": ["Zuid"]}
    # Exactly one Query per tenant partition.
    assert table.query_counts == {"tenant-a": 1, "tenant-b": 1}
