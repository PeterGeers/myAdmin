"""
SAM pytest for the R5 scheduled-run path (pivot-output-actions task 5.3) — the EventBridge-
Scheduler trigger entrypoint + the scheduled-run service glue + the scheduler-API port.

Phase 5 testing (tasks.md): "scheduled run reuses the P4 path and audits as unattended". These
exercise the trigger through its three injected ports — a tenant-scoped FAKE schedule store, a
fake execute-and-deliver port (the SAME surface the deliver route uses), and a fake audit sink —
with NO AWS/boto3 and NO real EventBridge/SQS. The heart of R5:

  * a scheduler-invocation event drives execute_and_deliver for the schedule's set (the fake
    captures the delegated call);
  * a DISABLED schedule is a NO-OP (no delegate, no job);
  * a MISSING record is a quiet no-op (a lingering schedule for a deleted record must not crash);
  * the tenant is PINNED from the stored record (never a partial scope — the run is tenant-wide);
  * the run is audited UNATTENDED (metadata-only — actor sentinel, no member data).

Also pins the scheduler-API port's call shape (CreateSchedule/UpdateSchedule/DeleteSchedule) via
an in-memory fake, and the trigger's event-shape detection (a foreign event is rejected loudly).

Validates: Requirements R5
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

from sam.members.domain.schedule import ScheduleEntry
from sam.members.domain.scheduled_run import (
    SCHEDULED_RUN_ACTOR,
    ExecuteAndDeliver,
    ScheduledRunOutcome,
    ScheduledRunService,
    ScheduleStore,
)
from sam.members.repository.scheduler_api import (
    SCHEDULER_EVENT_SOURCE,
    EventBridgeSchedulerApi,
    SchedulerApiPort,
    build_schedule_name,
    build_schedule_target_input,
)

TENANT = "h-dcn"
SCHEDULE_ID = "sch-1"
SET_ID = "set-9"


# ── fakes (the injected ports) ──────────────────────────────────────────────────────────


class FakeScheduleStore:
    """A tenant-scoped fake schedule store that pins ``tenant_id`` like the real repository.

    Holds schedule records keyed by ``(tenant_id, schedule_id)`` so a cross-tenant read is
    structurally impossible (Property 1), and RECORDS every lookup so a test can assert the
    read was keyed by the authoritative tenant.
    """

    def __init__(self):
        self._records: dict[tuple, ScheduleEntry] = {}
        self.get_calls: list[tuple] = []

    def put(self, entry: ScheduleEntry) -> None:
        self._records[(entry.tenant_id, entry.schedule_id)] = entry

    def get_schedule(self, tenant_id, schedule_id):
        self.get_calls.append((tenant_id, schedule_id))
        return self._records.get((tenant_id, schedule_id))


class _FakeDeliveryOutcome:
    """A stand-in for the service's DeliveryOutcome (what the deliver path returns)."""

    def __init__(self, run_id, mode="per_recipient", enqueued=3, skipped_no_address=0):
        self.run_id = run_id
        self.mode = mode
        self.enqueued = enqueued
        self.skipped_no_address = skipped_no_address
        self.job_ids = tuple(f"job-{i}" for i in range(enqueued))


class FakeExecuteAndDeliver:
    """A fake execute-and-deliver port that CAPTURES the delegated call (the shared send path)."""

    def __init__(self):
        self.calls: list[tuple] = []

    def execute_and_deliver(self, tenant_id, set_id, run_id):
        self.calls.append((tenant_id, set_id, run_id))
        return _FakeDeliveryOutcome(run_id)


class FakeAudit:
    """An in-memory audit sink matching ``log_analytics_output``'s keyword signature."""

    def __init__(self):
        self.records: list[dict] = []

    def __call__(self, *, actor, tenant, output_kind, set_key=None, record_count=None):
        self.records.append(
            {
                "actor": actor,
                "tenant": tenant,
                "output_kind": output_kind,
                "set_key": set_key,
                "record_count": record_count,
            }
        )


