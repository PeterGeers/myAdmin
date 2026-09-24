"""
S5 Task 1.4 — tests for the tenant-scoped Members **table design** + boto3-backed repository.

These pin the design-of-record + the concrete :class:`DynamoDbMembersRepository`, the sole
DynamoDB touch-point (design C6). They exercise the invariants the repository OWNS:

- **Structural tenant isolation (Property 1):** every operation is keyed by ``tenant_id`` and
  a query cannot address another tenant's partition — a second tenant's identically-numbered
  member is invisible, and a blank tenant is refused.
- **Member number is a plain OPTIONAL string (s5k):** it may be empty, may duplicate (no
  uniqueness guard — a duplicate is a data-quality concern, not a write-time conflict), and is
  stored verbatim (numeric or alphanumeric). ``save_member``/``delete_member`` are single-item
  writes; there is no atomic counter and no ``membernum#`` guard.
- The **key shape** (SK builders / split, item builders, fail-fast table-name resolution).

DynamoDB is faked with an in-memory ``FakeDynamoTable`` + ``FakeDynamoClient`` (mirrors the
``FakeTable`` pattern in ``sam/tests/test_projection_governance_reader.py`` — no moto, no live
AWS). The fake implements the exact surface the repository uses: ``get_item`` / ``put_item`` /
``delete_item`` / ``query`` (Key ``eq`` + ``begins_with``) / ``update_item`` (atomic ADD) and
a ``transact_write_items`` that is all-or-nothing and honours the uniqueness condition — so
the isolation + uniqueness + atomicity properties are genuinely tested, not mocked away.

Validates: Requirements R3.1 (C6, Property 1, Property 6)
"""

from __future__ import annotations

import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors sam/conftest.py + the pretokengen tests) so
# `sam.members...` and its `services.dynamodb_client` dependency both import.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import (
    DynamoDbMembersRepository,
    MembersRepository,
)


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB (table + client) — faithful to the surface used
# ---------------------------------------------------------------------------


class _ConditionalCheckFailed(Exception):
    """Stand-in for a boto3 conditional-check failure raised by the fake."""

    def __init__(self, transactional: bool):
        if transactional:
            response = {
                "Error": {"Code": "TransactionCanceledException"},
                "CancellationReasons": [
                    {"Code": "None"},
                    {"Code": "ConditionalCheckFailed"},
                ],
            }
        else:
            response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        self.response = response
        super().__init__(response["Error"]["Code"])


def _pk(item):
    return item[td.PARTITION_KEY_ATTR]


def _sk(item):
    return item[td.SORT_KEY_ATTR]


class FakeDynamoTable:
    """In-memory stand-in for a boto3 DynamoDB Table + its client (the used surface only).

    Stores items keyed by ``(tenant_id, sk)``. ``query`` honours a partition-key ``eq`` and an
    optional sort-key ``begins_with`` and returns ONLY the matching tenant's items, so
    cross-tenant items are structurally unreturnable — the same isolation a real table + IAM
    ``LeadingKeys`` enforce. ``update_item`` implements the atomic ``ADD`` counter.
    ``transact_write_items`` (on the client) is all-or-nothing and evaluates the uniqueness
    ``ConditionExpression`` used by ``save_member``.
    """

    def __init__(self, name="test_members"):
        self.name = name
        self.store: dict[tuple, dict] = {}
        self.query_calls = 0
        self.meta = _FakeMeta(FakeDynamoClient(self))

    # -- reads -------------------------------------------------------------
    def get_item(self, Key=None):
        key = (Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR])
        item = self.store.get(key)
        return {"Item": dict(item)} if item is not None else {}

    def query(self, KeyConditionExpression=None, ExclusiveStartKey=None):
        self.query_calls += 1
        tenant_id, sk_prefix = _parse_key_condition(KeyConditionExpression)
        items = [
            dict(v)
            for k, v in self.store.items()
            if k[0] == tenant_id and (sk_prefix is None or k[1].startswith(sk_prefix))
        ]
        return {"Items": items}

    # -- writes ------------------------------------------------------------
    def put_item(self, Item=None):
        self.store[(_pk(Item), _sk(Item))] = dict(Item)
        return {}

    def delete_item(self, Key=None):
        self.store.pop((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]), None)
        return {}

    def update_item(
        self,
        Key=None,
        UpdateExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        ReturnValues=None,
    ):
        # Only the atomic-ADD counter form is used by the repository.
        assert UpdateExpression == "ADD #value :one"
        key = (Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR])
        item = self.store.setdefault(
            key,
            {
                td.PARTITION_KEY_ATTR: Key[td.PARTITION_KEY_ATTR],
                td.SORT_KEY_ATTR: Key[td.SORT_KEY_ATTR],
                "value": 0,
            },
        )
        item["value"] = int(item.get("value", 0)) + int(ExpressionAttributeValues[":one"])
        return {"Attributes": {"value": item["value"]}}


