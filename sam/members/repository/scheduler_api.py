"""
EventBridge-Scheduler **schedule-management port** (R5, pivot-output-actions task 5.3) — the
storage-agnostic seam the schedule CRUD path (task 5.2) uses to materialize / tear down the
ONE EventBridge schedule that backs each stored ``schedule#<id>`` record (design §4.3/§5).

Dynamic-per-schedule, not static (design §4.3/§5)
-------------------------------------------------
The design (§4.3) says "EventBridge Scheduler fires **per** ``schedule#<id>.cron``" — i.e. one
EventBridge Scheduler SCHEDULE exists per stored schedule record, created at RUNTIME when a user
creates a schedule (task 5.2) and deleted when they delete it. The schedules cannot be declared
statically in ``template.yaml`` because they are tenant/user data (an unknown, growing set),
so the create/delete-schedule service calls the Scheduler API through THIS port. The static SAM
infra (task 5.3 IaC) is only the fixed plumbing: the IAM role EventBridge Scheduler assumes to
invoke the Members function (the scheduler-execution-role), plus the Members function's own
``scheduler:*`` + ``iam:PassRole`` grant scoped to that exact role ARN.

Layering (design §4.1, steering 35)
-----------------------------------
This mirrors :mod:`sam.members.repository.mail_send_queue` exactly — the queue PORT the
execute-and-deliver service depends on. The schedule CRUD service (task 5.2) depends ONLY on the
:class:`SchedulerApiPort` Protocol (``create_schedule`` / ``update_schedule`` /
``delete_schedule``) so it carries NO boto3 dependency and stays storage-agnostic. THIS module is
the production implementation of that port — the EventBridge-Scheduler counterpart to the SQS
``SqsMailSendQueue``: it lives in the repository/adapter layer (the domain never imports it; the
route/service edge injects it) and is the sole EventBridge-Scheduler touch-point.

What a materialized schedule targets (design §4.3/§5)
-----------------------------------------------------
Each EventBridge schedule TARGETS the Members Lambda (same plane) with a static JSON payload
identifying ``{"source": "members.schedule", "tenant_id": ..., "schedule_id": ...}``. When the
schedule fires, EventBridge Scheduler invokes the Members function with that payload; the
scheduler trigger entrypoint (:mod:`sam.members.handler.scheduler_app`) detects the shape,
resolves the ``schedule#<id>`` record, confirms it is ``enabled``, and calls the SAME
execute-and-deliver service the interactive ``deliver`` route uses — so there is ONE send path
for interactive + scheduled (R4/R5). The target carries NO member scope: the schedule's
create-time gate (task 5.2 — ``members:admin`` or ``members:write`` + the ``["*"]`` all-regions
grant) guarantees the owner had tenant-wide access, so a scheduled run is always tenant-wide
(R5) — there is no partial scope to resolve, and none is encoded in the target.

Config + fail-fast (mirrors ``mail_send_queue.resolve_mail_send_queue_url``)
---------------------------------------------------------------------------
The two pieces of wiring the production adapter needs resolve from env with NO default — a
missing/blank var raises :class:`~services.dynamodb_client.DynamoDBConfigError`, reusing the one
fail-fast ``require_env`` so the no-dangerous-fallback discipline (steering 23) lives in a single
place:

- ``SCHEDULER_TARGET_FUNCTION_ARN`` — the Members function ARN each schedule invokes (the
  target). Wired per env by ``template.yaml`` from ``!GetAtt MembersFunction.Arn``.
- ``SCHEDULER_EXECUTION_ROLE_ARN`` — the role EventBridge Scheduler assumes to invoke that
  target. Wired per env from the scheduler-execution-role declared in ``template.yaml``; the
  Members function's ``iam:PassRole`` grant is scoped to exactly this ARN.

The boto3 ``scheduler`` client resolves LAZILY on first use, so importing this module (and the
handler, and the test suite) touches NO AWS. The client is injectable so a test can supply a fake
without an AWS round-trip (dependency inversion) — the schedule-CRUD tests inject a FAKE
scheduler and assert the create/delete call shape, never touching EventBridge.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol, runtime_checkable

from services.dynamodb_client import REGION_ENV_VAR, require_env

__all__ = [
    "SCHEDULER_EXECUTION_ROLE_ARN_ENV_VAR",
    "SCHEDULER_EVENT_SOURCE",
    "SCHEDULER_GROUP_NAME_ENV_VAR",
    "SCHEDULER_TARGET_FUNCTION_ARN_ENV_VAR",
    "SchedulerApiPort",
    "build_schedule_target_input",
    "build_schedule_name",
    "resolve_scheduler_execution_role_arn",
    "resolve_scheduler_target_function_arn",
    "EventBridgeSchedulerApi",
]

#: The ``source`` discriminator stamped on every scheduled target payload. The scheduler trigger
#: entrypoint (``handler/scheduler_app.py``) keys on this to tell an EventBridge-Scheduler
#: invocation apart from an API-Gateway proxy event — a distinct event shape, detected explicitly
#: rather than guessed. Changing it is a cross-file contract (the entrypoint matches it), so it
#: lives here as the single source and the entrypoint imports it.
SCHEDULER_EVENT_SOURCE = "members.schedule"

#: Env var carrying the Members function ARN each schedule invokes (the target). Wired per env by
#: the SAM template from ``!GetAtt MembersFunction.Arn``. No default — fail-fast (mirrors
#: ``MAIL_SEND_QUEUE_URL``): a mis-deploy that forgot to wire it breaks loudly.
SCHEDULER_TARGET_FUNCTION_ARN_ENV_VAR = "SCHEDULER_TARGET_FUNCTION_ARN"

#: Env var carrying the role EventBridge Scheduler assumes to invoke the target. Wired per env by
#: the SAM template from the scheduler-execution-role; the function's ``iam:PassRole`` grant is
#: scoped to exactly this ARN. No default — fail-fast.
SCHEDULER_EXECUTION_ROLE_ARN_ENV_VAR = "SCHEDULER_EXECUTION_ROLE_ARN"

#: Env var carrying the EventBridge Scheduler schedule-GROUP the per-schedule schedules live in
#: (per env, e.g. ``members-schedules`` / ``members-schedules-test``). Grouping keeps the
#: per-env schedules in one named bucket (and lets the IAM grant scope to that group's ARN
#: pattern). Optional at the adapter level — a blank/absent value falls back to the account
#: ``default`` group so a local run / early env without a declared group still works.
SCHEDULER_GROUP_NAME_ENV_VAR = "SCHEDULER_GROUP_NAME"


def resolve_scheduler_target_function_arn() -> str:
    """Return the Members function target ARN from the env, or fail fast.

    Reuses :func:`services.dynamodb_client.require_env` so the no-dangerous-fallback discipline
    (steering 23) lives in one place.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: the var is missing/blank.
    """
    return require_env(SCHEDULER_TARGET_FUNCTION_ARN_ENV_VAR)


def resolve_scheduler_execution_role_arn() -> str:
    """Return the scheduler-execution-role ARN from the env, or fail fast.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: the var is missing/blank.
    """
    return require_env(SCHEDULER_EXECUTION_ROLE_ARN_ENV_VAR)


def build_schedule_name(tenant_id: str, schedule_id: str) -> str:
    """Derive the EventBridge-Scheduler schedule NAME for a stored ``schedule#<id>`` record.

    Deterministic from ``(tenant_id, schedule_id)`` so the create/update/delete calls all name
    the SAME schedule for a given record (an update is create-or-replace on the same name, a
    delete removes exactly it). The name is sanitized to the EventBridge-Scheduler charset
    (``[a-zA-Z0-9-_.]`` only, ≤ 64 chars): any other character in a tenant/schedule id is mapped
    to ``_`` so an arbitrary stored id can never produce an invalid schedule name. The tenant is
    first so a tenant's schedules sort/scope together.
    """
    raw = f"m-{tenant_id}-{schedule_id}"
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in raw)
    return safe[:64]


def build_schedule_target_input(tenant_id: str, schedule_id: str) -> str:
    """Build the static JSON target payload a materialized schedule invokes the function with.

    The payload identifies the stored schedule to run — ``{"source": "members.schedule",
    "tenant_id": ..., "schedule_id": ...}`` (design §4.3). It carries NO member scope: the
    create-time gate (task 5.2) guarantees the owner had tenant-wide access, so a scheduled run
    is always tenant-wide (R5) and the entrypoint resolves ``set_id`` from the record, not the
    payload. The scheduler trigger entrypoint parses this shape; ``SCHEDULER_EVENT_SOURCE`` is
    the shared discriminator.
    """
    return json.dumps(
        {
            "source": SCHEDULER_EVENT_SOURCE,
            "tenant_id": tenant_id,
            "schedule_id": schedule_id,
        }
    )


@runtime_checkable
class SchedulerApiPort(Protocol):
    """The minimal schedule-management port the schedule CRUD service (task 5.2) depends on.

    Storage-agnostic — the CRUD service materializes/updates/removes the ONE EventBridge schedule
    behind a stored ``schedule#<id>`` record through this shape and never learns the backing is
    EventBridge Scheduler. :class:`EventBridgeSchedulerApi` is the production implementation; a
    test injects an in-memory fake with the same three methods. All three are keyed by
    ``(tenant_id, schedule_id)`` so the adapter derives the EventBridge schedule name itself (the
    service never deals in EventBridge names).
    """

    def create_schedule(
        self, tenant_id: str, schedule_id: str, cron: str, *, enabled: bool = True
    ) -> str:
        """Create (or replace) the EventBridge schedule for a record; return its name/arn."""
        ...

    def update_schedule(
        self, tenant_id: str, schedule_id: str, cron: str, *, enabled: bool = True
    ) -> str:
        """Update the EventBridge schedule (cron / enabled) for a record; return its name/arn."""
        ...

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        """Delete the EventBridge schedule for a record (idempotent — a missing one is a no-op)."""
        ...


class EventBridgeSchedulerApi:
    """The EventBridge-Scheduler-backed schedule manager — the production :class:`SchedulerApiPort`.

    Structurally satisfies the port (``create_schedule`` / ``update_schedule`` /
    ``delete_schedule``) so the CRUD service depends on the shape, not this class. Each schedule
    TARGETS the Members function (resolved fail-fast from the env) and is invoked under the
    scheduler-execution-role (also fail-fast from the env); EventBridge Scheduler fires it per the
    record's ``cron``. The boto3 ``scheduler`` client + the two ARNs resolve LAZILY + fail-fast on
    first use so import touches no AWS. The client is injectable (dependency inversion) for tests.

    Args:
        client: An optional boto3 ``scheduler`` client (or a compatible fake). If omitted,
            resolved lazily on first use against the resolved region.
        target_function_arn: An optional override for the target ARN. If omitted, resolved lazily
            + fail-fast from ``SCHEDULER_TARGET_FUNCTION_ARN`` on first use.
        execution_role_arn: An optional override for the scheduler-execution-role ARN. If
            omitted, resolved lazily + fail-fast from ``SCHEDULER_EXECUTION_ROLE_ARN``.
        group_name: An optional schedule-group override. If omitted, resolved from
            ``SCHEDULER_GROUP_NAME`` (blank/absent → the account ``default`` group).
    """

    def __init__(
        self,
        *,
        client: Any = None,
        target_function_arn: str | None = None,
        execution_role_arn: str | None = None,
        group_name: str | None = None,
    ):
        self._client = client
        self._target_function_arn = target_function_arn
        self._execution_role_arn = execution_role_arn
        self._group_name = group_name

    # ── lazy, fail-fast resource resolution ───────────────────────────────────────────

    @property
    def client(self):
        """The boto3 ``scheduler`` client, resolved lazily on first use."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "scheduler", region_name=require_env(REGION_ENV_VAR)
            )
        return self._client

    @property
    def target_function_arn(self) -> str:
        """The target Members-function ARN, resolved lazily + fail-fast from the env."""
        if self._target_function_arn is None:
            self._target_function_arn = resolve_scheduler_target_function_arn()
        return self._target_function_arn

    @property
    def execution_role_arn(self) -> str:
        """The scheduler-execution-role ARN, resolved lazily + fail-fast from the env."""
        if self._execution_role_arn is None:
            self._execution_role_arn = resolve_scheduler_execution_role_arn()
        return self._execution_role_arn

    @property
    def group_name(self) -> str:
        """The schedule-group name (``default`` when unset — a blank env is not fail-fast here)."""
        if self._group_name is None:
            import os

            self._group_name = os.environ.get(SCHEDULER_GROUP_NAME_ENV_VAR, "").strip()
        return self._group_name or "default"

    # ── the SchedulerApiPort port ──────────────────────────────────────────────────────

    def create_schedule(
        self, tenant_id: str, schedule_id: str, cron: str, *, enabled: bool = True
    ) -> str:
        """Create the EventBridge schedule for a record (``CreateSchedule``); return its name.

        The schedule's ``ScheduleExpression`` is the record's ``cron`` (``cron(...)`` /
        ``rate(...)`` / ``at(...)`` — EventBridge Scheduler enforces the grammar here, the entity
        only pre-screened it as non-blank at task 5.1). The target is the Members function + the
        static JSON payload (:func:`build_schedule_target_input`); the schedule runs under the
        scheduler-execution-role. ``State`` reflects ``enabled`` so a disabled record never fires.
        A ``FlexibleTimeWindow`` of ``OFF`` means it fires exactly on the expression.
        """
        name = build_schedule_name(tenant_id, schedule_id)
        self.client.create_schedule(
            Name=name,
            GroupName=self.group_name,
            ScheduleExpression=cron,
            State="ENABLED" if enabled else "DISABLED",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": self.target_function_arn,
                "RoleArn": self.execution_role_arn,
                "Input": build_schedule_target_input(tenant_id, schedule_id),
            },
        )
        return name

    def update_schedule(
        self, tenant_id: str, schedule_id: str, cron: str, *, enabled: bool = True
    ) -> str:
        """Update the EventBridge schedule for a record (``UpdateSchedule``); return its name.

        ``UpdateSchedule`` is a full-replace in EventBridge Scheduler, so the whole target +
        expression + state are re-sent — the same shape :meth:`create_schedule` sends. This keeps
        the record and its materialized schedule in lock-step when a user edits the cron or flips
        ``enabled`` (task 5.2).
        """
        name = build_schedule_name(tenant_id, schedule_id)
        self.client.update_schedule(
            Name=name,
            GroupName=self.group_name,
            ScheduleExpression=cron,
            State="ENABLED" if enabled else "DISABLED",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": self.target_function_arn,
                "RoleArn": self.execution_role_arn,
                "Input": build_schedule_target_input(tenant_id, schedule_id),
            },
        )
        return name

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> None:
        """Delete the EventBridge schedule for a record (``DeleteSchedule``), idempotently.

        A record whose EventBridge schedule was already removed (or never materialized) must not
        make a delete fail — the stored ``schedule#<id>`` record is the system of record, and the
        EventBridge schedule is its derived shadow. So a ``ResourceNotFoundException`` is
        swallowed (idempotent delete); any other error propagates.
        """
        name = build_schedule_name(tenant_id, schedule_id)
        try:
            self.client.delete_schedule(Name=name, GroupName=self.group_name)
        except Exception as exc:  # noqa: BLE001 — only a not-found is swallowed; re-raise others
            if type(exc).__name__ == "ResourceNotFoundException" or _is_not_found(exc):
                return
            raise


def _is_not_found(exc: Exception) -> bool:
    """True when a boto3 ``ClientError`` carries a ``ResourceNotFoundException`` error code.

    boto3 raises ``botocore.exceptions.ClientError`` (not a dedicated class) for a missing
    schedule, carrying the code in ``response['Error']['Code']``. Checked structurally (no
    botocore import) so a fake in tests can raise a lookalike and this stays import-light.
    """
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            return error.get("Code") == "ResourceNotFoundException"
    return False
