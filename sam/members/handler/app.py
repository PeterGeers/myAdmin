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
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol

from sam.members.handler.router import (
    MethodNotAllowed,
    NoRouteMatch,
    RouteMatch,
    get_router,
)
from sam.members.handler.routes import (
    RouteSpec,
)
from sam.members.domain.field_resolver import TenantOverlay, TenantOverlayProvider
from sam.members.domain.fixed_fields import MembershipStatus
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import (
    DEFAULT_SCOPE_DIMENSION_KEY,
    MemberNotFound,
    MemberValidationError,
    MembershipService,
    MembershipTypeConflict,
    MembershipTypeNotFound,
    ScopeDenied,
    TransitionDenied,
)
from sam.members.domain.membership_type_catalog import MembershipTypeValidationError
from sam.members.domain.scope_access import ScopeAccess, resolve_scope_access
from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfigProvider,
    ScopeDimension,
)
from sam.members.domain.tenant_hooks import TenantHookRegistry
from sam.members.domain.view_contexts import ViewContext, ViewContextsProvider
from sam.members.repository.members_repository import (
    DynamoDbMembersRepository,
    MemberNumberConflictError,
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
_SCOPE_CONFIG_PROVIDER_OVERRIDE: Optional[ScopeConfigProvider] = None

#: Test-only override for the overlay provider (``None`` in production → fresh reader).
_OVERLAY_PROVIDER_OVERRIDE: Optional[TenantOverlayProvider] = None

#: Test-only override for the view-contexts provider (``None`` in production → fresh reader).
#: Mirrors :data:`_OVERLAY_PROVIDER_OVERRIDE` — a test injects a ``StaticViewContextsProvider``
#: (or a ``MembersProjectionReader`` over a fake table) so the field-config endpoint's
#: ``view_contexts`` can be driven without an AWS round-trip. When unset (production), each read
#: builds a fresh projection reader (see :class:`_ProjectionViewContextsProvider`).
_VIEW_CONTEXTS_PROVIDER_OVERRIDE: Optional[ViewContextsProvider] = None


def _new_projection_reader() -> MembersProjectionReader:
    """Build a FRESH projection reader for one request (per-invocation cache, R5).

    A new reader per read means its per-invocation ``_partition_cache`` never outlives the
    request, so a re-projected config/grant edit is picked up on the next request rather than
    only at cold start. The table resolves lazily + fail-fast on the first Query, so building
    the reader touches no AWS.
    """
    return MembersProjectionReader()


#: Test-only override for the scope-GRANT reader (``None`` in production → fresh reader).
#: The scope-config provider (:data:`_SCOPE_CONFIG_PROVIDER_OVERRIDE`) supplies the tenant's
#: ``ScopeConfig`` shape; this override supplies the caller's PROJECTED grants (task 8.3), so
#: a test can drive the projected-grant model (a Noord-scoped caller → ``["Noord"]``, an
#: all-access caller → ``["*"]``, a ``required_for``-capability caller with no grant → deny)
#: without an AWS round-trip. When unset (production), each request reads grants off the same
#: fresh :class:`MembersProjectionReader` used for the scope config (one Query per partition).
_SCOPE_GRANTS_READER_OVERRIDE: Optional["_ScopeGrantsReader"] = None


class _ScopeGrantsReader(Protocol):
    """The minimal seam the edge needs to read a caller's PROJECTED scope grants (C5).

    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`
    satisfies this by duck-typing (``get_scope_grants(tenant_id, email) -> {dim: values}``);
    a test may inject any object with the same method.
    """

    def get_scope_grants(self, tenant_id: str, email: str) -> Mapping[str, List[str]]:
        ...


def _scope_config_provider() -> ScopeConfigProvider:
    """The active :class:`ScopeConfigProvider` for this request (override, else fresh reader).

    Returns the test override when one is installed; otherwise a fresh projection reader so
    the scope config reflects the current projection (never a stale warm-container cache).
    """
    if _SCOPE_CONFIG_PROVIDER_OVERRIDE is not None:
        return _SCOPE_CONFIG_PROVIDER_OVERRIDE
    return _new_projection_reader()


def _scope_grants_reader() -> "_ScopeGrantsReader":
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
    "handler",
    "RouteNotImplemented",
    "AuthorizationError",
    "TenantResolutionError",
]


