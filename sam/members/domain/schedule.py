"""
The tenant-scoped **schedule** entity (R5 — scheduled execution of a saved set + delivery).

A schedule attaches a recurring run to a saved analytics-set that has a delivery block, so a
recurring send happens on its own (e.g. a monthly clubblad). This module owns ONLY the
**entity model** (the tenant-agnostic entry shape + its ``validate()`` + the storage-shape
``to_item`` / ``from_item`` mapping), mirroring :mod:`sam.members.domain.analytics_set`
(:class:`AnalyticsSetEntry`) and :mod:`sam.members.domain.template`. Nothing here talks to
DynamoDB, EventBridge, or boto3.

Entry shape (design §2.3 / §5)::

    { "tenant_id": "<pk>", "schedule_id": "<server-chosen id>" (SK id),
      "set_id": "<analyticsset#<id>>",   # the analytics-set to run (must have a delivery block)
      "cron": "<EventBridge Scheduler schedule expression>",  # cron(...)/rate(...)/at(...)
      "created_by": "<Cognito sub>",     # must have been CRUD+region-all or admin at create (R5)
      "enabled": true,                   # default True
      "created_at": "<ISO-8601 UTC>", "updated_at": "<ISO-8601 UTC>" }

STORAGE-ONLY, by design
-----------------------
The entity carries ``set_id`` but is deliberately **storage-only**: the rule "a set is only
schedulable if it has a delivery block" (R5) is a SERVICE/route gate (task 5.2), NOT an entity
concern — this layer never reads the referenced set. The ``tenant_id`` is PINNED in the
schedule because an unattended run has no interactive user (R5); the run resolves tenant-wide
member scope because only a tenant-wide-capable role (``members:admin`` or ``members:write`` +
the ``["*"]`` all-regions grant) could create it — again, a create-time gate, not an entity
rule.

The ``cron`` is validated here only as a **non-blank string**: the design (§5) specifies "an
EventBridge Scheduler schedule expression" without pinning a single grammar (it accepts
``cron(...)``, ``rate(...)``, and ``at(...)`` forms), so the exact expression grammar is
enforced by the scheduler wiring at task 5.3 — this layer refuses only the clearly-unusable
empty/blank/non-string value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sam.members.domain.error_codes import (
    SCHEDULE_CRON,
    SCHEDULE_ENABLED,
    SCHEDULE_ID,
    SCHEDULE_SET,
    SCHEDULE_TENANT,
    FieldError,
)

__all__ = [
    "SORT_KEY_SEPARATOR",
    "ScheduleEntry",
    "ScheduleValidationError",
]

#: Mirrors ``table_design.SORT_KEY_SEPARATOR`` — a ``schedule_id`` may not contain it, since the
#: id becomes a sort-key segment. Duplicated here (not imported) to keep the domain layer free
#: of any dependency on the repository/storage layer (dependencies point downward only).
SORT_KEY_SEPARATOR = "#"


class ScheduleValidationError(Exception):
    """Raised when a schedule entry is malformed (a client/data bug → 422 at the edge).

    Carries ``errors`` — a mapping of field name → :class:`FieldError` (machine ``code`` +
    English ``detail``, API standard v1.0) — so a caller surfaces every problem at once,
    localizable via the code (mirrors :class:`AnalyticsSetValidationError`).
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = dict(errors)
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"schedule entry is invalid: {detail}")


