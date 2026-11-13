"""Serialization, parsing and stale-bundle guard helpers.
Part of _dispatch_services (task 9).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sam.members.domain.execute_and_deliver import AdHocMailBody
from sam.members.handler._http import ParsedRequest
from sam.members.handler.routes import CAP_MEMBERS_ADMIN
from sam.shared.auth_utils import has_capability

if (
    TYPE_CHECKING
):  # pragma: no cover - typing only, avoids an app<->_dispatch import cycle
    from sam.members.handler.app import RequestContext

from ._dispatch_services_shared import (
    _ATTR_OPS,
    _FIELD_IDENTITY_OPS,
    _FIELDS_OP_METHODS,
    _FIXED_PAGE_SIZES,
    _PAGE_SIZE_MAX,
    _WHOLE_OVERLAY_BODY_KEYS,
)


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
        # The DISPLAY names ride the envelope so the worker (task 6.2) can NAME the export
        # (`{Tenant_Name}-{Pivot_Name}.csv`) + PREFIX the subject without a second lookup
        # (members-overview-tweaks R5.2/R5.3/R5.5). `tenant_id` / `set_id` above are opaque
        # keys; these were stamped onto the MailJob at enqueue from the AUTHORITATIVE verified
        # tenant context + the stored set — never a request-body value. Defaulted to "" on a
        # job that predates the fields (additive, backward-compatible); the worker falls back
        # to a safe generic name when either is blank.
        "tenant_name": job.tenant_name,
        "pivot_name": job.pivot_name,
    }


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
        template_id=template_id
        if isinstance(template_id, str) and template_id
        else None,
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


class StaleClientBundleError(RuntimeError):
    """A ``config#fields`` write arrived in the RETIRED whole-overlay shape (spec 03 Task 5.3a).

    During the deprecation window (design "Migration/rollout — Slice 3") the server still gets
    the occasional write from a CACHED OLD SPA bundle that has not reloaded since the frontend
    switched to the Change-Op contract. That bundle sends a WHOLE RECORD — ``fields`` /
    ``overrides`` / ``fixed_overrides`` / ``functional_groups`` / ``field_overlay`` as a whole
    object — instead of an ``ops`` Change-Op list. Without this guard such a body falls into the
    GENERIC empty-ops :class:`ConfigFieldsCrudError` (a 400 "must carry a non-empty 'ops' list"),
    which the user on a stale tab cannot act on.

    This exception marks that specific shape so the edge can map it to an INTELLIGIBLE,
    caller-safe "reload the app" response (a distinct machine code + a 409), DISTINCT from the
    ops-validation 400 — so the SPA can render a dedicated "a newer version is available, please
    reload" prompt rather than an obscure validation failure. It carries NO raw internals
    (steering 39): the message names only the stale-client condition and the remedy.

    A :class:`RuntimeError` (not a :class:`ConfigFieldsCrudError`/``ValueError``) so the handler
    catches it on its OWN branch and never collapses it into the generic validation 400.
    """


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


def _parse_page_size(query: Mapping[str, Any]) -> tuple[bool, int | None]:
    """Parse the `?page_size=` Rows_Per_Page selector param (Req 25).

    Returns ``(paging_requested, limit)``:

    - no `page_size` param → ``(False, None)``: the LEGACY list path (the full scope-narrowed
      list, backward-compatible with callers that do not opt into cursor paging).
    - `page_size=max` (any case) → ``(True, None)``: the `Max` option — one DynamoDB Query page
      with NO `Limit`, bounded by the natural ~1 MB response boundary (R25.3).
    - `page_size=50|100|250|500` → ``(True, <int>)``: a fixed option applied as the Query
      `Limit` (R25.2).

    An unrecognised value (not `max` and not one of the fixed options) falls back to the
    platform-default fixed option (50) rather than erroring — a stray/garbled selector value
    must never 500 a plain list read; the frontend only ever sends the known tokens (R25.10).
    """
    raw = query.get("page_size") if isinstance(query, Mapping) else None
    if raw is None:
        return False, None
    token = str(raw).strip().lower()
    if token == _PAGE_SIZE_MAX:
        return True, None
    try:
        value = int(token)
    except (TypeError, ValueError):
        return True, 50
    if value in _FIXED_PAGE_SIZES:
        return True, value
    # Unknown numeric selector → platform fallback fixed option (never all-rows, never a raise).
    return True, 50


def _write_body(request: ParsedRequest) -> Mapping[str, Any]:
    """The parsed request body for a WRITE route, as a mapping (empty when absent/non-JSON).

    Write routes carry a JSON object body; a missing or non-object body is normalised to an
    empty mapping so the domain layer's authoritative validation surfaces the "required
    field" errors (a 422), rather than the handler guessing. The handler never enriches the
    body — the domain stamps the verified ``tenant_id`` itself (verify-before-trust).
    """
    body = request.body
    return body if isinstance(body, Mapping) else {}


def _dispatch_config_fields_ops(
    service: Any, tenant_id: str, request: ParsedRequest
) -> dict:
    """Apply a Change-Op list body to config#fields, op-by-op, via the injected service (2.7).

    The body MUST be ``{"ops": [ {op, key|group, attrs?, client_op_id?}, ... ]}`` (a bare list is
    also accepted for tolerance). The edge validates ONLY the envelope shape — an empty/absent ops
    list, an op that is not an object, or an unknown ``op`` token is a deliberate caller-safe
    :class:`ConfigFieldsCrudError` (→ 400). It does NOT validate op semantics (attribute surfaces,
    placement, version): each op is handed to the matching service method, which owns that and
    raises ``ConfigFieldsCrudError`` (→ 400) / ``StaleVersionError`` (→ 409). ``tenant_id`` is the
    VERIFIED tenant — the body never carries a tenant (steering 39).

    Returns an envelope ``{"success": True, "results": [<per-op service result>, ...]}`` so the
    caller sees each op's authoritative new version (the service result verbatim).

    Stale-SPA-bundle guard (TASK 5.3a — design "Migration/rollout Slice 3"): a body that carries
    a RETIRED whole-overlay shape (``fields`` / ``overrides`` / ``fixed_overrides`` /
    ``functional_groups`` / ``field_overlay`` as a whole record, no ``ops`` list) is a cached OLD
    SPA bundle that has not reloaded since the Change-Op switch. It is rejected with a distinct
    :class:`StaleClientBundleError` (→ an intelligible 409 "reload the app" the SPA can prompt on),
    NOT the generic empty-ops 400 — so a user on a stale tab gets an actionable message.
    """
    body = request.body
    # Accept either {"ops": [...]} (the canonical shape) or a bare list (tolerance).
    if isinstance(body, Mapping):
        raw_ops = body.get("ops")
    elif isinstance(body, (list, tuple)):
        raw_ops = body
    else:
        raw_ops = None

    if not isinstance(raw_ops, (list, tuple)) or not raw_ops:
        # BEFORE the generic empty-ops rejection: a whole-overlay body (the retired shape a cached
        # old SPA bundle sends — a whole record keyed by `fields`/`overrides`/`fixed_overrides`/
        # `functional_groups`/`field_overlay`, never an `ops` list) is a STALE CLIENT, not a
        # malformed Change-Op envelope. Surface the intelligible "reload the app" rejection so the
        # SPA prompts a reload instead of showing an obscure validation 400 (Task 5.3a).
        if isinstance(body, Mapping) and _WHOLE_OVERLAY_BODY_KEYS.intersection(body):
            raise StaleClientBundleError(
                "This change was sent in a retired format by an out-of-date app version. "
                "Please reload the page to get the latest version, then try again."
            )
        from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError

        raise ConfigFieldsCrudError(
            "config#fields write body must carry a non-empty 'ops' Change-Op list "
            "(the whole-overlay body is no longer accepted on this route)"
        )

    results: list[Any] = []
    for index, op in enumerate(raw_ops):
        results.append(_apply_one_config_fields_op(service, tenant_id, op, index))
    return {"success": True, "results": results}


def _apply_one_config_fields_op(
    service: Any, tenant_id: str, op: Any, index: int
) -> Any:
    """Dispatch ONE Change-Op mapping to its ConfigFieldsCrudService method (2.7).

    Validates only the op ENVELOPE (a mapping, a known ``op`` token, a non-empty identity); the
    service owns the attribute-surface / placement / version semantics. The dotted or bare field
    key is passed through verbatim (the service resolves placement). ``client_op_id`` is forwarded
    when present (lost-response idempotency). A malformed envelope raises
    :class:`ConfigFieldsCrudError` (→ caller-safe 400), naming the op INDEX, never echoing internals.
    """
    from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError

    if not isinstance(op, Mapping):
        raise ConfigFieldsCrudError(f"op[{index}] must be an object")
    op_kind = op.get("op")
    if op_kind not in _FIELDS_OP_METHODS:
        raise ConfigFieldsCrudError(
            f"op[{index}] has unknown op {op_kind!r}; must be one of "
            f"{sorted(_FIELDS_OP_METHODS)}"
        )

    client_op_id = op.get("client_op_id")
    client_op_id = (
        client_op_id if isinstance(client_op_id, str) and client_op_id else None
    )

    # Identity: a FIELD op keys on `key` (accept `field_key` too); a GROUP op keys on `group`
    # (accept `group_key` too). The service re-validates a blank identity, but surface a clear
    # envelope error here so the caller sees WHICH op is malformed.
    if op_kind in _FIELD_IDENTITY_OPS:
        identity = op.get("key") or op.get("field_key")
        identity_label = "key"
    else:
        identity = op.get("group") or op.get("group_key")
        identity_label = "group"
    if not isinstance(identity, str) or not identity:
        raise ConfigFieldsCrudError(
            f"op[{index}] ({op_kind}) requires a non-empty {identity_label!r} identity"
        )

    method = getattr(service, op_kind)
    if op_kind in _ATTR_OPS:
        attrs = op.get("attrs")
        if not isinstance(attrs, Mapping):
            raise ConfigFieldsCrudError(
                f"op[{index}] ({op_kind}) requires an 'attrs' object of attribute changes"
            )
        return method(tenant_id, identity, attrs, client_op_id=client_op_id)
    # reset_field / delete_field / delete_group — identity only, no attrs payload.
    return method(tenant_id, identity, client_op_id=client_op_id)
