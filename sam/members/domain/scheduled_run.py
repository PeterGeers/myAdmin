"""
The **scheduled-run service** (R5, pivot-output-actions task 5.3, design §4.3/§5) — the
storage-agnostic Members-domain glue that turns ONE EventBridge-Scheduler firing into a run of
the SAME execute-and-deliver path the interactive ``deliver`` route uses.

Why this exists (R5 / design §4.3)
----------------------------------
R5 asks for a saved set + delivery to run on a schedule, reusing the R4 send path so there is a
SINGLE send path for interactive + scheduled. When EventBridge Scheduler fires a schedule it
invokes the Members Lambda with a static payload identifying ``{tenant_id, schedule_id}`` (see
:func:`sam.members.repository.scheduler_api.build_schedule_target_input`). This service is what
that invocation delegates to: it

1. **resolves the stored ``schedule#<id>`` record** through the repository (tenant pinned —
   Property 1), 404-style absent → a no-op (a deleted record whose EventBridge schedule lingered
   must not crash the run);
2. **confirms the record is ``enabled``** — a disabled schedule is a NO-OP (the stored flag is
   authoritative even if EventBridge somehow fired a DISABLED schedule — belt-and-suspenders over
   the ``State=DISABLED`` the adapter sets);
3. **audits the run as UNATTENDED** (metadata-only — reuses the task-4.3 audit sink), BEFORE
   enqueuing, so an unattended run is always recorded even if the enqueue later partially fails;
4. **calls the SAME** :class:`~sam.members.domain.execute_and_deliver.ExecuteAndDeliverService`
   ``execute_and_deliver(tenant_id, set_id, run_id)`` the ``deliver`` route calls — which
   resolves the set, re-fetches the tenant's rows (tenant-wide — the create-time gate at task 5.2
   guarantees the owner had tenant-wide access, so there is NO partial scope to resolve, R5),
   runs the pivot, and ENQUEUES send jobs to the SAME ``MailSendQueue``.

Tenant-wide, pinned, no scope math (R5)
---------------------------------------
``tenant_id`` comes from the stored record (pinned at create — an unattended run has no
interactive user). The run is tenant-wide by construction: only a tenant-wide-capable role could
have created the schedule (task 5.2 gate), so this service does NO scope resolution — it never
narrows to a region. That guarantee lives at create time (steering 22), not here.

UNATTENDED audit (design §8, reuses task 4.3)
---------------------------------------------
The run is audited with the SAME metadata-only sink the worker uses
(:func:`sam.members.worker.mail_audit.log_analytics_output`), tagged ``actor=UNATTENDED`` so a
scheduled run is distinguishable from an interactive one in the audit log. It is metadata-only by
construction (the sink only knows ids + a count); no member data, no addresses. The per-send
audit still happens in the worker (task 4.3) — this is the RUN-level unattended marker.

Layering & seams (steering 35)
------------------------------
entrypoint (thin) → THIS service (glue, storage-agnostic) → ports (:class:`ScheduleStore` for
the tenant-pinned record read; :class:`ExecuteAndDeliver` for the send-path reuse; an audit
callable). It names no boto3, no EventBridge, no SQS — only the shapes. The production ports are
wired at the entrypoint (``handler/scheduler_app.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "SCHEDULED_RUN_ACTOR",
    "ExecuteAndDeliver",
    "ScheduleStore",
    "ScheduledRunOutcome",
    "ScheduledRunService",
]

#: The audit ``actor`` for an unattended scheduled run (design §8). A fixed sentinel (NOT a user
#: sub — the run has no interactive user, R5) so a scheduled run is greppable apart from an
#: interactive ``deliver`` in the metadata-only audit log.
SCHEDULED_RUN_ACTOR = "UNATTENDED"


@runtime_checkable
class ScheduleStore(Protocol):
    """The read port for a stored ``schedule#<id>`` record — a subset of the repository (R5).

    The service depends only on ``get_schedule(tenant_id, schedule_id) -> ScheduleEntry | None``
    (tenant pinned — Property 1), so it never learns the backing is DynamoDB. The production
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` satisfies this
    by its ``get_schedule`` method; a test injects a fake with the same method.
    """

    def get_schedule(self, tenant_id: str, schedule_id: str) -> Any | None:
        """Return the schedule record for ``tenant_id`` / ``schedule_id`` (or ``None``)."""
        ...


@runtime_checkable
class ExecuteAndDeliver(Protocol):
    """The send-path port — the SAME execute-and-deliver surface the ``deliver`` route uses (R4).

    The service depends on ``execute_and_deliver(tenant_id, set_id, run_id)`` so a scheduled run
    reuses the one send path (R4/R5). The production
    :class:`~sam.members.domain.execute_and_deliver.ExecuteAndDeliverService` satisfies this; a
    test injects a fake (or the real service over fakes) with the same method.
    """

    def execute_and_deliver(self, tenant_id: str, set_id: str, run_id: str) -> Any:
        """Resolve the set + its delivery, re-fetch rows, run the pivot, enqueue send job(s)."""
        ...


@dataclass(frozen=True)
class ScheduledRunOutcome:
    """What a scheduled firing did — for the entrypoint to log / return.

    - ``schedule_id`` — the record that fired.
    - ``ran`` — ``True`` when the execute-and-deliver path was invoked; ``False`` for a no-op
      (missing or disabled record).
    - ``skipped_reason`` — ``"not_found"`` / ``"disabled"`` for a no-op, else ``None``.
    - ``run_id`` — the logical run id handed to the send path (``None`` on a no-op).
    - ``delivery`` — the send path's own :class:`~sam.members.domain.execute_and_deliver.
      DeliveryOutcome` (what was enqueued), or ``None`` on a no-op.
    """

    schedule_id: str
    ran: bool
    skipped_reason: str | None = None
    run_id: str | None = None
    delivery: Any | None = None


class ScheduledRunService:
    """Run ONE scheduled firing: resolve the record, gate on ``enabled``, audit, delegate (R5).

    Storage-agnostic: depends only on the injected :class:`ScheduleStore` (the tenant-pinned
    record read), the :class:`ExecuteAndDeliver` port (the shared send path), and an audit
    callable (the metadata-only sink, reused from task 4.3). ``tenant_id`` is authoritative from
    the stored record (pinned at create — R5); the run is tenant-wide by construction (the
    create-time gate owns the scope guarantee — steering 22), so this service does NO scope math.
    """

    def __init__(
        self,
        schedules: ScheduleStore,
        execute_and_deliver: ExecuteAndDeliver,
        audit: Any,
    ):
        self._schedules = schedules
        self._deliver = execute_and_deliver
        self._audit = audit

    def run_scheduled(self, tenant_id: str, schedule_id: str) -> ScheduledRunOutcome:
        """Run the schedule ``schedule_id`` for ``tenant_id`` (the firing's identity).

        Args:
            tenant_id: the AUTHORITATIVE tenant from the firing payload (pinned at create — never
                a partial scope; the run is tenant-wide, R5). Every read is keyed by it.
            schedule_id: the stored ``schedule#<id>`` record that fired.

        Returns:
            A :class:`ScheduledRunOutcome`. A missing record → ``ran=False``,
            ``skipped_reason="not_found"`` (a lingering EventBridge schedule for a deleted record
            must be a quiet no-op, not a crash). A disabled record → ``ran=False``,
            ``skipped_reason="disabled"`` (the stored flag is authoritative). Otherwise the
            execute-and-deliver path runs and its outcome is carried back.
        """
        record = self._schedules.get_schedule(tenant_id, schedule_id)
        if record is None:
            return ScheduledRunOutcome(
                schedule_id=schedule_id, ran=False, skipped_reason="not_found"
            )

        if not getattr(record, "enabled", False):
            # A disabled schedule is a NO-OP — the stored flag is authoritative even if the
            # EventBridge schedule somehow fired while DISABLED (belt-and-suspenders, R5).
            return ScheduledRunOutcome(
                schedule_id=schedule_id, ran=False, skipped_reason="disabled"
            )

        set_id = record.set_id
        run_id = self._new_run_id(tenant_id, schedule_id)

        # Audit the UNATTENDED run (metadata-only, reuse task 4.3) BEFORE enqueuing, so the
        # unattended firing is always recorded even if the enqueue later partially fails. The
        # sink only knows ids — no member data, no addresses, no record_count yet (the per-send
        # metadata audit still happens in the worker, task 4.3).
        self._audit(
            actor=SCHEDULED_RUN_ACTOR,
            tenant=tenant_id,
            output_kind="ses_mail",
            set_key=set_id,
            record_count=None,
        )

        delivery = self._deliver.execute_and_deliver(tenant_id, set_id, run_id)
        return ScheduledRunOutcome(
            schedule_id=schedule_id,
            ran=True,
            run_id=run_id,
            delivery=delivery,
        )

    @staticmethod
    def _new_run_id(tenant_id: str, schedule_id: str) -> str:
        """Mint a ``run_id`` for one scheduled firing (audit attribution + idempotency, R5/R4).

        Mirrors the interactive route's ``_new_run_id`` (``handler/_dispatch``) but tagged
        ``schedule:`` and seeded by the schedule id + a UTC timestamp, so a scheduled run's jobs
        carry a distinct, traceable id folded into the send path's stable job ids (design §4.2).
        """
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"schedule:{schedule_id}:{stamp}"