@dataclass(frozen=True)
class ScheduleEntry:
    """One tenant's stored schedule for a saved set + delivery (R5).

    Frozen because an entry is data resolved and shared like the sibling entities
    (:class:`AnalyticsSetEntry`, :class:`TemplateEntry`). The fields map 1:1 to the design's
    entry shape (§2.3):

    - ``tenant_id`` — the owning tenant (partition key). PINNED here because an unattended run
      has no interactive user (R5). A blank tenant is a cross-tenant hazard and is refused
      (Property 1).
    - ``schedule_id`` — the entry's stable server-chosen id (sort-key id). Non-blank, no key
      separator.
    - ``set_id`` — the analytics-set the schedule runs (storage-only ref; the "has a delivery
      block" check is a service/route gate at task 5.2, NOT validated here). Non-blank.
    - ``cron`` — the EventBridge Scheduler schedule expression (``cron(...)`` / ``rate(...)`` /
      ``at(...)``). Validated here as a non-blank string only; the exact grammar is enforced by
      the scheduler at task 5.3.
    - ``created_by`` — the verified Cognito ``sub`` of the creator (ATTRIBUTION/audit — the
      creator must have been CRUD+region-all or admin at create, R5; that is a create-time gate,
      never re-checked here). Optional (older items leave it blank).
    - ``enabled`` — whether the schedule is active. A bool; defaults to ``True`` (a new schedule
      is live unless explicitly disabled).
    - ``created_at`` / ``updated_at`` — ISO-8601 UTC timestamp strings stamped by the service.
    """

    tenant_id: str
    schedule_id: str
    set_id: str
    cron: str
    created_by: str = ""
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""

    # ── validation ──────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the entry shape, raising :class:`ScheduleValidationError` on failure.

        Rules: non-blank ``tenant_id``; non-blank ``schedule_id`` with no key separator;
        non-blank ``set_id``; non-blank ``cron`` string (the schedule expression — exact
        grammar enforced by the scheduler at task 5.3); ``enabled`` is a bool. The "set must
        have a delivery block" rule (R5) is a SERVICE gate, NOT checked here (storage-only
        entity). Returns None when well-formed.
        """
        errors: dict[str, FieldError] = {}

        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            errors["tenant_id"] = FieldError(
                code=SCHEDULE_TENANT,
                detail="must be a non-blank string (tenant isolation, Property 1)",
            )

        if not isinstance(self.schedule_id, str) or not self.schedule_id.strip():
            errors["schedule_id"] = FieldError(
                code=SCHEDULE_ID, detail="must be a non-blank string"
            )
        elif SORT_KEY_SEPARATOR in self.schedule_id:
            errors["schedule_id"] = FieldError(
                code=SCHEDULE_ID,
                detail=(
                    f"must not contain {SORT_KEY_SEPARATOR!r} (it becomes a sort-key id segment)"
                ),
                params={"separator": SORT_KEY_SEPARATOR},
            )

        if not isinstance(self.set_id, str) or not self.set_id.strip():
            errors["set_id"] = FieldError(
                code=SCHEDULE_SET,
                detail="must be a non-blank string (the analytics-set the schedule runs)",
            )

        if not isinstance(self.cron, str) or not self.cron.strip():
            errors["cron"] = FieldError(
                code=SCHEDULE_CRON,
                detail="must be a non-blank schedule expression (cron/rate/at)",
            )

        # `enabled` must be a genuine bool (not a truthy string/int) — the stored flag drives
        # whether an unattended run fires. `bool` is a subclass of `int`, so check bool first.
        if not isinstance(self.enabled, bool):
            errors["enabled"] = FieldError(
                code=SCHEDULE_ENABLED, detail="must be a boolean"
            )

        # `created_by` is attribution-only (R5 create-time gate) — optional and un-gated here.

        if errors:
            raise ScheduleValidationError(errors)

    # ── storage-shape mapping (used by the repository; storage-agnostic here) ─────────

    def to_item(self) -> dict[str, Any]:
        """Serialize to the plain dict the repository persists (validated first).

        Carries the domain-facing attributes only (``tenant_id`` / ``schedule_id`` / ``set_id``
        / ``cron`` / ``created_by`` / ``enabled`` / ``created_at`` / ``updated_at``); the
        repository stamps the physical primary-key attributes on top. Validates before
        serializing so a malformed entry can never be written.
        """
        self.validate()
        return {
            "tenant_id": self.tenant_id,
            "schedule_id": self.schedule_id,
            "set_id": self.set_id,
            "cron": self.cron,
            "created_by": self.created_by,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_item(cls, item: Mapping[str, Any]) -> ScheduleEntry:
        """Rebuild an entry from a stored item (inverse of :meth:`to_item`).

        Tolerant of the physical primary-key attributes the repository adds (e.g. ``sk``): it
        reads only the domain attributes. ``enabled`` defaults to ``True`` for a legacy item
        written before the field existed (a schedule is live unless explicitly disabled) and is
        coerced to a genuine bool; ``created_by`` defaults to blank (older items carry no
        attribution).
        """
        if not isinstance(item, Mapping):
            raise ScheduleValidationError(
                {"item": FieldError(code=SCHEDULE_SET, detail="must be a mapping")}
            )
        created_by = item.get("created_by")
        # `enabled` defaults to True when absent (legacy item); any present value is coerced to
        # a genuine bool so a stored non-bool never leaks through as the live/disabled flag.
        raw_enabled = item.get("enabled", True)
        enabled = bool(raw_enabled) if raw_enabled is not None else True
        return cls(
            tenant_id=item.get("tenant_id", ""),
            schedule_id=item.get("schedule_id", ""),
            set_id=item.get("set_id", ""),
            cron=item.get("cron", ""),
            created_by=created_by if isinstance(created_by, str) else "",
            enabled=enabled,
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )

    def sort_order_key(self) -> tuple[str, str]:
        """Stable sort key for list presentation: ``(set_id, schedule_id)`` ascending."""
        return (self.set_id, self.schedule_id)
