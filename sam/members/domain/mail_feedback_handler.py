"""
Members mail — the SES FEEDBACK INGESTION service (mail-spec task 5.2; R8.4/R9.5; design
"(Layered) SES feedback ingestion").

The storage-agnostic SERVICE behind the task-5.2 ingestion Lambda. SES publishes
bounce/complaint/delivery events to ONE account-level SNS sink per configuration set (it has no
module/tenant/run concept — R9.5); this service takes ONE already-deserialized SES notification
and ROUTES it back to the Members store by the custom message tags the send-path stamped
(:mod:`sam.members.domain.mail_feedback_tags`), recording a FAILURE against the originating run.

What it does per event
----------------------
1. Parse the SES notification: ``eventType`` (bounce/complaint/delivery), the ``mail.tags`` the
   config set echoes back (the ROUTING key — the authoritative ``tenant_id`` + the ``run_id``),
   ``mail.messageId``, and the failed recipient address(es) + reason from the event body
   (``bounce.bouncedRecipients`` / ``complaint.complainedRecipients``).
2. For a FAILURE (bounce / complaint): call
   :meth:`record_mail_failure(..., adjust_run_tally=True)` on the injected repository for EACH
   failed recipient — a LATE async failure for a previously-"sent" recipient CREATES the
   failure sub-record (there was none) AND moves that run's tally sent→failed (R8.4).
3. A DELIVERY event is INFORMATIONAL — the core status model is sent/failed and the view must not
   claim per-recipient "delivered" from SES acceptance (R9.4). So delivery is a NO-OP (debug log);
   the layer records only the true per-recipient FAILURES the core view cannot know.

Tenancy + no silent drop (R9.5 / Property 3 / Property 6)
---------------------------------------------------------
``tenant_id`` is taken ONLY from the stamped tag — AUTHORITATIVE, never guessed from the address
or the SES source domain (fail-closed). An event that cannot be routed (missing/corrupt tag, no
run_id, no failed recipient) is LOGGED + REPORTED on the result (``unroutable``), never silently
dropped — the entry-point decides whether that is retryable. The repository pins every write to
the tag's ``tenant_id``, so even a mis-stamped event cannot cross tenants.

Pure / injectable (steering 35)
-------------------------------
Depends only on the injected :class:`MailFailureStore` seam (the SAM-plane concrete is
:class:`~sam.members.repository.members_repository.DynamoDbMembersRepository`, satisfied by
duck-typing its ``record_mail_failure``). Names no boto3 / no DynamoDB. A unit test drives it with
an in-memory fake repo and synthetic SES events, no AWS.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.mail_feedback_tags import (
    SES_TAG_RUN_ID,
    SES_TAG_TENANT_ID,
    decode_ses_tag_value,
)
from sam.members.repository.members_repository import (
    MAIL_RECIPIENT_STATUS_BOUNCED,
    MAIL_RECIPIENT_STATUS_COMPLAINT,
)

logger = logging.getLogger(__name__)

__all__ = [
    "EVENT_TYPE_BOUNCE",
    "EVENT_TYPE_COMPLAINT",
    "EVENT_TYPE_DELIVERY",
    "FeedbackResult",
    "MailFailureStore",
    "MailFeedbackService",
]

#: The three SES event types the config-set event destination publishes (task 5.1). Bounce +
#: complaint are FAILURES recorded against the run; delivery is informational (no-op). Matched
#: case-insensitively (SES uses ``Bounce``/``Complaint``/``Delivery`` for the ``eventType`` /
#: legacy ``notificationType`` field).
EVENT_TYPE_BOUNCE = "bounce"
EVENT_TYPE_COMPLAINT = "complaint"
EVENT_TYPE_DELIVERY = "delivery"


@runtime_checkable
class MailFailureStore(Protocol):
    """The minimal, tenant-pinned write seam this service needs (design C "MembersRepository").

    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` satisfies it by
    duck-typing its task-3.1 ``record_mail_failure``. Keyed by ``tenant_id`` so the service cannot
    reach another tenant's data even by mistake (Property 3).
    """

    def record_mail_failure(
        self,
        tenant_id: str,
        run_id: str,
        *,
        address: str,
        status: str = ...,
        reason: str | None = ...,
        message_id: str | None = ...,
        adjust_run_tally: bool = ...,
    ) -> Mapping[str, Any]:
        """Write a FAILURE-ONLY ``mailrecipient#`` sub-record (optionally adjusting the tally)."""
        ...


@dataclass(frozen=True)
class FeedbackResult:
    """The outcome of ingesting ONE SES notification — for the entry-point to report / log.

    - ``event_type`` — the normalised event type (bounce/complaint/delivery/other/``""``).
    - ``recorded`` — how many FAILURE sub-records were written (one per failed recipient).
    - ``ignored`` — True for a handled-but-not-recorded event (a delivery no-op), so the
      entry-point distinguishes "nothing to do" from "could not route".
    - ``unroutable_reason`` — set (and ``recorded == 0``) when the event could NOT be routed
      (missing/corrupt tenant/run tag, no failed recipient): the entry-point surfaces it (R9.5 —
      never a silent drop) and decides retry.
    - ``tenant_id`` / ``run_id`` — the resolved routing key (empty when unroutable), for the log.
    - ``addresses`` — the failed recipient address(es) a failure was recorded for.
    """

    event_type: str
    recorded: int = 0
    ignored: bool = False
    unroutable_reason: str | None = None
    tenant_id: str = ""
    run_id: str = ""
    addresses: tuple[str, ...] = field(default_factory=tuple)

    @property
    def routed(self) -> bool:
        """True when the event was understood + routed (recorded a failure OR a delivery no-op)."""
        return self.unroutable_reason is None


class MailFeedbackService:
    """Route ONE SES feedback notification to the Members store by its stamped tags (R8.4/R9.5).

    Storage-agnostic: depends only on the injected :class:`MailFailureStore`. ``tenant_id`` is
    AUTHORITATIVE from the stamped tag on every path (never guessed). A failure (bounce/complaint)
    is recorded with ``adjust_run_tally=True`` (the LATE path — the recipient succeeded at send,
    so the sub-record is CREATED now and the tally moved sent→failed). A delivery is a no-op.
    """

    def __init__(self, store: MailFailureStore):
        self._store = store

    def ingest(self, notification: Mapping[str, Any]) -> FeedbackResult:
        """Ingest ONE deserialized SES notification; return a :class:`FeedbackResult`.

        Never raises for a routing problem — an unroutable event is reported on the result (the
        entry-point surfaces + decides retry, R9.5). A ``record_mail_failure`` raising (a real
        store fault) DOES propagate so the entry-point can fail the record for redelivery.
        """
        if not isinstance(notification, Mapping):
            return FeedbackResult(
                event_type="", unroutable_reason="notification is not a JSON object"
            )

        event_type = self._event_type(notification)
        mail = notification.get("mail")
        mail = mail if isinstance(mail, Mapping) else {}
        tags = mail.get("tags") if isinstance(mail.get("tags"), Mapping) else {}

        tenant_id = decode_ses_tag_value(self._tag(tags, SES_TAG_TENANT_ID))
        run_id = decode_ses_tag_value(self._tag(tags, SES_TAG_RUN_ID))
        message_id = str(mail.get("messageId") or "") or None

        # A DELIVERY is informational — the core view is sent/failed and must not claim
        # per-recipient "delivered" from SES acceptance (R9.4). Handle (so it is not reported
        # unroutable) but record nothing. Done BEFORE the routing-key check so an untagged
        # delivery (benign) is a clean no-op, not a spurious unroutable report.
        if event_type == EVENT_TYPE_DELIVERY:
            logger.debug(
                "mail feedback: delivery event (message_id=%s run=%s) — informational, no-op",
                message_id,
                run_id,
            )
            return FeedbackResult(
                event_type=event_type,
                ignored=True,
                tenant_id=tenant_id,
                run_id=run_id,
            )

        if event_type not in (EVENT_TYPE_BOUNCE, EVENT_TYPE_COMPLAINT):
            # Not a type this layer records (e.g. a Reject/Send/Open slipped through). Report it
            # ignored rather than unroutable — benign, nothing to do.
            logger.info("mail feedback: unhandled event type %r — ignoring", event_type)
            return FeedbackResult(event_type=event_type or "", ignored=True)

        # FAILURE path — the routing key is REQUIRED. tenant_id is authoritative; without BOTH we
        # cannot place the failure, so report unroutable (never guess a tenant — fail-closed).
        if not tenant_id or not run_id:
            reason = "missing routing tag(s): " + ", ".join(
                name
                for name, present in (
                    ("tenant_id", bool(tenant_id)),
                    ("run_id", bool(run_id)),
                )
                if not present
            )
            logger.warning(
                "mail feedback: UNROUTABLE %s event (message_id=%s): %s",
                event_type,
                message_id,
                reason,
            )
            return FeedbackResult(event_type=event_type, unroutable_reason=reason)

        failures = self._failed_recipients(event_type, notification)
        if not failures:
            logger.warning(
                "mail feedback: %s event for run %s carried no recipient — nothing to record",
                event_type,
                run_id,
            )
            return FeedbackResult(
                event_type=event_type,
                unroutable_reason="no failed recipient in the event body",
                tenant_id=tenant_id,
                run_id=run_id,
            )

        status = (
            MAIL_RECIPIENT_STATUS_BOUNCED
            if event_type == EVENT_TYPE_BOUNCE
            else MAIL_RECIPIENT_STATUS_COMPLAINT
        )
        recorded: list[str] = []
        for address, reason in failures:
            # adjust_run_tally=True — the LATE async path (R8.4): the recipient was previously
            # counted as sent, so this CREATES the failure sub-record and moves the tally
            # sent→failed. tenant_id is authoritative (from the tag), pinned by the repository.
            self._store.record_mail_failure(
                tenant_id,
                run_id,
                address=address,
                status=status,
                reason=reason,
                message_id=message_id,
                adjust_run_tally=True,
            )
            recorded.append(address)

        logger.info(
            "mail feedback: recorded %d %s failure(s) for tenant=%s run=%s (message_id=%s)",
            len(recorded),
            event_type,
            tenant_id,
            run_id,
            message_id,
        )
        return FeedbackResult(
            event_type=event_type,
            recorded=len(recorded),
            tenant_id=tenant_id,
            run_id=run_id,
            addresses=tuple(recorded),
        )

    # ── parsing helpers ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _event_type(notification: Mapping[str, Any]) -> str:
        """The normalised (lowercased) event type.

        SES event-publishing uses ``eventType``; legacy identity feedback uses
        ``notificationType`` — accept either so the handler is robust to both wirings.
        """
        raw = notification.get("eventType") or notification.get("notificationType") or ""
        return str(raw).strip().lower()

    @staticmethod
    def _tag(tags: Mapping[str, Any], name: str) -> str:
        """Read ONE SES tag's single value — ``mail.tags`` is ``{name: [value, ...]}``.

        Returns the first value (SES stamps one value per custom tag), or ``""`` when the tag is
        absent / malformed (→ decodes to a missing routing key → the event is reported unroutable).
        """
        value = tags.get(name)
        if isinstance(value, (list, tuple)) and value:
            return str(value[0] or "")
        if isinstance(value, str):
            return value
        return ""

    @classmethod
    def _failed_recipients(
        cls, event_type: str, notification: Mapping[str, Any]
    ) -> list[tuple[str, str | None]]:
        """Extract ``(address, reason)`` for each failed recipient of a bounce/complaint event.

        - BOUNCE → ``bounce.bouncedRecipients[]`` with ``emailAddress`` + a diagnostic reason
          (``diagnosticCode`` / ``status`` / the bounce (sub)type).
        - COMPLAINT → ``complaint.complainedRecipients[]`` with ``emailAddress`` + the
          ``complaintFeedbackType`` as the reason.

        The reason is a metadata SES code/string (never member PII beyond the address being mailed,
        design §8). An address-less recipient entry is skipped.
        """
        if event_type == EVENT_TYPE_BOUNCE:
            bounce = notification.get("bounce")
            bounce = bounce if isinstance(bounce, Mapping) else {}
            default_reason = cls._join_reason(
                bounce.get("bounceType"), bounce.get("bounceSubType")
            )
            return cls._recipients(
                bounce.get("bouncedRecipients"),
                lambda r: cls._first_reason(
                    r.get("diagnosticCode"), r.get("status"), default_reason
                ),
            )
        if event_type == EVENT_TYPE_COMPLAINT:
            complaint = notification.get("complaint")
            complaint = complaint if isinstance(complaint, Mapping) else {}
            default_reason = cls._first_reason(
                complaint.get("complaintFeedbackType"), None, "complaint"
            )
            return cls._recipients(
                complaint.get("complainedRecipients"),
                lambda _r: default_reason,
            )
        return []

    @staticmethod
    def _recipients(
        raw: Any, reason_of: Any
    ) -> list[tuple[str, str | None]]:
        """Map a list of SES recipient entries to ``(address, reason)`` pairs (skip address-less)."""
        out: list[tuple[str, str | None]] = []
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return out
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            address = str(entry.get("emailAddress") or "").strip()
            if not address:
                continue
            out.append((address, reason_of(entry)))
        return out

    @staticmethod
    def _first_reason(*candidates: Any) -> str | None:
        """The first non-blank candidate as the failure reason (or ``None`` when all blank)."""
        for candidate in candidates:
            if candidate is not None and str(candidate).strip():
                return str(candidate).strip()
        return None

    @staticmethod
    def _join_reason(*parts: Any) -> str | None:
        """Join non-blank parts with ``/`` (e.g. ``Permanent/General``), or ``None`` when all blank."""
        joined = "/".join(str(p).strip() for p in parts if p is not None and str(p).strip())
        return joined or None
