"""
Tests for the Copy_Utility (`scripts/copy-prod-to-test.py`) — test-environment
spec Req 16 (+ 20.4).

These pin the utility's contract and its SAFETY guards without touching real AWS:
in-memory fakes for the Cognito and DynamoDB clients record every write, so the
tests can assert the central guarantee — the Copy_Utility only ever writes TEST,
and never writes toward PROD (Req 16.4/16.5) — structurally, not by inspection.

Covered:
- Dry-run is the default: reads the source, writes NOTHING (16.2/16.3).
- --apply without the explicit acknowledgement is refused (16.2/16.3).
- With --apply + acknowledgement: writes TEST only; the PROD source is never
  written (16.4/16.5), proven by a fake that FAILS the test if a write targets PROD.
- Direction/destination guards: a non-test destination (wrong pool / unprefixed
  table / source==dest) is refused BEFORE any write (defense in depth, 19/20).

Validates: Requirements 16.1-16.6, 19.1-19.2, 20.4
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)


def _load_script_module():
    """Import the hyphen-named Copy_Utility script by path (not a valid module name)."""
    path = os.path.join(_REPO_ROOT, "scripts", "test-environment", "copy-prod-to-test.py")
    spec = importlib.util.spec_from_file_location("copy_prod_to_test", path)
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec so @dataclass (under `from __future__ import
    # annotations`) can resolve the module's own namespace during class processing.
    sys.modules["copy_prod_to_test"] = module
    spec.loader.exec_module(module)
    return module


copy_mod = _load_script_module()

PROD_POOL = copy_mod.PROD_POOL_ID
TEST_POOL = copy_mod.TEST_POOL_ID


# ---------------------------------------------------------------------------
# In-memory fakes that REFUSE (fail the test) on any write toward PROD
# ---------------------------------------------------------------------------


class _FakeUserNotFound(Exception):
    """Stand-in for cognito-idp's UserNotFoundException."""


class _FakeCognitoExceptions:
    """Mimics the boto3 ``client.exceptions`` namespace the script references."""

    UserNotFoundException = _FakeUserNotFound


class FakeCognitoClient:
    """Records attribute writes; asserts no write ever targets the PROD pool."""

    exceptions = _FakeCognitoExceptions

    def __init__(self, prod_users: dict[str, dict], test_users: dict[str, dict] | None = None):
        # {email: {attr: value}} per pool.
        self._prod = dict(prod_users)
        self._test = dict(test_users or {})
        self.writes: list[tuple[str, str]] = []  # (pool_id, email) for every write

    # -- read-only surface (PROD or TEST) --
    def admin_get_user(self, UserPoolId=None, Username=None):
        store = self._prod if UserPoolId == PROD_POOL else self._test
        if Username not in store:
            raise _FakeUserNotFound()
        attrs = store[Username]
        return {"UserAttributes": [{"Name": k, "Value": v} for k, v in attrs.items()]}

    # -- write surface (must only ever be the TEST pool) --
    def admin_create_user(self, UserPoolId=None, Username=None, UserAttributes=None, **_):
        self._record_write(UserPoolId, Username, UserAttributes)

    def admin_update_user_attributes(self, UserPoolId=None, Username=None, UserAttributes=None, **_):
        self._record_write(UserPoolId, Username, UserAttributes)

    def _record_write(self, pool_id, email, attrs):
        # The core safety assertion: a write must NEVER target PROD.
        assert pool_id != PROD_POOL, (
            f"Copy_Utility attempted to WRITE the PROD pool {pool_id} — "
            "it must only ever write TEST (Req 16.5)"
        )
        self.writes.append((pool_id, email))
        self._test[email] = {a["Name"]: a["Value"] for a in (attrs or [])}


class _FakeBatchWriter:
    def __init__(self, table):
        self._table = table

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def put_item(self, Item=None):
        self._table._put(Item)


