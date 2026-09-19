"""
S5 Task 3.2 — tests for the generic membership engine's **READ surface** (design C2).

These pin the domain-layer read behaviour the handler edge delegates to: tenant-scoped
repository reads (Property 1) + domain-layer scope filtering by ``allowed_scopes`` (design
C4, Property 4) + self-service ownership (design C1 ``self_service`` routes).

- **Scope filtering:** wildcard (``["*"]``) sees all; a subset sees only records whose
  gating-dimension values intersect the subset; an empty scope (``[]``) sees nothing (the
  scope-deny default, Property 4) — on both list and single-record reads.
- **Structural isolation:** the service only ever asks the repository within a ``tenant_id``,
  so another tenant's records are structurally unreachable (Property 1).
- **Self-service:** a member may read their OWN record (matched on sub / member_id /
  contact) even without a broad scope grant, and never any other member's.
- **Missing / out-of-scope member:** an indistinguishable :class:`MemberNotFound` (no
  existence leak of out-of-scope records).

A tiny in-memory fake :class:`MembersRepository` backs the service (mirrors the fake-repo
pattern in ``sam/tests/test_members_repository.py`` — inject a fake, no boto3, no AWS).

Validates: Requirements R1.2, R3.1, R3.3, R6.1
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

from sam.members.domain.membership_service import (
    MemberNotFound,
    MembershipService,
)
from sam.members.repository.members_repository import MembersRepository


# ---------------------------------------------------------------------------
# In-memory fake repository (the domain depends on the Protocol shape only)
# ---------------------------------------------------------------------------


class FakeMembersRepository:
    """A minimal in-memory :class:`MembersRepository` for domain read tests.

    Stores members/memberships/payments keyed by ``tenant_id`` so a read cannot cross
    tenants (the same structural isolation the real repository enforces). Only the read
    methods the service uses are implemented; writes are convenience seeders for tests.
    """

    def __init__(self):
        self.members: dict[tuple[str, str], dict] = {}
        self.memberships: dict[tuple[str, str, str], dict] = {}
        self.payments: dict[tuple[str, str], list] = {}

    # -- seed helpers ------------------------------------------------------
    def add_member(self, tenant_id: str, member: dict) -> None:
        self.members[(tenant_id, member["member_id"])] = dict(member)

    def add_membership(self, tenant_id: str, member_id: str, membership: dict) -> None:
        self.memberships[(tenant_id, member_id, membership["membership_id"])] = dict(
            membership
        )

    def add_payment(self, tenant_id: str, member_id: str, payment: dict) -> None:
        self.payments.setdefault((tenant_id, member_id), []).append(dict(payment))

    # -- MembersRepository read surface ------------------------------------
    def get_member(self, tenant_id, member_id):
        return self.members.get((tenant_id, member_id))

    def list_members(self, tenant_id, *, filters=None, scope_filter=None):
        return [
            dict(m) for (t, _mid), m in self.members.items() if t == tenant_id
        ]

    def get_membership(self, tenant_id, member_id, membership_id):
        return self.memberships.get((tenant_id, member_id, membership_id))

    def list_memberships(self, tenant_id, member_id):
        return [
            dict(ms)
            for (t, mid, _msid), ms in self.memberships.items()
            if t == tenant_id and mid == member_id
        ]

    def list_member_payments(self, tenant_id, member_id):
        return [dict(p) for p in self.payments.get((tenant_id, member_id), [])]

    # -- unused-by-reads members of the Protocol (raise if touched) --------
    def save_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def delete_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_membership(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def delete_membership(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_delegates(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_member_delegates(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def next_counter(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_membership_types(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def get_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def deactivate_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


def _member(member_id, *, region=None, name="Alex", contact=None, sub=None) -> dict:
    rec = {
        "member_id": member_id,
        "personal": {"name": name, "contact": contact or f"{member_id}@example.com"},
        "membership": {"member_number": member_id.replace("M-", ""), "status": "active"},
    }
    if region is not None:
        rec["scope_values"] = {"region": [region]}
    if sub is not None:
        rec["sub"] = sub
    return rec


@pytest.fixture()
def repo() -> FakeMembersRepository:
    r = FakeMembersRepository()
    r.add_member("h-dcn", _member("M-1", region="Noord", name="Noord Person"))
    r.add_member("h-dcn", _member("M-2", region="Zuid", name="Zuid Person"))
    r.add_member("h-dcn", _member("M-3", region="Oost", name="Oost Person"))
    # A different tenant — must be structurally invisible to h-dcn reads.
    r.add_member("other", _member("M-9", region="Noord", name="Other Tenant"))
    return r


@pytest.fixture()
def service(repo) -> MembershipService:
    return MembershipService(repo)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_fake_repo_satisfies_the_protocol(repo):
    assert isinstance(repo, MembersRepository)


# ---------------------------------------------------------------------------
# list_members — scope filtering (design C4, Property 4)
# ---------------------------------------------------------------------------


class TestListMembersScope:
    def test_wildcard_sees_all_of_the_tenant(self, service):
        listed = service.list_members("h-dcn", ["*"], dimension_key="region")
        assert sorted(m["member_id"] for m in listed) == ["M-1", "M-2", "M-3"]

    def test_subset_sees_only_intersecting_records(self, service):
        listed = service.list_members("h-dcn", ["Noord"], dimension_key="region")
        assert [m["member_id"] for m in listed] == ["M-1"]

    def test_multi_value_subset_unions_the_records(self, service):
        listed = service.list_members("h-dcn", ["Noord", "Oost"], dimension_key="region")
        assert sorted(m["member_id"] for m in listed) == ["M-1", "M-3"]

    def test_empty_scope_denies_by_default(self, service):
        # Property 4: no scope grant → see nothing (never tenant-wide).
        assert service.list_members("h-dcn", [], dimension_key="region") == []

    def test_scope_never_crosses_tenants(self, service):
        # A wildcard in h-dcn still never returns the 'other' tenant's member (isolation).
        listed = service.list_members("h-dcn", ["*"], dimension_key="region")
        assert all(m["member_id"] != "M-9" for m in listed)

    def test_subset_with_no_scope_values_on_record_is_not_visible(self, service, repo):
        repo.add_member("h-dcn", _member("M-noscope"))  # no scope_values at all
        listed = service.list_members("h-dcn", ["Noord"], dimension_key="region")
        assert "M-noscope" not in [m["member_id"] for m in listed]

    def test_wildcard_sees_records_without_scope_values(self, service, repo):
        repo.add_member("h-dcn", _member("M-noscope"))
        listed = service.list_members("h-dcn", ["*"], dimension_key="region")
        assert "M-noscope" in [m["member_id"] for m in listed]


# ---------------------------------------------------------------------------
# export_members — same scope semantics as list
# ---------------------------------------------------------------------------


class TestExportMembers:
    def test_export_is_scope_narrowed_like_list(self, service):
        exported = service.export_members("h-dcn", ["Zuid"], dimension_key="region")
        assert [m["member_id"] for m in exported] == ["M-2"]

    def test_export_empty_scope_is_empty(self, service):
        assert service.export_members("h-dcn", [], dimension_key="region") == []


# ---------------------------------------------------------------------------
# get_member — scope + self-service + missing
# ---------------------------------------------------------------------------


class TestGetMember:
    def test_wildcard_reads_any_member(self, service):
        assert service.get_member("h-dcn", "M-2", ["*"], dimension_key="region")[
            "member_id"
        ] == "M-2"

    def test_in_scope_member_is_returned(self, service):
        assert service.get_member("h-dcn", "M-1", ["Noord"], dimension_key="region")[
            "member_id"
        ] == "M-1"

    def test_out_of_scope_member_is_not_found(self, service):
        # Scoped to Noord, asking for a Zuid member → indistinguishable not-found.
        with pytest.raises(MemberNotFound):
            service.get_member("h-dcn", "M-2", ["Noord"], dimension_key="region")

    def test_missing_member_is_not_found(self, service):
        with pytest.raises(MemberNotFound):
            service.get_member("h-dcn", "does-not-exist", ["*"], dimension_key="region")

    def test_cannot_read_another_tenants_member(self, service):
        # 'M-9' exists only in tenant 'other' → not found under 'h-dcn' even with wildcard.
        with pytest.raises(MemberNotFound):
            service.get_member("h-dcn", "M-9", ["*"], dimension_key="region")

    def test_self_service_reads_own_record_without_scope(self, service):
        # Empty scope (would deny) but the caller owns M-2 via member_id → allowed.
        got = service.get_member(
            "h-dcn", "M-2", [], requester_sub="M-2", self_service=True, dimension_key="region"
        )
        assert got["member_id"] == "M-2"

    def test_self_service_matches_on_cognito_sub(self, service, repo):
        repo.add_member("h-dcn", _member("M-5", region="West", sub="cognito-abc"))
        got = service.get_member(
            "h-dcn",
            "M-5",
            [],
            requester_sub="cognito-abc",
            self_service=True,
            dimension_key="region",
        )
        assert got["member_id"] == "M-5"

    def test_self_service_matches_on_contact_email(self, service, repo):
        repo.add_member("h-dcn", _member("M-6", region="West", contact="me@example.com"))
        got = service.get_member(
            "h-dcn",
            "M-6",
            [],
            requester_sub="me@example.com",
            self_service=True,
            dimension_key="region",
        )
        assert got["member_id"] == "M-6"

    def test_self_service_does_not_grant_access_to_other_members(self, service):
        # Owns M-2, but asks for M-3 → self-service does not widen to other members.
        with pytest.raises(MemberNotFound):
            service.get_member(
                "h-dcn",
                "M-3",
                [],
                requester_sub="M-2",
                self_service=True,
                dimension_key="region",
            )

    def test_self_service_flag_off_still_denies_out_of_scope(self, service):
        with pytest.raises(MemberNotFound):
            service.get_member(
                "h-dcn", "M-2", [], requester_sub="M-2", self_service=False, dimension_key="region"
            )


# ---------------------------------------------------------------------------
# get_self — the /members/me self-service read
# ---------------------------------------------------------------------------


class TestGetSelf:
    def test_returns_the_callers_own_record(self, service):
        assert service.get_self("h-dcn", "M-1")["member_id"] == "M-1"

    def test_no_sub_is_not_found(self, service):
        with pytest.raises(MemberNotFound):
            service.get_self("h-dcn", None)

    def test_unknown_sub_is_not_found(self, service):
        with pytest.raises(MemberNotFound):
            service.get_self("h-dcn", "nobody")

    def test_self_is_tenant_scoped(self, service):
        # The 'other' tenant's member is never resolvable as h-dcn's self.
        with pytest.raises(MemberNotFound):
            service.get_self("h-dcn", "M-9")


# ---------------------------------------------------------------------------
# Membership reads — gated by the parent member's visibility
# ---------------------------------------------------------------------------


class TestMembershipReads:
    def test_list_memberships_for_visible_member(self, service, repo):
        repo.add_membership("h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"})
        got = service.list_memberships("h-dcn", "M-1", ["Noord"], dimension_key="region")
        assert [m["membership_id"] for m in got] == ["MS-1"]

    def test_list_memberships_denied_for_out_of_scope_member(self, service, repo):
        repo.add_membership("h-dcn", "M-2", {"membership_id": "MS-2"})
        with pytest.raises(MemberNotFound):
            service.list_memberships("h-dcn", "M-2", ["Noord"], dimension_key="region")

    def test_get_membership_for_visible_member(self, service, repo):
        repo.add_membership("h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"})
        got = service.get_membership(
            "h-dcn", "M-1", "MS-1", ["Noord"], dimension_key="region"
        )
        assert got["status"] == "active"

    def test_get_membership_missing_is_not_found(self, service):
        with pytest.raises(MemberNotFound):
            service.get_membership("h-dcn", "M-1", "nope", ["*"], dimension_key="region")

    def test_membership_read_via_self_service(self, service, repo):
        repo.add_membership("h-dcn", "M-2", {"membership_id": "MS-9"})
        got = service.list_memberships(
            "h-dcn", "M-2", [], requester_sub="M-2", self_service=True, dimension_key="region"
        )
        assert [m["membership_id"] for m in got] == ["MS-9"]


# ---------------------------------------------------------------------------
# Member payments — gated by the parent member's visibility
# ---------------------------------------------------------------------------


class TestMemberPayments:
    def test_payments_for_visible_member(self, service, repo):
        repo.add_payment("h-dcn", "M-1", {"payment_id": "P-1", "amount": 42})
        got = service.get_member_payments("h-dcn", "M-1", ["Noord"], dimension_key="region")
        assert [p["amount"] for p in got] == [42]

    def test_payments_denied_for_out_of_scope_member(self, service, repo):
        repo.add_payment("h-dcn", "M-2", {"payment_id": "P-2", "amount": 99})
        with pytest.raises(MemberNotFound):
            service.get_member_payments("h-dcn", "M-2", ["Noord"], dimension_key="region")

    def test_payments_empty_when_member_visible_but_none_recorded(self, service):
        assert service.get_member_payments("h-dcn", "M-1", ["*"], dimension_key="region") == []

    def test_payments_via_self_service(self, service, repo):
        repo.add_payment("h-dcn", "M-2", {"payment_id": "P-3", "amount": 7})
        got = service.get_member_payments(
            "h-dcn", "M-2", [], requester_sub="M-2", self_service=True, dimension_key="region"
        )
        assert [p["amount"] for p in got] == [7]
