"""
Members mail — the SES FEEDBACK INGESTION Lambda **entry point** (mail-spec task 5.2; R8.4/R9.5).

The CONSUMER side of the SES → SNS feedback pipeline the task-5.1 infra wired: the Members SES
configuration set publishes bounce/complaint/delivery events to the ``MembersMailFeedbackTopic``
SNS topic; this handler is SUBSCRIBED to that topic (template ``AWS::SNS::Subscription``) and
routes each event back to the Members store by the stamped message tags (R9.5).

Thin by design (steering 35, mirrors :mod:`sam.members.worker.app`): the handler's whole job is

    parse the SNS event → unwrap each record's SES notification → delegate to the service → report

and nothing else. All logic (tag routing, failure recording, the delivery no-op, the fail-closed
tenancy) lives in :class:`~sam.members.domain.mail_feedback_handler.MailFeedbackService`. The
production store (the DynamoDB Members repository) is wired once at cold start by
:func:`get_service` and resolves lazily + fail-fast on first use, so importing this module (and the
test suite) touches NO AWS. Tests set ``_SERVICE`` / patch :func:`get_service` to inject a service
over a fake repo.

SNS → Lambda delivery (NO partial batch)
----------------------------------------
Unlike the SQS worker, an SNS → Lambda subscription has NO partial-batch response: the whole
invocation either succeeds (SNS considers the message delivered) or RAISES (SNS retries per its
delivery policy, then dead-letters if a subscription DLQ is configured). SNS normally delivers ONE
record per invocation, but the handler loops defensively. An UNROUTABLE event (missing tag / no
recipient) is NOT a transient fault — retrying will never make the tag appear — so it is LOGGED +
counted but does NOT raise (never a silent drop: it is surfaced in the log/return, R9.5). A real
STORE fault (``record_mail_failure`` raising) DOES propagate so SNS retries the delivery.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

__all__ = ["get_service", "handler"]

#: The module-global ingestion service, built once at cold start (``None`` until first use). A warm
#: Lambda container reuses it; the store resolves lazily + fail-fast on first use.
_SERVICE: Any = None


def get_service() -> Any:
    """Return the module-global SES-feedback ingestion service, building it once at cold start.

    Wires the task-5.2 service over its production store — the DynamoDB Members repository
    (:class:`~sam.members.repository.members_repository.DynamoDbMembersRepository`), whose
    tenant-pinned ``record_mail_failure`` satisfies the service's ``MailFailureStore`` seam.
    Everything resolves lazily + fail-fast on first use, so importing this module (and the tests)
    never touches AWS. Tests patch this accessor (or set ``_SERVICE``) to inject a service over a
    fake repo.
    """
    global _SERVICE
    if _SERVICE is None:
        from sam.members.domain.mail_feedback_handler import MailFeedbackService
        from sam.members.repository.members_repository import DynamoDbMembersRepository

        _SERVICE = MailFeedbackService(store=DynamoDbMembersRepository())
    return _SERVICE


def handler(event: Any, context: Any = None) -> dict[str, Any]:
    """Ingest one SNS batch of SES feedback notifications; return a metadata-only summary.

    Parses the SNS event, unwraps each record's ``Sns.Message`` (a JSON STRING = the SES
    notification), and delegates each to the ingestion service. A record whose SES payload cannot
    be parsed, or that routes to an unroutable event, is LOGGED + counted (never silently dropped,
    R9.5) but does not raise — retrying cannot fix a malformed/untagged event. A STORE fault from
    the service propagates so SNS retries the delivery.
    """
    records = event.get("Records", []) if isinstance(event, dict) else []
    service = get_service()

    recorded = routed = unroutable = ignored = 0
    for record in records:
        try:
            notification = _parse_record(record)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            # A malformed SES payload is not transient — log + skip rather than churn SNS retries.
            logger.warning("mail feedback: skipping malformed SNS record: %s", exc)
            unroutable += 1
            continue

        result = service.ingest(notification)
        if result.routed:
            routed += 1
            recorded += result.recorded
            if result.ignored:
                ignored += 1
        else:
            unroutable += 1
            logger.warning(
                "mail feedback: unroutable %s event: %s",
                result.event_type or "unknown",
                result.unroutable_reason,
            )

    summary = {
        "records": len(records),
        "routed": routed,
        "recorded": recorded,
        "ignored": ignored,
        "unroutable": unroutable,
    }
    logger.info("mail feedback: batch summary %s", summary)
    return summary


def _parse_record(record: Any) -> dict[str, Any]:
    """Unwrap one SNS record into the SES notification mapping.

    An SNS → Lambda record is ``{"Sns": {"Message": "<json string>", ...}}`` — the ``Message`` is
    the SES notification serialized as a JSON STRING (SES publishes JSON; SNS carries it as the
    message body). Deserialize it into the mapping the service consumes. A non-object record / a
    missing or non-JSON ``Message`` is malformed — raise so it is logged + skipped.
    """
    if not isinstance(record, dict):
        raise TypeError("SNS record must be an object")
    sns = record.get("Sns")
    if not isinstance(sns, dict):
        raise ValueError("SNS record is missing the 'Sns' envelope")
    message = sns.get("Message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("SNS record is missing a JSON 'Message'")
    notification = json.loads(message)
    if not isinstance(notification, dict):
        raise TypeError("SES notification must be a JSON object")
    return notification
