"""Status/audit record building and failure recording.

Part of MailSendWorker (task 7).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)


class MailAuditMixin:
    """Status/audit record building and failure recording."""

    def _advance_run(
        self, tenant_id: str, run_id: str, *, sent: int = 0, failed: int = 0
    ) -> None:
        """Advance the run tally (best-effort): mark sending + add sent/failed counts, then close the run
        when every recipient it was sized for has been accounted for. Never let a
        status-tracking error fail the actual send/delete (the mail already went or will retry)."""
        if self._run_store is None or not run_id:
            return
        try:
            self._run_store.update_mail_run_status(tenant_id, run_id, "sending")
            updated = None
            if sent or failed:
                updated = self._run_store.increment_mail_run_counts(
                    tenant_id, run_id, sent=sent, failed=failed
                )
            # Determine the current tally + recipient count to decide completion.
            run = updated if updated is not None else self._run_store.get_mail_run(tenant_id, run_id)
            if run is not None:
                total = int(run.get("recipient_count") or 0)
                done = int(run.get("sent") or 0) + int(run.get("failed") or 0)
                if total > 0 and done >= total and run.get("status") != "completed":
                    self._run_store.update_mail_run_status(tenant_id, run_id, "completed")
        except Exception:
            logger.warning(
                "mail-send worker: run-status update failed for run %s (non-fatal)",
                run_id,
            )

    def _record_run_failure(self, tenant_id, run_id, recipients, *, reason):
        """Record a permanent send failure against the run (best-effort): a FAILURE-only
        `mailrecipient#` sub-record per recipient + a `failed` tally increment. Never let a
        status-tracking error mask the original send failure (the job still dead-letters)."""
        if self._run_store is None or not run_id:
            return
        try:
            for address in recipients:
                self._run_store.record_mail_failure(
                    tenant_id, run_id, address=address, reason=reason
                )
            self._run_store.increment_mail_run_counts(
                tenant_id, run_id, failed=len(recipients)
            )
        except Exception:
            logger.warning(
                "mail-send worker: run-failure recording failed for run %s (non-fatal)",
                run_id,
            )

    def _emit_audit(
        self, envelope: Mapping[str, Any], tenant_id: str, recipient_count: int
    ) -> None:
        """Emit the metadata-only ``ses_mail`` audit record (design §8) — never bodies / PII.

        Only the SHAPE of the send is recorded: who ran it (``run_id`` attribution), the tenant,
        the set, the recipient COUNT, and the output kind. No subject, no body, no merge values,
        no recipient addresses. A failing audit never fails the send (the mail already went) — it
        is logged at warning.
        """
        if self._audit is None:
            return
        try:
            self._audit(
                actor=str(envelope.get("run_id") or "mail-send-worker"),
                actor_roles=[],
                tenant=tenant_id,
                output_kind="ses_mail",
                set_key=envelope.get("set_id"),
                record_count=recipient_count,
            )
        except Exception as exc:
            logger.warning(
                "mail-send worker: audit emit failed for job %s: %s",
                envelope.get("job_id"),
                exc,
            )
