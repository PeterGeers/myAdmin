"""In-place update operations (mail-run counters/status).

Part of DynamoDbMembersRepository (task 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.repository import table_design as td

from ._members_repository_shared import (
    MAIL_RECIPIENT_STATUS_BOUNCED,
    MAIL_RECIPIENT_STATUS_COMPLAINT,
    MAIL_RECIPIENT_STATUS_FAILED,
    MAIL_RUN_STATUS_COMPLETED,
    MAIL_RUN_STATUS_QUEUED,
    MAIL_RUN_STATUS_SENDING,
)


class MembersUpdateMixin:
    """In-place update operations (mail-run counters/status)."""

    def update_mail_run_status(
        self, tenant_id: str, run_id: str, status: str
    ) -> Mapping[str, Any] | None:
        """Advance a run's ``status`` from the worker (``queued`` → ``sending`` → ``completed``).

        A read-modify-write of the tenant-pinned tally (the worker drains one job at a time —
        BatchSize 1 — so there is no concurrent writer to race). Returns the updated tally, or
        ``None`` when no such run exists (nothing to advance). ``ttl`` / ``created_at`` are
        preserved; ``updated_at`` is refreshed.
        """
        self._require_tenant(tenant_id)
        if status not in (
            MAIL_RUN_STATUS_QUEUED,
            MAIL_RUN_STATUS_SENDING,
            MAIL_RUN_STATUS_COMPLETED,
        ):
            raise ValueError(f"unknown mail-run status {status!r}")
        current = self.get_mail_run(tenant_id, run_id)
        if current is None:
            return None
        updated = dict(current)
        updated["status"] = status
        updated["updated_at"] = self._now_iso()
        item = td.build_mail_run_item(tenant_id, run_id, updated)
        self.table.put_item(Item=item)
        return item

    def increment_mail_run_counts(
        self, tenant_id: str, run_id: str, *, sent: int = 0, failed: int = 0
    ) -> Mapping[str, Any] | None:
        """Add to a run's ``sent`` / ``failed`` tally as the worker processes jobs (R9.1).

        A read-modify-write of the tenant-pinned tally (worker BatchSize 1 — no concurrent
        writer). Returns the updated tally, or ``None`` when no such run exists. Negative deltas
        are supported so a late bounce can move a count from sent→failed (see
        :meth:`record_mail_failure` with ``adjust_run_tally=True``); the tally is floored at 0.
        """
        self._require_tenant(tenant_id)
        current = self.get_mail_run(tenant_id, run_id)
        if current is None:
            return None
        updated = dict(current)
        updated["sent"] = max(0, int(updated.get("sent", 0)) + int(sent))
        updated["failed"] = max(0, int(updated.get("failed", 0)) + int(failed))
        updated["updated_at"] = self._now_iso()
        item = td.build_mail_run_item(tenant_id, run_id, updated)
        self.table.put_item(Item=item)
        return item

    def record_mail_failure(
        self,
        tenant_id: str,
        run_id: str,
        *,
        address: str,
        status: str = MAIL_RECIPIENT_STATUS_FAILED,
        reason: str | None = None,
        message_id: str | None = None,
        adjust_run_tally: bool = False,
    ) -> Mapping[str, Any]:
        """Write a FAILURE-ONLY ``mailrecipient#<run_id>#<n>`` sub-record (R9.5, design decision).

        Written ONLY for a failure — a send-time reject / no-address, or a LATE async
        bounce/complaint (R8.4) for a recipient that SUCCEEDED at send time (there is no
        sub-record yet, since successes are only counted). ``adjust_run_tally=True`` is the late
        path: it ALSO moves the run tally from sent→failed (``sent -= 1`` / ``failed += 1``),
        since the recipient was previously counted as sent. The ``<n>`` sort-key segment is the
        run's current failure COUNT (``failed``) so two failures never collide. Sets the TTL
        (default 90 days). Tenant-pinned (Property 3). Metadata only — the ``reason`` is an SES
        code/message, never member PII beyond the address being mailed.
        """
        self._require_tenant(tenant_id)
        if not run_id:
            raise ValueError("run_id must be non-empty")
        if status not in (
            MAIL_RECIPIENT_STATUS_FAILED,
            MAIL_RECIPIENT_STATUS_BOUNCED,
            MAIL_RECIPIENT_STATUS_COMPLAINT,
        ):
            raise ValueError(f"unknown mail-recipient failure status {status!r}")

        # The failure sequence is the run's failure count SO FAR (0-based) — a stable, collision-
        # free per-run discriminator. Fall back to the number of existing sub-records if the run
        # tally is absent (defensive — a late bounce could arrive after a manual run delete).
        run = self.get_mail_run(tenant_id, run_id)
        if run is not None:
            seq = int(run.get("failed", 0))
        else:
            seq = len(self.list_mail_run_failures(tenant_id, run_id))

        entry: dict[str, Any] = {
            "address": address,
            "status": status,
            "updated_at": self._now_iso(),
            "ttl": self._ttl_epoch(),
        }
        if reason is not None:
            entry["reason"] = reason
        if message_id is not None:
            entry["message_id"] = message_id
        item = td.build_mail_recipient_item(tenant_id, run_id, str(seq), entry)
        self.table.put_item(Item=item)

        # Adjust the run tally. On the LATE path the recipient was previously counted as sent, so
        # move it sent→failed; otherwise just increment failed (a send-time failure the worker is
        # recording as it processes the job).
        if run is not None:
            if adjust_run_tally:
                self.increment_mail_run_counts(tenant_id, run_id, sent=-1, failed=1)
            else:
                self.increment_mail_run_counts(tenant_id, run_id, failed=1)
        return item
