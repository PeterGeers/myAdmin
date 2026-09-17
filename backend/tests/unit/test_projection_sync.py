"""Unit tests for the S3 governance projection sync (T16, R5.1/R5.2/R5.6/R5.9).

Covers design.md D3 "Components and interfaces" + "Versioning + idempotence"
+ "One-directional guardrail": ``ProjectionSync`` is the SOLE writer of the
projection table, reads MySQL read-only (zero MySQL writes), builds + validates
items, and conditionally writes them with monotonic versioning.

These are concrete example tests using **in-memory fakes** for both seams (no
real AWS, no real MySQL): a ``FakeTable`` implementing DynamoDB's
``get_item`` / ``put_item`` (with the same conditional-version semantics a real
table would enforce), and a fake ``SourceProvider``. The exhaustive
property-based coverage (Properties 1/4/6 over generated inputs) lands in
T17/T18/T22; these pin the behaviour with specific scenarios.

Feature: s3-claims-and-projection
"""

import pytest

from services import projection_schema as schema
from services.module_registry import MODULE_REGISTRY
from services.projection_sync import (
    DatabaseSourceProvider,
    ProjectionSync,
    SyncResult,
    TenantSource,
)
from services.projection_validator import ProjectionValidationError

# A test-local SAM-backed module so the builder's projection gate fires without
# touching the shipped registry (mirrors test_projection_builder.py).
_SAM_MODULE_NAME = "SAM_TEST_MODULE"


@pytest.fixture
def sam_module(monkeypatch):
    entry = {
        "description": "Temporary SAM-backed test module",
        "required_params": {},
        "required_tax_rates": [],
        "required_roles": ["SamTest_Read"],
        "backing": {
            "kind": "sam",
            "api_base_env": "SAM_TEST_MODULE_API_BASE",
            "data_namespace": "sam_test",
        },
    }
    monkeypatch.setitem(MODULE_REGISTRY, _SAM_MODULE_NAME, entry)
    return _SAM_MODULE_NAME


# --- in-memory fakes --------------------------------------------------------


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table.

    Stores items keyed by (tenant_id, sk). Implements the two methods the sync
    uses — ``get_item`` and ``put_item`` — and enforces the conditional-version
    guarantee a real table would: a put with the sync's
    ``attribute_not_exists(#v) OR #v < :incoming`` condition is rejected (raising
    a botocore-shaped ConditionalCheckFailedException) when the stored version is
    already >= the incoming version. Records every put for write-count assertions.
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
        # Enforce the same conditional semantics a real table would, so the fake
        # is not more permissive than production.
        if ConditionExpression is not None:
            existing = self.store.get(self._key_tuple(Item))
            incoming = (ExpressionAttributeValues or {}).get(":incoming")
            if existing is not None:
                stored_version = existing.get(schema.VERSION_ATTR)
                if stored_version is not None and not (stored_version < incoming):
                    raise _conditional_check_failed()
        self.store[self._key_tuple(Item)] = dict(Item)
        return {}


def _conditional_check_failed():
    err = Exception("The conditional request failed")
    err.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    return err


class FakeSource:
    """In-memory `SourceProvider` — returns pre-set `TenantSource`s, no I/O."""

    def __init__(self, sources: dict[str, TenantSource]):
        self._sources = sources

    def list_administrations(self):
        return list(self._sources.keys())

    def get_tenant_source(self, administration):
        return self._sources.get(administration)


class SpyDb:
    """A `DatabaseManager` spy that records every query and its intent.

    Used to prove the sync issues ZERO MySQL writes (R5.1/R5.2/R5.9): only
    ``fetch=True`` SELECTs may reach it; a write (``commit=True`` / ``fetch=False``)
    would be recorded and asserted absent.
    """

    def __init__(self, responses: dict):
        self._responses = responses
        self.calls: list[dict] = []

    def execute_query(self, query, params=None, fetch=True, commit=False):
        self.calls.append(
            {"query": query, "params": params, "fetch": fetch, "commit": commit}
        )
        for prefix, rows in self._responses.items():
            if query.strip().upper().startswith(prefix):
                if "WHERE" not in query.upper():
                    return rows
                # scoped query: filter by administration param
                admin = params[0] if params else None
                return [r for r in rows if r.get("administration") == admin]
        return []


