"""
Production adapters for the mail-send WORKER ports (R4, pivot-output-actions task 4.3) — the
repository/adapter-layer implementations of the two seams the worker service depends on:

- :class:`SesBotoSender` — the boto3 SES send port (``SesSender``). The sole SES touch-point:
  ``send_email`` for a simple message, ``send_raw_email`` (MIME) when the job carries an
  attachment. The verified From + Reply-To are supplied PER SEND (R4, mail-spec task 1.2) — the
  caller (worker, task 1.3) resolves the active tenant's ``noreply@<tenant-domain>`` From and the
  triggering user's Reply-To and passes them in; there is NO single global ``SES_SENDER_EMAIL``
  source of truth (its removal kills the ``jabaki.nl`` substitute-sender leak). Only the
  configuration set (``SES_CONFIGURATION_SET``) is still resolved fail-safe from the env. An SES
  business error is NOT raised here — it is reported on the
  :class:`~sam.members.worker.mail_send_worker.SesSendOutcome` so the SERVICE decides
  retryable-vs-permanent (keeping the SES-limit policy in one place).

- :class:`DynamoDbMailSentMarkerStore` — the idempotency-marker store port
  (``MailSentMarkerStore``). A CONDITIONAL ``attribute_not_exists`` put of a ``mailsent#<job_id>``
  item (:func:`~sam.members.repository.table_design.mail_sent_marker_sk`) so an at-least-once SQS
  redelivery of the same job finds the marker and is skipped. Metadata-only (job/run/set ids +
  timestamp + a TTL) — never message bodies or member PII.

Config + fail-fast (mirrors ``template_body_store`` / ``mail_send_queue``)
--------------------------------------------------------------------------
There is NO global sender env var any more (mail-spec task 1.2): the verified From + Reply-To are
PER-SEND arguments, so the adapter never reads ``SES_SENDER_EMAIL`` and never falls back to a
substitute sender. ``SES_CONFIGURATION_SET`` remains OPTIONAL and is only attached when non-blank
(mirroring the Flask ``ses_email_service.py`` contract). The boto3 clients + the DynamoDB table resolve LAZILY on first use so importing this
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
    "DynamoDbMailSentMarkerStore",
    "SesBotoSender",
    "resolve_ses_configuration_set",
]

#: The SES configuration set that publishes bounce/complaint events. OPTIONAL — attached per
#: send only when non-blank (mirrors the Flask ``ses_email_service.py`` behaviour).
SES_CONFIGURATION_SET_ENV_VAR = "SES_CONFIGURATION_SET"

#: How long a mail-sent idempotency marker is retained (seconds). 14 days matches the SQS
#: message retention / DLQ window — a redelivery can only occur within that window, so once it
#: lapses the marker is no longer needed and DynamoDB TTL reclaims it (keeps the table from
#: accumulating markers forever). TTL is best-effort cleanup, not a correctness guarantee.
MAIL_SENT_MARKER_TTL_SECONDS = 14 * 24 * 60 * 60


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
    when the job carries an attachment. The verified **From** and the **Reply-To** are supplied
    PER SEND (mail-spec task 1.2): the caller resolves the active tenant's
    ``noreply@<tenant-domain>`` From + the triggering user's Reply-To and passes them in. There is
    NO global ``SES_SENDER_EMAIL`` source of truth and NO substitute-sender fallback — a send
    without a resolved From is refused up front (Property 2; killing the ``jabaki.nl`` leak).

    An SES ``ClientError`` is CAUGHT and reported on the outcome (``ok=False`` + the
    ``"<Code>: <Message>"`` error string) rather than raised, so the worker SERVICE applies the
    retryable-vs-permanent policy. The client + config set resolve lazily on first use; both are
    injectable for tests.

    Args:
        client: an optional boto3 SES client (or a compatible fake); resolved lazily otherwise.
        configuration_set: an optional config-set override; resolved lazily otherwise.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        configuration_set: str | None = None,
    ):
        self._client = client
        self._config_set = configuration_set

    @property
    def client(self):
        """The boto3 SES client, resolved lazily + fail-fast on first use."""
        if self._client is None:
            import boto3

            self._client = boto3.client("ses", region_name=require_env(REGION_ENV_VAR))
        return self._client

    @property
    def configuration_set(self) -> str:
        if self._config_set is None:
            self._config_set = resolve_ses_configuration_set()
        return self._config_set

    def send(
        self,
        *,
        from_address: str,
        reply_to: str | None = None,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        tags: Mapping[str, str] | None = None,
    ) -> SesSendOutcome:
        """Send one message via SES from ``from_address`` (Reply-To ``reply_to``); report the outcome.

        ``from_address`` is the per-send resolved tenant sender (``noreply@<tenant-domain>``) —
        required, no fallback (Property 2). ``reply_to`` is the triggering user's address when
        present. ``tags`` is the per-send SES MESSAGE TAGS the config set echoes back on every
        feedback event (``mail.tags``) so the task-5.2 ingestion handler can ROUTE the
        bounce/complaint/delivery back to the originating Members run (R9.5) — the caller (worker,
        task 1.3) supplies ``{SES_TAG_TENANT_ID: <enc tenant>, SES_TAG_RUN_ID: <enc run>}`` already
        encoded via :func:`encode_ses_tag_value`. Blank tag values are OMITTED (SES rejects an
        empty value). Never raises for an SES business error — it is reported on the outcome so the
        worker SERVICE classifies it retryable-vs-permanent.
        """
        sender = (from_address or "").strip()
        if not sender:
            # No resolved From → refuse rather than send from a substitute (Property 2 / R4.2).
            return SesSendOutcome(
                ok=False,
                error="MessageRejected: no resolved sender (From) for this send",
            )
        reply = (reply_to or "").strip() or None
        message_tags = _clean_message_tags(tags)
        try:
            if attachments:
                return self._send_raw(
                    sender, reply, recipients, subject, body_html, attachments, message_tags
                )
            return self._send_simple(
                sender, reply, recipients, subject, body_html, message_tags
            )
        except ClientError as exc:  # SES business error → report, let the service classify it
            error = _client_error_string(exc)
            logger.warning("SES send failed: %s", error)
            return SesSendOutcome(ok=False, error=error)

    def _send_simple(
        self,
        sender: str,
        reply_to: str | None,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        message_tags: list[dict[str, str]],
    ) -> SesSendOutcome:
        kwargs: dict[str, Any] = {
            "Source": sender,
            "Destination": {"ToAddresses": list(recipients)},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": body_html or "", "Charset": "UTF-8"}},
            },
        }
        if reply_to:
            kwargs["ReplyToAddresses"] = [reply_to]
        if self.configuration_set:
            kwargs["ConfigurationSetName"] = self.configuration_set
        # SES message tags (the feedback routing key, R9.5) — supplied via the SendEmail `Tags`
        # parameter on the simple path (echoed back as `mail.tags` on every feedback event).
        if message_tags:
            kwargs["Tags"] = message_tags
        size = len(subject.encode("utf-8")) + len((body_html or "").encode("utf-8"))
        response = self.client.send_email(**kwargs)
        return SesSendOutcome(
            ok=True, message_id=str(response.get("MessageId", "")), size_bytes=size
        )

    def _send_raw(
        self,
        sender: str,
        reply_to: str | None,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        attachments: Sequence[Mapping[str, Any]],
        message_tags: list[dict[str, str]],
    ) -> SesSendOutcome:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        if reply_to:
            msg["Reply-To"] = reply_to
        # SES message tags on the RAW (attachment) path cannot ride the SendRawEmail `Tags` of the
        # simple path — SES reads them off the `X-SES-MESSAGE-TAGS` header instead (same key=value
        # pairs, comma-separated), echoed back identically as `mail.tags` (R9.5). One mechanism,
        # both send paths, so a to_fixed attachment send is routed back exactly like a per_recipient.
        if message_tags:
            msg["X-SES-MESSAGE-TAGS"] = ", ".join(
                f"{t['Name']}={t['Value']}" for t in message_tags
            )
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
            "Source": sender,
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


def _clean_message_tags(tags: Mapping[str, str] | None) -> list[dict[str, str]]:
    """Normalise the per-send tag mapping into the SES ``[{Name, Value}]`` list, dropping blanks.

    SES rejects an empty tag VALUE, so a tag whose (already-encoded) value is blank — e.g. a
    scheduled run with no ``run_id`` would never happen, but a defensive guard — is OMITTED rather
    than stamped empty. Both send paths (simple `Tags`, raw `X-SES-MESSAGE-TAGS`) consume this list.
    """
    if not tags:
        return []
    out: list[dict[str, str]] = []
    for name, value in tags.items():
        if name and value:
            out.append({"Name": str(name), "Value": str(value)})
    return out


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
