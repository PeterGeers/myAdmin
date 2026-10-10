"""
Members Lambda edge — route dispatch (extracted from ``app`` for cohesion).

The per-route delegation to the generic membership engine (design C2). The edge stays
**thin**: for each resolved route it hands the domain service the verified ``tenant_id``
(isolation, Property 1), the resolved per-dimension ``allowed_scopes`` map (domain-layer
scope filtering, design C4 / Property 4/6), the requester ``sub`` + ``self_service`` flag,
and the router's path params. No scope math, no field resolution, no DynamoDB here.

Re-exported from :mod:`sam.members.handler.app`; its public import surface is unchanged.
In particular :class:`RouteNotImplemented` and the small body-reading helpers remain
importable from ``app``. The facade keeps a thin ``_dispatch(spec, request, ctx)`` wrapper
that resolves the module-global service (via the patchable ``app._get_membership_service``)
and delegates to :func:`dispatch_route` here — so the test monkeypatch seams
(``app._dispatch`` / ``app._get_membership_service``) are preserved. Pure structural split
(code-quality M2) with zero behaviour change.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sam.members.domain.execute_and_deliver import AdHocMailBody
from sam.members.domain.fixed_fields import MembershipStatus
from sam.members.domain.membership_service import (
    MemberValidationError,
)
from sam.members.handler._http import AcceptedResult, ParsedRequest
from sam.members.handler.routes import CAP_MEMBERS_ADMIN, RouteSpec
from sam.shared.auth_utils import has_capability

if (
    TYPE_CHECKING
):  # pragma: no cover - typing only, avoids an app<->_dispatch import cycle
    from sam.members.domain.membership_service import MembershipService
    from sam.members.domain.template_service import TemplateService
    from sam.members.handler.app import RequestContext


# ── Template service seam (R2 — pivot-output-actions task 2.3) ─────────────────────────
#
# The template CRUD routes are backed by the standalone
# :class:`~sam.members.domain.template_service.TemplateService` (not the MembershipService).
# It is resolved lazily once (warm-reuse) over the production repository (which structurally
# satisfies the service's metadata-store port) + the S3-backed body store, mirroring
# :func:`sam.members.handler.app._get_membership_service`. A test replaces :data:`_TEMPLATE_SERVICE`
# (or patches :func:`get_template_service`) with a service over in-memory fakes, so no AWS is
# touched. Kept HERE (not on the ``app`` facade) because the template dispatch lives here; the
# accessor is module-global so warm invocations reuse one service.

#: The module-global template service, built once at cold start (``None`` until first use).
_TEMPLATE_SERVICE: TemplateService | None = None


def get_template_service() -> TemplateService:
    """Return the module-global :class:`TemplateService`, building it once at cold start.

    Wires the template service (R2) over the tenant-scoped
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` (its four
    ``*_template`` methods structurally satisfy the service's ``TemplateMetadataStore`` port)
    and the S3-backed
    :class:`~sam.members.repository.template_body_store.S3TemplateBodyStore`. Both the table and
    the bucket resolve lazily + fail-fast on first use, so importing the module (and the
    auth-only tests) never touches AWS. Tests patch this accessor (or set ``_TEMPLATE_SERVICE``)
    to inject a service over in-memory fakes.
    """
    global _TEMPLATE_SERVICE
    if _TEMPLATE_SERVICE is None:
        from sam.members.domain.template_service import TemplateService
        from sam.members.repository.members_repository import DynamoDbMembersRepository
        from sam.members.repository.template_body_store import S3TemplateBodyStore

        _TEMPLATE_SERVICE = TemplateService(
            DynamoDbMembersRepository(), S3TemplateBodyStore()
        )
    return _TEMPLATE_SERVICE


# ── Execute-and-deliver service seam (R4 — pivot-output-actions task 4.2) ──────────────
#
# The `deliver` route (`POST /members/analytics-sets/{set_id}/deliver`) is backed by the
# standalone :class:`~sam.members.domain.execute_and_deliver.ExecuteAndDeliverService` (task
# 4.1 — NOT the MembershipService). It is resolved lazily once (warm-reuse), mirroring
# :func:`get_template_service` / :func:`app._get_membership_service`. A test replaces
# :data:`_EXECUTE_AND_DELIVER_SERVICE` (or patches :func:`get_execute_and_deliver_service`) with
# a service over an in-memory fake repo + a FAKE queue, so no AWS/SQS is touched. Kept HERE (not
# on the ``app`` facade) because the deliver dispatch lives here; the accessor is module-global
# so warm invocations reuse one service.
#
# The task-4.1 service takes THREE injected ports — ``(repo, pivot_runner, queue)`` — and the
# ``MailQueue`` port it enqueues through is ``enqueue(MailJob) -> None``. Two thin production
# shims bridge that service to this stack's existing adapters:
#   * ``_PassThroughPivotRunner`` — the pivot/list engine is not built on the SAM plane yet
#     (design §4.2: today the pivot runs frontend/Flask-side), so the production runner passes
#     the re-fetched member rows through as the result rows. It satisfies the service's
#     ``PivotRunner`` Protocol; when the real engine lands it drops in unchanged.
#   * ``_SqsMailQueueAdapter`` — the production ``SqsMailSendQueue`` enqueues a plain JSON
#     mapping (``enqueue(Mapping) -> str``); the service hands it a frozen ``MailJob`` and
#     expects ``enqueue(MailJob) -> None``. This adapter converts the job to the JSON send-job
#     envelope the worker (task 4.3) consumes and forwards it, satisfying the ``MailQueue`` port.

#: The module-global execute-and-deliver service, built once at cold start (``None`` until first use).
_EXECUTE_AND_DELIVER_SERVICE: Any = None


class _PassThroughPivotRunner:
    """Production ``PivotRunner`` shim — returns the re-fetched member rows as the result rows.

    The pivot/list computation is not yet built on the SAM plane (design §4.2 — it runs
    frontend/Flask-side today), but the ``deliver`` route must still resolve the set, re-fetch
    the tenant's rows, and fan them out into send jobs. For both delivery modes the result rows
    ARE the member rows (``per_recipient`` mails each; ``to_fixed`` attaches the set), so a
    faithful pass-through is the honest interim runner. It satisfies the service's ``PivotRunner``
    Protocol, so when the real pivot engine lands it replaces this shim with no service change.
    """

    def run(self, tenant_id: str, definition: Mapping[str, Any], rows: Any) -> list[Any]:
        return list(rows)


class _SqsMailQueueAdapter:
    """Bridge the task-4.1 ``MailQueue`` port (``enqueue(MailJob)``) onto ``SqsMailSendQueue``.

    The service builds frozen :class:`~sam.members.domain.execute_and_deliver.MailJob` records
    and enqueues them through the ``MailQueue`` Protocol (``enqueue(job) -> None``). The
    production :class:`~sam.members.repository.mail_send_queue.SqsMailSendQueue` instead takes a
    plain JSON-serializable mapping (``enqueue(Mapping) -> str``) — the send-job envelope the
    worker (task 4.3) consumes. This adapter flattens a ``MailJob`` into that envelope and
    forwards it, so the domain service stays storage-agnostic and the SQS adapter stays
    shape-agnostic (neither learns about the other).
    """

    def __init__(self, sqs_queue: Any):
        self._queue = sqs_queue

    def enqueue(self, job: Any) -> None:
        self._queue.enqueue(_mail_job_to_envelope(job))


def _mail_job_to_envelope(job: Any) -> dict[str, Any]:
    """Flatten a frozen ``MailJob`` into the JSON send-job envelope the worker consumes (task 4.3)."""
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "set_id": job.set_id,
        "run_id": job.run_id,
        "mode": job.mode,
        "recipients": list(job.recipients),
        # The resolved tenant From + the user's Reply-To, stamped at enqueue (mail-spec task 1.3)
        # — the worker FORWARDS them to SES without re-resolving (Property 2).
        "from_address": job.from_address,
        "reply_to": job.reply_to,
        "template_id": job.template_id,
        "merge_values": dict(job.merge_values),
        "attachment": dict(job.attachment) if job.attachment is not None else None,
        "rows": [dict(r) for r in job.rows],
    }


def get_execute_and_deliver_service() -> Any:
    """Return the module-global execute-and-deliver service, building it once at cold start (R4).

    Wires the task-4.1 service over its THREE ports:
      * the tenant-scoped :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository`
        (its ``get_analytics_set`` + ``list_members`` pin ``tenant_id`` — Property 1);
      * :class:`_PassThroughPivotRunner` (the interim production pivot runner — design §4.2);
      * :class:`_SqsMailQueueAdapter` over the SQS-backed
        :class:`~sam.members.repository.mail_send_queue.SqsMailSendQueue`.

    The table and the queue resolve lazily + fail-fast on first use, so importing the module
    (and the auth-only tests) never touches AWS. Tests patch this accessor (or set
    ``_EXECUTE_AND_DELIVER_SERVICE``) to inject a service over an in-memory fake repo + a fake
    queue.
    """
    global _EXECUTE_AND_DELIVER_SERVICE
    if _EXECUTE_AND_DELIVER_SERVICE is None:
        from sam.members.domain.execute_and_deliver import ExecuteAndDeliverService
        from sam.members.domain.mail_sender_resolver import MailSenderResolver
        from sam.members.repository.mail_send_queue import SqsMailSendQueue
        from sam.members.repository.members_repository import DynamoDbMembersRepository
        from sam.members.repository.projection_config_reader import (
            MembersProjectionReader,
        )

        # The pre-send certification resolver reads the PROJECTED config#mail flags (Option B —
        # no live SES call on the send path); MembersProjectionReader satisfies its
        # MailConfigReader seam by duck-typing. The table resolves lazily + fail-fast on first use.
        _EXECUTE_AND_DELIVER_SERVICE = ExecuteAndDeliverService(
            DynamoDbMembersRepository(),
            _PassThroughPivotRunner(),
            _SqsMailQueueAdapter(SqsMailSendQueue()),
            MailSenderResolver(MembersProjectionReader()),
        )
    return _EXECUTE_AND_DELIVER_SERVICE


# ── Send-run status read service seam (R9 — mail-spec task 3.2) ───────────────────────
#
# The two mail-run READ routes (`GET /members/mail-runs[/{run_id}]`) are backed by the
# standalone :class:`~sam.members.domain.mail_run_status.MailRunStatusService` (NOT the
# MembershipService) over the tenant-pinned repository's task-3.1 read methods
# (`list_mail_runs` / `get_mail_run` / `list_mail_run_failures`). It is resolved lazily once
# (warm-reuse), mirroring :func:`get_template_service` / :func:`get_execute_and_deliver_service`.
# A test replaces :data:`_MAIL_RUN_STATUS_SERVICE` (or patches :func:`get_mail_run_status_service`)
# with a service over an in-memory fake repo, so no AWS is touched. The user-vs-admin SCOPING
# (R9.3) is resolved HERE in the dispatch (from the verified sub + the members:admin entitlement)
# and handed to the service as a plain boolean — the service holds the scope rule, the edge holds
# the auth fact (verify-before-trust).

#: The module-global mail-run status service, built once at cold start (``None`` until first use).
_MAIL_RUN_STATUS_SERVICE: Any = None


class MailRunNotFound(Exception):
    """Raised when a requested send-run is not visible to the caller (→ 404).

    Either the run does not exist in the tenant, OR it exists but was triggered by ANOTHER
    user and the caller is not a Tenant_Admin (R9.3). The two cases are deliberately
    INDISTINGUISHABLE — a non-admin cannot tell "no such run" apart from "someone else's run",
    so a scoped caller cannot probe for another user's runs (mirrors the member-read 404
    not-found policy). The edge maps this to a 404.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"mail run '{run_id}' not found or not visible")


