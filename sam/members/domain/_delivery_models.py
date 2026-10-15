"""Value objects, ports, and errors for the execute-and-deliver service (R4, design §4.1/§4.2).

This is the pure DATA + PORT layer the :class:`~sam.members.domain.execute_and_deliver.
ExecuteAndDeliverService` resolves into and depends on — carved off along a clean cohesion seam
so the service module holds only resolution logic:

- the errors the edge maps to 4xx (:class:`DeliveryNotConfigured`, :class:`MailNotCertified`,
  :class:`AdHocMailInvalid`),
- the storage-agnostic PORT Protocols the service depends on (:class:`PivotRunner`,
  :class:`MailQueue`),
- the immutable messages/outputs it builds (:class:`MailJob`, :class:`AdHocMailBody`,
  :class:`DeliveryOutcome`), and
- the :data:`DEFAULT_RECIPIENT_FIELD` constant.

None of these carry resolution logic (that is ``ExecuteAndDeliverService``), and none import a
repository or SQS — they name only the Protocols and the typed certification reason. The
service module re-exports every name here VERBATIM, so the public import surface
``sam.members.domain.execute_and_deliver`` is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.mail_sender_resolver import NotCertifiedReason

__all__ = [
    "DEFAULT_RECIPIENT_FIELD",
    "AdHocMailBody",
    "AdHocMailInvalid",
    "DeliveryNotConfigured",
    "DeliveryOutcome",
    "MailJob",
    "MailQueue",
    "MailNotCertified",
    "PivotRunner",
]

#: The dotted path into a member/result row that resolves a ``per_recipient`` recipient
#: address when the delivery block names no explicit field. ``personal.email`` is the
#: canonical member contact key the Members plane already uses (fixed-fields +
#: lifecycle guards both key on it). The ADDRESS is resolved from the dataset at run
#: time — never stored on the block (design §2.1). A delivery block MAY override this by
#: carrying a ``recipient_field`` dotted path (e.g. an alternate contact column).
DEFAULT_RECIPIENT_FIELD = "personal.email"


class DeliveryNotConfigured(Exception):
    """Raised when a set has no stored ``delivery`` block but a delivery was requested (→ 422).

    A saved set with no ``delivery`` (the legacy default) has nothing to run: there is no
    mode, no template, no recipients. The deliver route (task 4.2) maps this to a clear
    client error rather than silently enqueuing nothing — "configure a delivery first".
    """

    def __init__(self, tenant_id: str, set_id: str):
        self.tenant_id = tenant_id
        self.set_id = set_id
        super().__init__(
            f"analytics set {set_id!r} has no delivery block for tenant {tenant_id!r} "
            "(configure a delivery before running it)"
        )


class MailNotCertified(Exception):
    """Raised when the active tenant has no usable verified From — refuse BEFORE enqueue (R4.2/R5.2).

    The pre-send certification gate (:class:`~sam.members.domain.mail_sender_resolver.
    MailSenderResolver`) runs SYNCHRONOUSLY on the enqueue path, before any job is placed on the
    queue. When it refuses — mail not enabled, tenant not certified, or no mail domain projected —
    this is raised carrying the TYPED :class:`~sam.members.domain.mail_sender_resolver.
    NotCertifiedReason` so the edge maps it to a clear bilingual 4xx + action (Property 6 — never a
    silent drop). NOTHING is enqueued and NO substitute sender is ever used (R4.2 — the ``jabaki.nl``
    foreign-sender regression stays dead; Property 2/4). The ``run_id`` is carried for the edge's
    attribution/trace.
    """

    def __init__(self, tenant_id: str, set_id: str, reason: NotCertifiedReason):
        self.tenant_id = tenant_id
        self.set_id = set_id
        self.reason = reason
        super().__init__(
            f"tenant {tenant_id!r} cannot send mail for set {set_id!r}: "
            f"{reason.value} (refused before enqueue — no send, no substitute sender)"
        )


class AdHocMailInvalid(Exception):
    """Raised when an AD-HOC compose body is malformed (a client bug → 422 at the edge).

    The ad-hoc send (``POST /members/mail/send``, mail-spec task 2.1) carries the compose body
    itself — the current result rows, the typed recipients / template / attachment — rather than
    a saved set + stored delivery. There is NO entity ``validate()`` behind it (unlike a saved
    set), so this service validates the body's SHAPE before building any job: an unknown ``mode``,
    a ``per_recipient`` body with no result rows to mail, or a ``to_fixed`` body with no explicit
    recipients. The edge maps this to a clear 422 rather than silently enqueuing nothing (Property
    6 — never a silent drop). The gate is validated BEFORE the pre-send certification check only
    for shape; nothing is enqueued when it raises.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"ad-hoc mail body is invalid: {detail}")


