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

import json

import pytest

from services import projection_schema as schema
from services.module_registry import MODULE_REGISTRY
from services.projection_sync import (
    DatabaseSourceProvider,
    ProjectionSync,
    SyncResult,
    TenantSource,
    _supersedes,
    build_config_fields_row,
    build_config_mail_row,
    build_config_scope_row,
    build_scopegrant_rows,
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

    Stores items keyed by (tenant_id, sk). Implements the four methods the sync
    uses — ``get_item`` / ``put_item`` and (for the ODx4b diff-and-delete
    reconcile, task 3.5) ``query`` / ``delete_item`` — with the same semantics a
    real boto3 Table has, so the tests exercise the real reconcile, not a mock of
    it:

    - ``put_item`` enforces the conditional-version guarantee a real table would:
      a put with the sync's ``attribute_not_exists(#v) OR #v < :incoming``
      condition is rejected (raising a botocore-shaped
      ConditionalCheckFailedException) when the stored version is already >= the
      incoming version.
    - ``query`` supports the sync's tenant-scoped, ``begins_with(sk, …)`` key
      condition (``#pk = :pk AND begins_with(#sk, :sk_prefix)``), returning only
      the matching partition's rows — so a query cannot address another tenant.
    - ``delete_item`` removes the row at a (tenant_id, sk) key (a no-op if absent).

    Records every put/delete for write/delete-count assertions.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.put_calls: list[dict] = []
        self.delete_calls: list[dict] = []

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

    def query(
        self,
        KeyConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        ExclusiveStartKey=None,
    ):
        # Resolve the placeholders the sync uses. The partition is REQUIRED
        # (:pk); the sk-prefix (:sk_prefix) restricts to begins_with(sk, prefix).
        # A real Query only ever scans one partition — so does this fake, which is
        # exactly why the tenant-scoped reconcile can never touch another tenant.
        values = ExpressionAttributeValues or {}
        pk = values.get(":pk")
        sk_prefix = values.get(":sk_prefix")
        items = []
        for (tenant_id, sk), stored in self.store.items():
            if tenant_id != pk:
                continue
            if sk_prefix is not None and not sk.startswith(sk_prefix):
                continue
            items.append(dict(stored))
        # Single page — no pagination needed at test volumes (LastEvaluatedKey
        # omitted signals the sync's paginate loop to stop).
        return {"Items": items}

    def delete_item(self, Key):
        self.delete_calls.append(dict(Key))
        self.store.pop(self._key_tuple(Key), None)
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
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())

    result = sync.sync_administration("TenantA")

    written = _items_in(table, "TenantA")
    # tenant record + module record + role record
    assert schema.build_sort_key(schema.RECORD_TYPE_TENANT) in written
    assert schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module) in written
    assert (
        schema.build_sort_key(schema.RECORD_TYPE_ROLE, "a@b.example", "SamTest_Read")
        in written
    )
    # + the always-present config rows (empty/fail-closed when un-configured,
    # R1.6/R1.7/R5.1/R0):
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope") in written
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields") in written
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail") in written
    # Phase 2 (R5.3): the config#views row is no longer emitted.
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "views") not in written
    # tenant + module + role + config#scope + config#fields +
    # config#mail = 6 (no scopegrant: no scope_dimensions authored in the empty
    # FakeParameterService).
    assert result.written == 6
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
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())

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
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())
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
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())
    sync.sync_administration("TenantA")

    module_sk = schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module)

    result = sync.sync_administration("TenantA")  # same version 3

    assert result.written == 0
    assert table.store[("TenantA", module_sk)][schema.VERSION_ATTR] == 3


def test_sync_lower_version_does_not_overwrite(sam_module):
    table = FakeTable()
    sources = {"TenantA": _tenant_source("TenantA", sam_module, module_version=10)}
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())
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
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())

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
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())

    result = sync.sync_all()

    assert set(result.administrations) == {"TenantA", "TenantB"}
    assert _items_in(table, "TenantA")
    assert _items_in(table, "TenantB")
    # Tenant isolation: no cross-tenant keys.
    assert all(k[0] in {"TenantA", "TenantB"} for k in table.store)


def test_sync_all_tolerates_unknown_module_tenant_and_projects_good_tenant(sam_module):
    """R8.6: a source containing an unknown/legacy-module tenant + a good tenant
    completes without raising and projects the good tenant.

    Mirrors the dev-MySQL reality: 'myAdmin' has only a legacy 'ADMIN' module
    (unregistered) — it must be swept cleanly (nothing projected), NOT abort the
    whole run — while a Members-enabled tenant projects normally.
    """
    table = FakeTable()
    source = FakeSource(
        {
            # Unknown/legacy module only -> nothing to project, must NOT raise.
            "myAdmin": _tenant_source("myAdmin", "ADMIN"),
            # A legitimately SAM-enabled tenant -> projects.
            "GoodTenant": _tenant_source("GoodTenant", sam_module),
        }
    )
    sync = ProjectionSync(source, table=table, parameter_service=FakeParameterService())

    result = sync.sync_all()

    # The whole sweep completed and visited both tenants (no crash).
    assert set(result.administrations) == {"myAdmin", "GoodTenant"}
    # The unknown-module tenant projected nothing at all.
    assert _items_in(table, "myAdmin") == {}
    # The good tenant projected its rows.
    assert _items_in(table, "GoodTenant")
    assert result.written > 0


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
    sync = ProjectionSync(provider, table=table, parameter_service=FakeParameterService())

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


# --- C2 config#scope builder (S5b design.md C2, R1.1/R1.2) -----------------


class FakeParameterService:
    """In-memory `ParameterService` stand-in — read-only `get_param`, no I/O.

    Records every call so tests can prove the builder READS the tenant-scope
    `members.scope_dimensions` parameter and issues zero writes (Property 1,
    one-directional). Returns pre-set values keyed by (namespace, key, tenant).
    """

    def __init__(
        self,
        params: dict[tuple, object] | None = None,
        revisions: dict[tuple, object] | None = None,
    ):
        self._params = params or {}
        # Per-param revisions (the ``parameters.updated_at`` the real
        # ``get_param_revision`` returns), keyed by (namespace, key, tenant). A key
        # with no entry → None (un-authored / code-default: no per-param revision),
        # exactly like the real method, so the builders fall back to the tenant row.
        self._revisions = revisions or {}
        self.calls: list[dict] = []
        self.revision_calls: list[dict] = []

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        self.calls.append(
            {"namespace": namespace, "key": key, "tenant": tenant}
        )
        return self._params.get((namespace, key, tenant))

    def get_param_revision(self, namespace, key, tenant=None, role=None, user=None):
        self.revision_calls.append(
            {"namespace": namespace, "key": key, "tenant": tenant}
        )
        return self._revisions.get((namespace, key, tenant))


def _hdcn_region_dimension():
    """The h-dcn region dimension as authored tenant-scope parameter data.

    s5d clean break (R2.2/R8.1): no ``Regio_*`` ``all_wildcard`` role and no ``multi_valued``
    flag — scope is sourced from ``user_tenant_scope``, and each dimension binds to a member
    ``field`` (defaults to the dimension ``key``).
    """
    return {
        "key": "region",
        "field": "region",
        "label": {"nl": "Regio", "en": "Region"},
        "enabled": True,
        "values": ["Noord", "Zuid", "Oost", "West"],
        "required_for": ["Members_CRUD"],
    }


def test_build_config_scope_row_maps_authored_dimensions_to_row_shape():
    """Authored members.scope_dimensions param → config#scope dimensions shape."""
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )

    item = build_config_scope_row({"administration": "h-dcn", "version": 7}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope")
    assert item.version == 7
    assert item.attributes["dimensions"] == [_hdcn_region_dimension()]
    # A DynamoDB item carries the canonical key attrs + the dimensions list.
    dynamo = item.to_dynamodb_item()
    assert dynamo[schema.PARTITION_KEY_ATTR] == "h-dcn"
    assert dynamo[schema.SORT_KEY_ATTR] == "config#scope"
    assert dynamo["dimensions"][0]["values"] == ["Noord", "Zuid", "Oost", "West"]


def test_build_config_scope_row_no_param_yields_empty_dimensions():
    """Empty-is-valid (R1.6): an un-configured tenant → empty dimensions, no raise."""
    params = FakeParameterService({})  # nothing authored

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == "config#scope"
    assert item.attributes["dimensions"] == []
    assert item.version == 0  # deterministic fallback when the row has no version


def test_build_config_scope_row_partial_dimension_fills_safe_defaults():
    """A partially-authored dimension still yields a well-formed entry."""
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [{"key": "region"}]}
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    dim = item.attributes["dimensions"][0]
    assert dim["key"] == "region"
    assert dim["enabled"] is True
    assert dim["values"] == []
    assert dim["label"] == {}
    assert dim["field"] is None
    assert dim["required_for"] == []
    # s5d clean break: the Regio_* role encoding is gone — no all_wildcard/multi_valued keys.
    assert "all_wildcard" not in dim
    assert "multi_valued" not in dim


def test_build_config_scope_row_issues_zero_writes_and_reads_tenant_scope():
    """One-directional (Property 1): only tenant-scoped READS, zero writes.

    Phase 3 step 9: the builder reads the field_overlay FIRST (scope-as-field-attribute, the
    canonical authoring surface) and falls back to the standalone scope_dimensions param — both
    tenant-scoped READS, both on this tenant's members.* namespace, no writes.
    """
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )

    build_config_scope_row({"administration": "h-dcn"}, params)

    # Two reads (overlay-first, then the standalone fallback), both scoped to this tenant's
    # members.* params. No field scope authored → the fallback drives the row.
    assert params.calls == [
        {"namespace": "members", "key": "field_overlay", "tenant": "h-dcn"},
        {"namespace": "members", "key": "scope_dimensions", "tenant": "h-dcn"},
    ]


def test_build_config_scope_row_missing_tenant_key_raises():
    """A tenant without administration/tenant_id is a cross-tenant hazard (R5.4)."""
    with pytest.raises(ValueError):
        build_config_scope_row({}, FakeParameterService({}))


def test_build_config_scope_row_non_list_param_treated_as_empty():
    """A malformed (non-list) authored value degrades to empty, never raises."""
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): "not-a-list"}
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.attributes["dimensions"] == []


