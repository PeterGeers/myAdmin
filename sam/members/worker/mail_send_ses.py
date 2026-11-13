"""SES send path, throttle classification and outcome enforcement.

Part of MailSendWorker (task 7).
"""

from __future__ import annotations

import logging

from sam.members.domain.mail_feedback_tags import (
    build_feedback_tags as _build_feedback_tags,
)

logger = logging.getLogger(__name__)

from ._mail_send_shared import (
    MAX_MESSAGE_BYTES,
    MailSendPermanent,
    MailSendRetryable,
    SesSendOutcome,
    is_ses_rate_limited,
)


class MailSesMixin:
    """SES send path, throttle classification and outcome enforcement."""

    def _send_via_ses(
        self, envelope, tenant_id, recipients, subject, body_html, attachments
    ):
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
