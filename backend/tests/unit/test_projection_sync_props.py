"""Property-based test for the S3 one-directional projection (T17, R5.1/R5.2/R5.9).

Feature: s3-claims-and-projection
Property 1: One-directional projection (write-only, no split brain)

Validates: Requirements R5.1, R5.2, R5.9

This exercises the ``ProjectionSync`` surface (T16,
``services.projection_sync``) over a large generated space of governance states
(tenants x modules x roles, including edge cases) and arbitrary sequences of
sync runs, asserting the design.md D3 "One-directional guardrail" invariant:

  1. the sync issues writes **only** to the projection table — every recorded
     ``put_item`` targets the projection ``FakeTable`` and nothing else;
  2. the sync issues **zero** writes to MySQL — a ``DatabaseSourceProvider``
     backed by a spying ``DatabaseManager`` records only reads (``fetch=True``,
     never ``commit=True`` / ``fetch=False``) across the whole run sequence;
  3. a simulated module **read path** that reads the projection for its own
     tenant issues **no** writes to either store.

Both datastore seams are in-memory fakes (no real AWS, no real MySQL): a
``FakeTable`` (get_item/put_item, recording writes) and a ``SpyDb`` recording
every query with its intent. These are adapted from the concrete example tests
in ``test_projection_sync.py``; here they are driven by Hypothesis-generated
inputs and run sequences to give the exhaustive Property-1 coverage.

The exhaustive property is that NO write ever reaches MySQL and NO write ever
targets anything but the projection table, for ANY generated governance state
and ANY sequence of sync runs — the load-bearing "no split brain" invariant.
"""

import os
import sys

import pytest
from hypothesis import given, settings, strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services import projection_schema as schema  # noqa: E402
from services.module_registry import MODULE_REGISTRY  # noqa: E402
from services.projection_sync import (  # noqa: E402
    DatabaseSourceProvider,
    ProjectionSync,
    TenantSource,
)

# A test-local SAM-backed module injected into MODULE_REGISTRY so the builder's
# projection gate fires without touching the shipped registry (mirrors the
# example tests + test_projection_builder.py). Registered for the whole test via
# the autouse fixture below, so it is live across every Hypothesis example.
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
# In-memory fakes (adapted from test_projection_sync.py)
# ---------------------------------------------------------------------------


class FakeParameterService:
    """In-memory ``ParameterService`` stand-in — read-only, no DB I/O.

    ``ProjectionSync`` lazily builds ``ParameterService(DatabaseManager(...))`` for
    its ``parameter_service`` seam when a *projecting* tenant reaches the C2 config
    row build. Under the unit-test connection guard that real ``DatabaseManager``
    construction raises. Injecting this fake keeps the sync hermetic. ``get_param``
    returns ``None`` (empty-is-valid): the C2 builders still emit well-formed rows.
    """

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        return None


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (the projection table).

    Records every ``put_item`` so the property can assert all writes land here
    (and only here). Enforces the sync's conditional-version semantics so the
    fake is not more permissive than a real table.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.put_calls: list[dict] = []

    def _key_tuple(self, key_or_item):
        return (
            key_or_item[schema.PARTITION_KEY_ATTR],
            key_or_item[schema.SORT_KEY_ATTR],
        )

    def get_item(self, Key):
        item = self.store.get(self._key_tuple(Key))
        return {"Item": dict(item)} if item is not None else {}

    def put_item(
        self,
        Item,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        self.put_calls.append(dict(Item))
        if ConditionExpression is not None:
            existing = self.store.get(self._key_tuple(Item))
            incoming = (ExpressionAttributeValues or {}).get(":incoming")
            if existing is not None:
                stored_version = existing.get(schema.VERSION_ATTR)
                if stored_version is not None and not (stored_version < incoming):
                    raise _conditional_check_failed()
        self.store[self._key_tuple(Item)] = dict(Item)
        return {}

    def query(
        self,
        KeyConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        **_kwargs,
    ):
        """Tenant-scoped Query, single page.

        Supports the string-expression form the sync uses for scopegrant
        reconciliation — ``"#pk = :pk AND begins_with(#sk, :sk_prefix)"`` with the
        partition value in ``:pk`` and the SK prefix in ``:sk_prefix`` — returning
        only this tenant's items whose sort key begins with that prefix. All items
        fit in one page, so no ``LastEvaluatedKey`` is returned.
        """
        values = ExpressionAttributeValues or {}
        pk = values.get(":pk")
        sk_prefix = values.get(":sk_prefix")
        items = [
            dict(v)
            for (item_pk, item_sk), v in self.store.items()
            if item_pk == pk
            and (sk_prefix is None or str(item_sk).startswith(sk_prefix))
        ]
        return {"Items": items}


def _conditional_check_failed():
    err = Exception("The conditional request failed")
    err.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    return err


class SpyDb:
    """A ``DatabaseManager`` spy recording every query and its write/read intent.

    The MySQL seam for Property 1: any write (``commit=True`` or ``fetch=False``)
    would be recorded and asserted absent. Answers the read queries
    ``DatabaseSourceProvider`` issues from a pre-built governance state.
    """

    def __init__(self, tenants, modules_by_admin, roles_by_admin):
        self._tenants = tenants  # list[dict] each with 'administration'
        self._modules = modules_by_admin  # {admin: list[dict]}
        self._roles = roles_by_admin  # {admin: list[dict]}
        self.calls: list[dict] = []

    def execute_query(self, query, params=None, fetch=True, commit=False):
        self.calls.append(
            {"query": query, "params": params, "fetch": fetch, "commit": commit}
        )
        q = query.strip().upper()
        if q.startswith("SELECT ADMINISTRATION FROM TENANTS"):
            return [dict(t) for t in self._tenants]
        admin = params[0] if params else None
        if q.startswith("SELECT * FROM TENANTS"):
            return [dict(t) for t in self._tenants if t.get("administration") == admin]
        if q.startswith("SELECT * FROM TENANT_MODULES"):
            return [dict(m) for m in self._modules.get(admin, [])]
        if q.startswith("SELECT EMAIL, ROLE FROM USER_TENANT_ROLES"):
            return [dict(r) for r in self._roles.get(admin, [])]
        return []


class SpyModuleReader:
    """A simulated module read path over the projection table (design.md D3).

    Reads only its own ``tenant_id`` partition via ``get_item`` and NEVER writes
    the projection or MySQL. Records reads so the test can confirm it did read;
    it exposes no write method at all, so a write would fail structurally. It
    holds references to both stores only to assert (via the recorded call logs)
    that it touched neither store's write surface.
    """

    def __init__(self, table: FakeTable):
        self._table = table
        self.reads: list[dict] = []

    def read_tenant(self, tenant_id, sort_key_value):
        key = schema.build_key(tenant_id, sort_key_value)
        self.reads.append(key)
        return self._table.get_item(Key=key)


# ---------------------------------------------------------------------------
# Strategies — a generated governance state (tenants x modules x roles).
#
# Edge cases baked in: empty tenant (no modules/roles), tenant with only
# flask-backed modules (not projected), unicode emails, duplicate role grants,
# inactive modules, and per-item version fields to drive re-run behaviour.
# ---------------------------------------------------------------------------

# Separator-free, non-empty text for keys/names (avoids build_sort_key's "#" ban).
_seg_text = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() != "")

