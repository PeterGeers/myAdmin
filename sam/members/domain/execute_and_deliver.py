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
from sam.members.repository.members_repository import MembersRepository

__all__ = [
    "DEFAULT_RECIPIENT_FIELD",
    "DeliveryNotConfigured",
    "ExecuteAndDeliverService",
    "MailJob",
    "MailQueue",
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
    template_id: str | None = None
    merge_values: Mapping[str, Any] = field(default_factory=dict)
    attachment: Mapping[str, Any] | None = None
    rows: tuple[Mapping[str, Any], ...] = ()


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
    pivot/list computation), and the :class:`MailQueue` port (the enqueue seam). It owns the
    FAN-OUT: ``per_recipient`` → one job per member; ``to_fixed`` → one job. ``tenant_id`` is
    authoritative on every call.
    """

    def __init__(
        self,
        repo: MembersRepository,
        pivot_runner: PivotRunner,
        queue: MailQueue,
    ):
        self._repo = repo
        self._pivot = pivot_runner
        self._queue = queue

    # ── public entry point ────────────────────────────────────────────────────────────

    def execute_and_deliver(
        self, tenant_id: str, set_id: str, run_id: str
    ) -> DeliveryOutcome:
        """Resolve the set, re-fetch rows (tenant-pinned), run the pivot, and enqueue job(s).

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

        Returns:
            A :class:`DeliveryOutcome` describing what was enqueued.
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

        # 2. Re-fetch the member rows FRESH through the repository (tenant pinned — Property 1;
        #    this is list_members keyed by tenant_id, NEVER a .scan()).
        rows = list(self._repo.list_members(tenant_id))

        # 3. Run the pivot/list over the re-fetched rows to get the result rows.
        result_rows = list(self._pivot.run(tenant_id, entry.definition, rows))

        # 4. Fan out into enqueue job(s) per the delivery mode.
        if mode == DELIVERY_MODE_PER_RECIPIENT:
            return self._deliver_per_recipient(
                tenant_id, set_id, run_id, delivery, result_rows
            )
        if mode == DELIVERY_MODE_TO_FIXED:
            return self._deliver_to_fixed(
                tenant_id, set_id, run_id, delivery, result_rows
            )
        # The entity validates the mode at save time, so an unknown mode here is a stored-data
        # fault; refuse it loudly rather than enqueue nothing silently.
        raise DeliveryNotConfigured(tenant_id, set_id)

    # ── per_recipient: one job PER member (merge values + template ref) ─────────────────

    def _deliver_per_recipient(
        self,
        tenant_id: str,
        set_id: str,
        run_id: str,
        delivery: Mapping[str, Any],
        result_rows: Sequence[Mapping[str, Any]],
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