def get_mail_run_status_service() -> Any:
    """Return the module-global mail-run status service, building it once at cold start (R9).

    Wires the task-3.2 :class:`~sam.members.domain.mail_run_status.MailRunStatusService` over
    the tenant-scoped
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` (its
    ``list_mail_runs`` / ``get_mail_run`` / ``list_mail_run_failures`` pin ``tenant_id`` —
    Property 3). The table resolves lazily + fail-fast on first use, so importing the module
    (and the auth-only tests) never touches AWS. Tests patch this accessor (or set
    ``_MAIL_RUN_STATUS_SERVICE``) to inject a service over an in-memory fake repo.
    """
    global _MAIL_RUN_STATUS_SERVICE
    if _MAIL_RUN_STATUS_SERVICE is None:
        from sam.members.domain.mail_run_status import MailRunStatusService
        from sam.members.repository.members_repository import DynamoDbMembersRepository

        _MAIL_RUN_STATUS_SERVICE = MailRunStatusService(DynamoDbMembersRepository())
    return _MAIL_RUN_STATUS_SERVICE


def _caller_is_tenant_admin(ctx: RequestContext) -> bool:
    """True when the verified caller holds ``members:admin`` for the active tenant (R9.3).

    The R9.3 scope decision — a plain user sees only their OWN sends, a Tenant_Admin sees ALL
    the tenant's — is an AUTHORIZATION fact, so it derives from the VERIFIED entitlement, never
    a header/body (verify-before-trust, Property 3). Uses the three-state
    :func:`~sam.shared.auth_utils.has_capability`: only an authoritative ``True`` grant counts
    as admin; a ``False`` (token-backed denial) or ``None`` (the token does not answer) both
    resolve to NOT-admin, so the caller is scoped to their own sends — fail-closed to the
    narrower view, never a silent widening to the whole tenant.
    """
    return has_capability(ctx.claims, ctx.tenant_id, CAP_MEMBERS_ADMIN) is True


