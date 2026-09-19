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
    build_config_fields_row,
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
    # + the two always-present S5b C2 config rows (empty when un-configured, R1.6/R1.7):
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope") in written
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields") in written
    # tenant + module + role + config#scope + config#fields = 5 (no scopegrant: no
    # scope_dimensions authored in the empty FakeParameterService).
    assert result.written == 5
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

    def __init__(self, params: dict[tuple, object] | None = None):
        self._params = params or {}
        self.calls: list[dict] = []

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        self.calls.append(
            {"namespace": namespace, "key": key, "tenant": tenant}
        )
        return self._params.get((namespace, key, tenant))


def _hdcn_region_dimension():
    """The h-dcn region dimension as authored tenant-scope parameter data."""
    return {
        "key": "region",
        "label": {"nl": "Regio", "en": "Region"},
        "enabled": True,
        "multi_valued": False,
        "values": ["Noord", "Zuid", "Oost", "West"],
        "all_wildcard": "Regio_All",
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
    assert dim["multi_valued"] is False
    assert dim["values"] == []
    assert dim["label"] == {}
    assert dim["all_wildcard"] is None
    assert dim["required_for"] == []


def test_build_config_scope_row_issues_zero_writes_and_reads_tenant_scope():
    """One-directional (Property 1): only a read of the tenant-scope param."""
    params = FakeParameterService(
        {("members", "scope_dimensions", "h-dcn"): [_hdcn_region_dimension()]}
    )

    build_config_scope_row({"administration": "h-dcn"}, params)

    # Exactly one read, scoped to this tenant's members.scope_dimensions param.
    assert params.calls == [
        {"namespace": "members", "key": "scope_dimensions", "tenant": "h-dcn"}
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
        "overrides": {
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
    """One-directional (Property 1): only a read of the tenant-scope param."""
    params = FakeParameterService(
        {("members", "field_overlay", "h-dcn"): _hdcn_field_overlay()}
    )

    build_config_fields_row({"administration": "h-dcn"}, params)

    # Exactly one read, scoped to this tenant's members.field_overlay param.
    assert params.calls == [
        {"namespace": "members", "key": "field_overlay", "tenant": "h-dcn"}
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
                "overrides": {"personal.name": "nope", "personal.email": {"order": 2}},
            }
        }
    )

    item = build_config_fields_row({"administration": "h-dcn"}, params)

    assert set(item.attributes["fields"]) == {"motor_type"}
    assert set(item.attributes["overrides"]) == {"personal.email"}


# --- C2 scopegrant#<email>#<dimension> builder (S5b design.md C2, R2.1/R2.2) ---


def _scope_params(dimensions, tenant="h-dcn"):
    """A FakeParameterService carrying the tenant's members.scope_dimensions list."""
    return FakeParameterService({("members", "scope_dimensions", tenant): dimensions})


def test_build_scopegrant_rows_all_access_role_maps_to_wildcard():
    """An all-access (all_wildcard) role → values ["*"] (R2.4)."""
    params = _scope_params([_hdcn_region_dimension()])
    roles = [{"email": "boss@h-dcn.example", "role": "Regio_All"}]

    items = build_scopegrant_rows({"administration": "h-dcn", "version": 7}, roles, params)

    assert len(items) == 1
    item = items[0]
    assert item.tenant_id == "h-dcn"
    assert item.sort_key == schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "boss@h-dcn.example", "region"
    )
    assert item.version == 7
    assert item.attributes == {"dimension": "region", "values": ["*"]}
    dynamo = item.to_dynamodb_item()
    assert dynamo[schema.SORT_KEY_ATTR] == "scopegrant#boss@h-dcn.example#region"
    assert dynamo["values"] == ["*"]


