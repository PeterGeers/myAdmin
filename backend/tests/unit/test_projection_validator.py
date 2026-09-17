"""Unit tests for the S3 governance projection write-time validator (T14, R5.5).

Covers design.md D3 "Write-time validation (R5.5)": an item is valid iff its
tenant key is present, its sort key is well-formed, its version is present, and
its required fields are well-formed. Invalid -> raise
``ProjectionValidationError``, do not write. The rest (a valid batch) is
unaffected.

The validator is pure (no I/O), so these are plain in-memory example tests — no
DB/DynamoDB mocks needed. Items are constructed via the T12
``ProjectionItem`` builder / directly, then fed to the validator. Property 5
(over generated inputs) lands in T15; these are the concrete examples that pin
the behaviour.

Feature: s3-claims-and-projection
"""

import pytest

from services import projection_schema as schema
from services.projection_builder import ProjectionItem
from services.projection_validator import (
    ProjectionValidationError,
    is_valid_item,
    validate_item,
    validate_items,
)


def _tenant_item(tenant_id="TenantA", version=1, attrs=None):
    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_TENANT),
        version=version,
        attributes=attrs or {"display_name": "Tenant A"},
    )


def _module_item(tenant_id="TenantA", name="SAM_TEST_MODULE", is_active=True, version=1):
    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_MODULE, name),
        version=version,
        attributes={"is_active": is_active},
    )


def _role_item(tenant_id="TenantA", email="a@b.example", role="SamTest_Read", version=1):
    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_ROLE, email, role),
        version=version,
        attributes={"email": email, "role": role},
    )


# --- valid items pass -------------------------------------------------------


def test_validate_item_valid_tenant_item_returns_item():
    item = _tenant_item()
    assert validate_item(item) is item
    assert is_valid_item(item) is True


def test_validate_item_valid_module_item_returns_item():
    item = _module_item()
    assert validate_item(item) is item
    assert is_valid_item(item) is True


def test_validate_item_valid_role_item_returns_item():
    item = _role_item()
    assert validate_item(item) is item
    assert is_valid_item(item) is True


# --- missing tenant key raises (the primary R5.5/R5.4 hazard) ---------------


def test_validate_item_missing_tenant_key_raises():
    item = _tenant_item(tenant_id="")
    with pytest.raises(ProjectionValidationError, match="tenant key"):
        validate_item(item)
    assert is_valid_item(item) is False


def test_validate_item_blank_whitespace_tenant_key_raises():
    item = _tenant_item(tenant_id="   ")
    with pytest.raises(ProjectionValidationError, match="tenant key"):
        validate_item(item)


def test_validate_item_none_tenant_key_raises():
    item = _tenant_item(tenant_id=None)
    with pytest.raises(ProjectionValidationError, match="tenant key"):
        validate_item(item)


# --- missing / malformed sort key raises ------------------------------------


def test_validate_item_missing_sort_key_raises():
    item = ProjectionItem(tenant_id="TenantA", sort_key="", version=1, attributes={})
    with pytest.raises(ProjectionValidationError, match="sort key"):
        validate_item(item)


def test_validate_item_module_sort_key_without_id_segment_raises():
    # "module" alone is not a well-formed module key — it needs the module name.
    item = ProjectionItem(
        tenant_id="TenantA",
        sort_key=schema.RECORD_TYPE_MODULE,
        version=1,
        attributes={"is_active": True},
    )
    with pytest.raises(ProjectionValidationError, match="id segment"):
        validate_item(item)


# --- missing version raises (R5.6 versioned write needs one) ----------------


def test_validate_item_missing_version_raises():
    item = _tenant_item(version=None)
    with pytest.raises(ProjectionValidationError, match="version"):
        validate_item(item)


def test_validate_item_zero_version_is_valid():
    # The builder's deterministic fallback version is 0 — 0 is present, not None.
    item = _tenant_item(version=0)
    assert validate_item(item) is item


# --- missing / malformed required fields raise ------------------------------


def test_validate_item_module_missing_is_active_raises():
    item = ProjectionItem(
        tenant_id="TenantA",
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_MODULE, "SAM_TEST_MODULE"),
        version=1,
        attributes={},  # missing is_active
    )
    with pytest.raises(ProjectionValidationError, match="is_active"):
        validate_item(item)


def test_validate_item_module_non_bool_is_active_raises():
    item = ProjectionItem(
        tenant_id="TenantA",
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_MODULE, "SAM_TEST_MODULE"),
        version=1,
        attributes={"is_active": "yes"},  # not a bool
    )
    with pytest.raises(ProjectionValidationError, match="is_active"):
        validate_item(item)


def test_validate_item_role_missing_role_field_raises():
    item = ProjectionItem(
        tenant_id="TenantA",
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_ROLE, "a@b.example", "SamTest_Read"),
        version=1,
        attributes={"email": "a@b.example"},  # missing role
    )
    with pytest.raises(ProjectionValidationError, match="role"):
        validate_item(item)


def test_validate_item_role_blank_email_field_raises():
    item = ProjectionItem(
        tenant_id="TenantA",
        sort_key=schema.build_sort_key(schema.RECORD_TYPE_ROLE, "a@b.example", "SamTest_Read"),
        version=1,
        attributes={"email": "   ", "role": "SamTest_Read"},  # blank email
    )
    with pytest.raises(ProjectionValidationError, match="email"):
        validate_item(item)


# --- error type + context ---------------------------------------------------


def test_projection_validation_error_is_a_value_error():
    # Subclasses ValueError so existing ValueError handlers keep working (T12).
    assert issubclass(ProjectionValidationError, ValueError)


def test_validate_item_error_carries_key_identity_not_secrets():
    secret_ish = "super-secret-display-name"
    item = _tenant_item(tenant_id="", attrs={"display_name": secret_ish})
    with pytest.raises(ProjectionValidationError) as excinfo:
        validate_item(item)
    # identity (sort key) surfaced for tracing; attribute values are NOT dumped.
    assert "tenant" in str(excinfo.value)
    assert secret_ish not in str(excinfo.value)


def test_validate_item_rejects_non_projection_item():
    with pytest.raises(ProjectionValidationError, match="ProjectionItem"):
        validate_item({"tenant_id": "TenantA"})  # a raw dict, not a ProjectionItem


# --- batch: one bad item fails loudly, the rest is unaffected framing -------


def test_validate_items_all_valid_returns_batch():
    batch = [_tenant_item(), _module_item(), _role_item()]
    assert validate_items(batch) is batch


def test_validate_items_one_missing_tenant_key_raises_for_batch():
    # A single malformed item makes the batch fail loudly — no partial write.
    batch = [_tenant_item(), _module_item(tenant_id=""), _role_item()]
    with pytest.raises(ProjectionValidationError, match="tenant key"):
        validate_items(batch)


def test_validate_items_valid_siblings_unaffected_when_validated_alone():
    # The "rest unaffected" framing: the valid siblings of a bad item each pass
    # validation on their own — only the malformed one is rejected.
    good_tenant = _tenant_item()
    good_role = _role_item()
    bad_module = _module_item(tenant_id="")

    assert is_valid_item(good_tenant) is True
    assert is_valid_item(good_role) is True
    assert is_valid_item(bad_module) is False
