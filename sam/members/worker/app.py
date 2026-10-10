"""
S5 / pivot-output-actions task 4.3 — the mail-send WORKER Lambda **entry point** (thin adapter).

This is the CONSUMER side of the R4 queued send path (design §4.2/§4.3): the SQS event source
on ``MailSendQueue`` (task 4.4, ``BatchSize 1``, bounded concurrency) pushes send jobs here; the
handler drains them and does the actual SES send so the ``deliver`` request / scheduler never
blocks on it.

Thin by design (steering 35): the handler's whole job is

    parse the SQS event → deserialize each record's envelope → delegate to the service → report

and nothing else. All business logic — dedupe on the stable ``job_id``, render (mail-merge /
attach), SES send respecting the SES limits, metadata-only audit, retryable-vs-permanent
classification — lives in :class:`~sam.members.worker.mail_send_worker.MailSendWorker`. The
production ports (boto3 SES sender, the DynamoDB marker store, the template service, the audit
sink) are wired once at cold start by :func:`get_worker` and resolve lazily + fail-fast on first
use, so importing this module (and the test suite) touches NO AWS. Tests set
``_WORKER`` / patch :func:`get_worker` to inject a worker over fakes.

Batch + partial-batch failures (design §4.2/§9)
-----------------------------------------------
The event source is ``BatchSize 1`` (one record per invocation), but the handler loops the
batch DEFENSIVELY. It reports failures using the SQS **partial batch response**
(``batchItemFailures``) so a FAILED record is retried (→ DLQ after ``maxReceiveCount``) while
successful records in the same batch are deleted — a failure is never swallowed and a success is
never needlessly re-driven. A :class:`~sam.members.worker.mail_send_worker.MailSendRetryable`
(SES throttle) and a :class:`~sam.members.worker.mail_send_worker.MailSendPermanent` (non-
retryable fault) BOTH mark the record failed so SQS redelivers it toward the DLQ rather than
dropping the send.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

__all__ = ["get_worker", "handler"]

#: The module-global worker, built once at cold start (``None`` until first use). A warm Lambda
#: container reuses it across invocations (the ports resolve lazily + fail-fast on first use).
_WORKER: Any = None


def get_worker() -> Any:
    """Return the module-global mail-send worker, building it once at cold start (R4, task 4.3).

    Wires the task-4.3 service over its production ports:
      * :class:`~sam.members.repository.mail_send_adapters.SesBotoSender` — the sole SES touch-
        point (fail-fast sender + optional config set from the env);
      * :class:`~sam.members.repository.mail_send_adapters.DynamoDbMailSentMarkerStore` — the
        conditional ``mailsent#<job_id>`` dedupe marker on the members table;
      * :class:`~sam.members.domain.template_service.TemplateService` over the Members metadata
        store (the repository) + the S3 body store — for the ``per_recipient`` merge /
        ``to_fixed`` covering body;
      * :func:`~sam.members.worker.mail_audit.log_analytics_output` — the metadata-only audit
        sink (SAM-plane, Flask-free).

    Everything resolves lazily + fail-fast on first use, so importing this module (and the auth-
    free worker tests) never touches AWS. Tests patch this accessor (or set ``_WORKER``) to
    inject a worker over in-memory fakes.
    """
    global _WORKER
    if _WORKER is None:
        from sam.members.domain.template_service import TemplateService
        from sam.members.repository.mail_send_adapters import (
            DynamoDbMailSentMarkerStore,
            SesBotoSender,
        )
        from sam.members.repository.members_repository import DynamoDbMembersRepository
        from sam.members.repository.template_body_store import S3TemplateBodyStore
        from sam.members.worker.mail_audit import log_analytics_output
        from sam.members.worker.mail_send_worker import MailSendWorker

        repo = DynamoDbMembersRepository()
        template_service = TemplateService(repo, S3TemplateBodyStore())
        _WORKER = MailSendWorker(
            ses=SesBotoSender(),
            marker_store=DynamoDbMailSentMarkerStore(),
            template_service=template_service,
            audit=log_analytics_output,
            # Advance the send-run status tally (R9.1) — same repo the template service uses.
            run_store=repo,
        )
    return _WORKER


def handler(event: Any, context: Any = None) -> dict[str, Any]:
    """Drain one SQS batch of send jobs; return the SQS partial-batch failure response.

    Parses the SQS event, deserializes each record's JSON body into the send-job envelope, and
    delegates each to the worker service. A record that raises (throttle → retryable, or a
    permanent fault) is reported in ``batchItemFailures`` so SQS redelivers it toward the DLQ;
    a succeeded / deduped record is left out so it is deleted. ``BatchSize 1`` means a single
    record per invocation in production, but the batch is handled defensively.
    """
    records = event.get("Records", []) if isinstance(event, dict) else []
    worker = get_worker()

    failures: list[dict[str, str]] = []
    for record in records:
        message_id = record.get("messageId", "") if isinstance(record, dict) else ""
        try:
            envelope = _parse_record(record)
            result = worker.process(envelope)
            logger.info(
                "mail-send worker: processed message %s (job=%s sent=%s deduped=%s)",
                message_id,
                result.job_id,
                result.sent,
                result.deduped,
            )
        except Exception as exc:  # noqa: BLE001 — a failed record must be retried, not dropped
            logger.warning(
                "mail-send worker: message %s failed (will retry → DLQ after N): %s",
                message_id,
                exc,
            )
            if message_id:
                failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}


def _parse_record(record: Any) -> dict[str, Any]:
    """Deserialize one SQS record's JSON body into the send-job envelope mapping.

    Mirrors the enqueue side (``handler/_dispatch._mail_job_to_envelope`` →
    ``repository/mail_send_queue.SqsMailSendQueue.enqueue`` which ``json.dumps`` the mapping as
    the ``MessageBody``), so the worker deserializes the SAME shape. A non-JSON / non-object body
    is a malformed message — raise so it is reported failed and dead-letters.
    """
    if not isinstance(record, dict):
        raise TypeError("SQS record must be an object")
    body = record.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("SQS record is missing a JSON 'body'")
    envelope = json.loads(body)
    if not isinstance(envelope, dict):
        raise TypeError("send-job envelope must be a JSON object")
    return envelope
