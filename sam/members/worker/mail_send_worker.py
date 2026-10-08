"""
The **mail-send worker service** (R4, pivot-output-actions task 4.3) — the CONSUMER side of
the queued send path (design §4.2/§4.3). It takes ONE deserialized send-job envelope (the
shape ``handler/_dispatch._mail_job_to_envelope`` writes onto the queue — task 4.2) and:

1. **Dedupes on the stable ``job_id``** (idempotency, design §4.2). SQS is at-least-once, so a
   redelivery of the same logical job must be a no-op, not a second send. The worker does a
   CONDITIONAL ``attribute_not_exists`` put of a ``mailsent#<job_id>`` marker BEFORE sending;
   if the marker already exists the job was already handled and the worker returns without
   sending again.
2. **Renders** the message:
   - ``per_recipient`` → mail-merge the job's ``template_id`` with the job's ``merge_values``
     (reusing :class:`~sam.members.domain.template_service.TemplateService.render_for_recipient`
     → :func:`~sam.members.domain.template.render_with_merge`), one recipient.
   - ``to_fixed`` → build the attachment (``csv`` / ``pdf_labels``) from the job's ``rows`` +
     an optional covering-template body, sent to the fixed recipients.
3. **Sends via SES** from ``SES_SENDER_EMAIL`` (attaching ``SES_CONFIGURATION_SET`` when set),
   respecting ALL SES limits (recipients-per-message, message size — design §6.4). The actual
   SES call is an injected PORT (:class:`SesSender`) so the service carries no boto3.
4. **Audits metadata-only** (``log_analytics_output`` / ``ses_mail``) — tenant, set, run,
   recipient COUNT, output kind — NEVER message bodies or member PII (design §8). The audit
   sink is an injected port.

Retry / DLQ (design §4.2/§9)
----------------------------
On a RATE-LIMIT / throttle (detected with the same markers as the Flask
``members_mail._is_ses_rate_limited``) the worker RAISES :class:`MailSendRetryable` — it does
NOT swallow — so the SQS message is not deleted, becomes visible again, and is retried; after
``maxReceiveCount`` (5, task 4.4) the queue redrives it to the DLQ. A PERMANENT SES failure
(e.g. a non-retryable ``MessageRejected``) also RAISES (:class:`MailSendPermanent`) so it
surfaces and dead-letters rather than being silently dropped. A successful send (or a deduped
redelivery) returns normally so the Lambda event-source deletes the message.

Layering (steering 35)
----------------------
This is the SERVICE (business logic, storage-agnostic). It depends only on injected ports:
:class:`SesSender`, :class:`MailSentMarkerStore`, a template renderer with
``render_for_recipient(...)``, and an audit callable. The thin Lambda entrypoint
(:mod:`sam.members.worker.app`) wires the production ports and delegates. ``tenant_id`` is
authoritative on every path (it rides on the envelope the service that enqueued stamped from
the verified context — never trusted from a member body).
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_LANG",
    "MAX_MESSAGE_BYTES",
    "MAX_RECIPIENTS_PER_MESSAGE",
    "MailSendPermanent",
    "MailSendResult",
    "MailSendRetryable",
    "MailSendWorker",
    "MailSentMarkerStore",
    "SesSendOutcome",
    "SesSender",
    "is_ses_rate_limited",
]

#: The language variant a ``per_recipient`` merge renders when the job names none. ``nl`` is the
#: Members plane's primary language (the app is NL-first); a template without ``nl`` surfaces a
#: clear render error rather than a silent wrong-language send.
DEFAULT_LANG = "nl"

#: SES hard limit: at most 50 recipients (To + Cc + Bcc) PER message (design §6.4). A
#: ``to_fixed`` job with more fixed recipients than this would be rejected by SES, so the worker
#: refuses it up front as a permanent fault (it will never succeed on retry) rather than
#: hammering the DLQ. ``per_recipient`` jobs carry exactly one recipient, so they are always
#: under the limit.
MAX_RECIPIENTS_PER_MESSAGE = 50

#: SES hard limit: a single message (after MIME encoding) may not exceed 10 MB (design §6.4). A
#: rendered body + attachment larger than this can never be sent, so the worker refuses it as a
#: permanent fault rather than retrying forever into the DLQ. Checked on the assembled payload
#: the sender port reports back (bytes), so it covers both the simple and the attachment path.
MAX_MESSAGE_BYTES = 10 * 1024 * 1024


# ── SES rate-limit / throttle detection (reused from the Flask members_mail pattern) ────

#: The throttling markers that mark an SES error string as a RATE LIMIT / throttle rather than a
#: permanent rejection. Mirrors ``backend/src/routes/members_mail.py`` ``_SES_THROTTLE_MARKERS``
#: / ``_is_ses_rate_limited`` so BOTH planes classify a throttle identically — a throttled send
#: is RETRYABLE (SQS retries, DLQ after N), a permanent rejection is not. SES surfaces these as
#: an error code/message like ``Throttling: Maximum sending rate exceeded`` or
#: ``LimitExceeded`` / a daily-quota rejection.
_SES_THROTTLE_MARKERS = (
    "throttl",  # Throttling / ThrottlingException
    "throughput",
    "maximum sending rate exceeded",
    "max sending rate",
    "rate exceeded",
    "sending rate",
    "limitexceeded",  # LimitExceeded (quota)
    "limit exceeded",
    "daily message quota",
    "quota exceeded",
    "too many requests",
)


def is_ses_rate_limited(error: str | None) -> bool:
    """Does an SES error string indicate a rate limit / throttle / quota (R4, design §6.4)?

    Reuses the Flask ``members_mail._is_ses_rate_limited`` DETECTION pattern so both planes
    agree on what counts as a RETRYABLE throttle (as opposed to a permanent rejection). Matches
    the known throttling / quota markers case-insensitively against the SES error string
    (``"<Code>: <Message>"``). A throttle is retryable — the worker raises
    :class:`MailSendRetryable` so SQS retries and the DLQ catches it after N; a non-matching
    (permanent) error raises :class:`MailSendPermanent`.
    """
    if not error:
        return False
    haystack = error.lower()
    return any(marker in haystack for marker in _SES_THROTTLE_MARKERS)


# ── errors (drive the SQS retry / DLQ semantics) ────────────────────────────────────────


class MailSendRetryable(Exception):
    """A transient failure (SES throttle / quota) — RAISE so SQS retries → DLQ after N.

    The worker does NOT swallow a throttle: it re-raises as this so the Lambda SQS event
    source does not delete the message, it becomes visible again, and SQS retries it; after
    ``maxReceiveCount`` (5, task 4.4) the queue redrives it to the DLQ (design §4.2/§9).
    """


class MailSendPermanent(Exception):
    """A permanent failure (non-retryable rejection / oversize / bad job) — RAISE so it dead-letters.

    A permanent SES rejection (e.g. ``MessageRejected`` for an unverified identity), an oversize
    message, or a malformed job can NEVER succeed on retry. The worker still RAISES (never
    silently drops a send, design §9) so the message rides out its receives and lands in the DLQ
    as an operational signal rather than vanishing.
    """


# ── ports (storage-agnostic seams) ──────────────────────────────────────────────────────


@runtime_checkable
class MailSentMarkerStore(Protocol):
    """The idempotency-marker store PORT — records that a ``job_id`` was already sent (design §4.2).

    :meth:`mark_if_absent` is a CONDITIONAL write: it stores a ``mailsent#<job_id>`` marker only
    if one does not already exist, returning ``True`` when it created the marker (this invocation
    owns the send) and ``False`` when the marker was already present (a redelivery — the worker
    skips the send). This is the at-least-once → exactly-once bridge: SQS may deliver a job more
    than once, but only the first conditional put wins. Keyed by ``tenant_id`` (a marker can only
    ever match within its own tenant — Property 1).
    """

    def mark_if_absent(
        self, tenant_id: str, job_id: str, metadata: Mapping[str, Any]
    ) -> bool:
        """Create the ``mailsent#<job_id>`` marker iff absent; return True iff THIS call created it."""
        ...


