"""Shared constants/type aliases for the members repository mixins.
Part of DynamoDbMembersRepository (task 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# --- Send-run status constants (R9, mail-spec task 3.1) --------------------------------

#: How long a send-run status record (``mailrun#`` + its ``mailrecipient#`` failures) is retained
#: (seconds) via DynamoDB TTL — the design DEFAULT of 90 days. 90d covers ~3 monthly newsletter
#: cycles of look-back; the records are tiny metadata. TTL is best-effort auto-cleanup; a manual
#: delete (:meth:`DynamoDbMembersRepository.delete_mail_run`) is also supported. (Distinct from the
#: dedupe marker's 14d — a different, short-lived purpose.)
MAIL_RUN_TTL_SECONDS = 90 * 24 * 60 * 60

# --- Public-application session de-dup constant (R3a, application-app task 2.1) --------

#: How long a public-application session de-dup marker (``appsession#<session_key>``) is retained
#: (seconds) via DynamoDB TTL. A session key de-dups a single fill-in session's submits (first
#: creates, resends update that record); once the applicant has gone away the mapping is no longer
#: needed, so 30 days generously covers an interrupted-and-resumed session while keeping the table
#: from accumulating markers forever. TTL is best-effort auto-cleanup, not a correctness guarantee
#: — the member record it maps to is the source of truth and is NOT TTL'd.
APP_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60

#: The send-run status lifecycle (R9.1): written ``queued`` at enqueue, advanced to ``sending`` /
#: ``completed`` by the worker as it drains the run's jobs.
MAIL_RUN_STATUS_QUEUED = "queued"
MAIL_RUN_STATUS_SENDING = "sending"
MAIL_RUN_STATUS_COMPLETED = "completed"

#: The FAILURE sub-record statuses (R9.5): a send-time ``failed`` or a late async ``bounced`` /
#: ``complaint`` (R8.4). A success is never stored (it is counted in the run tally).
MAIL_RECIPIENT_STATUS_FAILED = "failed"
MAIL_RECIPIENT_STATUS_BOUNCED = "bounced"
MAIL_RECIPIENT_STATUS_COMPLAINT = "complaint"


# Convenience aliases so the intent of each argument is legible in the signatures.
Member = Mapping[str, Any]
Membership = Mapping[str, Any]
Payment = Mapping[str, Any]
Delegate = Mapping[str, Any]
