"""
SQS-backed **mail-send queue** (R4, pivot-output-actions task 4.2) — the production
send-job enqueue port the execute-and-deliver service (task 4.1) depends on.

The send is **queued, not synchronous** (R4, design §4.1/§4.2): the interactive
``POST /members/analytics-sets/{set_id}/deliver`` route (and, later, the EventBridge-
scheduled run — R5) must NOT block on the actual SES send — a per-recipient mail-merge is N
sends and SES is rate-limited, so a synchronous request would time out. The execute-and-
deliver service therefore RESOLVES the set + builds the output and then ENQUEUES one send job
per unit of work; a worker Lambda (task 4.3/4.4 — the consumer side, NOT built here) drains the
queue at the SES rate.

Layering (design §4.1, steering 35)
-----------------------------------
The execute-and-deliver SERVICE (``sam/members/domain/execute_and_deliver.py``) depends ONLY on
the :class:`MailSendQueuePort` Protocol (``enqueue`` / ``enqueue_many``) so it carries NO boto3
dependency and stays storage-agnostic — exactly how
:class:`~sam.members.domain.template_service.TemplateService` depends only on the
``TemplateBodyStore`` shape, not on :class:`~sam.members.repository.template_body_store.
S3TemplateBodyStore`. THIS module is the production implementation of that port — the SQS
counterpart to the S3 body store: it lives in the repository/adapter layer (the domain never
imports it; the handler edge injects it) and is the sole SQS touch-point.

Config + fail-fast (mirrors ``template_body_store.resolve_shared_bucket_name``)
-------------------------------------------------------------------------------
The queue URL is resolved from ``MAIL_SEND_QUEUE_URL`` (the real SQS queue URL, wired per env by
``sam/members/template.yaml`` from the ``members-mail-send[-test]`` queue) with NO default — a
missing/blank var raises :class:`~services.dynamodb_client.DynamoDBConfigError`, reusing the one
fail-fast ``require_env`` so the no-dangerous-fallback discipline (steering 23) lives in a single
place. The boto3 SQS client + the queue URL resolve LAZILY on first use, so importing this module
(and the handler, and the test suite) touches NO AWS. The client is injectable so a test can
supply a fake / a local emulator without an AWS round-trip (dependency inversion) — the route
tests inject a FAKE queue and assert the service enqueued, never touching SQS.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Protocol

from services.dynamodb_client import REGION_ENV_VAR, require_env

__all__ = [
    "MAIL_SEND_QUEUE_URL_ENV_VAR",
    "MailSendQueuePort",
    "SqsMailSendQueue",
    "resolve_mail_send_queue_url",
]

#: The env var carrying the real SQS send-queue URL (``members-mail-send[-test]``), wired per env
#: by the SAM template (task 4.2 IaC). No default is ever synthesized — a missing/blank var fails
#: fast (mirrors ``MEMBERS_TABLE`` / ``S3_SHARED_BUCKET``), so a mis-deploy that forgot to wire the
#: queue breaks loudly rather than silently dropping sends.
MAIL_SEND_QUEUE_URL_ENV_VAR = "MAIL_SEND_QUEUE_URL"


def resolve_mail_send_queue_url() -> str:
    """Return the SQS send-queue URL from ``MAIL_SEND_QUEUE_URL``, or fail fast.

    Reuses the fail-fast client (:func:`services.dynamodb_client.require_env`) so the
    no-dangerous-fallback discipline (steering 23) lives in one place.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: ``MAIL_SEND_QUEUE_URL`` is missing/blank.
    """
    return require_env(MAIL_SEND_QUEUE_URL_ENV_VAR)


class MailSendQueuePort(Protocol):
    """The minimal enqueue port the execute-and-deliver service (task 4.1) depends on.

    Storage-agnostic — the service enqueues send jobs through this shape and never learns that
    the backing store is SQS. :class:`SqsMailSendQueue` is the production implementation; a test
    injects an in-memory fake with the same two methods.
    """

    def enqueue(self, job: Mapping[str, Any]) -> str:
        """Enqueue one send job; return the backing message id."""
        ...

    def enqueue_many(self, jobs: Iterable[Mapping[str, Any]]) -> list[str]:
        """Enqueue many send jobs (per-recipient fan-out); return the message ids in order."""
        ...


class SqsMailSendQueue:
    """The SQS-backed send-job queue — the production :class:`MailSendQueuePort` (R4).

    Structurally satisfies the port (``enqueue`` / ``enqueue_many``) so the domain service
    depends on the shape, not this class. Each job is a plain JSON-serializable mapping (the
    send-job envelope the worker consumes — task 4.3); this adapter only serializes it and calls
    ``SendMessage``, it owns no job-shape logic of its own. The SQS client + queue URL resolve
    LAZILY + fail-fast on first use so import touches no AWS. The client is injectable (dependency
    inversion) for tests.

    Args:
        client: An optional boto3 SQS client (or a compatible fake). If omitted, resolved lazily
            on first use against the resolved region.
        queue_url: An optional queue-URL override. If omitted, resolved lazily + fail-fast from
            ``MAIL_SEND_QUEUE_URL`` on first use.
    """

    def __init__(self, *, client: Any = None, queue_url: str | None = None):
        self._client = client
        self._queue_url = queue_url

    # ── lazy, fail-fast resource resolution ───────────────────────────────────────────

    @property
    def client(self):
        """The boto3 SQS client, resolved lazily + fail-fast on first use."""
        if self._client is None:
            import boto3

            self._client = boto3.client("sqs", region_name=require_env(REGION_ENV_VAR))
        return self._client

    @property
    def queue_url(self) -> str:
        """The send-queue URL, resolved lazily + fail-fast from the env on first use."""
        if self._queue_url is None:
            self._queue_url = resolve_mail_send_queue_url()
        return self._queue_url

    # ── the MailSendQueuePort port ─────────────────────────────────────────────────────

    def enqueue(self, job: Mapping[str, Any]) -> str:
        """Enqueue one send job as a JSON ``SendMessage``; return the SQS ``MessageId``.

        The job mapping is the send-job envelope the worker (task 4.3) consumes — this adapter
        serializes it verbatim (``json.dumps``) and never inspects it. A non-mapping job is a
        programming error (fail loud) rather than a silent empty send.
        """
        if not isinstance(job, Mapping):
            raise TypeError("a send job must be a mapping (the send-job envelope)")
        response = self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(job, default=str),
        )
        return str(response.get("MessageId", ""))

    def enqueue_many(self, jobs: Iterable[Mapping[str, Any]]) -> list[str]:
        """Enqueue many send jobs (``per_recipient`` fan-out); return the message ids in order.

        Sends one message per job (not an SQS batch) — the worker is idempotent on a stable job
        id (design §4.2), so one-message-per-job keeps the enqueue path simple and each job
        independently retryable/dead-letterable. Returns the ids in the same order as ``jobs`` so
        a caller can correlate.
        """
        return [self.enqueue(job) for job in jobs]
