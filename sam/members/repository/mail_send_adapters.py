"""
Production adapters for the mail-send WORKER ports (R4, pivot-output-actions task 4.3) — the
repository/adapter-layer implementations of the two seams the worker service depends on:

- :class:`SesBotoSender` — the boto3 SES send port (``SesSender``). The sole SES touch-point:
  ``send_email`` for a simple message, ``send_raw_email`` (MIME) when the job carries an
  attachment. Scoped to the verified sender identity (``SES_SENDER_EMAIL``) + the configuration
  set (``SES_CONFIGURATION_SET``) resolved fail-fast from the env — the same contract the SAM
  template IAM statement (``MailWorkerSendViaSes``) is Condition-scoped to, so env var and grant
  cannot disagree. An SES business error is NOT raised here — it is reported on the
  :class:`~sam.members.worker.mail_send_worker.SesSendOutcome` so the SERVICE decides
  retryable-vs-permanent (keeping the SES-limit policy in one place).

- :class:`DynamoDbMailSentMarkerStore` — the idempotency-marker store port
  (``MailSentMarkerStore``). A CONDITIONAL ``attribute_not_exists`` put of a ``mailsent#<job_id>``
  item (:func:`~sam.members.repository.table_design.mail_sent_marker_sk`) so an at-least-once SQS
  redelivery of the same job finds the marker and is skipped. Metadata-only (job/run/set ids +
  timestamp + a TTL) — never message bodies or member PII.

Config + fail-fast (mirrors ``template_body_store`` / ``mail_send_queue``)
--------------------------------------------------------------------------
The sender/config-set env vars resolve fail-fast via :func:`services.dynamodb_client.require_env`
(``SES_SENDER_EMAIL`` has no default — a missing var breaks loudly; ``SES_CONFIGURATION_SET`` is
OPTIONAL and only attached when non-blank, mirroring the Flask ``ses_email_service.py``
contract). The boto3 clients + the DynamoDB table resolve LAZILY on first use so importing this
module (and the worker, and the test suite) touches NO AWS. Both clients/handles are injectable so
tests supply fakes / a local emulator without an AWS round-trip (dependency inversion).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from botocore.exceptions import ClientError
from services.dynamodb_client import REGION_ENV_VAR, require_env

from sam.members.repository import table_design as td
from sam.members.worker.mail_send_worker import SesSendOutcome

logger = logging.getLogger(__name__)

__all__ = [
    "SES_CONFIGURATION_SET_ENV_VAR",
    "SES_SENDER_EMAIL_ENV_VAR",
    "DynamoDbMailSentMarkerStore",
    "SesBotoSender",
    "resolve_ses_configuration_set",
    "resolve_ses_sender_email",
]

#: The verified From address the worker sends as (fail-fast — no default). The SAM template's
#: SES IAM statement is Condition-scoped to exactly this value.
SES_SENDER_EMAIL_ENV_VAR = "SES_SENDER_EMAIL"

#: The SES configuration set that publishes bounce/complaint events. OPTIONAL — attached per
#: send only when non-blank (mirrors the Flask ``ses_email_service.py`` behaviour).
SES_CONFIGURATION_SET_ENV_VAR = "SES_CONFIGURATION_SET"

#: How long a mail-sent idempotency marker is retained (seconds). 14 days matches the SQS
#: message retention / DLQ window — a redelivery can only occur within that window, so once it
#: lapses the marker is no longer needed and DynamoDB TTL reclaims it (keeps the table from
#: accumulating markers forever). TTL is best-effort cleanup, not a correctness guarantee.
MAIL_SENT_MARKER_TTL_SECONDS = 14 * 24 * 60 * 60


def resolve_ses_sender_email() -> str:
    """Return the verified SES sender address from ``SES_SENDER_EMAIL``, or fail fast."""
    return require_env(SES_SENDER_EMAIL_ENV_VAR)


def resolve_ses_configuration_set() -> str:
    """Return the SES configuration set from ``SES_CONFIGURATION_SET`` (``""`` when unset).

    OPTIONAL — unlike the sender, a blank config set is valid (no config set wired yet); the
    sender only attaches it when non-blank. Read directly (not via ``require_env``) so an absent
    var is an empty string rather than a fail-fast error.
    """
    import os

    return (os.environ.get(SES_CONFIGURATION_SET_ENV_VAR) or "").strip()


class SesBotoSender:
    """The boto3-backed SES send port (``SesSender``) — the sole SES touch-point (R4).

    ``send_email`` for a simple (bodied) message; ``send_raw_email`` (MIME ``multipart/mixed``)
    when the job carries an attachment. Scoped to the resolved verified sender + config set. An
    SES ``ClientError`` is CAUGHT and reported on the outcome (``ok=False`` + the
    ``"<Code>: <Message>"`` error string) rather than raised, so the worker SERVICE applies the
    retryable-vs-permanent policy. The client + sender/config resolve lazily + fail-fast on first
    use; both are injectable for tests.

    Args:
        client: an optional boto3 SES client (or a compatible fake); resolved lazily otherwise.
        sender_email: an optional sender override; resolved lazily + fail-fast otherwise.
        configuration_set: an optional config-set override; resolved lazily otherwise.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        sender_email: str | None = None,
        configuration_set: str | None = None,
    ):
        self._client = client
        self._sender = sender_email
        self._config_set = configuration_set

    @property
    def client(self):
        """The boto3 SES client, resolved lazily + fail-fast on first use."""
        if self._client is None:
            import boto3

            self._client = boto3.client("ses", region_name=require_env(REGION_ENV_VAR))
        return self._client

    @property
    def sender(self) -> str:
        if self._sender is None:
            self._sender = resolve_ses_sender_email()
        return self._sender

    @property
    def configuration_set(self) -> str:
        if self._config_set is None:
            self._config_set = resolve_ses_configuration_set()
        return self._config_set

    def send(
        self,
        *,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        attachments: Sequence[Mapping[str, Any]] | None = None,
    ) -> SesSendOutcome:
        """Send one message via SES; report the outcome (never raises for an SES business error)."""
        try:
            if attachments:
                return self._send_raw(recipients, subject, body_html, attachments)
            return self._send_simple(recipients, subject, body_html)
        except ClientError as exc:  # SES business error → report, let the service classify it
            error = _client_error_string(exc)
            logger.warning("SES send failed: %s", error)
            return SesSendOutcome(ok=False, error=error)

    def _send_simple(
        self, recipients: Sequence[str], subject: str, body_html: str
    ) -> SesSendOutcome:
        kwargs: dict[str, Any] = {
            "Source": self.sender,
            "Destination": {"ToAddresses": list(recipients)},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": body_html or "", "Charset": "UTF-8"}},
            },
        }
        if self.configuration_set:
            kwargs["ConfigurationSetName"] = self.configuration_set
        size = len(subject.encode("utf-8")) + len((body_html or "").encode("utf-8"))
        response = self.client.send_email(**kwargs)
        return SesSendOutcome(
            ok=True, message_id=str(response.get("MessageId", "")), size_bytes=size
        )

    def _send_raw(
        self,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        attachments: Sequence[Mapping[str, Any]],
    ) -> SesSendOutcome:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body_html or "", "html", "utf-8"))
        for att in attachments:
            content = att.get("content") or b""
            if isinstance(content, memoryview):
                content = bytes(content)
            part = MIMEApplication(content)
            part.add_header(
                "Content-Disposition", "attachment", filename=att.get("filename", "attachment")
            )
            if att.get("content_type"):
                part.set_type(str(att["content_type"]))
            msg.attach(part)

        raw = msg.as_string()
        kwargs: dict[str, Any] = {
            "Source": self.sender,
            "Destinations": list(recipients),
            "RawMessage": {"Data": raw},
        }
        if self.configuration_set:
            kwargs["ConfigurationSetName"] = self.configuration_set
        response = self.client.send_raw_email(**kwargs)
        return SesSendOutcome(
            ok=True,
            message_id=str(response.get("MessageId", "")),
            size_bytes=len(raw.encode("utf-8")),
        )


