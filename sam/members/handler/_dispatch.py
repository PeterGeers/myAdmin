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

from sam.members.domain.fixed_fields import MembershipStatus
from sam.members.domain.membership_service import (
    MemberValidationError,
)
from sam.members.handler._http import ParsedRequest
from sam.members.handler.routes import RouteSpec

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an app<->_dispatch import cycle
    from sam.members.domain.membership_service import MembershipService
    from sam.members.handler.app import RequestContext


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

    # ── Group MEMBER (writes — task 5.2) ──────────────────────────────────────────────
    if name == "create_member":
        return service.create_member(
            tenant_id, _write_body(request), scopes,
            requester_sub=ctx.sub, caller_roles=ctx.groups,
        )

    if name == "update_member":
        member_id = _require_path_param(ctx, "member_id")
        return service.update_member(
            tenant_id, member_id, _write_body(request), scopes,
            requester_sub=ctx.sub, self_service=spec.self_service,
            caller_roles=ctx.groups,
        )

    if name == "delete_member":
        member_id = _require_path_param(ctx, "member_id")
        return service.delete_member(
            tenant_id, member_id, scopes, requester_sub=ctx.sub,
        )

    # ── Group MEMBERSHIP (writes — task 5.2) ──────────────────────────────────────────
    if name == "create_membership":
        member_id = _require_path_param(ctx, "member_id")
        return service.create_membership(
            tenant_id, member_id, _write_body(request), scopes,
            requester_sub=ctx.sub,
        )

    if name == "update_membership":
        member_id = _require_path_param(ctx, "member_id")
        membership_id = _require_path_param(ctx, "membership_id")
        return service.update_membership(
            tenant_id, member_id, membership_id, _write_body(request), scopes,
            requester_sub=ctx.sub,
        )

    if name == "delete_membership":
        member_id = _require_path_param(ctx, "member_id")
        membership_id = _require_path_param(ctx, "membership_id")
        return service.delete_membership(
            tenant_id, member_id, membership_id, scopes,
            requester_sub=ctx.sub,
        )

    if name == "transition_membership":
        member_id = _require_path_param(ctx, "member_id")
        body = _write_body(request)
        to_state = _parse_to_state(body)
        result = service.transition_member(
            tenant_id, member_id, to_state, scopes,
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
            tenant_id, [str(m) for m in member_ids], to_state, scopes,
            context=_transition_context(body),
            requester_sub=ctx.sub,
        )

    # ── Group DELEGATE (writes — task 5.2; self-service) ──────────────────────────────
    if name == "manage_delegates":
        member_id = _require_path_param(ctx, "member_id")
        return service.manage_delegates(
            tenant_id, member_id, _write_body(request), scopes,
            requester_sub=ctx.sub, self_service=spec.self_service,
        )

    if name == "send_delegate_invitation":
        member_id = _require_path_param(ctx, "member_id")
        return service.send_delegate_invitation(
            tenant_id, member_id, _write_body(request), scopes,
            requester_sub=ctx.sub, self_service=spec.self_service,
        )

    # ── Group CATALOG (Lidmaatschap Beheer writes, design C8 — task 5.3) ─────────────
    if name == "create_membership_type":
        # Create a catalog entry; a duplicate type_code is a 409 (never a silent overwrite).
        # Tenant-scoped by the verified tenant_id (never a body tenant_id — verify-before-trust).
        return service.create_membership_type(tenant_id, _write_body(request))

    if name == "update_membership_type":
        type_code = _require_path_param(ctx, "type_code")
        return service.update_membership_type(tenant_id, type_code, _write_body(request))

    if name == "deactivate_membership_type":
        # Soft-delete (retire → active=false), NEVER a hard delete (C8 referential integrity).
        type_code = _require_path_param(ctx, "type_code")
        return service.deactivate_membership_type(tenant_id, type_code)

    # Anything not wired above → honest 501.
    raise RouteNotImplemented(spec.name)


__all__ = [
    "RouteNotImplemented",
    "_parse_to_state",
    "_query_flag",
    "_require_path_param",
    "_transition_context",
    "_write_body",
    "dispatch_route",
]