# --- helpers ----------------------------------------------------------------


def _tenant_source(admin, module_name, *, module_version=1, tenant_version=1, roles=None):
    return TenantSource(
        tenant={"administration": admin, "display_name": f"{admin} Ltd", "version": tenant_version},
        tenant_modules=[
            {"module_name": module_name, "is_active": True, "version": module_version}
        ],
        user_tenant_roles=roles or [],
    )


def _items_in(table, admin):
    return {k[1]: v for k, v in table.store.items() if k[0] == admin}


# --- single-tenant sync writes the expected items --------------------------


def test_sync_administration_single_tenant_writes_expected_items(sam_module):
    table = FakeTable()
    source = FakeSource(
        {
            "TenantA": _tenant_source(
                "TenantA",
                sam_module,
                roles=[{"email": "a@b.example", "role": "SamTest_Read"}],
            )
        }
    )
    sync = ProjectionSync(source, table=table)

    result = sync.sync_administration("TenantA")

    written = _items_in(table, "TenantA")
    # tenant record + module record + role record
    assert schema.build_sort_key(schema.RECORD_TYPE_TENANT) in written
    assert schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module) in written
    assert (
        schema.build_sort_key(schema.RECORD_TYPE_ROLE, "a@b.example", "SamTest_Read")
        in written
    )
    assert result.written == 3
    assert result.skipped == 0


def test_sync_administration_non_sam_tenant_writes_nothing():
    # No SAM-backed module enabled -> builder returns [] -> nothing written.
    table = FakeTable()
    source = FakeSource(
        {
            "TenantA": TenantSource(
                tenant={"administration": "TenantA"},
                tenant_modules=[],
                user_tenant_roles=[],
            )
        }
    )
    sync = ProjectionSync(source, table=table)

    result = sync.sync_administration("TenantA")

    assert result.written == 0
    assert table.store == {}


def test_sync_administration_absent_tenant_is_noop(sam_module):
    table = FakeTable()
    sync = ProjectionSync(FakeSource({}), table=table)
    result = sync.sync_administration("Unknown")
    assert result.is_noop
    assert table.store == {}


# --- idempotence: re-run against unchanged source is a no-op (R5.6) ---------


def test_sync_administration_rerun_unchanged_source_is_noop(sam_module):
    table = FakeTable()
    source = FakeSource({"TenantA": _tenant_source("TenantA", sam_module)})
    sync = ProjectionSync(source, table=table)

    first = sync.sync_administration("TenantA")
    assert first.written > 0
    snapshot = {k: dict(v) for k, v in table.store.items()}

    second = sync.sync_administration("TenantA")

    assert second.written == 0
    assert second.skipped == first.written
    # Stored items + versions are byte-for-byte identical (no version churn).
    assert {k: dict(v) for k, v in table.store.items()} == snapshot


# --- versioning: higher overwrites, equal/lower does not (R5.6) ------------


def test_sync_higher_version_overwrites(sam_module):
    table = FakeTable()
    sources = {"TenantA": _tenant_source("TenantA", sam_module, module_version=1)}
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table)
    sync.sync_administration("TenantA")

    module_sk = schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module)
    assert table.store[("TenantA", module_sk)][schema.VERSION_ATTR] == 1

    # Bump the module version in the source and re-sync.
    sources["TenantA"] = _tenant_source("TenantA", sam_module, module_version=5)
    result = sync.sync_administration("TenantA")

    assert table.store[("TenantA", module_sk)][schema.VERSION_ATTR] == 5
    assert result.written >= 1


def test_sync_equal_version_does_not_overwrite(sam_module):
    table = FakeTable()
    source = FakeSource({"TenantA": _tenant_source("TenantA", sam_module, module_version=3)})
    sync = ProjectionSync(source, table=table)
    sync.sync_administration("TenantA")

    module_sk = schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module)

    result = sync.sync_administration("TenantA")  # same version 3

    assert result.written == 0
    assert table.store[("TenantA", module_sk)][schema.VERSION_ATTR] == 3


