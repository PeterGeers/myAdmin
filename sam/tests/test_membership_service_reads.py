"""
S5 Task 3.2 — tests for the generic membership engine's **READ surface** (design C2).

These pin the domain-layer read behaviour the handler edge delegates to: tenant-scoped
repository reads (Property 1) + domain-layer scope filtering by ``allowed_scopes`` (design
C4, Property 4) + self-service ownership (design C1 ``self_service`` routes).

- **Scope filtering:** ``allowed_scopes`` is a PER-DIMENSION map ``{dimension_key: [values]}``.
  Per dimension, wildcard (``["*"]``) passes; a subset passes only when the member's value for
  that dimension's field intersects it; an empty grant (``[]``) fails (the scope-deny default,
  Property 4). A member is visible only when it passes EVERY dimension (AND — Property 6);
  an empty map sees nothing. Single-dimension tenants (h-dcn ``region``) are the N=1 case.
- **Structural isolation:** the service only ever asks the repository within a ``tenant_id``,
  so another tenant's records are structurally unreachable (Property 1).
- **Self-service:** a member may read their OWN record (matched on sub / member_id /
  contact) even without a broad scope grant, and never any other member's.
- **Missing / out-of-scope member:** an indistinguishable :class:`MemberNotFound` (no
  existence leak of out-of-scope records).

A tiny in-memory fake :class:`MembersRepository` backs the service (mirrors the fake-repo
pattern in ``sam/tests/test_members_repository.py`` — inject a fake, no boto3, no AWS).

Validates: Requirements R1.2, R3.1, R3.2, R3.3, R3.5, R6.1, R6.2, R9.6
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


def _member(
    member_id, *, region=None, age_group=None, name="Alex", contact=None, sub=None
) -> dict:
    rec = {
        "member_id": member_id,
        "personal": {"first_name": name, "last_name": name, "email": contact or f"{member_id}@example.com"},
        "membership": {"member_number": member_id.replace("M-", ""), "status": "active"},
    }
    overlay: dict = {}
    if region is not None:
        # S5d D1: scope is a plain member field now — h-dcn's `region` dimension binds to the
        # tenant-added `overlay.region` field (NOT the retired `scope_values` bucket).
        overlay["region"] = region
    if age_group is not None:
        # A SECOND scope dimension binding to its OWN field (`overlay.age_group`) — used by
        # the multi-dimension AND tests (Property 6) to prove each dimension reads its own
        # field and both must pass.
        overlay["age_group"] = age_group
    if overlay:
        rec["overlay"] = overlay
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
        listed = service.list_members("h-dcn", {"region": ["*"]})
        assert sorted(m["member_id"] for m in listed) == ["M-1", "M-2", "M-3"]

    def test_subset_sees_only_intersecting_records(self, service):
        listed = service.list_members("h-dcn", {"region": ["Noord"]})
        assert [m["member_id"] for m in listed] == ["M-1"]

    def test_multi_value_subset_unions_the_records(self, service):
        listed = service.list_members("h-dcn", {"region": ["Noord", "Oost"]})
        assert sorted(m["member_id"] for m in listed) == ["M-1", "M-3"]

    def test_empty_scope_denies_by_default(self, service):
        # Property 4: no scope grant → see nothing (never tenant-wide).
        assert service.list_members("h-dcn", {"region": []}) == []

    def test_scope_never_crosses_tenants(self, service):
        # A wildcard in h-dcn still never returns the 'other' tenant's member (isolation).
        listed = service.list_members("h-dcn", {"region": ["*"]})
        assert all(m["member_id"] != "M-9" for m in listed)

    def test_subset_with_no_scope_values_on_record_is_not_visible(self, service, repo):
        repo.add_member("h-dcn", _member("M-noscope"))  # no scope_values at all
        listed = service.list_members("h-dcn", {"region": ["Noord"]})
        assert "M-noscope" not in [m["member_id"] for m in listed]

    def test_wildcard_sees_records_without_scope_values(self, service, repo):
        repo.add_member("h-dcn", _member("M-noscope"))
        listed = service.list_members("h-dcn", {"region": ["*"]})
        assert "M-noscope" in [m["member_id"] for m in listed]


# ---------------------------------------------------------------------------
# export_members — same scope semantics as list
# ---------------------------------------------------------------------------


class TestExportMembers:
    def test_export_is_scope_narrowed_like_list(self, service):
        exported = service.export_members("h-dcn", {"region": ["Zuid"]})
        assert [m["member_id"] for m in exported] == ["M-2"]

    def test_export_empty_scope_is_empty(self, service):
        assert service.export_members("h-dcn", {"region": []}) == []


# ---------------------------------------------------------------------------
# get_member — scope + self-service + missing
# ---------------------------------------------------------------------------


class TestGetMember:
    def test_wildcard_reads_any_member(self, service):
        assert service.get_member("h-dcn", "M-2", {"region": ["*"]})[
            "member_id"
        ] == "M-2"

    def test_in_scope_member_is_returned(self, service):
        assert service.get_member("h-dcn", "M-1", {"region": ["Noord"]})[
            "member_id"
        ] == "M-1"

    def test_out_of_scope_member_is_not_found(self, service):
        # Scoped to Noord, asking for a Zuid member → indistinguishable not-found.
        with pytest.raises(MemberNotFound):
            service.get_member("h-dcn", "M-2", {"region": ["Noord"]})

    def test_missing_member_is_not_found(self, service):
        with pytest.raises(MemberNotFound):
            service.get_member("h-dcn", "does-not-exist", {"region": ["*"]})

    def test_cannot_read_another_tenants_member(self, service):
        # 'M-9' exists only in tenant 'other' → not found under 'h-dcn' even with wildcard.
        with pytest.raises(MemberNotFound):
            service.get_member("h-dcn", "M-9", {"region": ["*"]})

    def test_self_service_reads_own_record_without_scope(self, service):
        # Empty scope (would deny) but the caller owns M-2 via member_id → allowed.
        got = service.get_member(
            "h-dcn", "M-2", {"region": []}, requester_sub="M-2", self_service=True
        )
        assert got["member_id"] == "M-2"

    def test_self_service_matches_on_cognito_sub(self, service, repo):
        repo.add_member("h-dcn", _member("M-5", region="West", sub="cognito-abc"))
        got = service.get_member(
            "h-dcn",
            "M-5",
            {"region": []},
            requester_sub="cognito-abc",
            self_service=True,
        )
        assert got["member_id"] == "M-5"

    def test_self_service_matches_on_contact_email(self, service, repo):
        repo.add_member("h-dcn", _member("M-6", region="West", contact="me@example.com"))
        got = service.get_member(
            "h-dcn",
            "M-6",
            {"region": []},
            requester_sub="me@example.com",
            self_service=True,
        )
        assert got["member_id"] == "M-6"

    def test_self_service_does_not_grant_access_to_other_members(self, service):
        # Owns M-2, but asks for M-3 → self-service does not widen to other members.
        with pytest.raises(MemberNotFound):
            service.get_member(
                "h-dcn",
                "M-3",
                {"region": []},
                requester_sub="M-2",
                self_service=True,
            )

    def test_self_service_flag_off_still_denies_out_of_scope(self, service):
        with pytest.raises(MemberNotFound):
            service.get_member(
                "h-dcn", "M-2", {"region": []}, requester_sub="M-2", self_service=False
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
        got = service.list_memberships("h-dcn", "M-1", {"region": ["Noord"]})
        assert [m["membership_id"] for m in got] == ["MS-1"]

    def test_list_memberships_denied_for_out_of_scope_member(self, service, repo):
        repo.add_membership("h-dcn", "M-2", {"membership_id": "MS-2"})
        with pytest.raises(MemberNotFound):
            service.list_memberships("h-dcn", "M-2", {"region": ["Noord"]})

    def test_get_membership_for_visible_member(self, service, repo):
        repo.add_membership("h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"})
        got = service.get_membership(
            "h-dcn", "M-1", "MS-1", {"region": ["Noord"]}
        )
        assert got["status"] == "active"

    def test_get_membership_missing_is_not_found(self, service):
        with pytest.raises(MemberNotFound):
            service.get_membership("h-dcn", "M-1", "nope", {"region": ["*"]})

    def test_membership_read_via_self_service(self, service, repo):
        repo.add_membership("h-dcn", "M-2", {"membership_id": "MS-9"})
        got = service.list_memberships(
            "h-dcn", "M-2", {"region": []}, requester_sub="M-2", self_service=True
        )
        assert [m["membership_id"] for m in got] == ["MS-9"]


# ---------------------------------------------------------------------------
# Member payments — gated by the parent member's visibility
# ---------------------------------------------------------------------------


class TestMemberPayments:
    def test_payments_for_visible_member(self, service, repo):
        repo.add_payment("h-dcn", "M-1", {"payment_id": "P-1", "amount": 42})
        got = service.get_member_payments("h-dcn", "M-1", {"region": ["Noord"]})
        assert [p["amount"] for p in got] == [42]

    def test_payments_denied_for_out_of_scope_member(self, service, repo):
        repo.add_payment("h-dcn", "M-2", {"payment_id": "P-2", "amount": 99})
        with pytest.raises(MemberNotFound):
            service.get_member_payments("h-dcn", "M-2", {"region": ["Noord"]})

    def test_payments_empty_when_member_visible_but_none_recorded(self, service):
        assert service.get_member_payments("h-dcn", "M-1", {"region": ["*"]}) == []

    def test_payments_via_self_service(self, service, repo):
        repo.add_payment("h-dcn", "M-2", {"payment_id": "P-3", "amount": 7})
        got = service.get_member_payments(
            "h-dcn", "M-2", {"region": []}, requester_sub="M-2", self_service=True
        )
        assert [p["amount"] for p in got] == [7]


# ---------------------------------------------------------------------------
# Multi-dimension AND (design → enforcement item 3, ODx2 Option A, Property 6)
#
# _in_scope iterates the per-dimension allowed_scopes map: a member is visible ONLY IF it
# passes EVERY dimension. Each dimension reads its OWN field (_record_scope_values(member,
# dimension_key)). ["*"] passes a dimension; [] fails it. Single-dimension is the N=1 case.
# ---------------------------------------------------------------------------


@pytest.fixture()
def multidim_repo() -> FakeMembersRepository:
    """Two-dimension members: `region` (overlay.region) AND `age_group` (overlay.age_group)."""
    r = FakeMembersRepository()
    r.add_member("club", _member("A", region="Noord", age_group="youth", name="A"))
    r.add_member("club", _member("B", region="Noord", age_group="senior", name="B"))
    r.add_member("club", _member("C", region="Zuid", age_group="youth", name="C"))
    r.add_member("club", _member("D", region="Zuid", age_group="senior", name="D"))
    return r


@pytest.fixture()
def multidim_service(multidim_repo) -> MembershipService:
    return MembershipService(multidim_repo)


class TestMultiDimensionAnd:
    def test_member_visible_only_when_it_passes_BOTH_dimensions(self, multidim_service):
        # region=Noord AND age_group=youth → only member A (Noord+youth) passes both.
        listed = multidim_service.list_members(
            "club", {"region": ["Noord"], "age_group": ["youth"]}
        )
        assert [m["member_id"] for m in listed] == ["A"]

    def test_passes_one_dimension_but_not_the_other_is_not_visible(self, multidim_service):
        # B is Noord (passes region) but senior (fails age_group=youth) → NOT visible.
        listed = multidim_service.list_members(
            "club", {"region": ["Noord"], "age_group": ["youth"]}
        )
        assert "B" not in [m["member_id"] for m in listed]
        # C is youth (passes age_group) but Zuid (fails region=Noord) → NOT visible.
        assert "C" not in [m["member_id"] for m in listed]

    def test_wildcard_on_one_dimension_passes_that_axis(self, multidim_service):
        # region wildcard (all regions) AND age_group=senior → B (Noord+senior) + D (Zuid+senior).
        listed = multidim_service.list_members(
            "club", {"region": ["*"], "age_group": ["senior"]}
        )
        assert sorted(m["member_id"] for m in listed) == ["B", "D"]

    def test_wildcard_on_every_dimension_sees_all(self, multidim_service):
        listed = multidim_service.list_members(
            "club", {"region": ["*"], "age_group": ["*"]}
        )
        assert sorted(m["member_id"] for m in listed) == ["A", "B", "C", "D"]

    def test_empty_grant_on_one_dimension_denies_that_axis(self, multidim_service):
        # age_group=[] fails EVERY member on that axis → the AND yields nothing, even though
        # region wildcard would pass on its own.
        listed = multidim_service.list_members(
            "club", {"region": ["*"], "age_group": []}
        )
        assert listed == []

    def test_empty_map_denies_by_default(self, multidim_service):
        # No dimension grant at all → deny (never vacuously visible).
        assert multidim_service.list_members("club", {}) == []

    def test_subset_on_both_dimensions_unions_within_each_axis(self, multidim_service):
        # region in {Noord,Zuid} AND age_group in {youth} → A (Noord+youth) + C (Zuid+youth).
        listed = multidim_service.list_members(
            "club", {"region": ["Noord", "Zuid"], "age_group": ["youth"]}
        )
        assert sorted(m["member_id"] for m in listed) == ["A", "C"]

    def test_each_dimension_reads_its_own_field(self, multidim_service):
        # A two-dimension member carries values on two DIFFERENT fields (overlay.region and
        # overlay.age_group). Swapping the grants across axes must NOT match: granting
        # region=youth (a value that only exists on the age_group field) matches nobody,
        # proving each dimension reads its own field rather than a shared bucket.
        listed = multidim_service.list_members(
            "club", {"region": ["youth"], "age_group": ["youth"]}
        )
        assert listed == []

    def test_get_member_enforces_and_across_dimensions(self, multidim_service):
        # C is youth but Zuid → fails region=Noord → indistinguishable not-found.
        with pytest.raises(MemberNotFound):
            multidim_service.get_member(
                "club", "C", {"region": ["Noord"], "age_group": ["youth"]}
            )
        # A passes both → returned.
        got = multidim_service.get_member(
            "club", "A", {"region": ["Noord"], "age_group": ["youth"]}
        )
        assert got["member_id"] == "A"


# ---------------------------------------------------------------------------
# Canonicalized-equality (design Property 4 — "canonical exactness: never partial/
# prefix/fuzzy"). R7.2/R3.5/R9.6.
#
# _in_scope/_passes_dimension reduce BOTH the member's stored field value and every granted
# value through the shared `scope_canon` (NFKD diacritic-fold → casefold → separator-fold →
# trim) and match on EXACT equality of the canonical form. So case / diacritic / separator
# VARIANTS of the same value MATCH, but a PARTIAL / PREFIX substring NEVER does (neither a
# grant that is a prefix of the member's value, nor a member value that is a prefix of the
# grant). These exercise `_in_scope` directly with the per-dimension map shape AND drive the
# same outcomes through `list_members`/`get_member`. The member value here is the multi-word,
# diacritic-bearing "Noord-Holland" so every canonicalization step is genuinely exercised
# (the earlier tests use already-canonical single tokens like "Noord").
# ---------------------------------------------------------------------------


@pytest.fixture()
def canon_repo() -> FakeMembersRepository:
    """A member whose scope field carries a multi-word, diacritic value + a plain one."""
    r = FakeMembersRepository()
    # "Noord-Holland" → canon "noord holland": exercises separator-fold + casefold.
    r.add_member("h-dcn", _member("NH", region="Noord-Holland", name="NH Person"))
    # "Fryslân" → canon "fryslan": exercises the diacritic-fold (â → a).
    r.add_member("h-dcn", _member("FR", region="Fryslân", name="FR Person"))
    return r


@pytest.fixture()
def canon_service(canon_repo) -> MembershipService:
    return MembershipService(canon_repo)


class TestCanonicalizedEqualityInScope:
    """Property 4: enforcement is exact-equality on `scope_canon`, never partial/prefix/fuzzy."""

    @pytest.mark.parametrize(
        "grant",
        [
            "Noord-Holland",   # identical
            "noord-holland",   # case variant
            "NOORD-HOLLAND",   # case variant (upper)
            "noord holland",   # separator variant (space instead of hyphen)
            "Noord Holland",   # case + separator variant
            "Noord / Holland", # separator variant (slash, spaced)
            "  Noord-Holland ",# surrounding whitespace
        ],
    )
    def test_case_and_separator_variants_of_grant_match(self, canon_service, canon_repo, grant):
        """A grant that is a case/diacritic/separator VARIANT of the member's stored value
        matches (both fold to the same canonical form)."""
        member = canon_repo.get_member("h-dcn", "NH")
        assert canon_service._in_scope(member, {"region": [grant]}) is True
        # And end-to-end through list_members.
        listed = canon_service.list_members("h-dcn", {"region": [grant]})
        assert "NH" in [m["member_id"] for m in listed]

    def test_diacritic_variant_of_grant_matches(self, canon_service, canon_repo):
        # Grant "FRYSLAN" (no diacritic, upper) matches member "Fryslân" (diacritic).
        member = canon_repo.get_member("h-dcn", "FR")
        assert canon_service._in_scope(member, {"region": ["FRYSLAN"]}) is True
        assert canon_service._in_scope(member, {"region": ["fryslan"]}) is True
        listed = canon_service.list_members("h-dcn", {"region": ["fryslan"]})
        assert "FR" in [m["member_id"] for m in listed]

    @pytest.mark.parametrize(
        "grant",
        [
            "Noord",           # prefix of "Noord-Holland" — must NOT partial-match
            "noord",           # prefix (canonical) — must NOT partial-match
            "Holland",         # suffix substring — must NOT partial-match
            "Noord-Hol",       # prefix substring
            "oord-Holland",    # suffix substring
            "Noord-Hollands",  # the member value is a PREFIX of the grant — no reverse partial
            "Zuid-Holland",    # a different sibling value — must not match
        ],
    )
    def test_partial_and_prefix_substrings_never_match(self, canon_service, canon_repo, grant):
        """A PARTIAL/PREFIX substring (in either direction) or a sibling value NEVER matches —
        enforcement is exact canonical equality, not `startswith`/`contains`/fuzzy."""
        member = canon_repo.get_member("h-dcn", "NH")
        assert canon_service._in_scope(member, {"region": [grant]}) is False
        listed = canon_service.list_members("h-dcn", {"region": [grant]})
        assert "NH" not in [m["member_id"] for m in listed]

    def test_get_member_matches_on_canonical_variant(self, canon_service):
        # A single-record read is scope-enforced on the SAME canonical equality.
        got = canon_service.get_member("h-dcn", "NH", {"region": ["noord holland"]})
        assert got["member_id"] == "NH"

    def test_get_member_partial_grant_is_not_found(self, canon_service):
        # A prefix grant ("Noord") must not open a partial match → indistinguishable not-found.
        with pytest.raises(MemberNotFound):
            canon_service.get_member("h-dcn", "NH", {"region": ["Noord"]})

    def test_passes_dimension_is_exact_canonical_equality(self, canon_service, canon_repo):
        # _passes_dimension (the per-dimension primitive) matches a canonical variant but not
        # a prefix — proving the exactness lives in the dimension check itself.
        member = canon_repo.get_member("h-dcn", "NH")
        assert canon_service._passes_dimension(member, "region", ["NOORD-HOLLAND"]) is True
        assert canon_service._passes_dimension(member, "region", ["Noord"]) is False

    def test_variant_grant_within_a_multi_value_subset_matches(self, canon_service):
        # A subset mixing a non-matching sibling with a canonical VARIANT of the member's value
        # still matches (union semantics + canonical equality on each entry).
        listed = canon_service.list_members(
            "h-dcn", {"region": ["Zuid-Holland", "noord holland"]}
        )
        assert "NH" in [m["member_id"] for m in listed]


class TestSingleDimensionRegression:
    """h-dcn single-dimension `region` behaviour is unchanged — the N=1 case of the AND."""

    def test_single_dimension_wildcard_sees_all(self, service):
        listed = service.list_members("h-dcn", {"region": ["*"]})
        assert sorted(m["member_id"] for m in listed) == ["M-1", "M-2", "M-3"]

    def test_single_dimension_subset_narrows(self, service):
        listed = service.list_members("h-dcn", {"region": ["Noord"]})
        assert [m["member_id"] for m in listed] == ["M-1"]

    def test_single_dimension_empty_denies(self, service):
        assert service.list_members("h-dcn", {"region": []}) == []
