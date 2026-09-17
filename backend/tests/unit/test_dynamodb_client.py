"""Unit tests for the S3 projection DynamoDB client factory.

Covers the fail-fast / no-dangerous-fallback discipline (S3 requirements R4.1):
the endpoint override is used ONLY when AWS_ENDPOINT_URL_DYNAMODB is set, and a
missing table/region var throws rather than silently defaulting.

Feature: s3-claims-and-projection
"""

import pytest

from services.dynamodb_client import (
    DynamoDBConfigError,
    get_dynamodb_resource,
    get_endpoint_url,
    get_projection_table,
    require_env,
)

# Env vars this module reads; cleared before each test for isolation.
_RELEVANT_VARS = (
    "GOVERNANCE_PROJECTION_TABLE",
    "AWS_ENDPOINT_URL_DYNAMODB",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start every test from a clean slate for the projection env vars."""
    for name in _RELEVANT_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


# --- require_env -----------------------------------------------------------


def test_require_env_present_returns_stripped_value(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "  eu-west-1  ")
    assert require_env("AWS_REGION") == "eu-west-1"


def test_require_env_missing_raises_config_error():
    with pytest.raises(DynamoDBConfigError):
        require_env("GOVERNANCE_PROJECTION_TABLE")


def test_require_env_blank_raises_config_error(monkeypatch):
    monkeypatch.setenv("GOVERNANCE_PROJECTION_TABLE", "   ")
    with pytest.raises(DynamoDBConfigError):
        require_env("GOVERNANCE_PROJECTION_TABLE")


# --- get_endpoint_url ------------------------------------------------------


def test_get_endpoint_url_unset_returns_none():
    # No AWS_ENDPOINT_URL_DYNAMODB -> None (boto3 will resolve real AWS).
    assert get_endpoint_url() is None


def test_get_endpoint_url_blank_returns_none(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "   ")
    assert get_endpoint_url() is None


def test_get_endpoint_url_set_returns_stripped_value(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", " http://localhost:8000 ")
    assert get_endpoint_url() == "http://localhost:8000"


# --- get_dynamodb_resource -------------------------------------------------


def test_get_dynamodb_resource_missing_region_raises():
    # No AWS_REGION and no explicit region -> fail fast, no default.
    with pytest.raises(DynamoDBConfigError):
        get_dynamodb_resource()


def test_get_dynamodb_resource_local_endpoint_used_when_set(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
    resource = get_dynamodb_resource()
    # boto3 records the configured endpoint on the underlying client.
    assert resource.meta.client.meta.endpoint_url == "http://localhost:8000"


def test_get_dynamodb_resource_no_local_endpoint_uses_real_aws(monkeypatch):
    # AWS_ENDPOINT_URL_DYNAMODB unset -> boto3 resolves the real AWS endpoint,
    # NOT a hardcoded localhost default (no dangerous fallback the other way).
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    resource = get_dynamodb_resource()
    endpoint = resource.meta.client.meta.endpoint_url
    assert "localhost" not in endpoint
    assert "amazonaws.com" in endpoint


def test_get_dynamodb_resource_region_override_bypasses_env(monkeypatch):
    # Explicit region works even with AWS_REGION unset.
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
    resource = get_dynamodb_resource(region="us-east-1")
    assert resource.meta.client.meta.region_name == "us-east-1"


# --- get_projection_table --------------------------------------------------


def test_get_projection_table_missing_table_var_raises(monkeypatch):
    # Region present, but no table name -> fail fast (no defaulted table name).
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
    with pytest.raises(DynamoDBConfigError):
        get_projection_table()


def test_get_projection_table_resolves_configured_name(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
    monkeypatch.setenv("GOVERNANCE_PROJECTION_TABLE", "test_governance_projection")
    table = get_projection_table()
    assert table.name == "test_governance_projection"
