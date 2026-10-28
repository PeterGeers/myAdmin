"""
S5 Task 3.2 — tests for the Members handler **READ-route dispatch** (design C1 read → C2/C6).

These pin the wiring the thin handler now performs for the READ routes: once a request is
authenticated + authorized (task 3.0) and its scope is resolved (task 3.1), the edge
delegates to the generic membership engine (C2), threads the router's path params
(``{member_id}`` / ``{membership_id}``) + the requester ``sub`` + the route's
``self_service`` flag, and shapes the domain result into an HTTP response:

- a granted + scoped READ request returns **200** with the scope-narrowed data (not 501);
- a wildcard (admin) caller sees the tenant's data; a scoped caller sees only their subset;
- a deny (empty scope) list returns 200 with an empty list (never tenant-wide);
- ``get_member`` for an out-of-scope / missing member returns **404** (no existence leak);
- self-service (``/members/me``, own ``{member_id}``) returns the caller's own record;
- the WRITE routes are still **501** (Step 5).

The domain service is exercised over an in-memory fake repository injected at the edge (via
``app._get_membership_service``), so these are true edge→domain→repo dispatch tests without
boto3 / AWS. Auth is supplied as verified API-GW-authorizer claims (the task-3.0 gate).

Validates: Requirements R1.2, R3.1, R3.3, R6.1
"""

from __future__ import annotations

import json

import pytest

from sam.members.domain.membership_service import MembershipService
from sam.members.handler import app

# ── Fake repository + injected service ─────────────────────────────────────────────────


class FakeMembersRepository:
    """Minimal in-memory repository for edge-dispatch tests (read surface only)."""

    def __init__(self):
        self.members = {}
        self.memberships = {}
        self.payments = {}

    def add_member(self, tenant_id, member):
        self.members[(tenant_id, member["member_id"])] = dict(member)

    def add_membership(self, tenant_id, member_id, membership):
        self.memberships[(tenant_id, member_id, membership["membership_id"])] = dict(
            membership
        )

    def add_payment(self, tenant_id, member_id, payment):
        self.payments.setdefault((tenant_id, member_id), []).append(dict(payment))

    def get_member(self, tenant_id, member_id):
        return self.members.get((tenant_id, member_id))

    def list_members(self, tenant_id, *, filters=None):
        return [dict(m) for (t, _mid), m in self.members.items() if t == tenant_id]

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


def _member(member_id, *, region=None, sub=None, contact=None):
    rec = {
        "member_id": member_id,
        "personal": {
            "first_name": member_id,
            "last_name": member_id,
            "email": contact or f"{member_id}@x.com",
        },
        "membership": {"member_number": member_id, "status": "active"},
    }
    if region is not None:
        # S5d D1: scope is a plain member field now — h-dcn's `region` dimension binds to the
        # tenant-added `overlay.region` field (NOT the retired `scope_values` bucket).
        rec["overlay"] = {"region": region}
    if sub is not None:
        rec["sub"] = sub
    return rec


@pytest.fixture()
def repo():
    r = FakeMembersRepository()
    r.add_member("h-dcn", _member("M-1", region="North", sub="sub-noord"))
    r.add_member("h-dcn", _member("M-2", region="South", sub="sub-zuid"))
    r.add_membership("h-dcn", "M-1", {"membership_id": "MS-1", "status": "active"})
    r.add_payment("h-dcn", "M-1", {"payment_id": "P-1", "amount": 42})
    return r


# ── Projected scope grants (S5b task 8.3, design C5) ──────────────────────────────────
#
# The caller's scope now comes from the PROJECTED ``scopegrant#`` rows (design C5), NOT the
# token groups. Each test caller is identified by an EMAIL, and the edge reads that email's
# grants for the gating dimension (``region``). We map the S5 scope intents to projected
# grants keyed by email: all-access → ``["*"]``, a region → that subset, and a
# ``required_for`` caller with NO grant is simply ABSENT (deny-by-default).