# ── Ports (the storage-agnostic seams this task owns / depends on) ──────────────────────


@runtime_checkable
class PivotRunner(Protocol):
    """The pivot/list computation PORT — turns a set definition + member rows into result rows.

    The pivot/list engine is NOT a DynamoDB concern and is not yet built in the SAM plane
    (today the pivot runs frontend/Flask-side), so this service depends on the SHAPE of a
    runner, not a concrete engine. A ``count`` set aggregates; a ``list`` set filters — either
    way the runner returns the RESULT ROWS the delivery fans out over. A fake runner in tests
    returns a canned shape; the real engine satisfies this Protocol unchanged when it lands.
    """

    def run(
        self,
        tenant_id: str,
        definition: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        """Run ``definition`` over the re-fetched ``rows`` and return the result rows."""
        ...


@runtime_checkable
class MailQueue(Protocol):
    """The enqueue PORT — the storage-agnostic seam between this service and the send worker.

    The service builds :class:`MailJob` records and hands them here; WHERE they go (real SQS,
    task 4.2) is behind this Protocol so this task needs no AWS wiring and tests capture the
    enqueued jobs with an in-memory fake. ``enqueue`` is idempotent-friendly: the job carries a
    stable :attr:`MailJob.job_id` so an at-least-once redelivery is de-duped downstream
    (the worker, task 4.3) — the queue itself only needs to deliver at-least-once.
    """

    def enqueue(self, job: "MailJob") -> None:
        """Place one send job on the queue (at-least-once delivery is sufficient)."""
        ...


@dataclass(frozen=True)
class MailJob:
    """One send job the worker (task 4.3) drains — the stable, self-describing unit of work.

    Frozen (it is an immutable message). The shape is the SAME for both delivery modes and for
    both the interactive and the scheduled trigger (design §4.2 — one job shape, one worker):

    - ``job_id`` — the STABLE idempotency id (design §4.2). Deterministic from the run
      identity, so an at-least-once SQS redelivery of the same logical job carries the same id
      and the worker dedupes it; two distinct runs never collide.
    - ``tenant_id`` — the owning tenant (the worker sends only within it; Property 1).
    - ``set_id`` — the saved set this run came from (audit + trace).
    - ``run_id`` — the caller-supplied id for ONE logical run (shared by every job of a
      ``per_recipient`` fan-out, so a run can be traced/deduped as a whole).
    - ``mode`` — ``per_recipient`` or ``to_fixed`` (the worker renders accordingly).
    - ``from_address`` — the RESOLVED tenant From (``noreply@<tenant-domain>``) this job sends
      FROM (mail-spec task 1.3; design "MailJob (EXTENDED): carries resolved from_address").
      Resolved ONCE at enqueue time by the pre-send :class:`~sam.members.domain.
      mail_sender_resolver.MailSenderResolver` and STAMPED onto every job (both modes), so the
      worker FORWARDS it to SES without re-resolving (Property 2 — one correct sender, never a
      substitute). Always a non-empty verified From here (a refusal raises before any job is built).
    - ``reply_to`` — the triggering user's verified email the replies go to (R4.3), stamped from
      the edge's verified JWT. ``None`` for an unattended (scheduled) run with no triggering user.
    - ``recipients`` — the address(es) this job sends to: exactly one for a ``per_recipient``
      job (resolved from the member's row), or the fixed list for a ``to_fixed`` job.
    - ``template_id`` — the template ref to render (``per_recipient`` merge / the body of a
      ``to_fixed`` covering mail); ``None`` when the mode carries none.
    - ``merge_values`` — THIS recipient's ``{field: value}`` map for the mail-merge
      (``per_recipient`` only; empty for ``to_fixed``). Resolved from the member's result row.
    - ``attachment`` — the attachment descriptor for a ``to_fixed`` job
      (``{"kind": "csv"|"pdf_labels", "label_options": {...}|None}``) or ``None``.
    - ``rows`` — the result rows the worker needs to BUILD a ``to_fixed`` attachment from
      (empty for ``per_recipient``, which carries per-member merge values instead).
    """

    job_id: str
    tenant_id: str
    set_id: str
    run_id: str
    mode: str
    recipients: tuple[str, ...]
    from_address: str = ""
    reply_to: str | None = None
    template_id: str | None = None
    merge_values: Mapping[str, Any] = field(default_factory=dict)
    attachment: Mapping[str, Any] | None = None
    rows: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class AdHocMailBody:
    """The AD-HOC compose body a stateless ``POST /members/mail/send`` carries (mail-spec task 2.2).

    The ad-hoc interactive send is DIFFERENT from the saved-set deliver: it carries the compose's
    OWN inputs — the current result rows + the typed recipients / template / attachment — not an
    ``analyticsset#<id>`` + a stored ``delivery`` block (design "What to ADD" #1 / "Resolved
    implementation choices"). So this frozen body is the ad-hoc analogue of a saved set's
    ``(delivery, result_rows)`` pair: it feeds the SAME fan-out helpers (``_deliver_per_recipient``
    / ``_deliver_to_fixed``) and therefore produces the SAME :class:`MailJob` shape and runs the
    SAME pre-send gate. There is no saved set, so :attr:`set_id` is a free-form LABEL for audit /
    the stable job id, not an entity key — the body carries no DynamoDB identity and the service
    does NO repository re-fetch for an ad-hoc send (the rows arrive on the body).

    - ``mode`` — ``per_recipient`` or ``to_fixed`` (the same discriminator a saved delivery uses).
    - ``result_rows`` — the CURRENT result rows the compose is sending (already computed
      client/pivot-side). For ``per_recipient`` the per-member address is resolved from each row
      exactly as the saved path does; for ``to_fixed`` the whole set ships once as the attachment
      source.
    - ``recipients`` — the fixed recipient list for ``to_fixed`` (ignored for ``per_recipient``,
      whose addresses come from the rows). Non-empty for ``to_fixed``.
    - ``template_id`` — the template to render (``per_recipient`` merge / ``to_fixed`` covering
      mail body); ``None`` when the compose carries none.
    - ``attachment`` — the ``to_fixed`` attachment kind (``"csv"`` / ``"pdf_labels"``) or ``None``.
    - ``label_options`` — the ``pdf_labels`` options mapping, when the attachment is labels.
    - ``recipient_field`` — the dotted path that resolves a ``per_recipient`` address, defaulting
      to :data:`DEFAULT_RECIPIENT_FIELD` (``personal.email``) — same override seam as a saved block.
    - ``set_id`` — a free-form LABEL (default ``"adhoc"``) folded into the audit + the stable job
      id; NOT a saved-set key (an ad-hoc send has no set).
    """

    mode: str
    result_rows: tuple[Mapping[str, Any], ...] = ()
    recipients: tuple[str, ...] = ()
    template_id: str | None = None
    attachment: str | None = None
    label_options: Mapping[str, Any] | None = None
    recipient_field: str | None = None
    set_id: str = "adhoc"

    def as_delivery(self) -> dict[str, Any]:
        """Project this ad-hoc body into the SAME ``delivery``-mapping shape the fan-out reads.

        The fan-out helpers (``_deliver_per_recipient`` / ``_deliver_to_fixed``) read a
        ``delivery`` mapping (``mode`` / ``recipients`` / ``template_id`` / ``attachment`` /
        ``label_options`` / ``recipient_field``). Projecting the ad-hoc body into that exact shape
        is what lets BOTH routes share ONE send path with ZERO branching in the helpers — the
        helpers never learn whether their ``delivery`` came from a stored set or an ad-hoc compose
        (design "two thin routes, ONE shared send service").
        """
        delivery: dict[str, Any] = {"mode": self.mode}
        if self.recipients:
            delivery["recipients"] = list(self.recipients)
        if self.template_id:
            delivery["template_id"] = self.template_id
        if self.attachment is not None:
            delivery["attachment"] = self.attachment
        if self.label_options is not None:
            delivery["label_options"] = dict(self.label_options)
        if self.recipient_field:
            delivery["recipient_field"] = self.recipient_field
        return delivery


@dataclass(frozen=True)
class DeliveryOutcome:
    """The result of an execute-and-deliver run — what was enqueued, for the route to echo.

    - ``run_id`` — the logical run id (shared by every enqueued job).
    - ``mode`` — the delivery mode that ran.
    - ``enqueued`` — how many jobs were placed on the queue.
    - ``skipped_no_address`` — ``per_recipient`` result rows with no resolvable recipient
      address (they cannot be mailed, so no job is enqueued for them — surfaced, not hidden).
    - ``job_ids`` — the stable ids enqueued (idempotency keys; useful for the route/audit).
    """

    run_id: str
    mode: str
    enqueued: int
    skipped_no_address: int
    job_ids: tuple[str, ...]
