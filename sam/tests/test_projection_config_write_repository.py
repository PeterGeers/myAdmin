"""
Spec 02 Task 1.2 — unit tests for the Members config **write repository**.

Covers :class:`sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`
— the net-new, SAM-owned versioned writer (design C3) that performs a single ``put_item`` on
exactly the three SAM-owned ``config#*`` rows (``config#fields`` / ``config#scope`` /
``config#mail``), the structural second guard behind the route's ``configId`` check.

What this asserts
-----------------
- **Versioned put**: ``put_config`` writes the EXACT ``build_key`` key (partition + sort) plus
  the ``version`` stamp plus the caller-shaped attributes, and the key/version always win over a
  stray same-named body attribute (R1.4, R1.6).
- **Closed-set guard**: a ``config_id`` outside ``{fields, scope, mail}`` — including ``views`` and
  any unknown id — raises ``ValueError`` BEFORE any ``put_item`` (R2.1, R2.3, R2.4, R2.5).
- **Blank tenant guard**: a blank ``tenant_id`` raises ``ValueError`` BEFORE any ``put_item`` so the
  tenancy boundary is never crossed by a blank key (R3.5, R5.5).
- **Fail-fast table resolution**: when ``GOVERNANCE_PROJECTION_TABLE`` is missing/blank and no
  ``table`` is injected, the first real write fails loud via ``DynamoDBConfigError`` rather than
  defaulting to a table (R5.1, R5.2).

**Property 2: Split-ownership prefix invariant** — for ALL writes the repository accepts, the
written sort key is ``config#{fields,scope,mail}``; it NEVER authors ``tenant`` / ``module#`` /
``role#`` / ``scopegrant#`` / ``config#views``, so the split-ownership partition between SAM and
``ProjectionSync`` (Flask) stays clean (R2.1, R2.4, R2.5).

**Validates: Requirements 2.1, 2.3, 2.4, 5.2, 5.5**

DynamoDB is faked in-memory with a ``RecordingFakeTable`` whose ``put_item`` records every written
item (mirrors the write-side contract the way ``test_members_projection_reader.py`` fakes the read
side). No live AWS, no MySQL.
"""

import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# backend/src on sys.path so `services.projection_schema` resolves (mirrors
# test_members_projection_reader.py — the projection schema is the single source of truth for the
# key shape, shared across both planes).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema
from services.dynamodb_client import PROJECTION_TABLE_ENV_VAR, DynamoDBConfigError

from sam.members.repository.projection_config_write_repository import (
    MembersConfigWriteRepository,
)

_TENANT_ID = "write-repo-tenant"


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (WRITE side)
# ---------------------------------------------------------------------------


class RecordingFakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table that RECORDS every ``put_item``.

    Stores written items keyed by ``(tenant_id, sk)`` (last write wins, like a real upsert) and
    keeps an ordered log of every item written so tests can assert BOTH the final stored shape and
    that a guard rejected a call BEFORE any ``put_item`` (``put_items == []``).
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}
        self.put_items: list[dict] = []

    def put_item(self, Item=None):
        self.put_items.append(dict(Item))
        key = (Item[schema.PARTITION_KEY_ATTR], Item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(Item)
        return {}

    @property
    def put_count(self) -> int:
        return len(self.put_items)


# ---------------------------------------------------------------------------
# Versioned put — writes the expected key + version + attributes (R1.4, R1.6)
# ---------------------------------------------------------------------------


class TestVersionedPut:
    def test_put_config_fields_writes_expected_key_version_and_attributes(self):
        """A ``fields`` write stores the canonical key + version stamp + body attributes.

        Validates: Requirements 2.1, 5.5
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        attributes = {
            "fields": {"nickname": {"key": "nickname", "type": "string"}},
            "overrides": {},
            "functional_groups": [],
        }
        item = repo.put_config(
            _TENANT_ID, schema.CONFIG_ID_FIELDS, attributes, "2026-01-01T00:00:00+00:00"
        )

        expected_sk = schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
        )
        assert expected_sk == "config#fields"
        # Exactly one put_item, carrying key + version + the authored attributes.
        assert table.put_count == 1
        stored = table.store[(_TENANT_ID, expected_sk)]
        assert stored[schema.PARTITION_KEY_ATTR] == _TENANT_ID
        assert stored[schema.SORT_KEY_ATTR] == expected_sk
        assert stored[schema.VERSION_ATTR] == "2026-01-01T00:00:00+00:00"
        assert stored["fields"] == attributes["fields"]
        assert stored["overrides"] == {}
        assert stored["functional_groups"] == []
        # The returned item is exactly what was written.
        assert item == stored

    def test_put_config_scope_and_mail_write_their_own_sort_key(self):
        """``scope`` and ``mail`` each write their own ``config#<id>`` sort key.

        Validates: Requirement 2.1
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        repo.put_config(
            _TENANT_ID, schema.CONFIG_ID_SCOPE, {"dimensions": []}, "v-scope"
        )
        repo.put_config(
            _TENANT_ID, schema.CONFIG_ID_MAIL, {"mail_enabled": True}, "v-mail"
        )

        assert (_TENANT_ID, "config#scope") in table.store
        assert (_TENANT_ID, "config#mail") in table.store
        assert table.store[(_TENANT_ID, "config#scope")]["dimensions"] == []
        assert table.store[(_TENANT_ID, "config#mail")]["mail_enabled"] is True

    def test_key_and_version_win_over_stray_body_attributes(self):
        """A body that smuggles key/version attrs cannot shadow the authoritative key + version.

        Validates: Requirements 2.1, 5.5
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        # A malicious/buggy body that tries to override the partition key, sort key, and version.
        attributes = {
            schema.PARTITION_KEY_ATTR: "attacker-tenant",
            schema.SORT_KEY_ATTR: "scopegrant#evil@x#region",
            schema.VERSION_ATTR: "spoofed-version",
            "dimensions": [],
        }
        item = repo.put_config(
            _TENANT_ID, schema.CONFIG_ID_SCOPE, attributes, "real-version"
        )

        # The key + version stamp win — the body never shadows them.
        assert item[schema.PARTITION_KEY_ATTR] == _TENANT_ID
        assert item[schema.SORT_KEY_ATTR] == "config#scope"
        assert item[schema.VERSION_ATTR] == "real-version"

    def test_none_attributes_still_writes_key_and_version(self):
        """A ``None`` body degrades to an empty dict — only the key + version are written.

        Validates: Requirement 2.1
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        item = repo.put_config(_TENANT_ID, schema.CONFIG_ID_MAIL, None, "v1")

        assert item == {
            schema.PARTITION_KEY_ATTR: _TENANT_ID,
            schema.SORT_KEY_ATTR: "config#mail",
            schema.VERSION_ATTR: "v1",
        }


# ---------------------------------------------------------------------------
# Closed-set guard — views / unknown id raise BEFORE any put_item (R2.3/R2.4/R2.5)
# ---------------------------------------------------------------------------


class TestClosedSetGuard:
    def test_views_config_id_raises_before_any_put(self):
        """``views`` (retired residue) is rejected before a write — Config_Views_Residue stays unauthored.

        Validates: Requirements 2.3, 2.4, 2.5
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        with pytest.raises(ValueError):
            repo.put_config(_TENANT_ID, schema.CONFIG_ID_VIEWS, {}, "v1")
        assert table.put_items == []

    @pytest.mark.parametrize(
        "bad_id",
        [
            "views",
            "tenant",
            "module",
            "role",
            "scopegrant",
            "unknown",
            "",
            "Fields",  # case-sensitive — not the canonical token
        ],
    )
    def test_config_id_outside_closed_set_raises_before_any_put(self, bad_id):
        """Any id outside ``{fields, scope, mail}`` raises ``ValueError`` and performs no write.

        Validates: Requirements 2.3, 2.4
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        with pytest.raises(ValueError):
            repo.put_config(_TENANT_ID, bad_id, {}, "v1")
        assert table.put_items == []


# ---------------------------------------------------------------------------
# Blank tenant guard — raises BEFORE any put_item (R3.5/R5.5)
# ---------------------------------------------------------------------------


class TestBlankTenantGuard:
    @pytest.mark.parametrize("blank", ["", None])
    def test_blank_tenant_id_raises_before_any_put(self, blank):
        """A blank ``tenant_id`` raises ``ValueError`` and performs no write (tenancy boundary).

        Validates: Requirement 5.5
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        with pytest.raises(ValueError):
            repo.put_config(blank, schema.CONFIG_ID_FIELDS, {}, "v1")
        assert table.put_items == []

    def test_blank_tenant_is_checked_before_config_id(self):
        """The blank-tenant guard fires even when the config_id is ALSO invalid — no write either way.

        Validates: Requirements 5.5, 2.3
        """
        table = RecordingFakeTable()
        repo = MembersConfigWriteRepository(table=table)

        with pytest.raises(ValueError):
            repo.put_config("", schema.CONFIG_ID_VIEWS, {}, "v1")
        assert table.put_items == []


# ---------------------------------------------------------------------------
# Fail-fast table resolution — missing/blank env fails loud on first write (R5.1/R5.2)
# ---------------------------------------------------------------------------


class TestFailFastTableResolution:
    def test_missing_projection_table_env_raises_on_first_write(self, monkeypatch):
        """With no injected table and ``GOVERNANCE_PROJECTION_TABLE`` unset, the first write fails loud.

        Validates: Requirements 5.1, 5.2
        """
        monkeypatch.delenv(PROJECTION_TABLE_ENV_VAR, raising=False)
        # No `table=` injected: the lazy `table` property must resolve fail-fast from the env.
        repo = MembersConfigWriteRepository()

        with pytest.raises(DynamoDBConfigError):
            repo.put_config(_TENANT_ID, schema.CONFIG_ID_FIELDS, {}, "v1")

    def test_blank_projection_table_env_raises_on_first_write(self, monkeypatch):
        """A blank ``GOVERNANCE_PROJECTION_TABLE`` is treated as missing — no default table.

        Validates: Requirements 5.1, 5.2
        """
        monkeypatch.setenv(PROJECTION_TABLE_ENV_VAR, "   ")
        repo = MembersConfigWriteRepository()

        with pytest.raises(DynamoDBConfigError):
            repo.put_config(
                _TENANT_ID, schema.CONFIG_ID_SCOPE, {"dimensions": []}, "v1"
            )

    def test_guards_run_before_fail_fast_table_resolution(self, monkeypatch):
        """A blank tenant / closed-set violation raises BEFORE the table is ever resolved.

        The ``ValueError`` guards precede the fail-fast table access, so even a misconfigured env
        surfaces the validation error (not a config error) and never touches DynamoDB.

        Validates: Requirements 2.3, 5.5
        """
        monkeypatch.delenv(PROJECTION_TABLE_ENV_VAR, raising=False)
        repo = MembersConfigWriteRepository()

        # Blank tenant -> ValueError (not DynamoDBConfigError), table never resolved.
        with pytest.raises(ValueError):
            repo.put_config("", schema.CONFIG_ID_FIELDS, {}, "v1")
        # Closed-set violation -> ValueError, table never resolved.
        with pytest.raises(ValueError):
            repo.put_config(_TENANT_ID, "views", {}, "v1")


# ---------------------------------------------------------------------------
# Property 2 — Split-ownership prefix invariant
# ---------------------------------------------------------------------------
#
# The repository is the structural guard that keeps the SAM / ProjectionSync split-ownership
# partition clean: SAM writes ONLY `config#{fields,scope,mail}`; it NEVER authors a `tenant`,
# `module#`, `role#`, `scopegrant#`, or `config#views` row. Property 2 asserts this over a broad
# generated input space — both the accepted ids (always the config#<id> prefix) and the forbidden
# ids (always rejected with no write).
# ---------------------------------------------------------------------------

#: The three ids the repository is allowed to write (the single source is the shared schema).
_WRITABLE_IDS = (schema.CONFIG_ID_FIELDS, schema.CONFIG_ID_SCOPE, schema.CONFIG_ID_MAIL)

#: Sort-key prefixes SAM must NEVER author (ProjectionSync-owned rows + the retired views residue).
_FORBIDDEN_PREFIXES = ("tenant", "module#", "role#", "scopegrant#", "config#views")

_TOKEN = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=1,
    max_size=12,
)


@settings(max_examples=100)
@given(
    tenant_id=_TOKEN,
    config_id=st.sampled_from(_WRITABLE_IDS),
    version=_TOKEN,
)
def test_property_accepted_writes_only_emit_config_prefix(
    tenant_id, config_id, version
):
    """Property 2: every accepted write emits a ``config#{fields,scope,mail}`` sort key — nothing else.

    Validates: Requirements 2.1, 2.4

    For ALL ``(tenant_id, config_id ∈ {fields,scope,mail})``, the written sort key is
    ``config#<config_id>`` and never begins with any forbidden (ProjectionSync-owned / retired)
    prefix.
    """
    table = RecordingFakeTable()
    repo = MembersConfigWriteRepository(table=table)

    item = repo.put_config(tenant_id, config_id, {}, version)

    sk = item[schema.SORT_KEY_ATTR]
    assert sk == schema.build_sort_key(schema.RECORD_TYPE_CONFIG, config_id)
    assert sk in {"config#fields", "config#scope", "config#mail"}
    # Never a ProjectionSync-owned or retired-views prefix.
    for forbidden in _FORBIDDEN_PREFIXES:
        assert not sk.startswith(forbidden)
    # Exactly one row written, under the caller's own tenant partition.
    assert table.put_count == 1
    assert item[schema.PARTITION_KEY_ATTR] == tenant_id


@settings(max_examples=100)
@given(
    tenant_id=_TOKEN,
    forbidden_id=st.sampled_from(["tenant", "module", "role", "scopegrant", "views"]),
    version=_TOKEN,
)
def test_property_forbidden_ids_never_write(tenant_id, forbidden_id, version):
    """Property 2: a forbidden config id is ALWAYS rejected before any ``put_item``.

    Validates: Requirements 2.3, 2.4, 2.5

    For ALL ``(tenant_id, forbidden_id)``, ``put_config`` raises ``ValueError`` and performs no
    write — so SAM can never author a ProjectionSync-owned row or the retired ``config#views``
    residue, no matter the input.
    """
    table = RecordingFakeTable()
    repo = MembersConfigWriteRepository(table=table)

    with pytest.raises(ValueError):
        repo.put_config(tenant_id, forbidden_id, {}, version)
    assert table.put_items == []
