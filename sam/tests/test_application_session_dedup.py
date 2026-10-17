"""
application-app task 2.1 — tests for the public-application SESSION de-dup primitive (R3a.1–R3a.3).

These pin the two seams this task adds, mirroring the ``mailsent#<job_id>`` idempotency pattern:

- :func:`sam.members.repository.table_design.app_session_sk` + ``RECORD_TYPE_APP_SESSION`` — the
  ``appsession#<session_key>`` sort-key shape (key composition, guard against a separator in the
  key, round-trips through ``split_sort_key``).
- :meth:`DynamoDbMembersRepository.claim_application_session` — a CONDITIONAL
  ``attribute_not_exists`` put so the FIRST submit of a session claims it (``True``), and a
  same-session resend is condition-rejected (``False``) rather than inserting a second record
  (R3a.3, the double-submit race → single record).
- :meth:`DynamoDbMembersRepository.get_application_session_member` — reads the session→member_id
  mapping a resend uses to resolve the record to UPDATE (R3a.2).

DynamoDB is faked in-memory with a table that HONOURS the ``attribute_not_exists`` conditional
put (mirrors the ``FakeTable`` in ``test_mail_send_adapters.py`` + the repo's own fake) so the
first-wins / resend-rejected behaviour is genuinely exercised, not mocked away. The repository's
module-level ``ClientError`` is rebound to a fake so its ``except ClientError`` catches the fake
table's conditional-check failure.

Validates: Requirements R3a.1, R3a.2, R3a.3, R3a.4
"""

from __future__ import annotations

import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors test_members_repository.py) so
# `sam.members...` and its `services.dynamodb_client` dependency both import.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.repository import members_repository as repo_mod
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table honouring the attribute_not_exists conditional put
# ---------------------------------------------------------------------------


class FakeClientError(Exception):
    """Stand-in for ``botocore.exceptions.ClientError`` with the ``.response`` shape."""

    def __init__(self, code, message="boom"):
        self.response = {"Error": {"Code": code, "Message": message}}
        super().__init__(f"{code}: {message}")


class FakeTable:
    """A fake DynamoDB Table that honours the ``attribute_not_exists`` conditional put."""

    def __init__(self, name="test_members"):
        self.name = name
        self.items: dict[tuple, dict] = {}
        self.put_calls = 0
        self.get_calls = 0

    def put_item(self, *, Item, ConditionExpression=None):
        self.put_calls += 1
        key = (Item[td.PARTITION_KEY_ATTR], Item[td.SORT_KEY_ATTR])
        if (
            ConditionExpression
            and "attribute_not_exists" in ConditionExpression
            and key in self.items
        ):
            raise FakeClientError("ConditionalCheckFailedException", "exists")
        self.items[key] = dict(Item)
        return {}

    def get_item(self, *, Key):
        self.get_calls += 1
        item = self.items.get((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]))
        return {"Item": dict(item)} if item is not None else {}


@pytest.fixture(autouse=True)
def _patch_client_error(monkeypatch):
    """Rebind the repository module's ``ClientError`` to the fake so ``except`` catches it.

    The repository does ``from botocore.exceptions import ClientError`` at module top, so the
    fake table raises a stand-in that the repository's ``except ClientError`` must catch — done
    by rebinding the name in the repository's namespace.
    """
    monkeypatch.setattr(repo_mod, "ClientError", FakeClientError)


@pytest.fixture
def table():
    return FakeTable()


@pytest.fixture
def repo(table):
    return DynamoDbMembersRepository(table=table)


# ---------------------------------------------------------------------------
# 1. table_design: the appsession#<session_key> sort-key shape
# ---------------------------------------------------------------------------


class TestAppSessionSortKey:
    def test_app_session_sk_composes_the_record_type_and_key(self):
        assert td.app_session_sk("sess-123") == "appsession#sess-123"
        assert td.app_session_sk("sess-123").startswith(
            td.RECORD_TYPE_APP_SESSION + td.SORT_KEY_SEPARATOR
        )

    def test_app_session_sk_round_trips_through_split(self):
        sk = td.app_session_sk("abc-def")
        assert td.split_sort_key(sk) == (td.RECORD_TYPE_APP_SESSION, "abc-def")

    def test_app_session_sk_rejects_a_key_containing_the_separator(self):
        # A '#' in the session key would make the composite ambiguous to parse.
        with pytest.raises(ValueError):
            td.app_session_sk("bad#key")

    def test_app_session_sk_rejects_a_blank_key(self):
        with pytest.raises(ValueError):
            td.app_session_sk("")

    def test_record_type_token_is_exported(self):
        assert td.RECORD_TYPE_APP_SESSION == "appsession"
        assert "RECORD_TYPE_APP_SESSION" in td.__all__
        assert "app_session_sk" in td.__all__


