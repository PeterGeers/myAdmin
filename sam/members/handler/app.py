"""
S5 Task 3.0 — the Members Lambda **entry point** (thin adapter; verified-auth edge).

This is the single Members module's HTTP edge (R1.1, design C1). It is deliberately
**thin** (steering: "the handler is an adapter, not the logic"): its whole job is

    parse → authenticate (verified) → tenant context → authorize → route → delegate → respond

and nothing else. No business rule, no field resolution, no scope math, and no DynamoDB
call lives here — those belong to the domain service and the repository, which the handler
*calls* (dependencies point downward only).

Scope of THIS task (3.0): adopt the verified-auth + entitlement toolkit **once** at the
edge (R1.1) so every route parses → authenticates (verified) → establishes tenant context
→ authorizes (``has_capability`` + scope) → routes → responds. The toolkit lives in
``sam/shared/auth_utils.py`` and is consumed here and nowhere else in the module:

- **Authenticate (verified):** :func:`sam.shared.auth_utils.get_verified_claims` reads
  claims from the API-Gateway Cognito authorizer's *verified* context, or (fallback) runs
  a full RS256 verification of the bearer token. There is **no** unverified path — a
  missing/invalid token is a 401, a JWKS outage a 503 (Property 2, ADR 0004). Client
  headers like ``X-Enhanced-Groups`` / ``X-Tenant`` are **never** consulted.
- **Tenant context (verify-before-trust):** the ``tenant_id`` is derived from the
  **verified** entitlement claim (``tenant_keys``), never from a client-supplied header or
  body. For the pilot the token answers for a single tenant; if the token does not answer
  (absent / unknown / malformed / overflow claim, or no tenant listed) the request is
  denied by default — the module's fail-safe policy (Property 3).
- **Authorize (``has_capability`` + scope):** each :class:`RouteSpec` declares the
  capability it requires and whether it is self-service. The edge calls
  :func:`sam.shared.auth_utils.has_capability`, which is **three-state**: ``True`` grant,
  ``False`` authoritative token-backed denial, ``None`` = the token does not answer →
  deny per module policy (never a silent allow). The **scope** decision runs behind a
  clean seam (:func:`_resolve_scope_access`) sourced from the caller's PROJECTED
  ``scopegrant#`` values (s5d, R2.2 — scope is an independent axis from
  ``user_tenant_scope``, not a decoded role name): ``["*"]`` → all, a subset → that subset,
  and a scope-requiring capability held without a projected grant → deny (Property 4).
- **Domain dispatch** — the generic membership engine (C2) is built in Steps 3/5. Until a
  route is implemented, dispatch raises :class:`RouteNotImplemented`, which the edge maps
  to ``501 Not Implemented`` — an honest "route exists, behaviour pending" answer.

So an authenticated + authorized request to a declared-but-unbuilt route returns 501; an
unauthenticated request returns 401; an authenticated-but-unentitled request returns 403;
an unknown path returns 404; a known path with the wrong method returns 405.

Internal layout (code-quality split M2 — a pure structural refactor, no behaviour change).
This module is the **stable facade / entry point**. The HTTP adapter helpers (request
parsing + response/error shaping) live in :mod:`sam.members.handler._http`, and the
per-route delegation lives in :mod:`sam.members.handler._dispatch`; both are re-exported
here so the module's public surface — ``handler``, ``RouteNotImplemented``,
``has_capability``, ``_response`` / ``_json_default``, the ``_*_OVERRIDE`` test seams, and
``_get_membership_service`` / ``_dispatch`` / ``_resolve_scope_access`` /
``_scope_access_from_grant`` — is unchanged. The auth/tenant/scope resolution (which is
coupled to the module-level provider-override seams the tests rebind) stays HERE, and the
thin ``_dispatch(spec, request, ctx)`` wrapper resolves the service via the patchable
``_get_membership_service`` before delegating, so every existing monkeypatch seam holds.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sam.members.domain.analytics_set import AnalyticsSetValidationError
from sam.members.domain.error_codes import FieldError  # noqa: F401 (surface compat)
from sam.members.domain.execute_and_deliver import DeliveryNotConfigured
from sam.members.domain.field_resolver import TenantOverlay, TenantOverlayProvider
from sam.members.domain.fixed_fields import (
    MembershipStatus,  # noqa: F401 (surface compat)
)
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import (
    DEFAULT_SCOPE_DIMENSION_KEY,
    AnalyticsSetConflict,
    AnalyticsSetNotFound,
    MemberNotFound,
    MembershipService,
    MembershipTypeConflict,
    MembershipTypeNotFound,
    MemberValidationError,
    ScheduleNotFound,
    ScopeDenied,
    TransitionDenied,
)
from sam.members.domain.membership_type_catalog import MembershipTypeValidationError
from sam.members.domain.scope_access import ScopeAccess, resolve_scope_access
from sam.members.domain.template import TemplateValidationError
from sam.members.domain.template_service import TemplateNotFound
from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfigProvider,
    ScopeDimension,
)
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.domain.view_contexts import ViewContext, ViewContextsProvider
from sam.members.domain.mail_gate import MailGateProvider

# ── Per-route dispatch (the generic membership engine delegation) — re-exported ────────
from sam.members.handler._dispatch import (
    RouteNotImplemented,
    dispatch_route,
    get_execute_and_deliver_service,  # noqa: F401 (surface compat: tests reach app.get_execute_and_deliver_service)
    get_template_service,  # noqa: F401 (surface compat: tests reach app.get_template_service)
)

# ── HTTP adapter helpers (request parsing + response shaping) — re-exported ────────────
from sam.members.handler._http import (
    AcceptedResult,
    ParsedRequest,
    _error,
    _field_errors_array,
    _json_default,  # noqa: F401 (surface compat: tests reach app._json_default)
    _parse_request,
    _reasons_array,
    _response,
)
from sam.members.handler.router import (
    MethodNotAllowed,
    NoRouteMatch,
    RouteMatch,
    get_router,
)
from sam.members.handler.routes import (
    CAP_MEMBERS_ADMIN,
    CAP_MEMBERS_WRITE,
    RouteSpec,
)
from sam.members.repository.members_repository import (
    DynamoDbMembersRepository,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks
from sam.shared.auth_utils import (
    DecodedEntitlements,
    InvalidTokenError,
    ServiceUnavailableError,
    get_entitlements_from_claims,
    get_groups,
    get_verified_claims,
    has_capability,
)

logger = logging.getLogger(__name__)

# ── Projection-backed config/overlay providers (S5b task 8.2 — design C6) ─────────────
#
# The tenant scope config (:class:`ScopeConfigProvider`) and the per-tenant field overlay
# (:class:`TenantOverlayProvider`) now come from the S5b **governance projection**, read via
# :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`, instead
# of the S5 in-memory ``Static*`` reference providers. This is the swap the S5 seams always
# documented ("a later step swaps in a DynamoDB-backed provider behind the same seam") — no
# domain code changes; the reader already duck-types both Protocols. Lifecycle config is NOT
# part of the projection, so ``_LIFECYCLE_PROVIDER`` below stays a ``Static*`` provider.
#
# PER-INVOCATION FRESHNESS (correctness, R5). ``MembersProjectionReader`` holds a
# ``_partition_cache`` that is meant to live for **one** request (a tenant partition Queried
# at most once per invocation). Reusing a single reader across warm Lambda invocations would
# let that cache go STALE — a Tenant-Admin config/grant edit re-projected by the sync would
# not be seen until the next cold start. So we DO NOT freeze one reader: we build a FRESH
# reader per request wherever a config/overlay read happens (mirroring how
# ``sam/pretokengen`` reads its projection once per invocation, but re-derived each request
# here because the Members edge stays warm and must reflect edits within the projection's
# bounded delay). Constructing a reader is cheap — its table resolves lazily + fail-fast on
# the first Query, so import and the auth-only tests still touch NO AWS.
#
# TEST SEAM. ``_SCOPE_CONFIG_PROVIDER_OVERRIDE`` / ``_OVERLAY_PROVIDER_OVERRIDE`` let a test
# inject a provider (a ``Static*`` provider, or a ``MembersProjectionReader`` over a fake /
# local dynamodb-local table) without an AWS round-trip. When unset (production), each read
# builds a fresh projection reader. Tests set these at the same cold-start seam they already
# use for ``_get_membership_service`` (see ``sam/tests/conftest.py``).

#: Test-only override for the scope-config provider (``None`` in production → fresh reader).
_SCOPE_CONFIG_PROVIDER_OVERRIDE: ScopeConfigProvider | None = None

#: Test-only override for the overlay provider (``None`` in production → fresh reader).
_OVERLAY_PROVIDER_OVERRIDE: TenantOverlayProvider | None = None

#: Test-only override for the view-contexts provider (``None`` in production → fresh reader).
#: Mirrors :data:`_OVERLAY_PROVIDER_OVERRIDE` — a test injects a ``StaticViewContextsProvider``
#: (or a ``MembersProjectionReader`` over a fake table) so the field-config endpoint's
#: ``view_contexts`` can be driven without an AWS round-trip. When unset (production), each read
#: builds a fresh projection reader (see :class:`_ProjectionViewContextsProvider`).
_VIEW_CONTEXTS_PROVIDER_OVERRIDE: ViewContextsProvider | None = None

#: Test-only override for the mail-gate provider (``None`` in production → fresh reader).
#: Mirrors :data:`_VIEW_CONTEXTS_PROVIDER_OVERRIDE` — a test injects a
#: ``StaticMailGateProvider`` (or a ``MembersProjectionReader`` over a fake table) so the
#: field-config endpoint's ``mail_enabled`` flag (pivot-output-actions R0/R1, design §6.3)
#: can be driven without an AWS round-trip. When unset (production), each read builds a fresh
#: projection reader (see :class:`_ProjectionMailGateProvider`).
_MAIL_GATE_PROVIDER_OVERRIDE: MailGateProvider | None = None


def _new_projection_reader() -> MembersProjectionReader:
    """Build a FRESH projection reader for one request (per-invocation cache, R5).

    A new reader per read means its per-invocation ``_partition_cache`` never outlives the
    request, so a re-projected config/grant edit is picked up on the next request rather than
    only at cold start. The table resolves lazily + fail-fast on the first Query, so building
    the reader touches no AWS.
    """
    return MembersProjectionReader()


class _ScopeGrantsReader(Protocol):
    """The minimal seam the edge needs to read a caller's PROJECTED scope grants (C5).

    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`
    satisfies this by duck-typing (``get_scope_grants(tenant_id, email) -> {dim: values}``);
    a test may inject any object with the same method.
    """

    def get_scope_grants(
        self, tenant_id: str, email: str
    ) -> Mapping[str, list[str]]: ...


#: Test-only override for the scope-GRANT reader (``None`` in production → fresh reader).
#: The scope-config provider (:data:`_SCOPE_CONFIG_PROVIDER_OVERRIDE`) supplies the tenant's
#: ``ScopeConfig`` shape; this override supplies the caller's PROJECTED grants (task 8.3), so
#: a test can drive the projected-grant model (a Noord-scoped caller → ``["Noord"]``, an
#: all-access caller → ``["*"]``, a ``required_for``-capability caller with no grant → deny)
#: without an AWS round-trip. When unset (production), each request reads grants off the same
#: fresh :class:`MembersProjectionReader` used for the scope config (one Query per partition).
_SCOPE_GRANTS_READER_OVERRIDE: _ScopeGrantsReader | None = None


def _scope_config_provider() -> ScopeConfigProvider:
    """The active :class:`ScopeConfigProvider` for this request (override, else fresh reader).

    Returns the test override when one is installed; otherwise a fresh projection reader so
    the scope config reflects the current projection (never a stale warm-container cache).
    """
    if _SCOPE_CONFIG_PROVIDER_OVERRIDE is not None:
        return _SCOPE_CONFIG_PROVIDER_OVERRIDE
    return _new_projection_reader()


def _scope_grants_reader() -> _ScopeGrantsReader:
    """The active scope-GRANT reader for this request (override, else fresh reader).

    Returns the test override when one is installed; otherwise a fresh projection reader.
    Production callers pass a single per-request reader (see :func:`_authenticate_and_authorize`)
    so the tenant partition is Queried at most once per invocation (Property 5).
    """
    if _SCOPE_GRANTS_READER_OVERRIDE is not None:
        return _SCOPE_GRANTS_READER_OVERRIDE
    return _new_projection_reader()


class _ProjectionOverlayProvider:
    """A thin :class:`TenantOverlayProvider` indirection over a per-call fresh reader (C6).

    The :class:`MembershipService` is a lazy module-level singleton that builds its
    :class:`FieldResolver` **once** from an overlay provider. To avoid staleness without
    rebuilding the service per request (which would touch the domain / the existing tests'
    injection seam), the service's overlay provider is this stable indirection: every
    ``get_overlay`` call delegates to a FRESH :class:`MembersProjectionReader` (or the test
    override), so the resolved field config always reflects the current projection while the
    domain and the service singleton stay UNCHANGED.
    """

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        if _OVERLAY_PROVIDER_OVERRIDE is not None:
            return _OVERLAY_PROVIDER_OVERRIDE.get_overlay(tenant_id)
        return _new_projection_reader().get_overlay(tenant_id)


#: The overlay provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionOverlayProvider`).
_OVERLAY_PROVIDER: TenantOverlayProvider = _ProjectionOverlayProvider()


