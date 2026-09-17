"""
S4 D2 (amended, Option A) — unit tests for the projection-backed governance reader.

Covers :class:`sam.pretokengen.projection_governance_reader.ProjectionGovernanceReader`
— the read-only seam that reads the S3 DynamoDB projection (NOT MySQL) for a
user's per-tenant roles + active modules (design.md "Design amendment A"):

- roles are filtered to the CALLING user's email (``role#<email>#<role>`` items);
- active modules are the ``module#<name>`` items whose ``is_active`` is truthy;
- an empty / missing partition returns ``[]`` (empty is valid, never a raise);
- multi-tenant: each tenant's own partition answers only for that tenant (R5.4);
- per-invocation cache: a tenant's partition is Queried at most ONCE per issuance.

DynamoDB is faked with an in-memory ``FakeTable`` (mirrors
``sam/tests/test_entitlement_reader.py`` fakes + ``backend/tests/unit/
test_projection_reader.py``): its ``query(KeyConditionExpression=...)`` returns
ONLY the seeded items whose partition key matches the boto3 ``Key(...).eq(...)``
condition, so cross-tenant items are never returned — the same tenant-scoping a
real table + IAM ``LeadingKeys`` enforces. No live AWS, no MySQL.
"""

import os
import sys

import pytest

# repo root on sys.path (mirrors sam/conftest.py) so `sam.pretokengen` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.pretokengen.projection_governance_reader import ProjectionGovernanceReader


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (read side)
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side only).

    Stores items keyed by (tenant_id, sk). ``query(KeyConditionExpression=...)``
    extracts the requested tenant from the boto3 ``Key(...).eq(...)`` condition
    and returns ONLY that partition's items (cross-tenant items are never
    returned). Counts queries per tenant so tests can assert the reader's
    per-invocation cache reads each partition at most once.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.query_counts: dict[str, int] = {}

    def put(self, item: dict) -> None:
        """Test helper — seed an item (NOT part of the reader's surface)."""
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


def _role_item(tenant_id, email, role, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_ROLE, email, role
        ),
        "role": role,
        schema.VERSION_ATTR: version,
    }


def _module_item(tenant_id, module_name, is_active=True, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_MODULE, module_name
        ),
        "is_active": is_active,
        schema.VERSION_ATTR: version,
    }


def _tenant_item(tenant_id, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_TENANT),
        schema.VERSION_ATTR: version,
    }


# ---------------------------------------------------------------------------
# get_user_roles_by_tenant — filtered to the calling user's email
# ---------------------------------------------------------------------------


class TestGetUserRolesByTenant:
    def test_roles_filtered_to_the_calling_email(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "user@example.com", "Finance_CRUD"))
        table.put(_role_item("TenantA", "user@example.com", "STR_Read"))
        # A different user's role in the SAME partition must be excluded.
        table.put(_role_item("TenantA", "other@example.com", "Admin"))

        reader = ProjectionGovernanceReader(table=table)
        result = reader.get_user_roles_by_tenant("user@example.com", ["TenantA"])

        assert set(result.keys()) == {"TenantA"}
        assert sorted(result["TenantA"]) == ["Finance_CRUD", "STR_Read"]

    def test_module_items_are_not_treated_as_roles(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "user@example.com", "Finance_CRUD"))
        table.put(_module_item("TenantA", "FIN", is_active=True))
        table.put(_tenant_item("TenantA"))

        reader = ProjectionGovernanceReader(table=table)
        result = reader.get_user_roles_by_tenant("user@example.com", ["TenantA"])

        assert result == {"TenantA": ["Finance_CRUD"]}

    def test_tenant_with_no_matching_roles_maps_to_empty_list(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "other@example.com", "Admin"))

        reader = ProjectionGovernanceReader(table=table)
        result = reader.get_user_roles_by_tenant("user@example.com", ["TenantA"])

        # Present but no roles for THIS user — empty is valid, not an error.
        assert result == {"TenantA": []}

    def test_missing_partition_returns_empty_list_never_raises(self):
        table = FakeTable()  # nothing seeded for TenantZ
        reader = ProjectionGovernanceReader(table=table)
        result = reader.get_user_roles_by_tenant("user@example.com", ["TenantZ"])
        assert result == {"TenantZ": []}

    def test_empty_tenant_list_returns_empty_map(self):
        reader = ProjectionGovernanceReader(table=FakeTable())
        assert reader.get_user_roles_by_tenant("user@example.com", []) == {}


