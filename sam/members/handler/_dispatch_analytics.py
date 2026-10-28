"""
Members edge — per-resource dispatch: ANALYTICS-SETS / SCHEDULES / DELIVER / MAIL-RUNS /
PREFERENCES / TEMPLATES.

The subset of :func:`sam.members.handler._dispatch.dispatch_route` for the analytics/mailing
surface. Most routes delegate to the generic
:class:`~sam.members.domain.membership_service.MembershipService`; the deliver / ad-hoc send,
mail-run status reads, and template CRUD are backed by the STANDALONE services resolved via the
lazy accessors in :mod:`sam.members.handler._dispatch_services` (patchable test seams). The edge
stays THIN: ``tenant_id`` is authoritative from the verified context (never a body — verify-
before-trust), and the user-vs-admin mail-run scoping is derived from the verified entitlement.

:func:`dispatch_analytics` returns :data:`~sam.members.handler._dispatch_services.UNHANDLED`
when the route ``name`` is not one of this group's. Pure structural split (code-quality task 4)
— no behaviour change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sam.members.handler._dispatch_services import (
    MailRunNotFound,
    UNHANDLED,
    _caller_is_tenant_admin,
    _delivery_outcome_to_dict,
    _mail_failure_to_dict,
    _mail_run_to_dict,
    _new_run_id,
    _parse_ad_hoc_body,
    _require_path_param,
    _verified_email,
    _write_body,
)
from sam.members.handler._http import AcceptedResult, ParsedRequest
from sam.members.handler.routes import RouteSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sam.members.domain.membership_service import MembershipService
    from sam.members.handler.app import RequestContext


def dispatch_analytics(
    service: "MembershipService",
    spec: RouteSpec,
    request: ParsedRequest,
    ctx: "RequestContext",
) -> Any:
    """Delegate an ANALYTICS / SCHEDULE / MAIL / PREFERENCE / TEMPLATE route, or :data:`UNHANDLED`.

    The standalone-service accessors (``get_execute_and_deliver_service`` /
    ``get_mail_run_status_service`` / ``get_template_service``) are resolved through the
    :mod:`sam.members.handler._dispatch` module OBJECT at call time — NOT bound as imported
    values — so the test seam that patches ``_dispatch.get_*_service`` (the documented monkeypatch
    point, preserved across the by-resource split) still redirects the edge to an in-memory fake.
    """
    # Resolve the service accessors off the `_dispatch` facade at call time so a
    # `monkeypatch.setattr(_dispatch, "get_*_service", ...)` in a test is honoured (the accessors
    # are DEFINED in `_dispatch_services` and re-exported on `_dispatch`; binding the imported
    # value here would freeze past the patch point — the seam the deliver/mail/template tests use).
    from sam.members.handler import _dispatch as _dispatch_mod

    tenant_id = ctx.tenant_id
    name = spec.name

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
        deliver_service = _dispatch_mod.get_execute_and_deliver_service()
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
        send_service = _dispatch_mod.get_execute_and_deliver_service()
        outcome = send_service.send_ad_hoc(tenant_id, body, run_id, reply_to=reply_to)
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
        status_service = _dispatch_mod.get_mail_run_status_service()
        admin = _caller_is_tenant_admin(ctx)
        runs = status_service.list_runs(tenant_id, requester_sub=ctx.sub, admin=admin)
        return [_mail_run_to_dict(r) for r in runs]

    if name == "get_mail_run":
        # One run's tally + its FAILURE drill-down, subject to the SAME scope: a plain user may
        # drill only into a run they triggered (an existing-but-other-user run is reported as
        # absent → MailRunNotFound → 404, so a scoped caller cannot probe for another user's
        # runs); a Tenant_Admin may drill into any tenant run. A truly absent run is a 404 for
        # everyone. The service returns None in both not-visible cases; the edge maps it to a 404.
        run_id = _require_path_param(ctx, "run_id")
        status_service = _dispatch_mod.get_mail_run_status_service()
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
        status_service = _dispatch_mod.get_mail_run_status_service()
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
        template_service = _dispatch_mod.get_template_service()

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

    return UNHANDLED