class RouteNotImplemented(NotImplementedError):
    """Raised by the (stubbed) domain dispatch for a route whose behaviour is pending.

    The route exists in the map and resolved correctly; its domain implementation is a
    later Step-1/Step-3/Step-5 task. The edge maps this to ``501 Not Implemented`` so a
    caller can tell "route not built yet" apart from "no such route" (404).
    """

    def __init__(self, route_name: str):
        self.route_name = route_name
        super().__init__(f"route '{route_name}' is not implemented yet")


# ── Request parsing (handler-layer adapter concern) ───────────────────────────────────


@dataclass(frozen=True)
class ParsedRequest:
    """The pieces of an API Gateway proxy event the router + edge need."""

    method: str
    path: str
    headers: Mapping[str, Any]
    query: Mapping[str, Any]
    body: Any


def _parse_request(event: Mapping[str, Any]) -> ParsedRequest:
    """Extract method/path/headers/query/body from an API Gateway proxy event.

    Supports both the REST/HTTP-v1 shape (``httpMethod`` + ``path``) and the HTTP-v2 shape
    (``requestContext.http.method`` + ``rawPath``). JSON bodies are decoded best-effort; a
    non-JSON or empty body is passed through as-is (the domain layer validates content).
    """
    event = event or {}

    method = event.get("httpMethod")
    path = event.get("path")
    request_context = event.get("requestContext") or {}
    http_ctx = request_context.get("http") if isinstance(request_context, Mapping) else None
    if not method and isinstance(http_ctx, Mapping):
        method = http_ctx.get("method")
    if not path:
        path = event.get("rawPath") or (http_ctx.get("path") if isinstance(http_ctx, Mapping) else None)

    headers = event.get("headers") or {}
    query = event.get("queryStringParameters") or {}

    body: Any = event.get("body")
    if isinstance(body, str) and body:
        try:
            body = json.loads(body)
        except (ValueError, TypeError):
            # Leave the raw string; the domain layer decides whether that is acceptable.
            pass

    return ParsedRequest(
        method=method or "",
        path=path or "/",
        headers=headers if isinstance(headers, Mapping) else {},
        query=query if isinstance(query, Mapping) else {},
        body=body,
    )


# ── Response shaping (handler-layer adapter concern) ──────────────────────────────────


_CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
}


def _response(status: int, payload: Mapping[str, Any]) -> dict:
    """Build an API Gateway proxy response with a JSON body and CORS headers.

    Every response the edge shapes carries the same CORS headers so a browser client can
    read it (including the 401/403 error envelopes below); the body is always well-formed
    JSON.
    """
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **_CORS_HEADERS},
        "body": json.dumps(payload),
    }


def _error(status: int, message: str, **extra: Any) -> dict:
    """Shape a JSON error response ``{"error": message, ...}``."""
    payload: dict[str, Any] = {"error": message}
    payload.update(extra)
    return _response(status, payload)


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

    The tenant is derived from the verified entitlement's ``tenant_keys`` (verify-before-
    trust) — never a client header/body. If the token does not answer (absent / unknown /
    malformed / overflow claim, or it lists no single usable tenant), there is no tenant to
    operate under, so the module denies by default (Property 3 fail-safe).
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

    tenant_id: Optional[str] = None
    sub: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    capability: Optional[str] = None
    allowed_scopes: Dict[str, List[str]] = field(default_factory=dict)
    claims: Mapping[str, Any] = field(default_factory=dict)
    path_params: Mapping[str, str] = field(default_factory=dict)
    scope_dimension_key: Optional[str] = None


def _establish_tenant_context(entitlement: DecodedEntitlements) -> str:
    """Derive the request's ``tenant_id`` from the **verified** entitlement (R6.1).

    Verify-before-trust: the tenant comes from the verified token's entitlement claim
    (``tenant_keys``), NEVER from a client-supplied header or body. For the pilot the
    entitlement answers for a single tenant, so exactly one usable ``tenant_key`` resolves
    the context.

    Fail-safe (Property 3): if the token does not answer — the claim requires fallback, is
    an overflow signal, or lists no tenant (an empty projection → empty entitlement is a
    valid *handled* outcome, not a crash) — there is no tenant to operate under and the
    edge denies by default via :class:`TenantResolutionError`. It never guesses a tenant
    and never falls back to a hardcoded one (no ``h-dcn`` default).

    Raises:
        TenantResolutionError: The verified token carries no single usable tenant.
    """
    if entitlement.fallback_required or entitlement.is_overflow:
        # The token does not carry a usable per-user answer; consult-fallback/deny is the
        # policy. This module denies by default (Property 3) rather than guess a tenant.
        raise TenantResolutionError("Token does not carry a usable tenant entitlement")

    tenant_keys = entitlement.tenant_keys
    if len(tenant_keys) == 1:
        return tenant_keys[0]

    # Zero tenants (empty entitlement — valid, handled) or, for the pilot, an ambiguous
    # multi-tenant token with no selector: deny by default rather than pick one.
    raise TenantResolutionError(
        "Verified entitlement does not resolve a single tenant context"
    )


