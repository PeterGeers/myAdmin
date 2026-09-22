"""Unit tests for the pure S3 governance projection item builder (T12, R5.3).

Covers the tenant-level projection rules from design.md D3 "What is projected":
the SAM-backed-module gate, the tenant/module/role item shapes, version
attachment, and the guarantee that no per-user token-only (S4) data is emitted.

The builder is pure (no I/O), so these are plain in-memory example tests — no
DB/DynamoDB mocks needed. A temporary SAM-backed module is injected into
MODULE_REGISTRY per test via monkeypatch (mirroring test_module_registry.py) so
the gate has something to fire on without touching the shipped registry.

Feature: s3-claims-and-projection
"""

import pytest

from services import projection_schema as schema
from services.module_registry import MODULE_REGISTRY
from services.projection_builder import (
    ProjectionItem,
    build_projection_items,
)

# Temporary SAM-backed module name — kept test-local so it never collides with a
# real registry module or leaks between tests (monkeypatch.setitem restores).
_SAM_MODULE_NAME = "SAM_TEST_MODULE"


@pytest.fixture
def sam_module(monkeypatch):
    """Inject a temporary SAM-backed module into MODULE_REGISTRY for one test."""
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


def _sk_of(item: ProjectionItem) -> str:
    return item.sort_key


# --- gate: only SAM-backed-enabled tenants are projected (R5.3) -------------


def test_build_empty_tenant_no_modules_returns_no_items():
    # A tenant with no modules has no SAM-backed module -> nothing projected.
    assert build_projection_items({"administration": "TenantA"}) == []


def test_build_tenant_with_only_flask_modules_returns_no_items():
    # FIN/STR/TENADMIN/ZZP are all flask-backed: the projection serves the SAM
    # module plane only, so a flask-only tenant is not projected.
    modules = [
        {"module_name": "FIN", "is_active": True},
        {"module_name": "STR", "is_active": True},
    ]
    assert build_projection_items({"administration": "TenantA"}, modules) == []


def test_build_tenant_with_inactive_sam_module_returns_no_items(sam_module):
    # A SAM-backed module that is present but NOT active does not open the gate.
    modules = [{"module_name": sam_module, "is_active": False}]
    assert build_projection_items({"administration": "TenantA"}, modules) == []


def test_build_tenant_with_active_sam_module_is_projected(sam_module):
    modules = [{"module_name": sam_module, "is_active": True}]
    items = build_projection_items({"administration": "TenantA"}, modules)
    assert items, "an active SAM-backed module must open the projection gate"


# --- R8.6: reconciliation tolerates unknown/legacy module rows -------------
#
# The periodic backstop (sync_all) sweeps EVERY tenant's tenant_modules rows,
# and dev MySQL legitimately carries other tenants' unregistered/legacy names
# (e.g. 'ADMIN', lowercase 'members'/'events'/'webshop'). One such row must NOT
# raise and abort the sweep; it is treated as NON-SAM-backed (skipped).


def test_build_tenant_with_only_unknown_module_returns_no_items_no_raise():
    # A tenant whose ONLY active module is unregistered/legacy projects nothing —
    # exactly like a flask-only tenant — and does NOT raise (R8.6).
    modules = [{"module_name": "ADMIN", "is_active": True}]
    assert build_projection_items({"administration": "myAdmin"}, modules) == []


def test_build_tenant_with_lowercase_unknown_module_returns_no_items():
    # s3test_hdcn's lowercase 'members' is NOT the registered 'MEMBERS' — unknown.
    modules = [
        {"module_name": "members", "is_active": True},
        {"module_name": "events", "is_active": True},
        {"module_name": "webshop", "is_active": True},
    ]
    assert build_projection_items({"administration": "s3test_hdcn"}, modules) == []


