"""Property-based test for S3 projection tenant isolation (T20, R5.4).

Feature: s3-claims-and-projection
Property 3: Tenant isolation of the projection

Validates: Requirements R5.4

This exercises the tenant-scoped read side ``ProjectionReader`` (T19,
``services.projection_reader``) over a large generated space of **multi-tenant**
governance states (>= 2 tenants x modules x roles, including edge cases) and
asserts the design.md "Correctness Properties -> Property 3" invariant:

  For any multi-tenant source state, a projection read scoped to tenant ``T``
  returns only items whose partition key is ``T``; no item from another tenant
  is addressable from ``T``'s scope.

The DynamoDB seam is an in-memory ``FakeTable`` (no real AWS) reusing the
partition-key-scoping ``query`` pattern from ``test_projection_reader.py`` (which
scopes reads by partition key exactly like a real table + IAM ``LeadingKeys``):
its ``query`` returns only the requested partition and its ``get_item`` matches
on the full ``(tenant_id, sort_key)`` primary key, so the fake cannot leak
cross-tenant items. The table is populated *through the real projection
builder + sync* (T12/T16) from the generated state, so isolation is verified
against genuinely projected data rather than hand-placed items.

Edge cases baked into the generators: unicode tenant ids, overlapping sort keys
across tenants (the same module/role rows under different tenants), empty
tenants (no SAM-backed module -> nothing projected), and >= 2 tenants always.
A SAM-backed module is injected into ``MODULE_REGISTRY`` (autouse
``monkeypatch.setitem``, matching T17/T18) so the builder's projection gate can
fire.
"""

import os
import sys

import pytest
from hypothesis import given, settings, strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services import projection_schema as schema  # noqa: E402
from services.module_registry import MODULE_REGISTRY  # noqa: E402
from services.projection_reader import ProjectionReader  # noqa: E402
from services.projection_sync import ProjectionSync, TenantSource  # noqa: E402


# A test-local SAM-backed module so the builder's projection gate fires without
# touching the shipped registry (mirrors T17/T18's autouse monkeypatch.setitem).
_SAM_MODULE_NAME = "SAM_TEST_MODULE"
_FLASK_MODULE_NAME = "FLASK_TEST_MODULE"


@pytest.fixture(autouse=True)
def _test_modules(monkeypatch):
    """Inject a SAM-backed and a flask-backed test module into MODULE_REGISTRY.

    Autouse so the registry entries exist for the entire duration of each test
    function — including every Hypothesis example, which all run inside the
    function body while the fixture is active.
    """
    monkeypatch.setitem(
        MODULE_REGISTRY,
        _SAM_MODULE_NAME,
        {
            "description": "Temporary SAM-backed test module",
            "required_params": {},
            "required_tax_rates": [],
            "required_roles": ["SamTest_Read"],
            "backing": {
                "kind": "sam",
                "api_base_env": "SAM_TEST_MODULE_API_BASE",
                "data_namespace": "sam_test",
            },
        },
    )
    monkeypatch.setitem(
        MODULE_REGISTRY,
        _FLASK_MODULE_NAME,
        {
            "description": "Temporary flask-backed test module",
            "required_params": {},
            "required_tax_rates": [],
            "required_roles": ["FlaskTest_Read"],
            # No 'backing' block -> flask-backed (module_backing default).
        },
    )


# ---------------------------------------------------------------------------
# In-memory fake table (partition-key-scoping) — same pattern as
# test_projection_reader.py, extended with put_item so ProjectionSync can
# populate it. query() returns ONLY the requested partition; get_item() matches
# the full (tenant_id, sort_key) primary key — so cross-tenant items are never
# addressable, exactly like a real table + IAM LeadingKeys.
# ---------------------------------------------------------------------------


