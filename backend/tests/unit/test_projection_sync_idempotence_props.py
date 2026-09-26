"""Property-based test for the S3 projection's idempotent, versioned sync (T18).

Feature: s3-claims-and-projection
Property 4: Idempotent, versioned sync

Validates: Requirements R5.6, R5.8

design.md "Correctness Properties" states Property 4 as:

    *For any* source state, running the sync twice with the source unchanged
    leaves the projection items and their versions identical to the state after
    the first run (a second run is a no-op).

This exercises the ``ProjectionSync`` surface (T16, ``services.projection_sync``)
over a large generated space of governance states (tenants x modules x roles,
including edge cases: empty tenant, no modules, duplicate role grants, inactive
modules, mixed SAM/flask backing) and asserts:

  * **Idempotence (R5.6).** After sync #1, we snapshot the projection table
    (items + versions). Sync #2 on the UNCHANGED source is a no-op: the stored
    items and their ``version`` attributes are byte-for-byte identical to the
    snapshot, and ``SyncResult.written == 0`` on the second run (no version
    churn).

  * **Versioned staleness (R5.8).** Where a tenant has projectable items, a
    real source change that BUMPS an item's version is picked up by a re-sync:
    the new version strictly supersedes the old one (versions are monotonic and
    comparable), a reader holding the old version ``v`` would observe ``v' > v``,
    and a tenant-scoped read of the projection reflects the changed value
    (convergence). A stale (lower) version never clobbers the newer stored value.

Both datastore seams are in-memory fakes (no real AWS, no real MySQL): a
``FakeTable`` (get_item/put_item with the sync's conditional-version semantics)
and an in-memory ``FakeSource``. These mirror the patterns established in
``test_projection_sync.py`` and ``test_projection_sync_props.py`` (T17). A
test-local SAM-backed module is injected into ``MODULE_REGISTRY`` via an autouse
``monkeypatch.setitem`` so the builder's projection gate fires across every
Hypothesis example.
"""

import copy
import os
import sys

import pytest
from hypothesis import given, settings, strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services import projection_schema as schema  # noqa: E402
from services.module_registry import MODULE_REGISTRY  # noqa: E402
from services.projection_sync import ProjectionSync, TenantSource  # noqa: E402

# A test-local SAM-backed module injected into MODULE_REGISTRY so the builder's
# projection gate fires without touching the shipped registry (mirrors T17). A
# flask-backed module is also injected to exercise the "not-projected" edge.
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
            # No 'backing' block -> flask-backed (not SAM, not the projection gate).
        },
    )


# ---------------------------------------------------------------------------
# In-memory fakes (adapted from test_projection_sync.py / _props.py)
# ---------------------------------------------------------------------------