# --- Phase 3 step 9 (R2.1/R2.5): scope-binding authored as a field attribute ----------
#
# The authoring representation moves from the standalone members.scope_dimensions list onto a
# `scope` attribute on a members.field_overlay field. The builder DERIVES config#scope from
# those field attributes, keeping the projected row — and so the resolver's ScopeConfig —
# SEMANTICALLY EQUIVALENT (Property 2). The standalone param stays the fallback source so the
# scopegrant grants / grant-validation / picker (which read members.scope_dimensions) are
# untouched (R2.3/R2.4).


def test_build_config_scope_row_derives_dimensions_from_fixed_field_scope_attribute():
    """A fixed field's `scope` attribute → the same config#scope dimension shape (R2.1)."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.region": {
                        "scope": {
                            "enabled": True,
                            "values": ["Noord", "Zuid", "Oost", "West"],
                            "label": {"nl": "Regio", "en": "Region"},
                            "required_for": ["Members_CRUD"],
                        }
                    }
                }
            }
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.attributes["dimensions"] == [_hdcn_region_dimension()]


def test_build_config_scope_row_derived_equals_standalone_scope_dimensions():
    """Property 2 (semantic equivalence): field-authored scope projects the SAME row as the
    equivalent standalone members.scope_dimensions."""
    overlay_params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.region": {
                        "scope": {
                            "enabled": True,
                            "values": ["Noord", "Zuid", "Oost", "West"],
                            "label": {"nl": "Regio", "en": "Region"},
                            "required_for": ["Members_CRUD"],
                        }
                    }
                }
            }
        }
    )
    standalone_params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )

    derived = build_config_scope_row({"administration": "h-dcn"}, overlay_params)
    standalone = build_config_scope_row({"administration": "h-dcn"}, standalone_params)

    assert derived.attributes["dimensions"] == standalone.attributes["dimensions"]


def test_build_config_scope_row_derives_from_variable_field_scope_attribute():
    """An added variable field's `scope` attribute also derives a dimension (R2.1).

    Single-vocabulary (R3.4): the dimension values are the field's ENUM VALUES (`choices`),
    not `scope.values`. A `scope` object with no `values` is sufficient — the enum is the
    one vocabulary.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fields": {
                    "region": {
                        "type": "enum",
                        "choices": ["Noord", "Zuid"],
                        "scope": {"enabled": True},
                    }
                }
            }
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    dim = item.attributes["dimensions"][0]
    assert dim["key"] == "region"
    assert dim["field"] == "region"
    assert dim["values"] == ["Noord", "Zuid"]


def test_build_config_scope_row_derives_values_from_enum_not_scope_values():
    """Single-vocabulary (R3.4): when the field has enum values AND a legacy `scope.values`,
    the dimension values come from the ENUM — `scope.values` is ignored (not the authority)."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fields": {
                    "region": {
                        "type": "enum",
                        "choices": ["Noord", "Zuid", "Oost"],
                        # Stale legacy scope.values — MUST be ignored in favour of the enum.
                        "scope": {"enabled": True, "values": ["STALE"]},
                    }
                }
            }
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.attributes["dimensions"][0]["values"] == ["Noord", "Zuid", "Oost"]


def test_build_config_scope_row_derives_values_from_rich_options():
    """Single-vocabulary (R3.4): rich enum `options` ({value,label,roles?}) are the vocabulary —
    the dimension values are the per-option `value`s, in order."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fields": {
                    "region": {
                        "type": "enum",
                        "options": [
                            {"value": "Noord", "label": {"nl": "Noord"}},
                            {"value": "Zuid", "label": {"nl": "Zuid"}},
                        ],
                        "scope": {"enabled": True},
                    }
                }
            }
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.attributes["dimensions"][0]["values"] == ["Noord", "Zuid"]


def test_build_config_scope_row_honours_legacy_scope_values_when_no_enum():
    """Migration fallback (R3.4): a field with NO enum vocabulary still derives its dimension
    values from a legacy `scope.values` — pre-single-vocabulary authoring keeps working."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.region": {
                        "scope": {"enabled": True, "values": ["Noord", "Zuid"]}
                    }
                }
            }
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.attributes["dimensions"][0]["values"] == ["Noord", "Zuid"]


def test_build_config_scope_row_falls_back_to_standalone_param_when_no_field_scope():
    """A tenant that has not moved authoring onto fields still drives config#scope from the
    standalone members.scope_dimensions param (R2.4 — grant machinery untouched)."""
    params = FakeParameterService(
        {
            # An overlay with NO scope attribute on any field.
            ("members", "field_overlay", "h-dcn"): {
                "fields": {"motor_type": {"type": "string"}}
            },
            ("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()],
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    assert item.attributes["dimensions"] == [_hdcn_region_dimension()]


def test_build_config_scope_row_field_scope_takes_precedence_over_standalone_param():
    """When the overlay declares a scope axis, it drives the row (the two are not merged)."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.region": {
                        "scope": {"enabled": True, "values": ["A", "B"]}
                    }
                }
            },
            # A stale standalone param that must be IGNORED once field scope is authored.
            ("members", "scope_dimensions", "h-dcn"): [
                {"key": "season", "values": ["2024"]}
            ],
        }
    )

    item = build_config_scope_row({"administration": "h-dcn"}, params)

    keys = [d["key"] for d in item.attributes["dimensions"]]
    assert keys == ["region"]


# --- C2 config#fields builder (S5b design.md C2, R1.3) ---------------------


def _hdcn_field_overlay():
    """The h-dcn field overlay as authored tenant-scope parameter data.

    Mirrors the design.md ``config#fields`` example: a ``fields`` map (the
    variable overlay, e.g. a ``motor_type`` club detail) + an ``overrides`` map
    (presentation overrides of fixed fields, e.g. relabel/reorder ``personal.name``)
    — the shape ``sam/members/domain/field_resolver.py`` ``TenantOverlay`` consumes.
    """
    return {
        "fields": {
            "motor_type": {
                "type": "string",
                "required": False,
                "label": {"nl": "Motor", "en": "Motorcycle"},
                "order": 10,
            }
        },
        # The AUTHORED/validated key is ``fixed_overrides`` (design Data Models +
        # members_parameters.json + validate_field_overlay), NOT ``overrides`` — the
        # projection builder maps authored ``fixed_overrides`` → projected ``overrides``.
        "fixed_overrides": {
            "personal.name": {
                "label": {"nl": "Naam", "en": "Name"},
                "order": 1,
            }
        },
    }


def test_build_config_fields_row_maps_authored_overlay_to_row_shape():
    """Authored members.field_overlay param → config#fields fields/overrides shape."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()}
    )

    item = build_config_fields_row({"administration": "h-dcn", "version": 7}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields")
    assert item.version == 7
    # Variable overlay field carries the OverlayField shape (key defaulted from map key).
    motor = item.attributes["fields"]["motor_type"]
    assert motor["key"] == "motor_type"
    assert motor["type"] == "string"
    assert motor["required"] is False
    assert motor["label"] == {"nl": "Motor", "en": "Motorcycle"}
    assert motor["order"] == 10
    # Fixed-field override carries only the authored (presentation-only) aspects.
    name_override = item.attributes["overrides"]["personal.name"]
    assert name_override == {"label": {"nl": "Naam", "en": "Name"}, "order": 1}
    # A DynamoDB item carries the canonical key attrs + the two maps.
    dynamo = item.to_dynamodb_item()
    assert dynamo[schema.PARTITION_KEY_ATTR] == "h-dcn"
    assert dynamo[schema.SORT_KEY_ATTR] == "config#fields"
    assert dynamo["fields"]["motor_type"]["label"]["nl"] == "Motor"


def test_build_config_fields_row_no_param_yields_empty_overlay():
    """Empty-is-valid (R1.7): an un-configured tenant → empty maps, no raise."""
    params = FakeParameterService({})  # nothing authored

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == "config#fields"
    assert item.attributes["fields"] == {}
    assert item.attributes["overrides"] == {}
    # Phase 2 step (a): the config#fields row always carries a default_page_size key
    # (None when the tenant authored no members.default_page_size), so the SAM reader
    # can surface it on the field-config response.
    assert item.attributes["default_page_size"] is None
    assert item.version == 0  # deterministic fallback when the row has no version


def test_build_config_fields_row_partial_overlay_field_fills_safe_defaults():
    """A partially-authored variable field still yields a well-formed entry."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): {"fields": {"motor_type": {}}}}
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    field = item.attributes["fields"]["motor_type"]
    assert field["key"] == "motor_type"  # defaulted from the map key
    assert field["type"] == "string"
    assert field["required"] is False
    assert field["label"] == {}
    assert field["choices"] is None
    assert field["visible"] is True
    assert field["order"] == 0
    # No overrides authored -> empty overrides map.
    assert item.attributes["overrides"] == {}


def test_build_config_fields_row_issues_zero_writes_and_reads_tenant_scope():
    """One-directional (Property 1): only tenant-scoped READS, zero writes.

    Phase 2 step (a) adds a second read — the tenant-level ``default_page_size`` scalar
    carried on the SAME config#fields row — so the builder now reads BOTH ``field_overlay``
    and ``default_page_size``. Both are tenant-scoped ``get_param`` reads; still zero writes
    (``FakeParameterService`` exposes no write path).
    """
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()}
    )

    build_config_fields_row({"administration": "h-dcn"}, params)

    # Two reads, both scoped to this tenant's members.* params (overlay + page-size default).
    assert params.calls == [
        {"namespace": "members", "key": "field_overlay", "tenant": "h-dcn"},
        {"namespace": "members", "key": "default_page_size", "tenant": "h-dcn"},
    ]


def test_build_config_fields_row_missing_tenant_key_raises():
    """A tenant without administration/tenant_id is a cross-tenant hazard (R5.4)."""
    with pytest.raises(ValueError):
        build_config_fields_row({}, FakeParameterService({}))


def test_build_config_fields_row_non_mapping_param_treated_as_empty():
    """A malformed (non-mapping) authored value degrades to empty, never raises."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): "not-a-mapping"}
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["fields"] == {}
    assert item.attributes["overrides"] == {}


def test_build_config_fields_row_malformed_entries_are_skipped():
    """Non-mapping field/override entries are skipped; well-formed ones survive."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fields": {"bad": "not-a-mapping", "motor_type": {"type": "string"}},
                "fixed_overrides": {"personal.name": "nope", "personal.email": {"order": 2}},
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert set(item.attributes["fields"]) == {"motor_type"}
    assert set(item.attributes["overrides"]) == {"personal.email"}