def test_build_known_sam_plus_unknown_module_projects_known_without_raise(sam_module):
    # A Members-enabled tenant that ALSO carries an unknown/legacy module row
    # still projects its known rows; the unknown row is skipped, not raised.
    tenant = {"administration": "TenantA"}
    modules = [
        {"module_name": sam_module, "is_active": True},
        {"module_name": "ADMIN", "is_active": True},  # unknown/legacy — skipped
    ]

    items = build_projection_items(tenant, modules)

    module_sks = {i.sort_key for i in items if i.sort_key.startswith("module#")}
    # The known SAM module IS emitted; the unknown 'ADMIN' module is NOT.
    assert schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module) in module_sks
    assert schema.build_sort_key(schema.RECORD_TYPE_MODULE, "ADMIN") not in module_sks
    # The tenant record is still projected (tenant is eligible via the SAM module).
    assert any(i.sort_key == "tenant" for i in items)


def test_build_known_flask_plus_unknown_module_still_not_projected():
    # An unknown module does not grant projection: a tenant with only a flask
    # module + an unknown one still projects nothing (unknown is skipped, the
    # flask module does not open the gate).
    modules = [
        {"module_name": "FIN", "is_active": True},
        {"module_name": "ADMIN", "is_active": True},
    ]
    assert build_projection_items({"administration": "TenantA"}, modules) == []


# --- tenant item ------------------------------------------------------------


def test_build_emits_single_tenant_record_with_tenant_attrs(sam_module):
    tenant = {"administration": "TenantA", "display_name": "Tenant A", "country": "NL"}
    modules = [{"module_name": sam_module, "is_active": True}]

    items = build_projection_items(tenant, modules)

    tenant_items = [i for i in items if _sk_of(i) == "tenant"]
    assert len(tenant_items) == 1
    ti = tenant_items[0]
    assert ti.tenant_id == "TenantA"
    # tenant-level attributes travel with the item; key fields are excluded.
    assert ti.attributes == {"display_name": "Tenant A", "country": "NL"}


