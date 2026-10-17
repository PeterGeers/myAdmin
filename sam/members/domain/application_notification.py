"""
Member-application spec task 6.2 — the **offloaded notification ENQUEUE orchestration**
(R8/R8a/R9, D5/D10; design §6 / seam e).

ONE storage-agnostic Members-domain component with ONE job: on a successful public
application (``create_application``, Phase 2), enqueue the **two** notification jobs — a
STAFF notification and an APPLICANT confirmation (D10) — onto the EXISTING members mail-send
queue via the :class:`~sam.members.repository.mail_send_queue.MailSendQueuePort` port
(``enqueue`` / ``enqueue_many``). It REUSES that queue exactly as the pivot/analytics mail
path does (``ExecuteAndDeliverService`` fans jobs onto the SAME port) — it does NOT build a
new queue, a new SES client, or a new DynamoDB touch-point.

Where it sits (steering 35)
---------------------------
thin public edge (``handler/public_app``) → ``create_application`` (writes the record) → THIS
service (builds + enqueues the two jobs) → the :class:`MailSendQueuePort` seam. It is the
ENQUEUE half of seam e only: it names no boto3, no SES, no DynamoDB, no projection — only the
queue Protocol. The WORKER half (task 6.3) drains these jobs and owns recipient resolution
(``role-recipients`` reader, task 6.1), ``From`` composition (``MailSenderResolver``, D4),
Reply-To (D8/D24), and the bilingual template rendering; the ``NO_NOTIFY`` note + the send-log
tally (D22) are task 6.4. So this module deliberately carries only what the worker needs to
START each branch — it resolves no recipients and renders no body.

Why offloaded (D5, R8.7/R8a.3)
------------------------------
The applicant's request returns a neutral 202 the instant the record is written; the actual
recipient resolution + SES send happen in the worker, so a slow / failing SES call never sits
in the applicant's request path and can NEVER roll back the committed record. Enqueue is the
only synchronous step, and it is cheap (two ``SendMessage`` calls). An enqueue failure is
best-effort by R8.7/R8.8 — the record is already the source of truth and is always discoverable
in the ``status=application`` inbox (R8b.4) even if nothing was enqueued — so this service
NEVER lets an enqueue error fail the submission (see :meth:`enqueue_application_notifications`).

``tenant_id`` is AUTHORITATIVE on the envelope (D5/D10, R2/R8.9 — the point of this task)
----------------------------------------------------------------------------------------
Both job envelopes carry ``tenant_id`` SERVER-SIDE from the resolved tenant (the slug→tenant
resolution of R2, passed by the caller), NEVER from the applicant's body. The worker reads
recipients, the ``config#mail`` sender, and the send-log run ALL keyed by this envelope
``tenant_id`` (Property 1 — a notification can never cross tenants, and a public caller can
never choose its recipients or sender, R8.9). The applicant NEVER contributes the tenant.

The two jobs (design §6)
------------------------
Each job is a plain JSON-serializable mapping — the send-job ENVELOPE the worker consumes —
discriminated by a stable :data:`JOB_KIND_KEY` (``"kind"``) so the worker branches on it
(task 6.3) exactly as the pivot worker branches on ``mode``:

- :data:`JOB_KIND_STAFF` (``member_application_staff``) — the staff notification. Carries the
  authoritative ``tenant_id``, the ``member_id`` for the deep-link to the authenticated member
  detail (R8.6 — review behind auth, so NO applicant PII rides the envelope beyond a display
  name), and the neutral ``duplicate_suspected`` marker (R8.6a — a one-line triage hint derived
  from the record's ``DUP`` note, which NEVER names the matched member). Recipients + Reply-To
  are resolved by the worker (task 6.1/6.3), NOT here.
- :data:`JOB_KIND_APPLICANT` (``member_application_ack``) — the applicant confirmation (D10).
  Carries the authoritative ``tenant_id``, the applicant's OWN server-validated ``email``
  (R8a.4 — never any other client-supplied address), the applicant's ``locale`` (R6b/R8a.2 —
  the confirmation renders in the applicant's chosen language), and a copy of the applicant's
  OWN submitted data (``submitted`` — their own data is not a PII leak, R8a.4). The worker
  renders the "application received" body from it (task 6.3).

The envelope is intentionally MINIMAL (identity + the branch's start inputs) — the worker owns
every downstream decision — so this seam stays a pure, side-effect-light orchestration that a
test drives with an in-memory fake queue and asserts: two jobs enqueued, ``tenant_id``
authoritative on EACH, and the staff-vs-applicant ``kind`` discrimination.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from sam.members.domain.applicant_locale import locale_of_record
from sam.members.repository.mail_send_queue import MailSendQueuePort

logger = logging.getLogger(__name__)

__all__ = [
    "JOB_KIND_APPLICANT",
    "JOB_KIND_KEY",
    "JOB_KIND_STAFF",
    "NO_NOTIFY_KEYWORD",
    "ApplicationNotificationService",
    "append_additional_info_keyword",
    "build_application_notification_jobs",
]

#: The members-record overlay bucket + the leftover-info free-text key the keyword notes ride.
#: Mirrors ``_MembershipWrites._OVERLAY_ADDITIONAL_INFO_KEY`` / ``field_resolver.OVERLAY_GROUP``
#: — kept as local constants so this notifier module appends a keyword WITHOUT importing the
#: writes mixin (one-way dependency: the notifier reads/annotates a record, the mixin owns the
#: create path). No new flag column (design): both the ``DUP`` and ``NO_NOTIFY`` signals ride
#: this one free-text field, keyword-filterable on the applications inbox (R8b.5).
_OVERLAY_GROUP = "overlay"
_ADDITIONAL_INFO_KEY = "additional_info"

#: The envelope key that discriminates the two application jobs (the analogue of the pivot
#: path's ``mode``). The worker (task 6.3) branches on it to pick the staff vs applicant
#: composition; a job with an unknown/absent kind is a programming fault the worker refuses
#: loudly rather than mis-sending.
JOB_KIND_KEY = "kind"

#: The STAFF notification job kind (design §6). Deep-link + neutral duplicate marker, NO PII.
JOB_KIND_STAFF = "member_application_staff"

#: The APPLICANT confirmation job kind (design §6/D10). The applicant's own data + their locale.
JOB_KIND_APPLICANT = "member_application_ack"

#: The stable ``overlay.additional_info`` keyword the duplicate flag (task 2.5/D25) writes when
#: an applicant's name+DOB matches an existing member. Mirrors ``_MembershipWrites._DUP_KEYWORD``
#: — kept as an independent constant here so this module reads the record WITHOUT importing the
#: writes mixin (one-way dependency: the notifier reads a record, it does not write members).
#: The STAFF job surfaces only the neutral boolean fact "a possible duplicate exists" (R8.6a);
#: the matched member is NEVER named on the envelope (no cross-member PII, R8.6/R12.4).
_DUP_KEYWORD = "DUP"

#: The stable ``overlay.additional_info`` keyword the worker (task 6.4) appends to a committed
#: application record when its staff notification had NO recipients — no all-scope ``Members_CRUD``
#: AND no ``TenantAdmin`` (R8.4/R8.5). The application is NOT lost: it is in the
#: ``status=application`` inbox (R8b.4); this note makes the "landed but could not be auto-notified"
#: fact keyword-filterable there (R8b.5) rather than merely a Lambda log line. A DOCUMENTED, stable
#: token (R9.5) so the inbox filter and any later tooling match it exactly.
NO_NOTIFY_KEYWORD = "NO_NOTIFY"


def append_additional_info_keyword(
    record: dict[str, Any], keyword: str
) -> bool:
    """Append ``keyword`` to ``overlay.additional_info`` (space-separated), idempotently.

    The pure, storage-agnostic mechanism BOTH the create-path duplicate flag (task 2.5's
    ``_MembershipWrites._append_additional_info_keyword``, the ``DUP`` note) and the worker-side
    ``NO_NOTIFY`` note (task 6.4) share: no new flag column (design) — the signal rides the
    existing ``overlay.additional_info`` leftover-info free-text field as a space-separated
    keyword entry, keyword-filterable on the applications inbox (R8b.5). Appending (not replacing)
    preserves any existing note (e.g. a ``DUP`` keyword already there); a keyword already present
    is NOT re-added, so a redelivery / resend never accumulates duplicate markers.

    Mutates ``record`` in place (creating the ``overlay`` bucket if absent) and returns ``True``
    when it actually appended the keyword, ``False`` when it was already present (idempotent
    no-op) — the caller uses that to decide whether a persist is needed.
    """
    overlay = record.get(_OVERLAY_GROUP)
    if not isinstance(overlay, dict):
        overlay = dict(overlay) if isinstance(overlay, Mapping) else {}
        record[_OVERLAY_GROUP] = overlay
    existing = overlay.get(_ADDITIONAL_INFO_KEY)
    existing_text = str(existing).strip() if existing not in (None, "") else ""
    if keyword in existing_text.split():
        return False  # already flagged — idempotent (a redelivery must not double-append)
    overlay[_ADDITIONAL_INFO_KEY] = (
        f"{existing_text} {keyword}".strip() if existing_text else keyword
    )
    return True


def _record_str(record: Mapping[str, Any], *path: str) -> str:
    """Read a nested string off a member record by ``path``, returning ``""`` when absent/blank.

    Walks ``a.b`` into nested mappings (``record["personal"]["email"]``), tolerating a non-mapping
    at any level (→ ``""``). Used to pull the applicant's own ``personal.email`` / display name off
    the committed record without trusting a parallel raw body — the record is already the
    server-sanitized source of truth (``create_application`` forced/validated it).
    """
    current: Any = record
    for segment in path:
        if not isinstance(current, Mapping):
            return ""
        current = current.get(segment)
    return current.strip() if isinstance(current, str) and current.strip() else ""


def _duplicate_suspected(record: Mapping[str, Any]) -> bool:
    """Return whether the record carries the duplicate flag — a NEUTRAL boolean (R8.6a).

    Reads the ``DUP`` keyword off ``overlay.additional_info`` (task 2.5 appended it there as a
    space-separated keyword). Returns ONLY the boolean fact so the staff email can show a neutral
    one-line triage hint; it NEVER reveals the matched member (no cross-member PII, R8.6/R12.4) —
    the actual comparison happens behind the authenticated deep-link (R8b.5).
    """
    overlay = record.get("overlay")
    if not isinstance(overlay, Mapping):
        return False
    info = overlay.get("additional_info")
    if not isinstance(info, str):
        return False
    return _DUP_KEYWORD in info.split()


def _applicant_display_name(record: Mapping[str, Any]) -> str:
    """A non-sensitive display name for the staff notification subject line (R8.6).

    Composed from the record's own ``personal`` name parts (first + optional infix + last). This
    is the ONE piece of applicant-identifying text the staff email carries — enough to recognise
    the notification, no more (the full record is behind the deep-link, R8.6). Blank when the name
    parts are absent (the worker falls back to a generic subject).
    """
    parts = [
        _record_str(record, "personal", "first_name"),
        _record_str(record, "personal", "name_infix"),
        _record_str(record, "personal", "last_name"),
    ]
    return " ".join(p for p in parts if p)


def build_application_notification_jobs(
    tenant_id: str,
    record: Mapping[str, Any],
    run_id: str,
) -> list[dict[str, Any]]:
    """Build the TWO application-notification job envelopes (staff + applicant), tenant-authoritative.

    Pure (no I/O): turns an authoritative ``tenant_id`` + the committed application ``record`` into
    the two JSON-serializable envelopes the worker (task 6.3) consumes. Split out from
    :meth:`ApplicationNotificationService.enqueue_application_notifications` so the envelope SHAPE
    is unit-testable without a queue, and so the enqueue method stays a thin "build then enqueue".

    ``tenant_id`` is stamped on BOTH envelopes from the resolved-tenant argument — NEVER from the
    record's own ``tenant_id`` and NEVER from the applicant (D5/D10, R2/R8.9). (``create_application``
    already stamped the record's ``tenant_id`` authoritatively from the same source, so they agree;
    taking it from the explicit argument keeps this function's contract honest — the caller owns the
    authoritative tenant.)

    Args:
        tenant_id: the AUTHORITATIVE tenant (the slug→tenant resolution of R2), stamped on every
            envelope. The worker keys recipients / sender / send-log by it (Property 1).
        record: the committed application member record (``create_application``'s return) — the
            server-sanitized source of truth. The applicant's email / locale / display name /
            duplicate flag are read FROM it, never from a parallel raw body.
        run_id: the id for this ONE logical notification run, shared by BOTH jobs so the send-log
            (task 6.4/D22) and any trace correlate the staff + applicant sends of one application.

    Returns:
        A two-element list ``[staff_job, applicant_job]`` — each a plain mapping with the
        authoritative ``tenant_id`` + its :data:`JOB_KIND_KEY` discriminator.
    """
    member_id = _record_str(record, "member_id") or str(record.get("member_id") or "")
    locale = locale_of_record(record)

    # STAFF job — deep-link + neutral duplicate marker, NO applicant PII beyond a display name
    # (R8.6/R8.6a). Recipients + Reply-To are the worker's job (task 6.1/6.3), not the envelope's.
    staff_job: dict[str, Any] = {
        JOB_KIND_KEY: JOB_KIND_STAFF,
        "tenant_id": tenant_id,  # AUTHORITATIVE — server-side, never the applicant (D5/D10)
        "run_id": run_id,
        "member_id": member_id,  # the deep-link target /members/{member_id} (R8.6/R8b.1)
        "applicant_display_name": _applicant_display_name(record),
        "duplicate_suspected": _duplicate_suspected(record),  # neutral triage hint (R8.6a)
    }

    # APPLICANT confirmation job (D10) — the applicant's OWN email + locale + a copy of their OWN
    # submitted data (their own data is not a PII leak, R8a.4). From/sender is the worker's job.
    applicant_job: dict[str, Any] = {
        JOB_KIND_KEY: JOB_KIND_APPLICANT,
        "tenant_id": tenant_id,  # AUTHORITATIVE — same resolved tenant as the staff job (D5/D10)
        "run_id": run_id,
        "member_id": member_id,
        "recipient": _record_str(record, "personal", "email"),  # server-validated address (R8a.4)
        "locale": locale,  # the applicant's chosen locale (R6b/R8a.2)
        "submitted": _submitted_copy(record),  # the applicant's OWN data (R8a.4)
    }

    return [staff_job, applicant_job]


def _submitted_copy(record: Mapping[str, Any]) -> dict[str, Any]:
    """A JSON-serializable copy of the applicant's OWN submitted field groups (R8a.4).

    The applicant confirmation embeds a copy of what they submitted (R8a.1/R8a.4 — their own data,
    not a leak). This carries the record's field GROUPS (``personal`` / ``membership`` / ``overlay``
    and any tenant overlay groups) minus the server-owned identity/control keys the applicant did
    not submit and does not need echoed (``tenant_id`` / ``member_id`` / ``consent`` / ``locale`` —
    the latter two ride the envelope explicitly). The worker renders the body from this; keeping it
    a shallow copy of the group mappings keeps the envelope small and JSON-serializable.
    """
    skip = {"tenant_id", "member_id", "consent", "locale"}
    copy: dict[str, Any] = {}
    for key, value in record.items():
        if key in skip:
            continue
        if isinstance(value, Mapping):
            copy[key] = dict(value)
        else:
            copy[key] = value
    return copy


class ApplicationNotificationService:
    """Enqueue the two application-notification jobs (staff + applicant) — the ENQUEUE seam (task 6.2).

    Storage-agnostic: depends ONLY on the injected :class:`MailSendQueuePort` (the SAME queue the
    pivot/analytics mail path uses — reused, not rebuilt). It builds the two envelopes
    (:func:`build_application_notification_jobs`) and enqueues them; it resolves no recipients,
    composes no ``From``, renders no template (all the worker's job, task 6.3). ``tenant_id`` is
    authoritative on every envelope (D5/D10).

    Best-effort by design (R8.7/R8.8): the applicant's record is already committed before this is
    called, so an enqueue failure must NEVER propagate back into the request and fail the
    submission — the application is always discoverable in the ``status=application`` inbox (R8b.4)
    regardless. :meth:`enqueue_application_notifications` therefore logs-and-swallows an enqueue
    error and reports how many jobs made it onto the queue, rather than raising.
    """

    def __init__(self, queue: MailSendQueuePort):
        self._queue = queue

    def enqueue_application_notifications(
        self,
        tenant_id: str,
        record: Mapping[str, Any],
        run_id: str | None = None,
    ) -> list[str]:
        """Enqueue the staff + applicant notification jobs for a committed application; best-effort.

        Builds the two tenant-authoritative envelopes and enqueues them via the port. The two jobs
        share one ``run_id`` (minted here when the caller supplies none) so the send-log (task
        6.4/D22) and any trace correlate them as one notification run.

        Best-effort (R8.7/R8.8): the record is ALREADY committed, so an enqueue error is logged and
        swallowed — it never rolls back the submission or changes the applicant's neutral 202 (the
        application stays discoverable in the inbox, R8b.4). Each job is enqueued independently so a
        failure on one still lets the other land.

        Args:
            tenant_id: the AUTHORITATIVE tenant (the resolved slug→tenant of R2), stamped on BOTH
                envelopes — never the applicant's value (D5/D10, R8.9).
            record: the committed application member record (``create_application``'s return).
            run_id: an optional caller-supplied run id (the edge may mint one for its trace); a
                server-minted ``uuid4`` is used when absent so both jobs still correlate.

        Returns:
            The backing message ids of the jobs that were successfully enqueued, in
            ``[staff, applicant]`` order — possibly fewer than two if an enqueue failed (best-effort).
        """
        effective_run_id = run_id or str(uuid.uuid4())
        jobs = build_application_notification_jobs(tenant_id, record, effective_run_id)

        message_ids: list[str] = []
        for job in jobs:
            try:
                message_ids.append(self._queue.enqueue(job))
            except Exception:
                # Best-effort (R8.7/R8.8): the record is already committed. A failed enqueue must
                # never fail the applicant's submission — log server-side and carry on so the
                # other job still gets its chance. The application is in the inbox either way.
                logger.exception(
                    "Failed to enqueue %s application-notification job for tenant %r (run_id=%s)",
                    job.get(JOB_KIND_KEY),
                    tenant_id,
                    effective_run_id,
                )
        return message_ids
