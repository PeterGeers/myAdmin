"""
Members edge — per-resource dispatch: CONFIG WRITE / config#fields CHANGE-OP / APPLICATION PUBLISH.

The subset of :func:`sam.members.handler._dispatch.dispatch_route` for the SAM-owned governance
writes. All three routes are backed by STANDALONE services resolved via the lazy accessors in
:mod:`sam.members.handler._dispatch_services`:

- ``write_config`` (``PUT /members/config/{configId}``) — the GENERIC whole-object door, closed
  to exactly ``{scope, mail}`` (``config#fields`` is deliberately excluded — spec 03 Task 7.1);
- ``write_config_fields`` (``PUT /members/config/fields``) — the ONLY client-reachable
  ``config#fields`` write, a Change-Op list dispatched op-by-op (a partial payload can never
  truncate the catalog);
- ``publish_application_form`` — the readiness-gated application-form publish.

``tenant_id`` is AUTHORITATIVE from the verified context — never read off the body (steering 39).
The edge has already verified the JWT + enforced the members:admin gate BEFORE reaching here.

:func:`dispatch_config` returns :data:`~sam.members.handler._dispatch_services.UNHANDLED` when
the route ``name`` is not one of this group's. Pure structural split (code-quality task 4) — no
behaviour change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from collections.abc import Mapping

from sam.members.domain.config_write_service import ConfigWriteValidationError
from sam.members.domain.look_and_feel_settings_service import (
    DEFAULT_PAGE_ID,
    LookAndFeelValidationError,
)

from sam.members.handler._dispatch_services import (
    UNHANDLED,
    _WRITABLE_CONFIG_IDS,
    _dispatch_config_fields_ops,
    _require_path_param,
    _write_body,
)
from sam.members.handler._http import ParsedRequest
from sam.members.handler.routes import RouteSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sam.members.domain.membership_service import MembershipService
    from sam.members.handler.app import RequestContext


def dispatch_config(
    service: "MembershipService",
    spec: RouteSpec,
    request: ParsedRequest,
    ctx: "RequestContext",
) -> Any:
    """Delegate a CONFIG-WRITE / config#fields / PUBLISH route, or :data:`UNHANDLED`.

    The standalone-service accessors (``get_config_fields_crud_service`` /
    ``get_config_write_service`` / ``get_application_publish_service``) are resolved through the
    :mod:`sam.members.handler._dispatch` module OBJECT at call time — NOT bound as imported
    values — so the test seam that patches ``_dispatch.get_*_service`` (the documented monkeypatch
    point, preserved across the by-resource split) still redirects the edge to an in-memory fake.
    """
    # Resolve the service accessors off the `_dispatch` facade at call time so a
    # `monkeypatch.setattr(_dispatch, "get_*_service", ...)` in a test is honoured (see the
    # sibling note in `_dispatch_analytics.dispatch_analytics`).
    from sam.members.handler import _dispatch as _dispatch_mod

    tenant_id = ctx.tenant_id
    name = spec.name

    # ── config#fields CHANGE-OP write — PUT /members/config/fields (spec 03 Task 2.7) ──
    #
    # The edge has already verified the JWT, resolved `tenant_id` from the verified token (never
    # the body — steering 39), and enforced the members:admin entitlement (the route's gate)
    # BEFORE reaching here. This branch dispatches the Change-Op list body op-by-op to the
    # standalone ConfigFieldsCrudService (design C1), which decides storage placement server-side
    # and issues a single version-conditional `update_item` path write per op — so a partial
    # payload can never truncate the catalog. Op-semantic / placement / version errors surface as
    # ConfigFieldsCrudError (→ 400) / StaleVersionError (→ 409) at the handler; `tenant_id` is
    # AUTHORITATIVE from the verified context. The whole-overlay body is NOT accepted here (Q7a).
    if name == "write_config_fields":
        crud_service = _dispatch_mod.get_config_fields_crud_service()
        return _dispatch_config_fields_ops(crud_service, tenant_id, request)

    # ── Config write — SAM-owned config#* rows (spec 02, Task 1.6) ───────────────────
    #
    # The single WRITE entry point for the three SAM-owned config rows. The edge has already
    # verified the bearer JWT, resolved `tenant_id` from the verified token (never the body —
    # verify-before-trust, Property 2), and enforced the Tenant_Admin entitlement (the route's
    # members:admin gate) BEFORE reaching here. This branch closes the GENERIC whole-object write
    # surface: `configId` MUST be in {scope, mail}. An id outside the set (incl. `fields` and
    # `views`) raises ConfigWriteValidationError → 400 at the edge, and the write path is NEVER
    # entered (no put_item). `config#fields` is excluded on purpose (spec 03 Task 7.1 —
    # R1.5/R11.1): it is writable ONLY via the Change-Op route (`write_config_fields` →
    # `apply_ops`), so the dangerous whole-row `put_config` replace is structurally unreachable
    # from a client; `views` stays rejected so Config_Views_Residue is never authored (R2.2/R2.5).
    # On success the service returns `{success, configId, version}` which the edge shapes into a
    # 200 (R1.3).
    if name == "write_config":
        config_id = _require_path_param(ctx, "configId")
        if config_id not in _WRITABLE_CONFIG_IDS:
            # Reject `fields`/`views`/unknown at the route — no write, deliberate caller-safe 400.
            # The GENERIC whole-object door is closed to exactly {scope, mail}: `config#fields` is
            # DELIBERATELY excluded (spec 03 Task 7.1 — R1.5/R11.1) so the dangerous whole-row
            # `put_config` replace is STRUCTURALLY unreachable from a client; `config#fields` is
            # writable ONLY via the Change-Op route (`write_config_fields` → `apply_ops`). `views`
            # stays rejected (Config_Views_Residue never authored, R2.5).
            raise ConfigWriteValidationError(
                f"configId must be one of {sorted(_WRITABLE_CONFIG_IDS)}; "
                f"{config_id!r} is not writable"
            )
        config_write_service = _dispatch_mod.get_config_write_service()
        return config_write_service.put_config(
            tenant_id, config_id, _write_body(request)
        )

    # ── Application-form PUBLISH — explicit, readiness-gated (spec 12 Task 2.1, §C4/R5) ──
    #
    # The edge has already verified the JWT, resolved `tenant_id` from the verified token (never
    # the body — verify-before-trust, Property 2), and enforced the members:admin entitlement
    # (the route's gate) BEFORE reaching here. This branch delegates to the standalone publish
    # service, which:
    #   1. Enforces READINESS before any (future) write (R5.4): a stored slug (R4, the form's
    #      public address) + a certified sender (the SAME authoritative is_send_ready predicate
    #      the submit gate uses — certified flag AND a projected domain, reused not duplicated) +
    #      ≥1 on-form field (counted off get_public_field_config, the single filter authority). A
    #      missing precondition raises PublishNotReady (→ a clear members:admin-facing 409 at the
    #      edge) and NO write is attempted — never a broken artifact.
    #   2. On a READY tenant, reaches the publish seam. Per the task-2.1 "scaffold, handler
    #      dormant" scope the live S3 render/write + CloudFront invalidation is task 2.2 — the
    #      seam raises PublishPipelineNotWired (→ a caller-safe 501 at the edge). Task 2.2 swaps
    #      the stub for the real pipeline; the success shape then mirrors the frontend caller's
    #      MembersApplicationPublishResult (success, slug, published_version, published_at).
    # `tenant_id` is AUTHORITATIVE from the verified context; this POST carries no path params and
    # the body is not trusted for tenant (the whole publish target is the verified tenant's form).
    if name == "publish_application_form":
        publish_service = _dispatch_mod.get_application_publish_service()
        return publish_service.publish(tenant_id)

    # ── Application-form SLUG author/change (bugfix-slug-lifecycle task 3.1) ──────────
    #
    # The MISSING client-reachable SAM slug WRITE (bugfix defect B). The edge has already verified
    # the JWT, resolved `tenant_id` from the verified token (NEVER the body — steering 39), and
    # enforced the members:admin gate BEFORE reaching here. This branch lifts the `{slug}` body
    # value and delegates to `ConfigFieldsCrudService.set_form_slug`, which validates (format then
    # SEC-4 prefix-ownership), claims the shared `_slugs/{slug}` marker, and persists
    # `config#fields.slug` via a SINGLE identity Change-Op (an explicit `null` CLEARS it). The
    # service owns ALL semantics: a malformed/reserved/out-of-prefix slug raises SlugAuthorRejected
    # (→ 422), a foreign-owned slug raises SlugAuthorConflict (→ 409), a stale row raises
    # StaleVersionError (→ 409) — all mapped caller-safe at the handler (never str(e)). The body is
    # trusted ONLY for the slug VALUE; `tenant_id` is AUTHORITATIVE from the verified context.
    if name == "set_application_form_slug":
        crud_service = _dispatch_mod.get_config_fields_crud_service()
        body = request.body if isinstance(request.body, dict) else {}
        # An ABSENT `slug` key is a malformed request (the one thing this route carries); surface a
        # caller-safe 422 via the service's own rejection rather than silently clearing the slug.
        if "slug" not in body:
            raise ConfigWriteValidationError(
                "request body must carry a 'slug' value (a string to author, or null to clear)"
            )
        return crud_service.set_form_slug(tenant_id, body.get("slug"))

    # ── Application-form slug PREFIX author/change (slug-prefix SAM-owned) ────────────
    #
    # The tenant's own public slug PREFIX author path (the SEC-4 stem every form slug must sit
    # under). The edge has verified the JWT, resolved `tenant_id` from the token (NEVER the body),
    # and enforced members:admin BEFORE here. This branch lifts the `{prefix}` body value and
    # delegates to `ConfigFieldsCrudService.set_public_prefix`, which validates slug-safe format
    # and persists `config#fields.public_prefix` via a SINGLE identity Change-Op (explicit `null`
    # CLEARS it). A malformed/reserved prefix raises SlugAuthorRejected (→ 422); a stale row raises
    # StaleVersionError (→ 409) — mapped caller-safe at the handler (never str(e)). The body is
    # trusted ONLY for the prefix VALUE; `tenant_id` is AUTHORITATIVE from the verified context.
    if name == "set_application_form_prefix":
        crud_service = _dispatch_mod.get_config_fields_crud_service()
        body = request.body if isinstance(request.body, dict) else {}
        if "prefix" not in body:
            raise ConfigWriteValidationError(
                "request body must carry a 'prefix' value (a string to author, or null to clear)"
            )
        return crud_service.set_public_prefix(tenant_id, body.get("prefix"))

    # ── Page look-and-feel — Layer-1 authoring GET (resolve current VALUES) (spec 15 Task 8) ──
    #
    # The edge has already verified the JWT, resolved `tenant_id` from the verified token (NEVER
    # the body — verify-before-trust, steering 39), and enforced the members:admin gate BEFORE
    # reaching here. This branch delegates to the standalone LookAndFeelSettingsService (design
    # C3), which reads the resolved `look_and_feel` slice for the VERIFIED tenant — VALUES only,
    # never generated CSS; an absent slice/key resolves to an empty map so Layer 2 applies its
    # SAM-owned defaults. `tenant_id` is AUTHORITATIVE from the verified context; this GET carries
    # no body and no tenant can be supplied by the client.
    if name == "get_look_and_feel":
        laf_service = _dispatch_mod.get_look_and_feel_settings_service()
        return {"settings": dict(laf_service.get_settings(tenant_id))}

    # ── Page look-and-feel — Layer-1 authoring WRITE (set one value / copy) (spec 15 Task 8) ──
    #
    # The edge has verified the JWT, resolved `tenant_id` from the token (NEVER the body), and
    # enforced members:admin BEFORE here. ONE body carries the action:
    #   * `{op:"copy", source_page, target_page}` → a one-time snapshot copy within the verified
    #     tenant (Req 9). A source from another tenant raises CrossTenantCopyError (→ 403); an
    #     unknown page id raises LookAndFeelValidationError (→ 422).
    #   * `{attribute, value}` (the default action) → author ONE attribute value (an explicit
    #     `null` value CLEARS it). An unsupported attribute or an out-of-set value raises
    #     LookAndFeelValidationError (→ 422) BEFORE any write, so the stored values are unchanged.
    # Both delegate to LookAndFeelSettingsService → the shared config#fields Change-Op seam, a
    # single version-conditional `update_item` (a stale row surfaces as StaleVersionError → 409).
    # The edge is THIN: it only lifts the body action; the service owns ALL validation/placement.
    # `tenant_id` is AUTHORITATIVE from the verified context — a rogue body tenant is ignored.
    if name == "write_look_and_feel":
        laf_service = _dispatch_mod.get_look_and_feel_settings_service()
        body = request.body if isinstance(request.body, Mapping) else {}

        if body.get("op") == "copy":
            # A one-time snapshot copy (Req 9). The page ids default to the single SAM-owned page
            # (the application form) today; an unknown id is rejected by the service. The verified
            # tenant scopes both read and write — `source_tenant_id` is carried so a cross-tenant
            # source is rejected (403), never silently honoured.
            source_page = body.get("source_page") or DEFAULT_PAGE_ID
            target_page = body.get("target_page") or DEFAULT_PAGE_ID
            return laf_service.copy_settings(
                tenant_id,
                source_page,
                target_page,
                source_tenant_id=body.get("source_tenant_id"),
                client_op_id=body.get("client_op_id"),
            )

        # Default action: author ONE attribute value. An ABSENT `attribute` key is a malformed
        # request (the one thing this action carries) — surface a caller-safe 422 via the service's
        # own rejection rather than guessing. `page` defaults to the application form today.
        if "attribute" not in body:
            raise LookAndFeelValidationError(
                "request body must carry an 'attribute' to author (and a 'value', or null to "
                "clear), or {op: 'copy'} to snapshot another page's values"
            )
        page_id = body.get("page") or DEFAULT_PAGE_ID
        return laf_service.set_setting(
            tenant_id,
            page_id,
            body.get("attribute"),
            body.get("value"),
            client_op_id=body.get("client_op_id"),
        )

    return UNHANDLED