def test_build_config_fields_row_honors_authored_fixed_overrides_key_with_functional_group():
    """The AUTHORED key is ``fixed_overrides`` and ``functional_group`` is carried (R4.9).

    A design example (``members.field_overlay.fixed_overrides["personal.street"] =
    {"functional_group": "address"}``) must project into the ``config#fields`` row's
    ``overrides`` map with ``functional_group`` carried — proving the builder reads the
    authored ``fixed_overrides`` source (not the old wrong ``overrides`` source key) and
    that R4.9 display-group reassignment survives projection.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.street": {"functional_group": "address"},
                    "personal.name": {"label": {"nl": "Naam"}, "order": 1},
                }
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn", "version": 3}, params)

    overrides = item.attributes["overrides"]
    assert overrides["personal.street"] == {"functional_group": "address"}
    assert overrides["personal.name"] == {"label": {"nl": "Naam"}, "order": 1}


def test_build_config_fields_row_fixed_override_enum_relabel_survives_projection():
    """I-9 (R5.1): a fixed-override enum relabel carries ``options`` + a coherent ``choices``.

    A tenant that relabels a FIXED enum field (e.g. ``personal.status``) authors rich
    ``options`` ({value, label}). Those options — and a bare ``choices`` list COHERENT with
    them (the per-option values, in order) — MUST survive projection to ``config#fields``
    rather than being silently dropped (the defect: the fixed-override builder dropped enum
    values). This is presentation-only (relabelling existing values), never a weakening.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.status": {
                        "label": {"nl": "Status", "en": "Status"},
                        "options": [
                            {"value": "active", "label": {"nl": "Actief", "en": "Active"}},
                            {"value": "lapsed", "label": {"nl": "Verlopen", "en": "Lapsed"}},
                        ],
                    }
                }
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    status = item.attributes["overrides"]["personal.status"]
    assert status["label"] == {"nl": "Status", "en": "Status"}
    # Rich options survive verbatim.
    assert status["options"] == [
        {"value": "active", "label": {"nl": "Actief", "en": "Active"}},
        {"value": "lapsed", "label": {"nl": "Verlopen", "en": "Lapsed"}},
    ]
    # The bare `choices` list is COHERENT with the rich options (per-option values, in order).
    assert status["choices"] == ["active", "lapsed"]


def test_build_config_fields_row_fixed_override_options_overwrite_incoherent_choices():
    """R5.1 coherence: an authored ``choices`` that disagrees with ``options`` is corrected.

    When both ``options`` and a stale/incoherent ``choices`` are authored, the projected
    ``choices`` is DERIVED from ``options`` (the single, consistent vocabulary) so the two
    representations can never disagree downstream.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.status": {
                        "options": [
                            {"value": "active", "label": {"nl": "Actief"}},
                            {"value": "lapsed", "label": {"nl": "Verlopen"}},
                        ],
                        # Stale/incoherent bare list — must be corrected to the options values.
                        "choices": ["STALE"],
                    }
                }
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    status = item.attributes["overrides"]["personal.status"]
    assert status["choices"] == ["active", "lapsed"]


def test_build_config_fields_row_fixed_override_bare_choices_carried_verbatim():
    """R5.1: a fixed override with only a bare ``choices`` list carries it through verbatim."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.region": {"choices": ["Noord", "Zuid", "Oost"]}
                }
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["overrides"]["personal.region"]["choices"] == [
        "Noord",
        "Zuid",
        "Oost",
    ]


def test_build_config_fields_row_fixed_override_scope_survives_projection():
    """I-9 (R5.1): a fixed-override ``scope`` attribute survives projection to config#fields.

    A tenant that marks a FIXED field a scope axis authors ``scope`` ({enabled, required_for}
    — the single-vocabulary shape, values live on the field's enum). That attribute MUST reach
    ``config#fields`` so the SAM read path (3.1) can serialize it back onto the resolved field
    for the modal to read, instead of the builder dropping it. config#scope stays the
    authoritative resolver source (R3); carrying the read representation here never weakens it.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {
                    "personal.region": {
                        "options": [
                            {"value": "Noord", "label": {"nl": "Noord"}},
                            {"value": "Zuid", "label": {"nl": "Zuid"}},
                        ],
                        "scope": {"enabled": True, "required_for": ["Members_CRUD"]},
                    }
                }
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    region = item.attributes["overrides"]["personal.region"]
    assert region["scope"] == {"enabled": True, "required_for": ["Members_CRUD"]}
    # The enum vocabulary (the scope's single vocabulary) also survives, coherently.
    assert region["choices"] == ["Noord", "Zuid"]


def test_build_config_fields_row_ignores_legacy_overrides_when_fixed_overrides_authored():
    """When ``fixed_overrides`` is authored, a stray legacy ``overrides`` key is not honored.

    The authored/validated source of truth is ``fixed_overrides``; if both are present the
    canonical ``fixed_overrides`` wins (the old wrong ``overrides`` source is not the one
    honored — author under ``fixed_overrides``).
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fixed_overrides": {"personal.street": {"functional_group": "address"}},
                # A stale/legacy key that must be ignored in favor of fixed_overrides.
                "overrides": {"personal.city": {"functional_group": "WRONG"}},
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    overrides = item.attributes["overrides"]
    assert set(overrides) == {"personal.street"}
    assert overrides["personal.street"] == {"functional_group": "address"}
    assert "personal.city" not in overrides


def test_build_config_fields_row_legacy_overrides_key_is_not_honored():
    """Phase 2 (R6.7): the legacy top-level ``overrides`` input key is no longer accepted.

    The dual-accept fallback was retired AFTER the one-time migration (R6.1) rewrote every
    stored overlay's legacy top-level ``overrides`` into the canonical ``fixed_overrides``.
    The builder now reads ONLY ``fixed_overrides`` from the authored overlay, so an overlay
    carrying only the legacy key projects an EMPTY ``overrides`` map (no production row still
    carries the legacy key after the migration). The PROJECTED attribute name stays
    ``overrides`` (R6.8 — unchanged).
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "overrides": {"personal.name": {"order": 2}}
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["overrides"] == {}


def test_build_config_fields_row_projects_functional_groups_catalog():
    """R4.9: the authored ``functional_groups`` catalog is carried onto config#fields.

    The tenant's DISPLAY-group catalog (orthogonal to the storage bucket) MUST reach the
    projection so ``MembersProjectionReader.get_overlay`` can rebuild
    ``TenantOverlay.functional_groups`` and the resolver can section fields by FUNCTION.
    Regression guard for the builder that previously dropped the catalog.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "functional_groups": [
                    {"key": "personal", "label": {"nl": "Persoonlijk", "en": "Personal"}, "order": 1},
                    {"key": "membership", "label": {"nl": "Lidmaatschap", "en": "Membership"}, "order": 3},
                ]
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    groups = item.attributes["functional_groups"]
    assert [g["key"] for g in groups] == ["personal", "membership"]
    assert groups[0]["label"] == {"nl": "Persoonlijk", "en": "Personal"}
    assert groups[1]["order"] == 3


def test_build_config_fields_row_no_catalog_yields_empty_functional_groups():
    """Empty-is-valid (R4.9): an overlay with no catalog projects an empty groups list."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()}
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["functional_groups"] == []


def test_build_config_fields_row_malformed_functional_group_entries_are_skipped():
    """Malformed catalog entries (non-mapping / missing key) are skipped, never raise.

    Well-formed entries survive; a partially authored entry fills safe defaults
    (``label`` → ``{}``, ``order`` → ``0``) so the row is always well-formed.
    """
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "functional_groups": [
                    "not-a-mapping",
                    {"label": {"nl": "Geen key"}},  # missing key → skipped
                    {"key": "motor"},  # partial → safe defaults
                ]
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    groups = item.attributes["functional_groups"]
    assert [g["key"] for g in groups] == ["motor"]
    assert groups[0]["label"] == {}
    assert groups[0]["order"] == 0


# --- Phase 2 step (a): default_page_size carried on config#fields -------------
# The per-context view_contexts.page_size re-homes to a single tenant-level
# members.default_page_size scalar, projected onto the EXISTING config#fields row
# (NOT a new config#views row) so the SAM reader can surface it on the
# field-config response. Only a positive int survives; anything else → None.


def test_build_config_fields_row_carries_field_scope_attribute():
    """Phase 3 step 9 (R2.1): a field's `scope` attribute is carried onto config#fields so the
    SAM read representation expresses scope-binding as a field attribute too."""
    params = FakeParameterService(
        {
            ("members", "field_overlay", "h-dcn"): {
                "fields": {
                    "region": {
                        "type": "enum",
                        "choices": ["Noord", "Zuid"],
                        "scope": {"enabled": True, "values": ["Noord", "Zuid"]},
                    }
                }
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    field = item.attributes["fields"]["region"]
    assert field["scope"] == {"enabled": True, "values": ["Noord", "Zuid"]}


def test_build_config_fields_row_non_scope_field_carries_none_scope():
    """A field with no scope attribute carries `scope: None` (not a scope axis)."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()}
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["fields"]["motor_type"]["scope"] is None