def _gating_dimension_key(
    tenant_id: str, provider: Optional[ScopeConfigProvider] = None
) -> Optional[str]:
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
    tenant_id: str, dimension: ScopeDimension, granted_values: Optional[List[str]]
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
    config_provider: Optional[ScopeConfigProvider] = None,
    grants_reader: Optional["_ScopeGrantsReader"] = None,
) -> Dict[str, List[str]]:
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
    allowed: Dict[str, List[str]] = {}
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


def _authenticate_and_authorize(
    event: Mapping[str, Any],
    request: ParsedRequest,
    spec: RouteSpec,
    verifier: Any = None,
    path_params: Optional[Mapping[str, str]] = None,
) -> RequestContext:
    """Authenticate the caller, establish tenant context, and authorize the route.

    The single edge adoption of the ``sam/shared`` toolkit (R1.1). Flow:

    1. **Authenticate (verified):** ``get_verified_claims(event)`` — API-GW-authorizer
       context preferred, else full RS256 verification. A missing/invalid token raises
       :class:`InvalidTokenError` (401); a JWKS outage raises
       :class:`ServiceUnavailableError` (503). No unverified header is ever read (Property
       2).
    2. **Tenant context (verify-before-trust):** derive ``tenant_id`` from the verified
       entitlement's ``tenant_keys`` (:func:`_establish_tenant_context`). No tenant → 403.
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

    # (2) Tenant context — SOLELY from the verified entitlement (verify-before-trust). 403 if
    #     the token carries no single usable tenant (fail-safe, Property 3). There is NO
    #     tenant fallback: no MEMBERS_LOCAL_TENANT_ID substitution, no hardcoded/default tenant
    #     (R6.2, C-UNWIND). A no-entitlement token denies honestly here — the correct
    #     pre-wiring state until the PreTokenGen channel is switched on (Phase 5).
    entitlement = get_entitlements_from_claims(claims)
    tenant_id = _establish_tenant_context(entitlement)

    # One per-request projection reader shared by the scope-config and scope-grant reads and
    # the gating-dimension lookup, so the tenant partition is Queried at most once per
    # invocation (Property 5, one-Query-per-partition). Tests may override either seam.
    config_provider: ScopeConfigProvider = (
        _SCOPE_CONFIG_PROVIDER_OVERRIDE
        if _SCOPE_CONFIG_PROVIDER_OVERRIDE is not None
        else _new_projection_reader()
    )
    if _SCOPE_GRANTS_READER_OVERRIDE is not None:
        grants_reader: "_ScopeGrantsReader" = _SCOPE_GRANTS_READER_OVERRIDE
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
    allowed_scopes: Dict[str, List[str]] = {}
    if spec.capability is not None:
        granted = has_capability(claims, tenant_id, spec.capability)
        if granted is not True:
            # Capability comes SOLELY from the verified entitlement (custom:entitlements via
            # the S4 PreTokenGen channel). There is NO cognito:groups fallback (R6.1, removed
            # in s5c): False = authoritative token-backed denial; None = token does not answer
            # → module policy is deny (never a silent allow, never a blanket allow).
            reason = "denied" if granted is False else "not answered by token"
            logger.info(
                "Members route '%s' capability '%s' %s for tenant '%s'",
                spec.name,
                spec.capability,
                reason,
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
_SERVICE: Optional[MembershipService] = None


def _get_membership_service() -> MembershipService:
    """Return the module-global :class:`MembershipService`, building it once at cold start.

    Wires the generic membership engine (design C2) over the tenant-scoped
    :class:`~sam.members.repository.members_repository.DynamoDbMembersRepository` (C6). The
    repository resolves its real table lazily + fail-fast on first use, so importing the
    module (and running the auth-only tests) never touches AWS.
    """
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MembershipService(
            DynamoDbMembersRepository(),
            overlay_provider=_OVERLAY_PROVIDER,
            lifecycle_provider=_LIFECYCLE_PROVIDER,
            tenant_hooks=_TENANT_HOOKS,
            view_contexts_provider=_VIEW_CONTEXTS_PROVIDER,
        )
    return _SERVICE


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


# The READ routes this task (3.2) implements, dispatched by their stable route ``name``.
# WRITE routes (create/update/delete/transition/delegates) are intentionally absent — they
# fall through to :class:`RouteNotImplemented` (Step 5 / task 5.2).
def _dispatch(spec: RouteSpec, request: ParsedRequest, ctx: RequestContext) -> Any:
    """Delegate a resolved route to the generic membership engine (design C2).

    Task 3.2 wires the **READ** routes end-to-end: the edge hands the domain service the
    verified ``tenant_id`` (isolation, Property 1), the resolved per-dimension
    ``allowed_scopes`` map (domain-layer scope filtering, design C4 / Property 4/6; s5d task
    4.2 iterates it AND-across-dimensions, so no gating dimension is threaded),
    the requester ``sub`` and the route's ``self_service`` flag (so a member can read their
    OWN record), and the router's path params (``{member_id}`` / ``{membership_id}``). The
    handler stays thin — no scope math, no field resolution, no DynamoDB here.

    WRITE routes remain a stub: they raise :class:`RouteNotImplemented` (→ 501) until Step 5.
    """
    service = _get_membership_service()
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
        return _error(404, "Not found")

    if isinstance(resolution, MethodNotAllowed):
        response = _error(
            405, "Method not allowed", allowed=list(resolution.allowed_methods)
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
        return _error(getattr(exc, "http_status", 401), "Unauthorized")
    except ServiceUnavailableError as exc:
        return _error(getattr(exc, "http_status", 503), "Authentication service unavailable")
    except AuthorizationError:
        return _error(403, "Forbidden")

    # 3) Delegate to the domain service (task 3.2 reads / Step 5 writes); shape the response.
    try:
        result = _dispatch(spec, request, ctx)
    except RouteNotImplemented:
        logger.info("Members route '%s' resolved but not implemented yet", spec.name)
        return _error(501, "Not implemented", route=spec.name)
    except MemberNotFound:
        # Missing member within the tenant, OR out of the caller's scope on a READ —
        # deliberately indistinguishable so a scoped caller cannot probe for out-of-scope
        # records.
        return _error(404, "Not found")
    except MembershipTypeNotFound:
        # Absent Lidmaatschap Beheer catalog entry for the tenant (design C8) → 404,
        # consistent with the member not-found mapping above (update/delete of an absent code).
        return _error(404, "Not found")
    except MembershipTypeConflict:
        # Creating a catalog entry whose type_code already exists (design C8) → 409 Conflict;
        # never a silent overwrite of a live type (an intentional change uses the PUT route).
        return _error(409, "Membership type already exists")
    except MembershipTypeValidationError as exc:
        # A malformed catalog write (blank/invalid code, missing nl label, non-int order) →
        # 422 Unprocessable, carrying the per-field errors (mirrors MemberValidationError).
        return _error(422, "Validation failed", errors=exc.errors)
    except MemberNumberConflictError:
        # A racing/duplicate per-tenant member number lost the repository's conditional write
        # (Property 6) → 409 Conflict; never a silent overwrite.
        return _error(409, "Member number already in use")
    except ScopeDenied:
        # A scoped caller attempted a WRITE outside their allowed_scopes (Property 4). Unlike a
        # read (404, no existence leak), an authenticated+entitled write out of scope is an
        # honest authorization denial.
        return _error(403, "Forbidden")
    except TransitionDenied as exc:
        # A lifecycle transition that is not declared, or whose guards/required-fields fail
        # (design C2) → 409 Conflict, carrying the human-readable reasons. Never a silent
        # allow; the hook did not fire and the record was not mutated.
        return _error(409, "Transition denied", reasons=list(exc.reasons))
    except MemberValidationError as exc:
        # A well-formed write that violates the fixed-field or tenant validate_member rules
        # (design C2/C5) → 422 Unprocessable, carrying the per-field errors.
        return _error(422, "Validation failed", errors=exc.errors)
    except KeyError as exc:
        # A resolved route missing an expected path param (defensive — the router only
        # matches when the {param} segments are present).
        return _error(400, "Bad request", missing=str(exc.args[0]) if exc.args else None)

    return _response(200, {"data": result})
