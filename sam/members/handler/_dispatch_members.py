"""
Members edge — per-resource dispatch: MEMBER / MEMBERSHIP / PAYMENT / CATALOG / DELEGATE.

The subset of :func:`sam.members.handler._dispatch.dispatch_route` that delegates the
member-centric routes (and the membership-type catalog) to the generic
:class:`~sam.members.domain.membership_service.MembershipService`. The edge stays THIN: it
hands the domain service the verified ``tenant_id`` (isolation, Property 1), the resolved
per-dimension ``allowed_scopes`` map (domain-layer scope filtering, design C4 / Property 4/6),
the requester ``sub`` + ``self_service`` flag, and the router's path params. No scope math, no
field resolution, no DynamoDB here.

:func:`dispatch_members` returns :data:`~sam.members.handler._dispatch_services.UNHANDLED`
when the route ``name`` is not one of this group's — so the top-level dispatcher moves on to
the next group, preserving the exact fall-through of the original single ``if name == ...``
chain. Pure structural split (code-quality task 4) — no behaviour change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sam.members.handler._dispatch_services import (
    UNHANDLED,
    _query_flag,
    _parse_page_size,
    _require_path_param,
    _write_body,
)
from sam.members.handler._http import ParsedRequest
from sam.members.handler.routes import RouteSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sam.members.domain.membership_service import MembershipService
    from sam.members.handler.app import RequestContext


def dispatch_members(
    service: "MembershipService",
    spec: RouteSpec,
    request: ParsedRequest,
    ctx: "RequestContext",
) -> Any:
    """Delegate a MEMBER / MEMBERSHIP / PAYMENT / CATALOG / DELEGATE route, or :data:`UNHANDLED`."""
    tenant_id = ctx.tenant_id
    scopes = ctx.allowed_scopes
    name = spec.name

    # ── Group MEMBER (reads) ──────────────────────────────────────────────────────────
    if name == "list_members":
        # Rows-per-page selector + DynamoDB cursor paging (Req 25, Task 1.17). When the caller
        # opts into paging (`?page_size=`), return ONE DynamoDB page + the opaque next-page
        # cursor: a fixed option (50/100/250/500) is the Query `Limit`; `Max` omits the `Limit`
        # (one page up to ~1 MB). `?cursor=` resumes a prior page; the domain decodes it with a
        # tenant check (a cross-tenant / tampered cursor raises CursorError → 400 at the edge).
        # Without `page_size`, the LEGACY full scope-narrowed list is returned unchanged
        # (backward compatible with callers that do not page). `page_size` + `cursor` are
        # per-user RUNTIME params on the read query — never tenant config (R25.9).
        paging, limit = _parse_page_size(request.query)
        if not paging:
            return service.list_members(tenant_id, scopes)
        cursor = (
            request.query.get("cursor") if isinstance(request.query, dict) else None
        )
        rows, next_cursor = service.list_members_page(
            tenant_id, scopes, page_size=limit, cursor=cursor
        )
        return {"items": rows, "cursor": next_cursor}

    if name == "list_members_filtered":
        filters = request.body if isinstance(request.body, dict) else None
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

    return UNHANDLED
