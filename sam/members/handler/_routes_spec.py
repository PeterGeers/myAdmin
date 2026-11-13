"""HTTP method, route group and RouteSpec definition.
Part of the route map (task 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

    MEMBER = "member"  # member CRUD
    MEMBERSHIP = "membership"  # membership lifecycle
    DELEGATE = "delegate"  # delegates
    PAYMENT = "payment"  # member-scoped payments
    CATALOG = "catalog"  # Lidmaatschap Beheer membership-type catalog (C8)
    ANALYTICS = "analytics"  # member analytics-sets (F-012)


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
            ``None`` only for a route gated purely by self-service (see ``self_service``)
            OR by ``capabilities_any`` (an any-of gate).
        capabilities_any: An OPTIONAL any-of capability set (R11.3). When non-empty, the edge
            authorizes the route when the caller holds **ANY** listed capability (e.g.
            ``("members:export", "members:write")`` — an export-only OR a CRUD user both pass).
            Mutually complementary with ``capability``: a route uses EITHER the single
            ``capability`` (the common case) OR ``capabilities_any`` (never relies on both).
            Empty tuple (the default) means "no any-of gate" so existing single-capability
            routes are unchanged. The scope decision (if any) still runs after the capability
            check, same as for a single-capability route.
        self_service: True when a member may call it for **their own** record without the
            admin capability (e.g. ``get-self``); the domain layer enforces the ownership
            check. Metadata only at this step.
        summary: One-line description of the behaviour (for docs / parity audit).
        schedule_gate: True ONLY for the schedule CRUD routes (R5). Marks the SPECIAL
            combined capability+scope gate the edge enforces for scheduling: ``members:admin``
            OR (``members:write`` AND the ``["*"]`` all-regions scope grant). This is NOT a
            plain any-of capability gate — a region-narrowed ``members:write`` caller must be
            rejected (403) because an unattended scheduled run must never replay a partial
            regional slice (R5). When set, the edge's :func:`app._authorize_schedule_route`
            runs instead of the ordinary capability-any-of + scope seam. ``capabilities_any``
            still lists the capabilities involved (``members:admin``/``members:write``) so the
            route is never "ungated" and the integrity check passes.
    """

    name: str
    method: HttpMethod
    path: str
    group: RouteGroup
    capability: str | None
    self_service: bool
    summary: str
    capabilities_any: tuple[str, ...] = ()
    schedule_gate: bool = False


# ── The route map: union of h-dcn's ~18 handler behaviours (stubs only) ───────────────
#
# Paths are tenant-agnostic on the wire: the tenant is derived from the verified token +
# context at the handler edge (never a path/header the client supplies), and every read /
# write is keyed by ``tenant_id`` in the repository (Property 1 — structural isolation).