class FakeParameterService:
    """In-memory ``ParameterService`` stand-in — read-only, no DB I/O.

    Injected into ``ProjectionSync`` so a projecting tenant's C2 config-row build
    does not lazily construct ``ParameterService(DatabaseManager(...))`` (which the
    unit-test connection guard blocks). ``get_param`` → ``None`` is empty-is-valid.
    """

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        return None


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (the projection table).

    Implements ``get_item`` / ``put_item`` and enforces the sync's conditional
    version semantics (``attribute_not_exists(#v) OR #v < :incoming``) so the
    fake is not more permissive than a real table. Records every put so the
    property can count writes and detect version churn.
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


class FakeSource:
    """In-memory `SourceProvider` — returns pre-set `TenantSource`s, no I/O.

    Mutable by design: the R5.8 case bumps a source row's version between syncs
    to model a *real source change*, then re-syncs against the same provider.
    """

    def __init__(self, sources: dict[str, TenantSource]):
        self._sources = sources

    def list_administrations(self):
        return list(self._sources.keys())

    def get_tenant_source(self, administration):
        return self._sources.get(administration)

    def set(self, administration, source: TenantSource):
        self._sources[administration] = source


class SpyModuleReader:
    """A simulated module read path over the projection (design.md D3, R5.8).

    Reads only its own ``tenant_id`` partition via ``get_item`` and never writes.
    Used to confirm a reader holding an old version observes the newer version
    after a real source change (staleness detection / convergence).
    """

    def __init__(self, table: FakeTable):
        self._table = table

    def read_version(self, tenant_id, sort_key_value):
        key = schema.build_key(tenant_id, sort_key_value)
        response = self._table.get_item(Key=key)
        item = response.get("Item")
        return item.get(schema.VERSION_ATTR) if item else None


# ---------------------------------------------------------------------------
# Strategies — a generated governance state (tenants x modules x roles).
#
# Edge cases baked in: empty tenant (no modules/roles), tenant with only
# flask-backed modules (not projected), inactive modules, duplicate role grants,
# unicode-ish emails, and per-item versions to drive re-run behaviour.
# ---------------------------------------------------------------------------

# Separator-free, non-empty text for keys/names (avoids build_sort_key's "#" ban).
_seg_text = st.text(
    alphabet=st.characters(blacklist_characters="#", blacklist_categories=("Cs", "Cc")),
    min_size=1,
    max_size=10,
).filter(lambda s: s.strip() != "")

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
    """A user_tenant_roles row (email, role) — duplicate-prone."""
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
    tenants = draw(st.lists(_tenant_state_st(), min_size=0, max_size=4))
    # De-duplicate on administration so tenants are distinct partitions.
    seen = {}
    for t in tenants:
        seen[t["administration"]] = t
    return list(seen.values())


def _sources_from_state(state):
    """Turn a generated state into a {administration: TenantSource} mapping."""
    return {
        t["administration"]: TenantSource(
            tenant={
                "administration": t["administration"],
                "display_name": t["display_name"],
                "version": t["version"],
            },
            tenant_modules=[dict(m) for m in t["modules"]],
            user_tenant_roles=[dict(r) for r in t["roles"]],
        )
        for t in state
    }


def _snapshot(table: FakeTable):
    """A deep, comparable snapshot of the projection table (items + versions)."""
    return {k: copy.deepcopy(v) for k, v in table.store.items()}


# ---------------------------------------------------------------------------
# Property 4: Idempotent, versioned sync — the unchanged re-run is a no-op.
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(state=_governance_state_st())
def test_sync_twice_unchanged_source_is_a_noop(state):
    """Feature: s3-claims-and-projection, Property 4: Idempotent, versioned sync.

    For ANY generated governance state: after sync #1, a second sync against the
    UNCHANGED source writes nothing and leaves every projected item and its
    version byte-for-byte identical to the post-sync-#1 snapshot (R5.6).
    """
    sources = _sources_from_state(state)
    table = FakeTable()
    sync = ProjectionSync(
        FakeSource(sources), table=table, parameter_service=FakeParameterService()
    )

    first = sync.sync_all()
    snapshot = _snapshot(table)
    puts_after_first = len(table.put_calls)

    second = sync.sync_all()

    # Second run is a no-op: nothing written. Every item the sync builds is now
    # skipped (idempotent, ordering-tolerant, R5.6). The count of items built is
    # stable across runs, so the second run's skips equal the first run's total
    # attempts (writes + skips) — the latter can exceed the number of DISTINCT
    # stored keys when the source has duplicate rows collapsing to one key.
    assert second.written == 0
    assert second.skipped == first.written + first.skipped
    # No version churn: no new put_item calls landed on the second run.
    assert len(table.put_calls) == puts_after_first
    # Items + versions are byte-for-byte identical to the post-run-#1 snapshot.
    assert _snapshot(table) == snapshot


@settings(max_examples=150, deadline=None)
@given(state=_governance_state_st())
def test_repeated_syncs_are_stable_across_identical_reruns(state):
    """Feature: s3-claims-and-projection, Property 4: Idempotent, versioned sync.

    Running the sync several more times on the unchanged source never mutates the
    projection: the item set and every ``version`` stay fixed after the first run
    (R5.6). At minimum, versions are stable across identical re-runs.
    """
    sources = _sources_from_state(state)
    table = FakeTable()
    sync = ProjectionSync(
        FakeSource(sources), table=table, parameter_service=FakeParameterService()
    )

    sync.sync_all()
    snapshot = _snapshot(table)
    versions = {k: v.get(schema.VERSION_ATTR) for k, v in snapshot.items()}

    for _ in range(3):
        result = sync.sync_all()
        assert result.written == 0
        assert _snapshot(table) == snapshot
        assert {
            k: v.get(schema.VERSION_ATTR) for k, v in table.store.items()
        } == versions


# ---------------------------------------------------------------------------
# R5.8: a real source change bumps the version; a reader holding v sees v' > v.
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(state=_governance_state_st(), bump=st.integers(min_value=1, max_value=500))
def test_source_change_bumps_version_and_read_side_sees_it(state, bump):
    """Feature: s3-claims-and-projection, Property 4: Idempotent, versioned sync.

    R5.8 staleness/version angle. For ANY generated state that projects at least
    one item: after sync #1 a reader holds each item's version ``v``. A REAL
    source change that bumps every source row's version to ``v + bump`` (strictly
    greater) and a re-sync makes the new version supersede: the stored version is
    strictly greater than the snapshot, the reader now observes ``v' > v``
    (staleness detected), and a tenant-scoped read reflects the change
    (convergence). Then re-running the bumped source is itself a no-op again.
    """
    sources = _sources_from_state(state)
    provider = FakeSource(sources)
    table = FakeTable()
    sync = ProjectionSync(
        provider, table=table, parameter_service=FakeParameterService()
    )

    sync.sync_all()
    snapshot = _snapshot(table)

    # Skip the empty-projection case: no items means nothing to supersede. The
    # no-op property above already covers empty/flask-only tenants exhaustively.
    if not snapshot:
        return

    reader = SpyModuleReader(table)
    old_versions = {
        (k[0], k[1]): reader.read_version(k[0], k[1]) for k in snapshot
    }

    # Model a REAL source change: bump every source row's version strictly up.
    bumped = {}
    for admin, src in sources.items():
        bumped[admin] = TenantSource(
            tenant={**dict(src.tenant), "version": dict(src.tenant).get("version", 0) + bump},
            tenant_modules=[{**m, "version": m.get("version", 0) + bump} for m in src.tenant_modules],
            user_tenant_roles=[{**r, "version": r.get("version", 0) + bump} for r in src.user_tenant_roles],
        )
    for admin, src in bumped.items():
        provider.set(admin, src)

    result = sync.sync_all()

    # A real change was projected: at least one write happened this run.
    assert result.written >= 1

    # For every previously-stored item, the new version strictly supersedes and a
    # reader holding the old version detects the change (v' > v), reflecting the
    # converged source value.
    for (tenant_id, sk), old_v in old_versions.items():
        new_v = reader.read_version(tenant_id, sk)
        assert new_v is not None
        assert new_v > old_v, (
            f"version did not supersede for {(tenant_id, sk)!r}: "
            f"{new_v!r} !> {old_v!r}"
        )
        # Convergence: the stored version equals the (bumped) source version.
        assert new_v == old_v + bump

    # And the bumped source is now itself idempotent: re-running is a no-op.
    rerun = sync.sync_all()
    assert rerun.written == 0
    stable = _snapshot(table)
    assert sync.sync_all().written == 0
    assert _snapshot(table) == stable


@settings(max_examples=100, deadline=None)
@given(state=_governance_state_st(), drop=st.integers(min_value=1, max_value=1000))
def test_stale_lower_version_never_clobbers_newer_stored_value(state, drop):
    """Feature: s3-claims-and-projection, Property 4: Idempotent, versioned sync.

    Monotonicity guardrail behind R5.6/R5.8: a stale re-delivery carrying a
    strictly LOWER version must never overwrite the newer stored value. For any
    projecting state, lowering every source version and re-syncing writes nothing
    and leaves the stored items + versions identical to the first run.
    """
    sources = _sources_from_state(state)
    provider = FakeSource(sources)
    table = FakeTable()
    sync = ProjectionSync(
        provider, table=table, parameter_service=FakeParameterService()
    )

    sync.sync_all()
    snapshot = _snapshot(table)
    if not snapshot:
        return

    # Model a stale re-delivery: lower every source row's version.
    for admin, src in list(sources.items()):
        provider.set(
            admin,
            TenantSource(
                tenant={**dict(src.tenant), "version": _lower(dict(src.tenant).get("version", 0), drop)},
                tenant_modules=[{**m, "version": _lower(m.get("version", 0), drop)} for m in src.tenant_modules],
                user_tenant_roles=[{**r, "version": _lower(r.get("version", 0), drop)} for r in src.user_tenant_roles],
            ),
        )

    result = sync.sync_all()

    # Stale (lower/equal) versions are a no-op: the newer stored value stands.
    assert result.written == 0
    assert _snapshot(table) == snapshot


def _lower(version, drop):
    """A version strictly lower than ``version`` (clamped to stay non-negative)."""
    return version - drop if version - drop >= 0 else 0 if version > 0 else version


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "--tb=short"]))
