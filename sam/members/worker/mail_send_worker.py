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
3. **Sends via SES** from the per-send resolved tenant From (``noreply@<tenant-domain>``) with the
   triggering user's Reply-To (both ride on the envelope — mail-spec task 1.2/1.3; no global env
   sender), attaching ``SES_CONFIGURATION_SET`` when set, respecting ALL SES limits (recipients-
   per-message, message size — design §6.4). The actual SES call is an injected PORT
   (:class:`SesSender`) so the service carries no boto3.
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
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.mail_feedback_tags import build_feedback_tags as _build_feedback_tags
from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
)
from sam.members.domain.application_notification import (
    JOB_KIND_APPLICANT,
    JOB_KIND_KEY,
    JOB_KIND_STAFF,
    NO_NOTIFY_KEYWORD,
    append_additional_info_keyword,
)
from sam.members.domain.applicant_locale import DEFAULT_LOCALE, normalize_locale
from sam.members.domain.application_messages import render_application_message

logger = logging.getLogger(__name__)

__all__ = [
    "APPLICATION_TRIGGERED_BY",
    "DEFAULT_LANG",
    "MAX_MESSAGE_BYTES",
    "MAX_RECIPIENTS_PER_MESSAGE",
    "MODE_MEMBER_APPLICATION",
    "ApplicationRecipientResolver",
    "ApplicationSenderResolver",
    "MailSendPermanent",
    "MailSendResult",
    "MailSendRetryable",
    "MailSendWorker",
    "MailSentMarkerStore",
    "SesSendOutcome",
    "SesSender",
    "is_ses_rate_limited",
]

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
        run_store: Any = None,
        recipient_resolver: ApplicationRecipientResolver | None = None,
        sender_resolver: ApplicationSenderResolver | None = None,
        members_store: Any = None,
    ):
        self._ses = ses
        self._markers = marker_store
        self._templates = template_service
        self._audit = audit
        self._default_lang = default_lang
        # Member-application ports (task 6.3). Optional so the pivot/analytics send path (which
        # never carries an application job) wires neither; an application job that arrives with
        # no resolver wired is a deploy fault the branch refuses loudly (permanent → DLQ).
        #   * recipient_resolver — the staff-recipient + Reply-To resolution (task 6.1, D9/D9a).
        #   * sender_resolver     — the From composition (MailSenderResolver, D4).
        self._recipient_resolver = recipient_resolver
        self._sender_resolver = sender_resolver
        # Optional send-run status store (R9.1): the worker ADVANCES the `mailrun#<run_id>` tally
        # the enqueue side created — status queued→sending→(implicitly completed via counts), and
        # the per-job sent/failed counts. Tenant-pinned `increment_mail_run_counts` /
        # `update_mail_run_status` / `record_mail_failure` (the DynamoDbMembersRepository satisfies
        # it). Optional + guarded so tests/local that do not wire it still send; a None store means
        # "do not track" (the send itself never depends on the tally).
        self._run_store = run_store
        # Optional members store (application-app task 6.4): used ONLY by the staff NO_NOTIFY seam
        # to UPDATE the already-committed application record's `overlay.additional_info` with the
        # stable NO_NOTIFY keyword when there are no recipients (R8.5). Needs `get_member` +
        # `save_member` (the DynamoDbMembersRepository satisfies it — it is the SAME repo wired as
        # the run_store). Optional + guarded: a None store (or a lookup/save error) only means the
        # note is not written — it NEVER fails the worker (the application is already in the inbox).
        self._members_store = members_store

    def _advance_run(self, tenant_id: str, run_id: str, *, sent: int = 0, failed: int = 0) -> None:
        """Advance the run tally (best-effort): mark sending + add sent/failed counts. Never let a
        status-tracking error fail the actual send/delete (the mail already went or will retry)."""
        if self._run_store is None or not run_id:
            return
        try:
            self._run_store.update_mail_run_status(tenant_id, run_id, "sending")
            if sent or failed:
                self._run_store.increment_mail_run_counts(
                    tenant_id, run_id, sent=sent, failed=failed
                )
        except Exception:  # noqa: BLE001 — status tracking must never break the send path
            logger.warning(
                "mail-send worker: run-status update failed for run %s (non-fatal)", run_id
            )

    # ── public entry point ──────────────────────────────────────────────────────────────

    def process(self, envelope: Mapping[str, Any]) -> MailSendResult:
        """Process ONE deserialized send-job envelope end to end (dedupe → render → send → audit).

        Returns a :class:`MailSendResult` on success or a deduped redelivery (both mean the SQS
        message may be deleted). Raises :class:`MailSendRetryable` on an SES throttle (SQS retries
        → DLQ after N) or :class:`MailSendPermanent` on a non-retryable fault (surfaces → DLQ);
        never swallows a send failure (design §9).
        """
        # Member-application branch (application-app task 6.3): the two public-intake jobs are
        # discriminated by `kind` (member_application_staff / member_application_ack), NOT the
        # pivot path's `mode`. They resolve their own recipients (6.1), compose From via the
        # sender resolver (D4), set a multi-address Reply-To (D8/D24), and render a bilingual
        # feature template — so they take a dedicated path rather than the mode-based one below.
        kind = str(envelope.get(JOB_KIND_KEY) or "")
        if kind in (JOB_KIND_STAFF, JOB_KIND_APPLICANT):
            return self._process_application(envelope, kind)

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

        # 2+3. Render + send. A PERMANENT failure (bad job / SES rejection / oversize) means
        #     this job's recipients will NEVER be sent — record it against the run tally (R9.5:
        #     a FAILURE-only `mailrecipient#` sub-record + failed count) BEFORE re-raising so the
        #     message dead-letters. A RETRYABLE failure (SES throttle) is NOT recorded — the job
        #     will be retried, so counting it failed now would be wrong.
        try:
            subject, body_html, attachments = self._render(envelope, mode, recipients)
            outcome = self._send_via_ses(
                envelope, tenant_id, recipients, subject, body_html, attachments
            )
            self._enforce_outcome(job_id, outcome)
        except MailSendPermanent as exc:
            self._record_run_failure(
                tenant_id, str(envelope.get("run_id") or ""), recipients, reason=str(exc)
            )
            raise

        # 4. Audit metadata-only (ses_mail) — never bodies / member PII (design §8).
        self._emit_audit(envelope, tenant_id, len(recipients))

        logger.info(
            "mail-send worker: job %s sent to %d recipient(s) (message_id=%s)",
            job_id,
            len(recipients),
            outcome.message_id,
        )
        # Advance the run tally: this job's recipients are now SENT (R9.1). Guarded by the dedupe
        # marker above (we only reach here when the marker was freshly created), so an at-least-
        # once redelivery of the same job returns deduped earlier and never double-counts.
        self._advance_run(tenant_id, str(envelope.get("run_id") or ""), sent=len(recipients))
        return MailSendResult(
            job_id=job_id, sent=True, deduped=False, recipient_count=len(recipients)
        )

    # ── member-application branch (task 6.3) ──────────────────────────────────────────

    def _process_application(
        self, envelope: Mapping[str, Any], kind: str
    ) -> MailSendResult:
        """Process ONE member-application notification job (staff OR applicant), task 6.3.

        The public-intake notification (design §6 / seam e). Shared spine with the pivot path —
        authoritative ``tenant_id``, a conditional dedupe marker, the From resolved per send, the
        best-effort / DLQ outcome classification — but the recipients, Reply-To, and body are
        composed HERE rather than riding the envelope:

        - **From (D4):** :class:`ApplicationSenderResolver` composes
          ``<mail_local_part|noreply>@<mail_domain>`` from the tenant's ``config#mail``. The
          readiness gate (R5.4/R9.4) means a send-ready tenant is the norm; a refusal (a sender
          lapsing between precheck and send) is best-effort — the record is already committed, so
          the branch skips the send rather than crashing (R8.8).
        - **STAFF job:** resolve recipients + the multi-address Reply-To via
          :class:`ApplicationRecipientResolver` (task 6.1, D9/D9a/R9a). Render the staff body —
          a deep-link to ``/members/{member_id}`` + a neutral ``DUP`` marker when flagged, NO
          applicant PII (R8.6/R8.6a) — in the recipient/tenant locale (R6b.5, default ``nl``).
          WHEN there are no recipients this is the R8.5 ``NO_NOTIFY`` seam (task 6.4): the branch
          appends the ``NO_NOTIFY`` keyword to the committed record's ``overlay.additional_info``
          + raises a platform-operator alert, then returns a not-sent result rather than
          dead-lettering (the application is already in the ``status=application`` inbox, R8b.4).
        - **APPLICANT job:** send to the applicant's OWN server-validated address (R8a.4) with a
          body that embeds their own submitted data (their own data is not a leak), rendered in
          the APPLICANT's chosen locale (R6b/R8a). No Reply-To chain — the confirmation is one-way.

        Best-effort + DLQ (R8.8): a transient SES throttle raises :class:`MailSendRetryable`
        (SQS retries → DLQ after N); a permanent SES rejection raises :class:`MailSendPermanent`
        (dead-letters) — neither rolls back the already-committed application record. Idempotent
        on the stable ``run_id``+``kind`` marker so an at-least-once redelivery sends once.
        """
        tenant_id = self._require(envelope, "tenant_id")
        run_id = self._require(envelope, "run_id")
        # The application envelopes carry no `job_id` (they discriminate on `kind`); derive a
        # STABLE idempotency key from the run + kind so an at-least-once redelivery of the SAME
        # logical job dedupes to one send (the two jobs of one run differ by kind, so they do
        # not collide).
        job_id = f"{run_id}#{kind}"

        # Send-log (D22/0.4): the two application sends (staff + applicant) are jobs of ONE run.
        # Reuse the SAME `mailrun#<run_id>` tally the pivot path uses — created idempotently here
        # (the enqueue side mints no run; the first of the two jobs to arrive creates it, the
        # second is a no-op) with the application mode + public-intake `triggered_by` (no
        # interactive user). Best-effort: a tally error never fails the actual send (R9.1).
        self._ensure_application_run(tenant_id, run_id)

        if kind == JOB_KIND_STAFF:
            recipients, reply_to = self._resolve_application_staff_recipients(envelope, tenant_id)
            if not recipients:
                # R8.5 NO_NOTIFY seam (task 6.4): no all-scope `Members_CRUD` AND no `TenantAdmin`.
                # This is NOT a failure — the application is already in the status=application
                # inbox (R8b.4). We (1) append the stable NO_NOTIFY keyword to the committed
                # record's overlay.additional_info so staff see "landed but not auto-notified"
                # (keyword-filterable, R8b.5), and (2) raise a platform-operator alert so the
                # operator knows a tenant has no notifiable staff. Do NOT send, do NOT dead-letter,
                # do NOT mark the run failed.
                member_id = self._clean_single(envelope.get("member_id"))
                self._mark_no_notify(tenant_id, member_id)
                self._operator_alert_no_recipients(tenant_id, run_id, member_id)
                return MailSendResult(
                    job_id=job_id, sent=False, deduped=False, recipient_count=0
                )
        else:  # JOB_KIND_APPLICANT
            recipient = self._clean_single(envelope.get("recipient"))
            if not recipient:
                # No applicant address → nothing to confirm. Best-effort: the record stands.
                logger.info(
                    "mail-send worker: application ack job for tenant %r (run=%s) has no "
                    "applicant address — skipping",
                    tenant_id,
                    run_id,
                )
                return MailSendResult(
                    job_id=job_id, sent=False, deduped=False, recipient_count=0
                )
            recipients, reply_to = [recipient], ()

        # From (D4) — resolved per send from config#mail. A refusal is best-effort (R8.8): the
        # readiness gate should have caught it, but a late lapse never crashes the worker.
        from_address = self._resolve_application_from(tenant_id)
        if not from_address:
            logger.warning(
                "mail-send worker: application %s job for tenant %r (run=%s) has no usable "
                "sender (config#mail not certified) — skipping send (best-effort, R8.8)",
                kind,
                tenant_id,
                run_id,
            )
            return MailSendResult(
                job_id=job_id, sent=False, deduped=False, recipient_count=len(recipients)
            )

        # Dedupe BEFORE sending (idempotency, mirrors the pivot path). A redelivery skips.
        created = self._markers.mark_if_absent(
            tenant_id,
            job_id,
            {"run_id": run_id, "kind": kind, "recipient_count": len(recipients)},
        )
        if not created:
            logger.info(
                "mail-send worker: application %s job %s already sent (redelivery) — skipping",
                kind,
                job_id,
            )
            return MailSendResult(
                job_id=job_id, sent=False, deduped=True, recipient_count=len(recipients)
            )

        subject, body_html = self._render_application(envelope, kind)
        # Send + classify (mirrors the pivot path, design §9): a PERMANENT failure means this
        # job's recipients will NEVER be sent — record it against the run (R9.5: a FAILURE-only
        # `mailrecipient#` sub-record + failed count) BEFORE re-raising so the message dead-letters.
        # A RETRYABLE throttle is NOT recorded (the job retries). The marker above is already set,
        # so a retry dedupes to a no-op; the run-failure record is still correct on the first fault.
        try:
            outcome = self._ses.send(
                from_address=from_address,
                reply_to=_join_reply_to(reply_to),
                recipients=recipients,
                subject=subject,
                body_html=body_html,
                attachments=None,
                tags=_build_feedback_tags(tenant_id, run_id),
            )
            self._enforce_outcome(job_id, outcome)
        except MailSendPermanent as exc:
            self._record_run_failure(tenant_id, run_id, recipients, reason=str(exc))
            raise

        # Advance the run tally: this job's recipients are now SENT (R9.1/D22). Guarded by the
        # dedupe marker above (reached only on a freshly created marker), so an at-least-once
        # redelivery returns deduped earlier and never double-counts.
        self._advance_run(tenant_id, run_id, sent=len(recipients))

        logger.info(
            "mail-send worker: application %s job %s sent to %d recipient(s) (message_id=%s)",
            kind,
            job_id,
            len(recipients),
            outcome.message_id,
        )
        return MailSendResult(
            job_id=job_id, sent=True, deduped=False, recipient_count=len(recipients)
        )

    def _resolve_application_staff_recipients(
        self, envelope: Mapping[str, Any], tenant_id: str
    ) -> tuple[list[str], tuple[str, ...]]:
        """Resolve the staff TO set + the multi-address Reply-To set via task 6.1 (D9/D9a/R9a).

        Delegates WHOLLY to the injected :class:`ApplicationRecipientResolver` — the all-scope
        ``Members_CRUD`` set (+ optional scope-matched copy when the envelope carries the
        applicant's scope value, gated upstream by task 8.2's toggle) with a ``TenantAdmin``
        fallback, and the mirrored ``RecipientResolution.reply_to`` (R9a.2/R9a.3). The Reply-To
        chain ORDER is resolved in 6.1 (0.6/D24) — the worker never recomputes it. An unwired
        resolver on an application job is a deploy fault → permanent (dead-letters).
        """
        if self._recipient_resolver is None:
            raise MailSendPermanent(
                "application staff job requires a recipient resolver (none wired)"
            )
        applicant_scope_value = self._clean_single(envelope.get("applicant_scope_value")) or None
        resolution = self._recipient_resolver.resolve_recipients(
            tenant_id, applicant_scope_value
        )
        recipients = self._clean_recipients(getattr(resolution, "recipients", ()))
        reply_to = _dedupe_addresses(getattr(resolution, "reply_to", ()))
        return recipients, reply_to

    def _resolve_application_from(self, tenant_id: str) -> str | None:
        """Compose the per-tenant From via the sender resolver (D4); ``None`` when not usable.

        Returns the composed ``<mail_local_part|noreply>@<mail_domain>`` on a usable resolution,
        else ``None`` (the caller skips the send best-effort, R8.8). An unwired resolver on an
        application job is a deploy fault → permanent.
        """
        if self._sender_resolver is None:
            raise MailSendPermanent(
                "application job requires a sender resolver (none wired)"
            )
        resolution = self._sender_resolver.resolve(tenant_id)
        from_address = getattr(resolution, "from_address", None)
        return from_address if isinstance(from_address, str) and from_address else None

    def _render_application(
        self, envelope: Mapping[str, Any], kind: str
    ) -> tuple[str, str]:
        """Render the bilingual application body for the job's kind (R8.6/R8.6a/R8a).

        The two feature templates are rendered by the pure, on-plane
        :func:`~sam.members.domain.application_messages.render_application_message`:

        - STAFF (``member_application_staff``): a deep-link to ``/members/{member_id}`` + a
          neutral one-line ``DUP`` triage marker when ``duplicate_suspected`` is set, and NO
          applicant PII beyond the display name (R8.6/R8.6a). Rendered in the recipient/tenant
          locale — the STAFF locale is NOT the applicant's choice (R6b.5), defaulting to ``nl``.
        - APPLICANT (``member_application_ack``): a confirmation embedding the applicant's OWN
          submitted data (their own data is not a leak, R8a.4), rendered in the APPLICANT's
          chosen locale (R6b/R8a.2).
        """
        if kind == JOB_KIND_STAFF:
            # Staff locale = recipient/tenant locale (R6b.5), not the applicant's — default nl.
            lang = DEFAULT_LOCALE
        else:
            lang = normalize_locale(envelope.get("locale"))
        return render_application_message(kind, lang, envelope)

    @staticmethod
    def _clean_single(raw: Any) -> str:
        """Normalize a single optional address/value to a trimmed string (``""`` when absent)."""
        return raw.strip() if isinstance(raw, str) and raw.strip() else ""

    def _send_via_ses(self, envelope, tenant_id, recipients, subject, body_html, attachments):
        """The raw SES send call (extracted so process() can wrap render+send in one try)."""
        return self._ses.send(
            from_address=str(envelope.get("from_address") or ""),
            reply_to=(str(envelope["reply_to"]) if envelope.get("reply_to") else None),
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            attachments=attachments,
            # SES MESSAGE TAGS = the feedback ROUTING key (mail-spec task 5.2, R9.5): the config
            # set echoes these back as `mail.tags` on every bounce/complaint/delivery event, so
            # the ingestion handler can route the outcome to the originating run. tenant_id is the
            # AUTHORITATIVE routing key (never guessed downstream) + run_id locates the run so a
            # LATE bounce can create a failure sub-record + adjust the tally. Encoded into the
            # SES-allowed tag charset at the sole seam that knows SES (the sender encodes).
            tags=_build_feedback_tags(tenant_id, str(envelope.get("run_id") or "")),
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
        except Exception:  # noqa: BLE001 — status tracking must never mask the send failure
            logger.warning(
                "mail-send worker: run-failure recording failed for run %s (non-fatal)", run_id
            )

    # ── member-application send-log + NO_NOTIFY seam (task 6.4, D22/R8.5) ──────────────

    def _ensure_application_run(self, tenant_id: str, run_id: str) -> None:
        """Create the application send-run tally idempotently (D22/0.4), best-effort.

        The two application jobs (staff + applicant) are jobs of ONE run that the enqueue side
        does NOT create — so the FIRST of the two to reach the worker creates the shared
        ``mailrun#<run_id>`` tally (``status=queued``, application mode, public-intake
        ``triggered_by``), and the second is an idempotent no-op (``create_mail_run`` returns the
        existing run without resetting counts the first may already have advanced). Guarded +
        swallowed: a tally error never fails the actual send (R9.1 — the tally is additive)."""
        if self._run_store is None or not run_id:
            return
        try:
            self._run_store.create_mail_run(
                tenant_id,
                run_id,
                mode=MODE_MEMBER_APPLICATION,
                triggered_by=APPLICATION_TRIGGERED_BY,
                recipient_count=0,
            )
        except Exception:  # noqa: BLE001 — status tracking must never break the send path
            logger.warning(
                "mail-send worker: application run create failed for run %s (non-fatal)", run_id
            )

    def _mark_no_notify(self, tenant_id: str, member_id: str) -> None:
        """Append the stable ``NO_NOTIFY`` keyword to the committed record's overlay (R8.5).

        The staff notification had NO recipients (no all-scope ``Members_CRUD``, no
        ``TenantAdmin``). The application record is already committed and in the
        ``status=application`` inbox (R8b.4); this UPDATE annotates it so a reviewer sees it
        "landed but could not be auto-notified" and can keyword-filter it (R8b.5). Idempotent
        (``append_additional_info_keyword`` no-ops if already present, so an at-least-once
        redelivery of the staff job never double-appends) and fully best-effort: a missing store,
        a record that vanished, or a save error only means the note is not written — it NEVER
        fails the worker (the application is not lost; it is in the inbox either way, R8.7)."""
        if self._members_store is None or not member_id:
            logger.warning(
                "mail-send worker: NO_NOTIFY note not written for tenant %r member %r "
                "(no members store wired or no member_id) — the application is still in the "
                "status=application inbox",
                tenant_id,
                member_id,
            )
            return
        try:
            record = self._members_store.get_member(tenant_id, member_id)
            if record is None:
                logger.warning(
                    "mail-send worker: NO_NOTIFY note skipped — member %r not found for tenant %r",
                    member_id,
                    tenant_id,
                )
                return
            record = dict(record)
            if append_additional_info_keyword(record, NO_NOTIFY_KEYWORD):
                self._members_store.save_member(tenant_id, record)
        except Exception:  # noqa: BLE001 — annotating the inbox must never fail the worker
            logger.warning(
                "mail-send worker: NO_NOTIFY note write failed for tenant %r member %r "
                "(non-fatal) — the application is still in the status=application inbox",
                tenant_id,
                member_id,
            )

    @staticmethod
    def _operator_alert_no_recipients(
        tenant_id: str, run_id: str, member_id: str
    ) -> None:
        """Raise a PLATFORM-OPERATOR alert that a tenant has no notifiable staff (R8.5).

        A tenant with an application-ready sender but NO all-scope ``Members_CRUD`` and no
        ``TenantAdmin`` is a config gap only the platform operator can fix — so it is surfaced
        as an ``ERROR`` with a stable, greppable marker (``OPERATOR_ALERT NO_RECIPIENTS``) rather
        than an ``INFO`` line lost in the stream. Metadata only (tenant / run / member id) — never
        applicant PII. Logging is the SAM plane's operator-alert channel (a metric filter /
        alarm subscribes to this marker; no SNS client is wired on this unauthenticated plane)."""
        logger.error(
            "OPERATOR_ALERT NO_RECIPIENTS: tenant %r has no notifiable staff for a new "
            "application (no all-scope Members_CRUD, no TenantAdmin) — run=%s member=%s. The "
            "application landed (status=application) but could not be auto-notified (R8.5).",
            tenant_id,
            run_id,
            member_id,
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

        # Export naming (R5.2/5.3/5.5, task 6.3). The tenant + pivot DISPLAY names ride the
        # envelope (task 6.1 stamped them from the verified context) — opaque `tenant_id` /
        # `set_id` are not human-readable. Compose the attachment filename and the default
        # pivot-export subject from them via the shared PURE helpers (task 6.2), which encode the
        # `{Tenant}-{Pivot}.csv` / `{Tenant} - {Pivot}` rule and already handle the backward-compat
        # fallback (blank/absent names → export.csv / generic subject) for older in-flight jobs.
        tenant_name = envelope.get("tenant_name")
        pivot_name = envelope.get("pivot_name")
        export_name = _export_file_name(tenant_name, pivot_name)

        # Default pivot-export subject = tenant prefix + pivot name. A covering TEMPLATE subject
        # (when a `template_id` is supplied) still takes precedence for the body below — the
        # composed name is only the default when no covering template overrides it.
        subject = _export_subject(tenant_name, pivot_name)
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
            built = self._build_attachment(
                kind, rows, attachment.get("label_options"), export_name=export_name
            )
            if built is not None:
                attachments = [built]
        return subject, body_html, attachments

    def _build_attachment(
        self,
        kind: str,
        rows: Sequence[Mapping[str, Any]],
        label_options: Any,
        *,
        export_name: str = DEFAULT_EXPORT_FILENAME,
    ) -> dict[str, Any] | None:
        """Build the attachment descriptor (``{filename, content, content_type}``) for the SES port.

        ``csv`` → a UTF-8 CSV of the result rows (header = the union of row keys, stable order),
        named ``export_name`` — the ``{Tenant_Name}-{Pivot_Name}.csv`` name the caller composed
        off the envelope (R5.2/5.5), replacing the old hard-coded ``members.csv``. ``export_name``
        is keyword-only and defaults to the safe generic :data:`DEFAULT_EXPORT_FILENAME` so a
        caller that supplies no name (or an older in-flight job) never emits a malformed filename.
        ``pdf_labels`` → delegated to the shared address-label generator seam when available;
        the worker does not reimplement label layout. An unknown kind is a permanent fault.
        """
        if kind == "csv":
            content = _rows_to_csv_bytes(rows)
            return {
                "filename": export_name,
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


# ── tenant-prefixed export naming (R5.2/5.3/5.5) ──────────────────────────────────────────
#
# The Python copy of the shared ``{Tenant_Name}-{Pivot_Name}.csv`` export-naming rule — the
# MIRROR of the frontend TypeScript rule in ``frontend/src/utils/csvExport.ts`` (``sanitize`` +
# ``exportFileName``). The two planes do NOT share code, so each owns its copy; both encode the
# SAME rule and are pinned by filename properties (P3 frontend, P4 worker) so they cannot drift.
# A downloaded CSV and an emailed attachment for the same tenant+pivot therefore carry the
# identical name. These helpers are PURE + storage-agnostic; task 6.3 threads them into
# ``_build_attachment`` / ``_render_to_fixed`` (this task adds the rule only).

#: Matches the characters :func:`_sanitize_export_part` strips before the whitespace-collapse:
#: path separators (``/`` ``\``) and ASCII control chars, EXCEPT tab/newline/CR which are left in
#: so the ``\s+`` collapse turns them into a single space rather than deleting them outright.
#: Mirrors the frontend ``sanitize`` character class.
_EXPORT_SANITIZE_STRIP = re.compile(
    "[/\\\\\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]"
)
_EXPORT_WHITESPACE_RUN = re.compile(r"\s+")


def _sanitize_export_part(part: Any) -> str:
    """Sanitize one export-name part (a tenant or pivot display name) for a filename/subject.

    The Python mirror of the frontend ``sanitize`` (``csvExport.ts``): strips filesystem-hostile
    characters — path separators and ASCII control chars — and collapses any whitespace run to a
    single space, trimming the edges. The result never contains a path separator, a control char,
    or leading/trailing whitespace, so it can neither escape a directory nor inject a mail header.
    A ``None`` / non-string input sanitizes to an empty string (the caller's fallback then kicks
    in).
    """
    text = part if isinstance(part, str) else ("" if part is None else str(part))
    text = _EXPORT_SANITIZE_STRIP.sub("", text)
    text = _EXPORT_WHITESPACE_RUN.sub(" ", text)
    return text.strip()


def _export_file_name(tenant_name: Any, pivot_name: Any) -> str:
    """Build the pivot-export attachment filename from the tenant + pivot display names (R5.2/5.5).

    Encodes the shared rule ``sanitize(tenant) + "-" + sanitize(pivot) + ".csv"`` — identical to
    the frontend ``exportFileName`` so a downloaded file and an emailed attachment match. Both
    parts are run through :func:`_sanitize_export_part` so the result carries no path separators
    or control characters.

    **Backward-compat fallback (design §"Error Handling").** When EITHER sanitized part is blank
    — an older in-flight job that predates the ``tenant_name`` / ``pivot_name`` envelope stamp
    (task 6.1), or a name that sanitizes to nothing — the helper does NOT raise and does NOT emit
    a malformed ``-.csv``; it degrades to the safe generic :data:`DEFAULT_EXPORT_FILENAME`
    (``export.csv``). A pivot export never regresses to a hard failure over a cosmetic name.
    """
    tenant = _sanitize_export_part(tenant_name)
    pivot = _sanitize_export_part(pivot_name)
    if not tenant or not pivot:
        return DEFAULT_EXPORT_FILENAME
    return f"{tenant}-{pivot}.csv"


def _export_subject(tenant_name: Any, pivot_name: Any) -> str:
    """Compose the pivot-export email subject: the tenant name as a leading prefix + the pivot (R5.3).

    Combines the sanitized tenant name as a LEADING PREFIX with the pivot name as
    ``"{Tenant} - {Pivot}"``, so the subject identifies which tenant and which pivot the emailed
    export belongs to. Parts are sanitized with :func:`_sanitize_export_part` (no control chars,
    so no header injection).

    **Backward-compat fallback (design §"Error Handling").** When EITHER sanitized part is blank
    (an older in-flight job with no stamped names), the helper falls back to the generic
    :data:`DEFAULT_EXPORT_SUBJECT` rather than composing a lopsided ``"Tenant - "`` /
    ``" - Pivot"`` subject or raising — matching the filename fallback so the two degrade
    together.
    """
    tenant = _sanitize_export_part(tenant_name)
    pivot = _sanitize_export_part(pivot_name)
    if not tenant or not pivot:
        return DEFAULT_EXPORT_SUBJECT
    return f"{tenant} - {pivot}"


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


def _dedupe_addresses(raw: Any) -> tuple[str, ...]:
    """De-duplicate an address sequence (case-insensitive key), preserving first-seen order.

    Used for the application Reply-To set (R9a) — the all-scope ``Members_CRUD`` / ``TenantAdmin``
    addresses the 6.1 resolver returns. A non-sequence / empty input yields ``()``.
    """
    if not isinstance(raw, (list, tuple)):
        return ()
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
    return tuple(out)


def _join_reply_to(addresses: Sequence[str]) -> str | None:
    """Join a multi-address Reply-To SET into the single ``reply_to`` the SES port takes (R9a.2).

    The application Reply-To is the all-scope ``Members_CRUD`` recipient SET (D8/D24), so it can be
    more than one address — but the :class:`SesSender` port carries a single ``reply_to`` string.
    SES ``ReplyToAddresses`` is an address LIST, so a comma-separated address list in that one field
    is split back into the multiple header addresses by the adapter (``SesBotoSender`` splits on
    commas). An empty set → ``None`` (no Reply-To header set, R9a.4).
    """
    cleaned = [a for a in (addresses or ()) if a]
    if not cleaned:
        return None
    return ", ".join(cleaned)