@runtime_checkable
class SesSender(Protocol):
    """The SES send PORT — the sole SES touch-point (the service carries no boto3).

    One method sends one rendered message (simple or with an attachment) and returns a
    :class:`SesSendOutcome`. The production implementation (task 4.3 edge wiring) is a thin
    boto3 ``send_email`` / ``send_raw_email`` adapter scoped to the verified sender identity +
    the configuration set; a fake in tests CAPTURES the send and can simulate a throttle /
    permanent error. The port never raises for an SES business error — it reports it on the
    outcome (``ok=False`` + ``error``) so the SERVICE decides retryable-vs-permanent (keeping the
    SES-limit policy in one place).
    """

    def send(
        self,
        *,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        attachments: Sequence[Mapping[str, Any]] | None = None,
    ) -> SesSendOutcome:
        """Send one message; return the outcome (never raises for an SES business error)."""
        ...


class SesSendOutcome:
    """The result of one :meth:`SesSender.send` — success + message id, or an SES error string.

    A plain value object (not a dataclass to keep this module dependency-light). ``ok`` is the
    send result; ``message_id`` is set on success; ``error`` carries the SES ``"<Code>: <Message>"``
    string on failure (the service classifies it via :func:`is_ses_rate_limited`); ``size_bytes``
    is the assembled message size (so the service can enforce the 10 MB SES limit — design §6.4).
    """

    __slots__ = ("error", "message_id", "ok", "size_bytes")

    def __init__(
        self,
        *,
        ok: bool,
        message_id: str | None = None,
        error: str | None = None,
        size_bytes: int = 0,
    ):
        self.ok = ok
        self.message_id = message_id
        self.error = error
        self.size_bytes = size_bytes