class DynamoDbMailSentMarkerStore:
    """The DynamoDB-backed idempotency-marker store (``MailSentMarkerStore``) — the dedupe bridge.

    :meth:`mark_if_absent` does a CONDITIONAL ``PutItem`` with
    ``attribute_not_exists(<sort key>)`` so only the FIRST delivery of a ``job_id`` creates the
    ``mailsent#<job_id>`` marker; a redelivery's put fails the condition (``True`` → created /
    this call owns the send; ``False`` → already present → skip). Keyed by ``tenant_id`` (a
    marker only ever matches within its own tenant — Property 1). Metadata only + a TTL. The
    table resolves lazily + fail-fast on first use; injectable for tests.

    Args:
        table: an optional boto3 DynamoDB Table (or compatible fake); resolved lazily otherwise.
    """

    def __init__(self, table: Any = None):
        self._table = table

    @property
    def table(self):
        if self._table is None:
            self._table = td.get_members_table_resource()
        return self._table

    def mark_if_absent(
        self, tenant_id: str, job_id: str, metadata: Mapping[str, Any]
    ) -> bool:
        """Create the ``mailsent#<job_id>`` marker iff absent; return True iff THIS call created it."""
        if not tenant_id or not job_id:
            raise ValueError("mail-sent marker requires a non-empty tenant_id and job_id")

        now = datetime.now(timezone.utc)
        item: dict[str, Any] = {
            td.PARTITION_KEY_ATTR: tenant_id,
            td.SORT_KEY_ATTR: td.mail_sent_marker_sk(job_id),
            "job_id": job_id,
            "sent_at": now.isoformat(),
            "ttl": int(now.timestamp()) + MAIL_SENT_MARKER_TTL_SECONDS,
        }
        # Metadata only — ids + counts, NEVER bodies / member PII.
        for key in ("run_id", "set_id", "mode", "recipient_count"):
            value = metadata.get(key)
            if value is not None:
                item[key] = value

        try:
            self.table.put_item(
                Item=td.floats_to_decimal(item),
                ConditionExpression=(
                    f"attribute_not_exists({td.SORT_KEY_ATTR})"
                ),
            )
            return True
        except ClientError as exc:
            code = _client_error_code(exc)
            if code == "ConditionalCheckFailedException":
                return False  # marker already present → redelivery → skip the send
            raise


def _client_error_code(exc: Any) -> str:
    """Best-effort SES/DynamoDB ``ClientError`` code extraction (empty string when unavailable)."""
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            return str(error.get("Code", ""))
    return ""


def _client_error_string(exc: Any) -> str:
    """Render an SES ``ClientError`` as ``"<Code>: <Message>"`` (the shape the worker classifies)."""
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            return f"{error.get('Code', 'Error')}: {error.get('Message', str(exc))}"
    return str(exc)
