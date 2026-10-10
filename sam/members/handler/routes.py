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

__all__ = [
    "ROUTES",
    "HttpMethod",
    "RouteGroup",
    "RouteSpec",
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
    # ── Column preferences — per-user overview columns (session-columns R6) ──────────
    #
    # The per-user chosen-column list for the Members overview, mirroring the preferred-list
    # route pair end to end. Keyed by the verified ``sub`` at the edge (NOT a path param, NOT a
    # body owner — user ≠ member, R11.1). DECLARED BEFORE the ``/members/{member_id}`` routes so
    # the LITERAL ``column-preferences`` segment wins over the ``{member_id}`` placeholder (the
    # router returns the first matching route in declaration order for a method); the literal
    # path is also disjoint from the ``/members/analytics-sets...`` and other ``/members/...``
    # literal routes. GET = members:read; PUT = members:export OR members:write (R6.3 — any user
    # who can run/export sets may curate their own columns).
    RouteSpec(
        name="get_column_preferences",
        method=HttpMethod.GET,
        path="/members/column-preferences",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary=(
            "Get the calling user's chosen overview columns (empty when unset, R6.4)."
        ),
    ),
    RouteSpec(
        name="save_column_preferences",
        method=HttpMethod.PUT,
        path="/members/column-preferences",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Replace the calling user's chosen overview columns (ordered field keys, R6.5). "
            "Gate: members:export OR members:write."
        ),
    ),
    # ── Analytics-sets — CRUD (5), F-012 ───────────────────────────────────────────
    #
    # Tenant-scoped member analytics-sets: saved pivot/list definitions owned by the Members
    # module (DynamoDB), replacing the Flask /api/pivot/models store. The literal
    # `/members/analytics-sets` prefix is disjoint from `/members/{member_id}` and the other
    # `/members/...` literal routes (field-config, export, me, search) so no (method, path)
    # collision or shadowing. DECLARED BEFORE the `{member_id}` routes so the literal prefix
    # matches FIRST (the router returns the first matching route in declaration order for a
    # method).
    #
    # Gates (R11.3 — any-of): the analytics-set surface is NOT admin-only. Reads use
    # `members:read`. CREATE is allowed for an EXPORT user OR a CRUD/write user
    # (`members:export` | `members:write`). EDIT/DELETE of a (shared) set is allowed for a
    # CRUD/write user OR a tenant admin (`members:write` | `members:admin`) — not restricted to
    # the set's creator (`created_by` is attribution only). A predefined (code) preset has no
    # stored item and is never a DELETE/UPDATE target.
    RouteSpec(
        name="create_analytics_set",
        method=HttpMethod.POST,
        path="/members/analytics-sets",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Create a member analytics-set (saved pivot/list definition, F-012). "
            "Gate: members:export OR members:write (R11.3)."
        ),
    ),
    RouteSpec(
        name="list_analytics_sets",
        method=HttpMethod.GET,
        path="/members/analytics-sets",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary="List the tenant's member analytics-sets (the shared library).",
    ),
    # Per-user PREFERRED LIST (R11.2 layer 2). Keyed by the verified sub at the edge (NOT a
    # path param). DECLARED BEFORE the `/{set_id}` routes so the LITERAL `preferred` segment
    # wins over the `{set_id}` placeholder (the router returns the first matching route in
    # declaration order for a method). GET = members:read; PUT = members:export OR members:write
    # (R11.3 — any user who can run/create sets may curate their own preferred list).
    RouteSpec(
        name="get_preferred_list",
        method=HttpMethod.GET,
        path="/members/analytics-sets/preferred",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary="Get the calling user's preferred analytics-set list (empty when unset, R11.2).",
    ),
    RouteSpec(
        name="save_preferred_list",
        method=HttpMethod.PUT,
        path="/members/analytics-sets/preferred",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Replace the calling user's preferred analytics-set list (ordered tagged refs, "
            "R11.2). Gate: members:export OR members:write."
        ),
    ),
    RouteSpec(
        name="get_analytics_set",
        method=HttpMethod.GET,
        path="/members/analytics-sets/{set_id}",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_READ,
        self_service=False,
        summary="Get a single member analytics-set by its set_id (404 if absent).",
    ),
    RouteSpec(
        name="update_analytics_set",
        method=HttpMethod.PUT,
        path="/members/analytics-sets/{set_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_WRITE, CAP_MEMBERS_ADMIN),
        self_service=False,
        summary=(
            "Update a member analytics-set by its set_id (404 if absent). "
            "Gate: members:write OR members:admin (R11.3)."
        ),
    ),
    RouteSpec(
        name="delete_analytics_set",
        method=HttpMethod.DELETE,
        path="/members/analytics-sets/{set_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_WRITE, CAP_MEMBERS_ADMIN),
        self_service=False,
        summary=(
            "Delete a member analytics-set (hard delete; 404 if absent). "
            "Gate: members:write OR members:admin (R11.3)."
        ),
    ),
    # ── Analytics-set DELIVERY block — set/clear (2), R3 (pivot-output-actions 3.3) ──
    #
    # The optional stored "what to do with the result" block on a saved set (design §2.1/§3).
    # Two routes set / clear it on an EXISTING set (the delivery block is an additive field on
    # the `analyticsset#<set_id>` item — task 3.1/3.2 — not a new record type). The literal
    # `/delivery` sub-path carries an EXTRA segment past `/{set_id}`, so it can never collide
    # with (or be shadowed by) the `/{set_id}` CRUD routes; it is also disjoint from the
    # `preferred` literal. Declared right after the set CRUD for cohesion.
    #
    # Gate (R3, design §3/§8): `members:export` + the EXISTING scope — the SAME gate the
    # analytics-set surface already carries. A stored delivery can only send what the user
    # could already export within their scope, so it introduces NO new permission and NO
    # audit-on-save (normal send-time auditing per R4 still applies, elsewhere). This is the
    # single-capability `members:export` gate (not an any-of), distinct from the create
    # (export OR write) / edit (write OR admin) gates: storing a delivery is an export-class
    # action, so export alone is both necessary and sufficient.
    RouteSpec(
        name="set_analytics_set_delivery",
        method=HttpMethod.PUT,
        path="/members/analytics-sets/{set_id}/delivery",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "Set/replace a saved set's stored delivery block (R3; 404 if the set is absent, "
            "422 on an invalid block). Gate: members:export + existing scope."
        ),
    ),
    RouteSpec(
        name="clear_analytics_set_delivery",
        method=HttpMethod.DELETE,
        path="/members/analytics-sets/{set_id}/delivery",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "Clear a saved set's stored delivery block (set delivery back to None, R3; "
            "404 if the set is absent). Gate: members:export + existing scope."
        ),
    ),
    # ── Analytics-set DELIVER — run execute-and-deliver NOW (1), R4 (task 4.2) ───────
    #
    # The interactive "run this set's stored delivery now" action (design §3/§4). It invokes
    # the execute-and-deliver service (task 4.1), which resolves the set, builds the send
    # job(s), and ENQUEUES them to the SQS send queue (`members-mail-send[-test]`); a worker
    # Lambda (task 4.3/4.4 — the consumer side) drains the queue and performs the actual SES
    # send. The route is THIN (steering 35): it never blocks on the send — it returns an
    # ACCEPTED (202-style, enqueued) result, so a long per-recipient run cannot time out the
    # request (R4: queued, not synchronous).
    #
    # The literal `/deliver` sub-path carries an EXTRA segment past `/{set_id}` (exactly like
    # `/delivery`), so it can never collide with or be shadowed by the `/{set_id}` CRUD routes;
    # it is disjoint from the `preferred` + `delivery` literals. Declared right after the
    # delivery set/clear routes for cohesion.
    #
    # Gate (R4, design §3/§8): `members:export` + the EXISTING scope — the SAME gate the
    # stored delivery (set/clear, task 3.3) carries. A send can only dispatch what the user
    # could already export within their scope, so it introduces NO new permission (normal
    # send-time auditing per R4 happens in the worker). Single-capability `members:export`,
    # matching the delivery set/clear gate.
    RouteSpec(
        name="deliver_analytics_set",
        method=HttpMethod.POST,
        path="/members/analytics-sets/{set_id}/deliver",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "Run a saved set's stored delivery NOW — enqueues the send job(s) and returns an "
            "ACCEPTED (202) result (R4; 404 if the set is absent, 422 if it has no delivery "
            "block). Gate: members:export + existing scope."
        ),
    ),
    # ── Ad-hoc interactive send — stateless (1), R2 (mail-spec task 2.1) ──────────────
    #
    # The SIBLING of the saved-set `deliver` route (design "two thin routes, ONE shared send
    # service"). Where `/deliver` runs a SAVED set + its stored delivery block, this stateless
    # route carries the COMPOSE body itself — the current result rows + the typed recipients /
    # template / attachment (an `AdHocMailBody`, mail-spec task 2.2) — so the interactive
    # `per_recipient` compose can send WITHOUT first saving a set. Both routes delegate to the
    # ONE execute-and-deliver service (`send_ad_hoc` here, `execute_and_deliver` there),
    # converging on the SAME pre-send certification gate, fan-out, MailJob shape, and MailQueue.
    #
    # The LITERAL `/members/mail/send` path is disjoint from `/members/{member_id}` (the first
    # segment past `/members/` is the literal `mail`, which is matched by its own route before
    # the `{member_id}` placeholder could capture it — the router returns the first matching
    # route in declaration order, and this is declared BEFORE the `{member_id}` routes) and from
    # every other `/members/...` literal (analytics-sets / templates / schedules / field-config /
    # export / me / search / column-preferences / membership-types), so there is no (method,
    # path) collision or shadowing.
    #
    # Gate (R2, design §3/§8): `members:export` — the SAME single-capability gate the saved-set
    # `deliver` route carries. An ad-hoc send can only dispatch what the user could already
    # export within their scope, so it introduces NO new permission; it is an export-class
    # action (export alone is both necessary and sufficient), matching the deliver gate.
    RouteSpec(
        name="send_ad_hoc_mail",
        method=HttpMethod.POST,
        path="/members/mail/send",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "Send an ad-hoc interactive compose NOW (current result rows + typed recipients / "
            "template / attachment) — enqueues the send job(s) and returns an ACCEPTED (202) "
            "result (R2; 422 on a malformed body or an un-certified tenant). Gate: "
            "members:export + existing scope."
        ),
    ),
    # ── Send-run STATUS — read (2), R9 (mail-spec task 3.2) ──────────────────────────
    #
    # The pull-model status/history SURFACE (R9.6): the React screen READS the send-run
    # records the enqueue path + worker write (task 3.1) and renders them — a list of runs
    # ("Newsletter — 198 sent, 2 failed") with per-run drill-down to the FAILURE sub-records.
    # TWO thin reads back it: a LIST of the tenant's runs, and a SINGLE run + its failures.
    # Both are keyed by `tenant_id` in the repository (Property 3 — no cross-tenant read); the
    # ROLE-SCOPING (R9.3 — a plain user sees only their OWN sends, a Tenant_Admin sees ALL the
    # tenant's) is resolved in the dispatch from the verified sub + the members:admin
    # entitlement, then applied by the thin MailRunStatusService (the handler stays thin).
    #
    # The literal `/members/mail-runs` prefix is disjoint from `/members/{member_id}` (the
    # first segment past `/members/` is the literal `mail-runs`, matched by its own route
    # before the `{member_id}` placeholder could capture it — the router returns the first
    # matching route in declaration order, and these are declared BEFORE the `{member_id}`
    # routes) and from every other `/members/...` literal (analytics-sets / templates /
    # schedules / mail / field-config / export / me / search / column-preferences /
    # membership-types), so there is no (method, path) collision or shadowing. `mail-runs`
    # (hyphen) is also distinct from the `mail` literal (`/members/mail/send`), so neither
    # shadows the other.
    #
    # Gate (R9, design §Components): `members:export` + the active tenant — the SAME mail
    # capability the send routes carry. Reading the status of a send is a mail-class action
    # for anyone who could trigger a send; it introduces NO new permission. The user-vs-admin
    # SCOPING is NOT a capability gate (both a plain export user and an admin pass the gate) —
    # it is the data-visibility narrowing applied AFTER the gate, in the dispatch/service.
    RouteSpec(
        name="list_mail_runs",
        method=HttpMethod.GET,
        path="/members/mail-runs",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "List the send-run status records (R9.2/R9.6) — a plain user sees only their OWN "
            "sends (triggered_by == sub), a Tenant_Admin sees ALL the tenant's. "
            "Gate: members:export + active tenant; role-scoped by members:admin."
        ),
    ),
    RouteSpec(
        name="get_mail_run",
        method=HttpMethod.GET,
        path="/members/mail-runs/{run_id}",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "Get one send-run's tally + its per-recipient FAILURE drill-down (R9.2), subject "
            "to the same scope: a plain user may drill only into their OWN run (else 404, no "
            "probe), a Tenant_Admin into any tenant run. Gate: members:export + active tenant."
        ),
    ),
    # ── Send-run RETENTION — manual delete (1), R9.6 (mail-spec task 3.3) ─────────────
    #
    # The manual-delete half of the R9 retention model (design "Resolved implementation
    # choices" → retention = a manual delete action + a DynamoDB TTL auto-delete). The user /
    # Tenant_Admin may purge a run from the status screen before the 90-day TTL fires; the
    # repository's `delete_mail_run` (task 3.1) removes the `mailrun#` tally AND all its
    # `mailrecipient#` FAILURE sub-records in one tenant-pinned op (no orphaned failures).
    #
    # Same literal `/members/mail-runs/{run_id}` path as the single-run GET, distinguished by
    # the DELETE method (the router keys on `(method, path)`), so it neither collides with nor
    # is shadowed by the GET read; `mail-runs` (hyphen) stays distinct from the `mail` literal
    # (`/members/mail/send`). Declared right after the status reads for cohesion.
    #
    # Gate (R9, design §Components): `members:export` + the active tenant — the SAME mail
    # capability the status reads carry; deleting a run you can see is a mail-class action,
    # no new permission. The user-vs-admin SCOPING (a plain user may delete only their OWN
    # run; a Tenant_Admin any tenant run) is NOT a capability gate — it is the same
    # data-visibility narrowing applied AFTER the gate, in the dispatch/service (an
    # out-of-scope run is reported absent → 404, no probe), mirroring `get_mail_run`.
    RouteSpec(
        name="delete_mail_run",
        method=HttpMethod.DELETE,
        path="/members/mail-runs/{run_id}",
        group=RouteGroup.ANALYTICS,
        capability=CAP_MEMBERS_EXPORT,
        self_service=False,
        summary=(
            "Manually delete a send-run status record (R9.6 retention) — removes the run tally "
            "AND all its FAILURE sub-records, tenant-pinned. Subject to the same scope: a plain "
            "user may delete only their OWN run (else 404, no probe), a Tenant_Admin any tenant "
            "run. Gate: members:export + active tenant."
        ),
    ),
    # ── Templates — CRUD (5), R2 (pivot-output-actions task 2.3) ────────────────────
    #
    # Tenant-scoped stored mail templates (metadata on-plane `template#<id>`; body HTML +
    # logo binaries in S3 `myadmin-shared`, task 2.1/2.2). The literal `/members/templates`
    # prefix is disjoint from `/members/{member_id}` and the other `/members/...` literal
    # routes (analytics-sets, field-config, export, me, search, column-preferences) so there
    # is no (method, path) collision or shadowing. DECLARED BEFORE the `{member_id}` routes
    # so the literal prefix matches FIRST (the router returns the first matching route in
    # declaration order for a method).
    #
    # Gate (design §3 / R2): the template CRUD surface is gated `members:export` OR
    # `members:write` (an any-of gate, same shape as the analytics-set create gate) — an
    # export user OR a CRUD/write user may manage templates. The AI-improve route (task 2.4)
    # carries its own stricter gate and is NOT part of this task. A server-generated uuid4
    # `template_id` means a create never collides; `{template_id}` addresses one template.
    RouteSpec(
        name="create_template",
        method=HttpMethod.POST,
        path="/members/templates",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Create a stored mail template (R2). Gate: members:export OR members:write."
        ),
    ),
    RouteSpec(
        name="list_templates",
        method=HttpMethod.GET,
        path="/members/templates",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "List the tenant's stored mail templates (metadata only, R2). "
            "Gate: members:export OR members:write."
        ),
    ),
    RouteSpec(
        name="get_template",
        method=HttpMethod.GET,
        path="/members/templates/{template_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Get a single stored mail template by its template_id (404 if absent, R2). "
            "Gate: members:export OR members:write."
        ),
    ),
    RouteSpec(
        name="update_template",
        method=HttpMethod.PUT,
        path="/members/templates/{template_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Update a stored mail template by its template_id (404 if absent, R2). "
            "Gate: members:export OR members:write."
        ),
    ),
    RouteSpec(
        name="delete_template",
        method=HttpMethod.DELETE,
        path="/members/templates/{template_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_EXPORT, CAP_MEMBERS_WRITE),
        self_service=False,
        summary=(
            "Delete a stored mail template (metadata + bodies; 404 if absent, R2). "
            "Gate: members:export OR members:write."
        ),
    ),
    # ── Schedules — CRUD (4), R5 (pivot-output-actions task 5.2) ─────────────────────
    #
    # Tenant-scoped recurring runs of a saved set + delivery (metadata on-plane
    # `schedule#<id>`, task 5.1). A schedule runs a set's stored delivery on a cron/rate
    # expression (EventBridge Scheduler wiring is task 5.3). The literal `/members/schedules`
    # prefix is disjoint from `/members/{member_id}` and the other `/members/...` literal
    # routes (analytics-sets, templates, field-config, export, me, search, column-preferences)
    # so there is no (method, path) collision or shadowing. DECLARED BEFORE the `{member_id}`
    # routes so the literal prefix matches FIRST (the router returns the first matching route
    # in declaration order for a method). A server-generated uuid4 `schedule_id` means a
    # create never collides; `{schedule_id}` addresses one schedule.
    #
    # GATE (R5, design §3/§8 — the CRITICAL rule): `members:admin` OR (`members:write` AND the
    # `["*"]` all-regions scope grant). A region-NARROWED members:write caller (e.g. region
    # ["Oost"]) must be REJECTED (403) — an unattended scheduled run must never replay a
    # partial regional slice. This is NOT a plain capability any-of; it needs a SCOPE check, so
    # it is marked `schedule_gate=True` and the edge's `_authorize_schedule_route` enforces the
    # combined capability+scope gate. `capabilities_any` lists the two involved capabilities so
    # the route is never "ungated" (the import-time integrity check passes), but the edge does
    # NOT treat it as a plain any-of for a schedule_gate route.
    RouteSpec(
        name="create_schedule",
        method=HttpMethod.POST,
        path="/members/schedules",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_ADMIN, CAP_MEMBERS_WRITE),
        schedule_gate=True,
        self_service=False,
        summary=(
            "Create a schedule for a saved set + delivery (R5; 422 if the set has no delivery "
            "block). Gate: members:admin OR (members:write + the ['*'] all-regions grant)."
        ),
    ),
    RouteSpec(
        name="list_schedules",
        method=HttpMethod.GET,
        path="/members/schedules",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_ADMIN, CAP_MEMBERS_WRITE),
        schedule_gate=True,
        self_service=False,
        summary=(
            "List the tenant's schedules (R5). Gate: members:admin OR (members:write + the "
            "['*'] all-regions grant)."
        ),
    ),
    RouteSpec(
        name="get_schedule",
        method=HttpMethod.GET,
        path="/members/schedules/{schedule_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_ADMIN, CAP_MEMBERS_WRITE),
        schedule_gate=True,
        self_service=False,
        summary=(
            "Get a single schedule by its schedule_id (404 if absent, R5). Gate: members:admin "
            "OR (members:write + the ['*'] all-regions grant)."
        ),
    ),
    RouteSpec(
        name="update_schedule",
        method=HttpMethod.PUT,
        path="/members/schedules/{schedule_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_ADMIN, CAP_MEMBERS_WRITE),
        schedule_gate=True,
        self_service=False,
        summary=(
            "Update a schedule by its schedule_id (404 if absent; 422 if a new set_id has no "
            "delivery block, R5). Gate: members:admin OR (members:write + ['*'] all-regions)."
        ),
    ),
    RouteSpec(
        name="delete_schedule",
        method=HttpMethod.DELETE,
        path="/members/schedules/{schedule_id}",
        group=RouteGroup.ANALYTICS,
        capability=None,
        capabilities_any=(CAP_MEMBERS_ADMIN, CAP_MEMBERS_WRITE),
        schedule_gate=True,
        self_service=False,
        summary=(
            "Delete a schedule (hard delete; 404 if absent, R5). Gate: members:admin OR "
            "(members:write + the ['*'] all-regions grant)."
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
            raise ValueError(
                f"duplicate route endpoint: {spec.method.value} {spec.path}"
            )
        seen_endpoints.add(endpoint)
        if spec.name in seen_names:
            raise ValueError(f"duplicate route name: {spec.name}")
        seen_names.add(spec.name)
        # A route must be gated by a capability, an any-of capability set, self-service, or a
        # combination — never nothing.
        if (
            spec.capability is None
            and not spec.capabilities_any
            and not spec.self_service
        ):
            raise ValueError(
                f"route {spec.name} has no gate "
                "(needs a capability, capabilities_any, or self_service)"
            )


_assert_route_map_is_consistent()


def route_names() -> tuple[str, ...]:
    """All route behaviour names in declaration order (parity-audit source of truth)."""
    return tuple(spec.name for spec in ROUTES)


def routes_by_group(group: RouteGroup) -> tuple[RouteSpec, ...]:
    """Return the routes belonging to one behaviour group."""
    return tuple(spec for spec in ROUTES if spec.group is group)