class _FakeTable:
    def __init__(self, resource, name):
        self._resource = resource
        self._name = name

    def scan(self, **kwargs):
        # Read-only; returns everything in one page (no pagination needed for the fake).
        return {"Items": list(self._resource.data.get(self._name, []))}

    def batch_writer(self):
        return _FakeBatchWriter(self)

    def _put(self, item):
        # Safety assertion: a write must NEVER target a non-test (PROD) table.
        assert self._name.startswith("test_"), (
            f"Copy_Utility attempted to WRITE a non-TEST table {self._name!r} — "
            "it must only ever write test_ tables (Req 16.5)"
        )
        self._resource.data.setdefault(self._name, []).append(item)
        self._resource.writes.append(self._name)


class FakeDynamoResource:
    def __init__(self, data: dict[str, list[dict]]):
        self.data = {k: list(v) for k, v in data.items()}
        self.writes: list[str] = []

    def Table(self, name):
        return _FakeTable(self, name)


# ---------------------------------------------------------------------------
# Cognito plane
# ---------------------------------------------------------------------------


class TestCognitoCopy:
    def _client(self):
        prod = {
            "ref@example.org": {
                "email": "ref@example.org",
                "email_verified": "true",
                "custom:tenants": "TenantA",
                "custom:role": "Admin",
            }
        }
        fake = FakeCognitoClient(prod_users=prod)
        return copy_mod.CognitoCopyClient(region="eu-west-1", client=fake), fake

    def test_dry_run_writes_nothing(self):
        client, fake = self._client()
        result = copy_mod.copy_cognito_account(
            "ref@example.org", region="eu-west-1", apply=False, confirmed=False, client=client
        )
        assert result.applied is False
        assert fake.writes == []  # nothing written in dry-run
        # It DID read the PROD attributes for the plan.
        assert result.attributes["custom:tenants"] == "TenantA"

    def test_apply_without_confirmation_is_refused(self):
        client, fake = self._client()
        with pytest.raises(copy_mod.ConfirmationRequiredError):
            copy_mod.copy_cognito_account(
                "ref@example.org", region="eu-west-1", apply=True, confirmed=False, client=client
            )
        assert fake.writes == []  # refused before any write

    def test_apply_writes_test_pool_only(self):
        client, fake = self._client()
        result = copy_mod.copy_cognito_account(
            "ref@example.org", region="eu-west-1", apply=True, confirmed=True, client=client
        )
        assert result.applied is True
        # Exactly one write, and it targeted the TEST pool (the fake asserts != PROD).
        assert fake.writes == [(TEST_POOL, "ref@example.org")]
        assert all(pool == TEST_POOL for pool, _ in fake.writes)

    def test_only_non_secret_allowlist_attributes_are_copied(self):
        prod = {
            "ref@example.org": {
                "email": "ref@example.org",
                "custom:tenants": "TenantA",
                "sub": "should-not-copy",
                "cognito:mfa_enabled": "should-not-copy",
            }
        }
        fake = FakeCognitoClient(prod_users=prod)
        client = copy_mod.CognitoCopyClient(region="eu-west-1", client=fake)
        result = copy_mod.copy_cognito_account(
            "ref@example.org", region="eu-west-1", apply=True, confirmed=True, client=client
        )
        assert "sub" not in result.attributes
        assert "cognito:mfa_enabled" not in result.attributes
        assert set(result.attributes) <= set(copy_mod.COPYABLE_COGNITO_ATTRS)


# ---------------------------------------------------------------------------
# DynamoDB plane
# ---------------------------------------------------------------------------