class _FakeMeta:
    def __init__(self, client):
        self.client = client


class FakeDynamoClient:
    """Client-level surface the repository uses: ``transact_write_items`` (all-or-nothing)."""

    def __init__(self, table: FakeDynamoTable):
        self._table = table

    def transact_write_items(self, TransactItems=None):
        # Two-phase: evaluate every condition against a snapshot; only apply if ALL pass
        # (mirrors DynamoDB's all-or-nothing transaction semantics).
        planned = []
        for entry in TransactItems:
            if "Put" in entry:
                spec = entry["Put"]
                item = spec["Item"]
                if not self._condition_passes(spec, item):
                    raise _ConditionalCheckFailed(transactional=True)
                planned.append(("put", (_pk(item), _sk(item)), dict(item)))
            elif "Delete" in entry:
                key = entry["Delete"]["Key"]
                planned.append(
                    (
                        "delete",
                        (key[td.PARTITION_KEY_ATTR], key[td.SORT_KEY_ATTR]),
                        None,
                    )
                )
            else:  # pragma: no cover - the repository only uses Put/Delete
                raise AssertionError(f"unsupported transact item: {entry!r}")
        for op, key, item in planned:
            if op == "put":
                self._table.store[key] = item
            else:
                self._table.store.pop(key, None)
        return {}

    def _condition_passes(self, spec, item) -> bool:
        expr = spec.get("ConditionExpression")
        if not expr:
            return True
        # The repository uses exactly: "attribute_not_exists(#pk) OR #owner = :member_id".
        assert expr == "attribute_not_exists(#pk) OR #owner = :member_id"
        existing = self._table.store.get((_pk(item), _sk(item)))
        if existing is None:
            return True  # attribute_not_exists → free to claim
        values = spec["ExpressionAttributeValues"]
        return existing.get("member_id") == values[":member_id"]


def _parse_key_condition(condition):
    """Extract ``(tenant_id, sk_prefix|None)`` from a boto3 Key condition used by the repo.

    Handles both a bare ``Key(pk).eq(t)`` and the ``&``-combined
    ``Key(pk).eq(t) & Key(sk).begins_with(p)`` the repository issues.
    """
    expr = condition.get_expression()
    operator = expr["format"] if isinstance(expr, dict) and "format" in expr else None
    # boto3 conditions expose .get_expression() -> {"operator", "values"}; an AND yields
    # nested conditions. Normalise by walking the values.
    return _walk_condition(condition)


def _walk_condition(condition):
    expr = condition.get_expression()
    op = expr["operator"]
    values = expr["values"]
    if op == "AND":
        tenant_id = None
        sk_prefix = None
        for sub in values:
            t, p = _walk_condition(sub)
            tenant_id = tenant_id if t is None else t
            sk_prefix = sk_prefix if p is None else p
        return tenant_id, sk_prefix
    if op == "=":
        attr = values[0].name
        if attr == td.PARTITION_KEY_ATTR:
            return values[1], None
        return None, None
    if op == "begins_with":
        return None, values[1]
    return None, None  # pragma: no cover


# ---------------------------------------------------------------------------
# Fixtures + seed helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


def _member(member_id: str, member_number: str, *, region=None, name="Alex") -> dict:
    rec = {
        "member_id": member_id,
        "personal": {"first_name": name, "last_name": name, "email": f"{member_id}@example.com"},
        "membership": {
            "member_number": member_number,
            "status": "active",
            "membership_type": "erelid",
            "joined_date": "2024-01-01",
        },
    }
    if region is not None:
        rec["scope_values"] = {"region": [region]}
    return rec


