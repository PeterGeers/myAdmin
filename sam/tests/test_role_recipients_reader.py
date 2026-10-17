"""
Member Application Form seam (d) — unit tests for the **role-recipients reader**.

Covers :class:`sam.members.repository.role_recipients_reader.RoleRecipientsReader`
— the read-only seam that resolves a new application's STAFF recipients from the shared
governance projection (R8.2–R8.5, R9a; D9/D9a), scope-generically:

- **all-scope filter (R8.3):** only ``Members_CRUD`` users with a ``["*"]`` grant on the
  governing scope dimension are the base recipients; a scope-LIMITED ``Members_CRUD`` user is
  excluded;
- **scope-matched copy (R8.3a/D9a):** WHEN the applicant's selected scope value is supplied,
  the ``Members_CRUD`` users scoped to that value are ALSO included, ADDING to (not replacing)
  the all-scope set, and never duplicating an all-scope user;
- **``TenantAdmin`` fallback (R8.4):** when no all-scope ``Members_CRUD`` exists, fall back to
  the ``role#<email>#TenantAdmin`` holders;
- **empty → ``NO_NOTIFY`` (R8.5):** no all-scope ``Members_CRUD`` and no ``TenantAdmin`` →
  ``is_empty`` is ``True``;
- **no-scope-dimension tenant (R8.3):** a tenant whose ``config#scope`` enables no dimension
  treats ALL its ``Members_CRUD`` as all-scope;
- **tenancy (R8.1/Property 1):** each tenant's partition answers only for that tenant.

DynamoDB is faked with the SAME in-memory ``FakeTable`` discipline as
``test_projection_governance_reader.py`` — ``query`` returns ONLY the seeded items whose
partition key matches the boto3 ``Key(...).eq(...)`` condition, so cross-tenant items are
never returned. The governing scope dimension is injected via a ``StaticScopeConfigProvider``
(the storage-agnostic reference provider) so the reader stays scope-generic. No live AWS, no
MySQL.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema

from sam.members.domain.scope_dimensions import (
    ScopeDimension,
    StaticScopeConfigProvider,
)
from sam.members.repository.role_recipients_reader import (
    MEMBERS_CRUD_ROLE,
    TENANT_ADMIN_ROLE,
    RoleRecipientsReader,
)

# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (read side) — mirrors test_projection_governance_reader
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side only).

    ``query(KeyConditionExpression=...)`` returns ONLY the seeded items whose partition key
    matches the boto3 ``Key(...).eq(...)`` condition, so cross-tenant items are never returned
    — the same tenant-scoping a real table + IAM ``LeadingKeys`` enforces. Counts queries per
    tenant so a test can assert the per-invocation cache reads each partition at most once.
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
    expr = condition.get_expression()
    return expr["values"][1]


# ---------------------------------------------------------------------------
# Seed helpers (canonical schema builders so keys match production)
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


def _grant_item(tenant_id, email, dimension, values, version=1):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_SCOPEGRANT, email, dimension
        ),
        "dimension": dimension,
        "values": list(values),
        schema.VERSION_ATTR: version,
    }


#: A single enabled "region" governing dimension (abstract synthetic values, D17).
_REGION_DIM = ScopeDimension(
    key="region",
    label={"en": "Region"},
    enabled=True,
    values=("North", "South", "East", "West"),
    required_for=(MEMBERS_CRUD_ROLE,),
)


def _reader(table, *, dimensions=(_REGION_DIM,), tenant="TenantA"):
    """Build a reader whose scope config for ``tenant`` has ``dimensions`` (scope-generic)."""
    provider = StaticScopeConfigProvider({tenant: dimensions})
    return RoleRecipientsReader(scope_config_provider=provider, table=table)


# ---------------------------------------------------------------------------
# R8.3 — all-scope filter: only ["*"] Members_CRUD; scope-limited excluded
# ---------------------------------------------------------------------------


class TestAllScopeFilter:
    def test_all_scope_members_crud_included_scope_limited_excluded(self):
        table = FakeTable()
        # all-scope reviewer — region grant ["*"]
        table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))
        # scope-limited reviewer — region grant ["North"] (administers one region only)
        table.put(_role_item("TenantA", "north@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "north@ex.com", "region", ["North"]))
        # a Members_CRUD with NO grant at all → deny-by-default, not all-scope
        table.put(_role_item("TenantA", "nogrant@ex.com", MEMBERS_CRUD_ROLE))

        result = _reader(table).resolve_recipients("TenantA")

        assert result.all_scope == ("all@ex.com",)
        assert result.recipients == ("all@ex.com",)
        assert not result.fallback_used
        assert not result.is_empty

    def test_non_members_crud_role_never_a_recipient(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))
        # A different role with an all-scope grant must NOT be pulled into the set.
        table.put(_role_item("TenantA", "finance@ex.com", "Finance_CRUD"))
        table.put(_grant_item("TenantA", "finance@ex.com", "region", ["*"]))

        result = _reader(table).resolve_recipients("TenantA")

        assert result.all_scope == ("all@ex.com",)


# ---------------------------------------------------------------------------
# R8.3a / D9a — scope-matched copy for the applicant's selected value
# ---------------------------------------------------------------------------


class TestScopeMatchedCopy:
    def test_scope_matched_copy_added_for_applicant_value(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))
        table.put(_role_item("TenantA", "north@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "north@ex.com", "region", ["North"]))
        table.put(_role_item("TenantA", "south@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "south@ex.com", "region", ["South"]))

        result = _reader(table).resolve_recipients(
            "TenantA", applicant_scope_value="North"
        )

        # base all-scope unchanged; the North scope-local reviewer is added as a copy.
        assert result.all_scope == ("all@ex.com",)
        assert result.scope_matched == ("north@ex.com",)
        # South reviewer is NOT in scope for a North applicant.
        assert "south@ex.com" not in result.recipients
        assert set(result.recipients) == {"all@ex.com", "north@ex.com"}

    def test_scope_copy_does_not_duplicate_an_all_scope_user(self):
        table = FakeTable()
        # An all-scope user also "covers" North — but must appear once, in all_scope only.
        table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))

        result = _reader(table).resolve_recipients(
            "TenantA", applicant_scope_value="North"
        )

        assert result.all_scope == ("all@ex.com",)
        assert result.scope_matched == ()
        assert result.recipients == ("all@ex.com",)

    def test_no_applicant_value_keeps_base_behaviour(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))
        table.put(_role_item("TenantA", "north@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "north@ex.com", "region", ["North"]))

        result = _reader(table).resolve_recipients("TenantA")  # no scope value

        assert result.scope_matched == ()
        assert result.recipients == ("all@ex.com",)


# ---------------------------------------------------------------------------
# R8.4 — TenantAdmin fallback when no all-scope Members_CRUD
# ---------------------------------------------------------------------------


class TestTenantAdminFallback:
    def test_fallback_to_tenant_admin_when_no_all_scope_crud(self):
        table = FakeTable()
        # Only a scope-limited Members_CRUD (not all-scope) + a TenantAdmin.
        table.put(_role_item("TenantA", "north@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "north@ex.com", "region", ["North"]))
        table.put(_role_item("TenantA", "admin@ex.com", TENANT_ADMIN_ROLE))

        result = _reader(table).resolve_recipients("TenantA")

        assert result.all_scope == ()
        assert result.tenant_admin == ("admin@ex.com",)
        assert result.fallback_used is True
        assert result.recipients == ("admin@ex.com",)
        assert result.reply_to == ("admin@ex.com",)
        assert not result.is_empty

    def test_tenant_admin_not_used_when_all_scope_crud_exists(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))
        table.put(_role_item("TenantA", "admin@ex.com", TENANT_ADMIN_ROLE))

        result = _reader(table).resolve_recipients("TenantA")

        assert result.recipients == ("all@ex.com",)
        assert result.tenant_admin == ()
        assert result.fallback_used is False


# ---------------------------------------------------------------------------
# R8.5 — empty → NO_NOTIFY signal
# ---------------------------------------------------------------------------


class TestNoNotifySignal:
    def test_no_crud_no_tenant_admin_is_empty(self):
        table = FakeTable()
        # A scope-limited Members_CRUD only — not all-scope, and no TenantAdmin.
        table.put(_role_item("TenantA", "north@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_grant_item("TenantA", "north@ex.com", "region", ["North"]))

        result = _reader(table).resolve_recipients("TenantA")

        assert result.recipients == ()
        assert result.reply_to == ()
        assert result.is_empty is True

    def test_missing_partition_is_empty_never_raises(self):
        table = FakeTable()  # nothing seeded
        result = _reader(table).resolve_recipients("TenantZ")
        assert result.is_empty is True

    def test_blank_tenant_is_empty(self):
        result = _reader(FakeTable()).resolve_recipients("")
        assert result.is_empty is True


# ---------------------------------------------------------------------------
# R8.3 — no scope dimension configured → all Members_CRUD are all-scope
# ---------------------------------------------------------------------------


class TestNoScopeDimensionTenant:
    def test_all_members_crud_are_all_scope_when_no_dimension(self):
        table = FakeTable()
        # No scopegrant rows at all; a tenant-wide (no enabled dimension) config.
        table.put(_role_item("TenantA", "a@ex.com", MEMBERS_CRUD_ROLE))
        table.put(_role_item("TenantA", "b@ex.com", MEMBERS_CRUD_ROLE))

        reader = _reader(table, dimensions=())
        result = reader.resolve_recipients("TenantA")

        assert set(result.all_scope) == {"a@ex.com", "b@ex.com"}
        assert set(result.recipients) == {"a@ex.com", "b@ex.com"}
        assert not result.is_empty

    def test_disabled_dimension_collapses_to_tenant_wide(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "a@ex.com", MEMBERS_CRUD_ROLE))
        # An explicit region grant exists but the dimension is DISABLED → ignored.
        table.put(_grant_item("TenantA", "a@ex.com", "region", ["North"]))

        disabled = ScopeDimension(key="region", enabled=False)
        result = _reader(table, dimensions=(disabled,)).resolve_recipients("TenantA")

        # Disabled dimension is a no-op: the scope-limited grant does not exclude the user.
        assert result.all_scope == ("a@ex.com",)

    def test_scope_copy_noop_when_no_dimension(self):
        table = FakeTable()
        table.put(_role_item("TenantA", "a@ex.com", MEMBERS_CRUD_ROLE))

        result = _reader(table, dimensions=()).resolve_recipients(
            "TenantA", applicant_scope_value="North"
        )

        # Everyone is already all-scope; there is nothing to match → no extra copy.
        assert result.scope_matched == ()
        assert result.recipients == ("a@ex.com",)


# ---------------------------------------------------------------------------
# Tenancy (R8.1 / Property 1) + per-invocation cache
# ---------------------------------------------------------------------------


def test_recipients_are_partition_scoped():
    table = FakeTable()
    table.put(_role_item("TenantA", "a@ex.com", MEMBERS_CRUD_ROLE))
    table.put(_grant_item("TenantA", "a@ex.com", "region", ["*"]))
    # A different tenant's all-scope reviewer must never leak into TenantA.
    table.put(_role_item("TenantB", "b@ex.com", MEMBERS_CRUD_ROLE))
    table.put(_grant_item("TenantB", "b@ex.com", "region", ["*"]))

    provider = StaticScopeConfigProvider(
        {"TenantA": (_REGION_DIM,), "TenantB": (_REGION_DIM,)}
    )
    reader = RoleRecipientsReader(scope_config_provider=provider, table=table)

    assert reader.resolve_recipients("TenantA").recipients == ("a@ex.com",)


def test_partition_queried_once_per_invocation():
    table = FakeTable()
    table.put(_role_item("TenantA", "all@ex.com", MEMBERS_CRUD_ROLE))
    table.put(_grant_item("TenantA", "all@ex.com", "region", ["*"]))
    table.put(_role_item("TenantA", "north@ex.com", MEMBERS_CRUD_ROLE))
    table.put(_grant_item("TenantA", "north@ex.com", "region", ["North"]))

    reader = _reader(table)
    # Resolve with a scope value so the role scan + both grant scans all run.
    reader.resolve_recipients("TenantA", applicant_scope_value="North")

    # Role + every grant lookup share ONE Query for the partition (cache).
    assert table.query_counts["TenantA"] == 1
