"""Shared constants, ports and result types for MailSendWorker (task 7)."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


#: The ``mode`` stamped on a member-application send-run tally (D22/0.4). The two application
#: sends (staff + applicant) are jobs of ONE run; this value discriminates an application run
#: from a pivot/analytics run (``per_recipient`` / ``to_fixed``) in the shared ``mailrun#`` store.
MODE_MEMBER_APPLICATION = "member_application"

#: The ``triggered_by`` recorded on a member-application run (D22). The public intake has NO
#: interactive user (R5/D27) — the run is attributed to the public application form, not a person.
APPLICATION_TRIGGERED_BY = "public_application_intake"

#: The language variant a ``per_recipient`` merge renders when the job names none. ``nl`` is the
#: Members plane's primary language (the app is NL-first); a template without ``nl`` surfaces a
#: clear render error rather than a silent wrong-language send.
DEFAULT_LANG = "nl"

#: The generic fallback export filename used when a job carries no usable tenant/pivot display
#: name (R5 error handling, design §"Error Handling"). An older in-flight job enqueued before the
#: envelope stamped ``tenant_name`` / ``pivot_name`` (task 6.1) has neither — rather than emit an
#: empty or malformed name (``-.csv``) or RAISE over a cosmetic detail, the worker degrades to
#: this safe generic name so a pivot export never regresses to a hard failure. Keeps the naming
#: change backward-compatible with jobs already on the queue at deploy time.
DEFAULT_EXPORT_FILENAME = "export.csv"

#: The generic fallback email subject, paired with :data:`DEFAULT_EXPORT_FILENAME` for the same
#: missing-name case (design §"Error Handling"). Used when neither a usable tenant name nor a
#: pivot name is available to compose the ``{Tenant} - {Pivot}`` subject.
DEFAULT_EXPORT_SUBJECT = "Member set"

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
    :class:`SesSendOutcome`. The verified **From** (``from_address``) and the **Reply-To**
    (``reply_to``) are supplied PER SEND (mail-spec task 1.2): the service resolves the active
    tenant's ``noreply@<tenant-domain>`` From + the triggering user's Reply-To and passes them in
    — there is no global env sender and no substitute-sender fallback (Property 2). The production
    implementation (:class:`~sam.members.repository.mail_send_adapters.SesBotoSender`) is a thin
    boto3 ``send_email`` / ``send_raw_email`` adapter scoped to the configuration set; a fake in
    tests CAPTURES the send and can simulate a throttle / permanent error. The port never raises
    for an SES business error — it reports it on the outcome (``ok=False`` + ``error``) so the
    SERVICE decides retryable-vs-permanent (keeping the SES-limit policy in one place).
    """

    def send(
        self,
        *,
        from_address: str,
        reply_to: str | None = None,
        recipients: Sequence[str],
        subject: str,
        body_html: str,
        attachments: Sequence[Mapping[str, Any]] | None = None,
    ) -> SesSendOutcome:
        """Send one message from ``from_address`` (Reply-To ``reply_to``); return the outcome."""
        ...


@runtime_checkable
class ApplicationRecipientResolver(Protocol):
    """The staff-recipient resolution PORT for application jobs (task 6.1 / seam (d)).

    The member-application STAFF job resolves WHO to notify ENTIRELY SAM-side from the
    governance projection — the all-scope ``Members_CRUD`` set (+ optional scope-matched copy)
    with a ``TenantAdmin`` fallback (D9/D9a), and the mirrored Reply-To set (D8/D24). The
    concrete is :class:`~sam.members.repository.role_recipients_reader.RoleRecipientsReader`
    (whose ``resolve_recipients`` satisfies this Protocol by duck-typing); a test passes a
    static fake. The returned object is a
    :class:`~sam.members.repository.role_recipients_reader.RecipientResolution` — the worker
    reads ``.recipients`` (the TO set) and ``.reply_to`` (the multi-address Reply-To set, R9a)
    off it, never recomputing the Reply-To chain here (it lives in one place, 6.1).
    """

    def resolve_recipients(
        self, tenant_id: str, applicant_scope_value: str | None = None
    ) -> Any:
        """Resolve the staff recipients (+ Reply-To set) for a new application in ``tenant_id``."""
        ...


@runtime_checkable
class ApplicationSenderResolver(Protocol):
    """The From-composition PORT for application jobs (D4 — per-tenant ``noreply@<mail_domain>``).

    Reused verbatim from the members mail flow: the concrete is
    :class:`~sam.members.domain.mail_sender_resolver.MailSenderResolver` (whose ``resolve``
    satisfies this Protocol). It composes ``From = <mail_local_part|noreply>@<mail_domain>``
    from the tenant's projected ``config#mail`` row, gated by ``mail_certified`` — returning a
    :class:`~sam.members.domain.mail_sender_resolver.SenderResolution` carrying EITHER a usable
    From or a typed not-certified reason. The readiness gate (R5.4/R9.4) means a non-ready
    tenant never reaches submit, so a refusal here is an edge case (a sender lapsing between
    precheck and send) the worker treats as best-effort — never a crash.
    """

    def resolve(self, tenant_id: str) -> Any:
        """Resolve the active tenant's usable From, or a typed not-certified reason (D4)."""
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

    def __init__(self, *, job_id: str, sent: bool, deduped: bool, recipient_count: int):
        self.job_id = job_id
        self.sent = sent
        self.deduped = deduped
        self.recipient_count = recipient_count


# ── the service ─────────────────────────────────────────────────────────────────────────