# ---------------------------------------------------------------------------
# Table design (key shape) — the design-of-record
# ---------------------------------------------------------------------------


class TestTableDesign:
    def test_concrete_repo_satisfies_the_protocol(self, repo):
        assert isinstance(repo, MembersRepository)

    def test_sort_key_builders_use_the_documented_shape(self):
        assert td.member_sk("M-1") == "member#M-1"
        assert td.membership_sk("M-1", "MS-9") == "member#M-1#membership#MS-9"
        assert td.delegates_sk("M-1") == "member#M-1#delegates"
        assert td.payment_sk("M-1", "P-3") == "member#M-1#payment#P-3"

    def test_split_sort_key_is_inverse_of_build(self):
        assert td.split_sort_key(td.membership_sk("M-1", "MS-9")) == (
            "member",
            "M-1",
            "membership",
            "MS-9",
        )

    def test_build_sort_key_rejects_empty_and_separator_segments(self):
        with pytest.raises(ValueError):
            td.build_sort_key()
        with pytest.raises(ValueError):
            td.build_sort_key("member", "")
        with pytest.raises(ValueError):
            td.build_sort_key("member", "has#hash")

    def test_build_key_refuses_a_blank_tenant(self):
        with pytest.raises(ValueError):
            td.build_key("", td.member_sk("M-1"))

    def test_build_member_item_stamps_authoritative_tenant_and_key(self):
        item = td.build_member_item("h-dcn", "M-1", _member("M-1", "1001"))
        assert item[td.PARTITION_KEY_ATTR] == "h-dcn"
        assert item[td.SORT_KEY_ATTR] == "member#M-1"
        assert item["member_id"] == "M-1"

    def test_build_member_item_overwrites_a_payload_tenant_id(self):
        # A domain-layer payload that carries the WRONG tenant cannot land elsewhere.
        payload = {**_member("M-1", "1001"), td.PARTITION_KEY_ATTR: "evil-tenant"}
        item = td.build_member_item("h-dcn", "M-1", payload)
        assert item[td.PARTITION_KEY_ATTR] == "h-dcn"

    def test_resolve_table_name_fails_fast_when_env_missing(self, monkeypatch):
        monkeypatch.delenv(td.MEMBERS_TABLE_ENV_VAR, raising=False)
        from services.dynamodb_client import DynamoDBConfigError

        with pytest.raises(DynamoDBConfigError):
            td.resolve_members_table_name()

    def test_resolve_table_name_reads_env(self, monkeypatch):
        monkeypatch.setenv(td.MEMBERS_TABLE_ENV_VAR, "test_members")
        assert td.resolve_members_table_name() == "test_members"

    def test_leading_keys_plan_scopes_to_the_tenant_partition(self):
        plan = td.LEADING_KEYS_IAM_POLICY_PLAN
        condition = plan["Statement"][0]["Condition"]["ForAllValues:StringEquals"]
        assert condition["dynamodb:LeadingKeys"] == ["${aws:PrincipalTag/tenant_id}"]


# ---------------------------------------------------------------------------
# Member CRUD + structural tenant isolation (Property 1)
# ---------------------------------------------------------------------------


