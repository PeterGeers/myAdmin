"""
S5 Task 1.0 — the Members module **internal route map** (stubs only).

This is the single source of truth for the Members Lambda's internal routes: the
**union of h-dcn's ~18 per-action handler behaviours**, collapsed into one module that
routes internally by ``(method, path)`` (design C1, migration-plan Step 1, R1.1). h-dcn's
Members backend is ~18 one-Lambda-per-action handlers — a learning-curve artefact, not a
design to preserve — so the migration goes straight to the best-practice shape: **one
module, many routes**, the auth/entitlement toolkit adopted **once** at the edge.

Scope of THIS task (1.0): **stubs only.** Each route is declared with its method, path
pattern, a stable ``name``, the behaviour ``group`` it belongs to, and the
``capability``/``self_service`` metadata the handler edge (task 3.0) will gate on. No
route has an implementation yet — the domain service + repository that back them are
populated by the later Step 1 / Step 3 / Step 5 tasks. The router (``router.py``) resolves
an incoming request to one of these specs; the thin handler (``app.py``) then delegates to
the (still-stubbed) domain layer.

Layering (see ``.kiro/steering/35-sam-module-architecture-sam.md``): this module is part of
the **handler layer**. It holds NO business logic and NO DynamoDB access — only the
declarative description of the HTTP surface. Dependencies point downward only.

The route names mirror h-dcn's handler behaviours so parity is auditable at the Go/No-Go:

    Member CRUD ............ create · get-by-id · get-self · list · list-filtered ·
                            update · delete · export                     (8)
    Membership lifecycle ... create · get · list · update · delete ·
                            transition · bulk-transition                 (7)
    Delegates .............. manage delegates · send delegate invitation (2)
    Payments (member) ...... get member payments                        (1)
                                                                    total 18
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

__all__ = [
    "HttpMethod",
    "RouteGroup",
    "RouteSpec",
    "ROUTES",
    "route_names",
    "routes_by_group",
]


class HttpMethod(str, Enum):
    """The HTTP methods the Members module routes on."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class RouteGroup(str, Enum):
    """The behaviour groups the h-dcn handlers collapse into (design C1), plus the catalog.

    The first four mirror h-dcn's ~18 per-action handlers. ``CATALOG`` is a **new** group the
    migration adds (design C8, R2.4): the tenant-scoped **Lidmaatschap Beheer** membership-type
    catalog has no h-dcn analogue (h-dcn's type vocabulary is hardcoded). It gets its own group
    — rather than being folded into MEMBER — so the catalog surface stays independently
    auditable at the Go/No-Go and its read/write routes (this task adds the reads; task 5.3
    the writes) are grouped together.
    """

    MEMBER = "member"                 # member CRUD
    MEMBERSHIP = "membership"         # membership lifecycle
    DELEGATE = "delegate"             # delegates
    PAYMENT = "payment"               # member-scoped payments
    CATALOG = "catalog"               # Lidmaatschap Beheer membership-type catalog (C8)


# The capability names the entitlement gate (task 3.0, C7) checks. Declared here as
# metadata only — this task wires no enforcement; it records WHICH capability each route
# will require so the handler edge has a single declarative place to read it from.
CAP_MEMBERS_READ = "members:read"
CAP_MEMBERS_WRITE = "members:write"
CAP_MEMBERS_EXPORT = "members:export"
CAP_MEMBERS_ADMIN = "members:admin"


@dataclass(frozen=True)
class RouteSpec:
    """One internal route: how it is matched and how the edge will later gate it.

    Attributes:
        name: Stable identifier for the behaviour (mirrors an h-dcn handler behaviour);
            the router returns it and the domain layer dispatches on it.
        method: The HTTP method this route matches.
        path: The path **pattern**, using ``{param}`` placeholders (e.g.
            ``/members/{member_id}``). The router extracts the named params.
        group: The behaviour group (member / membership / delegate / payment).
        capability: The entitlement capability the handler edge will require (task 3.0).
            ``None`` only for a route gated purely by self-service (see ``self_service``).
        self_service: True when a member may call it for **their own** record without the
            admin capability (e.g. ``get-self``); the domain layer enforces the ownership
            check. Metadata only at this step.
        summary: One-line description of the behaviour (for docs / parity audit).
    """

    name: str
    method: HttpMethod
    path: str
    group: RouteGroup
    capability: Optional[str]
    self_service: bool
    summary: str


# ── The route map: union of h-dcn's ~18 handler behaviours (stubs only) ───────────────
#
# Paths are tenant-agnostic on the wire: the tenant is derived from the verified token +
# context at the handler edge (never a path/header the client supplies), and every read /
# write is keyed by ``tenant_id`` in the repository (Property 1 — structural isolation).