def test_build_config_fields_row_projects_authored_default_page_size():
    """An authored positive members.default_page_size is carried onto config#fields (R2.1)."""
    params = FakeParameterService(
        {("members", "default_page_size", "h-dcn"): 50}
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["default_page_size"] == 50
    # Carried verbatim onto the DynamoDB item under the config#fields row.
    dynamo = item.to_dynamodb_item()
    assert dynamo[schema.SORT_KEY_ATTR] == "config#fields"
    assert dynamo["default_page_size"] == 50


def test_build_config_fields_row_no_default_page_size_param_yields_none():
    """Empty-is-valid (R2.4): an un-authored default_page_size → None (platform fallback)."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()}
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert item.attributes["default_page_size"] is None


def test_build_config_fields_row_non_positive_or_malformed_default_page_size_yields_none():
    """A non-positive / non-int / boolean default_page_size collapses to None (read-side guard).

    The authoring validator (task 1.1) rejects a non-positive value at Save; this is the
    symmetric projection-side guard so a stray stored value never projects a zero/negative
    default that would violate the resolver's positive-int guarantee (R2.4).
    """
    for raw in (0, -5, "25", 3.5, True, False, [], {}, None):
        params = FakeParameterService(
            {("members", "default_page_size", "h-dcn"): raw}
        )
        item = build_config_fields_row({"administration": "h-dcn"}, params)
        assert item.attributes["default_page_size"] is None, f"raw={raw!r} must collapse to None"


def test_build_config_fields_row_versions_off_default_page_size_param_revision():
    """A default_page_size edit ALONE bumps config#fields' version (the trap fix, R2.1).

    config#fields is now driven by TWO params (field_overlay + default_page_size); an edit to
    EITHER must advance the row's version so the version-guarded conditional put WRITES it.
    Here only the default_page_size revision is newer than the tenant row.
    """
    params = FakeParameterService(
        params={("members", "default_page_size", "h-dcn"): 25},
        revisions={("members", "default_page_size", "h-dcn"): "2026-10-13T09:00:00"},
    )

    item = build_config_fields_row(
        {"administration": "h-dcn", "updated_at": "2026-01-01T00:00:00"}, params
    )

    assert item.version == "2026-10-13T09:00:00"


# --- Version-bump trap fix: config#* rows version off their SOURCE param ------
# (impact-analysis §0.3 / Phase 0 step 2). A members.* param edit alone must bump
# the relevant config row's version so the version-guarded conditional put WRITES
# the change instead of silently skipping it (written=0 skipped=N was the bug).


def test_build_config_fields_row_versions_off_param_revision_when_present():
    """A field_overlay edit alone bumps config#fields' version (the trap fix).

    The param's updated_at (get_param_revision) supersedes the tenant row's version:
    editing the overlay without touching the tenant row still produces a NEW version.
    """
    params = FakeParameterService(
        params={("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()},
        revisions={("members", "field_overlay", "h-dcn"): "2026-10-12T09:00:00"},
    )

    # Tenant row carries an OLD updated_at; the param revision is newer and wins.
    item = build_config_fields_row(
        {"administration": "h-dcn", "updated_at": "2026-01-01T00:00:00"}, params
    )

    assert item.version == "2026-10-12T09:00:00"


def test_build_config_scope_and_fields_version_off_their_source_params():
    """Each config row versions off ITS OWN source param set (Phase 3 step 9).

    After scope-as-field-attribute, config#scope is driven by BOTH field_overlay (the new
    authoring surface) AND scope_dimensions (the fallback source), so an edit to EITHER bumps
    it — the version is the MAX of their revisions. config#fields is driven by field_overlay
    (+ default_page_size). A scope_dimensions-only edit must NOT bump config#fields.
    """
    params = FakeParameterService(
        params={
            ("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()],
            ("members", "field_overlay", "h-dcn"): {"fields": {}, "fixed_overrides": {}},
        },
        revisions={
            ("members", "scope_dimensions", "h-dcn"): "2026-05-01T00:00:00",
            ("members", "field_overlay", "h-dcn"): "2026-06-01T00:00:00",
        },
    )
    tenant = {"administration": "h-dcn", "updated_at": "2026-01-01T00:00:00"}

    scope = build_config_scope_row(tenant, params)
    fields = build_config_fields_row(tenant, params)

    # config#scope: max(field_overlay=06-01, scope_dimensions=05-01) = 06-01.
    assert scope.version == "2026-06-01T00:00:00"
    # config#fields: driven by field_overlay (+ default_page_size) = 06-01.
    assert fields.version == "2026-06-01T00:00:00"


def test_build_config_scope_row_versions_off_scope_dimensions_edit_alone():
    """A scope_dimensions-only edit still bumps config#scope (the fallback source, R2.4)."""
    params = FakeParameterService(
        params={("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]},
        revisions={("members", "scope_dimensions", "h-dcn"): "2026-05-01T00:00:00"},
    )

    item = build_config_scope_row(
        {"administration": "h-dcn", "updated_at": "2026-01-01T00:00:00"}, params
    )

    assert item.version == "2026-05-01T00:00:00"


def test_build_config_mail_row_versions_off_max_of_four_param_revisions():
    """config#mail is driven by four params — an edit to ANY bumps the row (max wins)."""
    params = FakeParameterService(
        params={("members", "mail_enabled", "h-dcn"): True},
        revisions={
            ("members", "mail_enabled", "h-dcn"): "2026-02-01T00:00:00",
            # mail_certified was edited most recently → its revision must win.
            ("members", "mail_certified", "h-dcn"): "2026-09-01T00:00:00",
        },
    )

    item = build_config_mail_row(
        {"administration": "h-dcn", "updated_at": "2026-01-01T00:00:00"}, params
    )

    assert item.version == "2026-09-01T00:00:00"


def test_build_config_row_falls_back_to_tenant_version_without_param_revision():
    """No per-param revision authored → fall back to the tenant row version (unchanged)."""
    params = FakeParameterService(
        params={("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()},
        # No revisions registered → get_param_revision returns None for every key.
    )

    item = build_config_fields_row({"administration": "h-dcn", "version": 7}, params)

    assert item.version == 7


def test_sync_param_edit_alone_projects_the_change(sam_module):
    """End-to-end: a field_overlay edit with an UNCHANGED tenant row still writes.

    This is the exact #6/#7/#8 symptom the trap caused (written=0 skipped=N). After
    the fix, re-syncing with a newer param revision supersedes the stored config#fields
    version so the conditional put WRITES it — written>0 (impact-analysis acceptance).
    """
    table = FakeTable()
    params = FakeParameterService(
        params={("members", "field_overlay", "TenantA"): {"fields": {}}},
        revisions={("members", "field_overlay", "TenantA"): "2026-01-01T00:00:00"},
    )
    source = FakeSource({"TenantA": _tenant_source("TenantA", sam_module)})
    sync = ProjectionSync(source, table=table, parameter_service=params)

    sync.sync_administration("TenantA")
    fields_sk = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields")
    assert table.store[("TenantA", fields_sk)][schema.VERSION_ATTR] == "2026-01-01T00:00:00"

    # Edit the param ONLY (tenant row untouched): a newer param revision.
    params._revisions[("members", "field_overlay", "TenantA")] = "2026-10-12T12:00:00"
    result = sync.sync_administration("TenantA")

    # The edit propagated: config#fields was re-written with the newer version.
    assert table.store[("TenantA", fields_sk)][schema.VERSION_ATTR] == "2026-10-12T12:00:00"
    assert result.written >= 1


# --- C2 scopegrant#<email>#<dimension> builder (S5b design.md C2, R2.1/R2.2) ---


def _scope_params(dimensions, tenant="h-dcn"):
    """A FakeParameterService carrying the tenant's members.scope_dimensions list."""
    return FakeParameterService({("members", "scope_dimensions", tenant): dimensions})


def _scope_row(email, scopes, *, module="MEMBERS"):
    """A user_tenant_scope row — s5d's source (module + scopes JSON).

    ``scopes`` is passed as a JSON string here (the common MySQL-driver shape); the
    builder also accepts an already-parsed dict — covered by a dedicated test.
    """
    return {"email": email, "module": module, "scopes": json.dumps(scopes)}


def test_build_scopegrant_rows_all_access_sentinel_maps_to_wildcard():
    """An all-access grant (["*"]) → values ["*"] (R2.1)."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [_scope_row("boss@h-dcn.example", {"region": ["*"]})]

    items = build_scopegrant_rows({"administration": "h-dcn", "version": 7}, scope, params)

    assert len(items) == 1
    item = items[0]
    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "boss@h-dcn.example", "region"
    )
    assert item.version == 7
    # Row SHAPE unchanged (R2.5): {dimension, values} + version.
    assert item.attributes == {"dimension": "region", "values": ["*"]}
    dynamo = item.to_dynamodb_item()
    assert dynamo[schema.SORT_KEY_ATTR] == "scopegrant#boss@h-dcn.example#region"
    assert dynamo["values"] == ["*"]


def test_build_scopegrant_rows_single_value_grant_maps_to_that_value():
    """A single-value grant (["Noord"]) → values ["Noord"] (R2.1/R2.5)."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Noord"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    assert items[0].attributes == {"dimension": "region", "values": ["Noord"]}
    assert items[0].version == 0  # deterministic fallback when the row has no version


def test_build_scopegrant_rows_accepts_already_parsed_scopes_dict():
    """The scopes column may arrive already parsed (dict) — handled directly."""
    params = _scope_params([_hdcn_region_dimension()])
    # scopes as a dict, NOT a JSON string (some drivers deserialize JSON columns).
    scope = [{"email": "alice@h-dcn.example", "module": "MEMBERS",
              "scopes": {"region": ["Oost"]}}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    assert items[0].attributes == {"dimension": "region", "values": ["Oost"]}


def test_build_scopegrant_rows_multi_value_grant_in_declared_order():
    """A multi-value grant → the subset, in the dimension's declared value order."""
    params = _scope_params([_hdcn_region_dimension()])
    # Authored out of declared order — the builder re-orders to declared order.
    scope = [_scope_row("duo@h-dcn.example", {"region": ["West", "Noord"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    # Declared order is Noord, Zuid, Oost, West — so the subset preserves that order.
    assert items[0].attributes["values"] == ["Noord", "West"]


def test_build_scopegrant_rows_absent_dimension_yields_no_row():
    """Deny-by-default (R2.3): a user whose scopes omit the dimension → no row."""
    params = _scope_params([_hdcn_region_dimension()])
    # A scope record exists but carries no 'region' grant.
    scope = [_scope_row("plain@h-dcn.example", {"season": ["S1"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert items == []


def test_build_scopegrant_rows_empty_list_grant_yields_no_row():
    """Deny-by-default (R2.3): a dimension mapping to an empty list → no row."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [_scope_row("plain@h-dcn.example", {"region": []})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert items == []


def test_build_scopegrant_rows_unknown_value_dropped():
    """A granted value not in the dimension's declared values is dropped (R2.6)."""
    params = _scope_params([_hdcn_region_dimension()])
    # "Zuid" is declared; "Atlantis" is not — only "Zuid" survives.
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Zuid", "Atlantis"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    assert items[0].attributes == {"dimension": "region", "values": ["Zuid"]}


def test_build_scopegrant_rows_all_values_unknown_yields_no_row():
    """When every granted value is unknown, nothing survives → no row (deny, R2.3)."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Atlantis", "Narnia"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert items == []


def test_build_scopegrant_rows_value_matched_by_canonicalized_equality():
    """A grant value is validated by scope_canon equality (belt-and-suspenders, R9.6)."""
    params = _scope_params([_hdcn_region_dimension()])
    # Diacritic/case/separator variant of "Noord" still canonicalizes to the declared
    # value; the emitted value is the DECLARED spelling.
    scope = [_scope_row("alice@h-dcn.example", {"region": ["  nOORd  "]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    assert items[0].attributes == {"dimension": "region", "values": ["Noord"]}


def test_build_scopegrant_rows_multiple_users_and_dimensions():
    """One row per (user, dimension) with a grant, across users and dimensions."""
    season = {
        "key": "season",
        "enabled": True,
        "values": ["S1", "S2"],
    }
    params = _scope_params([_hdcn_region_dimension(), season])
    scope = [
        _scope_row("alice@h-dcn.example", {"region": ["Noord"], "season": ["S1"]}),
        _scope_row("boss@h-dcn.example", {"region": ["*"]}),
        _scope_row("nobody@h-dcn.example", {}),  # scope record but no grants
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    by_sk = {i.sort_key: i.attributes for i in items}
    assert by_sk[schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )] == {"dimension": "region", "values": ["Noord"]}
    assert by_sk[schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "season"
    )] == {"dimension": "season", "values": ["S1"]}
    assert by_sk[schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "boss@h-dcn.example", "region"
    )] == {"dimension": "region", "values": ["*"]}
    # nobody@ has a scope record but no grants → no rows.
    assert not any("nobody@h-dcn.example" in sk for sk in by_sk)


def test_build_scopegrant_rows_filters_to_members_module():
    """Only module='MEMBERS' rows are projected (the s5d slice)."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [
        _scope_row("alice@h-dcn.example", {"region": ["Noord"]}, module="EVENTS"),
        _scope_row("bob@h-dcn.example", {"region": ["Oost"]}, module="MEMBERS"),
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    assert items[0].sort_key == schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "bob@h-dcn.example", "region"
    )
    assert items[0].attributes == {"dimension": "region", "values": ["Oost"]}


def test_build_scopegrant_rows_no_dimensions_yields_empty():
    """Empty-is-valid: no authored scope_dimensions → nothing to grant."""
    params = FakeParameterService({})  # nothing authored
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Noord"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert items == []


def test_build_scopegrant_rows_no_scope_rows_yields_empty():
    """A tenant with dimensions but no scope rows → no grants."""
    params = _scope_params([_hdcn_region_dimension()])

    items = build_scopegrant_rows({"administration": "h-dcn"}, [], params)

    assert items == []


def test_build_scopegrant_rows_disabled_dimension_yields_no_row():
    """A disabled dimension is a tenant-wide no-op → no per-user grant row."""
    disabled = dict(_hdcn_region_dimension(), enabled=False)
    params = _scope_params([disabled])
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Noord"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert items == []


def test_build_scopegrant_rows_issues_zero_writes_and_reads_tenant_scope():
    """One-directional (Property 1): only a read of the tenant-scope param."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Noord"]})]

    build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert params.calls == [
        {"namespace": "members", "key": "scope_dimensions", "tenant": "h-dcn"}
    ]


def test_build_scopegrant_rows_missing_tenant_key_raises():
    """A tenant without administration/tenant_id is a cross-tenant hazard (R5.4)."""
    with pytest.raises(ValueError):
        build_scopegrant_rows({}, [], _scope_params([_hdcn_region_dimension()]))


def test_build_scopegrant_rows_malformed_scopes_json_row_is_skipped():
    """A row with malformed scopes JSON (or shape) is skipped, never raises."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [
        "not-a-mapping",
        {"email": "bad-json@h-dcn.example", "module": "MEMBERS",
         "scopes": "{not valid json"},        # unparseable string → skipped
        {"email": "bad-shape@h-dcn.example", "module": "MEMBERS",
         "scopes": "[\"region\"]"},           # valid JSON but not a dict → skipped
        {"module": "MEMBERS", "scopes": "{}"},  # missing email → skipped
        _scope_row("alice@h-dcn.example", {"region": ["Zuid"]}),  # well-formed
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert len(items) == 1
    assert items[0].sort_key == schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    assert items[0].attributes == {"dimension": "region", "values": ["Zuid"]}


def test_build_scopegrant_rows_non_list_param_treated_as_empty():
    """A malformed (non-list) authored dimensions value degrades to empty, never raises."""
    params = _scope_params("not-a-list")
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Noord"]})]

    items = build_scopegrant_rows({"administration": "h-dcn"}, scope, params)

    assert items == []


# --- sync_administration emits the S5b C2 rows alongside base rows (T6.1, R5.3/R5.5) ---


def _sam_source_with_scope(admin, module_name, *, roles=None, scope=None, tenant_version=1):
    """A SAM-backed TenantSource carrying a scoped user (for scopegrant emission)."""
    return TenantSource(
        tenant={"administration": admin, "display_name": f"{admin} Ltd", "version": tenant_version},
        tenant_modules=[
            {"module_name": module_name, "is_active": True, "version": 1}
        ],
        user_tenant_roles=roles or [],
        user_tenant_scope=scope or [],
    )


def test_sync_administration_sam_tenant_emits_config_and_scopegrant_rows(sam_module):
    """A SAM tenant with authored scope params + a scoped user gets base + C2 rows."""
    table = FakeTable()
    source = FakeSource(
        {
            "h-dcn": _sam_source_with_scope(
                "h-dcn",
                sam_module,
                roles=[
                    {"email": "alice@h-dcn.example", "role": "SamTest_Read"},
                ],
                scope=[
                    {"email": "alice@h-dcn.example", "module": "MEMBERS",
                     "scopes": json.dumps({"region": ["Noord"]})},
                ],
                tenant_version=7,
            )
        }
    )
    params = FakeParameterService(
        {
            ("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()],
            ("members", "field_overlay", "h-dcn"): _hdcn_field_overlay(),
        }
    )
    sync = ProjectionSync(source, table=table, parameter_service=params)

    result = sync.sync_administration("h-dcn")

    written = _items_in(table, "h-dcn")
    # Existing base rows still present.
    assert schema.build_sort_key(schema.RECORD_TYPE_TENANT) in written
    assert schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module) in written
    assert (
        schema.build_sort_key(schema.RECORD_TYPE_ROLE, "alice@h-dcn.example", "SamTest_Read")
        in written
    )
    # New C2 rows emitted alongside them.
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope") in written
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields") in written
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail") in written
    # Phase 2 (R5.3): the config#views row is no longer emitted.
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "views") not in written
    scopegrant_sk = schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    assert scopegrant_sk in written
    # The scoped user's user_tenant_scope region grant projects values ["Noord"].
    assert written[scopegrant_sk]["values"] == ["Noord"]
    # The config#scope row carries the authored region dimension.
    scope_sk = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope")
    assert written[scope_sk]["dimensions"][0]["key"] == "region"
    # tenant + module + 1 role + config#scope + config#fields +
    # config#mail + scopegrant = 7.
    assert result.written == 7


def test_sync_administration_non_sam_tenant_emits_no_c2_rows(sam_module):
    """A non-SAM tenant (no base items) emits no C2 rows either — writes nothing."""
    table = FakeTable()
    source = FakeSource(
        {
            "h-dcn": TenantSource(
                tenant={"administration": "h-dcn", "version": 1},
                tenant_modules=[],  # no SAM-backed module
                user_tenant_roles=[
                    {"email": "alice@h-dcn.example", "role": "Regio_Noord"}
                ],
            )
        }
    )
    # Even though scope params are authored, a non-SAM tenant projects nothing.
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    sync = ProjectionSync(source, table=table, parameter_service=params)

    result = sync.sync_administration("h-dcn")

    assert result.written == 0
    assert table.store == {}
    # The C2 builders were never invoked — no read of the members.* params.
    assert params.calls == []


def test_sync_administration_malformed_c2_item_aborts_before_any_write(sam_module, monkeypatch):
    """A malformed C2 item aborts the whole combined batch with no partial write (R5.5)."""
    import services.projection_sync as sync_module
    from services.projection_builder import ProjectionItem

    table = FakeTable()
    source = FakeSource(
        {
            "h-dcn": _sam_source_with_scope(
                "h-dcn",
                sam_module,
                roles=[{"email": "alice@h-dcn.example", "role": "SamTest_Read"}],
            )
        }
    )
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    sync = ProjectionSync(source, table=table, parameter_service=params)

    # Force the config#fields C2 builder to yield a malformed item (version=None,
    # which the validator rejects) so the combined batch fails validation.
    def _bad_fields(tenant, parameter_service):
        return ProjectionItem(
            tenant_id=tenant.get("administration"),
            sort_key=schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields"),
            version=None,  # malformed -> validator rejects
            attributes={"fields": {}, "overrides": {}},
        )

    monkeypatch.setattr(sync_module, "build_config_fields_row", _bad_fields)

    with pytest.raises(ProjectionValidationError):
        sync.sync_administration("h-dcn")

    # No partial write: neither the valid base rows nor the valid C2 rows landed.
    assert table.store == {}
    assert table.put_calls == []


# ═══════════════════════════════════════════════════════════════════════════════════════
# pivot-output-actions Task 0.4 — build_config_mail_row (the config#mail gate row).
#
# Feature: pivot-output-actions, R0 / design §6.3 (the mail-enabled gate, cross-plane READ).
# Validates: Requirements R0.
#
# The per-tenant "mail-enabled / SES-certified" flag is authored on the Flask plane as
# members.mail_enabled and projected as a config#mail row so the Members edge reads it via
# the projection reader (NO live MySQL at request time). These tests pin the Flask-plane
# builder: authored members.mail_enabled param -> config#mail row, FAIL-CLOSED default
# (absent/malformed -> False), one-directional (read-only), and the cross-tenant guard.
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_build_config_mail_row_true_flag_projects_enabled():
    """Authored members.mail_enabled=True → config#mail row with mail_enabled True (R0).

    The row ALWAYS carries the local-part (defaulting to ``noreply``) and the
    ``mail_certified`` gate (fail-closed False here, as none authored); ``mail_domain``
    is omitted when none authored (task 0.2 extended shape, design Data Models).
    """
    params = FakeParameterService(
        {("members", "mail_enabled", "h-dcn"): True}
    )

    item = build_config_mail_row({"administration": "h-dcn", "version": 7}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail")
    assert item.version == 7
    assert item.attributes == {
        "mail_enabled": True,
        "mail_local_part": "noreply",
        "mail_certified": False,
    }


def test_build_config_mail_row_false_flag_projects_disabled():
    """An explicit False flag projects a present-but-disabled gate (R0)."""
    params = FakeParameterService(
        {("members", "mail_enabled", "h-dcn"): False}
    )

    item = build_config_mail_row({"administration": "h-dcn"}, params)

    assert item.attributes == {
        "mail_enabled": False,
        "mail_local_part": "noreply",
        "mail_certified": False,
    }


def test_build_config_mail_row_projects_all_four_fields_into_single_row():
    """All four members.* params → the SINGLE config#mail row (R4; task 0.2).

    When mail_enabled, mail_domain, mail_local_part and mail_certified are all
    authored, the ONE config#mail row carries exactly those four attributes — the
    shape the SAM reader + pre-send resolver consume. The domain is projected as the
    bare domain (From is composed downstream, never projected as a literal address).
    """
    params = FakeParameterService(
        {
            ("members", "mail_enabled", "h-dcn"): True,
            ("members", "mail_domain", "h-dcn"): "h-dcn.nl",
            ("members", "mail_local_part", "h-dcn"): "info",
            ("members", "mail_certified", "h-dcn"): True,
        }
    )

    item = build_config_mail_row({"administration": "h-dcn", "version": 3}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail")
    assert item.version == 3
    assert item.attributes == {
        "mail_enabled": True,
        "mail_domain": "h-dcn.nl",
        "mail_local_part": "info",
        "mail_certified": True,
    }
    # The DynamoDB projection carries the canonical key attrs + the four fields.
    dynamo = item.to_dynamodb_item()
    assert dynamo[schema.PARTITION_KEY_ATTR] == "h-dcn"
    assert dynamo[schema.SORT_KEY_ATTR] == "config#mail"
    assert dynamo["mail_domain"] == "h-dcn.nl"
    assert dynamo["mail_local_part"] == "info"
    assert dynamo["mail_certified"] is True


def test_build_config_mail_row_local_part_defaults_to_noreply_when_unset_or_blank():
    """mail_local_part DEFAULTS to ``noreply`` when unset or blank (design Data Models)."""
    for raw in (None, "", "   " and "", 0, [], {}):
        params = FakeParameterService(
            {
                ("members", "mail_enabled", "h-dcn"): True,
                ("members", "mail_local_part", "h-dcn"): raw,
            }
        )
        item = build_config_mail_row({"administration": "h-dcn"}, params)
        assert item.attributes["mail_local_part"] == "noreply", (
            f"raw local_part={raw!r} must default to noreply"
        )


def test_build_config_mail_row_omits_domain_when_absent_or_blank():
    """No safe default for a domain (R4.2): absent/blank → mail_domain OMITTED.

    A guessed host would be a foreign-sender leak (the jabaki.nl regression). The
    reader resolves an absent domain to None and refuses the send (fail-closed).
    """
    for raw in (None, "", 123, [], {}):
        params = FakeParameterService(
            {
                ("members", "mail_enabled", "h-dcn"): True,
                ("members", "mail_domain", "h-dcn"): raw,
            }
        )
        item = build_config_mail_row({"administration": "h-dcn"}, params)
        assert "mail_domain" not in item.attributes, (
            f"raw domain={raw!r} must NOT project a mail_domain attribute"
        )


def test_build_config_mail_row_certified_fails_closed_to_false():
    """Fail-closed (R5.2): only an explicit boolean True certifies; else False.

    A stray truthy string, a number, or None must NEVER open the certification gate.
    """
    for raw in ("true", "True", 1, "yes", [], {}, None, False):
        params = FakeParameterService(
            {
                ("members", "mail_enabled", "h-dcn"): True,
                ("members", "mail_certified", "h-dcn"): raw,
            }
        )
        item = build_config_mail_row({"administration": "h-dcn"}, params)
        assert item.attributes["mail_certified"] is False, (
            f"raw certified={raw!r} must fail closed"
        )


def test_build_config_mail_row_no_param_fails_closed_to_false():
    """Fail-closed (R0): an un-configured tenant → disabled/uncertified, no raise."""
    params = FakeParameterService({})  # nothing authored

    item = build_config_mail_row({"administration": "h-dcn"}, params)

    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail")
    assert item.attributes == {
        "mail_enabled": False,
        "mail_local_part": "noreply",
        "mail_certified": False,
    }


def test_build_config_mail_row_malformed_values_fail_closed_to_false():
    """Fail-closed (R0): any non-boolean-True value collapses to False, never raises.

    A stray truthy string ("true"), a number (1), or None must NEVER silently open the
    gate — only an explicit boolean True enables sending.
    """
    for raw in ("true", "True", 1, "yes", [], {}, None):
        params = FakeParameterService(
            {("members", "mail_enabled", "h-dcn"): raw}
        )
        item = build_config_mail_row({"administration": "h-dcn"}, params)
        assert item.attributes["mail_enabled"] is False, (
            f"raw={raw!r} must fail closed"
        )


def test_build_config_mail_row_issues_zero_writes_and_reads_tenant_scope():
    """One-directional (Property 1): only tenant-scope READS of the members.* params.

    The builder reads each of the four mail params for this tenant and issues ZERO
    writes — never a cross-tenant or unscoped read.
    """
    params = FakeParameterService(
        {("members", "mail_enabled", "h-dcn"): True}
    )

    build_config_mail_row({"administration": "h-dcn"}, params)

    # Every call is a read scoped to THIS tenant on the members namespace — no write.
    assert len(params.calls) == 4
    read_keys = {call["key"] for call in params.calls}
    assert read_keys == {
        "mail_enabled",
        "mail_domain",
        "mail_local_part",
        "mail_certified",
    }
    for call in params.calls:
        assert call["namespace"] == "members"
        assert call["tenant"] == "h-dcn"


def test_build_config_mail_row_missing_tenant_key_raises():
    """A tenant without administration/tenant_id is a cross-tenant hazard (R5.4)."""
    with pytest.raises(ValueError):
        build_config_mail_row({}, FakeParameterService({}))


# ═══════════════════════════════════════════════════════════════════════════════════════
# S5d Task 3.4 — Freshness fix: scopegrant version bump (ODx4a).
#
# Feature: s5d-member-scope-assignment, design § "Projection invocation + freshness"
# (FRESHNESS HAZARD + ODx4a). Requirements 2.4; Properties P2/P3.
#
# The scopegrant#… rows are written under the sync's VERSION-GUARDED conditional put.
# Sourcing the row version from the TENANT row (as the sibling config#* rows do) meant a
# grant-only change (Oost → Oost+Friesland) did NOT bump the version, so the conditional
# put SKIPPED the updated row → the projection stayed STALE (a user keeps seeing members
# they were unscoped from). ODx4a derives the row version PER USER from the
# user_tenant_scope row's updated_at (ON UPDATE CURRENT_TIMESTAMP): it advances on a
# changed grant (supersede → written) and is stable on an unchanged re-sync (no-op →
# idempotent). These tests prove: (1) an UPDATED grant supersedes + is written; (2) an
# UNCHANGED re-sync is a no-op (no version churn); (3) a NEW grant still writes.
#
# The FakeTable enforces the same conditional-version semantics as production
# (attribute_not_exists(#v) OR #v < :incoming), so a stale version genuinely fails to
# write — the tests exercise the real hazard, not a mock of it.
# ═══════════════════════════════════════════════════════════════════════════════════════


def _scope_row_at(email, scopes, updated_at, *, module="MEMBERS"):
    """A user_tenant_scope row carrying an explicit ``updated_at`` freshness signal.

    ``updated_at`` is an ISO-8601 string here (the shape ``_normalize_version`` also
    produces from a MySQL ``datetime``); the builder normalizes it and the conditional
    put compares it lexicographically == chronologically.
    """
    return {
        "email": email,
        "module": module,
        "scopes": json.dumps(scopes),
        "updated_at": updated_at,
    }


# --- unit: build_scopegrant_rows derives the row version from updated_at ----


def test_build_scopegrant_rows_version_derived_from_updated_at():
    """The emitted row version is the row's ``updated_at`` (ODx4a), not the tenant version."""
    params = _scope_params([_hdcn_region_dimension()])
    scope = [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                           "2026-08-20T12:00:00")]

    # Tenant version is 7 — but the scopegrant row must carry the row's updated_at.
    items = build_scopegrant_rows({"administration": "h-dcn", "version": 7}, scope, params)

    assert len(items) == 1
    assert items[0].version == "2026-08-20T12:00:00"


def test_build_scopegrant_rows_changed_grant_yields_higher_version():
    """A CHANGED grant (later updated_at) yields a strictly-superseding version (ODx4a).

    Same SK (alice/region), changed values Oost → Oost+Friesland, later updated_at → the
    new version sorts strictly after the stored one, so the conditional put will write it.
    """
    dimension = dict(_hdcn_region_dimension(), values=["Oost", "Friesland", "Noord"])
    params = _scope_params([dimension])

    before = build_scopegrant_rows(
        {"administration": "h-dcn"},
        [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]}, "2026-08-20T12:00:00")],
        params,
    )
    after = build_scopegrant_rows(
        {"administration": "h-dcn"},
        [_scope_row_at("alice@h-dcn.example", {"region": ["Oost", "Friesland"]},
                       "2026-08-20T13:30:00")],
        params,
    )

    assert before[0].sort_key == after[0].sort_key  # same row (SK) — this is an UPDATE
    assert before[0].attributes["values"] == ["Oost"]
    assert after[0].attributes["values"] == ["Oost", "Friesland"]
    # The changed grant's version strictly supersedes the stored one.
    assert _supersedes(after[0].version, before[0].version)


def test_build_scopegrant_rows_unchanged_grant_reproduces_same_version():
    """An UNCHANGED re-sync reproduces the SAME version (idempotence, no churn)."""
    params = _scope_params([_hdcn_region_dimension()])
    row = _scope_row_at("alice@h-dcn.example", {"region": ["Oost"]}, "2026-08-20T12:00:00")

    first = build_scopegrant_rows({"administration": "h-dcn"}, [row], params)
    second = build_scopegrant_rows({"administration": "h-dcn"}, [dict(row)], params)

    assert first[0].version == second[0].version
    assert not _supersedes(second[0].version, first[0].version)  # equal → no supersede


def test_build_scopegrant_rows_falls_back_to_tenant_version_when_no_updated_at():
    """A row without ``updated_at`` falls back to the tenant config version (well-formed)."""
    params = _scope_params([_hdcn_region_dimension()])
    # No updated_at on the row (e.g. a legacy/fixture row) → tenant version 5.
    scope = [_scope_row("alice@h-dcn.example", {"region": ["Oost"]})]

    items = build_scopegrant_rows({"administration": "h-dcn", "version": 5}, scope, params)

    assert len(items) == 1
    assert items[0].version == 5


# --- integration through the sync + FakeTable conditional put ---------------


def _sam_source_with_scope_rows(admin, module_name, scope_rows, *, tenant_version=7):
    """A SAM-backed TenantSource carrying explicit scope rows (with updated_at)."""
    return TenantSource(
        tenant={"administration": admin, "display_name": f"{admin} Ltd",
                "version": tenant_version},
        tenant_modules=[{"module_name": module_name, "is_active": True, "version": 1}],
        user_tenant_roles=[{"email": "alice@h-dcn.example", "role": "SamTest_Read"}],
        user_tenant_scope=scope_rows,
    )


def test_sync_updated_grant_supersedes_stored_scopegrant_row(sam_module):
    """FRESHNESS BUG FIXED: an UPDATED grant is WRITTEN, not skipped (ODx4a, R2.4).

    Scope alice/region Oost, sync; then edit to Oost+Friesland with a LATER updated_at and
    re-sync. Without ODx4a the tenant version is unchanged, the conditional put skips the
    row, and the projection stays STALE (["Oost"]). With ODx4a the row's updated_at
    advances → the put supersedes → the projection reflects ["Oost", "Friesland"].
    """
    table = FakeTable()
    scope_sk = schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    region = dict(_hdcn_region_dimension(), values=["Oost", "Friesland", "Noord"])
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [region]}
    )

    sources = {
        "h-dcn": _sam_source_with_scope_rows(
            "h-dcn", sam_module,
            [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                           "2026-08-20T12:00:00")],
        )
    }
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)

    sync.sync_administration("h-dcn")
    assert _items_in(table, "h-dcn")[scope_sk]["values"] == ["Oost"]

    # Edit the grant (Oost → Oost+Friesland) with a LATER updated_at; tenant version
    # is UNCHANGED (still 7) — the pre-ODx4a hazard.
    sources["h-dcn"] = _sam_source_with_scope_rows(
        "h-dcn", sam_module,
        [_scope_row_at("alice@h-dcn.example", {"region": ["Oost", "Friesland"]},
                       "2026-08-20T13:30:00")],
    )
    result = sync.sync_administration("h-dcn")

    # The updated grant SUPERSEDED the stored row and was written (no longer stale).
    assert _items_in(table, "h-dcn")[scope_sk]["values"] == ["Oost", "Friesland"]
    assert result.written >= 1


def test_sync_unchanged_grant_resync_is_noop(sam_module):
    """An UNCHANGED re-sync writes NOTHING for the scopegrant row (idempotence preserved)."""
    table = FakeTable()
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    scope_rows = [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                                "2026-08-20T12:00:00")]
    source = FakeSource(
        {"h-dcn": _sam_source_with_scope_rows("h-dcn", sam_module, scope_rows)}
    )
    sync = ProjectionSync(source, table=table, parameter_service=params)

    first = sync.sync_administration("h-dcn")
    assert first.written > 0
    snapshot = {k: dict(v) for k, v in table.store.items()}

    # Re-run against the identical source — no version churn, no writes.
    second = sync.sync_administration("h-dcn")

    assert second.written == 0
    assert second.skipped == first.written
    assert {k: dict(v) for k, v in table.store.items()} == snapshot


def test_sync_new_grant_writes(sam_module):
    """A NEW grant (SK did not exist) still writes fine (add propagates)."""
    table = FakeTable()
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    # Start with no scope rows.
    sources = {"h-dcn": _sam_source_with_scope_rows("h-dcn", sam_module, [])}
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)

    sync.sync_administration("h-dcn")
    scope_sk = schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    assert scope_sk not in _items_in(table, "h-dcn")  # no grant yet

    # Grant alice a NEW region scope.
    sources["h-dcn"] = _sam_source_with_scope_rows(
        "h-dcn", sam_module,
        [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]}, "2026-08-20T14:00:00")],
    )
    result = sync.sync_administration("h-dcn")

    assert _items_in(table, "h-dcn")[scope_sk]["values"] == ["Oost"]
    assert result.written >= 1


