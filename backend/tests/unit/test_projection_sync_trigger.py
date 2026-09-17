"""Unit tests for the S3 on-change sync trigger + reconciliation backstop.

T21 (design.md D3 "On-change sync trigger (R5.7)"). Covers:

- ``enqueue`` records the affected administration on the queue (and, for the
  in-process default queue, drains it by running the sync for that tenant).
- ``reconcile`` runs the idempotent ``sync_all()`` backstop.
- A governance write (via the module-level ``enqueue_sync`` hook + the process
  default trigger) triggers an enqueue for the affected tenant.
- An enqueue failure does **not** break the (already-committed) governance write
  path — ``enqueue_sync`` swallows the error and returns ``False`` so the caller
  is unaffected and the reconciliation backstop covers the miss (R5.7).

Concrete example tests with **in-memory fakes** — no real AWS, no real MySQL.
The exhaustive convergence property test lands in T22.

Feature: s3-claims-and-projection
"""

import pytest

from services import projection_sync_trigger as trigger_mod
from services.projection_sync_trigger import (
    InMemorySyncQueue,
    ProjectionSyncTrigger,
    enqueue_sync,
    reconcile,
    set_default_trigger,
)


# --- in-memory fakes --------------------------------------------------------


class FakeSync:
    """Records ``sync_administration`` / ``sync_all`` calls; does no I/O."""

    def __init__(self, *, fail_on=None):
        self.admin_calls: list[str] = []
        self.sync_all_calls: int = 0
        self._fail_on = fail_on

    def sync_administration(self, administration):
        if self._fail_on is not None and administration == self._fail_on:
            raise RuntimeError(f"boom syncing {administration}")
        self.admin_calls.append(administration)
        return {"administration": administration}

    def sync_all(self):
        self.sync_all_calls += 1
        return {"sync_all": True}


class RecordingQueue:
    """A non-draining `SyncQueue` fake that just records enqueues."""

    def __init__(self, *, fail=False):
        self.enqueued: list[str] = []
        self._fail = fail

    def enqueue(self, administration):
        if self._fail:
            raise RuntimeError("queue is down")
        self.enqueued.append(administration)


@pytest.fixture(autouse=True)
def _reset_default_trigger():
    """Ensure each test starts/ends with a clean process default trigger."""
    set_default_trigger(None)
    yield
    set_default_trigger(None)


# --- enqueue records the affected administration ----------------------------


def test_enqueue_records_affected_administration_on_queue():
    queue = RecordingQueue()
    sync = FakeSync()
    # Non-draining queue (not the in-memory default) → records only, no drain.
    trigger = ProjectionSyncTrigger(queue, sync=sync)

    trigger.enqueue("TenantA")

    assert queue.enqueued == ["TenantA"]
    # A plain recording queue is not the in-process default, so no sync ran.
    assert sync.admin_calls == []


def test_enqueue_inprocess_queue_drains_and_syncs_affected_tenant():
    sync = FakeSync()
    # Default in-memory queue → enqueue drains synchronously and syncs the tenant.
    trigger = ProjectionSyncTrigger(sync=sync)

    trigger.enqueue("TenantA")

    assert sync.admin_calls == ["TenantA"]
    # Queue is drained after processing.
    assert trigger.queue.pending == ()


def test_enqueue_inprocess_dedups_repeated_signals_for_same_tenant():
    # Two signals for the same tenant enqueued before a drain collapse to one
    # sync (idempotent, avoids redundant work). Use drain_on_enqueue=False to
    # batch, then drain once.
    sync = FakeSync()
    queue = InMemorySyncQueue()
    trigger = ProjectionSyncTrigger(queue, sync=sync, drain_on_enqueue=False)

    trigger.enqueue("TenantA")
    trigger.enqueue("TenantA")
    trigger.enqueue("TenantB")
    assert queue.pending == ("TenantA", "TenantA", "TenantB")

    trigger._drain()

    assert sync.admin_calls == ["TenantA", "TenantB"]


