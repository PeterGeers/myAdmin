"""
S5 Task 4.0 — tests for the SAM-plane Members table provisioning script
(``scripts/aws/provision-members-tables.py``).

These pin the script's *contract* + its safety guards without touching real AWS or relying
on a running emulator: an in-memory ``FakeDynamoResource`` (with a nested ``client``) stands
in for boto3's DynamoDB resource, and ``services.dynamodb_client.get_dynamodb_resource`` is
monkeypatched to return it. What is verified:

- **Key schema matches ``table_design``** — the created table's KeySchema / AttributeDefinitions
  are exactly the module's PK ``tenant_id`` (S) + SK ``sk`` (S), PAY_PER_REQUEST — so the
  script and the repository can never diverge on the key shape.
- **Idempotent skip** — a second run against an existing table creates nothing.
- **Dry-run creates nothing / prints the plan** — the default (no ``--apply``) makes no AWS
  calls but emits the plan (table name).
- **``--reset`` refused against real AWS** (no endpoint) and **allowed against local**
  (endpoint set) — never deletes a real data table (aws-accounts.md guardrail).
- **Table-name fail-fast** — a missing ``MEMBERS_TABLE`` raises rather than guessing a name.

Validates: Requirements R5.1 (C6, Property 1, Property 7)
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors sam/conftest.py + the other sam tests) so the
# script's `sam.members...` + `services.dynamodb_client` imports resolve.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from botocore.exceptions import ClientError

from sam.members.repository import table_design as td


def _load_script_module():
    """Import the hyphen-named provisioning script by path (not a valid module name)."""
    path = os.path.join(_REPO_ROOT, "scripts", "aws", "provision-members-tables.py")
    spec = importlib.util.spec_from_file_location("provision_members_tables", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provision_mod = _load_script_module()


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB resource + client (only the surface the script uses)
# ---------------------------------------------------------------------------


class _FakeWaiter:
    def wait(self, TableName=None):  # noqa: N803 - boto3 kwarg name
        return None


class FakeDynamoClient:
    """Client surface used by the script: describe_table, get_waiter."""

    def __init__(self, resource: "FakeDynamoResource"):
        self._resource = resource
        self.describe_calls: list[str] = []

    def describe_table(self, TableName=None):  # noqa: N803 - boto3 kwarg name
        self.describe_calls.append(TableName)
        if TableName not in self._resource.tables:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "nope"}},
                "DescribeTable",
            )
        return {"Table": self._resource.tables[TableName]}

    def get_waiter(self, name):
        return _FakeWaiter()


class _FakeTable:
    def __init__(self, resource: "FakeDynamoResource", name: str):
        self._resource = resource
        self._name = name

    def delete(self):
        self._resource.tables.pop(self._name, None)
        self._resource.deleted.append(self._name)


class _FakeMeta:
    def __init__(self, client):
        self.client = client


class FakeDynamoResource:
    """In-memory stand-in for boto3's DynamoDB resource (create_table / Table / meta.client)."""

    def __init__(self, existing: dict | None = None):
        self.tables: dict[str, dict] = dict(existing or {})
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.meta = _FakeMeta(FakeDynamoClient(self))

    def create_table(self, **kwargs):
        name = kwargs["TableName"]
        self.tables[name] = dict(kwargs)
        self.created.append(dict(kwargs))
        return _FakeTable(self, name)

    def Table(self, name):  # noqa: N802 - mirrors boto3 resource.Table
        return _FakeTable(self, name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(monkeypatch):
    """Baseline env: table name set, region set, NO endpoint (→ real-AWS mode by default)."""
    monkeypatch.setenv(td.MEMBERS_TABLE_ENV_VAR, "sam-members-test")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL_DYNAMODB", raising=False)
    return monkeypatch


@pytest.fixture()
def fake_resource(env, monkeypatch):
    """A FakeDynamoResource wired in via services.dynamodb_client.get_dynamodb_resource."""
    resource = FakeDynamoResource()

    def _fake_get_resource(*, region=None):
        return resource

    # The script calls services.dynamodb_client.get_dynamodb_resource — patch the name it
    # imported into its own module namespace.
    monkeypatch.setattr(provision_mod, "get_dynamodb_resource", _fake_get_resource)
    return resource


# ---------------------------------------------------------------------------
# Key schema matches table_design
# ---------------------------------------------------------------------------


class TestKeySchema:
    def test_apply_creates_one_table_with_the_table_design_key_shape(self, fake_resource):
        rc = provision_mod.provision("eu-west-1", apply=True, reset=False)
        assert rc == 0
        assert len(fake_resource.created) == 1  # ONE table, single-table design
        spec = fake_resource.created[0]
        assert spec["TableName"] == "sam-members-test"
        assert spec["BillingMode"] == "PAY_PER_REQUEST"
        assert spec["KeySchema"] == [
            {"AttributeName": td.PARTITION_KEY_ATTR, "KeyType": "HASH"},
            {"AttributeName": td.SORT_KEY_ATTR, "KeyType": "RANGE"},
        ]
        assert spec["AttributeDefinitions"] == [
            {"AttributeName": td.PARTITION_KEY_ATTR, "AttributeType": "S"},
            {"AttributeName": td.SORT_KEY_ATTR, "AttributeType": "S"},
        ]

    def test_created_table_name_comes_from_env_not_hardcoded(self, env, monkeypatch):
        monkeypatch.setenv(td.MEMBERS_TABLE_ENV_VAR, "sam-members")  # prod name
        resource = FakeDynamoResource()
        monkeypatch.setattr(
            provision_mod, "get_dynamodb_resource", lambda *, region=None: resource
        )
        provision_mod.provision("eu-west-1", apply=True, reset=False)
        assert resource.created[0]["TableName"] == "sam-members"


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


class TestIdempotence:
    def test_skips_create_when_table_already_exists(self, fake_resource):
        # First apply creates it.
        provision_mod.provision("eu-west-1", apply=True, reset=False)
        assert len(fake_resource.created) == 1
        # Second apply is a no-op (describe finds it → skip).
        rc = provision_mod.provision("eu-west-1", apply=True, reset=False)
        assert rc == 0
        assert len(fake_resource.created) == 1  # no second create


# ---------------------------------------------------------------------------
# Dry-run (the default) creates nothing but prints the plan
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_creates_nothing(self, fake_resource):
        rc = provision_mod.provision("eu-west-1", apply=False, reset=False)
        assert rc == 0
        assert fake_resource.created == []
        assert fake_resource.deleted == []

    def test_dry_run_prints_the_plan(self, fake_resource, capsys):
        provision_mod.provision("eu-west-1", apply=False, reset=False)
        out = capsys.readouterr().out
        assert "sam-members-test" in out
        assert "DRY-RUN" in out

    def test_dry_run_is_the_cli_default(self, fake_resource):
        # No --apply flag → main() dry-runs, creates nothing.
        rc = provision_mod.main([])
        assert rc == 0
        assert fake_resource.created == []


# ---------------------------------------------------------------------------
# --reset guard: refused against real AWS, allowed against local
# ---------------------------------------------------------------------------


class TestResetGuard:
    def test_reset_refused_against_real_aws_no_endpoint(self, fake_resource):
        # No AWS_ENDPOINT_URL_DYNAMODB → real AWS → reset must be refused, nothing deleted.
        with pytest.raises(provision_mod.ResetRefusedError):
            provision_mod.provision("eu-west-1", apply=True, reset=True)
        assert fake_resource.deleted == []
        assert fake_resource.created == []

    def test_reset_refused_returns_exit_code_2_via_main(self, fake_resource):
        rc = provision_mod.main(["--apply", "--reset"])
        assert rc == 2
        assert fake_resource.deleted == []

    def test_reset_allowed_against_local_endpoint(self, env, monkeypatch):
        # Endpoint set → local emulator → reset permitted: delete existing then recreate.
        monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
        resource = FakeDynamoResource(existing={"sam-members-test": {"TableName": "sam-members-test"}})
        monkeypatch.setattr(
            provision_mod, "get_dynamodb_resource", lambda *, region=None: resource
        )
        rc = provision_mod.provision("eu-west-1", apply=True, reset=True)
        assert rc == 0
        assert "sam-members-test" in resource.deleted  # old one deleted
        assert resource.created[0]["TableName"] == "sam-members-test"  # recreated


# ---------------------------------------------------------------------------
# Table-name fail-fast
# ---------------------------------------------------------------------------


class TestTableNameFailFast:
    def test_missing_members_table_env_fails_fast(self, monkeypatch):
        monkeypatch.delenv(td.MEMBERS_TABLE_ENV_VAR, raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        from services.dynamodb_client import DynamoDBConfigError

        with pytest.raises(DynamoDBConfigError):
            provision_mod.provision("eu-west-1", apply=False, reset=False)

    def test_missing_members_table_env_returns_exit_code_1_via_main(self, monkeypatch):
        monkeypatch.delenv(td.MEMBERS_TABLE_ENV_VAR, raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        rc = provision_mod.main([])
        assert rc == 1