class _ProjectionScopeConfigProvider:
    """A thin :class:`ScopeConfigProvider` indirection over a per-call fresh reader (S5j / C6).

    EXACTLY mirrors :class:`_ProjectionOverlayProvider`. The :class:`MembershipService` captures
    its providers once at cold start; the service's field resolver needs the tenant's scope
    config so a scope-dimension-backed overlay ``enum`` (h-dcn ``region``) can source its
    dropdown ``choices`` from ``scope_dimensions.values`` (design D1a). Delegating each
    ``get_scope_config`` to a FRESH :class:`MembersProjectionReader` (or the test override)
    keeps the choices in step with the current projection without rebuilding the service, and
    honours the same ``_SCOPE_CONFIG_PROVIDER_OVERRIDE`` seam the read path already uses.
    """

    def get_scope_config(self, tenant_id: str):
        return _scope_config_provider().get_scope_config(tenant_id)


#: The scope-config provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionScopeConfigProvider`). Without this the
#: service's `_scope_vocab` is empty and a scope-dimension enum with no inline choices (region)
#: is rejected → field-config 502. (This was the missing wiring in the first s5j deploy.)
_SCOPE_CONFIG_PROVIDER_FOR_SERVICE: ScopeConfigProvider = (
    _ProjectionScopeConfigProvider()
)


class _ProjectionViewContextsProvider:
    """A thin :class:`ViewContextsProvider` indirection over a per-call fresh reader (C-VIEW).

    S5c task 3.2 — the view-contexts seam wired at the module edge, EXACTLY mirroring
    :class:`_ProjectionOverlayProvider`. The :class:`MembershipService` is a lazy module-level
    singleton that captures its providers once; to reflect a re-projected ``config#views`` edit
    without rebuilding the service per request, its view-contexts provider is this stable
    indirection: every ``get_view_contexts`` call delegates to a FRESH
    :class:`MembersProjectionReader` (or the test override), so the field-config endpoint's
    ``view_contexts`` always reflects the current projection while the domain and the service
    singleton stay UNCHANGED. Empty-is-valid is owned by the reader (≥1 default context, R5.1).
    """

    def get_view_contexts(self, tenant_id: str) -> tuple[ViewContext, ...]:
        if _VIEW_CONTEXTS_PROVIDER_OVERRIDE is not None:
            return _VIEW_CONTEXTS_PROVIDER_OVERRIDE.get_view_contexts(tenant_id)
        return _new_projection_reader().get_view_contexts(tenant_id)