_EMAIL_ALL = "all@h-dcn.test"  # all-access → region ["*"]
_EMAIL_NOORD = "noord@h-dcn.test"  # scoped to Noord
_EMAIL_ZUID = "zuid@h-dcn.test"  # scoped to Zuid
_EMAIL_NOGRANT = "nogrant@h-dcn.test"  # holds Members_CRUD but NO region grant → deny

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
    ("h-dcn", _EMAIL_NOORD): {"region": ["North"]},
    ("h-dcn", _EMAIL_ZUID): {"region": ["South"]},
    # _EMAIL_NOGRANT deliberately absent → deny-by-default (R2.6).
}


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, repo):
    """Inject a MembershipService over the fake repo + the projected scope grants (task 8.3)."""
    from sam.tests.conftest import FakeScopeGrantsReader

    service = MembershipService(repo)
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── Auth helpers (verified API-GW-authorizer claims — the task-3.0 gate) ────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read", "members:export"),
    email=_EMAIL_ALL,
    groups=(),
    sub="admin-sub",
    body=None,
):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants,
    design C5), not ``groups`` — ``groups`` is kept only so token-role claims stay realistic.
    """
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "cognito:groups": list(groups),
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


# ── list_members ────────────────────────────────────────────────────────────────────


def test_list_members_wildcard_returns_all_and_not_501():
    # All-access projected grant (region ["*"]) → sees the whole tenant. 200 (not 501).
    resp = app.handler(_event("GET", "/members", email=_EMAIL_ALL))
    assert resp["statusCode"] == 200
    ids = sorted(m["member_id"] for m in _data(resp))
    assert ids == ["M-1", "M-2"]


def test_list_members_scoped_returns_only_the_subset():
    # Projected grant region ["Noord"] → scoped to Noord → only M-1 is visible.
    resp = app.handler(_event("GET", "/members", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert [m["member_id"] for m in _data(resp)] == ["M-1"]


def test_list_members_deny_scope_returns_empty_list():
    # A required_for capability (Members_CRUD) held with NO projected region grant → the grant
    # is ABSENT → deny → empty list (never tenant-wide) — Property 4 / R2.6.
    resp = app.handler(
        _event("GET", "/members", email=_EMAIL_NOGRANT, groups=("Members_CRUD",))
    )
    assert resp["statusCode"] == 200
    assert _data(resp) == []


def test_list_members_filtered_via_post_search():
    resp = app.handler(
        _event("POST", "/members/search", email=_EMAIL_ALL, body={"status": "active"})
    )
    assert resp["statusCode"] == 200
    assert sorted(m["member_id"] for m in _data(resp)) == ["M-1", "M-2"]


# ── export_members ──────────────────────────────────────────────────────────────────


def test_export_members_scoped():
    resp = app.handler(_event("GET", "/members/export", email=_EMAIL_ZUID))
    assert resp["statusCode"] == 200
    assert [m["member_id"] for m in _data(resp)] == ["M-2"]


# ── get_member ──────────────────────────────────────────────────────────────────────


def test_get_member_in_scope_returns_the_member():
    resp = app.handler(_event("GET", "/members/M-1", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert _data(resp)["member_id"] == "M-1"


def test_get_member_out_of_scope_returns_404():
    # Scoped to Noord, asking for the Zuid member → indistinguishable 404 (no existence leak).
    resp = app.handler(_event("GET", "/members/M-2", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 404


def test_get_member_missing_returns_404():
    resp = app.handler(_event("GET", "/members/nope", email=_EMAIL_ALL))
    assert resp["statusCode"] == 404


def test_get_member_self_service_reads_own_record_without_scope():
    # Caller has NO region grant (deny scope) but owns M-2 via sub → self-service allows it.
    resp = app.handler(
        _event(
            "GET",
            "/members/M-2",
            email=_EMAIL_NOGRANT,
            groups=("Members_CRUD",),
            sub="sub-zuid",
        )
    )
    assert resp["statusCode"] == 200
    assert _data(resp)["member_id"] == "M-2"


# ── get_self ──────────────────────────────────────────────────────────────────────────


def test_get_self_returns_own_record():
    # /members/me has no capability (pure self-service); tenant context still from entitlement.
    resp = app.handler(
        _event("GET", "/members/me", capabilities=("members:read",), sub="sub-noord")
    )
    assert resp["statusCode"] == 200
    assert _data(resp)["member_id"] == "M-1"


def test_get_self_unknown_sub_returns_404():
    resp = app.handler(
        _event("GET", "/members/me", capabilities=("members:read",), sub="nobody")
    )
    assert resp["statusCode"] == 404


# ── membership + payment reads ─────────────────────────────────────────────────────────


def test_list_memberships_for_visible_member():
    resp = app.handler(_event("GET", "/members/M-1/memberships", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert [m["membership_id"] for m in _data(resp)] == ["MS-1"]


def test_get_membership_for_visible_member():
    resp = app.handler(
        _event("GET", "/members/M-1/memberships/MS-1", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 200
    assert _data(resp)["status"] == "active"


def test_get_membership_out_of_scope_member_returns_404():
    resp = app.handler(
        _event("GET", "/members/M-2/memberships/MS-1", email=_EMAIL_NOORD)
    )
    assert resp["statusCode"] == 404


def test_get_member_payments_for_visible_member():
    resp = app.handler(_event("GET", "/members/M-1/payments", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 200
    assert [p["amount"] for p in _data(resp)] == [42]


def test_get_member_payments_out_of_scope_returns_404():
    resp = app.handler(_event("GET", "/members/M-2/payments", email=_EMAIL_NOORD))
    assert resp["statusCode"] == 404


# ── path params reach the domain (threaded through RequestContext) ─────────────────────


def test_path_params_are_threaded_to_the_domain(monkeypatch):
    captured = {}

    class _Spy:
        def get_membership(
            self, tenant_id, member_id, membership_id, allowed_scopes, **kw
        ):
            captured.update(
                tenant_id=tenant_id, member_id=member_id, membership_id=membership_id
            )
            return {"ok": True}

    monkeypatch.setattr(app, "_get_membership_service", lambda: _Spy())
    resp = app.handler(
        _event("GET", "/members/M-7/memberships/MS-42", email=_EMAIL_ALL)
    )
    assert resp["statusCode"] == 200
    assert captured == {
        "tenant_id": "h-dcn",
        "member_id": "M-7",
        "membership_id": "MS-42",
    }


# ── WRITE routes are now wired (Step 5 / task 5.2) — full coverage in test_members_write_dispatch ──


def test_write_route_now_dispatches_to_the_domain(monkeypatch):
    # The WRITE routes are no longer the 501 stub — they dispatch to the domain write path.
    # (End-to-end write behaviour is pinned in test_members_write_dispatch.py.)
    captured = {}

    class _Spy:
        def create_member(self, tenant_id, body, allowed_scopes, **kw):
            captured.update(
                tenant_id=tenant_id, body=dict(body), scopes=dict(allowed_scopes)
            )
            return {"member_id": "M-new", **dict(body)}

    monkeypatch.setattr(app, "_get_membership_service", lambda: _Spy())
    resp = app.handler(
        _event(
            "POST",
            "/members",
            capabilities=("members:write",),
            email=_EMAIL_ALL,
            body={"personal": {"first_name": "x"}},
        )
    )
    assert resp["statusCode"] == 200
    assert captured["tenant_id"] == "h-dcn"
    # s5d task 4.1: allowed_scopes is now a per-dimension map. h-dcn wires a single
    # ``region`` dimension, and _EMAIL_ALL is projected all-access → {"region": ["*"]}.
    assert captured["scopes"] == {"region": ["*"]}


# ---------------------------------------------------------------------------
# Bug 2 — pagination undercount, DOMAIN layer (spec
# member-scope-stale-projection-and-pagination-undercount, task 2).
#
# Property 3 (Bug Condition): page_size means returned in-scope rows.
#
# The domain `MembershipService.list_members_page` asks the repository for ONE
# raw page of up to `page_size` rows (the Query `Limit`), THEN narrows by
# `allowed_scopes`. With a scope-narrowed caller and a partition holding MORE
# in-scope members than `page_size` interleaved with out-of-scope members, the
# raw page is scope-shrunk below `min(page_size, total_in_scope)`.
#
# CRITICAL: these tests MUST FAIL on the UNFIXED code — the failure confirms the
# Limit-before-scope-filter root cause. DO NOT fix the test or the code when it
# fails; task 5 verifies them PASSING once the fix lands.
# ---------------------------------------------------------------------------

from sam.members.domain.scope_canon import scope_canon  # noqa: E402


class _LimitHonoringPagingRepo:
    """An in-memory repo whose ``list_members_page`` honours ``limit`` like DynamoDB's Query.

    Members are ordered by ``member_id`` (the repository's natural sort-key order). ``limit``
    caps the RAW rows returned BEFORE any scope narrowing (the domain does that on top), and a
    resume cursor is surfaced via ``start_key`` so the honest multi-page walk is representable.
    This faithfully reproduces Bug 2: a scope-narrowed page of ``limit`` RAW rows is shrunk by
    the domain's post-filter.
    """

    def __init__(self):
        self._members: dict[str, dict] = {}

    def add_member(self, member):
        self._members[member["member_id"]] = dict(member)

    def _ordered(self):
        return [self._members[mid] for mid in sorted(self._members)]

    def list_members(self, tenant_id, *, filters=None):
        return [dict(m) for m in self._ordered()]

    def list_members_page(self, tenant_id, *, limit=None, start_key=None, filters=None):
        ordered = self._ordered()
        start = 0
        if start_key:
            resume = start_key.get("member_id")
            for idx, m in enumerate(ordered):
                if m["member_id"] == resume:
                    start = idx + 1
                    break
        window = ordered[start:]
        last_key = None
        if limit is not None and limit < len(window):
            window = window[:limit]
            last_key = {"member_id": window[-1]["member_id"]}
        return [dict(m) for m in window], last_key

    # Single-member reads the service may touch (unused here but part of the shape).
    def get_member(self, tenant_id, member_id):
        return self._members.get(member_id)


def _scoped_member(member_id, region):
    """A member whose h-dcn ``region`` dimension binds to its ``overlay.region`` field."""
    return {
        "member_id": member_id,
        "personal": {
            "first_name": member_id,
            "last_name": member_id,
            "email": f"{member_id}@x.com",
        },
        "membership": {"member_number": member_id, "status": "active"},
        "overlay": {"region": region},
    }


class TestBug2PaginationUndercountDomainExploration:
    def _service_with_interleaved_regions(self, *, in_scope: int, out_of_scope: int):
        """Build a service over a partition that INTERLEAVES in-scope / out-of-scope members.

        member_ids sort so North (in-scope) and South (out-of-scope) members alternate, so any
        raw page of ``page_size`` rows contains both — the post-filter then drops the South
        rows, shrinking the page below ``page_size``.
        """
        repo = _LimitHonoringPagingRepo()
        total = max(in_scope, out_of_scope) * 2
        n_in = n_out = 0
        for i in range(1, total + 1):
            mid = f"M-{i:03d}"
            if i % 2 == 1 and n_in < in_scope:
                repo.add_member(_scoped_member(mid, "North"))
                n_in += 1
            elif n_out < out_of_scope:
                repo.add_member(_scoped_member(mid, "South"))
                n_out += 1
            elif n_in < in_scope:
                repo.add_member(_scoped_member(mid, "North"))
                n_in += 1
        return MembershipService(repo)

    def test_scoped_page_returns_fewer_in_scope_rows_than_page_size(self):
        """A North-scoped caller asking page_size=50 gets fewer than min(50, total_in_scope).

        60 North (in-scope) + 60 South (out-of-scope) members, interleaved. A raw Query
        ``Limit=50`` returns 50 interleaved rows (~25 North); the scope post-filter drops the
        South rows → ~25 returned, far below min(50, 60).

        **Validates: Requirements 4.1, 4.2**

        EXPECTED (unfixed): FAIL — returned in-scope count < min(50, 60).
        """
        service = self._service_with_interleaved_regions(in_scope=60, out_of_scope=60)

        rows, _cursor = service.list_members_page(
            "h-dcn", {"region": ["North"]}, page_size=50
        )

        assert len(rows) == min(50, 60), (
            f"BUG 2 counterexample: page_size=50 for a scope-narrowed caller yielded "
            f"{len(rows)} in-scope rows (expected 50). The Query Limit bounded the RAW "
            f"partition before the domain scope filter."
        )
        assert all(
            scope_canon((r.get("overlay") or {}).get("region")) == scope_canon("North")
            for r in rows
        ), "every returned row must be in the caller's scope"

    def test_all_access_page_fills_to_page_size_when_rows_available(self):
        """An all-access caller (``["*"]``) asking page_size=50 must return 50 of 60 members.

        **Validates: Requirements 4.1, 4.4**

        EXPECTED (unfixed): PASS for a pure all-member partition (no interleaving needed), but
        pinned here as the Property-3 all-access contract (task 5 keeps it green).
        """
        repo = _LimitHonoringPagingRepo()
        for i in range(1, 61):
            repo.add_member(_scoped_member(f"M-{i:03d}", "North"))
        service = MembershipService(repo)

        rows, _cursor = service.list_members_page(
            "h-dcn", {"region": ["*"]}, page_size=50
        )

        assert len(rows) == 50, (
            f"all-access page_size=50 returned {len(rows)} rows (expected 50)."
        )

    def test_scope_narrowed_case_returns_min_page_size_total_in_scope(self):
        """When total_in_scope < page_size, the page returns exactly total_in_scope.

        15 North members interleaved with 60 South. page_size=50 → expected 15 (all in-scope),
        not the scope-shrunk subset of a raw 50-row page.

        **Validates: Requirements 4.2, 4.3**

        EXPECTED (unfixed): FAIL — fewer than 15 in-scope rows on the first raw page.
        """
        service = self._service_with_interleaved_regions(in_scope=15, out_of_scope=60)

        rows, _cursor = service.list_members_page(
            "h-dcn", {"region": ["North"]}, page_size=50
        )

        assert len(rows) == min(50, 15), (
            f"BUG 2 counterexample: expected min(page_size=50, total_in_scope=15)=15 in-scope "
            f"rows, got {len(rows)}."
        )


# ---------------------------------------------------------------------------
# Bug 2 PRESERVATION property tests — DOMAIN layer (spec
# member-scope-stale-projection-and-pagination-undercount, task 3 / Property 4).
#
# Observation-first: these encode `MembershipService.list_members_page` /
# `list_members` behaviour OBSERVED on the UNFIXED code so the task-5 fix cannot
# regress it. They MUST PASS on unfixed code (the baseline to preserve).
#
# Property 4 (Preservation): for any input where isBugCondition_paging does NOT hold, the paged
# read behaves identically. The facets owned HERE (the domain read surface):
#   6.1 guaranteed-deny scope (empty map or a `[]` dimension) → ([], None) WITHOUT paging the repo;
#   6.2 a tampered/stale cursor naming another tenant RAISES (never resumes there);
#   6.3 the per-dimension AND rule + calculated-field enrichment are applied;
#   6.4 the non-paged `list_members` path is unchanged.
# (Child-item exclusion, 6.5, is a repository concern — covered in test_members_repository.py.)
#
# Validates: Requirements 6.1, 6.2, 6.3, 6.4
# ---------------------------------------------------------------------------

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from sam.members.repository.members_cursor import (  # noqa: E402
    CursorError,
    encode_cursor,
)

# A page size drawn from the real Rows_Per_Page options plus None (the "Max" option, R25.3).
_PAGE_SIZES = st.sampled_from([1, 5, 50, 100, 250, 500, None])


class _PagingRepoSpy(_LimitHonoringPagingRepo):
    """A paging repo that RECORDS whether ``list_members_page`` was actually called.

    Used to prove the guaranteed-deny short-circuit returns ``([], None)`` WITHOUT paging the
    repository at all (R6.1) — the spy's ``paged`` flag must stay False on a deny.
    """

    def __init__(self):
        super().__init__()
        self.paged = False

    def list_members_page(self, tenant_id, *, limit=None, start_key=None, filters=None):
        self.paged = True
        return super().list_members_page(
            tenant_id, limit=limit, start_key=start_key, filters=filters
        )


def _service_with_both_regions(n_north: int = 8, n_south: int = 8):
    repo = _PagingRepoSpy()
    for i in range(1, n_north + 1):
        repo.add_member(_scoped_member(f"N-{i:03d}", "North"))
    for i in range(1, n_south + 1):
        repo.add_member(_scoped_member(f"S-{i:03d}", "South"))
    return MembershipService(repo), repo


# Guaranteed-deny scopes: the empty map, or ANY dimension whose grant is [] (deny-by-default).
_DENY_SCOPES = st.sampled_from(
    [
        {},
        {"region": []},
        {"region": [], "team": ["*"]},
        {"region": ["*"], "team": []},
    ]
)


@settings(max_examples=100)
@given(deny=_DENY_SCOPES, page_size=_PAGE_SIZES)
def test_property_guaranteed_deny_returns_empty_without_paging(deny, page_size):
    """Preservation (R6.1): a guaranteed-deny scope → ([], None) WITHOUT paging the repository.

    For ANY deny scope (empty map or a ``[]`` dimension) and ANY page size, the paged read
    returns ``([], None)`` and never asks the repository for a page (the spy stays un-paged) —
    the deny short-circuit is unchanged. This holds independent of the pagination fix.
    """
    service, repo = _service_with_both_regions()

    rows, cursor = service.list_members_page("h-dcn", deny, page_size=page_size)

    assert rows == []
    assert cursor is None
    assert repo.paged is False  # short-circuit: the repository was never paged


@settings(max_examples=100)
@given(
    page_size=_PAGE_SIZES, tamper=st.sampled_from(["other-tenant", "", "h-dcn-evil"])
)
def test_property_tampered_cursor_raises_and_never_resumes(page_size, tamper):
    """Preservation (R6.2): a cursor naming ANOTHER tenant raises CursorError (never resumes).

    For any page size, a well-formed cursor whose partition key is NOT the caller's tenant is
    rejected by the cursor codec before any repository paging — tenant isolation is unchanged.
    (A blank partition key is likewise rejected.)
    """
    service, _repo = _service_with_both_regions()
    # A structurally-valid cursor that encodes a DIFFERENT tenant's resume key.
    foreign_cursor = encode_cursor({"tenant_id": tamper, "sk": "member#X-1"})

    with pytest.raises(CursorError):
        service.list_members_page(
            "h-dcn", {"region": ["*"]}, page_size=page_size, cursor=foreign_cursor
        )


@settings(max_examples=100)
@given(page_size=_PAGE_SIZES)
def test_property_and_rule_and_enrichment_applied_on_a_page(page_size):
    """Preservation (R6.3): the per-dimension scope rule + calculated enrichment apply to a page.

    For any page size, a North-scoped caller's returned page rows are ALL in the North region
    (the scope filter is applied) and each carries the calculated ``display_name`` enrichment
    (never stored, computed on read). This behaviour is independent of how many rows a page
    returns, so it holds on both the unfixed and fixed code.
    """
    service, _repo = _service_with_both_regions(n_north=8, n_south=8)

    rows, _cursor = service.list_members_page(
        "h-dcn", {"region": ["North"]}, page_size=page_size
    )

    for r in rows:
        # AND rule: every returned row is in the caller's single-dimension scope.
        assert scope_canon((r.get("overlay") or {}).get("region")) == scope_canon(
            "North"
        )
        # Enrichment: the calculated display_name is merged in under its storage bucket.
        assert (r.get("personal") or {}).get("display_name")


@settings(max_examples=100)
@given(
    north=st.integers(min_value=0, max_value=12),
    south=st.integers(min_value=0, max_value=12),
)
def test_property_non_paged_list_members_unchanged(north, south):
    """Preservation (R6.4): the non-paged ``list_members`` path returns the full in-scope set.

    The fix is scoped to the PAGED read. For any partition of North/South members, the non-paged
    ``list_members`` for a North-scoped caller returns EXACTLY the North members (all of them,
    no Limit involved), each enriched — the established non-paged contract, unchanged.
    """
    repo = _LimitHonoringPagingRepo()
    for i in range(1, north + 1):
        repo.add_member(_scoped_member(f"N-{i:03d}", "North"))
    for i in range(1, south + 1):
        repo.add_member(_scoped_member(f"S-{i:03d}", "South"))
    service = MembershipService(repo)

    rows = service.list_members("h-dcn", {"region": ["North"]})

    assert len(rows) == north  # the full in-scope set, never Limit-bounded
    assert all(
        scope_canon((r.get("overlay") or {}).get("region")) == scope_canon("North")
        for r in rows
    )
    if rows:
        assert all((r.get("personal") or {}).get("display_name") for r in rows)