# ── the worker's per-job result ─────────────────────────────────────────────────────────


class MailSendResult:
    """The outcome of processing ONE send job — for the handler to report / log (metadata only).

    ``sent`` is True when a message was dispatched; ``deduped`` is True when a redelivery was
    skipped (the marker already existed) — both are "the message may be deleted from the queue"
    outcomes. ``recipient_count`` is the number of addresses the job targeted (metadata only).
    """

    __slots__ = ("deduped", "job_id", "recipient_count", "sent")

    def __init__(
        self, *, job_id: str, sent: bool, deduped: bool, recipient_count: int
    ):
        self.job_id = job_id
        self.sent = sent
        self.deduped = deduped
        self.recipient_count = recipient_count


# ── the service ─────────────────────────────────────────────────────────────────────────


class MailSendWorker:
    """Render + send ONE queued mail job, idempotently, respecting SES limits (R4, task 4.3).

    Storage-agnostic: depends only on the injected ports — an :class:`SesSender`, a
    :class:`MailSentMarkerStore`, a template renderer exposing
    ``render_for_recipient(tenant_id, template_id, lang, merge_values)`` (the
    :class:`~sam.members.domain.template_service.TemplateService` satisfies it), and an audit
    callable with the ``log_analytics_output`` keyword shape. ``tenant_id`` is authoritative on
    every path.

    Args:
        ses: the SES send port (the sole SES touch-point).
        marker_store: the idempotency-marker store (the dedupe bridge).
        template_service: the template renderer (``render_for_recipient``); may be ``None`` for a
            job that carries no template (a plain ``to_fixed`` attachment with no covering body).
        audit: a callable invoked once per SENT job with the metadata-only audit kwargs
            (``actor`` / ``tenant`` / ``output_kind='ses_mail'`` / ``set_key`` / ``record_count``).
            Defaults to the no-op logger sink if omitted.
        default_lang: the language a ``per_recipient`` merge renders when the job names none.
    """

    def __init__(
        self,
        *,
        ses: SesSender,
        marker_store: MailSentMarkerStore,
        template_service: Any = None,
        audit: Callable[..., Any] | None = None,
        default_lang: str = DEFAULT_LANG,
    ):
        self._ses = ses
        self._markers = marker_store
        self._templates = template_service
        self._audit = audit
        self._default_lang = default_lang

    # ── public entry point ──────────────────────────────────────────────────────────────

    def process(self, envelope: Mapping[str, Any]) -> MailSendResult:
        """Process ONE deserialized send-job envelope end to end (dedupe → render → send → audit).

        Returns a :class:`MailSendResult` on success or a deduped redelivery (both mean the SQS
        message may be deleted). Raises :class:`MailSendRetryable` on an SES throttle (SQS retries
        → DLQ after N) or :class:`MailSendPermanent` on a non-retryable fault (surfaces → DLQ);
        never swallows a send failure (design §9).
        """
        job_id = self._require(envelope, "job_id")
        tenant_id = self._require(envelope, "tenant_id")
        mode = str(envelope.get("mode") or "")
        recipients = self._clean_recipients(envelope.get("recipients"))

        # SES recipients-per-message limit (design §6.4) — a permanent fault (never succeeds on
        # retry), refused up front so it does not churn the DLQ.
        if len(recipients) > MAX_RECIPIENTS_PER_MESSAGE:
            raise MailSendPermanent(
                f"job {job_id!r} targets {len(recipients)} recipients "
                f"(SES limit is {MAX_RECIPIENTS_PER_MESSAGE} per message)"
            )
        if not recipients:
            # Nothing to send (a per_recipient job must carry one address; a to_fixed job its
            # fixed list). An empty list is a malformed job — refuse it rather than send nothing.
            raise MailSendPermanent(f"job {job_id!r} carries no recipients")

        # 1. Dedupe — conditional marker put BEFORE sending (idempotency, design §4.2). A
        #    redelivery finds the marker and skips the send (returns deduped).
        created = self._markers.mark_if_absent(
            tenant_id,
            job_id,
            {
                "run_id": envelope.get("run_id"),
                "set_id": envelope.get("set_id"),
                "mode": mode,
                "recipient_count": len(recipients),
            },
        )
        if not created:
            logger.info(
                "mail-send worker: job %s already sent (redelivery) — skipping", job_id
            )
            return MailSendResult(
                job_id=job_id,
                sent=False,
                deduped=True,
                recipient_count=len(recipients),
            )

        # 2. Render per the mode.
        subject, body_html, attachments = self._render(envelope, mode, recipients)

        # 3. Send via SES (respect limits; classify failures retryable-vs-permanent).
        outcome = self._ses.send(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            attachments=attachments,
        )
        self._enforce_outcome(job_id, outcome)

        # 4. Audit metadata-only (ses_mail) — never bodies / member PII (design §8).
        self._emit_audit(envelope, tenant_id, len(recipients))

        logger.info(
            "mail-send worker: job %s sent to %d recipient(s) (message_id=%s)",
            job_id,
            len(recipients),
            outcome.message_id,
        )
        return MailSendResult(
            job_id=job_id, sent=True, deduped=False, recipient_count=len(recipients)
        )

    # ── render ────────────────────────────────────────────────────────────────────────

    def _render(
        self, envelope: Mapping[str, Any], mode: str, recipients: Sequence[str]
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        """Render the subject + body + any attachment for the job's mode.

        - ``per_recipient``: mail-merge the ``template_id`` with the job's ``merge_values`` (one
          recipient). The merge happens on-plane (never an AI prompt) via the template service's
          ``render_for_recipient``.
        - ``to_fixed``: build the attachment (``csv`` / ``pdf_labels``) from the job's ``rows`` +
          an optional covering-template body (merged with no per-recipient values — a static
          covering mail).
        """
        if mode == DELIVERY_MODE_PER_RECIPIENT:
            return self._render_per_recipient(envelope)
        if mode == DELIVERY_MODE_TO_FIXED:
            return self._render_to_fixed(envelope)
        raise MailSendPermanent(
            f"job {envelope.get('job_id')!r} has unknown delivery mode {mode!r}"
        )

    def _render_per_recipient(
        self, envelope: Mapping[str, Any]
    ) -> tuple[str, str, None]:
        template_id = envelope.get("template_id")
        merge_values = envelope.get("merge_values") or {}
        if not isinstance(merge_values, Mapping):
            merge_values = {}
        if not template_id:
            raise MailSendPermanent(
                f"per_recipient job {envelope.get('job_id')!r} carries no template_id"
            )
        if self._templates is None:
            raise MailSendPermanent(
                "per_recipient render requires a template service (none wired)"
            )
        lang = str(envelope.get("lang") or self._default_lang)
        rendered = self._templates.render_for_recipient(
            self._require(envelope, "tenant_id"),
            str(template_id),
            lang,
            dict(merge_values),
        )
        return rendered.subject, rendered.body_html, None

    def _render_to_fixed(
        self, envelope: Mapping[str, Any]
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        rows = envelope.get("rows") or []
        rows = [dict(r) for r in rows if isinstance(r, Mapping)]
        attachment = envelope.get("attachment")
        tenant_id = self._require(envelope, "tenant_id")

        # Optional covering-mail body from the template (no per-recipient merge values — a
        # static covering message to the fixed recipients). Absent template → an empty body.
        subject = "Member set"
        body_html = ""
        template_id = envelope.get("template_id")
        if template_id and self._templates is not None:
            lang = str(envelope.get("lang") or self._default_lang)
            rendered = self._templates.render_for_recipient(
                tenant_id, str(template_id), lang, {}
            )
            subject, body_html = rendered.subject, rendered.body_html

        attachments: list[dict[str, Any]] | None = None
        if isinstance(attachment, Mapping):
            kind = str(attachment.get("kind") or "")
            built = self._build_attachment(kind, rows, attachment.get("label_options"))
            if built is not None:
                attachments = [built]
        return subject, body_html, attachments

    def _build_attachment(
        self,
        kind: str,
        rows: Sequence[Mapping[str, Any]],
        label_options: Any,
    ) -> dict[str, Any] | None:
        """Build the attachment descriptor (``{filename, content, content_type}``) for the SES port.

        ``csv`` → a UTF-8 CSV of the result rows (header = the union of row keys, stable order).
        ``pdf_labels`` → delegated to the shared address-label generator seam when available;
        the worker does not reimplement label layout. An unknown kind is a permanent fault.
        """
        if kind == "csv":
            content = _rows_to_csv_bytes(rows)
            return {
                "filename": "members.csv",
                "content": content,
                "content_type": "text/csv",
            }
        if kind == "pdf_labels":
            content = self._build_pdf_labels(rows, label_options)
            return {
                "filename": "labels.pdf",
                "content": content,
                "content_type": "application/pdf",
            }
        raise MailSendPermanent(f"unknown attachment kind {kind!r}")

    def _build_pdf_labels(
        self, rows: Sequence[Mapping[str, Any]], label_options: Any
    ) -> bytes:
        """Render address-label PDF bytes from the result rows + shared ``label_options``.

        The label-layout generator is not yet on the SAM plane (it runs frontend-side today, R6),
        so a concrete generator is injected via the edge when available. Until it lands the
        worker refuses a ``pdf_labels`` job as a permanent fault rather than sending a corrupt /
        empty PDF — a loud, dead-lettered signal, never a silent bad send.
        """
        raise MailSendPermanent(
            "pdf_labels rendering is not available on the SAM plane yet "
            "(no label generator wired) — see design §6/R6"
        )

    # ── send outcome → retryable / permanent classification ─────────────────────────────

    def _enforce_outcome(self, job_id: str, outcome: SesSendOutcome) -> None:
        """Turn the SES port's outcome into success / retryable / permanent (design §6.4/§9).

        A successful send returns. An oversize message (over the 10 MB SES limit) is permanent.
        A failed send is RETRYABLE when its error matches a throttle/quota marker
        (:func:`is_ses_rate_limited`) — raise :class:`MailSendRetryable` so SQS retries → DLQ —
        otherwise PERMANENT — raise :class:`MailSendPermanent` so it surfaces → DLQ. A send
        failure is NEVER swallowed.
        """
        if outcome.size_bytes and outcome.size_bytes > MAX_MESSAGE_BYTES:
            raise MailSendPermanent(
                f"job {job_id!r} message is {outcome.size_bytes} bytes "
                f"(over the SES {MAX_MESSAGE_BYTES}-byte limit)"
            )
        if outcome.ok:
            return
        if is_ses_rate_limited(outcome.error):
            raise MailSendRetryable(
                f"job {job_id!r} throttled by SES: {outcome.error} (will retry → DLQ after N)"
            )
        raise MailSendPermanent(
            f"job {job_id!r} rejected by SES: {outcome.error} (dead-letters, not retried)"
        )

    # ── audit (metadata only) ───────────────────────────────────────────────────────────

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
        except Exception as exc:  # noqa: BLE001 — audit must never fail an already-sent mail
            logger.warning(
                "mail-send worker: audit emit failed for job %s: %s",
                envelope.get("job_id"),
                exc,
            )

    # ── helpers ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _require(envelope: Mapping[str, Any], key: str) -> str:
        value = envelope.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MailSendPermanent(
                f"send job is missing required field {key!r} (malformed envelope)"
            )
        return value

    @staticmethod
    def _clean_recipients(raw: Any) -> list[str]:
        """Normalize the envelope's recipients to a de-duplicated list of non-blank addresses."""
        if not isinstance(raw, (list, tuple)):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for entry in raw:
            if not isinstance(entry, str):
                continue
            addr = entry.strip()
            key = addr.lower()
            if addr and key not in seen:
                seen.add(key)
                out.append(addr)
        return out


def _rows_to_csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """Serialize result rows to UTF-8 CSV bytes (header = the union of row keys, stable order).

    Pure + storage-agnostic. The header is the first-appearance union of every row's keys so a
    ragged result (rows with differing keys) still produces a well-formed CSV; a missing value is
    an empty cell. An empty result yields a zero-row CSV (just no data lines).
    """
    header: list[str] = []
    for row in rows:
        for key in row:
            if key not in header:
                header.append(str(key))

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({str(k): _csv_cell(v) for k, v in row.items()})
    return buffer.getvalue().encode("utf-8")


def _csv_cell(value: Any) -> Any:
    """Flatten a cell value for CSV — nested mapping/sequence → str, scalars pass through."""
    if isinstance(value, (Mapping, list, tuple)):
        return str(value)
    return value