#: The view-contexts provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionViewContextsProvider`).
_VIEW_CONTEXTS_PROVIDER: ViewContextsProvider = _ProjectionViewContextsProvider()


class _ProjectionMailGateProvider:
    """A thin :class:`MailGateProvider` indirection over a per-call fresh reader (§6.3).

    pivot-output-actions R0/R1 task 1.3 — the mail-enabled gate seam wired at the module edge,
    EXACTLY mirroring :class:`_ProjectionViewContextsProvider`. The :class:`MembershipService`
    is a lazy module-level singleton that captures its providers once; to reflect a
    re-projected ``config#mail`` edit (the tenant-admin module flips the flag, it re-projects)
    without rebuilding the service per request, its mail-gate provider is this stable
    indirection: every ``is_mail_enabled`` call delegates to a FRESH
    :class:`MembersProjectionReader` (or the test override), so the field-config endpoint's
    ``mail_enabled`` always reflects the current projection while the domain and the service
    singleton stay UNCHANGED. Fail-closed is owned by the reader (missing row → ``False``, R0).
    """

    def is_mail_enabled(self, tenant_id: str) -> bool:
        if _MAIL_GATE_PROVIDER_OVERRIDE is not None:
            return _MAIL_GATE_PROVIDER_OVERRIDE.is_mail_enabled(tenant_id)
        return _new_projection_reader().is_mail_enabled(tenant_id)


#: The mail-gate provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionMailGateProvider`).
_MAIL_GATE_PROVIDER: MailGateProvider = _ProjectionMailGateProvider()

#: The tenants' membership-lifecycle configuration, carried as **data** (design C2, never an
#: ``if tenant == ...``): h-dcn is simply the first ``tenant_id`` the provider knows about
#: (its declarative state graph + guards, :data:`HDCN_LIFECYCLE_CONFIG`). A tenant with no
#: configured lifecycle has no state machine, so a transition request for it is denied (never
#: a silent allow). In-memory default; a later step swaps in a DynamoDB-backed provider behind
#: the same :class:`~sam.members.domain.lifecycle_config.LifecycleConfigProvider` seam.
_LIFECYCLE_PROVIDER = StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG})


def _build_tenant_hooks() -> TenantHookRegistry:
    """Build the unified Rung-3 hook registry with each tenant's hooks registered (design C5).

    Carried as **data/wiring** (never an ``if tenant == ...`` in the core): h-dcn's concrete
    hooks are bound by :func:`~sam.members.tenants.hdcn.hooks.register_hdcn_hooks` — the ONLY
    place h-dcn logic lives (Property 5). An unregistered tenant/hook resolves to the safe
    generic default. The write path resolves ``validate_member`` / ``derive_member_number``
    through this registry and the engine dispatches ``on_transition`` through its transition
    view (see :meth:`MembershipService.__init__`).
    """
    registry = TenantHookRegistry()
    register_hdcn_hooks(registry)
    return registry


#: The module-level unified hook registry (built once, mirrors the scope/overlay providers).
_TENANT_HOOKS = _build_tenant_hooks()

__all__ = [
    "AuthorizationError",
    "RouteNotImplemented",
    "TenantResolutionError",
    "handler",
]


# ── Auth + tenant context + authorization (task 3.0 — the verified-auth edge) ─────────


class AuthorizationError(Exception):
    """Raised when a verified caller is not authorized for the route (→ 403).

    Distinct from :class:`sam.shared.auth_utils.InvalidTokenError` (401 — *who are you?*):
    the caller is authenticated, but the verified entitlement does not grant the route's
    capability (or the required scope). Authorization derives **only** from verified
    claims / entitlement (Property 2); this is never raised from an unverified source.
    """

    def __init__(self, message: str = "Forbidden"):
        self.message = message
        super().__init__(message)


class TenantResolutionError(AuthorizationError):
    """Raised when tenant context cannot be established from the verified token (→ 403).

    The active tenant is the ``X-Tenant`` selection VALIDATED against the verified
    entitlement's ``tenant_keys`` (s5f) — the header selects among verified tenants, it never
    grants one. Raised when no valid active tenant can be established: the token does not
    answer (absent / unknown / malformed / overflow claim, or empty entitlement), OR the
    selected tenant is not in ``tenant_keys``, OR no tenant was selected and the caller has
    more than one (ambiguous). The module denies by default (Property 3 fail-safe); it never
    guesses a tenant and never trusts an unverified one.
    """

    def __init__(self, message: str = "No tenant context"):
        super().__init__(message)


@dataclass(frozen=True)
class RequestContext:
    """The authenticated + authorized context a route runs under.

    Every field is derived from **verified** material (the API-Gateway-verified authorizer
    context or a full RS256 verification) — never from a client-supplied header/body
    (Property 2). Populated by :func:`_authenticate_and_authorize` at the edge and passed
    down to the domain dispatch.

    Attributes:
        tenant_id: The tenant the request operates under, derived from the verified
            entitlement (``tenant_keys``). Always set on an authorized context.
        sub: The verified Cognito subject (stable user id), if present.
        groups: The caller's roles from the verified ``cognito:groups`` claim.
        capability: The capability the route required and the caller was granted (``None``
            for a pure self-service route).
        allowed_scopes: The scope the caller may act within for this tenant, as a
            **per-dimension map** ``{dimension_key: [values]}`` (s5d task 4.1, ODx2 Option
            A). The edge resolves EVERY enabled dimension independently: each dimension maps
            to ``["*"]`` (tenant-wide for that dimension), a subset (scoped for that
            dimension), or ``[]`` (no grant → deny for that dimension). A tenant-wide
            (un-partitioned) tenant resolves to a single ``{DEFAULT: ["*"]}`` entry. The
            domain layer enforces per-dimension: today the single-dimension case is
            preserved; task 4.2 formalizes AND-across-dimensions in ``_in_scope``.
        claims: The full verified claims dict (for layers that need more).
        path_params: The path parameters the router extracted from the matched route
            (e.g. ``{"member_id": "M-1"}`` for ``/members/{member_id}``). Threaded from the
            router's :class:`~sam.members.handler.router.RouteMatch` so the domain dispatch
            can reach ``{member_id}`` / ``{membership_id}`` — the edge stays thin and only
            carries them through.
        scope_dimension_key: The tenant's first-enabled scope-dimension key (h-dcn:
            ``"region"``), derived **generically** from the tenant's scope config, or ``None``
            for a tenant-wide (un-partitioned) tenant. **Vestigial since s5d task 4.2**: the
            domain scope check now iterates the full per-dimension ``allowed_scopes`` map
            (AND-across-dimensions, Property 6) instead of narrowing on a single gating
            dimension, so the read/write dispatch no longer threads this into the service. It
            is retained on the context for diagnostics and any future single-dimension caller.
    """

    tenant_id: str | None = None
    sub: str | None = None
    groups: list[str] = field(default_factory=list)
    capability: str | None = None
    allowed_scopes: dict[str, list[str]] = field(default_factory=dict)
    claims: Mapping[str, Any] = field(default_factory=dict)
    path_params: Mapping[str, str] = field(default_factory=dict)
    scope_dimension_key: str | None = None