# ---------------------------------------------------------------------------
# get_active_modules_by_tenant — only is_active modules
# ---------------------------------------------------------------------------


class TestGetActiveModulesByTenant:
    def test_only_active_modules_are_returned(self):
        table = FakeTable()
        table.put(_module_item("TenantA", "FIN", is_active=True))
        table.put(_module_item("TenantA", "STR", is_active=False))
        table.put(_module_item("TenantA", "WEB", is_active=True))

        reader = ProjectionGovernanceReader(table=table)
        result = reader.get_active_modules_by_tenant(["TenantA"])

        assert set(result.keys()) == {"TenantA"}
        assert sorted(result["TenantA"]) == ["FIN", "WEB"]

    def test_role_items_are_not_treated_as_modules(self):
        table = FakeTable()
        table.put(_module_item("TenantA", "FIN", is_active=True))
        table.put(_role_item("TenantA", "user@example.com", "Finance_CRUD"))

        reader = ProjectionGovernanceReader(table=table)
        result = reader.get_active_modules_by_tenant(["TenantA"])

        assert result == {"TenantA": ["FIN"]}

    def test_tenant_with_no_active_modules_maps_to_empty_list(self):
        table = FakeTable()
        table.put(_module_item("TenantA", "FIN", is_active=False))

        reader = ProjectionGovernanceReader(table=table)
        assert reader.get_active_modules_by_tenant(["TenantA"]) == {"TenantA": []}

    def test_missing_partition_returns_empty_list(self):
        reader = ProjectionGovernanceReader(table=FakeTable())
        assert reader.get_active_modules_by_tenant(["TenantZ"]) == {"TenantZ": []}


# ---------------------------------------------------------------------------
# Multi-tenant isolation (R5.4) — each partition answers only for its tenant
# ---------------------------------------------------------------------------


def test_multi_tenant_roles_and_modules_are_partition_scoped():
    table = FakeTable()
    # TenantA: user has a role + FIN active.
    table.put(_role_item("TenantA", "user@example.com", "Finance_CRUD"))
    table.put(_module_item("TenantA", "FIN", is_active=True))
    # TenantB: user has a different role + STR active.
    table.put(_role_item("TenantB", "user@example.com", "STR_CRUD"))
    table.put(_module_item("TenantB", "STR", is_active=True))

    reader = ProjectionGovernanceReader(table=table)

    roles = reader.get_user_roles_by_tenant("user@example.com", ["TenantA", "TenantB"])
    modules = reader.get_active_modules_by_tenant(["TenantA", "TenantB"])

    assert roles == {"TenantA": ["Finance_CRUD"], "TenantB": ["STR_CRUD"]}
    assert modules == {"TenantA": ["FIN"], "TenantB": ["STR"]}


# ---------------------------------------------------------------------------
# Per-invocation cache — a tenant's partition is Queried at most once
# ---------------------------------------------------------------------------


def test_partition_queried_once_across_both_reads():
    """Roles + modules for the same tenant share ONE Query (per-invocation cache)."""
    table = FakeTable()
    table.put(_role_item("TenantA", "user@example.com", "Finance_CRUD"))
    table.put(_module_item("TenantA", "FIN", is_active=True))

    reader = ProjectionGovernanceReader(table=table)

    reader.get_user_roles_by_tenant("user@example.com", ["TenantA"])
    reader.get_active_modules_by_tenant(["TenantA"])

    # Both method calls hit TenantA's partition, but the cache means exactly one
    # underlying Query was issued for it.
    assert table.query_counts["TenantA"] == 1


def test_repeated_reads_do_not_requery():
    table = FakeTable()
    table.put(_module_item("TenantA", "FIN", is_active=True))
    reader = ProjectionGovernanceReader(table=table)

    reader.get_active_modules_by_tenant(["TenantA"])
    reader.get_active_modules_by_tenant(["TenantA"])
    reader.get_active_modules_by_tenant(["TenantA"])

    assert table.query_counts["TenantA"] == 1