class FakeTable:
    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def _key_tuple(self, key_or_item):
        return (
            key_or_item[schema.PARTITION_KEY_ATTR],
            key_or_item[schema.SORT_KEY_ATTR],
        )

    # --- write side (used only by the sync to populate the fake) ------------

    def put_item(
        self,
        Item,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        # Honour the sync's conditional-version semantics so the fake is not more
        # permissive than a real table (a stale re-write is a no-op).
        if ConditionExpression is not None:
            existing = self.store.get(self._key_tuple(Item))
            incoming = (ExpressionAttributeValues or {}).get(":incoming")
            if existing is not None:
                stored_version = existing.get(schema.VERSION_ATTR)
                if stored_version is not None and not (stored_version < incoming):
                    raise _conditional_check_failed()
        self.store[self._key_tuple(Item)] = dict(Item)
        return {}

    # --- read side (used by ProjectionReader) -------------------------------

    def get_item(self, Key):
        item = self.store.get(self._key_tuple(Key))
        return {"Item": dict(item)} if item is not None else {}

    def query(self, KeyConditionExpression=None):
        # Scope to exactly one partition, mirroring a real Query + LeadingKeys.
        tenant_id = _tenant_from_condition(KeyConditionExpression)
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


def _conditional_check_failed():
    err = Exception("The conditional request failed")
    err.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    return err


def _tenant_from_condition(condition):
    """Extract the partition-key value from a boto3 Key(...).eq(...) condition."""
    expr = condition.get_expression()
    return expr["values"][1]


class _FakeSource:
    """An in-memory SourceProvider for ProjectionSync (no DB seam)."""

    def __init__(self, sources: dict[str, TenantSource]):
        self._sources = sources

    def list_administrations(self):
        return list(self._sources.keys())

    def get_tenant_source(self, administration):
        return self._sources.get(administration)


# ---------------------------------------------------------------------------
# Strategies — a MULTI-tenant governance state (>= 2 tenants), with distinct
# partition keys and the design's named edge cases: unicode tenant ids,
# overlapping sort keys across tenants (shared module names / role rows), and
# empty tenants (no SAM module -> nothing projected).
# ---------------------------------------------------------------------------

# Separator-free, non-empty text incl. unicode (avoids build_sort_key's "#" ban
# and the empty-segment guard). Surrogates/control chars excluded.
_seg_text = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() != "")

# Tenant ids include explicit unicode edge cases plus generated separator-free
# text, so partition keys exercise non-ASCII boundaries.
_tenant_id_st = st.one_of(
    st.sampled_from(["TenantA", "TenantB", "租户", "тенант", "Ω-tenant", "tenant-1"]),
    _seg_text,
)

_version = st.integers(min_value=0, max_value=1000)


def _module_row_st():
    return st.fixed_dictionaries(
        {
            # A SMALL name pool so the SAME module names recur across tenants,
            # producing OVERLAPPING sort keys between partitions (edge case).
            "module_name": st.sampled_from([_SAM_MODULE_NAME, _FLASK_MODULE_NAME]),
            "is_active": st.booleans(),
            "version": _version,
        }
    )


def _role_row_st():
    return st.fixed_dictionaries(
        {
            # Small pools so (email, role) sort keys overlap across tenants.
            "email": st.sampled_from(["a@ex", "b@ex", "üser@ex", "租户@ex"]),
            "role": st.sampled_from(["SamTest_Read", "SamTest_CRUD", "Tenant_Admin"]),
            "version": _version,
        }
    )


def _tenant_state_st():
    return st.fixed_dictionaries(
        {
            "administration": _tenant_id_st,
            "display_name": st.text(max_size=12),
            "version": _version,
            "modules": st.lists(_module_row_st(), min_size=0, max_size=4),
            "roles": st.lists(_role_row_st(), min_size=0, max_size=4),
        }
    )