class TestMemberCrudAndIsolation:
    def test_save_then_get_round_trips_the_member(self, repo):
        repo.save_member("h-dcn", _member("M-1", "1001"))
        got = repo.get_member("h-dcn", "M-1")
        assert got["personal"]["first_name"] == "Alex"
        assert got["membership"]["member_number"] == "1001"

    def test_get_missing_member_returns_none(self, repo):
        assert repo.get_member("h-dcn", "nope") is None

    def test_list_members_returns_only_bare_member_records(self, repo):
        repo.save_member("h-dcn", _member("M-1", "1001"))
        repo.save_member("h-dcn", _member("M-2", "1002"))
        repo.save_membership("h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"})
        repo.save_delegates("h-dcn", "M-1", [{"email": "d@example.com"}])

        listed = repo.list_members("h-dcn")
        ids = sorted(m["member_id"] for m in listed)
        # Memberships / delegates share the member# prefix but must NOT appear as members.
        assert ids == ["M-1", "M-2"]

    def test_get_member_cannot_cross_tenants(self, repo):
        repo.save_member("tenant-a", _member("M-1", "1001"))
        # The same member_id in another tenant is a different partition → not visible.
        assert repo.get_member("tenant-b", "M-1") is None

    def test_list_members_is_partition_scoped(self, repo):
        repo.save_member("tenant-a", _member("M-1", "1001"))
        repo.save_member("tenant-b", _member("M-9", "9001"))
        assert [m["member_id"] for m in repo.list_members("tenant-a")] == ["M-1"]
        assert [m["member_id"] for m in repo.list_members("tenant-b")] == ["M-9"]

    def test_every_operation_refuses_a_blank_tenant(self, repo):
        for call in (
            lambda: repo.get_member("", "M-1"),
            lambda: repo.list_members(""),
            lambda: repo.save_member("", _member("M-1", "1001")),
            lambda: repo.delete_member("", "M-1"),
        ):
            with pytest.raises(ValueError):
                call()

    def test_delete_member_removes_the_record(self, repo):
        repo.save_member("h-dcn", _member("M-1", "1001"))
        repo.delete_member("h-dcn", "M-1")
        assert repo.get_member("h-dcn", "M-1") is None


# ---------------------------------------------------------------------------
# Member number is a plain OPTIONAL string — no guard, no uniqueness (s5k)
# ---------------------------------------------------------------------------


class TestMemberNumberIsPlainOptionalString:
    def test_save_with_no_member_number_is_allowed(self, repo):
        # s5k: member_number is optional. A member with no number saves (single PutItem).
        m = _member("M-1", "1001")
        del m["membership"]["member_number"]
        repo.save_member("h-dcn", m)
        stored = repo.get_member("h-dcn", "M-1")
        assert stored is not None
        assert not stored["membership"].get("member_number")

    def test_duplicate_number_same_tenant_is_allowed(self, repo):
        # s5k: the uniqueness guard was removed — a duplicate number is a data-quality concern,
        # NOT a write-time conflict. Both saves succeed (last write wins per member_id).
        repo.save_member("h-dcn", _member("M-1", "1001"))
        repo.save_member("h-dcn", _member("M-2", "1001"))
        assert repo.get_member("h-dcn", "M-1")["membership"]["member_number"] == "1001"
        assert repo.get_member("h-dcn", "M-2")["membership"]["member_number"] == "1001"

    def test_arbitrary_string_number_is_stored_verbatim(self, repo):
        repo.save_member("h-dcn", _member("M-1", "ABCDEFG"))
        assert repo.get_member("h-dcn", "M-1")["membership"]["member_number"] == "ABCDEFG"

    def test_idempotent_resave_of_same_member_updates_in_place(self, repo):
        repo.save_member("h-dcn", _member("M-1", "1001", name="Alex"))
        repo.save_member("h-dcn", _member("M-1", "1001", name="Alexandra"))
        assert repo.get_member("h-dcn", "M-1")["personal"]["first_name"] == "Alexandra"


# ---------------------------------------------------------------------------
# Memberships / delegates / payments — tenant-scoped children
# ---------------------------------------------------------------------------