def _requested_tenant_from_request(request: ParsedRequest) -> str | None:
    """The client's SELECTED active tenant from the ``X-Tenant`` header, or ``None`` (s5f).

    A per-request SELECTOR, never an authorization: the returned value is validated against
    the verified entitlement's ``tenant_keys`` by :func:`_establish_tenant_context` before it
    is trusted (it can only ever *pick among* tenants the verified token already carries,
    never introduce a new one — Property 2).

    Case-insensitive on the header NAME (API Gateway REST v1 preserves the client casing
    ``X-Tenant``; HTTP API v2 lowercases to ``x-tenant``), mirroring
    :func:`sam.shared.auth_utils._bearer_token_from_event`. The header VALUE is returned
    verbatim (tenant ids are case-sensitive); an empty/whitespace value reads as ``None``
    ("no selection") so a blank header cannot masquerade as a choice.
    """
    headers = request.headers or {}
    for name, value in headers.items():
        if isinstance(name, str) and name.lower() == "x-tenant":
            if isinstance(value, list):
                value = value[0] if value else None
            if isinstance(value, str):
                v = value.strip()
                return v or None
    return None


def _establish_tenant_context(
    entitlement: DecodedEntitlements, requested_tenant: str | None
) -> str:
    """Resolve the request's ACTIVE ``tenant_id`` (s5f — verify-before-trust + selection).

    The active tenant is a PER-REQUEST selection: the client sends the chosen tenant via the
    ``X-Tenant`` header (already extracted into ``requested_tenant`` by
    :func:`_requested_tenant_from_request`), and the edge VALIDATES that selection against the
    verified entitlement's ``tenant_keys``. The header SELECTS among the caller's verified
    tenants; it NEVER grants one — a selected tenant absent from ``tenant_keys`` is denied, so
    no unverified tenant is ever operated under (Property 2). A single-tenant user is the
    degenerate case: one entitled tenant, no ambiguity.

    ``tenant_keys`` is the tenants the user has MEMBER-module capabilities for (from
    ``custom:entitlements``) — a capability-scoped set, NOT the broad ``custom:tenants``. So a
    tenant the user can log into but which grants no members capability (e.g. no MEMBERS
    module) is simply not in ``tenant_keys`` and is correctly denied here: the active tenant
    bounds capability.

    Resolution order:
    1. Non-answering token (``fallback_required`` / ``is_overflow``) → deny (fail-safe,
       Property 3) — the header cannot rescue a token that carries no usable entitlement.
    2. Empty ``tenant_keys`` (a valid, handled empty entitlement) → deny (no verified tenant
       to select from).
    3. ``requested_tenant`` present → return it IFF it is in ``tenant_keys``, else deny
       (the selector must name a verified tenant).
    4. No selector + exactly one entitled tenant → that tenant (single-tenant back-compat).
    5. No selector + multiple entitled tenants → deny (ambiguous; picking one could expose
       the wrong tenant's members). NEVER default-to-first.

    NO hardcoded/default tenant, NO env fallback (no ``h-dcn`` default, no
    ``MEMBERS_LOCAL_TENANT_ID``): the active tenant derives ONLY from the validated selector
    or the single-tenant degenerate case.

    Raises:
        TenantResolutionError: No valid active tenant could be established (all deny paths
            → 403 in :func:`handler`).
    """
    # (1) The token does not carry a usable per-user answer → deny by default (Property 3).
    if entitlement.fallback_required or entitlement.is_overflow:
        raise TenantResolutionError("Token does not carry a usable tenant entitlement")

    tenant_keys = entitlement.tenant_keys
    # (2) Empty entitlement (valid, handled) → no verified tenant to select from.
    if not tenant_keys:
        raise TenantResolutionError("Verified entitlement lists no tenant")

    # (3) A selection MUST be a verified tenant — the header selects, never grants. This is
    #     also the "active tenant grants no members capability" deny (the selected tenant is
    #     not in the capability-scoped tenant_keys).
    if requested_tenant:
        if requested_tenant in tenant_keys:
            return requested_tenant
        raise TenantResolutionError(
            "Selected tenant is not in the verified entitlement"
        )

    # (4) No selector, single entitled tenant → that tenant (back-compat, no ambiguity).
    if len(tenant_keys) == 1:
        return tenant_keys[0]

    # (5) No selector, multiple entitled tenants → ambiguous; deny rather than guess (OD1).
    raise TenantResolutionError("No tenant selected; specify X-Tenant")


def _gating_dimension_key(
    tenant_id: str, provider: ScopeConfigProvider | None = None
) -> str | None:
    """The key of the dimension that gates this tenant's reads, or ``None`` if tenant-wide.

    Derived **generically** from the tenant's scope config (data, via
    :func:`_scope_config_provider`, now the projection reader): the first enabled dimension's
    ``key`` (h-dcn wires a single ``region`` dimension). A tenant with no enabled dimension
    is un-partitioned → ``None`` (the domain filter never narrows on a dimension for a
    tenant-wide caller). Nothing tenant-specific is hardcoded — h-dcn is just the first
    tenant whose projected config carries a dimension.

    ``provider`` lets the caller pass the SAME per-request reader used for the grant read so
    the tenant partition is Queried at most once per invocation (Property 5); when omitted a
    fresh provider is resolved.
    """
    if provider is None:
        provider = _scope_config_provider()
    config = provider.get_scope_config(tenant_id)
    enabled = config.enabled()
    if not enabled:
        return None
    return enabled[0].key


def _scope_access_from_grant(
    tenant_id: str, dimension: ScopeDimension, granted_values: list[str] | None
):
    """Map a caller's PROJECTED grant values for one dimension to a :class:`ScopeAccess` (C5).

    s5d clean break (R2.2/R8.1, design → Projection Components item 4, Property 5): scope is
    an independent axis sourced from ``user_tenant_scope`` → the projected ``scopegrant#`` row,
    NOT decoded from a role name. The projection carries the RESOLVED grant **values** for the
    dimension (``["*"]`` for all-access, a subset for scoped, or the dimension is ABSENT for
    none). This seam maps those values DIRECTLY onto a :class:`ScopeAccess` — no ``Regio_*``
    role synthesis, no ``all_wildcard`` role name, no round-trip through the role decoder:

    - ``["*"]`` (all-access, R2.4) → ``allowed_scopes=["*"]``, ``access_type="all"``,
      ``full_access=True``.
    - a non-empty subset (scoped, R2.5) → exactly that subset, normalized to the dimension's
      declared value order (unknown values dropped), ``access_type="scoped"``.
    - ABSENT (``None``) or an empty/all-unknown grant → the deny-by-default branch
      (``[]`` / ``access_type="none"``) — a ``required_for`` capability held without a
      projected grant is denied (R2.6, Property 4).
    """
    # All-access sentinel: the projected ["*"] grant is tenant-wide (R2.4).
    if granted_values is not None and list(granted_values) == [WILDCARD]:
        return ScopeAccess(
            full_access=True, allowed_scopes=[WILDCARD], access_type="all"
        )

    # Scoped: keep only the dimension's declared values, in declared order, de-duplicated
    # (R2.5). The projected grant is authoritative; an unknown value (belt-and-suspenders)
    # is simply dropped rather than trusted.
    if granted_values:
        granted = set(granted_values)
        subset = [v for v in dimension.normalized_values() if v in granted]
        if subset:
            return ScopeAccess(
                full_access=False, allowed_scopes=subset, access_type="scoped"
            )

    # Absent / empty / all-unknown grant → deny-by-default (R2.6, Property 4).
    return ScopeAccess(full_access=False, allowed_scopes=[], access_type="none")