def test_sync_lower_version_does_not_overwrite(sam_module):
    table = FakeTable()
    sources = {"TenantA": _tenant_source("TenantA", sam_module, module_version=10)}
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table)
    sync.sync_administration("TenantA")

    module_sk = schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module)
    assert table.store[("TenantA", module_sk)][schema.VERSION_ATTR] == 10

    # A stale (lower) version must not clobber the newer stored value.
    sources["TenantA"] = _tenant_source("TenantA", sam_module, module_version=2)
    result = sync.sync_administration("TenantA")

    assert table.store[("TenantA", module_sk)][schema.VERSION_ATTR] == 10
    assert result.written == 0


# --- malformed item aborts the tenant with no partial write (R5.5) ---------


def test_sync_builder_error_on_missing_role_field_raises_before_write(sam_module):
    table = FakeTable()
    bad_source = TenantSource(
        tenant={"administration": "TenantA", "version": 1},
        tenant_modules=[{"module_name": sam_module, "is_active": True, "version": 1}],
        user_tenant_roles=[{"email": "a@b.example"}],  # missing 'role'
    )
    sync = ProjectionSync(FakeSource({"TenantA": bad_source}), table=table)

    with pytest.raises(ValueError):
        sync.sync_administration("TenantA")

    # No partial write: the malformed batch never reached the table.
    assert table.store == {}
    assert table.put_calls == []


def test_sync_validation_error_aborts_before_any_write(sam_module, monkeypatch):
    """A validator rejection aborts the tenant with zero writes (R5.5)."""
    import services.projection_sync as sync_module

    table = FakeTable()
    source = FakeSource(
        {
            "TenantA": _tenant_source(
                "TenantA",
                sam_module,
                roles=[{"email": "a@b.example", "role": "SamTest_Read"}],
            )
        }
    )
    sync = ProjectionSync(source, table=table)

    def _boom(items):
        raise ProjectionValidationError("forced validation failure")

    monkeypatch.setattr(sync_module, "validate_items", _boom)

    with pytest.raises(ProjectionValidationError):
        sync.sync_administration("TenantA")

    assert table.store == {}
    assert table.put_calls == []


# --- sync_all across multiple tenants ---------------------------------------


def test_sync_all_processes_every_administration(sam_module):
    table = FakeTable()
    source = FakeSource(
        {
            "TenantA": _tenant_source("TenantA", sam_module),
            "TenantB": _tenant_source("TenantB", sam_module),
        }
    )
    sync = ProjectionSync(source, table=table)

    result = sync.sync_all()

    assert set(result.administrations) == {"TenantA", "TenantB"}
    assert _items_in(table, "TenantA")
    assert _items_in(table, "TenantB")
    # Tenant isolation: no cross-tenant keys.
    assert all(k[0] in {"TenantA", "TenantB"} for k in table.store)


# --- zero MySQL writes (R5.1/R5.2/R5.9) -------------------------------------


def test_database_source_provider_issues_zero_mysql_writes(sam_module):
    """The MySQL-backed source reads only — no write ever reaches the DB."""
    db = SpyDb(
        {
            "SELECT ADMINISTRATION FROM TENANTS": [{"administration": "TenantA"}],
            "SELECT * FROM TENANTS": [
                {"administration": "TenantA", "display_name": "A", "version": 1}
            ],
            "SELECT * FROM TENANT_MODULES": [
                {
                    "administration": "TenantA",
                    "module_name": sam_module,
                    "is_active": True,
                    "version": 1,
                }
            ],
            "SELECT EMAIL, ROLE FROM USER_TENANT_ROLES": [],
        }
    )
    provider = DatabaseSourceProvider(db)
    table = FakeTable()
    sync = ProjectionSync(provider, table=table)

    sync.sync_all()

    # Every DB call must be a read (fetch=True, no commit) — zero writes.
    assert db.calls, "expected the sync to read from MySQL"
    assert all(c["fetch"] and not c["commit"] for c in db.calls)
    # And it actually projected the SAM tenant.
    assert _items_in(table, "TenantA")


def test_projection_sync_has_no_mysql_write_surface():
    """Structural guardrail: the sync exposes no method that writes MySQL."""
    write_ish = {"insert", "update", "delete", "commit", "write", "save"}
    method_names = {n.lower() for n in dir(ProjectionSync) if not n.startswith("_")}
    assert not (method_names & write_ish)
