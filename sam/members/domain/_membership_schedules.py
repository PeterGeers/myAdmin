"""Membership-service schedule CRUD surface (R5 — scheduled execution of a set + delivery).

Mixed into ``MembershipService`` — bodies mirror the :class:`AnalyticsSetsMixin` pattern end
to end (:mod:`sam.members.domain._membership_analytics`). A schedule attaches a recurring run
to a saved analytics-set that already carries a delivery block (R3/R4), so a recurring send
happens on its own (e.g. a monthly clubblad). The entity itself
(:class:`~sam.members.domain.schedule.ScheduleEntry`) + the repository CRUD are task 5.1; this
mixin owns the SERVICE surface (task 5.2):

- ``schedule_id`` is server-chosen (uuid4 hex) on create, like ``set_id`` — a schedule has no
  natural key.
- ``tenant_id`` is AUTHORITATIVE on every method (never trusted from a body) and PINNED in the
  stored schedule (an unattended run has no interactive user — R5).
- ``created_by`` is the verified caller ``sub`` (ATTRIBUTION only — the R5 create-time gate is
  a route/edge concern, never re-checked here).

PRECONDITION (R5 — the service's one business rule, left to this layer by task 5.1): a
schedule can only be CREATED for a set that HAS a delivery block (task 5.1's entity is
storage-only). The create (and a ``set_id``-changing update) resolve the referenced set and
raise :class:`~sam.members.domain.execute_and_deliver.DeliveryNotConfigured` (→ 422 at the
edge) when the set is absent or carries no delivery — "only schedulable if the set has a
delivery block". The GATE (``members:admin`` OR ``members:write`` + the ``["*"]`` all-regions
grant) is enforced at the EDGE (task 5.2, ``app._authorize_schedule_route``), not here.

EVENTBRIDGE SCHEDULER (R5, task 5.3 — this layer's second responsibility): each stored
``schedule#<id>`` record is backed by ONE EventBridge Scheduler schedule, created at runtime
when a user creates a schedule and torn down when they delete it (design §4.3/§5). The
lifecycle methods here therefore ALSO materialize / update / delete that EventBridge schedule
through an injected :class:`~sam.members.repository.scheduler_api.SchedulerApiPort` — the same
storage-agnostic seam the queue port is (``self._scheduler``, injected into
:class:`MembershipService`; the production boto3 impl is wired at the edge, a fake in tests).
The service NEVER names boto3 / EventBridge — only the port shape.

Create ORDER + rollback (design §5 "persist record then create schedule, roll back / mark on
failure"): create persists the DynamoDB record FIRST (the record is the system of record),
then creates the EventBridge schedule. If the scheduler call fails, the just-persisted record
is ROLLED BACK (deleted) and the error surfaced — a schedule record must never linger with no
live EventBridge schedule behind it. Update re-sends cron/enabled to the schedule after the
record is saved; delete removes the EventBridge schedule (idempotent) THEN the record. When no
scheduler port is injected (``self._scheduler is None`` — e.g. a unit test of the pure CRUD, or
a service built before the edge wires the port) the EventBridge calls are simply skipped, so
the record-only behaviour is preserved and nothing fails for want of AWS.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sam.members.domain._membership_errors import ScheduleNotFound
from sam.members.domain.execute_and_deliver import DeliveryNotConfigured
from sam.members.domain.schedule import ScheduleEntry


class SchedulesMixin:
    """CRUD surface for tenant-scoped member schedules (R5).

    Storage-agnostic + tenant-agnostic. The injected :class:`MembersRepository` (accessed as
    ``self._repo``) is the sole DynamoDB touch-point; the injected scheduler port (accessed as
    ``self._scheduler``, may be ``None``) is the sole EventBridge-Scheduler touch-point. Neither
    is named concretely here — only their shapes. ``tenant_id`` is AUTHORITATIVE on every method
    (never trusted from a body) and PINNED in the stored schedule. ``schedule_id`` is
    server-chosen (uuid4 hex, no natural key). The "set must have a delivery block" precondition
    (R5) is enforced here on create / set_id-changing update (task 5.1 left it to the service);
    the capability+scope GATE is enforced at the edge (task 5.2). Each record's ONE EventBridge
    schedule is materialized/updated/deleted here via ``self._scheduler`` (task 5.3) — create
    persists the record first then creates the schedule (rolling the record back on failure),
    delete removes the schedule then the record.
    """

    #: The injected scheduler port (set by :class:`MembershipService.__init__`). Declared here
    #: for the type checker / clarity; ``None`` means "no EventBridge wiring" (record-only CRUD,
    #: e.g. a pure-domain unit test), in which case the lifecycle methods skip the schedule calls.
    _scheduler: Any

    # ── list / get ──────────────────────────────────────────────────────────────────

    def list_schedules(self, tenant_id: str) -> list[dict[str, Any]]:
        """List the tenant's schedules, sorted by ``(set_id, schedule_id)`` for determinism.

        Returns the JSON-friendly shape (:meth:`_serialize_schedule`) for each entry.
        """
        entries = self._repo.list_schedules(tenant_id)
        return [self._serialize_schedule(entry) for entry in entries]

    def get_schedule(self, tenant_id: str, schedule_id: str) -> dict[str, Any]:
        """Fetch one schedule by its ``schedule_id`` (404 if absent)."""
        entry = self._repo.get_schedule(tenant_id, schedule_id)
        if entry is None:
            raise ScheduleNotFound(tenant_id, schedule_id)
        return self._serialize_schedule(entry)

    # ── create / update / delete ────────────────────────────────────────────────────

    def create_schedule(
        self, tenant_id: str, body: Mapping[str, Any], created_by: str | None = None
    ) -> dict[str, Any]:
        """Create a schedule for the tenant (R5). ``schedule_id`` is server-generated.

        Stamps the authoritative ``tenant_id`` (never trusting a body ``tenant_id`` /
        ``schedule_id`` — verify-before-trust), generates ``schedule_id = uuid4().hex``, reads
        ``set_id`` / ``cron`` / ``enabled`` from the body, stamps ``created_by`` = the verified
        caller ``sub`` (ATTRIBUTION only — the R5 gate is the edge's job),
        ``created_at = updated_at = now(UTC) ISO``, validates the entity, and persists.

        PRECONDITION (R5): the referenced set MUST exist AND carry a delivery block — a
        schedule has nothing to run otherwise. Resolves the set and raises
        :class:`DeliveryNotConfigured` (→ 422) when it is absent or has no ``delivery``. This is
        the "only schedulable if the set has a delivery block" rule task 5.1 left to the service.
        """
        payload = dict(body) if isinstance(body, Mapping) else {}
        now = datetime.now(timezone.utc).isoformat()
        schedule_id = uuid.uuid4().hex
        set_id = str(payload.get("set_id", ""))

        # R5 precondition — resolve the referenced set and require a delivery block BEFORE
        # persisting the schedule (storage-only entity does not check this). An absent set or
        # one with no delivery is a 422 (nothing schedulable), never a silent create.
        self._require_set_has_delivery(tenant_id, set_id)

        raw_enabled = payload.get("enabled", True)
        enabled = bool(raw_enabled) if raw_enabled is not None else True

        entry = ScheduleEntry(
            tenant_id=tenant_id,  # authoritative + PINNED — never the body (R5)
            schedule_id=schedule_id,  # server-chosen opaque id
            set_id=set_id,
            cron=str(payload.get("cron", "")),
            created_by=created_by or "",  # attribution only (R5 gate is the edge's job)
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        entry.validate()
        saved = self._repo.save_schedule(tenant_id, entry)

        # Materialize the ONE EventBridge schedule for this record (task 5.3). ORDER (design §5):
        # the record is persisted FIRST (it is the system of record); the schedule is created
        # AFTER. If the scheduler call fails, roll the record back so no schedule#<id> ever
        # lingers without a live EventBridge schedule behind it, then surface the error.
        if self._scheduler is not None:
            try:
                self._scheduler.create_schedule(
                    tenant_id, schedule_id, entry.cron, enabled=entry.enabled
                )
            except Exception:
                # Roll back the just-persisted record (best-effort) and re-raise the original
                # scheduler failure — a half-created schedule (record but no live schedule) is
                # worse than a clean failure the caller can retry.
                try:
                    self._repo.delete_schedule(tenant_id, schedule_id)
                except Exception:
                    pass  # the original scheduler error is what matters; don't mask it
                raise

        return self._serialize_schedule(saved)

    def update_schedule(
        self, tenant_id: str, schedule_id: str, body: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update an existing schedule (404 if absent).

        Loads the entry within the tenant (Property 1); an absent ``schedule_id`` raises
        :class:`ScheduleNotFound` (→ 404). Merges the client body over the existing entry — the
        path ``schedule_id`` + ``tenant_id`` are authoritative for identity, ``created_by`` /
        ``created_at`` are preserved, ``updated_at`` is bumped — then validates and persists.

        PRECONDITION (R5): if the update CHANGES ``set_id`` (re-points the schedule at a
        different set), the new set must exist AND carry a delivery block, same as create —
        raises :class:`DeliveryNotConfigured` (→ 422) otherwise. An update that leaves ``set_id``
        unchanged does NOT re-check (the set had a delivery when the schedule was created; a
        later clear of that delivery is handled operationally, not by refusing an enable/cron
        edit).
        """
        existing = self._repo.get_schedule(tenant_id, schedule_id)
        if existing is None:
            raise ScheduleNotFound(tenant_id, schedule_id)

        payload = dict(body) if isinstance(body, Mapping) else {}
        now = datetime.now(timezone.utc).isoformat()

        set_id = str(payload["set_id"]) if "set_id" in payload else existing.set_id
        cron = str(payload["cron"]) if "cron" in payload else existing.cron
        if "enabled" in payload:
            raw_enabled = payload.get("enabled")
            enabled = bool(raw_enabled) if raw_enabled is not None else existing.enabled
        else:
            enabled = existing.enabled

        # R5 precondition on a set_id change only (re-pointing at a different set must still
        # name a schedulable set); an edit that keeps the same set_id does not re-resolve.
        if set_id != existing.set_id:
            self._require_set_has_delivery(tenant_id, set_id)

        updated = ScheduleEntry(
            tenant_id=tenant_id,  # authoritative — never the body
            schedule_id=schedule_id,  # the path is authoritative for identity
            set_id=set_id,
            cron=cron,
            created_by=existing.created_by,  # preserved — original author attribution
            enabled=enabled,
            created_at=existing.created_at,  # preserved from original
            updated_at=now,  # bumped
        )
        updated.validate()
        saved = self._repo.save_schedule(tenant_id, updated)

        # Keep the record's ONE EventBridge schedule in lock-step with the edit (task 5.3): a
        # cron change or an enabled flip must flow through to the live schedule, else a disabled
        # record would keep firing (or a re-enabled one stay dark). UpdateSchedule is a
        # full-replace in EventBridge Scheduler, so the adapter re-sends the whole target. The
        # record is already saved; a scheduler failure here surfaces to the caller (the record
        # and its schedule can briefly disagree until a retry — a loud failure, not a silent
        # drift). Keyed by (tenant_id, schedule_id) so the adapter names the same schedule.
        if self._scheduler is not None:
            self._scheduler.update_schedule(
                tenant_id, schedule_id, updated.cron, enabled=updated.enabled
            )

        return self._serialize_schedule(saved)

    def delete_schedule(self, tenant_id: str, schedule_id: str) -> dict[str, Any]:
        """Delete a schedule (hard delete). 404 if absent.

        Does a get-first to raise :class:`ScheduleNotFound` for an absent ``schedule_id`` so the
        edge maps it to 404. A schedule has no referencing records, so a hard delete is correct
        (mirrors :meth:`AnalyticsSetsMixin.delete_analytics_set`).
        """
        existing = self._repo.get_schedule(tenant_id, schedule_id)
        if existing is None:
            raise ScheduleNotFound(tenant_id, schedule_id)

        # Tear down the ONE EventBridge schedule BEFORE deleting the record (task 5.3): remove
        # the live schedule first so it can never fire for a record that is about to vanish. The
        # adapter's delete is idempotent (a missing EventBridge schedule is a no-op), so a record
        # whose schedule was already gone still deletes cleanly. Then delete the record (the
        # system of record). A scheduler failure here surfaces — a lingering live schedule for a
        # deleted record would re-fire, so a loud failure is correct over a silent orphan.
        if self._scheduler is not None:
            self._scheduler.delete_schedule(tenant_id, schedule_id)
        self._repo.delete_schedule(tenant_id, schedule_id)
        return self._serialize_schedule(existing)

    # ── R5 precondition helper ───────────────────────────────────────────────────────

    def _require_set_has_delivery(self, tenant_id: str, set_id: str) -> None:
        """Raise :class:`DeliveryNotConfigured` unless ``set_id`` resolves to a set WITH a delivery.

        The R5 "only schedulable if the set has a delivery block" rule (task 5.1 left this to
        the service). Resolves the referenced set within the tenant (Property 1) and requires a
        non-empty ``delivery`` block — a schedule's whole purpose is to re-run the set's stored
        delivery, so a set with no delivery (the legacy default) has nothing to run. An absent
        set is treated the same as a set with no delivery (both → 422 ``DeliveryNotConfigured``):
        from the scheduler's point of view there is nothing schedulable either way, and this
        avoids leaking "set does not exist" vs "set has no delivery" as distinct answers.
        """
        existing = self._repo.get_analytics_set(tenant_id, set_id)
        if existing is None or getattr(existing, "delivery", None) is None:
            raise DeliveryNotConfigured(tenant_id, set_id)

    # ── serialization helper ───────────────────────────────────────────────────────

    @staticmethod
    def _serialize_schedule(entry: ScheduleEntry) -> dict[str, Any]:
        """Project a schedule entry to the JSON-friendly shape the handler returns.

        Carries ``schedule_id``, ``set_id``, ``cron``, ``created_by``, ``enabled``,
        ``created_at``, ``updated_at`` as plain JSON. ``tenant_id`` is omitted (the caller
        already knows the tenant context — mirrors :meth:`_serialize_analytics_set`).
        ``created_by`` is surfaced for attribution display (R5 — who created it) but is never
        a gate.
        """
        return {
            "schedule_id": entry.schedule_id,
            "set_id": entry.set_id,
            "cron": entry.cron,
            "created_by": entry.created_by,
            "enabled": entry.enabled,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