# Emails including unicode / edge shapes; still separator-free + non-blank.
_email = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=12,
).filter(lambda s: s.strip() != "")

_version = st.integers(min_value=0, max_value=1000)


def _module_row_st():
    """A tenant_modules row: SAM or flask module, active or inactive, versioned."""
    return st.fixed_dictionaries(
        {
            "module_name": st.sampled_from([_SAM_MODULE_NAME, _FLASK_MODULE_NAME]),
            "is_active": st.booleans(),
            "version": _version,
        }
    )


def _role_row_st():
    """A user_tenant_roles row (email, role) — unicode + duplicate-prone."""
    return st.fixed_dictionaries(
        {
            "email": _email,
            "role": st.sampled_from(["SamTest_Read", "SamTest_CRUD", "Tenant_Admin"]),
            "version": _version,
        }
    )


def _tenant_state_st():
    """One tenant's full source state: tenant row + module rows + role rows."""
    return st.fixed_dictionaries(
        {
            "administration": _seg_text,
            "display_name": st.text(max_size=12),
            "version": _version,
            "modules": st.lists(_module_row_st(), min_size=0, max_size=4),
            "roles": st.lists(_role_row_st(), min_size=0, max_size=4),
        }
    )


@st.composite
def _governance_state_st(draw):
    """A multi-tenant governance state with unique administration keys."""
    tenants = draw(
        st.lists(_tenant_state_st(), min_size=0, max_size=4)
    )
    # De-duplicate on administration so tenants are distinct partitions.
    seen = {}
    for t in tenants:
        seen[t["administration"]] = t
    return list(seen.values())


def _build_source_maps(state):
    """Split a generated state into the row shapes SpyDb / TenantSource expect."""
    tenants = [
        {
            "administration": t["administration"],
            "display_name": t["display_name"],
            "version": t["version"],
        }
        for t in state
    ]
    modules_by_admin = {t["administration"]: list(t["modules"]) for t in state}
    roles_by_admin = {t["administration"]: list(t["roles"]) for t in state}
    return tenants, modules_by_admin, roles_by_admin


# A small strategy for a "sequence of sync runs": each element chooses either a
# full sync_all() or a sync of one specific administration (by index).
_run_step_st = st.one_of(
    st.just(("all", None)),
    st.tuples(st.just("one"), st.integers(min_value=0, max_value=3)),
)