def _resolve_scope_access(
    spec: RouteSpec,
    tenant_id: str,
    claims: Mapping[str, Any],
    *,
    config_provider: ScopeConfigProvider | None = None,
    grants_reader: _ScopeGrantsReader | None = None,
) -> dict[str, list[str]]:
    """Resolve the caller's allowed scope as a PER-DIMENSION map — the scope seam (C5).

    s5d task 4.1 (R3.3/R6.2, ODx2 Option A, design → enforcement item 3, Property 6):
    the edge no longer collapses scope onto a single gating dimension. It resolves EVERY
    enabled dimension **independently** and returns ``{dimension_key: [values]}`` — so a
    multi-dimension tenant (e.g. ``region`` AND ``age_group``) carries a grant per axis and
    the domain (task 4.2) can enforce AND-across-dimensions. Single-dimension tenants
    (h-dcn's ``region`` today) are the N=1 case — a one-entry map — behaviour unchanged.

    The edge stays **thin** — it holds no scope logic:

    1. Resolve the tenant's :class:`ScopeConfig` (data, via the per-request projection
       reader). A tenant with no enabled dimension → tenant-wide: a single
       ``{DEFAULT_SCOPE_DIMENSION_KEY: ["*"]}`` entry (the R3.2 collapse, expressed as a
       one-entry map so the domain sees a uniform shape).
    2. Read the caller's PROJECTED grants ONCE via ``get_scope_grants(tenant_id, email)``
       (task 8.1), keyed by the caller's VERIFIED ``email`` claim (verify-before-trust —
       scope is never read from a header/body or a token scope claim; there is none). The
       returned map carries ``{dimension: values}`` for every dimension the caller holds a
       grant in; a dimension ABSENT from it is the deny signal for that dimension.
    3. LOOP over ALL enabled dimensions (no ``enabled[0]`` shortcut). For each, delegate to
       :func:`_scope_access_from_grant`, which maps the projected VALUES DIRECTLY onto a
       :class:`ScopeAccess` (s5d clean break — no role decode): ``["*"]`` → ``["*"]``
       (all-access, R2.4); a subset → that subset (scoped, R2.5); ABSENT/empty → ``[]``
       (deny-by-default, R2.6, Property 4). A dimension with no grant maps to ``[]``.

    ``config_provider`` / ``grants_reader`` let the caller pass a SINGLE per-request reader for
    both the config and grant reads so the tenant partition is Queried at most once per
    invocation (Property 5); when omitted each read resolves a fresh provider.
    """
    if config_provider is None:
        config_provider = _scope_config_provider()
    if grants_reader is None:
        grants_reader = _scope_grants_reader()

    config = config_provider.get_scope_config(tenant_id)

    # A tenant with no enabled dimension → tenant-wide (the R3.2 collapse), expressed as a
    # single-entry map keyed on the default dimension so the domain sees a uniform shape.
    enabled = config.enabled()
    if not enabled:
        wildcard = list(resolve_scope_access(tenant_id, None, []).allowed_scopes)
        return {DEFAULT_SCOPE_DIMENSION_KEY: wildcard}

    # The caller's scope comes from the PROJECTED grants (C5), keyed by the verified email —
    # read ONCE, then consumed per dimension below (one Query per partition, Property 5).
    email = claims.get("email")
    grants = grants_reader.get_scope_grants(tenant_id, str(email) if email else "")

    # LOOP over ALL enabled dimensions (drop the enabled[0] shortcut). Each dimension is
    # resolved independently; a dimension with no grant maps to [] (deny for that dimension).
    allowed: dict[str, list[str]] = {}
    for dimension in enabled:
        granted_values = grants.get(dimension.key)
        granted_list = list(granted_values) if granted_values is not None else None
        access = _scope_access_from_grant(tenant_id, dimension, granted_list)
        allowed[dimension.key] = list(access.allowed_scopes)
    return allowed


# ── Fallbacks removed — capability AND tenant come from the verified entitlement only ─
#
# The s5b local-dev shortcuts are GONE (R6.1 + R6.2, design C-UNWIND, Property 5):
#
# - The capability fallback (``_local_dev_group_grants_capability`` /
#   ``_local_auth_fallback_grants``, gated by ``MEMBERS_LOCAL_AUTH_FALLBACK``) was removed in
#   task 0.1: capability is carried by the real S4 channel (``custom:entitlements`` via
#   PreTokenGen); no code path derives a Members capability from ``cognito:groups``.
# - The tenant fallback (``_local_dev_tenant_fallback`` / ``MEMBERS_LOCAL_TENANT_ID``) is
#   removed here in task 0.2: the ``tenant_id`` resolves SOLELY from the verified entitlement
#   (``_establish_tenant_context``). There is no ``MEMBERS_LOCAL_TENANT_ID`` substitution and
#   no hardcoded/default tenant anywhere. When the verified token carries no usable tenant the
#   edge denies honestly (403 via :class:`TenantResolutionError`) — the correct pre-wiring
#   state until the PreTokenGen channel is switched on (Phase 5).
#
# ``has_capability`` off the verified entitlement is the sole capability authority (a
# ``None``/``False`` is an honest 403, never softened); the verified entitlement's
# ``tenant_keys`` is the sole tenant authority.


def _route_required_capabilities(spec: RouteSpec) -> tuple[str, ...]:
    """The capabilities a route requires, as an any-of tuple (R11.3).

    A route declares EITHER a single ``capability`` (the common case → a one-element tuple)
    OR an any-of ``capabilities_any`` set (→ that tuple). A self-service-only route (neither)
    returns an empty tuple, so the caller skips the capability gate. ``capabilities_any`` wins
    when both happen to be set (a route should use one or the other).
    """
    if spec.capabilities_any:
        return tuple(spec.capabilities_any)
    if spec.capability is not None:
        return (spec.capability,)
    return ()


def _any_capability_granted(
    claims: Mapping[str, Any], tenant_id: str, required: tuple[str, ...]
) -> bool:
    """True when the caller holds ANY of the ``required`` capabilities (R11.3).

    Each capability is checked with the three-state :func:`has_capability` (True = token-backed
    grant; False = token-backed denial; None = token does not answer → deny). The route passes
    as soon as ONE returns ``True``; if none do, it is a deny (the caller holds none of the
    accepted capabilities). This preserves the single-capability semantics exactly for a
    one-element tuple (True passes, False/None deny) while supporting the export-OR-write and
    write-OR-admin gates R11.3 needs — never a blanket allow.
    """
    return any(has_capability(claims, tenant_id, cap) is True for cap in required)


def _scopes_are_all_regions(allowed_scopes: Mapping[str, list[str]]) -> bool:
    """True when the caller's resolved scope is the ``["*"]`` all-regions grant on EVERY axis.

    The R5 schedule gate requires TENANT-WIDE member scope: a scheduled run is unattended, so
    it must never replay a partial regional slice. The resolved ``allowed_scopes`` is the
    per-dimension map :func:`_resolve_scope_access` builds (``{dimension: [values]}``). This is
    all-regions when EVERY enabled dimension maps to exactly the ``[WILDCARD]`` sentinel — a
    subset (``["Oost"]``) or an empty/deny (``[]``) on ANY dimension fails. An un-partitioned
    tenant collapses to a single ``{DEFAULT: ["*"]}`` entry (tenant-wide by construction), which
    passes. An empty map (no scope resolved) is NOT all-regions (fail-closed).
    """
    if not allowed_scopes:
        return False
    return all(list(values) == [WILDCARD] for values in allowed_scopes.values())