class TestMemberChildren:
    def test_membership_round_trips_under_its_member(self, repo):
        repo.save_member("h-dcn", _member("M-1", "1001"))
        repo.save_membership(
            "h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"}
        )
        got = repo.get_membership("h-dcn", "M-1", "MS-1")
        assert got["status"] == "active"
        assert [m["membership_id"] for m in repo.list_memberships("h-dcn", "M-1")] == [
            "MS-1"
        ]

    def test_memberships_do_not_leak_across_members(self, repo):
        repo.save_membership("h-dcn", "M-1", {"membership_id": "MS-1"})
        repo.save_membership("h-dcn", "M-2", {"membership_id": "MS-2"})
        assert [m["membership_id"] for m in repo.list_memberships("h-dcn", "M-1")] == [
            "MS-1"
        ]

    def test_delete_membership_removes_only_that_membership(self, repo):
        repo.save_membership("h-dcn", "M-1", {"membership_id": "MS-1"})
        repo.save_membership("h-dcn", "M-1", {"membership_id": "MS-2"})
        repo.delete_membership("h-dcn", "M-1", "MS-1")
        assert [m["membership_id"] for m in repo.list_memberships("h-dcn", "M-1")] == [
            "MS-2"
        ]

    def test_save_delegates_replaces_the_set(self, repo):
        repo.save_delegates("h-dcn", "M-1", [{"email": "a@x.com"}])
        stored = repo.save_delegates("h-dcn", "M-1", [{"email": "b@x.com"}])
        assert stored == [{"email": "b@x.com"}]

    def test_list_member_payments_is_scoped_to_the_member(self, repo):
        table = repo.table
        # Seed a payment directly under the member (write route is Step 5).
        table.put_item(
            Item={
                **td.build_key("h-dcn", td.payment_sk("M-1", "P-1")),
                "member_id": "M-1",
                "amount": 42,
            }
        )
        table.put_item(
            Item={
                **td.build_key("h-dcn", td.payment_sk("M-2", "P-2")),
                "member_id": "M-2",
                "amount": 99,
            }
        )
        payments = repo.list_member_payments("h-dcn", "M-1")
        assert [p["amount"] for p in payments] == [42]


# ---------------------------------------------------------------------------
# Lidmaatschap Beheer catalog repository methods (design C8, R2.4)
# ---------------------------------------------------------------------------


def _mtype(type_code, *, tenant_id="h-dcn", nl=None, active=True, order=0) -> MembershipTypeEntry:
    return MembershipTypeEntry(
        tenant_id=tenant_id,
        type_code=type_code,
        label={"nl": nl or type_code.title(), "en": type_code.title()},
        active=active,
        order=order,
    )


class TestMembershipTypeCatalog:
    def test_save_then_get_round_trips_the_entry(self, repo):
        repo.save_membership_type("h-dcn", _mtype("erelid", nl="Erelid", order=10))
        got = repo.get_membership_type("h-dcn", "erelid")
        assert got is not None
        assert got.type_code == "erelid"
        assert got.label["nl"] == "Erelid"
        assert got.active is True
        assert got.order == 10

    def test_get_missing_entry_returns_none(self, repo):
        assert repo.get_membership_type("h-dcn", "nope") is None

    def test_save_binds_entry_to_the_caller_tenant_when_unset(self, repo):
        # An entry with a blank tenant_id is bound to the caller's tenant on save.
        entry = MembershipTypeEntry(tenant_id="", type_code="donateur", label={"nl": "Donateur"})
        saved = repo.save_membership_type("h-dcn", entry)
        assert saved.tenant_id == "h-dcn"
        assert repo.get_membership_type("h-dcn", "donateur") is not None

    def test_save_refuses_a_cross_tenant_entry(self, repo):
        # An entry that names a DIFFERENT tenant may not be written under this tenant.
        with pytest.raises(ValueError):
            repo.save_membership_type("h-dcn", _mtype("erelid", tenant_id="other"))

    def test_save_refuses_a_blank_tenant(self, repo):
        with pytest.raises(ValueError):
            repo.save_membership_type("", _mtype("erelid"))

    def test_catalog_is_isolated_per_tenant(self, repo):
        repo.save_membership_type("tenant-a", _mtype("erelid", tenant_id="tenant-a"))
        # Another tenant's catalog is a different partition → not visible.
        assert repo.get_membership_type("tenant-b", "erelid") is None
        assert repo.list_membership_types("tenant-b") == []

    def test_list_returns_entries_ordered_by_order_then_code(self, repo):
        repo.save_membership_type("h-dcn", _mtype("sponsor", order=30))
        repo.save_membership_type("h-dcn", _mtype("erelid", order=10))
        repo.save_membership_type("h-dcn", _mtype("donateur", order=10))
        listed = repo.list_membership_types("h-dcn")
        # order asc, ties broken by type_code asc.
        assert [e.type_code for e in listed] == ["donateur", "erelid", "sponsor"]

    def test_empty_catalog_lists_empty(self, repo):
        assert repo.list_membership_types("h-dcn") == []

    def test_list_active_only_drops_soft_deleted(self, repo):
        repo.save_membership_type("h-dcn", _mtype("erelid", order=10))
        repo.save_membership_type("h-dcn", _mtype("sponsor", order=20, active=False))
        assert [e.type_code for e in repo.list_membership_types("h-dcn")] == [
            "erelid",
            "sponsor",
        ]
        assert [
            e.type_code for e in repo.list_membership_types("h-dcn", active_only=True)
        ] == ["erelid"]

    def test_deactivate_soft_deletes_without_hard_delete(self, repo):
        repo.save_membership_type("h-dcn", _mtype("erelid"))
        result = repo.deactivate_membership_type("h-dcn", "erelid")
        assert result is not None and result.active is False
        # The entry is still stored (no hard delete → historical references stay valid).
        still_there = repo.get_membership_type("h-dcn", "erelid")
        assert still_there is not None and still_there.active is False

    def test_deactivate_missing_entry_returns_none(self, repo):
        assert repo.deactivate_membership_type("h-dcn", "nope") is None

    def test_deactivate_is_idempotent(self, repo):
        repo.save_membership_type("h-dcn", _mtype("erelid"))
        repo.deactivate_membership_type("h-dcn", "erelid")
        again = repo.deactivate_membership_type("h-dcn", "erelid")
        assert again is not None and again.active is False

    def test_catalog_entries_do_not_leak_into_member_listing(self, repo):
        # A catalog entry shares the tenant partition but must not surface as a member.
        repo.save_member("h-dcn", _member("M-1", "1001"))
        repo.save_membership_type("h-dcn", _mtype("erelid"))
        assert [m["member_id"] for m in repo.list_members("h-dcn")] == ["M-1"]