# ═══════════════════════════════════════════════════════════════════════════════════════
# S5d Task 3.5 — Freshness fix: diff-and-delete obsolete scopegrant rows (ODx4b).
#
# Feature: s5d-member-scope-assignment, design § "Projection invocation + freshness"
# (ODx4b — DECIDED). Requirements 2.3/2.4; Properties P2/P3.
#
# The version bump (task 3.4, ODx4a) makes ADDS/UPDATES supersede, but a conditional put
# can NEVER delete a row. A REMOVED grant (user's scope cleared → deny) or a DOWNGRADED
# grant (a dimension dropped) leaves the OLD scopegrant#<email>#<dimension> row PRESENT in
# the projection, and deny-by-default enforcement then keeps honouring the stale grant —
# the user keeps seeing members they were unscoped from (SECURITY-relevant staleness). So
# after writing the DESIRED scopegrant rows, sync_administration reconciles the tenant's
# STORED scopegrant#… rows to that desired set, DELETING the obsolete ones. Confined to the
# scopegrant#… SK space (tenant-scoped query + delete); no other record type is touched.
#
# The FakeTable now implements query/delete_item with real-boto3 semantics (tenant-scoped
# begins_with query; delete at a key), so these tests exercise the real reconcile.
# ═══════════════════════════════════════════════════════════════════════════════════════