def _entry(**overrides):
    base = {
        "tenant_id": TENANT,
        "schedule_id": SCHEDULE_ID,
        "set_id": SET_ID,
        "cron": "cron(0 8 1 * ? *)",
        "created_by": "sub-1",
        "enabled": True,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return ScheduleEntry(**base)


@pytest.fixture()
def store():
    return FakeScheduleStore()


@pytest.fixture()
def deliver():
    return FakeExecuteAndDeliver()


@pytest.fixture()
def audit():
    return FakeAudit()


# ── port conformance ────────────────────────────────────────────────────────────────────


class TestPortConformance:
    def test_fake_store_satisfies_schedule_store_port(self, store):
        assert isinstance(store, ScheduleStore)

    def test_fake_deliver_satisfies_execute_and_deliver_port(self, deliver):
        assert isinstance(deliver, ExecuteAndDeliver)


# ── a scheduled firing drives execute_and_deliver for the schedule's set ──────────────────


class TestScheduledRunDrivesDeliver:
    def test_enabled_schedule_runs_the_shared_deliver_path_for_the_set(
        self, store, deliver, audit
    ):
        store.put(_entry())
        service = ScheduledRunService(store, deliver, audit)

        outcome = service.run_scheduled(TENANT, SCHEDULE_ID)

        assert isinstance(outcome, ScheduledRunOutcome)
        assert outcome.ran is True
        assert outcome.skipped_reason is None
        # The SAME execute-and-deliver surface the deliver route uses was called ONCE, for the
        # record's set, pinned to the record's tenant.
        assert len(deliver.calls) == 1
        tenant_id, set_id, run_id = deliver.calls[0]
        assert tenant_id == TENANT
        assert set_id == SET_ID
        assert run_id == outcome.run_id
        # The run id is a traceable scheduled-run id folded into the send path's job ids.
        assert run_id.startswith(f"schedule:{SCHEDULE_ID}:")

    def test_run_id_is_unique_per_firing(self, store, deliver, audit):
        store.put(_entry())
        service = ScheduledRunService(store, deliver, audit)
        a = service.run_scheduled(TENANT, SCHEDULE_ID)
        b = service.run_scheduled(TENANT, SCHEDULE_ID)
        assert a.run_id != b.run_id  # each firing is its own logical run


# ── a disabled schedule is a NO-OP ────────────────────────────────────────────────────────


class TestDisabledIsNoOp:
    def test_disabled_schedule_does_not_deliver_or_audit(self, store, deliver, audit):
        store.put(_entry(enabled=False))
        service = ScheduledRunService(store, deliver, audit)

        outcome = service.run_scheduled(TENANT, SCHEDULE_ID)

        assert outcome.ran is False
        assert outcome.skipped_reason == "disabled"
        assert deliver.calls == []  # the send path was NOT invoked
        assert audit.records == []  # a no-op is not an unattended run

    def test_missing_record_is_a_quiet_no_op(self, store, deliver, audit):
        # No record seeded — a lingering EventBridge schedule for a deleted record must not crash.
        service = ScheduledRunService(store, deliver, audit)

        outcome = service.run_scheduled(TENANT, "gone")

        assert outcome.ran is False
        assert outcome.skipped_reason == "not_found"
        assert deliver.calls == []
        assert audit.records == []


# ── tenant pinning (Property 1 — the run is tenant-wide, no partial scope) ─────────────────


class TestTenantPinning:
    def test_record_read_is_keyed_by_the_authoritative_tenant(
        self, store, deliver, audit
    ):
        store.put(_entry())
        service = ScheduledRunService(store, deliver, audit)

        service.run_scheduled(TENANT, SCHEDULE_ID)

        assert store.get_calls == [(TENANT, SCHEDULE_ID)]

    def test_another_tenants_schedule_is_not_found(self, store, deliver, audit):
        store.put(_entry())  # seeded under h-dcn
        service = ScheduledRunService(store, deliver, audit)

        outcome = service.run_scheduled("other-tenant", SCHEDULE_ID)

        assert outcome.ran is False
        assert outcome.skipped_reason == "not_found"
        assert deliver.calls == []


# ── unattended audit (metadata-only, reuses task 4.3) ─────────────────────────────────────


class TestUnattendedAudit:
    def test_run_audits_as_unattended_metadata_only(self, store, deliver, audit):
        store.put(_entry())
        service = ScheduledRunService(store, deliver, audit)

        service.run_scheduled(TENANT, SCHEDULE_ID)

        assert len(audit.records) == 1
        rec = audit.records[0]
        assert rec["actor"] == SCHEDULED_RUN_ACTOR == "UNATTENDED"
        assert rec["tenant"] == TENANT
        assert rec["output_kind"] == "ses_mail"
        assert rec["set_key"] == SET_ID
        # Metadata-only: the run-level audit carries ids + a (null) count — never member data,
        # never addresses, never merge values (the sink only knows ids).
        assert rec["record_count"] is None
        assert set(rec.keys()) == {
            "actor",
            "tenant",
            "output_kind",
            "set_key",
            "record_count",
        }

    def test_audit_happens_even_if_delivery_later_raises(self, store, audit):
        store.put(_entry())

        class Boom:
            def execute_and_deliver(self, *a, **k):
                raise RuntimeError("enqueue blew up")

        service = ScheduledRunService(store, Boom(), audit)
        with pytest.raises(RuntimeError):
            service.run_scheduled(TENANT, SCHEDULE_ID)
        # The UNATTENDED run was audited BEFORE the enqueue, so it is recorded even on failure.
        assert len(audit.records) == 1
        assert audit.records[0]["actor"] == "UNATTENDED"


# ── the trigger entrypoint (thin adapter — event-shape detection + delegation) ────────────


class TestTriggerEntrypoint:
    @pytest.fixture()
    def wired(self, monkeypatch, store, deliver, audit):
        """Wire the entrypoint over a service built on the fakes (no AWS)."""
        import sam.members.handler.scheduler_app as scheduler_app

        service = ScheduledRunService(store, deliver, audit)
        monkeypatch.setattr(
            scheduler_app, "get_scheduled_run_service", lambda: service
        )
        return scheduler_app, store, deliver, audit

    def test_firing_event_delegates_to_the_service(self, wired):
        scheduler_app, store, deliver, _audit = wired
        store.put(_entry())
        event = {
            "source": SCHEDULER_EVENT_SOURCE,
            "tenant_id": TENANT,
            "schedule_id": SCHEDULE_ID,
        }

        result = scheduler_app.handler(event)

        assert result["ran"] is True
        assert result["schedule_id"] == SCHEDULE_ID
        assert len(deliver.calls) == 1
        assert deliver.calls[0][0] == TENANT
        assert deliver.calls[0][1] == SET_ID

    def test_disabled_firing_reports_skip(self, wired):
        scheduler_app, store, deliver, _audit = wired
        store.put(_entry(enabled=False))
        event = {
            "source": SCHEDULER_EVENT_SOURCE,
            "tenant_id": TENANT,
            "schedule_id": SCHEDULE_ID,
        }

        result = scheduler_app.handler(event)

        assert result["ran"] is False
        assert result["skipped_reason"] == "disabled"
        assert deliver.calls == []

    def test_foreign_event_is_rejected_loudly(self, wired):
        scheduler_app, _store, _deliver, _audit = wired
        # An API-GW-proxy-ish event (no members-schedule source) must not silently run or skip.
        with pytest.raises(scheduler_app.ScheduledInvocationError):
            scheduler_app.handler({"httpMethod": "GET", "path": "/members"})

    def test_missing_ids_are_rejected(self, wired):
        scheduler_app, _store, _deliver, _audit = wired
        with pytest.raises(scheduler_app.ScheduledInvocationError):
            scheduler_app.handler({"source": SCHEDULER_EVENT_SOURCE, "tenant_id": "t"})
        with pytest.raises(scheduler_app.ScheduledInvocationError):
            scheduler_app.handler(
                {"source": SCHEDULER_EVENT_SOURCE, "schedule_id": "s"}
            )


# ── the scheduler-API port (the storage-agnostic seam task 5.2 calls) ─────────────────────


class FakeSchedulerClient:
    """An in-memory boto3-``scheduler``-lookalike that records the create/update/delete calls."""

    def __init__(self):
        self.created: list[dict] = []
        self.updated: list[dict] = []
        self.deleted: list[dict] = []
        self.raise_not_found_on_delete = False

    def create_schedule(self, **kwargs):
        self.created.append(kwargs)
        return {"ScheduleArn": "arn:aws:scheduler:::schedule/g/" + kwargs["Name"]}

    def update_schedule(self, **kwargs):
        self.updated.append(kwargs)
        return {"ScheduleArn": "arn:aws:scheduler:::schedule/g/" + kwargs["Name"]}

    def delete_schedule(self, **kwargs):
        if self.raise_not_found_on_delete:
            raise _ResourceNotFound()
        self.deleted.append(kwargs)
        return {}


class _ResourceNotFound(Exception):
    """A botocore-ClientError lookalike carrying a ResourceNotFoundException code."""

    def __init__(self):
        self.response = {"Error": {"Code": "ResourceNotFoundException"}}
        super().__init__("not found")


class TestSchedulerApiPort:
    def _api(self, client):
        return EventBridgeSchedulerApi(
            client=client,
            target_function_arn="arn:aws:lambda:eu-west-1:506221081911:function:members-scheduler-trigger-test",
            execution_role_arn="arn:aws:iam::506221081911:role/members-scheduler-exec-test",
            group_name="members-schedules-test",
        )

    def test_real_api_satisfies_the_port(self):
        assert isinstance(self._api(FakeSchedulerClient()), SchedulerApiPort)

    def test_create_schedule_targets_the_function_under_the_role(self):
        client = FakeSchedulerClient()
        api = self._api(client)

        name = api.create_schedule(TENANT, SCHEDULE_ID, "cron(0 8 1 * ? *)", enabled=True)

        assert name == build_schedule_name(TENANT, SCHEDULE_ID)
        [call] = client.created
        assert call["Name"] == name
        assert call["GroupName"] == "members-schedules-test"
        assert call["ScheduleExpression"] == "cron(0 8 1 * ? *)"
        assert call["State"] == "ENABLED"
        assert call["FlexibleTimeWindow"] == {"Mode": "OFF"}
        target = call["Target"]
        assert target["Arn"].endswith("members-scheduler-trigger-test")
        assert target["RoleArn"].endswith("members-scheduler-exec-test")
        # The static payload identifies the record (source discriminator + the two ids).
        payload = json.loads(target["Input"])
        assert payload == {
            "source": SCHEDULER_EVENT_SOURCE,
            "tenant_id": TENANT,
            "schedule_id": SCHEDULE_ID,
        }

    def test_create_disabled_schedule_sets_disabled_state(self):
        client = FakeSchedulerClient()
        api = self._api(client)
        api.create_schedule(TENANT, SCHEDULE_ID, "rate(30 days)", enabled=False)
        assert client.created[0]["State"] == "DISABLED"

    def test_update_schedule_full_replaces_the_target(self):
        client = FakeSchedulerClient()
        api = self._api(client)
        api.update_schedule(TENANT, SCHEDULE_ID, "cron(0 9 1 * ? *)", enabled=True)
        [call] = client.updated
        assert call["ScheduleExpression"] == "cron(0 9 1 * ? *)"
        assert call["State"] == "ENABLED"
        assert call["Target"]["Arn"].endswith("members-scheduler-trigger-test")

    def test_delete_schedule_names_the_record_schedule(self):
        client = FakeSchedulerClient()
        api = self._api(client)
        api.delete_schedule(TENANT, SCHEDULE_ID)
        [call] = client.deleted
        assert call["Name"] == build_schedule_name(TENANT, SCHEDULE_ID)
        assert call["GroupName"] == "members-schedules-test"

    def test_delete_is_idempotent_on_missing_schedule(self):
        client = FakeSchedulerClient()
        client.raise_not_found_on_delete = True
        api = self._api(client)
        # A missing EventBridge schedule for a deleted record must not raise (idempotent).
        api.delete_schedule(TENANT, SCHEDULE_ID)  # no exception

    def test_schedule_name_is_sanitized_and_bounded(self):
        # A tenant/schedule id with illegal chars is mapped to the EventBridge-Scheduler charset.
        name = build_schedule_name("ten ant/x", "sch:id!")
        assert all(c.isalnum() or c in "-_." for c in name)
        assert len(name) <= 64

    def test_target_input_is_stable_json(self):
        payload = json.loads(build_schedule_target_input(TENANT, SCHEDULE_ID))
        assert payload["source"] == SCHEDULER_EVENT_SOURCE
        assert payload["tenant_id"] == TENANT
        assert payload["schedule_id"] == SCHEDULE_ID
