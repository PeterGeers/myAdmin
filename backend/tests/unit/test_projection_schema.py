"""Unit tests for the S3 governance projection table shape module.

Covers the canonical key-shape constants, the sort-key compose/parse helpers,
the full-key builder, and the fail-fast table-name resolution (S3 R5.4, R4.1).

Feature: s3-claims-and-projection
"""

import json

import pytest

from services.dynamodb_client import DynamoDBConfigError
from services import projection_schema as schema

# Env vars the table-name resolution reads; cleared for isolation.
_RELEVANT_VARS = (
    "GOVERNANCE_PROJECTION_TABLE",
    "AWS_ENDPOINT_URL_DYNAMODB",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _RELEVANT_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


# --- key-shape constants ----------------------------------------------------


def test_key_attr_names_match_design_and_seed():
    # PK == tenancy boundary; SK attr name reconciled with the seed script ("sk").
    assert schema.PARTITION_KEY_ATTR == "tenant_id"
    assert schema.SORT_KEY_ATTR == "sk"
    assert schema.VERSION_ATTR == "version"
    assert schema.SORT_KEY_SEPARATOR == "#"


# --- build_sort_key ---------------------------------------------------------


def test_build_sort_key_tenant_record_has_no_id_segment():
    assert schema.build_sort_key(schema.RECORD_TYPE_TENANT) == "tenant"


def test_build_sort_key_module_joins_with_separator():
    assert schema.build_sort_key(schema.RECORD_TYPE_MODULE, "members") == "module#members"


def test_build_sort_key_role_joins_all_segments():
    result = schema.build_sort_key(schema.RECORD_TYPE_ROLE, "a@b", "Members_CRUD")
    assert result == "role#a@b#Members_CRUD"


def test_build_sort_key_config_scope_joins_with_separator():
    # C1 config#scope — tenant-level, single id segment (no per-user email).
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope") == "config#scope"


def test_build_sort_key_config_fields_joins_with_separator():
    # C1 config#fields — the other tenant-level config id.
    assert schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "fields") == "config#fields"


def test_build_sort_key_scopegrant_joins_all_segments():
    # C1 scopegrant#<email>#<dimension> — per-user, 3-part arity. The email
    # segment itself contains no "#", so the composite parses back unambiguously.
    result = schema.build_sort_key(
        schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"
    )
    assert result == "scopegrant#alice@h-dcn.example#region"


def test_build_sort_key_empty_record_type_raises():
    with pytest.raises(ValueError):
        schema.build_sort_key("")


def test_build_sort_key_empty_id_segment_raises():
    with pytest.raises(ValueError):
        schema.build_sort_key(schema.RECORD_TYPE_MODULE, "")


def test_build_sort_key_segment_containing_separator_raises():
    # A segment with "#" would make the composite ambiguous to parse back.
    with pytest.raises(ValueError):
        schema.build_sort_key(schema.RECORD_TYPE_MODULE, "mem#bers")


# --- split_sort_key ---------------------------------------------------------


def test_split_sort_key_tenant_returns_empty_id_parts():
    assert schema.split_sort_key("tenant") == ("tenant", ())


def test_split_sort_key_module_returns_single_id_part():
    assert schema.split_sort_key("module#members") == ("module", ("members",))


def test_split_sort_key_role_returns_multiple_id_parts():
    assert schema.split_sort_key("role#a@b#Members_CRUD") == (
        "role",
        ("a@b", "Members_CRUD"),
    )


def test_split_sort_key_config_scope_returns_single_id_part():
    assert schema.split_sort_key("config#scope") == ("config", ("scope",))


def test_split_sort_key_config_fields_returns_single_id_part():
    assert schema.split_sort_key("config#fields") == ("config", ("fields",))


def test_split_sort_key_scopegrant_returns_email_and_dimension_parts():
    # Splits back into (record_type, (<email>, <dimension>)) — the email keeps
    # its own "@" and is a single segment because it contains no separator.
    assert schema.split_sort_key("scopegrant#alice@h-dcn.example#region") == (
        "scopegrant",
        ("alice@h-dcn.example", "region"),
    )


def test_split_sort_key_empty_raises():
    with pytest.raises(ValueError):
        schema.split_sort_key("")


@pytest.mark.parametrize(
    "segments",
    [
        (schema.RECORD_TYPE_TENANT,),
        (schema.RECORD_TYPE_MODULE, "events"),
        (schema.RECORD_TYPE_ROLE, "user@example.invalid", "STR_Read"),
        (schema.RECORD_TYPE_CONFIG, "scope"),
        (schema.RECORD_TYPE_CONFIG, "fields"),
        (schema.RECORD_TYPE_SCOPEGRANT, "alice@h-dcn.example", "region"),
    ],
)
def test_split_is_inverse_of_build(segments):
    # round-trip: split(build(x)) == x  (compose/parse agree)
    composite = schema.build_sort_key(*segments)
    record_type, id_parts = schema.split_sort_key(composite)
    assert (record_type, *id_parts) == segments


# --- build_key --------------------------------------------------------------


def test_build_key_returns_pk_and_sk_dict():
    key = schema.build_key("TEST-TENANT-A", "module#members")
    assert key == {"tenant_id": "TEST-TENANT-A", "sk": "module#members"}


def test_build_key_blank_tenant_raises():
    # A blank partition key is a cross-tenant hazard (R5.4) — must fail loudly.
    with pytest.raises(ValueError):
        schema.build_key("", "tenant")


def test_build_key_blank_sort_key_raises():
    with pytest.raises(ValueError):
        schema.build_key("TEST-TENANT-A", "")


# --- resolve_projection_table_name (fail-fast, R4.1) ------------------------


def test_resolve_projection_table_name_missing_raises():
    # No GOVERNANCE_PROJECTION_TABLE -> fail fast, no default (R4.1).
    with pytest.raises(DynamoDBConfigError):
        schema.resolve_projection_table_name()


def test_resolve_projection_table_name_blank_raises(monkeypatch):
    monkeypatch.setenv("GOVERNANCE_PROJECTION_TABLE", "   ")
    with pytest.raises(DynamoDBConfigError):
        schema.resolve_projection_table_name()


def test_resolve_projection_table_name_returns_configured_value(monkeypatch):
    monkeypatch.setenv("GOVERNANCE_PROJECTION_TABLE", "test_governance_projection")
    assert schema.resolve_projection_table_name() == "test_governance_projection"


# --- IAM LeadingKeys policy plan --------------------------------------------


def test_leading_keys_policy_plan_targets_leading_keys_condition():
    statement = schema.LEADING_KEYS_IAM_POLICY_PLAN["Statement"][0]
    condition = statement["Condition"]["ForAllValues:StringEquals"]
    assert "dynamodb:LeadingKeys" in condition


def test_leading_keys_policy_json_is_valid_json():
    parsed = json.loads(schema.leading_keys_iam_policy_json())
    assert parsed == schema.LEADING_KEYS_IAM_POLICY_PLAN