def _scopegrant_sk(email, dimension):
    return schema.build_sort_key(schema.RECORD_TYPE_SCOPEGRANT, email, dimension)


def _sam_source_multi_dim_scope(admin, module_name, scope_rows, *, roles=None,
                                tenant_version=7):
    """A SAM-backed TenantSource carrying explicit multi-dimension scope rows."""
    return TenantSource(
        tenant={"administration": admin, "display_name": f"{admin} Ltd",
                "version": tenant_version},
        tenant_modules=[{"module_name": module_name, "is_active": True, "version": 1}],
        user_tenant_roles=roles or [{"email": "alice@h-dcn.example",
                                     "role": "SamTest_Read"}],
        user_tenant_scope=scope_rows,
    )


def test_sync_cleared_grant_deletes_stale_scopegrant_row(sam_module):
    """A CLEARED grant (scope row gone) → its projected scopegrant row is DELETED (ODx4b).

    Without diff-and-delete the row would stay present and deny-by-default enforcement
    would keep honouring the stale grant — the user keeps seeing members they were
    unscoped from (SECURITY-relevant).
    """
    table = FakeTable()
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    sk = _scopegrant_sk("alice@h-dcn.example", "region")

    # 1) Alice is scoped to Oost → the row is projected.
    sources = {
        "h-dcn": _sam_source_multi_dim_scope(
            "h-dcn", sam_module,
            [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                           "2026-08-20T12:00:00")],
        )
    }
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)
    sync.sync_administration("h-dcn")
    assert sk in _items_in(table, "h-dcn")

    # 2) Alice's scope is CLEARED (her user_tenant_scope row is gone) → re-sync.
    sources["h-dcn"] = _sam_source_multi_dim_scope("h-dcn", sam_module, [])
    result = sync.sync_administration("h-dcn")

    # The stale scopegrant row is DELETED (not left present).
    assert sk not in _items_in(table, "h-dcn")
    assert result.deleted == 1