def test_enqueue_blank_administration_raises_on_raw_trigger():
    trigger = ProjectionSyncTrigger(sync=FakeSync())
    with pytest.raises(ValueError):
        trigger.enqueue("")


# --- reconcile runs sync_all ------------------------------------------------


def test_reconcile_runs_sync_all_backstop():
    sync = FakeSync()
    trigger = ProjectionSyncTrigger(sync=sync)

    result = trigger.reconcile()

    assert sync.sync_all_calls == 1
    assert result == {"sync_all": True}


def test_module_reconcile_routes_through_default_trigger():
    sync = FakeSync()
    set_default_trigger(ProjectionSyncTrigger(sync=sync))

    reconcile()

    assert sync.sync_all_calls == 1


# --- a governance write triggers an enqueue (via the module hook) -----------


def test_enqueue_sync_hook_triggers_sync_for_affected_tenant():
    """Simulates what a governance write path does after committing."""
    sync = FakeSync()
    set_default_trigger(ProjectionSyncTrigger(sync=sync))

    ok = enqueue_sync("GoodwinSolutions")

    assert ok is True
    assert sync.admin_calls == ["GoodwinSolutions"]


def test_governance_write_path_calls_enqueue_sync(monkeypatch):
    """A governance write path (module_registry.activate_module) triggers an
    enqueue for the affected tenant after its commit."""
    from services import module_registry

    captured: list[str] = []
    monkeypatch.setattr(
        "services.projection_sync_trigger.enqueue_sync",
        lambda administration: captured.append(administration) or True,
    )

    # Minimal fakes: a registry entry with no deps, a db that records the write,
    # and a stubbed ParameterService so activate_module reaches the trigger.
    monkeypatch.setitem(
        module_registry.MODULE_REGISTRY,
        "TRIGTEST",
        {"description": "x", "required_roles": [], "depends_on": []},
    )

    class _DB:
        def execute_query(self, *a, **k):
            return None

    class _Params:
        def __init__(self, db):
            pass

        def seed_module_params(self, tenant, module):
            return 0

    monkeypatch.setattr(
        "services.parameter_service.ParameterService", _Params
    )

    module_registry.activate_module(_DB(), "TenantX", "TRIGTEST", "tester")

    assert captured == ["TenantX"]


# --- enqueue failure does not break the governance write --------------------


def test_enqueue_sync_swallows_queue_failure_and_returns_false():
    # A trigger whose queue raises → enqueue_sync must NOT propagate; the
    # governance write already committed (R5.7).
    set_default_trigger(ProjectionSyncTrigger(RecordingQueue(fail=True), sync=FakeSync()))

    ok = enqueue_sync("TenantA")

    assert ok is False  # logged + backstopped, not raised


def test_enqueue_sync_swallows_sync_failure_and_returns_false():
    # The in-process drain runs the sync, which raises for this tenant. The
    # failure must be swallowed so the governance write is unaffected.
    set_default_trigger(ProjectionSyncTrigger(sync=FakeSync(fail_on="TenantA")))

    ok = enqueue_sync("TenantA")

    assert ok is False


def test_enqueue_sync_blank_administration_returns_false_without_raising():
    set_default_trigger(ProjectionSyncTrigger(sync=FakeSync()))

    assert enqueue_sync("") is False
    assert enqueue_sync(None) is False


def test_enqueue_sync_failure_does_not_raise_into_caller():
    """Explicit guarantee: even a totally broken trigger cannot break a caller."""

    class _ExplodingTrigger(ProjectionSyncTrigger):
        def enqueue(self, administration):
            raise RuntimeError("catastrophic")

    set_default_trigger(_ExplodingTrigger(sync=FakeSync()))

    # Must not raise.
    result = enqueue_sync("TenantA")
    assert result is False
