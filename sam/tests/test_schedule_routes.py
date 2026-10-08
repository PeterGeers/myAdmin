"""
Tests for the member schedule CRUD routes (R5 — pivot-output-actions task 5.2), end-to-end
through the thin edge over the SAME faithful in-memory ``FakeDynamoTable`` +
``DynamoDbMembersRepository`` + real ``MembershipService`` the analytics-set / template route
tests use (no mocks).

What this closes:

1. **Schedule CRUD routes** (the SPECIAL R5 gate — admin OR write+all-regions):
   - ``POST /members/schedules`` — create; returns the serialized schedule with a
     server-generated ``schedule_id``; a set with NO delivery block is a **422**.
   - ``GET /members/schedules`` — list the tenant's schedules.
   - ``GET /members/schedules/{schedule_id}`` — one schedule; **404** for an absent id.
   - ``PUT /members/schedules/{schedule_id}`` — update (toggle enabled / cron); **404** absent;
     re-pointing at a set with no delivery is **422**.
   - ``DELETE /members/schedules/{schedule_id}`` — hard delete; a subsequent get is **404**.

2. **The R5 GATE** (the critical rule): ``members:admin`` OR (``members:write`` + the ``["*"]``
   all-regions scope grant). A region-NARROWED ``members:write`` caller (region ``["East"]``)
   is REJECTED (403) — an unattended scheduled run must never replay a partial regional slice.
   A read-only / export-only caller is 403.

3. **The precondition** (R5): a schedule is only schedulable for a set that HAS a delivery
   block (task 5.1 left this to the service — enforced on create + a set_id-changing update).

4. **Cross-tenant isolation**: a schedule created for one tenant is invisible to another.

5. **EventBridge-Scheduler lifecycle wiring** (R5, task 5.3): with a SchedulerApiPort injected,
   create/update/delete_schedule drive the port (create → CreateSchedule after the record is
   persisted, rolling the record back if the schedule call fails; update → UpdateSchedule with
   the new cron/enabled; delete → DeleteSchedule before the record). The port is a FAKE — no
   AWS / EventBridge is touched.

Validates: Requirements R5.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.execute_and_deliver import DeliveryNotConfigured
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import (
    MembershipService,
    ScheduleNotFound,
)
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.handler import app
from sam.members.repository.members_repository import DynamoDbMembersRepository
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks

# The faithful in-memory DynamoDB fake.
from sam.tests.test_members_repository import FakeDynamoTable

# ── Service wired like production: real repo over the fake table + h-dcn config/hooks ──


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


@pytest.fixture()
def hooks() -> TenantHookRegistry:
    return register_hdcn_hooks(TenantHookRegistry())


@pytest.fixture()
def service(repo, hooks) -> MembershipService:
    return MembershipService(
        repo,
        lifecycle_provider=StaticLifecycleConfigProvider(
            {"h-dcn": HDCN_LIFECYCLE_CONFIG}
        ),
        tenant_hooks=hooks,
    )


# Scope travels the caller's verified EMAIL via the PROJECTED grants (design C5). The R5
# schedule gate needs the resolved region grant to be the ["*"] wildcard for the members:write
# path — so the walkthrough wires an all-access email and a region-narrowed email.
_EMAIL_ALL = "all@h-dcn.test"  # all-access → region ["*"]
_EMAIL_EAST = "east@h-dcn.test"  # region-narrowed → region ["East"]

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
    ("h-dcn", _EMAIL_EAST): {"region": ["East"]},
    # A caller with no region entry → deny-by-default (absent grant).
}


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, service):
    from sam.tests.conftest import FakeScopeGrantsReader

    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


_ADMIN_CAPS = ("members:read", "members:write", "members:admin", "members:export")


def _event(
    method,
    path,
    *,
    tenant="h-dcn",
    capabilities=_ADMIN_CAPS,
    email=_EMAIL_ALL,
    sub="admin-sub",
    body=None,
    query=None,
):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants)."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "cognito:groups": [],
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


# ── Fixtures: a set WITH a delivery block, and one WITHOUT ────────────────────────────


def _count_definition():
    return {
        "data_source": "members",
        "group_columns": ["membership_type"],
        "aggregate_measures": [{"function": "COUNT", "column": "*"}],
        "filters": {},
        "column_pivot": None,
        "column_nest_levels": [],
        "display_mode": "flat",
        "include_rollup": False,
    }


def _seed_set_with_delivery(service, tenant="h-dcn") -> str:
    """Create a saved set and store a `to_fixed` delivery block on it; return its set_id."""
    created = service.create_analytics_set(
        tenant,
        {"name": "Monthly clubblad", "kind": "count", "definition": _count_definition()},
    )
    set_id = created["set_id"]
    service.set_analytics_set_delivery(
        tenant,
        set_id,
        {
            "mode": "to_fixed",
            "attachment": "csv",
            "recipients": ["agent@example.com"],
        },
    )
    return set_id


def _seed_set_without_delivery(service, tenant="h-dcn") -> str:
    """Create a saved set with NO delivery block; return its set_id."""
    created = service.create_analytics_set(
        tenant,
        {"name": "No delivery", "kind": "count", "definition": _count_definition()},
    )
    return created["set_id"]


# =====================================================================================
# Schedule CRUD — domain layer (MembershipService / SchedulesMixin)
# =====================================================================================


class TestScheduleDomain:
    def test_create_persists_and_returns_serialized_shape(self, service, repo):
        set_id = _seed_set_with_delivery(service)
        out = service.create_schedule(
            "h-dcn",
            {"set_id": set_id, "cron": "cron(0 9 1 * ? *)"},
            created_by="sub-123",
        )
        assert out["set_id"] == set_id
        assert out["cron"] == "cron(0 9 1 * ? *)"
        assert out["enabled"] is True  # default
        assert out["created_by"] == "sub-123"  # attribution from the edge
        assert out["schedule_id"]  # server-generated
        assert out["created_at"] and out["updated_at"]
        assert repo.get_schedule("h-dcn", out["schedule_id"]) is not None

    def test_create_generates_distinct_server_ids(self, service):
        set_id = _seed_set_with_delivery(service)
        a = service.create_schedule("h-dcn", {"set_id": set_id, "cron": "rate(1 day)"})
        b = service.create_schedule("h-dcn", {"set_id": set_id, "cron": "rate(1 day)"})
        assert a["schedule_id"] != b["schedule_id"]  # uuid4 — no collision

    def test_create_ignores_body_tenant_and_schedule_id(self, service, repo):
        set_id = _seed_set_with_delivery(service)
        out = service.create_schedule(
            "h-dcn",
            {
                "set_id": set_id,
                "cron": "rate(1 day)",
                "tenant_id": "evil",
                "schedule_id": "client-chosen",
            },
        )
        assert out["schedule_id"] != "client-chosen"  # server-generated, body ignored
        assert repo.get_schedule("evil", out["schedule_id"]) is None

    def test_create_for_set_without_delivery_raises_422(self, service):
        set_id = _seed_set_without_delivery(service)
        with pytest.raises(DeliveryNotConfigured):
            service.create_schedule("h-dcn", {"set_id": set_id, "cron": "rate(1 day)"})

    def test_create_for_absent_set_raises_422(self, service):
        with pytest.raises(DeliveryNotConfigured):
            service.create_schedule("h-dcn", {"set_id": "ghost", "cron": "rate(1 day)"})

    def test_update_toggles_enabled_and_bumps_updated_at(self, service):
        set_id = _seed_set_with_delivery(service)
        created = service.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
        )
        updated = service.update_schedule(
            "h-dcn", created["schedule_id"], {"enabled": False}
        )
        assert updated["enabled"] is False
        assert updated["created_at"] == created["created_at"]
        assert updated["updated_at"] >= created["updated_at"]

    def test_update_preserves_created_by(self, service):
        set_id = _seed_set_with_delivery(service)
        created = service.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}, created_by="author"
        )
        updated = service.update_schedule(
            "h-dcn", created["schedule_id"], {"cron": "rate(7 days)"}
        )
        assert updated["created_by"] == "author"  # attribution survives an edit

    def test_update_repoint_to_set_without_delivery_raises_422(self, service):
        set_id = _seed_set_with_delivery(service)
        bad_set = _seed_set_without_delivery(service)
        created = service.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
        )
        with pytest.raises(DeliveryNotConfigured):
            service.update_schedule(
                "h-dcn", created["schedule_id"], {"set_id": bad_set}
            )

    def test_update_same_set_does_not_recheck_delivery(self, service):
        # An edit that keeps the SAME set_id does not re-resolve the set's delivery (only a
        # set_id change does). Toggling enabled on the existing set succeeds.
        set_id = _seed_set_with_delivery(service)
        created = service.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
        )
        out = service.update_schedule(
            "h-dcn", created["schedule_id"], {"enabled": False}
        )
        assert out["enabled"] is False

    def test_update_absent_raises_not_found(self, service):
        with pytest.raises(ScheduleNotFound):
            service.update_schedule("h-dcn", "ghost", {"enabled": False})

    def test_delete_absent_raises_not_found(self, service):
        with pytest.raises(ScheduleNotFound):
            service.delete_schedule("h-dcn", "ghost")

    def test_schedules_are_isolated_per_tenant(self, service, repo):
        set_a = _seed_set_with_delivery(service, tenant="tenant-a")
        set_b = _seed_set_with_delivery(service, tenant="tenant-b")
        sa = service.create_schedule(
            "tenant-a", {"set_id": set_a, "cron": "rate(1 day)"}
        )
        service.create_schedule("tenant-b", {"set_id": set_b, "cron": "rate(1 day)"})
        # tenant-a's schedule is invisible to tenant-b.
        assert repo.get_schedule("tenant-b", sa["schedule_id"]) is None
        a_ids = [s["schedule_id"] for s in service.list_schedules("tenant-a")]
        assert sa["schedule_id"] in a_ids


# =====================================================================================
# Schedule CRUD — edge dispatch (routes → handler → domain → repo)
# =====================================================================================


class TestScheduleEdge:
    def test_create_returns_200_with_server_generated_id(self, service):
        set_id = _seed_set_with_delivery(service)
        resp = app.handler(
            _event(
                "POST",
                "/members/schedules",
                body={"set_id": set_id, "cron": "cron(0 9 1 * ? *)"},
            )
        )
        assert resp["statusCode"] == 200
        data = _data(resp)
        assert data["set_id"] == set_id
        assert data["schedule_id"]  # server-generated

    def test_create_stamps_created_by_from_token_sub(self, service):
        set_id = _seed_set_with_delivery(service)
        resp = app.handler(
            _event(
                "POST",
                "/members/schedules",
                sub="webmaster-sub",
                body={
                    "set_id": set_id,
                    "cron": "rate(1 day)",
                    "created_by": "spoofed",  # body attempt is ignored
                },
            )
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["created_by"] == "webmaster-sub"

    def test_create_for_set_without_delivery_returns_422(self, service):
        set_id = _seed_set_without_delivery(service)
        resp = app.handler(
            _event(
                "POST",
                "/members/schedules",
                body={"set_id": set_id, "cron": "rate(1 day)"},
            )
        )
        assert resp["statusCode"] == 422

    def test_list_returns_the_tenants_schedules(self, service):
        set_id = _seed_set_with_delivery(service)
        app.handler(
            _event(
                "POST", "/members/schedules", body={"set_id": set_id, "cron": "rate(1 day)"}
            )
        )
        resp = app.handler(_event("GET", "/members/schedules"))
        assert resp["statusCode"] == 200
        assert len(_data(resp)) == 1

    def test_get_by_id_returns_200(self, service):
        set_id = _seed_set_with_delivery(service)
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/schedules",
                    body={"set_id": set_id, "cron": "rate(1 day)"},
                )
            )
        )
        resp = app.handler(
            _event("GET", f"/members/schedules/{created['schedule_id']}")
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["set_id"] == set_id

    def test_get_absent_returns_404(self):
        resp = app.handler(_event("GET", "/members/schedules/ghost"))
        assert resp["statusCode"] == 404

    def test_update_toggles_enabled(self, service):
        set_id = _seed_set_with_delivery(service)
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/schedules",
                    body={"set_id": set_id, "cron": "rate(1 day)"},
                )
            )
        )
        resp = app.handler(
            _event(
                "PUT",
                f"/members/schedules/{created['schedule_id']}",
                body={"enabled": False},
            )
        )
        assert resp["statusCode"] == 200
        assert _data(resp)["enabled"] is False

    def test_update_absent_returns_404(self):
        resp = app.handler(
            _event("PUT", "/members/schedules/ghost", body={"enabled": False})
        )
        assert resp["statusCode"] == 404

    def test_delete_removes_it_subsequent_get_404(self, service):
        set_id = _seed_set_with_delivery(service)
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/schedules",
                    body={"set_id": set_id, "cron": "rate(1 day)"},
                )
            )
        )
        sched_id = created["schedule_id"]
        resp = app.handler(_event("DELETE", f"/members/schedules/{sched_id}"))
        assert resp["statusCode"] == 200
        assert (
            app.handler(_event("GET", f"/members/schedules/{sched_id}"))["statusCode"]
            == 404
        )

    def test_delete_absent_returns_404(self):
        resp = app.handler(_event("DELETE", "/members/schedules/ghost"))
        assert resp["statusCode"] == 404

    def test_routes_require_auth(self):
        resp = app.handler(
            {"httpMethod": "GET", "path": "/members/schedules", "headers": {}}
        )
        assert resp["statusCode"] in (401, 403)

    def test_schedule_route_not_shadowed_by_member_route(self, service):
        # The literal /members/schedules must resolve to the schedule create, NOT be swallowed
        # by /members/{member_id}. A successful 200 create proves the ordering.
        set_id = _seed_set_with_delivery(service)
        resp = app.handler(
            _event(
                "POST", "/members/schedules", body={"set_id": set_id, "cron": "rate(1 day)"}
            )
        )
        assert resp["statusCode"] == 200


# =====================================================================================
# The R5 GATE — admin OR (write + ["*"] all-regions); region-narrowed write REJECTED
# =====================================================================================


class TestScheduleGate:
    """The CRITICAL R5 rule: scheduling needs TENANT-WIDE member access — members:admin, OR
    members:write WITH the ["*"] all-regions grant. A region-narrowed members:write caller is
    REJECTED (403): an unattended scheduled run must never replay a partial regional slice."""

    def _create(self, service, *, capabilities, email):
        set_id = _seed_set_with_delivery(service)
        return app.handler(
            _event(
                "POST",
                "/members/schedules",
                capabilities=capabilities,
                email=email,
                body={"set_id": set_id, "cron": "rate(1 day)"},
            )
        )

    def test_admin_can_schedule(self, service):
        # members:admin is tenant-wide by definition — passes regardless of scope grant.
        resp = self._create(
            service, capabilities=("members:read", "members:admin"), email=_EMAIL_ALL
        )
        assert resp["statusCode"] == 200

    def test_admin_can_schedule_even_with_narrowed_region(self, service):
        # Admin needs no all-regions grant — the capability itself is tenant-wide. Even keyed
        # to the East-scoped email, an admin passes (scope is not consulted for admin).
        resp = self._create(
            service, capabilities=("members:read", "members:admin"), email=_EMAIL_EAST
        )
        assert resp["statusCode"] == 200

    def test_write_with_all_regions_can_schedule(self, service):
        resp = self._create(
            service, capabilities=("members:read", "members:write"), email=_EMAIL_ALL
        )
        assert resp["statusCode"] == 200

    def test_write_with_narrowed_region_is_rejected_403(self, service):
        # THE critical rejection: members:write but region ["East"] (not ["*"]) → 403. A
        # partial regional slice must never run unattended.
        resp = self._create(
            service, capabilities=("members:read", "members:write"), email=_EMAIL_EAST
        )
        assert resp["statusCode"] == 403

    def test_write_with_no_region_grant_is_rejected_403(self, service):
        # members:write but NO region grant at all (unknown email → absent grant → deny) → 403.
        resp = self._create(
            service,
            capabilities=("members:read", "members:write"),
            email="nogrant@h-dcn.test",
        )
        assert resp["statusCode"] == 403

    def test_read_only_caller_is_rejected_403(self, service):
        resp = self._create(
            service, capabilities=("members:read",), email=_EMAIL_ALL
        )
        assert resp["statusCode"] == 403

    def test_export_only_caller_is_rejected_403(self, service):
        # Export lets you store/run a delivery, but NOT schedule (that needs admin/write).
        resp = self._create(
            service, capabilities=("members:read", "members:export"), email=_EMAIL_ALL
        )
        assert resp["statusCode"] == 403

    def test_gate_applies_to_reads_too(self, service):
        # The gate guards the WHOLE schedule surface (not just create): a read-only caller
        # cannot even LIST schedules.
        resp = app.handler(
            _event("GET", "/members/schedules", capabilities=("members:read",))
        )
        assert resp["statusCode"] == 403

    def test_write_all_regions_can_list(self, service):
        resp = app.handler(
            _event(
                "GET",
                "/members/schedules",
                capabilities=("members:read", "members:write"),
                email=_EMAIL_ALL,
            )
        )
        assert resp["statusCode"] == 200

    def test_write_narrowed_region_cannot_delete(self, service):
        # Seed a schedule as admin, then a narrowed-region write caller is 403 on delete.
        set_id = _seed_set_with_delivery(service)
        created = _data(
            app.handler(
                _event(
                    "POST",
                    "/members/schedules",
                    body={"set_id": set_id, "cron": "rate(1 day)"},
                )
            )
        )
        resp = app.handler(
            _event(
                "DELETE",
                f"/members/schedules/{created['schedule_id']}",
                capabilities=("members:read", "members:write"),
                email=_EMAIL_EAST,
            )
        )
        assert resp["statusCode"] == 403


# =====================================================================================
# Edge gate helpers — unit cover for the combined capability+scope decision
# =====================================================================================


class TestScheduleGateHelpers:
    def test_scopes_are_all_regions_true_for_wildcard(self):
        assert app._scopes_are_all_regions({"region": ["*"]}) is True

    def test_scopes_are_all_regions_false_for_subset(self):
        assert app._scopes_are_all_regions({"region": ["East"]}) is False

    def test_scopes_are_all_regions_false_for_empty_map(self):
        assert app._scopes_are_all_regions({}) is False

    def test_scopes_are_all_regions_false_for_deny(self):
        assert app._scopes_are_all_regions({"region": []}) is False

    def test_scopes_are_all_regions_requires_all_dimensions_wildcard(self):
        # Multi-dimension: every axis must be ["*"]; one narrowed axis fails the whole gate.
        assert (
            app._scopes_are_all_regions({"region": ["*"], "season": ["2024"]}) is False
        )
        assert app._scopes_are_all_regions({"region": ["*"], "season": ["*"]}) is True


# =====================================================================================
# EventBridge-Scheduler lifecycle wiring (R5, task 5.3) — the SchedulerApiPort is driven
# =====================================================================================
#
# With a SchedulerApiPort injected into the MembershipService, the schedule CRUD surface
# materializes / updates / deletes the ONE EventBridge schedule behind each schedule#<id>
# record. These tests build the SAME real service over the fake repo but ALSO inject a FAKE
# scheduler port (no AWS / EventBridge) and assert the create/update/delete call shapes +
# the create-order rollback. The port's own call shape (CreateSchedule/UpdateSchedule/
# DeleteSchedule against boto3) is covered in test_scheduled_run.py — here we pin that the
# DOMAIN lifecycle drives the port correctly.


class FakeSchedulerApi:
    """In-memory :class:`SchedulerApiPort` that records the create/update/delete calls (no AWS).

    Structurally satisfies the port (``create_schedule`` / ``update_schedule`` /
    ``delete_schedule``), so the service depends on the shape, not this class. Records each call
    as a tuple so a test can assert the lifecycle drove the port with the right ids / cron /
    enabled. ``fail_create`` makes the next create raise, to exercise the create-order rollback.
    """

    def __init__(self):
        self.created: list[tuple] = []
        self.updated: list[tuple] = []
        self.deleted: list[tuple] = []
        self.fail_create = False

    def create_schedule(self, tenant_id, schedule_id, cron, *, enabled=True):
        if self.fail_create:
            raise RuntimeError("CreateSchedule blew up")
        self.created.append((tenant_id, schedule_id, cron, enabled))
        return f"m-{tenant_id}-{schedule_id}"

    def update_schedule(self, tenant_id, schedule_id, cron, *, enabled=True):
        self.updated.append((tenant_id, schedule_id, cron, enabled))
        return f"m-{tenant_id}-{schedule_id}"

    def delete_schedule(self, tenant_id, schedule_id):
        self.deleted.append((tenant_id, schedule_id))


@pytest.fixture()
def scheduler() -> FakeSchedulerApi:
    return FakeSchedulerApi()


@pytest.fixture()
def service_with_scheduler(repo, hooks, scheduler) -> MembershipService:
    """The real service, built like production but with the FAKE scheduler port injected."""
    return MembershipService(
        repo,
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        tenant_hooks=hooks,
        scheduler_port=scheduler,
    )


class TestScheduleLifecycleDrivesScheduler:
    def test_port_conformance(self, scheduler):
        from sam.members.repository.scheduler_api import SchedulerApiPort

        assert isinstance(scheduler, SchedulerApiPort)

    def test_create_materializes_the_eventbridge_schedule(
        self, service_with_scheduler, scheduler
    ):
        set_id = _seed_set_with_delivery(service_with_scheduler)
        out = service_with_scheduler.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "cron(0 9 1 * ? *)", "enabled": True}
        )
        # CreateSchedule was called ONCE, keyed by the record's (tenant, schedule_id) with the
        # record's cron + enabled.
        assert len(scheduler.created) == 1
        tenant_id, schedule_id, cron, enabled = scheduler.created[0]
        assert tenant_id == "h-dcn"
        assert schedule_id == out["schedule_id"]
        assert cron == "cron(0 9 1 * ? *)"
        assert enabled is True

    def test_create_disabled_schedule_is_materialized_disabled(
        self, service_with_scheduler, scheduler
    ):
        set_id = _seed_set_with_delivery(service_with_scheduler)
        service_with_scheduler.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(30 days)", "enabled": False}
        )
        assert scheduler.created[0][3] is False  # enabled flag flows through

    def test_create_persists_record_before_the_schedule(
        self, service_with_scheduler, scheduler, repo
    ):
        set_id = _seed_set_with_delivery(service_with_scheduler)
        out = service_with_scheduler.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
        )
        # Both the record and the schedule exist after a successful create.
        assert repo.get_schedule("h-dcn", out["schedule_id"]) is not None
        assert len(scheduler.created) == 1

    def test_create_rolls_back_the_record_when_the_schedule_fails(
        self, service_with_scheduler, scheduler, repo
    ):
        # The scheduler call fails → the just-persisted record must be rolled back so no
        # schedule#<id> lingers without a live EventBridge schedule, and the error surfaces.
        scheduler.fail_create = True
        set_id = _seed_set_with_delivery(service_with_scheduler)
        with pytest.raises(RuntimeError):
            service_with_scheduler.create_schedule(
                "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
            )
        # No schedule record survived the failed create (rollback), and none was listed.
        assert service_with_scheduler.list_schedules("h-dcn") == []

    def test_update_pushes_cron_and_enabled_to_the_schedule(
        self, service_with_scheduler, scheduler
    ):
        set_id = _seed_set_with_delivery(service_with_scheduler)
        created = service_with_scheduler.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
        )
        service_with_scheduler.update_schedule(
            "h-dcn", created["schedule_id"], {"cron": "cron(0 9 1 * ? *)", "enabled": False}
        )
        assert len(scheduler.updated) == 1
        tenant_id, schedule_id, cron, enabled = scheduler.updated[0]
        assert tenant_id == "h-dcn"
        assert schedule_id == created["schedule_id"]
        assert cron == "cron(0 9 1 * ? *)"
        assert enabled is False

    def test_delete_removes_the_schedule_and_the_record(
        self, service_with_scheduler, scheduler, repo
    ):
        set_id = _seed_set_with_delivery(service_with_scheduler)
        created = service_with_scheduler.create_schedule(
            "h-dcn", {"set_id": set_id, "cron": "rate(1 day)"}
        )
        sched_id = created["schedule_id"]
        service_with_scheduler.delete_schedule("h-dcn", sched_id)
        # DeleteSchedule was called for exactly this record, and the record is gone.
        assert scheduler.deleted == [("h-dcn", sched_id)]
        assert repo.get_schedule("h-dcn", sched_id) is None

    def test_crud_without_a_scheduler_port_is_record_only(self, service, scheduler):
        # The default service (no scheduler_port) must still do pure record CRUD — it never
        # touches the fake port (which it was not given). This preserves the pre-5.3 behaviour
        # and the auth-only / unit tests that build the service without AWS wiring.
        set_id = _seed_set_with_delivery(service)
        created = service.create_schedule("h-dcn", {"set_id": set_id, "cron": "rate(1 day)"})
        service.update_schedule("h-dcn", created["schedule_id"], {"enabled": False})
        service.delete_schedule("h-dcn", created["schedule_id"])
        # The fake we did NOT inject saw nothing.
        assert scheduler.created == [] and scheduler.updated == [] and scheduler.deleted == []