def test_sync_dropped_dimension_deletes_only_that_rows(sam_module):
    """A user who lost ONE dimension → only the dropped dimension's row is deleted (ODx4b).

    Retained dimensions' rows remain — the reconcile diffs to the desired SET, it does not
    wipe the user.
    """
    table = FakeTable()
    season = {"key": "season", "field": "season", "enabled": True,
              "values": ["S1", "S2"]}
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension(), season]}
    )
    region_sk = _scopegrant_sk("alice@h-dcn.example", "region")
    season_sk = _scopegrant_sk("alice@h-dcn.example", "season")

    # 1) Alice scoped on BOTH region + season.
    sources = {
        "h-dcn": _sam_source_multi_dim_scope(
            "h-dcn", sam_module,
            [_scope_row_at("alice@h-dcn.example",
                           {"region": ["Oost"], "season": ["S1"]},
                           "2026-08-20T12:00:00")],
        )
    }
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)
    sync.sync_administration("h-dcn")
    stored = _items_in(table, "h-dcn")
    assert region_sk in stored and season_sk in stored

    # 2) Alice DROPS season (keeps region) → re-sync.
    sources["h-dcn"] = _sam_source_multi_dim_scope(
        "h-dcn", sam_module,
        [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                       "2026-08-20T13:00:00")],
    )
    result = sync.sync_administration("h-dcn")

    stored = _items_in(table, "h-dcn")
    assert region_sk in stored          # retained dimension survives
    assert season_sk not in stored      # dropped dimension deleted
    assert result.deleted == 1


def test_sync_downgraded_grant_supersedes_and_does_not_delete_desired_row(sam_module):
    """A DOWNGRADED grant (Oost+Friesland → Oost) writes the superseding row AND keeps it.

    The still-desired scopegrant#…#region row must NOT be spuriously deleted by the
    reconcile (its SK is still in the desired set); only its values shrink (task 3.4
    supersede). This is the interaction of 3.4 (supersede) + 3.5 (diff-delete).
    """
    table = FakeTable()
    region = dict(_hdcn_region_dimension(), values=["Oost", "Friesland", "Noord"])
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [region]}
    )
    sk = _scopegrant_sk("alice@h-dcn.example", "region")

    # 1) Alice scoped Oost+Friesland.
    sources = {
        "h-dcn": _sam_source_multi_dim_scope(
            "h-dcn", sam_module,
            [_scope_row_at("alice@h-dcn.example", {"region": ["Oost", "Friesland"]},
                           "2026-08-20T12:00:00")],
        )
    }
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)
    sync.sync_administration("h-dcn")
    assert _items_in(table, "h-dcn")[sk]["values"] == ["Oost", "Friesland"]

    # 2) DOWNGRADE to Oost only (later updated_at) → re-sync.
    sources["h-dcn"] = _sam_source_multi_dim_scope(
        "h-dcn", sam_module,
        [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                       "2026-08-20T13:30:00")],
    )
    result = sync.sync_administration("h-dcn")

    stored = _items_in(table, "h-dcn")
    assert sk in stored                             # still-desired row NOT deleted
    assert stored[sk]["values"] == ["Oost"]         # superseded to the downgraded set
    assert result.deleted == 0                      # nothing obsolete for this tenant