ROUTES: tuple[RouteSpec, ...] = (
    # ── Member CRUD (8) ──────────────────────────────────────────────────────────────
    RouteSpec(
        name="create_member",
        method=HttpMethod.POST,
        path="/members",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_WRITE,
        self_service=False,
        summary="Create a new member for the current tenant.",
    ),
    RouteSpec(
        name="list_members",
        method=HttpMethod.GET,
        path="/members",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary="List members for the current tenant (scope-filtered).",
    ),
    RouteSpec(
        name="list_members_filtered",
        method=HttpMethod.POST,
        path="/members/search",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary="List members with server-side filters (scope-filtered).",
    ),
    RouteSpec(
        name="export_members",
        method=HttpMethod.GET,
        path="/members/export",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary="Export the tenant's members (scope-filtered).",
    ),
    RouteSpec(
        name="get_self",
        method=HttpMethod.GET,
        path="/members/me",
        group=RouteGroup.MEMBER,
        capability=None,
        self_service=True,
        summary="Get the calling member's own record.",
    ),
    RouteSpec(
        name="get_field_config",
        method=HttpMethod.GET,
        path="/members/field-config",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_READ,
        self_service=True,
        summary=(
            "Resolved field config (fixed ⊕ overlay) for the current tenant, incl. the "
            "membership_type dropdown = the tenant's active catalog entries."
        ),
    ),
    RouteSpec(
        name="get_member",
        method=HttpMethod.GET,
        path="/members/{member_id}",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_READ,
        self_service=True,
        summary="Get a single member by id (own record allowed via self-service).",
    ),
    RouteSpec(
        name="update_member",
        method=HttpMethod.PUT,
        path="/members/{member_id}",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_WRITE,
        self_service=False,
        summary="Update a member record.",
    ),
    RouteSpec(
        name="delete_member",
        method=HttpMethod.DELETE,
        path="/members/{member_id}",
        group=RouteGroup.MEMBER,
        capability=CAP_MEMBERS_ADMIN,
        self_service=False,
        summary="Delete a member record.",
    ),
    # ── Membership lifecycle (7) ──────────────────────────────────────────────────────
    RouteSpec(
        name="create_membership",
        method=HttpMethod.POST,
        path="/members/{member_id}/memberships",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_WRITE,
        self_service=False,
        summary="Create a membership for a member.",
    ),
    RouteSpec(
        name="list_memberships",
        method=HttpMethod.GET,
        path="/members/{member_id}/memberships",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_READ,
        self_service=True,
        summary="List a member's memberships.",
    ),
    RouteSpec(
        name="get_membership",
        method=HttpMethod.GET,
        path="/members/{member_id}/memberships/{membership_id}",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_READ,
        self_service=True,
        summary="Get a single membership of a member.",
    ),
    RouteSpec(
        name="update_membership",
        method=HttpMethod.PUT,
        path="/members/{member_id}/memberships/{membership_id}",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_WRITE,
        self_service=False,
        summary="Update a membership.",
    ),
    RouteSpec(
        name="delete_membership",
        method=HttpMethod.DELETE,
        path="/members/{member_id}/memberships/{membership_id}",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_ADMIN,
        self_service=False,
        summary="Delete a membership.",
    ),
    RouteSpec(
        name="transition_membership",
        method=HttpMethod.POST,
        path="/members/{member_id}/memberships/{membership_id}/transition",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_WRITE,
        self_service=False,
        summary="Apply a lifecycle transition to a membership (guarded by config/rules).",
    ),
    RouteSpec(
        name="bulk_transition_memberships",
        method=HttpMethod.POST,
        path="/memberships/transition",
        group=RouteGroup.MEMBERSHIP,
        capability=CAP_MEMBERS_ADMIN,
        self_service=False,
        summary="Apply a lifecycle transition to many memberships at once.",
    ),
    # ── Delegates (2) ─────────────────────────────────────────────────────────────────
    RouteSpec(
        name="manage_delegates",
        method=HttpMethod.PUT,
        path="/members/{member_id}/delegates",
        group=RouteGroup.DELEGATE,
        capability=CAP_MEMBERS_WRITE,
        self_service=True,
        summary="Manage (set) a member's delegates.",
    ),
    RouteSpec(
        name="send_delegate_invitation",
        method=HttpMethod.POST,
        path="/members/{member_id}/delegates/invitations",
        group=RouteGroup.DELEGATE,
        capability=CAP_MEMBERS_WRITE,
        self_service=True,
        summary="Send an invitation to a prospective delegate.",
    ),
    # ── Payments — member-scoped (1) ──────────────────────────────────────────────────
    RouteSpec(
        name="get_member_payments",
        method=HttpMethod.GET,
        path="/members/{member_id}/payments",
        group=RouteGroup.PAYMENT,
        capability=CAP_MEMBERS_READ,
        self_service=True,
        summary="Get a member's payments.",
    ),
    # ── Lidmaatschap Beheer catalog — reads (2), design C8 / task 3.4 ──────────────────
    #
    # The tenant-scoped membership-type catalog's MANAGEMENT read surface. Distinct from the
    # dropdown-options feed on ``GET /members/field-config`` (task 3.3), which returns only
    # ACTIVE entries: this list defaults to ALL entries (incl. soft-deleted ``active=false``)
    # so an admin can see/manage retired types, with an ``?active_only=true`` query filter to
    # narrow to just the assignable ones (design C8 soft-delete semantics). Read-only here;
    # catalog WRITE routes (create/update/soft-delete) come in task 5.3. Gated by the existing
    # ``members:read`` capability (the resolver emits ``members:read/write/export/admin`` — no
    # catalog-specific token exists to invent); not a self-service concern.
    #
    # The literal ``/membership-types`` prefix is disjoint from every ``/members...`` path, so
    # the ``{type_code}`` route can never shadow (or be shadowed by) a member route.
    RouteSpec(
        name="list_membership_types",
        method=HttpMethod.GET,
        path="/membership-types",
        group=RouteGroup.CATALOG,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary=(
            "List the tenant's Lidmaatschap Beheer membership-type catalog for management "
            "(ALL entries incl. retired; ?active_only=true narrows to assignable)."
        ),
    ),
    RouteSpec(
        name="get_membership_type",
        method=HttpMethod.GET,
        path="/membership-types/{type_code}",
        group=RouteGroup.CATALOG,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary="Get a single membership-type catalog entry by its type_code (404 if absent).",
    ),
    # ── Lidmaatschap Beheer catalog — writes (3), design C8 / task 5.3 ─────────────────
    #
    # Catalog MANAGEMENT writes: create / update / soft-delete (retire) a membership type.
    # Gated by ``members:admin`` (CAP_MEMBERS_ADMIN), NOT ``members:write``: managing the
    # tenant's type vocabulary is an administrative concern (like delete_member /
    # bulk_transition, which are also admin-gated), distinct from writing an individual member
    # record. The reads above use ``members:read`` (viewing the catalog is an ordinary read);
    # only mutation is elevated to admin. None are self-service — a member never manages the
    # tenant catalog. The ``{type_code}`` write routes share the ``/membership-types`` prefix
    # with the 3.4 reads, but the methods differ (GET vs PUT/DELETE), so there is no (method,
    # path) collision; the literal prefix stays disjoint from every ``/members...`` path.
    RouteSpec(
        name="create_membership_type",
        method=HttpMethod.POST,
        path="/membership-types",
        group=RouteGroup.CATALOG,
        capability=CAP_MEMBERS_ADMIN,
        self_service=False,
        summary="Create a Lidmaatschap Beheer membership-type catalog entry (409 on duplicate).",
    ),
    RouteSpec(
        name="update_membership_type",
        method=HttpMethod.PUT,
        path="/membership-types/{type_code}",
        group=RouteGroup.CATALOG,
        capability=CAP_MEMBERS_ADMIN,
        self_service=False,
        summary="Update a membership-type catalog entry by its type_code (404 if absent).",
    ),
    RouteSpec(
        name="deactivate_membership_type",
        method=HttpMethod.DELETE,
        path="/membership-types/{type_code}",
        group=RouteGroup.CATALOG,
        capability=CAP_MEMBERS_ADMIN,
        self_service=False,
        summary=(
            "Soft-delete (retire, active=false) a membership-type catalog entry — never a "
            "hard delete (C8 referential integrity); 404 if absent."
        ),
    ),
)


