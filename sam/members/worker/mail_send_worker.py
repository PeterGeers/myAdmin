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

import logging
from collections.abc import Callable, Mapping
from typing import Any

from sam.members.domain.application_notification import (
    JOB_KIND_APPLICANT,
    JOB_KIND_KEY,
    JOB_KIND_STAFF,
    NO_NOTIFY_KEYWORD,
    append_additional_info_keyword,
)
from sam.members.domain.mail_feedback_tags import (
    build_feedback_tags as _build_feedback_tags,
)

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
from ._mail_send_shared import (  # noqa: F401 (surface compat)
    _SES_THROTTLE_MARKERS,
    APPLICATION_TRIGGERED_BY,
    DEFAULT_EXPORT_FILENAME,
    DEFAULT_EXPORT_SUBJECT,
    DEFAULT_LANG,
    MAX_MESSAGE_BYTES,
    MAX_RECIPIENTS_PER_MESSAGE,
    MODE_MEMBER_APPLICATION,
    ApplicationRecipientResolver,
    ApplicationSenderResolver,
    MailSendPermanent,
    MailSendResult,
    MailSendRetryable,
    MailSentMarkerStore,
    SesSender,
    SesSendOutcome,
    is_ses_rate_limited,
)
from .mail_send_audit import MailAuditMixin
from .mail_send_render import (  # noqa: F401 (surface compat)
    _EXPORT_SANITIZE_STRIP,
    _EXPORT_WHITESPACE_RUN,
    MailRenderMixin,
    _csv_cell,
    _dedupe_addresses,
    _export_file_name,
    _export_subject,
    _join_reply_to,
    _rows_to_csv_bytes,
    _sanitize_export_part,
)
from .mail_send_ses import MailSesMixin


class MailSendWorker(
    MailRenderMixin,
    MailSesMixin,
    MailAuditMixin,
):
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
                tenant_id,
                str(envelope.get("run_id") or ""),
                recipients,
                reason=str(exc),
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
        self._advance_run(
            tenant_id, str(envelope.get("run_id") or ""), sent=len(recipients)
        )
        return MailSendResult(
            job_id=job_id, sent=True, deduped=False, recipient_count=len(recipients)
        )

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
            recipients, reply_to = self._resolve_application_staff_recipients(
                envelope, tenant_id
            )
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
                job_id=job_id,
                sent=False,
                deduped=False,
                recipient_count=len(recipients),
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
        applicant_scope_value = (
            self._clean_single(envelope.get("applicant_scope_value")) or None
        )
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
                "mail-send worker: application run create failed for run %s (non-fatal)",
                run_id,
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