def test_sync_reconcile_is_tenant_scoped_never_touches_other_tenant(sam_module):
    """Reconcile is tenant-scoped (Property 1/2): another tenant's scopegrant rows survive.

    Clearing TenantA's grant must delete ONLY TenantA's scopegrant row; TenantB's identical
    row is never queried, let alone deleted.
    """
    table = FakeTable()
    params = FakeParameterService(
        {
            ("members", "scope_dimensions", "TenantA"): [_hdcn_region_dimension()],
            ("members", "scope_dimensions", "TenantB"): [_hdcn_region_dimension()],
        }
    )
    a_sk = _scopegrant_sk("alice@h-dcn.example", "region")
    b_sk = _scopegrant_sk("bob@h-dcn.example", "region")

    sources = {
        "TenantA": _sam_source_multi_dim_scope(
            "TenantA", sam_module,
            [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                           "2026-08-20T12:00:00")],
            roles=[{"email": "alice@h-dcn.example", "role": "SamTest_Read"}],
        ),
        "TenantB": _sam_source_multi_dim_scope(
            "TenantB", sam_module,
            [_scope_row_at("bob@h-dcn.example", {"region": ["Oost"]},
                           "2026-08-20T12:00:00")],
            roles=[{"email": "bob@h-dcn.example", "role": "SamTest_Read"}],
        ),
    }
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)
    sync.sync_administration("TenantA")
    sync.sync_administration("TenantB")
    assert a_sk in _items_in(table, "TenantA")
    assert b_sk in _items_in(table, "TenantB")

    # Clear TenantA's grant only, then re-sync TenantA.
    sources["TenantA"] = _sam_source_multi_dim_scope(
        "TenantA", sam_module, [],
        roles=[{"email": "alice@h-dcn.example", "role": "SamTest_Read"}],
    )
    result = sync.sync_administration("TenantA")

    assert a_sk not in _items_in(table, "TenantA")  # TenantA's stale row deleted
    assert b_sk in _items_in(table, "TenantB")      # TenantB untouched
    assert result.deleted == 1
    # Every delete issued targeted TenantA's partition only (never TenantB's).
    assert all(
        key[schema.PARTITION_KEY_ATTR] == "TenantA" for key in table.delete_calls
    )


def test_sync_unchanged_resync_deletes_nothing_and_writes_nothing(sam_module):
    """An unchanged re-sync deletes nothing and writes nothing (idempotence preserved)."""
    table = FakeTable()
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    scope_rows = [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                                "2026-08-20T12:00:00")]
    sources = {"h-dcn": _sam_source_multi_dim_scope("h-dcn", sam_module, scope_rows)}
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)

    first = sync.sync_administration("h-dcn")
    assert first.written > 0
    snapshot = {k: dict(v) for k, v in table.store.items()}

    # Re-run against the identical source.
    second = sync.sync_administration("h-dcn")

    assert second.written == 0
    assert second.deleted == 0
    assert second.is_noop
    assert {k: dict(v) for k, v in table.store.items()} == snapshot


def test_sync_reconcile_never_deletes_non_scopegrant_rows(sam_module):
    """Non-scopegrant rows (tenant/module/role/config#*) are NEVER deleted by reconcile.

    Even when ALL scope grants are cleared, the tenant/module/role/config#* rows remain —
    the reconcile is confined to the scopegrant#… SK space (out-of-scope record types have
    their own lifecycle).
    """
    table = FakeTable()
    params = FakeParameterService(
        {
            ("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()],
            ("members", "field_overlay", "h-dcn"): _hdcn_field_overlay(),
        }
    )
    sources = {
        "h-dcn": _sam_source_multi_dim_scope(
            "h-dcn", sam_module,
            [_scope_row_at("alice@h-dcn.example", {"region": ["Oost"]},
                           "2026-08-20T12:00:00")],
        )
    }
    source = FakeSource(sources)
    sync = ProjectionSync(source, table=table, parameter_service=params)
    sync.sync_administration("h-dcn")

    non_scopegrant_before = {
        sk: dict(v)
        for sk, v in _items_in(table, "h-dcn").items()
        if not sk.startswith(schema.RECORD_TYPE_SCOPEGRANT + schema.SORT_KEY_SEPARATOR)
    }
    assert non_scopegrant_before  # sanity: there ARE non-scopegrant rows

    # Clear ALL scope grants → re-sync (the reconcile deletes the scopegrant row only).
    sources["h-dcn"] = _sam_source_multi_dim_scope("h-dcn", sam_module, [])
    sync.sync_administration("h-dcn")

    non_scopegrant_after = {
        sk: dict(v)
        for sk, v in _items_in(table, "h-dcn").items()
        if not sk.startswith(schema.RECORD_TYPE_SCOPEGRANT + schema.SORT_KEY_SEPARATOR)
    }
    # The non-scopegrant rows are untouched by the reconcile.
    assert set(non_scopegrant_after) == set(non_scopegrant_before)
    # No delete targeted a non-scopegrant SK.
    assert all(
        key[schema.SORT_KEY_ATTR].startswith(
            schema.RECORD_TYPE_SCOPEGRANT + schema.SORT_KEY_SEPARATOR
        )
        for key in table.delete_calls
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# S5d Task 3.3 / 7.1 — Role-decode REMOVAL (clean break, R2.2/R8.1; P1/P5).
#
# Feature: s5d-member-scope-assignment, design § "Projection: derive scopegrant from
# user_tenant_scope" item 4 (REMOVE) + "REUSE/ADD/REFACTOR/REMOVE" (projection_sync
# role-decode → REMOVE). Requirements 2.2/8.1; Properties P1 (single source of truth) /
# P5 (axis independence).
#
# s5d sources the scopegrant#…#<dimension> row from the user_tenant_scope table, NOT from
# decoding a Regio_* role name. The decode machinery is DELETED — the following helpers
# must no longer exist / be importable, and the scopegrant builder must IGNORE
# user_tenant_roles entirely (a Regio_* role can never produce a grant). These are the
# explicit removal assertions the 7.1 "role-decode removed" bullet requires (the rest of
# the s5d scopegrant coverage above proves the user_tenant_scope path positively; these
# nail the negative — that the OLD path is gone).
# ═══════════════════════════════════════════════════════════════════════════════════════

# The role-decode helpers deleted by the s5d clean break (design item 4 / task 3.3).
_REMOVED_ROLE_DECODE_HELPERS = (
    "_decode_grant_for_dimension",
    "_scoped_role_prefix",
    "_SCOPED_ROLE_SEPARATORS",
)


@pytest.mark.parametrize("removed_name", _REMOVED_ROLE_DECODE_HELPERS)
def test_projection_sync_role_decode_helper_no_longer_exists(removed_name):
    """The Regio_* role-decode helpers are DELETED — not attributes of the module (R2.2)."""
    import services.projection_sync as sync_module

    assert not hasattr(sync_module, removed_name), (
        f"{removed_name} must be removed by the s5d clean break (R2.2/R8.1) — scope is "
        "sourced from user_tenant_scope, not decoded from a role name"
    )


@pytest.mark.parametrize("removed_name", _REMOVED_ROLE_DECODE_HELPERS)
def test_projection_sync_role_decode_helper_not_importable(removed_name):
    """The removed helpers are not importable from services.projection_sync (R2.2)."""
    import services.projection_sync as sync_module

    with pytest.raises(AttributeError):
        getattr(sync_module, removed_name)()


def test_build_scopegrant_rows_signature_sources_user_tenant_scope_not_roles():
    """The builder's second positional param is the scope rows, not roles (R2.1/R2.2).

    The s5d rewrite changed the signature from (tenant, user_tenant_roles, param_svc) to
    (tenant, user_tenant_scope, param_svc). Pin the parameter name so a regression that
    re-introduces a role-sourced grant path is caught structurally.
    """
    import inspect

    params = list(inspect.signature(build_scopegrant_rows).parameters)
    assert params == ["tenant", "user_tenant_scope", "parameter_service"]


def test_build_scopegrant_rows_ignores_user_tenant_roles_regio_role():
    """A Regio_* role never produces a grant — the builder reads ONLY user_tenant_scope.

    Passing role rows in the scope-rows position (the shape the OLD role-decode path
    consumed) yields NO grant: a ``{email, role: "Regio_Noord"}`` row has no ``module`` /
    ``scopes``, so it is skipped like any malformed row. Grants come exclusively from
    ``user_tenant_scope`` (R2.2, clean break; P1 single-source, P5 axis independence).
    """
    params = _scope_params([_hdcn_region_dimension()])
    # The retired role-decode input: user_tenant_roles rows carrying a Regio_* role.
    role_rows = [
        {"email": "alice@h-dcn.example", "role": "Regio_Noord"},
        {"email": "boss@h-dcn.example", "role": "Regio_*"},
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, role_rows, params)

    # No Regio_* role is decoded into a grant — the old path is gone.
    assert items == []


def test_build_scopegrant_rows_grant_comes_from_scope_not_role_for_same_user(sam_module):
    """A user holding a Regio_* role but NO scope row gets NO grant (axis independence, P5).

    Even end-to-end through the sync: alice holds a legacy ``Regio_Noord`` role
    (capability axis) but has no ``user_tenant_scope`` row (scope axis). No
    scopegrant#…#region row is projected — the role does not leak into scope.
    """
    table = FakeTable()
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )
    source = FakeSource(
        {
            "h-dcn": TenantSource(
                tenant={"administration": "h-dcn", "display_name": "h-dcn Ltd",
                        "version": 7},
                tenant_modules=[
                    {"module_name": sam_module, "is_active": True, "version": 1}
                ],
                # Capability role only — NO user_tenant_scope grant.
                user_tenant_roles=[
                    {"email": "alice@h-dcn.example", "role": "Regio_Noord"},
                    {"email": "alice@h-dcn.example", "role": "SamTest_Read"},
                ],
                user_tenant_scope=[],
            )
        }
    )
    sync = ProjectionSync(source, table=table, parameter_service=params)

    sync.sync_administration("h-dcn")

    scope_sk = schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    written = _items_in(table, "h-dcn")
    # No scopegrant row from the Regio_* role — scope only comes from user_tenant_scope.
    assert scope_sk not in written
    # But the capability role IS still projected (roles axis untouched — P5).
    assert schema.build_sort_key(
        schema.RECORD_TYPE_ROLE, "alice@h-dcn.example", "SamTest_Read"
    ) in written