def _authorize_schedule_route(
    claims: Mapping[str, Any],
    tenant_id: str,
    *,
    config_provider: ScopeConfigProvider | None = None,
    grants_reader: _ScopeGrantsReader | None = None,
) -> dict[str, list[str]]:
    """Enforce the SPECIAL R5 schedule gate: admin OR (write + all-regions). Returns the scopes.

    The CRITICAL R5 rule (design §3/§8): a schedule may be managed by a caller with
    **tenant-wide member access** only — either ``members:admin``, or ``members:write`` WITH
    the ``["*"]`` all-regions scope grant. A region-NARROWED ``members:write`` caller (e.g.
    region ``["Oost"]``) is REJECTED (403), because an unattended scheduled run must never
    replay a partial regional slice. This is NOT a plain capability any-of — it is a combined
    **capability + scope** gate, so it lives here rather than in the ordinary
    ``_any_capability_granted`` + ``_resolve_scope_access`` path.

    Decision:

    1. ``members:admin`` (three-state :func:`has_capability` == ``True``) → PASS outright
       (admin is tenant-wide by definition; no scope check needed).
    2. Else ``members:write`` must be a token-backed grant AND the caller's resolved scope must
       be all-regions (:func:`_scopes_are_all_regions` over the projected grants) → PASS.
    3. Otherwise → :class:`AuthorizationError` (403): neither admin, nor write, nor a
       write-with-a-narrowed-region caller may schedule.

    Returns the resolved per-dimension ``allowed_scopes`` map (tenant-wide for an admin or an
    all-regions write caller) so the context carries it like any other route — a scheduled run
    operates tenant-wide, which the resolved ``["*"]`` map expresses.

    Raises:
        AuthorizationError: The caller is authenticated + tenant-resolved but does not satisfy
            the schedule gate (→ 403).
    """
    # (1) Admin is tenant-wide — pass without a scope check and resolve the (wildcard) scope.
    if has_capability(claims, tenant_id, CAP_MEMBERS_ADMIN) is True:
        return _resolve_scope_access_for_admin(
            tenant_id, config_provider=config_provider
        )

    # (2) members:write path — the capability AND the all-regions scope grant are BOTH required.
    if has_capability(claims, tenant_id, CAP_MEMBERS_WRITE) is True:
        allowed_scopes = _resolve_scope_access_for_schedule(
            tenant_id,
            claims,
            config_provider=config_provider,
            grants_reader=grants_reader,
        )
        if _scopes_are_all_regions(allowed_scopes):
            return allowed_scopes
        # A region-narrowed write caller — the scope is a subset / deny, NOT all-regions. An
        # unattended run must never replay a partial slice (R5), so this is an honest 403.
        logger.info(
            "Members schedule route denied: members:write caller for tenant '%s' lacks the "
            "all-regions ['*'] grant (resolved scopes=%s)",
            tenant_id,
            allowed_scopes,
        )
        raise AuthorizationError(
            "Scheduling requires members:admin or members:write with an all-regions grant"
        )

    # (3) Neither admin nor write → deny (read-only / export-only / unentitled callers).
    logger.info(
        "Members schedule route denied: caller for tenant '%s' holds neither members:admin "
        "nor members:write",
        tenant_id,
    )
    raise AuthorizationError("Missing required capability for scheduling")


def _resolve_scope_access_for_admin(
    tenant_id: str, *, config_provider: ScopeConfigProvider | None = None
) -> dict[str, list[str]]:
    """The tenant-wide (all-regions) scope map an admin schedule caller operates under.

    An admin is tenant-wide by definition (R5), so every enabled dimension is the ``[WILDCARD]``
    grant; an un-partitioned tenant collapses to ``{DEFAULT: ["*"]}``. Built from the tenant's
    scope config so the shape matches :func:`_resolve_scope_access` (the domain sees a uniform
    per-dimension map) without reading the caller's projected grants (admin needs none).
    """
    if config_provider is None:
        config_provider = _scope_config_provider()
    config = config_provider.get_scope_config(tenant_id)
    enabled = config.enabled()
    if not enabled:
        return {DEFAULT_SCOPE_DIMENSION_KEY: [WILDCARD]}
    return {dimension.key: [WILDCARD] for dimension in enabled}


def _resolve_scope_access_for_schedule(
    tenant_id: str,
    claims: Mapping[str, Any],
    *,
    config_provider: ScopeConfigProvider | None = None,
    grants_reader: _ScopeGrantsReader | None = None,
) -> dict[str, list[str]]:
    """Resolve a members:write schedule caller's per-dimension scope from the PROJECTED grants.

    A thin wrapper around the same :func:`_scope_access_from_grant` machinery
    :func:`_resolve_scope_access` uses, but it does NOT take a :class:`RouteSpec` — the schedule
    gate resolves scope for the combined decision in :func:`_authorize_schedule_route`. Returns
    ``{dimension: [values]}``; the caller checks whether every dimension is the ``["*"]`` grant.
    """
    if config_provider is None:
        config_provider = _scope_config_provider()
    if grants_reader is None:
        grants_reader = _scope_grants_reader()

    config = config_provider.get_scope_config(tenant_id)
    enabled = config.enabled()
    if not enabled:
        # Un-partitioned tenant → tenant-wide by construction (the R3.2 collapse).
        wildcard = list(resolve_scope_access(tenant_id, None, []).allowed_scopes)
        return {DEFAULT_SCOPE_DIMENSION_KEY: wildcard}

    email = claims.get("email")
    grants = grants_reader.get_scope_grants(tenant_id, str(email) if email else "")
    allowed: dict[str, list[str]] = {}
    for dimension in enabled:
        granted_values = grants.get(dimension.key)
        granted_list = list(granted_values) if granted_values is not None else None
        access = _scope_access_from_grant(tenant_id, dimension, granted_list)
        allowed[dimension.key] = list(access.allowed_scopes)
    return allowed


