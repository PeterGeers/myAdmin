"""
Spec 02, Task 1.18 — **Property 11: Rows-per-page selector + DynamoDB cursor paging**.

The SAM Members READ/query-path side of Requirement 25 (the frontend selector/paging has its
own vitest). These pin the DynamoDB-native cursor-paging contract end to end over the existing
in-memory repository/table fakes (NO live AWS, mirrors the fake-repo pattern in
``sam/tests/test_members_repository.py`` / ``test_membership_service_reads.py``):

- ``Max`` returns ONE page with NO ``Limit``, bounded by the natural ~1 MB boundary (here the
  fake returns the whole partition in one page) — ``Max`` is one Query page, NOT all rows.
- the FIXED options (50/100/250/500) apply the value as the DynamoDB Query ``Limit``.
- prev/next is cursor-based on the ``LastEvaluatedKey`` for EVERY option incl. ``Max``: the
  read path returns an opaque next-page cursor exactly when the last query returned a
  ``LastEvaluatedKey``.
- Next is disabled when no ``LastEvaluatedKey`` was returned (final page → cursor ``None``);
  Prev is disabled when no previous cursor exists (the first page is reached with cursor
  ``None``). The cursor round-trips opaquely and is TENANT-PINNED — a cursor from one tenant
  can never resume a read in another (Property 1).

**Validates: Requirement 25** (25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.9, 25.10)
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.membership_service import MembershipService
from sam.members.domain.scope_dimensions import WILDCARD
from sam.members.repository import table_design as td
from sam.members.repository.members_cursor import (
    CursorError,
    decode_cursor,
    encode_cursor,
)
from sam.members.repository.members_repository import DynamoDbMembersRepository

# A tenant-wide scope grant for the single default dimension (sees every member).
WIDE_SCOPE = {"region": [WILDCARD]}


# ---------------------------------------------------------------------------
# Faithful in-memory DynamoDB table — honours Limit / ExclusiveStartKey /
# LastEvaluatedKey for a SINGLE Query page (what cursor paging depends on).
# ---------------------------------------------------------------------------


class FakePagingTable:
    """In-memory table whose ``query`` returns ONE page, honouring Limit + the cursor.

    Items are kept in insertion order within each tenant (DynamoDB returns a partition's items
    in sort-key order; our member SKs sort by insertion here, which is enough to exercise the
    page/cursor walk). A single ``query`` call:

    - selects the tenant partition + the ``member#`` sort-key prefix (structural isolation);
    - resumes AFTER ``ExclusiveStartKey`` when given (the previous page's LastEvaluatedKey);
    - returns at most ``Limit`` items when ``Limit`` is set, else the WHOLE remaining partition
      in one page (the ``Max`` / no-limit case — one page up to the ~1 MB boundary, which the
      fake treats as "everything remaining");
    - sets ``LastEvaluatedKey`` to the last returned item's key IFF more items remain, else
      omits it (final page).
    """

    def __init__(self, name: str = "test_members"):
        self.name = name
        self._items: list[dict] = []

    def put_item(self, Item=None):
        self._items.append(dict(Item))
        return {}

    def _key_of(self, item: dict) -> dict:
        return {
            td.PARTITION_KEY_ATTR: item[td.PARTITION_KEY_ATTR],
            td.SORT_KEY_ATTR: item[td.SORT_KEY_ATTR],
        }

    def query(self, KeyConditionExpression=None, Limit=None, ExclusiveStartKey=None):
        tenant_id, sk_prefix = _parse_key_condition(KeyConditionExpression)
        rows = [
            dict(it)
            for it in self._items
            if it[td.PARTITION_KEY_ATTR] == tenant_id
            and (sk_prefix is None or it[td.SORT_KEY_ATTR].startswith(sk_prefix))
        ]
        start = 0
        if ExclusiveStartKey:
            for i, it in enumerate(rows):
                if it[td.SORT_KEY_ATTR] == ExclusiveStartKey[td.SORT_KEY_ATTR]:
                    start = i + 1
                    break
        remaining = rows[start:]
        if Limit is not None:
            page = remaining[:Limit]
        else:
            page = remaining  # Max / no-limit: one page = everything remaining
        response: dict = {"Items": page}
        consumed = start + len(page)
        if consumed < len(rows):
            response["LastEvaluatedKey"] = self._key_of(page[-1])
        return response


def _parse_key_condition(condition):
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
        if values[0].name == td.PARTITION_KEY_ATTR:
            return values[1], None
        return None, None
    if op == "begins_with":
        return None, values[1]
    return None, None  # pragma: no cover


# ---------------------------------------------------------------------------
# Fixtures / seed helpers
# ---------------------------------------------------------------------------


def _seed_members(repo: DynamoDbMembersRepository, tenant_id: str, count: int) -> None:
    """Put ``count`` bare member records (zero-padded ids sort stably) into the tenant."""
    for i in range(count):
        member_id = f"M{i:04d}"
        repo.table.put_item(
            Item={
                td.PARTITION_KEY_ATTR: tenant_id,
                td.SORT_KEY_ATTR: td.member_sk(member_id),
                "member_id": member_id,
                "personal": {"first_name": f"Member{i}"},
            }
        )


@pytest.fixture()
def repo() -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=FakePagingTable())


@pytest.fixture()
def service(repo) -> MembershipService:
    return MembershipService(repo)


# ---------------------------------------------------------------------------
# Cursor codec — opaque round-trip + tenant isolation (Property 1)
# ---------------------------------------------------------------------------


def test_encode_cursor_none_when_no_last_evaluated_key_returns_none():
    # No LastEvaluatedKey → no next page → cursor None (Next disabled, R25.5/R25.6).
    assert encode_cursor(None) is None
    assert encode_cursor({}) is None


def test_cursor_round_trips_opaquely_within_same_tenant():
    key = {td.PARTITION_KEY_ATTR: "h-dcn", td.SORT_KEY_ATTR: td.member_sk("M0042")}
    wire = encode_cursor(key)
    assert isinstance(wire, str) and wire  # opaque, non-empty
    # The client never parses it; the server decodes it back to the ExclusiveStartKey.
    assert decode_cursor(wire, "h-dcn") == key


def test_decode_cursor_rejects_cross_tenant_cursor():
    # A cursor minted in one tenant must NEVER resume a read in another (Property 1).
    wire = encode_cursor(
        {td.PARTITION_KEY_ATTR: "tenant-a", td.SORT_KEY_ATTR: td.member_sk("M1")}
    )
    with pytest.raises(CursorError):
        decode_cursor(wire, "tenant-b")


def test_decode_cursor_rejects_malformed_cursor():
    with pytest.raises(CursorError):
        decode_cursor("!!!not-base64!!!", "h-dcn")


def test_decode_cursor_none_for_first_page():
    assert decode_cursor(None, "h-dcn") is None
    assert decode_cursor("", "h-dcn") is None


# ---------------------------------------------------------------------------
# Repository — Max omits Limit; fixed options apply Limit; cursor advances
# ---------------------------------------------------------------------------


def test_max_returns_one_page_no_limit_bounded_by_page_boundary(repo):
    # Max (limit=None): ONE page, NO Limit, up to the natural boundary (R25.3). The fake
    # returns the whole partition in one page and NO LastEvaluatedKey → single page, no next.
    _seed_members(repo, "h-dcn", 320)
    members, last_key = repo.list_members_page("h-dcn", limit=None)
    assert len(members) == 320  # one page = everything remaining, NOT paged into chunks
    assert last_key is None  # no next page


@pytest.mark.parametrize("limit", [50, 100, 250, 500])
def test_fixed_option_applies_query_limit(repo, limit):
    # A fixed option applies the value as the DynamoDB Query Limit (R25.2): at most `limit` rows.
    _seed_members(repo, "h-dcn", 600)
    members, last_key = repo.list_members_page("h-dcn", limit=limit)
    assert len(members) == limit
    # 600 > limit → more remain → a LastEvaluatedKey (Next enabled, R25.5).
    assert last_key is not None


def test_fixed_option_last_page_has_no_cursor(repo):
    # When the tenant fits within one page for the selected size, there is no LastEvaluatedKey
    # → Next disabled, the result is one page (R25.6).
    _seed_members(repo, "h-dcn", 40)
    members, last_key = repo.list_members_page("h-dcn", limit=50)
    assert len(members) == 40
    assert last_key is None


def test_cursor_walks_forward_over_fixed_option_pages(repo):
    # prev/next walk the LastEvaluatedKey cursor (R25.4): paging with limit=50 over 120 members
    # yields 50 + 50 + 20 with no overlap and a None cursor on the final page.
    _seed_members(repo, "h-dcn", 120)

    page1, cur1 = repo.list_members_page("h-dcn", limit=50)
    assert len(page1) == 50 and cur1 is not None

    page2, cur2 = repo.list_members_page("h-dcn", limit=50, start_key=cur1)
    assert len(page2) == 50 and cur2 is not None

    page3, cur3 = repo.list_members_page("h-dcn", limit=50, start_key=cur2)
    assert len(page3) == 20
    assert cur3 is None  # final page → Next disabled (R25.5/R25.6)

    seen = [m["member_id"] for m in (*page1, *page2, *page3)]
    assert len(seen) == len(set(seen)) == 120  # no overlap, full coverage


def test_list_members_page_is_tenant_isolated(repo):
    # The page query pins tenant_id as the partition key — another tenant's members never leak.
    _seed_members(repo, "tenant-a", 10)
    _seed_members(repo, "tenant-b", 5)
    members, _ = repo.list_members_page("tenant-a", limit=None)
    assert len(members) == 10
    assert all(m["member_id"].startswith("M") for m in members)


# ---------------------------------------------------------------------------
# Domain — scope-narrowed page + opaque next cursor (prev/next semantics)
# ---------------------------------------------------------------------------


def test_domain_page_max_returns_one_page_and_no_cursor(service):
    service._repo and _seed_members(service._repo, "h-dcn", 80)
    rows, cursor = service.list_members_page("h-dcn", WIDE_SCOPE, page_size=None)
    assert len(rows) == 80
    assert cursor is None  # one page, no next


def test_domain_page_fixed_option_returns_cursor_then_resumes(service):
    _seed_members(service._repo, "h-dcn", 120)

    rows1, cursor1 = service.list_members_page("h-dcn", WIDE_SCOPE, page_size=50)
    assert len(rows1) == 50
    assert cursor1 is not None  # Next enabled (R25.5)

    # The opaque cursor round-trips back to resume the next page (R25.4/R25.7).
    rows2, cursor2 = service.list_members_page(
        "h-dcn", WIDE_SCOPE, page_size=50, cursor=cursor1
    )
    assert len(rows2) == 50
    assert cursor2 is not None

    rows3, cursor3 = service.list_members_page(
        "h-dcn", WIDE_SCOPE, page_size=50, cursor=cursor2
    )
    assert len(rows3) == 20
    assert cursor3 is None  # final page → Next disabled (R25.6)

    ids = [m["member_id"] for m in (*rows1, *rows2, *rows3)]
    assert len(ids) == len(set(ids)) == 120


def test_domain_page_deny_scope_sees_nothing(service):
    # An empty scope grant sees nothing and has no next page (deny-by-default, Property 4).
    _seed_members(service._repo, "h-dcn", 50)
    rows, cursor = service.list_members_page("h-dcn", {}, page_size=50)
    assert rows == []
    assert cursor is None


def test_domain_page_rejects_foreign_cursor(service):
    # A cursor minted for another tenant is rejected before any read (Property 1).
    _seed_members(service._repo, "h-dcn", 10)
    foreign = encode_cursor(
        {td.PARTITION_KEY_ATTR: "other", td.SORT_KEY_ATTR: td.member_sk("M1")}
    )
    with pytest.raises(CursorError):
        service.list_members_page("h-dcn", WIDE_SCOPE, page_size=50, cursor=foreign)