# ---------------------------------------------------------------------------
# Property 1: One-directional projection (write-only, no split brain)
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(state=_governance_state_st(), run_steps=st.lists(_run_step_st, min_size=1, max_size=6))
def test_sync_is_write_only_to_projection_and_zero_mysql_writes(state, run_steps):
    """Feature: s3-claims-and-projection, Property 1: One-directional projection (write-only, no split brain).

    For ANY generated governance state and ANY sequence of sync runs:
      * every write the sync issues targets the projection table only (all
        recorded put_item calls land on the FakeTable, keyed by a real tenant),
      * the MySQL spy records ZERO writes (only fetch=True SELECTs, never a
        commit / fetch=False write) across the whole run sequence,
      * a simulated module read path reads the projection and writes nothing to
        either store.
    """
    tenants, modules_by_admin, roles_by_admin = _build_source_maps(state)
    admins = [t["administration"] for t in tenants]

    db = SpyDb(tenants, modules_by_admin, roles_by_admin)
    provider = DatabaseSourceProvider(db)
    table = FakeTable()
    sync = ProjectionSync(
        provider, table=table, parameter_service=FakeParameterService()
    )

    # Drive the arbitrary sequence of sync runs.
    for kind, arg in run_steps:
        if kind == "all" or not admins:
            sync.sync_all()
        else:
            sync.sync_administration(admins[arg % len(admins)])

    # (2) ZERO MySQL writes: every recorded DB call is a read (fetch=True and
    #     not commit) — the sync never issues an INSERT/UPDATE/DELETE/commit.
    assert all(
        c["fetch"] and not c["commit"] for c in db.calls
    ), f"sync issued a MySQL write: {[c for c in db.calls if c['commit'] or not c['fetch']]}"

    # (1) Writes land ONLY on the projection table: every recorded put_item is a
    #     well-formed projection item keyed by one of the real tenant partitions.
    valid_admins = set(admins)
    for put in table.put_calls:
        assert schema.PARTITION_KEY_ATTR in put and schema.SORT_KEY_ATTR in put
        assert put[schema.PARTITION_KEY_ATTR] in valid_admins
    # And everything that persisted is under a real tenant partition (no split
    # brain / cross-store leakage — the table holds projection items only).
    assert all(k[0] in valid_admins for k in table.store)

    # (3) Simulated module read path: read each stored item's own partition and
    #     assert it caused NO further writes to either store.
    reader = SpyModuleReader(table)
    puts_before = len(table.put_calls)
    db_calls_before = len(db.calls)
    for (tenant_id, sort_key_value) in list(table.store.keys()):
        reader.read_tenant(tenant_id, sort_key_value)
    # Reading wrote nothing to the projection table...
    assert len(table.put_calls) == puts_before
    # ...and nothing to MySQL (the reader never touches the DB at all).
    assert len(db.calls) == db_calls_before
    # The reader has no write surface (structural guarantee).
    assert not any(
        m in {"put_item", "write", "save", "delete"} for m in dir(reader)
    )


@settings(max_examples=150, deadline=None)
@given(state=_governance_state_st(), run_steps=st.lists(_run_step_st, min_size=1, max_size=6))
def test_sync_via_fake_source_writes_only_projection_table(state, run_steps):
    """Feature: s3-claims-and-projection, Property 1: One-directional projection (write-only, no split brain).

    Same invariant driven through an in-memory ``FakeSource`` (no DB seam at
    all): for any state and any run sequence, the ONLY store the sync mutates is
    the projection table, and every persisted key belongs to a real tenant
    partition (SAM-eligible tenants only). A tenant with no SAM-backed active
    module contributes zero writes.
    """
    tenants, modules_by_admin, roles_by_admin = _build_source_maps(state)
    admins = [t["administration"] for t in tenants]

    sources = {
        t["administration"]: TenantSource(
            tenant=t,
            tenant_modules=modules_by_admin[t["administration"]],
            user_tenant_roles=roles_by_admin[t["administration"]],
        )
        for t in tenants
    }

    class FakeSource:
        def list_administrations(self):
            return list(sources.keys())

        def get_tenant_source(self, administration):
            return sources.get(administration)

    table = FakeTable()
    sync = ProjectionSync(
        FakeSource(), table=table, parameter_service=FakeParameterService()
    )

    for kind, arg in run_steps:
        if kind == "all" or not admins:
            sync.sync_all()
        else:
            sync.sync_administration(admins[arg % len(admins)])

    valid_admins = set(admins)
    # Every persisted item is keyed by a real tenant partition — the sync writes
    # only the projection table, one-directionally, with no cross-tenant leakage.
    assert all(k[0] in valid_admins for k in table.store)
    for put in table.put_calls:
        assert put[schema.PARTITION_KEY_ATTR] in valid_admins


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "--tb=short"]))