def _authenticate_and_authorize(
    event: Mapping[str, Any],
    request: ParsedRequest,
    spec: RouteSpec,
    verifier: Any = None,
    path_params: Mapping[str, str] | None = None,
) -> RequestContext:
    """Authenticate the caller, establish tenant context, and authorize the route.

    The single edge adoption of the ``sam/shared`` toolkit (R1.1). Flow:

    1. **Authenticate (verified):** ``get_verified_claims(event)`` — API-GW-authorizer
       context preferred, else full RS256 verification. A missing/invalid token raises
       :class:`InvalidTokenError` (401); a JWKS outage raises
       :class:`ServiceUnavailableError` (503). No unverified header is ever read (Property
       2).
    2. **Active tenant (verify-before-trust + selection, s5f):** the ``X-Tenant`` header
       SELECTS among the caller's verified tenants and is validated against the entitlement's
       ``tenant_keys`` (:func:`_establish_tenant_context`) — the header never GRANTS a tenant.
       A selected tenant not in ``tenant_keys`` → 403; a single-tenant user with no header →
       their one tenant; multiple with no header → 403 (no guess). No tenant → 403.
    3. **Authorize (``has_capability`` + scope):** if the route declares a ``capability``,
       ``has_capability`` must return ``True`` (a token-backed grant). ``False`` (token-
       backed denial) and ``None`` (token does not answer → module policy = deny) both
       raise :class:`AuthorizationError` (403) — ``None`` is never a silent allow. A
       self-service route with no capability skips the capability gate (the domain layer
       enforces the ownership check on ``sub``). The **scope** decision runs through
       :func:`_resolve_scope_access` (the task-3.1 seam), which denies by default.

    Returns:
        A :class:`RequestContext` carrying the verified tenant, subject, roles, granted
        capability, resolved scopes, and full claims — all from verified material.

    Raises:
        InvalidTokenError: No/invalid token (401).
        ServiceUnavailableError: JWKS could not be obtained (503).
        AuthorizationError / TenantResolutionError: Authenticated but not authorized (403).
    """
    # (1) Authenticate — verified claims only (401/503 on failure; never header trust).
    claims = get_verified_claims(event, verifier=verifier)
    groups = get_groups(claims)
    sub = claims.get("sub")

    # (2) Active tenant — per-request SELECTION validated against the verified entitlement
    #     (s5f). The X-Tenant header SELECTS among the caller's verified tenants; it never
    #     GRANTS one (a selected tenant not in tenant_keys → 403). A single-tenant user with
    #     no header resolves to their one tenant (back-compat); multiple with no header → 403.
    #     Still NO tenant fallback: no MEMBERS_LOCAL_TENANT_ID, no hardcoded/default tenant
    #     (R6.2, C-UNWIND). A no-entitlement token denies honestly regardless of the header.
    entitlement = get_entitlements_from_claims(claims)
    requested_tenant = _requested_tenant_from_request(request)
    tenant_id = _establish_tenant_context(entitlement, requested_tenant)

    # One per-request projection reader shared by the scope-config and scope-grant reads and
    # the gating-dimension lookup, so the tenant partition is Queried at most once per
    # invocation (Property 5, one-Query-per-partition). Tests may override either seam.
    config_provider: ScopeConfigProvider = (
        _SCOPE_CONFIG_PROVIDER_OVERRIDE
        if _SCOPE_CONFIG_PROVIDER_OVERRIDE is not None
        else _new_projection_reader()
    )
    if _SCOPE_GRANTS_READER_OVERRIDE is not None:
        grants_reader: _ScopeGrantsReader = _SCOPE_GRANTS_READER_OVERRIDE
    elif hasattr(config_provider, "get_scope_grants"):
        # In production the fresh projection reader satisfies BOTH seams, so reuse it and
        # keep the one-Query-per-partition property (its per-invocation cache).
        grants_reader = config_provider  # type: ignore[assignment]
    else:
        # The config provider is a config-only override (e.g. a StaticScopeConfigProvider in
        # tests) — resolve a separate grants reader so scope still comes from projected rows.
        grants_reader = _scope_grants_reader()

    # (3) Authorize — capability (three-state) + scope seam.
    #     s5d task 4.1: allowed_scopes is now a per-dimension map {dimension: [values]}.
    #     A self-service route (no capability) carries an empty map — the domain enforces
    #     ownership on `sub`, not scope.
    allowed_scopes: dict[str, list[str]] = {}

    # A schedule route (R5) carries the SPECIAL combined capability+scope gate — NOT a plain
    # any-of. `_authorize_schedule_route` enforces `members:admin` OR (`members:write` + the
    # `["*"]` all-regions grant); a region-narrowed write caller is rejected (403) so an
    # unattended run never replays a partial regional slice. It returns the tenant-wide scope
    # map (an admin / all-regions write caller operates tenant-wide), which the context carries
    # like any other route. This runs INSTEAD of the ordinary any-of + scope seam below.
    if spec.schedule_gate:
        allowed_scopes = _authorize_schedule_route(
            claims,
            tenant_id,
            config_provider=config_provider,
            grants_reader=grants_reader,
        )
        scope_dimension_key = _gating_dimension_key(
            tenant_id, provider=config_provider
        )
        return RequestContext(
            tenant_id=tenant_id,
            sub=str(sub) if sub is not None else None,
            groups=groups,
            capability=spec.capability,
            allowed_scopes=allowed_scopes,
            claims=claims,
            path_params=dict(path_params or {}),
            scope_dimension_key=scope_dimension_key,
        )

    # A route may be gated by a SINGLE capability (`spec.capability`) or an ANY-OF set
    # (`spec.capabilities_any`, R11.3 — e.g. export OR write). `_capability_gate` resolves
    # whichever applies into a single True/deny decision. A self-service-only route (neither
    # set) skips the capability gate entirely (the domain enforces ownership on `sub`).
    required_caps = _route_required_capabilities(spec)
    if required_caps:
        if not _any_capability_granted(claims, tenant_id, required_caps):
            # Capability comes SOLELY from the verified entitlement (custom:entitlements via
            # the S4 PreTokenGen channel). There is NO cognito:groups fallback (R6.1, removed
            # in s5c). A route passes when the caller holds ANY required capability; otherwise
            # deny (never a silent/blanket allow). For an any-of route, "none of them granted".
            logger.info(
                "Members route '%s' required capability (any of) %s not granted for tenant '%s'",
                spec.name,
                list(required_caps),
                tenant_id,
            )
            raise AuthorizationError("Missing required capability")

        # A granted capability may still require a scope grant — consult the scope seam,
        # which sources the caller's scope from the PROJECTED grants (C5) and delegates the
        # deny-by-default classification to the domain resolve_scope_access (Property 4).
        allowed_scopes = _resolve_scope_access(
            spec,
            tenant_id,
            claims,
            config_provider=config_provider,
            grants_reader=grants_reader,
        )

    scope_dimension_key = _gating_dimension_key(tenant_id, provider=config_provider)

    return RequestContext(
        tenant_id=tenant_id,
        sub=str(sub) if sub is not None else None,
        groups=groups,
        capability=spec.capability,
        allowed_scopes=allowed_scopes,
        claims=claims,
        path_params=dict(path_params or {}),
        scope_dimension_key=scope_dimension_key,
    )


# ── Domain dispatch seam (Steps 3/5 own the real bodies) ──────────────────────────────


#: The domain read service, built lazily once (warm-reuse) over the tenant-scoped
#: repository. It is storage-agnostic — the repository (design C6) is the sole DynamoDB
#: touch-point — so the edge simply hands each read to it. Tests replace :data:`_SERVICE`
#: (or patch :func:`_get_membership_service`) with a service over an in-memory fake repo.
_SERVICE: MembershipService | None = None


def _get_membership_service() -> MembershipService:
    """Return the module-global :class:`MembershipService`, building it once at cold start.

    Wires the generic membership engine (design C2) over the tenant-scoped
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` (C6). The
    repository resolves its real table lazily + fail-fast on first use, so importing the
    module (and running the auth-only tests) never touches AWS.
    """
    global _SERVICE
    if _SERVICE is None:
        # The production EventBridge-Scheduler management port (R5, task 5.3). It materializes
        # the ONE EventBridge schedule behind each schedule#<id> record on create/update/delete.
        # Its boto3 client + the two ARNs resolve lazily + fail-fast on FIRST USE
        # (SCHEDULER_TARGET_FUNCTION_ARN / SCHEDULER_EXECUTION_ROLE_ARN wired by template.yaml),
        # so constructing it here touches no AWS — only the schedule CRUD path exercises it.
        from sam.members.repository.scheduler_api import EventBridgeSchedulerApi

        _SERVICE = MembershipService(
            DynamoDbMembersRepository(),
            overlay_provider=_OVERLAY_PROVIDER,
            lifecycle_provider=_LIFECYCLE_PROVIDER,
            tenant_hooks=_TENANT_HOOKS,
            view_contexts_provider=_VIEW_CONTEXTS_PROVIDER,
            scope_config_provider=_SCOPE_CONFIG_PROVIDER_FOR_SERVICE,
            mail_gate_provider=_MAIL_GATE_PROVIDER,
            scheduler_port=EventBridgeSchedulerApi(),
        )
    return _SERVICE


def _dispatch(spec: RouteSpec, request: ParsedRequest, ctx: RequestContext) -> Any:
    """Delegate a resolved route to the generic membership engine (design C2).

    Thin wrapper preserved on the facade so the existing monkeypatch seams hold: it resolves
    the module-global :class:`MembershipService` via :func:`_get_membership_service` (which
    tests patch) and hands it to :func:`sam.members.handler._dispatch.dispatch_route` (which
    owns the per-route ``if name == ...`` body). The ``(spec, request, ctx)`` signature is
    unchanged — tests also patch ``app._dispatch`` directly with the same shape.

    WRITE/READ wiring and the honest-501 fall-through live in ``dispatch_route``.
    """
    service = _get_membership_service()
    return dispatch_route(service, spec, request, ctx)


# ── Lambda entry point ────────────────────────────────────────────────────────────────