@st.composite
def _multi_tenant_state_st(draw):
    """A MULTI-tenant state (>= 2 tenants) with unique administration keys."""
    tenants = draw(st.lists(_tenant_state_st(), min_size=2, max_size=5))
    # De-duplicate on administration so tenants are distinct partitions.
    seen: dict[str, dict] = {}
    for t in tenants:
        seen[t["administration"]] = t
    # Ensure the >= 2-tenant requirement survives de-duplication.
    if len(seen) < 2:
        extra = draw(_tenant_state_st())
        # Force a fresh distinct key.
        base = extra["administration"]
        candidate = base
        suffix = 0
        while candidate in seen:
            suffix += 1
            candidate = f"{base}~{suffix}"
        extra["administration"] = candidate
        seen[candidate] = extra
    return list(seen.values())


def _sources_from_state(state) -> dict[str, TenantSource]:
    return {
        t["administration"]: TenantSource(
            tenant={
                "administration": t["administration"],
                "display_name": t["display_name"],
                "version": t["version"],
            },
            tenant_modules=list(t["modules"]),
            user_tenant_roles=list(t["roles"]),
        )
        for t in state
    }


# ---------------------------------------------------------------------------
# Property 3: Tenant isolation of the projection
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(state=_multi_tenant_state_st())
def test_projection_reader_isolates_tenants(state):
    """Feature: s3-claims-and-projection, Property 3: Tenant isolation of the projection.

    For any multi-tenant source state: a read scoped to tenant ``T`` returns
    ONLY items whose partition key is ``T``, and a sort key that exists under
    another tenant is NOT addressable under ``T``'s scope (``get_item(T, sk)``
    is None unless ``T`` itself has that sort key). No cross-tenant leakage.
    """
    sources = _sources_from_state(state)
    admins = list(sources.keys())
    assert len(admins) >= 2  # generator guarantees a multi-tenant state

    # Populate the projection table through the REAL builder + sync (T12/T16).
    table = FakeTable()
    ProjectionSync(_FakeSource(sources), table=table).sync_all()

    reader = ProjectionReader(table=table)

    # Ground truth: the exact (tenant_id, sort_key) set the sync actually wrote,
    # grouped by tenant. Isolation is checked against this projected reality.
    sks_by_tenant: dict[str, set] = {a: set() for a in admins}
    for (tenant_id, sort_key) in table.store:
        sks_by_tenant.setdefault(tenant_id, set()).add(sort_key)

    for tenant in admins:
        own_sks = sks_by_tenant[tenant]

        # (1) query_tenant(T) returns ONLY items whose partition key is T.
        items = reader.query_tenant(tenant)
        returned_partitions = {i[schema.PARTITION_KEY_ATTR] for i in items}
        assert returned_partitions <= {tenant}, (
            f"query_tenant({tenant!r}) leaked other tenants' partitions: "
            f"{returned_partitions - {tenant}!r}"
        )
        # And it returns exactly this tenant's own projected items (no drops).
        assert {i[schema.SORT_KEY_ATTR] for i in items} == own_sks

        # (2) A sort key that exists under ANOTHER tenant is NOT addressable
        #     under T's scope — unless T itself also has that sort key.
        for other in admins:
            if other == tenant:
                continue
            for other_sk in sks_by_tenant[other]:
                fetched = reader.get_item(tenant, other_sk)
                if other_sk in own_sks:
                    # T legitimately has its own item under this shared sort key;
                    # it must be T's item (its own partition), never the other's.
                    assert fetched is not None
                    assert fetched[schema.PARTITION_KEY_ATTR] == tenant
                else:
                    # T does not have this sort key -> unaddressable from T.
                    assert fetched is None, (
                        f"tenant {tenant!r} addressed {other!r}'s item "
                        f"{other_sk!r} — cross-tenant leakage (R5.4)"
                    )

        # (3) Every item T can enumerate is genuinely T's (belt-and-braces).
        assert all(i[schema.PARTITION_KEY_ATTR] == tenant for i in items)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "--tb=short"]))
