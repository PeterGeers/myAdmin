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
from typing import Any

from sam.members.domain._delivery_models import (
    DEFAULT_RECIPIENT_FIELD,
    AdHocMailBody,
    AdHocMailInvalid,
    DeliveryNotConfigured,
    DeliveryOutcome,
    MailJob,
    MailNotCertified,
    MailQueue,
    PivotRunner,
)
from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
)
from sam.members.domain.mail_sender_resolver import (
    MailSenderResolver,
)
from sam.members.repository.members_repository import MembersRepository

# The value objects, ports, and errors now live in :mod:`._delivery_models` (a clean cohesion
# seam: pure dataclasses / Protocols / exceptions with no resolution logic). They are re-exported
# here VERBATIM so the public import surface ``sam.members.domain.execute_and_deliver`` is
# unchanged — every historical ``from ...execute_and_deliver import <symbol>`` keeps working.
# Only ``ExecuteAndDeliverService`` (the resolution/fan-out logic) is defined below.
__all__ = [
    "DEFAULT_RECIPIENT_FIELD",
    "AdHocMailBody",
    "AdHocMailInvalid",
    "DeliveryNotConfigured",
    "DeliveryOutcome",
    "ExecuteAndDeliverService",
    "MailJob",
    "MailNotCertified",
    "MailQueue",
    "PivotRunner",
]


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
                Reply-To so replies reach the real sender (an INTERACTIVE send). ``None`` for an
                unattended (scheduled) run — the service then resolves the tenant-authored
                ``config#mail.mail_reply_to_default``, falling back to the composed From when none
                is authored (Task 5.1). The From always carries the tenant identity.

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

        # 2b. Reply-To (spec 02 Task 5.1): an INTERACTIVE send passes the triggering user's
        #     verified email as ``reply_to`` (used verbatim). An UNATTENDED/scheduled run passes
        #     no ``reply_to`` — resolve the tenant-authored ``mail_reply_to_default``, falling back
        #     to the composed From when the tenant authored none (never a guessed address).
        if not (isinstance(reply_to, str) and reply_to.strip()):
            reply_to = self._sender.resolve_scheduled_reply_to(tenant_id, from_address)

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
            # A per_recipient send merges a stored template per member — a template is REQUIRED.
            # Fail fast here (no enqueue, no mailrun) so the caller gets a clear 422 instead of a
            # false "sent" that the worker would later dead-letter ("carries no template_id").
            if not getattr(body, "template_id", None):
                raise AdHocMailInvalid(
                    "a template is required for a per-recipient send"
                )
            # A per_recipient fan-out renders each recipient's message from a stored template —
            # it has NO other body source. A template-less per_recipient job is doomed: the
            # worker's _render_per_recipient hard-rejects it ("carries no template_id") and
            # dead-letters it AFTER a 202 "sent" was already returned (a false "sent"). Fail
            # fast here instead so the caller gets a clear 422 before anything is enqueued or any
            # mailrun is recorded. body.template_id is normalized to None-when-blank at the edge
            # (_dispatch.py::_parse_ad_hoc_body), so `not body.template_id` covers None and blank.
            if not body.template_id:
                raise AdHocMailInvalid(
                    "a template is required for a per-recipient send"
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
        template_ref = (
            template_id if isinstance(template_id, str) and template_id else None
        )
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

        # Write the send-run status TALLY at enqueue (R9.1): a `mailrun#<run_id>` row with
        # status=queued + the enqueued recipient count. Idempotent on run_id (a re-enqueue of
        # the same logical run does not reset an already-advanced run). The worker advances it
        # (sending/completed + sent/failed counts). This is what feeds the status/history screen.
        self._repo.create_mail_run(
            tenant_id,
            run_id,
            mode=DELIVERY_MODE_PER_RECIPIENT,
            triggered_by=reply_to or "",
            recipient_count=len(job_ids),
        )

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
        template_ref = (
            template_id if isinstance(template_id, str) and template_id else None
        )

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

        # Write the send-run status TALLY at enqueue (R9.1): one `mailrun#<run_id>` row with
        # status=queued. recipient_count = the fixed-recipient count (the worker sends ONE
        # message to the whole list, but the tally tracks the recipients). Idempotent on run_id.
        self._repo.create_mail_run(
            tenant_id,
            run_id,
            mode=DELIVERY_MODE_TO_FIXED,
            triggered_by=reply_to or "",
            recipient_count=len(recipients),
        )

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
