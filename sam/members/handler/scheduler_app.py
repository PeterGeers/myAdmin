"""
R5 / pivot-output-actions task 5.3 — the Members **scheduler trigger** Lambda entrypoint
(thin adapter; the EventBridge-Scheduler-invocation edge).

This is the TRIGGER side of the R5 scheduled send path (design §4.3/§5): EventBridge Scheduler
fires per a stored ``schedule#<id>`` record's ``cron`` and invokes the Members function with a
STATIC JSON payload identifying ``{tenant_id, schedule_id}`` (see
:func:`sam.members.repository.scheduler_api.build_schedule_target_input`). This handler detects
that invocation, resolves the schedule, confirms it is enabled, and delegates to the SAME
execute-and-deliver path the interactive ``deliver`` route uses — so there is ONE send path for
interactive + scheduled (R4/R5).

A distinct event shape from the API-GW proxy event (design §5)
--------------------------------------------------------------
The Members function already has an HTTP entrypoint (``handler/app.py``) that handles API-Gateway
proxy events. An EventBridge-Scheduler invocation is a DIFFERENT event shape: the whole event IS
the static target payload — a plain JSON object ``{"source": "members.schedule", "tenant_id":
..., "schedule_id": ...}`` — with none of the proxy-event keys (``httpMethod`` / ``requestContext``
/ ``path``). This handler is a DEDICATED entrypoint wired as the schedule target's function
handler, and it DETECTS the shape explicitly via the ``source`` discriminator (:data:`~sam.
members.repository.scheduler_api.SCHEDULER_EVENT_SOURCE`) rather than guessing — an event that is
NOT a members-schedule firing is rejected loudly (it should never reach this handler).

Thin by design (steering 35): the handler's whole job is

    detect + parse the firing payload → delegate to the scheduled-run service → log

and nothing else. The business logic — resolve the record, gate on ``enabled``, audit the
unattended run, reuse the execute-and-deliver path — lives in
:class:`~sam.members.domain.scheduled_run.ScheduledRunService`. The production ports (the
tenant-scoped repository as the schedule store, the SAME execute-and-deliver service the
``deliver`` route builds, the task-4.3 metadata-only audit sink) are wired once at cold start by
:func:`get_scheduled_run_service` and resolve lazily + fail-fast on first use, so importing this
module (and the test suite) touches NO AWS. Tests set ``_SERVICE`` / patch
:func:`get_scheduled_run_service` to inject a service over fakes.

Tenant-wide, no scope (R5)
--------------------------
The firing payload carries NO member scope: the create-time gate (task 5.2 — ``members:admin`` or
``members:write`` + the ``["*"]`` all-regions grant) guarantees the schedule owner had tenant-wide
access, so a scheduled run operates tenant-wide and there is no partial scope to resolve. This
handler therefore passes only ``(tenant_id, schedule_id)`` down; the service pins the tenant and
reuses the send path tenant-wide.
"""

from __future__ import annotations

import logging
from typing import Any

from sam.members.repository.scheduler_api import SCHEDULER_EVENT_SOURCE

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

__all__ = ["ScheduledInvocationError", "get_scheduled_run_service", "handler"]

#: The module-global scheduled-run service, built once at cold start (``None`` until first use). A
#: warm Lambda container reuses it across invocations (the ports resolve lazily + fail-fast on
#: first use). Tests set this (or patch :func:`get_scheduled_run_service`) to inject a service
#: over in-memory fakes.
_SERVICE: Any = None


class ScheduledInvocationError(Exception):
    """Raised when the event is not a well-formed members-schedule firing payload.

    The scheduler target payload is authored by THIS module's own adapter
    (:func:`sam.members.repository.scheduler_api.build_schedule_target_input`), so a malformed /
    foreign event reaching this handler is a wiring fault — fail loud rather than silently run (or
    skip) something. Carries the reason for the CloudWatch log.
    """


