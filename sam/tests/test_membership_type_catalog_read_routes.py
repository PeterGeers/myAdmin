"""
S5 Task 3.4 — tests for the Lidmaatschap Beheer catalog **READ routes** (design C8, R2.4/R6.1).

The tenant-scoped membership-type catalog's MANAGEMENT read surface, end-to-end
(routing → handler dispatch → domain → repository):

- ``GET /membership-types`` (list) — defaults to ALL entries (incl. soft-deleted
  ``active=false``) so an admin can see/manage retired types (contrast: task 3.3's
  ``/members/field-config`` options feed is active-only); ``?active_only=true`` narrows to
  just the assignable ones. Ordered by ``(order, type_code)``.
- ``GET /membership-types/{type_code}`` (get) — one entry (incl. a retired one), or a
  **404** for an absent code (consistent with ``get_member``'s not-found → 404).

Two layers are covered:

1. **Domain** — :meth:`MembershipService.list_membership_types` /
   :meth:`MembershipService.get_membership_type` project catalog entries to JSON-friendly
   management shapes, honour the ``active_only`` filter, and raise
   :class:`MembershipTypeNotFound` for an absent code. Both are tenant-scoped (Property 1).
2. **Edge dispatch** — a granted + authorized ``GET`` returns **200** with the data (not the
   old 501 stub); ``?active_only=true`` narrows; an absent code is **404**; an unauthenticated
   call is 401/403 (the task-3.0 gate still applies).

A tiny in-memory fake :class:`MembersRepository` (catalog surface only) backs the service —
no boto3, no AWS — mirroring the fake-repo pattern in the sibling read tests.

Validates: Requirements R2.4, R6.1
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.membership_service import (
    MembershipService,
    MembershipTypeNotFound,
)
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.handler import app


# ---------------------------------------------------------------------------
# In-memory fake repository (catalog surface only — the service depends on the Protocol)
# ---------------------------------------------------------------------------


class FakeCatalogRepository:
    """Minimal in-memory :class:`MembersRepository` exposing the catalog reads used here.

    Stores catalog entries keyed by ``tenant_id`` so a read cannot cross tenants (the same
    structural isolation the real repository enforces). ``list_membership_types`` mirrors the
    real contract: ``active_only=True`` drops soft-deleted entries; results are ordered by
    ``(order, type_code)``. ``get_membership_type`` returns the entry (incl. retired) or None.
    """

    def __init__(self):
        self.catalog: dict[str, list[MembershipTypeEntry]] = {}

    def add_type(self, tenant_id: str, entry: MembershipTypeEntry) -> None:
        self.catalog.setdefault(tenant_id, []).append(entry)

    def list_membership_types(self, tenant_id, *, active_only=False):
        entries = list(self.catalog.get(tenant_id, []))
        if active_only:
            entries = [e for e in entries if e.active]
        entries.sort(key=lambda e: e.sort_order_key())
        return entries

    def get_membership_type(self, tenant_id, type_code):
        for entry in self.catalog.get(tenant_id, []):
            if entry.type_code == type_code:
                return entry
        return None

    # -- unused-by-these-reads Protocol members (raise if touched) ----------
    def get_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_members(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def delete_member(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def get_membership(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_memberships(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def list_member_payments(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def save_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def deactivate_membership_type(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


def _entry(tenant, code, *, label=None, active=True, order=0):
    return MembershipTypeEntry(
        tenant_id=tenant,
        type_code=code,
        label=label or {"nl": code.title(), "en": code.title()},
        active=active,
        order=order,
    )


@pytest.fixture()
def repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    # Deliberately out of insertion order + one soft-deleted to pin ordering + inclusion.
    r.add_type("h-dcn", _entry("h-dcn", "donateur", label={"nl": "Donateur", "en": "Donor"}, order=20))
    r.add_type("h-dcn", _entry("h-dcn", "erelid", label={"nl": "Erelid", "en": "Honorary"}, order=10))
    r.add_type("h-dcn", _entry("h-dcn", "sponsor", label={"nl": "Sponsor", "en": "Sponsor"}, order=30))
    r.add_type("h-dcn", _entry("h-dcn", "retired", label={"nl": "Oud", "en": "Old"}, active=False, order=5))
    # A different tenant — must be structurally invisible to h-dcn's catalog.
    r.add_type("other", _entry("other", "member", order=10))
    return r


# ---------------------------------------------------------------------------
# Domain — MembershipService.list_membership_types / get_membership_type
# ---------------------------------------------------------------------------


class TestListMembershipTypesDomain:
    def test_list_all_returns_every_entry_including_retired_ordered(self, repo):
        service = MembershipService(repo)
        entries = service.list_membership_types("h-dcn")
        # ALL entries incl. active=false, ordered by (order, type_code).
        assert [e["type_code"] for e in entries] == ["retired", "erelid", "donateur", "sponsor"]

    def test_list_active_only_excludes_retired(self, repo):
        service = MembershipService(repo)
        entries = service.list_membership_types("h-dcn", active_only=True)
        assert [e["type_code"] for e in entries] == ["erelid", "donateur", "sponsor"]
        assert all(e["active"] for e in entries)

    def test_list_management_shape_carries_active_flag_and_label(self, repo):
        service = MembershipService(repo)
        entries = service.list_membership_types("h-dcn")
        retired = next(e for e in entries if e["type_code"] == "retired")
        assert retired == {
            "type_code": "retired",
            "label": {"nl": "Oud", "en": "Old"},
            "active": False,
            "order": 5,
        }

    def test_list_is_tenant_scoped(self, repo):
        service = MembershipService(repo)
        h = {e["type_code"] for e in service.list_membership_types("h-dcn")}
        other = {e["type_code"] for e in service.list_membership_types("other")}
        assert "member" not in h
        assert other == {"member"}

    def test_list_unknown_tenant_is_empty(self, repo):
        service = MembershipService(repo)
        assert service.list_membership_types("nobody") == []

    def test_list_is_json_serializable(self, repo):
        service = MembershipService(repo)
        json.dumps(service.list_membership_types("h-dcn"))  # must not raise


class TestGetMembershipTypeDomain:
    def test_get_returns_the_entry(self, repo):
        service = MembershipService(repo)
        entry = service.get_membership_type("h-dcn", "erelid")
        assert entry["type_code"] == "erelid"
        assert entry["label"] == {"nl": "Erelid", "en": "Honorary"}
        assert entry["active"] is True

    def test_get_returns_a_retired_entry_not_404(self, repo):
        # Management still shows retired types — a soft-deleted code is returned, not a 404.
        service = MembershipService(repo)
        entry = service.get_membership_type("h-dcn", "retired")
        assert entry["type_code"] == "retired"
        assert entry["active"] is False

    def test_get_absent_code_raises_not_found(self, repo):
        service = MembershipService(repo)
        with pytest.raises(MembershipTypeNotFound):
            service.get_membership_type("h-dcn", "nope")

    def test_get_is_tenant_scoped_absent_for_other_tenant(self, repo):
        # 'member' exists for tenant 'other' only — h-dcn must not see it (Property 1).
        service = MembershipService(repo)
        with pytest.raises(MembershipTypeNotFound):
            service.get_membership_type("h-dcn", "member")


# ---------------------------------------------------------------------------
# Edge dispatch — GET /membership-types and /membership-types/{type_code}
# ---------------------------------------------------------------------------


@pytest.fixture()
def inject_service(monkeypatch, repo):
    service = MembershipService(repo)
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    return service


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=("members:read",),
    groups=("Regio_All",),
    sub="admin-sub",
    query=None,
):
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": query,
        "body": None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "cognito:groups": list(groups),
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


def test_list_route_returns_200_all_entries_not_501(inject_service):
    resp = app.handler(_event("GET", "/membership-types"))
    assert resp["statusCode"] == 200
    codes = [e["type_code"] for e in _data(resp)]
    # Management default: ALL entries incl. retired, ordered.
    assert codes == ["retired", "erelid", "donateur", "sponsor"]


def test_list_route_active_only_query_narrows(inject_service):
    resp = app.handler(_event("GET", "/membership-types", query={"active_only": "true"}))
    assert resp["statusCode"] == 200
    codes = [e["type_code"] for e in _data(resp)]
    assert codes == ["erelid", "donateur", "sponsor"]
    assert "retired" not in codes


def test_list_route_active_only_false_returns_all(inject_service):
    resp = app.handler(_event("GET", "/membership-types", query={"active_only": "false"}))
    assert resp["statusCode"] == 200
    assert any(e["type_code"] == "retired" for e in _data(resp))


def test_get_route_returns_200_with_entry(inject_service):
    resp = app.handler(_event("GET", "/membership-types/erelid"))
    assert resp["statusCode"] == 200
    assert _data(resp)["type_code"] == "erelid"


def test_get_route_returns_retired_entry(inject_service):
    resp = app.handler(_event("GET", "/membership-types/retired"))
    assert resp["statusCode"] == 200
    assert _data(resp)["active"] is False


def test_get_route_absent_code_returns_404(inject_service):
    resp = app.handler(_event("GET", "/membership-types/nope"))
    assert resp["statusCode"] == 404


def test_get_route_is_tenant_scoped(inject_service):
    # 'member' exists only for tenant 'other' — a h-dcn caller gets a 404, no cross-tenant leak.
    resp = app.handler(_event("GET", "/membership-types/member", tenant="h-dcn"))
    assert resp["statusCode"] == 404


def test_list_route_tenant_isolation(inject_service):
    resp = app.handler(_event("GET", "/membership-types", tenant="other"))
    assert resp["statusCode"] == 200
    assert [e["type_code"] for e in _data(resp)] == ["member"]


def test_catalog_routes_require_auth():
    # No verified claims → 401/403 (the task-3.0 gate applies to the catalog routes too).
    resp = app.handler({"httpMethod": "GET", "path": "/membership-types", "headers": {}})
    assert resp["statusCode"] in (401, 403)


def test_list_route_denies_without_read_capability(inject_service):
    # A caller with no members:read grant is forbidden (capability gate at the edge).
    resp = app.handler(_event("GET", "/membership-types", capabilities=("members:write",)))
    assert resp["statusCode"] == 403
