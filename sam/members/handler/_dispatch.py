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
(``app._dispatch`` / ``app._get_membership_service``) are preserved.

This module stays the **stable public entry** for route dispatch. The per-route ``if name
== ...`` body — formerly one ~1000-line chain — was split BY RESOURCE into three cohesive
group dispatchers (code-quality task 4), with the shared service seams / helpers / exceptions
in :mod:`sam.members.handler._dispatch_services`:

- :func:`sam.members.handler._dispatch_members.dispatch_members` — MEMBER / MEMBERSHIP /
  PAYMENT / CATALOG / DELEGATE (reads + writes);
- :func:`sam.members.handler._dispatch_analytics.dispatch_analytics` — ANALYTICS-SETS /
  SCHEDULES / DELIVER + AD-HOC / MAIL-RUN STATUS / PREFERENCES / TEMPLATES;
- :func:`sam.members.handler._dispatch_config.dispatch_config` — CONFIG WRITE / config#fields
  CHANGE-OP / APPLICATION PUBLISH.

:func:`dispatch_route` tries each group in turn; a group returns the
:data:`~sam.members.handler._dispatch_services.UNHANDLED` sentinel when the route ``name`` is
not one of its own, so the fall-through to the honest ``501`` (:class:`RouteNotImplemented`)
is preserved exactly. Pure structural split — zero behaviour change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# The exception the config-write dispatch raises (re-exported for the handler's error mapping
# and for ``app.ConfigWriteValidationError`` surface compat).
from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudError  # noqa: F401
from sam.members.domain.config_write_service import ConfigWriteValidationError  # noqa: F401
from sam.members.repository.members_cursor import CursorError  # noqa: F401

from sam.members.handler._dispatch_analytics import dispatch_analytics
from sam.members.handler._dispatch_config import dispatch_config
from sam.members.handler._dispatch_members import dispatch_members

# The shared seams / helpers / exceptions — re-exported here so ``app`` (and the tests that
# reach ``app.*``) keep their unchanged public import surface after the by-resource split.
from sam.members.handler._dispatch_services import (  # noqa: F401
    UNHANDLED,
    MailRunNotFound,
    RouteNotImplemented,
    StaleClientBundleError,
    _WRITABLE_CONFIG_IDS,
    _apply_one_config_fields_op,
    _caller_is_tenant_admin,
    _delivery_outcome_to_dict,
    _dispatch_config_fields_ops,
    _mail_failure_to_dict,
    _mail_job_to_envelope,
    _mail_run_to_dict,
    _new_run_id,
    _parse_ad_hoc_body,
    _parse_page_size,
    _query_flag,
    _require_path_param,
    _row_tuple,
    _str_tuple,
    _verified_email,
    _write_body,
    get_application_publish_service,
    get_config_fields_crud_service,
    get_config_write_service,
    get_execute_and_deliver_service,
    get_mail_run_status_service,
    get_template_service,
)
from sam.members.handler._http import ParsedRequest
from sam.members.handler.routes import RouteSpec

if (
    TYPE_CHECKING
):  # pragma: no cover - typing only, avoids an app<->_dispatch import cycle
    from sam.members.domain.membership_service import MembershipService
    from sam.members.handler.app import RequestContext


# The per-resource group dispatchers, tried in order. Each returns ``UNHANDLED`` when the route
# ``name`` is not its own. Group order only needs to be STABLE (each route ``name`` is handled
# by exactly one group; the router already decides literal-vs-``{param}`` precedence), which it
# is — so this preserves the exact fall-through of the original single ``if name == ...`` chain.
_DISPATCH_GROUPS = (dispatch_members, dispatch_analytics, dispatch_config)


# The READ routes task 3.2 implements, dispatched by their stable route ``name``; the WRITE
# routes (create/update/delete/delegates) are wired by task 5.2/5.3. Anything not
# wired falls through to :class:`RouteNotImplemented`.
def dispatch_route(
    service: "MembershipService",
    spec: RouteSpec,
    request: ParsedRequest,
    ctx: "RequestContext",
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
    The per-route body is split by resource across the group dispatchers in
    :data:`_DISPATCH_GROUPS`; each returns :data:`UNHANDLED` when the route is not its own.
    Anything not wired by any group raises :class:`RouteNotImplemented` (→ 501).
    """
    for group in _DISPATCH_GROUPS:
        result = group(service, spec, request, ctx)
        if result is not UNHANDLED:
            return result

    # Anything not wired by any group → honest 501.
    raise RouteNotImplemented(spec.name)


__all__ = [
    "ConfigWriteValidationError",
    "CursorError",
    "MailRunNotFound",
    "RouteNotImplemented",
    "StaleClientBundleError",
    "_parse_page_size",
    "_query_flag",
    "_require_path_param",
    "_write_body",
    "dispatch_route",
    "get_application_publish_service",
    "get_config_write_service",
    "get_execute_and_deliver_service",
    "get_mail_run_status_service",
    "get_template_service",
]