# ── Import-time integrity checks (the route map is a single source of truth) ───────────
#
# A duplicate (method, path) or a duplicate behaviour name would make routing ambiguous,
# so we fail fast at import rather than silently shadow a route.
def _assert_route_map_is_consistent() -> None:
    seen_endpoints: set[tuple[str, str]] = set()
    seen_names: set[str] = set()
    for spec in ROUTES:
        endpoint = (spec.method.value, spec.path)
        if endpoint in seen_endpoints:
            raise ValueError(f"duplicate route endpoint: {spec.method.value} {spec.path}")
        seen_endpoints.add(endpoint)
        if spec.name in seen_names:
            raise ValueError(f"duplicate route name: {spec.name}")
        seen_names.add(spec.name)
        # A route must be gated by a capability, self-service, or both — never nothing.
        if spec.capability is None and not spec.self_service:
            raise ValueError(f"route {spec.name} has neither a capability nor self-service")


_assert_route_map_is_consistent()


def route_names() -> tuple[str, ...]:
    """All route behaviour names in declaration order (parity-audit source of truth)."""
    return tuple(spec.name for spec in ROUTES)


def routes_by_group(group: RouteGroup) -> tuple[RouteSpec, ...]:
    """Return the routes belonging to one behaviour group."""
    return tuple(spec for spec in ROUTES if spec.group is group)