def test_build_all_items_share_the_tenant_partition_key(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [{"module_name": sam_module, "is_active": True}]
    roles = [{"email": "a@b.example", "role": "SamTest_Read"}]

    items = build_projection_items(tenant, modules, roles)

    assert items and all(i.tenant_id == "TenantA" for i in items)


def test_build_tenant_missing_key_raises(sam_module):
    modules = [{"module_name": sam_module, "is_active": True}]
    with pytest.raises(ValueError, match="cross-tenant hazard"):
        build_projection_items({"display_name": "no key"}, modules)


# --- module items -----------------------------------------------------------


def test_build_emits_module_item_per_module_row(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [
        {"module_name": sam_module, "is_active": True},
        {"module_name": "FIN", "is_active": True},
    ]

    items = build_projection_items(tenant, modules)

    module_sks = {_sk_of(i) for i in items if i.sort_key.startswith("module#")}
    assert module_sks == {
        schema.build_sort_key(schema.RECORD_TYPE_MODULE, sam_module),
        schema.build_sort_key(schema.RECORD_TYPE_MODULE, "FIN"),
    }


def test_build_module_item_carries_is_active_bool(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [
        {"module_name": sam_module, "is_active": True},
        {"module_name": "FIN", "is_active": False},
    ]

    items = build_projection_items(tenant, modules)
    by_sk = {i.sort_key: i for i in items}

    assert by_sk[f"module#{sam_module}"].attributes == {"is_active": True}
    assert by_sk["module#FIN"].attributes == {"is_active": False}


def test_build_module_row_missing_name_raises(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [
        {"module_name": sam_module, "is_active": True},
        {"is_active": True},  # missing module_name
    ]
    with pytest.raises(ValueError, match="module_name"):
        build_projection_items(tenant, modules)


# --- role items -------------------------------------------------------------


def test_build_emits_role_item_per_role_grant(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [{"module_name": sam_module, "is_active": True}]
    roles = [
        {"email": "alice@example.invalid", "role": "SamTest_Read"},
        {"email": "bob@example.invalid", "role": "Finance_CRUD"},
    ]

    items = build_projection_items(tenant, modules, roles)

    role_items = {i.sort_key: i for i in items if i.sort_key.startswith("role#")}
    assert set(role_items) == {
        schema.build_sort_key(schema.RECORD_TYPE_ROLE, "alice@example.invalid", "SamTest_Read"),
        schema.build_sort_key(schema.RECORD_TYPE_ROLE, "bob@example.invalid", "Finance_CRUD"),
    }
    # role rows mirror (email, role) verbatim — tenant-level reference data.
    alice = role_items["role#alice@example.invalid#SamTest_Read"]
    assert alice.attributes == {"email": "alice@example.invalid", "role": "SamTest_Read"}


def test_build_role_row_missing_email_or_role_raises(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [{"module_name": sam_module, "is_active": True}]
    roles = [{"email": "alice@example.invalid"}]  # missing role
    with pytest.raises(ValueError, match="email'/'role"):
        build_projection_items(tenant, modules, roles)


def test_build_no_token_only_resolved_data_projected(sam_module):
    # S4 (per-user resolved answer) must NOT appear here. The builder mirrors the
    # tenant's role-assignment rows as reference data; it never emits a resolved
    # permission set / decision item. Assert no attribute leaks a resolved answer
    # and role items keep exactly the source (email, role) shape.
    tenant = {"administration": "TenantA"}
    modules = [{"module_name": sam_module, "is_active": True}]
    roles = [{"email": "alice@example.invalid", "role": "SamTest_Read"}]

    items = build_projection_items(tenant, modules, roles)

    forbidden = {"permissions", "resolved", "effective_permissions", "decision", "capabilities"}
    for item in items:
        assert forbidden.isdisjoint(item.attributes.keys()), (
            f"token-only (S4) data leaked into projection: {item.attributes!r}"
        )
    role_items = [i for i in items if i.sort_key.startswith("role#")]
    for ri in role_items:
        assert set(ri.attributes) == {"email", "role"}


# --- version attachment (R5.6) ----------------------------------------------


def test_build_version_read_from_source_row(sam_module):
    tenant = {"administration": "TenantA", "version": 7}
    modules = [{"module_name": sam_module, "is_active": True, "version": 3}]
    roles = [{"email": "a@b.example", "role": "SamTest_Read", "version": 5}]

    items = build_projection_items(tenant, modules, roles)
    by_sk = {i.sort_key: i for i in items}

    assert by_sk["tenant"].version == 7
    assert by_sk[f"module#{sam_module}"].version == 3
    assert by_sk["role#a@b.example#SamTest_Read"].version == 5


def test_build_version_falls_back_to_updated_at(sam_module):
    tenant = {"administration": "TenantA", "updated_at": "2026-01-01T00:00:00Z"}
    modules = [{"module_name": sam_module, "is_active": True}]

    items = build_projection_items(tenant, modules)
    tenant_item = next(i for i in items if i.sort_key == "tenant")

    assert tenant_item.version == "2026-01-01T00:00:00Z"


def test_build_version_default_when_absent_is_deterministic(sam_module):
    tenant = {"administration": "TenantA"}
    modules = [{"module_name": sam_module, "is_active": True}]

    items_a = build_projection_items(tenant, modules)
    items_b = build_projection_items(tenant, modules)

    # No version field -> deterministic fallback; two runs are identical (idempotent).
    assert all(i.version == 0 for i in items_a)
    assert items_a == items_b


# --- to_dynamodb_item shape -------------------------------------------------


def test_to_dynamodb_item_uses_canonical_attr_names(sam_module):
    tenant = {"administration": "TenantA", "version": 2, "display_name": "A"}
    modules = [{"module_name": sam_module, "is_active": True}]

    items = build_projection_items(tenant, modules)
    tenant_item = next(i for i in items if i.sort_key == "tenant")
    ddb = tenant_item.to_dynamodb_item()

    assert ddb[schema.PARTITION_KEY_ATTR] == "TenantA"
    assert ddb[schema.SORT_KEY_ATTR] == "tenant"
    assert ddb[schema.VERSION_ATTR] == 2
    assert ddb["display_name"] == "A"
