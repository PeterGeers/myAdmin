"""
The **execute-and-deliver service** (R4, design §4.1/§4.2) — one storage-agnostic
Members-domain component that runs a saved set + its stored ``delivery`` block and
FANS the result OUT into send jobs on a queue PORT.

Why this exists (R4 / design §4)
--------------------------------
R4 asks for ONE server-side component that runs a set and its delivery, so an
interactive ``POST .../deliver`` (task 4.2) and a scheduled run (R5, task 5.3) share a
single send path. That component is this service. It is deliberately NOT the handler
(steering 35 golden rule: the handler is a thin adapter; the business logic lives in a
service) and it is NOT the worker (task 4.3): this service only RESOLVES, RE-FETCHES,
RUNS, BUILDS, and ENQUEUES. The worker drains the queue and talks to SES.

What it does, step by step (design §4.2):

1. **Resolve the set + its delivery block.** Load the ``analyticsset#<set_id>`` entry
   through the repository (tenant pinned — Property 1). A set with NO delivery block
   (the legacy default) cannot be delivered: it raises :class:`DeliveryNotConfigured`.
2. **Re-fetch the member rows through the repository.** The rows are read FRESH at run
   time via :meth:`MembersRepository.list_members` — which takes ``tenant_id`` as its
   first argument and keys the DynamoDB query by that partition (Property 1 — NEVER a
   ``.scan()``). A scheduled/unattended run therefore reflects the data as it stands
   when it fires, and can never cross tenants.
3. **Run the pivot/list** to get the RESULT ROWS. The pivot/list computation is NOT a
   DynamoDB concern and is NOT built in the SAM plane yet, so it is an injected PORT
   (:class:`PivotRunner`) — a Protocol seam. The service hands it the set definition +
   the re-fetched rows and gets back the result rows; a fake runner in tests returns a
   canned shape. (When the real pivot engine lands it satisfies this Protocol; this
   service does not change.)
4. **Build the output and ENQUEUE job(s)** on the injected queue PORT
   (:class:`MailQueue`) — the storage-agnostic seam this task owns. Task 4.2 provides
   the real SQS implementation + the enqueue route; task 4.3 the worker:

   - ``per_recipient`` → **one job PER member** in the result, each carrying THAT
     member's merge values (resolved from its row) + the template ref. The recipient
     ADDRESS is resolved from the dataset row at run time (design §2.1 — a
     ``per_recipient`` delivery stores NO addresses); a row with no resolvable address
     is skipped (it cannot be mailed) and reported in the outcome.
   - ``to_fixed`` → **ONE job** carrying the fixed ``recipients`` list (stored on the
     block) + the attachment descriptor (``csv`` / ``pdf_labels`` + its
     ``label_options``). The attachment itself is rendered by the worker from the
     result rows carried on the job.

Idempotency (design §4.2)
-------------------------
Each job carries a STABLE id so an at-least-once SQS redelivery does not double-send
(the worker, task 4.3, dedupes on it). The id is derived deterministically from the
run identity: ``(tenant_id, set_id, run_id, mode, recipient-or-"fixed")`` hashed — so
the SAME run re-enqueued produces the SAME ids, while two distinct runs (different
``run_id``) never collide. ``run_id`` is supplied by the caller (the deliver route /
the scheduler) so one logical run has one id across a retry of the ENQUEUE itself.

Layering & seams (steering 35)
------------------------------
handler (thin) → THIS service (business logic, storage-agnostic) → ports
(:class:`MembersRepository` for the tenant-pinned re-fetch; :class:`PivotRunner` for
the pivot/list; :class:`MailQueue` for the enqueue). The service names no boto3, no
SQS, no DynamoDB — only the Protocols. ``tenant_id`` is AUTHORITATIVE on every call
(never trusted from a body — verify-before-trust, Property 2).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
)
from sam.members.domain.mail_sender_resolver import (
    MailSenderResolver,
    NotCertifiedReason,
)
from sam.members.repository.members_repository import MembersRepository

__all__ = [
    "DEFAULT_RECIPIENT_FIELD",
    "AdHocMailBody",
    "AdHocMailInvalid",
    "DeliveryNotConfigured",
    "ExecuteAndDeliverService",
    "MailJob",
    "MailQueue",
    "MailNotCertified",
    "PivotRunner",
    "DeliveryOutcome",
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


class ExecuteAndDeliverService:
    """Run a saved set + its delivery block and enqueue the send job(s) (R4, design §4.1/§4.2).

    Storage-agnostic: depends only on the injected :class:`MembersRepository` (the tenant-
    pinned re-fetch — the sole DynamoDB touch-point), the :class:`PivotRunner` port (the
    pivot/list computation), the :class:`MailQueue` port (the enqueue seam), and the
    :class:`~sam.members.domain.mail_sender_resolver.MailSenderResolver` (the SYNCHRONOUS pre-send
    certification gate — mail-spec task 1.3). It owns the FAN-OUT: ``per_recipient`` → one job per
    member; ``to_fixed`` → one job. ``tenant_id`` is authoritative on every call.

    Pre-send certification + sender stamping (mail-spec task 1.3, R4/R5; design "What to CHANGE"
    #1/#4): BEFORE any job is built, the resolver resolves the tenant From
    (``noreply@<tenant-domain>``) or REFUSES with a typed reason. On a refusal the service raises
    :class:`MailNotCertified` and enqueues NOTHING (no send, no substitute sender — Property 2/4).
    On success the resolved From + the triggering user's Reply-To are STAMPED onto EVERY job (both
    modes) so the worker FORWARDS them to SES without re-resolving.

    Two entry points, ONE send path (mail-spec task 2.2; design "two thin routes, ONE shared send
    service"): :meth:`execute_and_deliver` runs a SAVED set + its stored ``delivery`` (resolving +
    re-fetching from the repository), while :meth:`send_ad_hoc` runs an AD-HOC compose body
    (:class:`AdHocMailBody` — current result rows + typed recipients / template / attachment, NO
    stored delivery, NO re-fetch). BOTH converge on the SAME pre-send gate, the SAME fan-out
    helpers (``_deliver_per_recipient`` / ``_deliver_to_fixed``), the SAME :class:`MailJob` shape,
    and the SAME :class:`MailQueue`. The id-vs-no-id branch is WHICH method the thin route calls,
    not a sentinel inside one method — DRY logic, honest routes.
    """

    def __init__(
        self,
        repo: MembersRepository,
        pivot_runner: PivotRunner,
        queue: MailQueue,
        sender_resolver: MailSenderResolver,
    ):
        self._repo = repo
        self._pivot = pivot_runner
        self._queue = queue
        self._sender = sender_resolver

    # ── public entry point ────────────────────────────────────────────────────────────

    def execute_and_deliver(
        self,
        tenant_id: str,
        set_id: str,
        run_id: str,
        reply_to: str | None = None,
    ) -> DeliveryOutcome:
        """Resolve the set, gate on certification, re-fetch rows, run the pivot, and enqueue job(s).

        Args:
            tenant_id: the AUTHORITATIVE tenant (never a body value — Property 1/2). Every
                repository call is keyed by it, so the run can never read or mail another
                tenant's data.
            set_id: the saved set to run. Must exist for the tenant (else
                :class:`~sam.members.domain._membership_errors.AnalyticsSetNotFound`) and must
                carry a ``delivery`` block (else :class:`DeliveryNotConfigured`).
            run_id: the caller's id for ONE logical run (the deliver route / the scheduler
                supplies it). Shared by every job of a fan-out and folded into the stable
                job id, so re-enqueuing the same run is idempotent downstream.
            reply_to: the TRIGGERING USER's verified email (R4.3), stamped onto every job as the
                Reply-To so replies reach the real sender. ``None`` for an unattended (scheduled)
                run with no triggering user — the From still carries the tenant identity.

        Returns:
            A :class:`DeliveryOutcome` describing what was enqueued.

        Raises:
            MailNotCertified: the tenant has no usable verified From (mail disabled / not
                certified / no domain) — refused SYNCHRONOUSLY before any job is enqueued
                (R4.2/R5.2; Property 2/4). Nothing is placed on the queue.
        """
        # 1. Resolve the set + its delivery block (tenant pinned — Property 1).
        entry = self._repo.get_analytics_set(tenant_id, set_id)
        if entry is None:
            # Mirror the sibling CRUD not-found so the edge maps it to a 404.
            from sam.members.domain._membership_errors import AnalyticsSetNotFound

            raise AnalyticsSetNotFound(tenant_id, set_id)

        delivery = entry.delivery
        if not isinstance(delivery, Mapping) or not delivery:
            raise DeliveryNotConfigured(tenant_id, set_id)

        mode = delivery.get("mode")

        # 2. PRE-SEND certification gate (mail-spec task 1.3, R4/R5): resolve the tenant From
        #    SYNCHRONOUSLY before touching the queue. A refusal (mail disabled / not certified /
        #    no domain) raises MailNotCertified carrying the TYPED reason and enqueues NOTHING —
        #    never a substitute sender (R4.2 — the jabaki.nl regression stays dead; Property 2/4).
        resolution = self._sender.resolve(tenant_id)
        if not resolution.ok:
            raise MailNotCertified(tenant_id, set_id, resolution.reason)
        from_address = resolution.from_address

        # 3. Re-fetch the member rows FRESH through the repository (tenant pinned — Property 1;
        #    this is list_members keyed by tenant_id, NEVER a .scan()).
        rows = list(self._repo.list_members(tenant_id))

        # 4. Run the pivot/list over the re-fetched rows to get the result rows.
        result_rows = list(self._pivot.run(tenant_id, entry.definition, rows))

        # 5. Fan out into enqueue job(s) per the delivery mode, STAMPING the resolved From +
        #    the user's Reply-To onto every job (both modes) so the worker forwards them.
        if mode == DELIVERY_MODE_PER_RECIPIENT:
            return self._deliver_per_recipient(
                tenant_id, set_id, run_id, delivery, result_rows, from_address, reply_to
            )
        if mode == DELIVERY_MODE_TO_FIXED:
            return self._deliver_to_fixed(
                tenant_id, set_id, run_id, delivery, result_rows, from_address, reply_to
            )
        # The entity validates the mode at save time, so an unknown mode here is a stored-data
        # fault; refuse it loudly rather than enqueue nothing silently.
        raise DeliveryNotConfigured(tenant_id, set_id)

    # ── ad-hoc send (the SHARED entry for POST /members/mail/send, mail-spec task 2.2) ──

    def send_ad_hoc(
        self,
        tenant_id: str,
        body: AdHocMailBody,
        run_id: str,
        reply_to: str | None = None,
    ) -> DeliveryOutcome:
        """Send an AD-HOC compose (recipients/template/attachment + current rows) — no saved set.

        This is the SIBLING entry to :meth:`execute_and_deliver` and the point of mail-spec task
        2.2: the stateless ``POST /members/mail/send`` route delegates HERE, while the saved-set
        ``.../deliver`` route delegates to :meth:`execute_and_deliver`. BOTH converge on the SAME
        pre-send gate, the SAME fan-out helpers, the SAME :class:`MailJob` shape, and the SAME
        :class:`MailQueue` — ONE send path, two thin routes (design "Resolved implementation
        choices"). The ONLY difference is the INPUT: this takes the compose body + its already-
        computed ``result_rows`` directly, so there is NO set resolution and NO repository
        re-fetch (the ad-hoc compose carries no DynamoDB identity).

        Order of operations (identical gate to the saved path, Property 2/4/6):

        1. Validate the body SHAPE (:class:`AdHocMailInvalid`) — unknown mode, a ``to_fixed`` with
           no recipients, a ``per_recipient`` with no rows. No entity ``validate()`` stands behind
           an ad-hoc body, so this service owns that check.
        2. Run the SAME synchronous pre-send :class:`MailSenderResolver` — refuse with the typed
           :class:`MailNotCertified` BEFORE enqueue if the tenant is not certified (no substitute
           sender, R4.2). Nothing is enqueued on a refusal.
        3. Fan out via the SAME ``_deliver_per_recipient`` / ``_deliver_to_fixed`` helpers,
           STAMPING the resolved tenant From + the user's Reply-To onto every job.

        Args:
            tenant_id: the AUTHORITATIVE active tenant (never a body value — Property 3). The
                pre-send gate reads the projected config for THIS tenant; the stamped From is
                this tenant's ``noreply@<tenant-domain>``.
            body: the ad-hoc compose (:class:`AdHocMailBody`) — mode + result rows + the typed
                recipients / template / attachment.
            run_id: the caller's id for ONE logical run (the edge mints it), folded into every
                job's stable id so an at-least-once redelivery is idempotent.
            reply_to: the triggering user's verified email (R4.3), stamped as the Reply-To.

        Returns:
            A :class:`DeliveryOutcome` describing what was enqueued (same shape as the saved path).

        Raises:
            AdHocMailInvalid: the compose body is malformed (→ 422). Nothing is enqueued.
            MailNotCertified: the tenant has no usable verified From — refused SYNCHRONOUSLY
                before any job is enqueued (R4.2/R5.2; Property 2/4). Nothing is enqueued.
        """
        set_id = body.set_id or "adhoc"

        # 1. Shape-validate the ad-hoc body (no entity validate() stands behind it).
        if body.mode == DELIVERY_MODE_PER_RECIPIENT:
            if not body.result_rows:
                raise AdHocMailInvalid(
                    "per_recipient send carries no result rows to mail"
                )
        elif body.mode == DELIVERY_MODE_TO_FIXED:
            has_recipient = any(
                isinstance(r, str) and r.strip() for r in body.recipients
            )
            if not has_recipient:
                raise AdHocMailInvalid(
                    "to_fixed send requires a non-empty recipients list"
                )
        else:
            raise AdHocMailInvalid(f"unknown delivery mode {body.mode!r}")

        # 2. PRE-SEND certification gate — the SAME resolver, SAME typed refusal as the saved
        #    path (R4.2/R5.2). A refusal raises MailNotCertified and enqueues NOTHING (no
        #    substitute sender — the jabaki.nl regression stays dead; Property 2/4).
        resolution = self._sender.resolve(tenant_id)
        if not resolution.ok:
            raise MailNotCertified(tenant_id, set_id, resolution.reason)
        from_address = resolution.from_address

        # 3. Fan out via the SAME helpers, projecting the body into the delivery shape they read
        #    and passing the body's own (already-computed) result rows — no repository re-fetch.
        delivery = body.as_delivery()
        result_rows = list(body.result_rows)

        if body.mode == DELIVERY_MODE_PER_RECIPIENT:
            return self._deliver_per_recipient(
                tenant_id, set_id, run_id, delivery, result_rows, from_address, reply_to
            )
        return self._deliver_to_fixed(
            tenant_id, set_id, run_id, delivery, result_rows, from_address, reply_to
        )

    # ── per_recipient: one job PER member (merge values + template ref) ─────────────────

    def _deliver_per_recipient(
        self,
        tenant_id: str,
        set_id: str,
        run_id: str,
        delivery: Mapping[str, Any],
        result_rows: Sequence[Mapping[str, Any]],
        from_address: str,
        reply_to: str | None,
    ) -> DeliveryOutcome:
        """Enqueue ONE job per result row, each with that member's merge values + the template.

        The recipient address is resolved FROM the dataset row at run time (design §2.1 — a
        ``per_recipient`` block stores no addresses). The merge values are the row's own fields
        (the worker fills the template's ``{{ merge_field }}`` placeholders from them). A row
        with no resolvable address cannot be mailed, so it is SKIPPED (and counted in the
        outcome) rather than enqueued with no destination.
        """
        template_id = delivery.get("template_id")
        template_ref = template_id if isinstance(template_id, str) and template_id else None
        recipient_field = self._recipient_field(delivery)

        job_ids: list[str] = []
        skipped = 0
        for row in result_rows:
            address = self._resolve_address(row, recipient_field)
            if not address:
                skipped += 1
                continue
            merge_values = self._flatten_merge_values(row)
            job_id = self._stable_job_id(
                tenant_id, set_id, run_id, DELIVERY_MODE_PER_RECIPIENT, address
            )
            job = MailJob(
                job_id=job_id,
                tenant_id=tenant_id,
                set_id=set_id,
                run_id=run_id,
                mode=DELIVERY_MODE_PER_RECIPIENT,
                recipients=(address,),
                from_address=from_address,
                reply_to=reply_to,
                template_id=template_ref,
                merge_values=merge_values,
            )
            self._queue.enqueue(job)
            job_ids.append(job_id)

        return DeliveryOutcome(
            run_id=run_id,
            mode=DELIVERY_MODE_PER_RECIPIENT,
            enqueued=len(job_ids),
            skipped_no_address=skipped,
            job_ids=tuple(job_ids),
        )

    # ── to_fixed: ONE job (fixed recipients + attachment) ───────────────────────────────

    def _deliver_to_fixed(
        self,
        tenant_id: str,
        set_id: str,
        run_id: str,
        delivery: Mapping[str, Any],
        result_rows: Sequence[Mapping[str, Any]],
        from_address: str,
        reply_to: str | None,
    ) -> DeliveryOutcome:
        """Enqueue ONE job carrying the fixed recipients + the attachment descriptor.

        The whole result is sent as a single attachment to the stored ``recipients`` list
        (often one address). The worker (task 4.3) builds the attachment (``csv`` /
        ``pdf_labels`` with its ``label_options``) from the ``rows`` carried on the job, so the
        result is captured once here and shipped on the single job. The optional ``template_id``
        is the covering-mail body ref.
        """
        recipients = tuple(
            str(r).strip()
            for r in (delivery.get("recipients") or [])
            if isinstance(r, str) and r.strip()
        )
        # The entity's validate() already guarantees a non-empty recipients list for to_fixed,
        # so an empty tuple here would be a stored-data fault — treat it as nothing to send.
        if not recipients:
            raise DeliveryNotConfigured(tenant_id, set_id)

        template_id = delivery.get("template_id")
        template_ref = template_id if isinstance(template_id, str) and template_id else None

        attachment_kind = delivery.get("attachment")
        attachment: dict[str, Any] | None = None
        if attachment_kind is not None:
            label_options = delivery.get("label_options")
            attachment = {
                "kind": attachment_kind,
                "label_options": dict(label_options)
                if isinstance(label_options, Mapping)
                else None,
            }

        job_id = self._stable_job_id(
            tenant_id, set_id, run_id, DELIVERY_MODE_TO_FIXED, "fixed"
        )
        job = MailJob(
            job_id=job_id,
            tenant_id=tenant_id,
            set_id=set_id,
            run_id=run_id,
            mode=DELIVERY_MODE_TO_FIXED,
            recipients=recipients,
            from_address=from_address,
            reply_to=reply_to,
            template_id=template_ref,
            attachment=attachment,
            rows=tuple(dict(r) for r in result_rows),
        )
        self._queue.enqueue(job)

        return DeliveryOutcome(
            run_id=run_id,
            mode=DELIVERY_MODE_TO_FIXED,
            enqueued=1,
            skipped_no_address=0,
            job_ids=(job_id,),
        )

    # ── helpers ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _recipient_field(delivery: Mapping[str, Any]) -> str:
        """The dotted path that resolves a ``per_recipient`` address, defaulting to the member email.

        A delivery block MAY name an alternate contact column via ``recipient_field``; otherwise
        the canonical :data:`DEFAULT_RECIPIENT_FIELD` (``personal.email``) is used. The address
        is always resolved FROM the dataset row at run time — never stored on the block.
        """
        field_path = delivery.get("recipient_field")
        if isinstance(field_path, str) and field_path.strip():
            return field_path.strip()
        return DEFAULT_RECIPIENT_FIELD

    @staticmethod
    def _resolve_address(row: Mapping[str, Any], field_path: str) -> str:
        """Resolve a recipient address from a result row by a dotted ``field_path``.

        Walks ``a.b.c`` into nested mappings (so ``personal.email`` reaches
        ``row["personal"]["email"]``), and also accepts the dotted key stored FLAT on the row
        (``row["personal.email"]``) since a pivot result row may already be flattened. Returns
        the stripped address string, or ``""`` when absent/blank/non-string (an unmailable row).
        """
        # Flat dotted key first (a flattened result row).
        flat = row.get(field_path)
        if isinstance(flat, str) and flat.strip():
            return flat.strip()

        # Otherwise walk the dotted path into nested mappings.
        current: Any = row
        for segment in field_path.split("."):
            if not isinstance(current, Mapping):
                return ""
            current = current.get(segment)
        return current.strip() if isinstance(current, str) and current.strip() else ""

    @staticmethod
    def _flatten_merge_values(row: Mapping[str, Any]) -> dict[str, Any]:
        """Flatten a result row into a ``{merge_key: value}`` map for the mail-merge.

        The worker fills the template's ``{{ merge_field }}`` placeholders from this map. Both
        the top-level keys and the dotted paths into one level of nested mappings are exposed
        (so a template can reference either ``first_name`` or ``personal.email``), scalars only
        — nested mappings themselves are not injected as placeholder values. First-level only
        keeps the merge surface predictable (templates reference leaf fields).
        """
        merged: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, Mapping):
                for sub_key, sub_value in value.items():
                    if not isinstance(sub_value, Mapping):
                        merged[f"{key}.{sub_key}"] = sub_value
                        # Also expose the bare leaf key when it does not collide, so a template
                        # may reference `first_name` rather than `personal.first_name`.
                        merged.setdefault(str(sub_key), sub_value)
            else:
                merged[str(key)] = value
        return merged

    @staticmethod
    def _stable_job_id(
        tenant_id: str, set_id: str, run_id: str, mode: str, recipient: str
    ) -> str:
        """Derive the STABLE idempotency job id (design §4.2) from the run identity.

        Deterministic: the SAME ``(tenant_id, set_id, run_id, mode, recipient)`` always hashes
        to the SAME id, so an at-least-once SQS redelivery of a job carries the same id and the
        worker (task 4.3) dedupes it. Two distinct runs (different ``run_id``) — or two
        different recipients of one ``per_recipient`` run — never collide. A short SHA-256 hex
        digest keeps the id opaque, fixed-length, and safe as an SQS/DynamoDB key. The parts are
        length-prefixed before hashing so no two different tuples can alias by concatenation.
        """
        parts = (tenant_id, set_id, run_id, mode, recipient)
        payload = "\x00".join(f"{len(p)}:{p}" for p in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