def _mail_run_to_dict(run: Mapping[str, Any]) -> dict[str, Any]:
    """Shape a stored ``mailrun#`` tally into the JSON the status screen renders.

    Drops the DynamoDB plumbing keys (the partition/sort key + the ``ttl`` epoch) that are
    storage detail, not status the SPA needs, and passes the status fields through. The edge's
    JSON encoder already turns DynamoDB ``Decimal`` counts into ints, so the tally's numeric
    ``recipient_count`` / ``sent`` / ``failed`` serialize cleanly.
    """
    drop = {"tenant_id", "sk", "ttl"}
    return {k: v for k, v in run.items() if k not in drop}


def _mail_failure_to_dict(failure: Mapping[str, Any]) -> dict[str, Any]:
    """Shape a stored ``mailrecipient#`` FAILURE sub-record into the drill-down JSON.

    Drops the DynamoDB plumbing keys (partition/sort key + ``ttl``), surfacing the per-failure
    fields the screen shows — ``address`` / ``status`` / ``reason`` / ``message_id`` — as
    metadata only (never member PII beyond the mailed address).
    """
    drop = {"tenant_id", "sk", "ttl"}
    return {k: v for k, v in failure.items() if k not in drop}


def _new_run_id(tenant_id: str, set_id: str, requested_by: str | None) -> str:
    """Mint a ``run_id`` for one interactive deliver run (audit attribution + idempotency, R4).

    The service folds ``run_id`` into every job's stable idempotency id (design §4.2), so one
    logical run gets one id across the whole fan-out while two distinct runs never collide. For
    the interactive route each click is a fresh run, so the id combines the set, the verified
    caller (``requested_by`` — attribution, never a gate), and a UTC timestamp. The scheduler
    (R5, task 5.3) supplies its own run id the same way.
    """
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    who = requested_by or "anon"
    return f"deliver:{set_id}:{who}:{stamp}"


def _verified_email(ctx: RequestContext) -> str | None:
    """The triggering user's VERIFIED email (the mail Reply-To, R4.3) — from the JWT claims only.

    The Reply-To is the logged-in user's address so replies reach the real sender (R4.3). It is
    read from the VERIFIED token claims (``email``) the edge already decoded — never a header or
    body value (verify-before-trust, Property 3). Returns ``None`` when the token carries no email
    claim; the send still proceeds (the From carries the tenant identity) with no Reply-To, rather
    than guessing one.
    """
    email = ctx.claims.get("email") if isinstance(ctx.claims, Mapping) else None
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


def _delivery_outcome_to_dict(outcome: Any) -> dict[str, Any]:
    """Shape the service's frozen ``DeliveryOutcome`` into the JSON receipt the 202 echoes.

    The edge's JSON encoder (``_http._json_default``) only knows how to serialize Decimals, so
    the dataclass is flattened here into a plain mapping — the enqueued-send receipt (how many
    jobs went on the queue, how many rows were skipped for want of an address, the stable job
    ids) the SPA can surface after a deliver.
    """
    return {
        "run_id": outcome.run_id,
        "mode": outcome.mode,
        "enqueued": outcome.enqueued,
        "skipped_no_address": outcome.skipped_no_address,
        "job_ids": list(outcome.job_ids),
    }