class TestDynamoCopy:
    def _client(self, items=None):
        data = {"governance_projection": list(items or [{"tenant_id": "T", "sk": "tenant"}])}
        fake = FakeDynamoResource(data)
        return copy_mod.DynamoCopyClient(region="eu-west-1", resource=fake), fake

    def test_dry_run_writes_nothing(self):
        client, fake = self._client()
        result = copy_mod.copy_dynamodb_table(
            "governance_projection", region="eu-west-1", apply=False, confirmed=False, client=client
        )
        assert result.applied is False
        assert result.item_count == 1
        assert fake.writes == []

    def test_apply_without_confirmation_is_refused(self):
        client, fake = self._client()
        with pytest.raises(copy_mod.ConfirmationRequiredError):
            copy_mod.copy_dynamodb_table(
                "governance_projection", region="eu-west-1", apply=True, confirmed=False,
                client=client,
            )
        assert fake.writes == []

    def test_apply_writes_test_table_only(self):
        items = [{"tenant_id": "A", "sk": "tenant"}, {"tenant_id": "B", "sk": "tenant"}]
        client, fake = self._client(items)
        result = copy_mod.copy_dynamodb_table(
            "governance_projection", region="eu-west-1", apply=True, confirmed=True, client=client
        )
        assert result.applied is True
        assert result.dest_table == "test_governance_projection"
        assert result.written == 2
        # Every write targeted the test_ table (the fake asserts the prefix).
        assert set(fake.writes) == {"test_governance_projection"}

    def test_default_destination_is_source_with_test_prefix(self):
        client, _ = self._client()
        result = copy_mod.copy_dynamodb_table(
            "sam-members", region="eu-west-1", apply=False, confirmed=False, client=client
        )
        assert result.dest_table == "test_sam-members"


# ---------------------------------------------------------------------------
# Direction / destination guards (defense in depth) — refuse BEFORE any write
# ---------------------------------------------------------------------------


class TestDirectionGuards:
    def test_dynamodb_source_equals_dest_refused(self):
        client = copy_mod.DynamoCopyClient(
            region="eu-west-1", resource=FakeDynamoResource({"test_x": []})
        )
        with pytest.raises(copy_mod.CopyDirectionError):
            copy_mod.copy_dynamodb_table(
                "test_x", region="eu-west-1", apply=True, confirmed=True,
                dest_table="test_x", client=client,
            )

    def test_dynamodb_non_test_destination_refused(self):
        client = copy_mod.DynamoCopyClient(
            region="eu-west-1", resource=FakeDynamoResource({"governance_projection": []})
        )
        with pytest.raises(copy_mod.NotTestDestinationError):
            copy_mod.copy_dynamodb_table(
                "governance_projection", region="eu-west-1", apply=True, confirmed=True,
                dest_table="governance_projection_copy", client=client,  # no test_ prefix
            )

    def test_dynamodb_source_is_a_test_table_refused(self):
        client = copy_mod.DynamoCopyClient(
            region="eu-west-1", resource=FakeDynamoResource({"test_governance_projection": []})
        )
        with pytest.raises(copy_mod.CopyDirectionError):
            copy_mod.copy_dynamodb_table(
                "test_governance_projection", region="eu-west-1", apply=True, confirmed=True,
                dest_table="test_governance_projection_2", client=client,
            )

    def test_cognito_direction_assertion_rejects_same_pool(self):
        # Direct unit check of the guard: identical source/dest pools must raise.
        with pytest.raises(copy_mod.CopyDirectionError):
            copy_mod._assert_cognito_direction(PROD_POOL, PROD_POOL)

    def test_cognito_direction_assertion_rejects_non_test_dest(self):
        with pytest.raises(copy_mod.NotTestDestinationError):
            copy_mod._assert_cognito_direction(PROD_POOL, "eu-west-1_somethingelse")


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


class TestCli:
    def test_dynamodb_apply_without_ack_exits_2(self, monkeypatch):
        # Inject a fake resource so no real AWS is touched even if the guard let it through.
        monkeypatch.setattr(
            copy_mod.DynamoCopyClient,
            "__init__",
            lambda self, *, region, resource=None: setattr(
                self, "_resource", FakeDynamoResource({"governance_projection": []})
            ),
        )
        rc = copy_mod.main(["dynamodb", "--source-table", "governance_projection", "--apply"])
        assert rc == 2  # ConfirmationRequiredError

    def test_dynamodb_dry_run_default_exits_0(self, monkeypatch):
        monkeypatch.setattr(
            copy_mod.DynamoCopyClient,
            "__init__",
            lambda self, *, region, resource=None: setattr(
                self, "_resource", FakeDynamoResource({"governance_projection": [{"tenant_id": "A", "sk": "t"}]})
            ),
        )
        rc = copy_mod.main(["dynamodb", "--source-table", "governance_projection"])
        assert rc == 0