# ---------------------------------------------------------------------------
# float → Decimal coercion on write (DynamoDB rejects Python float)
# ---------------------------------------------------------------------------


class TestFloatToDecimalCoercion:
    """DynamoDB refuses Python ``float`` — writes must carry ``Decimal``.

    Regression cover for the h-dcn backfill: source rows carry a JSON float fee
    (``overlay.Bedrag = 22.6``) that reached ``transact_write_items`` untouched and raised
    "Float types are not supported. Use Decimal types instead." The item builders now coerce
    every nested float to ``Decimal`` (via ``td.floats_to_decimal``) so no write path can hand
    boto3 a float.
    """

    def test_floats_to_decimal_coerces_nested_floats(self):
        from decimal import Decimal

        out = td.floats_to_decimal(
            {
                "membership": {"member_number": "M00001"},
                "overlay": {"Bedrag": 22.6, "list": [1.5, {"deep": 3.25}]},
                "count": 7,          # int stays int
                "flag": True,        # bool stays bool (never numeric-coerced)
                "name": "Alex",      # str untouched
            }
        )
        assert out["overlay"]["Bedrag"] == Decimal("22.6")
        assert isinstance(out["overlay"]["Bedrag"], Decimal)
        # 22.6 must round-trip cleanly (Decimal(str(f)), not Decimal(f)).
        assert str(out["overlay"]["Bedrag"]) == "22.6"
        assert out["overlay"]["list"][0] == Decimal("1.5")
        assert out["overlay"]["list"][1]["deep"] == Decimal("3.25")
        assert out["count"] == 7 and isinstance(out["count"], int)
        assert out["flag"] is True and isinstance(out["flag"], bool)
        assert out["name"] == "Alex"

    def test_save_member_stores_overlay_float_as_decimal(self, repo):
        from decimal import Decimal

        member = _member("M-1", "1001")
        member["overlay"] = {"Bedrag": 22.6}  # the exact backfill scenario
        # Must not raise (previously: "Float types are not supported").
        repo.save_member("h-dcn", member)

        got = repo.get_member("h-dcn", "M-1")
        assert got["overlay"]["Bedrag"] == Decimal("22.6")
        assert isinstance(got["overlay"]["Bedrag"], Decimal)

    def test_save_membership_type_coerces_float(self, repo):
        from decimal import Decimal

        entry = _mtype("gewoon_lid")
        saved = repo.save_membership_type("h-dcn", entry)
        assert saved is not None
        # Build the item directly to assert the stored shape carries Decimal, not float.
        item = td.build_membership_type_item("h-dcn", "gewoon_lid", {"fee": 12.5})
        assert item["fee"] == Decimal("12.5")
        assert isinstance(item["fee"], Decimal)