def _str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a JSON array value into a tuple of strings (empty when absent/not a list).

    The ad-hoc body's ``recipients`` is a JSON array of addresses. API Gateway hands the body
    through as parsed JSON, so a well-formed array is already a ``list``; a missing / non-list
    value normalises to an empty tuple so the SERVICE'S shape validation surfaces the "to_fixed
    requires recipients" 422 (:class:`AdHocMailInvalid`) rather than the edge guessing. Non-str
    entries are dropped (the service's ``to_fixed`` guard already treats blank/absent as "no
    recipient").
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(v for v in value if isinstance(v, str))


def _row_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Coerce the body's ``result_rows`` JSON array into a tuple of row mappings.

    The compose ships its CURRENT result rows (already computed client/pivot-side) on the body;
    each row is a JSON object. A missing / non-list value normalises to an empty tuple so the
    service's ``per_recipient`` guard surfaces the "no result rows to mail" 422; non-object
    entries are dropped (a row that is not a mapping carries no resolvable address or merge
    values anyway).
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(r for r in value if isinstance(r, Mapping))


def _parse_ad_hoc_body(request: ParsedRequest) -> AdHocMailBody:
    """Parse the ad-hoc send request body into an :class:`AdHocMailBody` (SHAPE only, R2).

    The thin edge's whole job here is to lift the JSON compose body into the frozen
    :class:`~sam.members.domain.execute_and_deliver.AdHocMailBody` the service consumes — it
    does NOT validate it. The AUTHORITATIVE shape validation (unknown ``mode``, a ``to_fixed``
    with no recipients, a ``per_recipient`` with no rows) lives in
    :meth:`ExecuteAndDeliverService.send_ad_hoc` (raising :class:`AdHocMailInvalid` → 422 at the
    edge), so a malformed body is surfaced by the service, never guessed here (verify-before-
    trust: the handler never enriches the body; ``tenant_id`` + Reply-To are stamped by the
    dispatch from the VERIFIED context, never read off the body).

    A missing / non-object body normalises to an empty mapping, so an absent ``mode`` flows
    through as ``None`` and the service rejects it with the "unknown delivery mode" 422 — the
    honest "the body is malformed" answer rather than a silent no-op. ``set_id`` is a free-form
    audit LABEL (default ``"adhoc"``), NOT a saved-set key.
    """
    body = request.body if isinstance(request.body, Mapping) else {}

    attachment = body.get("attachment")
    label_options = body.get("label_options")
    recipient_field = body.get("recipient_field")
    template_id = body.get("template_id")
    set_id = body.get("set_id")

    return AdHocMailBody(
        mode=body.get("mode"),
        result_rows=_row_tuple(body.get("result_rows")),
        recipients=_str_tuple(body.get("recipients")),
        template_id=template_id if isinstance(template_id, str) and template_id else None,
        attachment=attachment if isinstance(attachment, str) and attachment else None,
        label_options=label_options if isinstance(label_options, Mapping) else None,
        recipient_field=(
            recipient_field
            if isinstance(recipient_field, str) and recipient_field
            else None
        ),
        set_id=set_id if isinstance(set_id, str) and set_id else "adhoc",
    )


class RouteNotImplemented(NotImplementedError):
    """Raised by the (stubbed) domain dispatch for a route whose behaviour is pending.

    The route exists in the map and resolved correctly; its domain implementation is a
    later Step-1/Step-3/Step-5 task. The edge maps this to ``501 Not Implemented`` so a
    caller can tell "route not built yet" apart from "no such route" (404).
    """

    def __init__(self, route_name: str):
        self.route_name = route_name
        super().__init__(f"route '{route_name}' is not implemented yet")


def _require_path_param(ctx: RequestContext, name: str) -> str:
    """Return a required path parameter, or raise :class:`RouteNotImplemented`-free 400-ish.

    The router only matches a route when its ``{param}`` segments are present, so a resolved
    READ route always carries its ids; this guard is defensive (a mis-wired route would
    surface loudly rather than silently reading the wrong member).
    """
    value = ctx.path_params.get(name)
    if not value:
        raise KeyError(name)
    return value


def _query_flag(query: Mapping[str, Any], name: str) -> bool:
    """Read a boolean query-string flag, tolerant of the usual truthy spellings.

    API Gateway hands query params as strings (or ``None`` when absent). ``true`` / ``1`` /
    ``yes`` / ``on`` (any case) read as ``True``; anything else (incl. a missing param) reads
    as ``False`` — so the flag defaults off, which for the catalog list means "management
    view: return ALL entries" unless the caller explicitly asks ``?active_only=true``.
    """
    raw = query.get(name) if isinstance(query, Mapping) else None
    if raw is None:
        return False
    return str(raw).strip().lower() in {"true", "1", "yes", "on"}


def _write_body(request: ParsedRequest) -> Mapping[str, Any]:
    """The parsed request body for a WRITE route, as a mapping (empty when absent/non-JSON).

    Write routes carry a JSON object body; a missing or non-object body is normalised to an
    empty mapping so the domain layer's authoritative validation surfaces the "required
    field" errors (a 422), rather than the handler guessing. The handler never enriches the
    body — the domain stamps the verified ``tenant_id`` itself (verify-before-trust).
    """
    body = request.body
    return body if isinstance(body, Mapping) else {}


def _parse_to_state(body: Mapping[str, Any]) -> MembershipStatus:
    """Read the requested target lifecycle state from a transition request body → enum.

    The transition routes carry ``{"to_state": "active", ...}`` (or ``"to"``). An absent or
    unrecognised state is a client error the edge maps to a 422 (:class:`MemberValidationError`)
    — the domain never guesses a target state.
    """
    raw = None
    if isinstance(body, Mapping):
        raw = body.get("to_state") or body.get("to")
    try:
        return MembershipStatus(raw)
    except (ValueError, TypeError):
        raise MemberValidationError(
            {"to_state": f"a valid target lifecycle state is required (got {raw!r})"}
        )


def _transition_context(body: Mapping[str, Any]) -> Mapping[str, Any]:
    """The declarative transition context (guard facts) from a transition request body.

    The lifecycle guards may read ``context.*`` facts threaded in at call time (e.g. h-dcn's
    ``context.approved`` approval flag). We pass through the body's ``context`` object when
    present, else an empty mapping — the guards treat missing facts as absent (deny where a
    guard requires the fact).
    """
    if isinstance(body, Mapping):
        ctx = body.get("context")
        if isinstance(ctx, Mapping):
            return ctx
    return {}


# The READ routes task 3.2 implements, dispatched by their stable route ``name``; the WRITE
# routes (create/update/delete/transition/delegates) are wired by task 5.2/5.3. Anything not
# wired falls through to :class:`RouteNotImplemented`.
def dispatch_route(
    service: MembershipService,
    spec: RouteSpec,
    request: ParsedRequest,
    ctx: RequestContext,
) -> Any:
    """Delegate a resolved route to the generic membership engine (design C2).

    Wires the **READ** routes end-to-end: the edge hands the domain service the verified
    ``tenant_id`` (isolation, Property 1), the resolved per-dimension ``allowed_scopes`` map
    (domain-layer scope filtering, design C4 / Property 4/6; s5d task 4.2 iterates it
    AND-across-dimensions, so no gating dimension is threaded), the requester ``sub`` and the
    route's ``self_service`` flag (so a member can read their OWN record), and the router's
    path params (``{member_id}`` / ``{membership_id}``). The handler stays thin — no scope
    math, no field resolution, no DynamoDB here.

    The caller (``app._dispatch``) supplies ``service`` from the module-global
    ``app._get_membership_service`` so the test seam that patches that accessor is preserved.
    Anything not wired below raises :class:`RouteNotImplemented` (→ 501).
    """
    tenant_id = ctx.tenant_id
    scopes = ctx.allowed_scopes

    name = spec.name

    # ── Group MEMBER (reads) ──────────────────────────────────────────────────────────
    if name == "list_members":
        return service.list_members(tenant_id, scopes)

    if name == "list_members_filtered":
        filters = request.body if isinstance(request.body, Mapping) else None
        return service.list_members(tenant_id, scopes, filters=filters)

    if name == "export_members":
        return service.export_members(tenant_id, scopes)

    if name == "get_self":
        # Pure self-service (capability None): only ever the caller's own record.
        return service.get_self(tenant_id, ctx.sub)

    if name == "get_field_config":
        # The resolved field config (fixed ⊕ overlay) + the tenant's ACTIVE membership-type
        # catalog as the membership_type dropdown options. Tenant-scoped by the verified
        # tenant_id (never a client-supplied tenant); the frontend renders it, enforces
        # nothing (R2.3/R2.4, design C3/C8).
        return service.get_field_config(tenant_id)

    if name == "get_member":
        member_id = _require_path_param(ctx, "member_id")
        return service.get_member(
            tenant_id,
            member_id,
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
        )

    # ── Group MEMBERSHIP (reads) ────────────────────────────────────────────────────
    if name == "list_memberships":
        member_id = _require_path_param(ctx, "member_id")
        return service.list_memberships(
            tenant_id,
            member_id,
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
        )

    if name == "get_membership":
        member_id = _require_path_param(ctx, "member_id")
        membership_id = _require_path_param(ctx, "membership_id")
        return service.get_membership(
            tenant_id,
            member_id,
            membership_id,
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
        )

    # ── Group PAYMENT (read) ──────────────────────────────────────────────────────────
    if name == "get_member_payments":
        member_id = _require_path_param(ctx, "member_id")
        return service.get_member_payments(
            tenant_id,
            member_id,
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
        )

    # ── Group CATALOG (Lidmaatschap Beheer reads, design C8 — task 3.4) ─────────────
    if name == "list_membership_types":
        # Management view defaults to ALL entries (incl. retired active=false); an explicit
        # ``?active_only=true`` narrows to the assignable ones. Tenant-scoped by the verified
        # tenant_id (never a client-supplied tenant); the catalog is not scope-partitioned.
        active_only = _query_flag(request.query, "active_only")
        return service.list_membership_types(tenant_id, active_only=active_only)

    if name == "get_membership_type":
        type_code = _require_path_param(ctx, "type_code")
        return service.get_membership_type(tenant_id, type_code)

    # ── Group ANALYTICS (member analytics-sets, F-012) ──────────────────────────────
    if name == "create_analytics_set":
        # Create a (tenant-shared) saved set; tenant-scoped by the verified tenant_id (never a
        # body tenant_id — verify-before-trust). set_id is server-generated. Empty group/measures
        # is first-class. created_by = the verified caller sub (R11.3 attribution; user ≠ member,
        # R11.1) — passed from the edge, never trusted from the body.
        return service.create_analytics_set(
            tenant_id, _write_body(request), created_by=ctx.sub
        )

    if name == "list_analytics_sets":
        return service.list_analytics_sets(tenant_id)

    if name == "get_analytics_set":
        set_id = _require_path_param(ctx, "set_id")
        return service.get_analytics_set(tenant_id, set_id)

    if name == "update_analytics_set":
        set_id = _require_path_param(ctx, "set_id")
        return service.update_analytics_set(tenant_id, set_id, _write_body(request))

    if name == "delete_analytics_set":
        set_id = _require_path_param(ctx, "set_id")
        return service.delete_analytics_set(tenant_id, set_id)

    if name == "set_analytics_set_delivery":
        # Set/replace a saved set's stored delivery block (R3). The request body IS the
        # delivery block; `tenant_id` + the path `set_id` are authoritative (never the body —
        # verify-before-trust). The service re-validates the whole entry, so a malformed block
        # surfaces the entity's FieldError array (→ 422) and an absent set is a 404. Gate =
        # the route's members:export + existing scope (no new permission, no audit-on-save).
        set_id = _require_path_param(ctx, "set_id")
        return service.set_analytics_set_delivery(
            tenant_id, set_id, _write_body(request)
        )

    if name == "clear_analytics_set_delivery":
        # Clear a saved set's stored delivery block (back to None, R3). 404 for an absent set.
        set_id = _require_path_param(ctx, "set_id")
        return service.clear_analytics_set_delivery(tenant_id, set_id)

    # ── Group ANALYTICS (schedules — R5, pivot-output-actions task 5.2) ──────────────
    #
    # Tenant-scoped recurring runs of a saved set + delivery. Backed by the MembershipService
    # (the SchedulesMixin) over the repository's schedule CRUD (task 5.1). `tenant_id` is
    # authoritative + PINNED from the verified context (never a body); `created_by` is the
    # verified caller sub (attribution only — the R5 gate is enforced at the edge). The service
    # raises ScheduleNotFound (→ 404) and DeliveryNotConfigured (→ 422, when the referenced set
    # has no delivery block). The GATE (members:admin OR members:write + ['*'] all-regions) runs
    # at the edge BEFORE dispatch — a region-narrowed CRUD caller never reaches here.
    if name == "create_schedule":
        return service.create_schedule(
            tenant_id, _write_body(request), created_by=ctx.sub
        )

    if name == "list_schedules":
        return service.list_schedules(tenant_id)

    if name == "get_schedule":
        schedule_id = _require_path_param(ctx, "schedule_id")
        return service.get_schedule(tenant_id, schedule_id)

    if name == "update_schedule":
        schedule_id = _require_path_param(ctx, "schedule_id")
        return service.update_schedule(tenant_id, schedule_id, _write_body(request))

    if name == "delete_schedule":
        schedule_id = _require_path_param(ctx, "schedule_id")
        return service.delete_schedule(tenant_id, schedule_id)

    if name == "deliver_analytics_set":
        # Run a saved set's stored delivery NOW (R4) — the THIN enqueue route. Delegates to the
        # standalone execute-and-deliver service (task 4.1), which resolves the set, builds the
        # send job(s), and ENQUEUES them to SQS; a worker (task 4.3/4.4) performs the actual SES
        # send. The route NEVER blocks on the send — it returns an ACCEPTED (202-style) result,
        # wrapped in `AcceptedResult` so the edge shapes a 202 (enqueued, not done). `tenant_id`
        # is authoritative; the caller sub seeds the `run_id` for audit attribution (R4 — never a
        # gate; the gate is the route's members:export + existing scope). An absent set raises
        # AnalyticsSetNotFound (→ 404); a set with no delivery block raises DeliveryNotConfigured
        # (→ 422) — both mapped at the edge.
        set_id = _require_path_param(ctx, "set_id")
        run_id = _new_run_id(tenant_id, set_id, ctx.sub)
        # Reply-To = the triggering user's VERIFIED email (R4.3) — from the verified JWT claims,
        # never a body value (verify-before-trust). The service runs the SYNCHRONOUS pre-send
        # certification gate and stamps the resolved tenant From + this Reply-To onto every job;
        # a not-certified tenant raises MailNotCertified (→ mapped at the edge), no enqueue.
        reply_to = _verified_email(ctx)
        deliver_service = get_execute_and_deliver_service()
        outcome = deliver_service.execute_and_deliver(
            tenant_id, set_id, run_id, reply_to=reply_to
        )
        # The service returns a frozen `DeliveryOutcome` dataclass; the edge's JSON encoder only
        # knows Decimals, so shape it into a plain dict here (the enqueued-send receipt the SPA
        # echoes). `AcceptedResult` makes the edge emit a 202, not a 200 (enqueued, not done).
        return AcceptedResult(_delivery_outcome_to_dict(outcome))

    if name == "send_ad_hoc_mail":
        # The AD-HOC interactive send (mail-spec task 2.1) — the stateless SIBLING of
        # `deliver_analytics_set`. The compose body IS the request body (the current result
        # rows + the typed recipients / template / attachment), NOT a saved set + stored
        # delivery; the edge parses it into an `AdHocMailBody` (shape only — the service owns
        # the authoritative validation) and delegates to the ONE shared send service's
        # `send_ad_hoc`, which runs the SAME synchronous pre-send certification gate, builds the
        # SAME MailJob shape, and ENQUEUES on the SAME MailQueue (design "two thin routes, ONE
        # shared send service"). The route stays THIN: no business logic here (the fan-out,
        # the gate, the address resolution all live in the service).
        #
        # `tenant_id` is AUTHORITATIVE from the verified context (never a body value —
        # verify-before-trust, Property 3). Reply-To = the triggering user's VERIFIED email
        # (R4.3), from the JWT claims only. A fresh `run_id` is minted per click (one logical
        # run, folded into every job's stable id for idempotent redelivery). A not-certified
        # tenant raises MailNotCertified (→ 422 errors.mail.notCertified at the edge) with NO
        # enqueue; a malformed body raises AdHocMailInvalid (→ 422 at the edge).
        body = _parse_ad_hoc_body(request)
        run_id = _new_run_id(tenant_id, body.set_id, ctx.sub)
        reply_to = _verified_email(ctx)
        send_service = get_execute_and_deliver_service()
        outcome = send_service.send_ad_hoc(
            tenant_id, body, run_id, reply_to=reply_to
        )
        return AcceptedResult(_delivery_outcome_to_dict(outcome))

    # ── Group ANALYTICS (send-run STATUS reads — R9, mail-spec task 3.2) ─────────────
    #
    # The pull-model status/history SURFACE (R9.2/R9.6): read the send-run records (task 3.1)
    # and render them. Backed by the standalone MailRunStatusService over the tenant-pinned
    # repository (`tenant_id` is authoritative — Property 3, no cross-tenant read). The R9.3
    # ROLE-SCOPING is resolved HERE from the VERIFIED context — a Tenant_Admin (holds
    # `members:admin`) sees ALL the tenant's runs; a plain user sees only their OWN
    # (`triggered_by == ctx.sub`). The admin fact comes from the three-state has_capability over
    # the verified claims (never a header/body — verify-before-trust); `ctx.sub` is the verified
    # caller id the run's `triggered_by` carries. The handler stays THIN: it hands the service
    # the authoritative tenant + sub + the computed admin boolean, and the service applies the
    # scope rule.
    if name == "list_mail_runs":
        status_service = get_mail_run_status_service()
        admin = _caller_is_tenant_admin(ctx)
        runs = status_service.list_runs(
            tenant_id, requester_sub=ctx.sub, admin=admin
        )
        return [_mail_run_to_dict(r) for r in runs]

    if name == "get_mail_run":
        # One run's tally + its FAILURE drill-down, subject to the SAME scope: a plain user may
        # drill only into a run they triggered (an existing-but-other-user run is reported as
        # absent → MailRunNotFound → 404, so a scoped caller cannot probe for another user's
        # runs); a Tenant_Admin may drill into any tenant run. A truly absent run is a 404 for
        # everyone. The service returns None in both not-visible cases; the edge maps it to a 404.
        run_id = _require_path_param(ctx, "run_id")
        status_service = get_mail_run_status_service()
        admin = _caller_is_tenant_admin(ctx)
        view = status_service.get_run(
            tenant_id, run_id, requester_sub=ctx.sub, admin=admin
        )
        if view is None:
            raise MailRunNotFound(run_id)
        return {
            "run": _mail_run_to_dict(view.run),
            "failures": [_mail_failure_to_dict(f) for f in view.failures],
        }

    if name == "delete_mail_run":
        # Manually delete one send-run (R9.6 retention) — the thin DELETE half of the status
        # surface. Subject to the SAME scope as `get_mail_run`: a plain user may delete only a
        # run they triggered, a Tenant_Admin any tenant run. The admin fact comes from the
        # three-state has_capability over the VERIFIED claims (never a header/body —
        # verify-before-trust, Property 3); `ctx.sub` is the verified caller id the run's
        # `triggered_by` carries. The service returns False in BOTH not-visible cases (truly
        # absent, or an existing-but-other-user run for a non-admin), which the edge maps to a
        # MailRunNotFound → 404 — deliberately indistinguishable so a scoped caller cannot probe
        # for (or destroy) another user's runs. On a visible run the service deletes the tally +
        # all FAILURE sub-records (tenant-pinned) and the edge returns an empty success (200
        # `{success:true, data:{}}`), consistent with the module's other DELETE routes.
        run_id = _require_path_param(ctx, "run_id")
        status_service = get_mail_run_status_service()
        admin = _caller_is_tenant_admin(ctx)
        deleted = status_service.delete_run(
            tenant_id, run_id, requester_sub=ctx.sub, admin=admin
        )
        if not deleted:
            raise MailRunNotFound(run_id)
        return {}

    if name == "get_preferred_list":
        # The caller's OWN preferred list, keyed by the verified sub (user ≠ member, R11.1 —
        # NOT a path param, NOT a body owner). Empty when the user has none (R11 empty-is-valid).
        return service.get_preferred_list(tenant_id, ctx.sub)

    if name == "save_preferred_list":
        # Replace the caller's OWN preferred list; sub is authoritative from the verified
        # context (never the body). refs is the ordered tagged-reference list.
        return service.save_preferred_list(tenant_id, ctx.sub, _write_body(request))

    if name == "get_column_preferences":
        # The caller's OWN chosen overview columns, keyed by the verified sub (user ≠ member,
        # R11.1 — NOT a path param, NOT a body owner). Empty when the user has none (R6.4
        # empty-is-valid — the first-time default is applied client-side).
        return service.get_column_preferences(tenant_id, ctx.sub)

    if name == "save_column_preferences":
        # Replace the caller's OWN chosen overview columns; sub is authoritative from the
        # verified context (never the body). columns is the ordered field-key list; the service
        # drops blank/dupe/non-candidate keys (R6.5).
        return service.save_column_preferences(tenant_id, ctx.sub, _write_body(request))

    # ── Group MEMBER (writes — task 5.2) ──────────────────────────────────────────────
    if name == "create_member":
        return service.create_member(
            tenant_id,
            _write_body(request),
            scopes,
            requester_sub=ctx.sub,
            caller_roles=ctx.groups,
        )

    if name == "update_member":
        member_id = _require_path_param(ctx, "member_id")
        return service.update_member(
            tenant_id,
            member_id,
            _write_body(request),
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
            caller_roles=ctx.groups,
        )

    if name == "delete_member":
        member_id = _require_path_param(ctx, "member_id")
        return service.delete_member(
            tenant_id,
            member_id,
            scopes,
            requester_sub=ctx.sub,
        )

    # ── Group MEMBERSHIP (writes — task 5.2) ──────────────────────────────────────────
    if name == "create_membership":
        member_id = _require_path_param(ctx, "member_id")
        return service.create_membership(
            tenant_id,
            member_id,
            _write_body(request),
            scopes,
            requester_sub=ctx.sub,
        )

    if name == "update_membership":
        member_id = _require_path_param(ctx, "member_id")
        membership_id = _require_path_param(ctx, "membership_id")
        return service.update_membership(
            tenant_id,
            member_id,
            membership_id,
            _write_body(request),
            scopes,
            requester_sub=ctx.sub,
        )

    if name == "delete_membership":
        member_id = _require_path_param(ctx, "member_id")
        membership_id = _require_path_param(ctx, "membership_id")
        return service.delete_membership(
            tenant_id,
            member_id,
            membership_id,
            scopes,
            requester_sub=ctx.sub,
        )

    if name == "transition_membership":
        member_id = _require_path_param(ctx, "member_id")
        body = _write_body(request)
        to_state = _parse_to_state(body)
        result = service.transition_member(
            tenant_id,
            member_id,
            to_state,
            scopes,
            context=_transition_context(body),
            requester_sub=ctx.sub,
        )
        return {
            "member": result.member,
            "from": result.from_state.value,
            "to": result.to_state.value,
        }

    if name == "bulk_transition_memberships":
        body = _write_body(request)
        to_state = _parse_to_state(body)
        member_ids = body.get("member_ids") if isinstance(body, Mapping) else None
        if not isinstance(member_ids, (list, tuple)) or not member_ids:
            raise MemberValidationError(
                {"member_ids": "a non-empty member_ids list is required"}
            )
        return service.bulk_transition_members(
            tenant_id,
            [str(m) for m in member_ids],
            to_state,
            scopes,
            context=_transition_context(body),
            requester_sub=ctx.sub,
        )

    # ── Group DELEGATE (writes — task 5.2; self-service) ──────────────────────────────
    if name == "manage_delegates":
        member_id = _require_path_param(ctx, "member_id")
        return service.manage_delegates(
            tenant_id,
            member_id,
            _write_body(request),
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
        )

    if name == "send_delegate_invitation":
        member_id = _require_path_param(ctx, "member_id")
        return service.send_delegate_invitation(
            tenant_id,
            member_id,
            _write_body(request),
            scopes,
            requester_sub=ctx.sub,
            self_service=spec.self_service,
        )

    # ── Group TEMPLATES (stored mail templates, R2 — pivot-output-actions task 2.3) ──
    #
    # The template CRUD surface is backed by the standalone TemplateService (NOT the
    # MembershipService) — a template carries no member/scope concern, so it lives behind a
    # module-agnostic seam (steering 35, rule of three). The service is resolved lazily via
    # `get_template_service()` (patchable test seam), mirroring `app._get_membership_service`.
    # `tenant_id` is authoritative from the verified context (never a body); `created_by` is
    # the verified caller sub (attribution only — the gate is the route capability, R2). The
    # service raises TemplateNotFound (→ 404) / TemplateValidationError (→ 422), mapped at the
    # edge to the API error standard v1.0.
    if name in {
        "create_template",
        "list_templates",
        "get_template",
        "update_template",
        "delete_template",
    }:
        template_service = get_template_service()

        if name == "create_template":
            return template_service.create_template(
                tenant_id, _write_body(request), created_by=ctx.sub
            )
        if name == "list_templates":
            return template_service.list_templates(tenant_id)
        if name == "get_template":
            template_id = _require_path_param(ctx, "template_id")
            return template_service.get_template(tenant_id, template_id)
        if name == "update_template":
            template_id = _require_path_param(ctx, "template_id")
            return template_service.update_template(
                tenant_id, template_id, _write_body(request)
            )
        if name == "delete_template":
            template_id = _require_path_param(ctx, "template_id")
            return template_service.delete_template(tenant_id, template_id)

    # ── Group CATALOG (Lidmaatschap Beheer writes, design C8 — task 5.3) ─────────────
    if name == "create_membership_type":
        # Create a catalog entry; a duplicate type_code is a 409 (never a silent overwrite).
        # Tenant-scoped by the verified tenant_id (never a body tenant_id — verify-before-trust).
        return service.create_membership_type(tenant_id, _write_body(request))

    if name == "update_membership_type":
        type_code = _require_path_param(ctx, "type_code")
        return service.update_membership_type(
            tenant_id, type_code, _write_body(request)
        )

    if name == "deactivate_membership_type":
        # Soft-delete (retire → active=false), NEVER a hard delete (C8 referential integrity).
        type_code = _require_path_param(ctx, "type_code")
        return service.deactivate_membership_type(tenant_id, type_code)

    # Anything not wired above → honest 501.
    raise RouteNotImplemented(spec.name)


__all__ = [
    "MailRunNotFound",
    "RouteNotImplemented",
    "_parse_to_state",
    "_query_flag",
    "_require_path_param",
    "_transition_context",
    "_write_body",
    "dispatch_route",
    "get_execute_and_deliver_service",
    "get_mail_run_status_service",
    "get_template_service",
]