# ---------------------------------------------------------------------------
# 2. claim_application_session: first submit claims, resend is condition-rejected
# ---------------------------------------------------------------------------


class TestClaimApplicationSession:
    def test_first_claim_creates_the_marker_and_returns_true(self, repo, table):
        created = repo.claim_application_session("tenant-A", "sess-1", "member-1")
        assert created is True
        # exactly one marker stored, under the appsession#<session_key> sort key
        [(pk, sk)] = list(table.items.keys())
        assert pk == "tenant-A"
        assert sk == td.app_session_sk("sess-1")
        assert table.items[(pk, sk)]["member_id"] == "member-1"

    def test_same_session_resubmit_is_condition_rejected_and_returns_false(
        self, repo, table
    ):
        assert repo.claim_application_session("tenant-A", "sess-1", "member-1") is True
        # A second submit of the SAME session (a double-click / retry) must NOT create a
        # second record — the conditional put fails and the claim returns False (R3a.3).
        second = repo.claim_application_session("tenant-A", "sess-1", "member-2")
        assert second is False
        # still exactly one marker, still mapping the FIRST member (first-wins).
        assert len(table.items) == 1
        [(pk, sk)] = list(table.items.keys())
        assert table.items[(pk, sk)]["member_id"] == "member-1"

    def test_marker_carries_only_metadata_and_a_ttl(self, repo, table):
        repo.claim_application_session("tenant-A", "sess-1", "member-1")
        [(_pk, _sk)] = list(table.items.keys())
        item = table.items[(_pk, _sk)]
        assert item["session_key"] == "sess-1"
        assert item["member_id"] == "member-1"
        assert "created_at" in item
        assert isinstance(item["ttl"], int) and item["ttl"] > 0

    def test_marker_is_tenant_scoped_same_session_key_different_tenants(
        self, repo, table
    ):
        # The same session_key in two tenants are DISTINCT markers (Property 1): each claims.
        assert repo.claim_application_session("tenant-A", "sess-1", "member-A") is True
        assert repo.claim_application_session("tenant-B", "sess-1", "member-B") is True
        assert len(table.items) == 2
        assert table.items[("tenant-A", td.app_session_sk("sess-1"))]["member_id"] == "member-A"
        assert table.items[("tenant-B", td.app_session_sk("sess-1"))]["member_id"] == "member-B"

    def test_claim_requires_a_tenant(self, repo):
        with pytest.raises(ValueError):
            repo.claim_application_session("", "sess-1", "member-1")

    def test_claim_requires_a_session_key_and_member_id(self, repo):
        with pytest.raises(ValueError):
            repo.claim_application_session("tenant-A", "", "member-1")
        with pytest.raises(ValueError):
            repo.claim_application_session("tenant-A", "sess-1", "")


# ---------------------------------------------------------------------------
# 3. get_application_session_member: the session→member_id mapping read (resend path)
# ---------------------------------------------------------------------------


class TestGetApplicationSessionMember:
    def test_read_returns_the_mapped_member_id_after_a_claim(self, repo):
        repo.claim_application_session("tenant-A", "sess-1", "member-1")
        assert repo.get_application_session_member("tenant-A", "sess-1") == "member-1"

    def test_read_returns_none_for_an_unclaimed_session(self, repo):
        assert repo.get_application_session_member("tenant-A", "never") is None

    def test_resend_resolves_to_the_first_members_id(self, repo):
        # The end-to-end R3a.2 shape: first submit claims → member-1; a resend's claim is
        # rejected → the caller reads the mapping and resolves to member-1 to UPDATE it.
        assert repo.claim_application_session("tenant-A", "sess-1", "member-1") is True
        assert repo.claim_application_session("tenant-A", "sess-1", "member-2") is False
        assert repo.get_application_session_member("tenant-A", "sess-1") == "member-1"

    def test_read_is_tenant_scoped(self, repo):
        repo.claim_application_session("tenant-A", "sess-1", "member-A")
        # Another tenant that never claimed this session sees nothing (Property 1).
        assert repo.get_application_session_member("tenant-B", "sess-1") is None

    def test_read_requires_a_tenant(self, repo):
        with pytest.raises(ValueError):
            repo.get_application_session_member("", "sess-1")

    def test_read_returns_none_for_a_blank_session_key(self, repo):
        assert repo.get_application_session_member("tenant-A", "") is None