def get_scheduled_run_service() -> Any:
    """Return the module-global scheduled-run service, building it once at cold start (R5).

    Wires :class:`~sam.members.domain.scheduled_run.ScheduledRunService` over its production ports:

      * the tenant-scoped
        :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` as the
        :class:`~sam.members.domain.scheduled_run.ScheduleStore` (its ``get_schedule`` pins
        ``tenant_id`` — Property 1);
      * the SAME execute-and-deliver service the interactive ``deliver`` route builds
        (:func:`sam.members.handler._dispatch.get_execute_and_deliver_service`) — so there is ONE
        send path for interactive + scheduled (R4/R5), enqueuing to the SAME ``MailSendQueue``;
      * :func:`sam.members.worker.mail_audit.log_analytics_output` — the task-4.3 metadata-only
        audit sink (reused for the UNATTENDED run-level audit, design §8).

    Everything resolves lazily + fail-fast on first use, so importing this module (and the auth-
    free tests) never touches AWS. Tests patch this accessor (or set ``_SERVICE``) to inject a
    service over in-memory fakes.
    """
    global _SERVICE
    if _SERVICE is None:
        from sam.members.domain.scheduled_run import ScheduledRunService
        from sam.members.handler._dispatch import get_execute_and_deliver_service
        from sam.members.repository.members_repository import DynamoDbMembersRepository
        from sam.members.worker.mail_audit import log_analytics_output

        _SERVICE = ScheduledRunService(
            DynamoDbMembersRepository(),
            get_execute_and_deliver_service(),
            log_analytics_output,
        )
    return _SERVICE


def _parse_firing(event: Any) -> tuple[str, str]:
    """Validate + extract ``(tenant_id, schedule_id)`` from a members-schedule firing event.

    The event IS the static target payload the adapter authored — a plain JSON object with the
    ``source`` discriminator and the two ids. This rejects anything that is not that shape (a
    foreign / malformed event) with :class:`ScheduledInvocationError` so a mis-wired target fails
    loudly rather than silently running or skipping. ``source`` must equal
    :data:`SCHEDULER_EVENT_SOURCE`; both ids must be non-blank strings.
    """
    if not isinstance(event, dict):
        raise ScheduledInvocationError("scheduler event must be a JSON object")
    if event.get("source") != SCHEDULER_EVENT_SOURCE:
        raise ScheduledInvocationError(
            f"not a members-schedule firing (source={event.get('source')!r}; "
            f"expected {SCHEDULER_EVENT_SOURCE!r})"
        )
    tenant_id = event.get("tenant_id")
    schedule_id = event.get("schedule_id")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ScheduledInvocationError("firing payload is missing a non-blank tenant_id")
    if not isinstance(schedule_id, str) or not schedule_id.strip():
        raise ScheduledInvocationError(
            "firing payload is missing a non-blank schedule_id"
        )
    return tenant_id.strip(), schedule_id.strip()


def handler(event: Any, context: Any = None) -> dict[str, Any]:
    """Run ONE scheduled firing (R5): detect the payload, delegate, log — thin by design.

    Parses + validates the EventBridge-Scheduler target payload into ``(tenant_id,
    schedule_id)``, then delegates to the scheduled-run service, which resolves the record, gates
    on ``enabled`` (a disabled / missing record is a quiet no-op), audits the UNATTENDED run, and
    reuses the execute-and-deliver path (enqueue to the SAME queue). Returns a small JSON summary
    (what ran / was skipped + the enqueue receipt) for CloudWatch; a malformed event raises
    :class:`ScheduledInvocationError` (a wiring fault — never a silent skip).
    """
    tenant_id, schedule_id = _parse_firing(event)
    service = get_scheduled_run_service()
    outcome = service.run_scheduled(tenant_id, schedule_id)

    if not outcome.ran:
        logger.info(
            "scheduler trigger: schedule %s skipped (%s)",
            schedule_id,
            outcome.skipped_reason,
        )
        return {
            "schedule_id": schedule_id,
            "ran": False,
            "skipped_reason": outcome.skipped_reason,
        }

    delivery = outcome.delivery
    logger.info(
        "scheduler trigger: schedule %s ran (run=%s mode=%s enqueued=%s)",
        schedule_id,
        outcome.run_id,
        getattr(delivery, "mode", None),
        getattr(delivery, "enqueued", None),
    )
    return {
        "schedule_id": schedule_id,
        "ran": True,
        "run_id": outcome.run_id,
        "mode": getattr(delivery, "mode", None),
        "enqueued": getattr(delivery, "enqueued", None),
        "skipped_no_address": getattr(delivery, "skipped_no_address", None),
    }