def handler(event: Mapping[str, Any], context: Any = None) -> dict:
    """API Gateway proxy entry point for the single Members module.

    Flow (thin adapter): parse → authenticate + tenant context → authorize → route →
    delegate to the domain service → shape the HTTP response.

    Returns an API Gateway proxy response dict. At the scaffold step: a resolved route
    returns ``501`` (behaviour pending), an unknown path returns ``404``, and a known path
    with the wrong method returns ``405`` with an ``Allow`` header.
    """
    request = _parse_request(event)

    # 1) Route: resolve (method, path) to a route spec (or 404 / 405).
    try:
        resolution = get_router().resolve(request.method, request.path)
    except NoRouteMatch:
        return _error(404, "Not found", code="errors.api.notFound")

    if isinstance(resolution, MethodNotAllowed):
        response = _error(
            405,
            "Method not allowed",
            code="errors.api.methodNotAllowed",
            allowed=list(resolution.allowed_methods),
        )
        response["headers"]["Allow"] = ", ".join(resolution.allowed_methods)
        return response

    assert isinstance(resolution, RouteMatch)
    spec = resolution.spec

    # 2) Authenticate (verified) + tenant context + authorize (the verified-auth edge).
    #    Verified-only, verify-before-trust: 401 unauth, 403 forbidden, 503 auth outage.
    #    The router's extracted path params are threaded onto the context so the domain
    #    dispatch can reach {member_id}/{membership_id} (the edge only carries them).
    try:
        ctx = _authenticate_and_authorize(
            event, request, spec, path_params=resolution.path_params
        )
    except InvalidTokenError as exc:
        return _error(
            getattr(exc, "http_status", 401),
            "Unauthorized",
            code="errors.api.unauthorized",
        )
    except ServiceUnavailableError as exc:
        return _error(
            getattr(exc, "http_status", 503),
            "Authentication service unavailable",
            code="errors.api.serviceUnavailable",
        )
    except AuthorizationError:
        return _error(403, "Forbidden", code="errors.api.forbidden")

    # 3) Delegate to the domain service (task 3.2 reads / Step 5 writes); shape the response.
    try:
        result = _dispatch(spec, request, ctx)
    except RouteNotImplemented:
        logger.info("Members route '%s' resolved but not implemented yet", spec.name)
        return _error(
            501, "Not implemented", code="errors.api.notImplemented", route=spec.name
        )
    except MemberNotFound:
        # Missing member within the tenant, OR out of the caller's scope on a READ —
        # deliberately indistinguishable so a scoped caller cannot probe for out-of-scope
        # records.
        return _error(404, "Not found", code="errors.api.notFound")
    except MembershipTypeNotFound:
        # Absent Lidmaatschap Beheer catalog entry for the tenant (design C8) → 404,
        # consistent with the member not-found mapping above (update/delete of an absent code).
        return _error(404, "Not found", code="errors.api.notFound")
    except MembershipTypeConflict:
        # Creating a catalog entry whose type_code already exists (design C8) → 409 Conflict;
        # never a silent overwrite of a live type (an intentional change uses the PUT route).
        return _error(
            409, "Membership type already exists", code="errors.membershiptype.conflict"
        )
    except MembershipTypeValidationError as exc:
        # A malformed catalog write (blank/invalid code, missing nl label, non-int order) →
        # 422 Unprocessable, carrying the per-field errors as an RFC 9457 array (v1.0).
        return _error(
            422,
            "Validation failed",
            code="errors.validation.failed",
            errors=_field_errors_array(exc.errors),
        )
    except AnalyticsSetNotFound:
        # Absent analytics-set for the tenant (F-012) → 404, consistent with the member /
        # catalog not-found mappings (get/update/delete of an absent set_id).
        return _error(404, "Not found", code="errors.api.notFound")
    except ScheduleNotFound:
        # Absent schedule for the tenant (R5) → 404, consistent with the analytics-set /
        # member / catalog not-found mappings (get/update/delete of an absent schedule_id).
        return _error(404, "Not found", code="errors.api.notFound")
    except AnalyticsSetConflict:
        # Creating an analytics-set whose set_id already exists (F-012) → 409 Conflict. With a
        # server-generated uuid4 this is effectively unreachable; carried for symmetry.
        return _error(
            409, "Analytics set already exists", code="errors.analyticsset.conflict"
        )
    except AnalyticsSetValidationError as exc:
        # A malformed analytics-set write (blank name, bad kind, non-mapping definition) → 422
        # Unprocessable, carrying the per-field errors as an RFC 9457 array (v1.0).
        return _error(
            422,
            "Validation failed",
            code="errors.validation.failed",
            errors=_field_errors_array(exc.errors),
        )
    except DeliveryNotConfigured:
        # A `deliver` (R4, task 4.2) was requested for a set that has NO stored delivery block —
        # there is nothing to send. A caller error (not a not-found: the set exists), mapped to a
        # 422 so the SPA can tell "set has no delivery, configure one first" apart from a 404.
        return _error(
            422,
            "The analytics set has no delivery block configured",
            code="errors.analyticsset.delivery.notConfigured",
        )
    except TemplateNotFound:
        # Absent stored mail template for the tenant (R2) → 404, consistent with the member /
        # catalog / analytics-set not-found mappings (get/update/delete of an absent template).
        return _error(404, "Not found", code="errors.api.notFound")
    except TemplateValidationError as exc:
        # A malformed template write (blank name, no usable language, bad merge fields) → 422
        # Unprocessable, carrying the per-field errors as an RFC 9457 array (v1.0). Also covers
        # a render-time data fault (an absent language variant / missing body object) surfaced
        # by the service as a TemplateValidationError.
        return _error(
            422,
            "Validation failed",
            code="errors.validation.failed",
            errors=_field_errors_array(exc.errors),
        )
    except ScopeDenied:
        # A scoped caller attempted a WRITE outside their allowed_scopes (Property 4). Unlike a
        # read (404, no existence leak), an authenticated+entitled write out of scope is an
        # honest authorization denial.
        return _error(403, "Forbidden", code="errors.api.forbidden")
    except TransitionDenied as exc:
        # A lifecycle transition that is not declared, or whose guards/required-fields fail
        # (design C2) → 409 Conflict, carrying the reasons as an RFC 9457 array (v1.0). Never a
        # silent allow; the hook did not fire and the record was not mutated.
        return _error(
            409,
            "Transition denied",
            code="errors.transition.denied",
            reasons=_reasons_array(exc.reasons),
        )
    except MemberValidationError as exc:
        # A well-formed write that violates the fixed-field or tenant validate_member rules
        # (design C2/C5) → 422 Unprocessable, carrying the per-field errors as an RFC 9457 array.
        return _error(
            422,
            "Validation failed",
            code="errors.validation.failed",
            errors=_field_errors_array(exc.errors),
        )
    except KeyError as exc:
        # A resolved route missing an expected path param (defensive — the router only
        # matches when the {param} segments are present).
        return _error(
            400,
            "Bad request",
            code="errors.api.badRequest",
            missing=str(exc.args[0]) if exc.args else None,
        )
    except Exception:
        # Any UNANTICIPATED error (a bug, a bad data shape, a dependency failure) becomes a
        # BODIED 500 — never an empty 502 the SPA can only render as "Failed to fetch". The full
        # traceback is logged SERVER-side (CloudWatch); the client gets only a stable code +
        # generic message, no internals/PII. MUST stay the LAST except so it never shadows the
        # anticipated domain mappings above.
        request_id = getattr(context, "aws_request_id", None)
        logger.exception(
            "Unhandled error dispatching Members route '%s' (request_id=%s)",
            spec.name,
            request_id,
        )
        return _error(500, "Internal error", code="errors.api.serverError")

    # A route may signal an ACCEPTED (202) outcome — the `deliver` route (R4) ENQUEUES the send
    # and returns before the work is done, so the honest status is 202, not 200. Everything else
    # is a completed 200. The envelope is identical (`{success:true, data}`); only the status
    # differs (202 is still in the 2xx success range).
    if isinstance(result, AcceptedResult):
        return _response(202, {"data": result.data})

    return _response(200, {"data": result})