def test_build_scopegrant_rows_subgroup_role_maps_to_that_value():
    """A subgroup-scoped role (Regio_Noord) → values ["Noord"] (R2.5)."""
    params = _scope_params([_hdcn_region_dimension()])
    roles = [{"email": "alice@h-dcn.example", "role": "Regio_Noord"}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert len(items) == 1
    assert items[0].attributes == {"dimension": "region", "values": ["Noord"]}
    assert items[0].version == 0  # deterministic fallback when the row has no version


def test_build_scopegrant_rows_bare_value_role_is_honoured():
    """A role named exactly after the value ("Noord") also grants that value."""
    params = _scope_params([_hdcn_region_dimension()])
    roles = [{"email": "alice@h-dcn.example", "role": "Noord"}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert items[0].attributes == {"dimension": "region", "values": ["Noord"]}


def test_build_scopegrant_rows_multi_valued_user_unions_grants_in_declared_order():
    """Multiple scoped roles for one user → the union subset, in declared order."""
    params = _scope_params([_hdcn_region_dimension()])
    roles = [
        {"email": "duo@h-dcn.example", "role": "Regio_West"},
        {"email": "duo@h-dcn.example", "role": "Regio_Noord"},
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert len(items) == 1
    # Declared order is Noord, Zuid, Oost, West — so the union preserves that order.
    assert items[0].attributes["values"] == ["Noord", "West"]


def test_build_scopegrant_rows_no_grant_user_yields_no_row():
    """Deny-by-default (R2.6): a user with no scope-granting role → no row."""
    params = _scope_params([_hdcn_region_dimension()])
    # Bare Members_CRUD without any Regio_* — a required_for capability, no grant.
    roles = [{"email": "plain@h-dcn.example", "role": "Members_CRUD"}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert items == []


def test_build_scopegrant_rows_multiple_users_and_dimensions():
    """One row per (user, dimension) with a grant, across users and dimensions."""
    season = {
        "key": "season",
        "enabled": True,
        "values": ["S1", "S2"],
        "all_wildcard": "Season_All",
    }
    params = _scope_params([_hdcn_region_dimension(), season])
    roles = [
        {"email": "alice@h-dcn.example", "role": "Regio_Noord"},
        {"email": "alice@h-dcn.example", "role": "Season_S1"},
        {"email": "boss@h-dcn.example", "role": "Regio_All"},
        {"email": "nobody@h-dcn.example", "role": "Members_Read"},
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

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
    # nobody@ holds no scope-granting role in any dimension → no rows.
    assert not any("nobody@h-dcn.example" in sk for sk in by_sk)


def test_build_scopegrant_rows_no_dimensions_yields_empty():
    """Empty-is-valid: no authored scope_dimensions → nothing to grant."""
    params = FakeParameterService({})  # nothing authored
    roles = [{"email": "alice@h-dcn.example", "role": "Regio_Noord"}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert items == []


def test_build_scopegrant_rows_no_roles_yields_empty():
    """A tenant with dimensions but no role assignments → no grants."""
    params = _scope_params([_hdcn_region_dimension()])

    items = build_scopegrant_rows({"administration": "h-dcn"}, [], params)

    assert items == []


def test_build_scopegrant_rows_disabled_dimension_yields_no_row():
    """A disabled dimension is a tenant-wide no-op → no per-user grant row."""
    disabled = dict(_hdcn_region_dimension(), enabled=False)
    params = _scope_params([disabled])
    roles = [{"email": "alice@h-dcn.example", "role": "Regio_Noord"}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert items == []


def test_build_scopegrant_rows_issues_zero_writes_and_reads_tenant_scope():
    """One-directional (Property 1): only a read of the tenant-scope param."""
    params = _scope_params([_hdcn_region_dimension()])
    roles = [{"email": "alice@h-dcn.example", "role": "Regio_Noord"}]

    build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert params.calls == [
        {"namespace": "members", "key": "scope_dimensions", "tenant": "h-dcn"}
    ]


def test_build_scopegrant_rows_missing_tenant_key_raises():
    """A tenant without administration/tenant_id is a cross-tenant hazard (R5.4)."""
    with pytest.raises(ValueError):
        build_scopegrant_rows({}, [], _scope_params([_hdcn_region_dimension()]))


def test_build_scopegrant_rows_malformed_role_rows_are_skipped():
    """A malformed role row (missing email/role, non-mapping) is skipped, never raises."""
    params = _scope_params([_hdcn_region_dimension()])
    roles = [
        "not-a-mapping",
        {"role": "Regio_Noord"},  # missing email
        {"email": "x@h-dcn.example"},  # missing role
        {"email": "alice@h-dcn.example", "role": "Regio_Zuid"},  # well-formed
    ]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert len(items) == 1
    assert items[0].attributes == {"dimension": "region", "values": ["Zuid"]}


def test_build_scopegrant_rows_non_list_param_treated_as_empty():
    """A malformed (non-list) authored dimensions value degrades to empty, never raises."""
    params = _scope_params("not-a-list")
    roles = [{"email": "alice@h-dcn.example", "role": "Regio_Noord"}]

    items = build_scopegrant_rows({"administration": "h-dcn"}, roles, params)

    assert items == []


# --- sync_administration emits the S5b C2 rows alongside base rows (T6.1, R5.3/R5.5) ---


def _sam_source_with_scope(admin, module_name, *, roles=None, tenant_version=1):
    """A SAM-backed TenantSource carrying a scoped user (for scopegrant emission)."""
    return TenantSource(
        tenant={"administration": admin, "display_name": f"{admin} Ltd", "version": tenant_version},
        tenant_modules=[
            {"module_name": module_name, "is_active": True, "version": 1}
        ],
        user_tenant_roles=roles or [],
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
                    {"email": "alice@h-dcn.example", "role": "Regio_Noord"},
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
        schema.build_sort_key(schema.RECORD_TYPE_ROLE, "alice@h-dcn.example", "Regio_Noord")
        in written
    )
    # New S5b C2 rows emitted alongside them.
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope") in written
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields") in written
    scopegrant_sk = schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    assert scopegrant_sk in written
    # The scoped user's Regio_Noord grant decodes to values ["Noord"].
    assert written[scopegrant_sk]["values"] == ["Noord"]
    # The config#scope row carries the authored region dimension.
    scope_sk = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope")
    assert written[scope_sk]["dimensions"][0]["key"] == "region"
    # tenant + module + 2 roles + config#scope + config#fields + scopegrant = 7.
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
