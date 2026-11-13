"""Verified-auth edge: tenant context, capability/scope authorization.

Extracted from :mod:`sam.members.handler.app` (code-quality-fixes-2026-11-12 task 5)
to keep the edge module under the size budget; re-exported from there so the public
import surface is unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sam.members.domain.error_codes import FieldError  # noqa: F401 (surface compat)
from sam.members.domain.membership_service import (
    DEFAULT_SCOPE_DIMENSION_KEY,
)
from sam.members.domain.scope_access import ScopeAccess, resolve_scope_access
from sam.members.domain.scope_dimensions import (
    WILDCARD,
    ScopeConfigProvider,
    ScopeDimension,
)
from sam.members.handler._dispatch import (
    CursorError,  # noqa: F401 (surface compat: tests reach app.CursorError)
    get_config_fields_crud_service,  # noqa: F401 (surface compat: tests reach app.get_config_fields_crud_service)
    get_config_write_service,  # noqa: F401 (surface compat: tests reach app.get_config_write_service)
    get_execute_and_deliver_service,  # noqa: F401 (surface compat: tests reach app.get_execute_and_deliver_service)
    get_mail_run_status_service,  # noqa: F401 (surface compat: tests reach app.get_mail_run_status_service)
    get_template_service,  # noqa: F401 (surface compat: tests reach app.get_template_service)
)
from sam.members.handler._http import (
    ParsedRequest,
    _json_default,  # noqa: F401 (surface compat: tests reach app._json_default)
)
from sam.members.handler.routes import (
    CAP_MEMBERS_ADMIN,
    CAP_MEMBERS_WRITE,
    RouteSpec,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader
from sam.shared.auth_utils import (
    DecodedEntitlements,
    get_entitlements_from_claims,
    get_groups,
    get_verified_claims,
    has_capability,
)

logger = logging.getLogger(__name__)


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


# ── Auth + tenant context + authorization (task 3.0 — the verified-auth edge) ─────────


class AuthorizationError(Exception):
    """Raised when a verified caller is not authorized for the route (→ 403).

    Distinct from :class:`sam.shared.auth_utils.InvalidTokenError` (401 — *who are you?*):
    the caller is authenticated, but the verified entitlement does not grant the route's
    capability (or the required scope). Authorization derives **only** from verified
    claims / entitlement (Property 2); this is never raised from an unverified source.
    """

    def __init__(self, message: str = "Forbidden") -> None:
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

    def __init__(self, message: str = "No tenant context") -> None:
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
) -> ScopeAccess:
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
        _config_provider_override()
        if _config_provider_override() is not None
        else _new_projection_reader()
    )
    if _grants_reader_override() is not None:
        grants_reader: _ScopeGrantsReader = _grants_reader_override()
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


# ── Test-seam resolution (code-quality-fixes-2026-11-12 task 5) ──────────────────────────
#
# The override slots stay on `app` (the documented seam every test + the parity harness uses).
# These thin accessors read them through a FUNCTION-LOCAL import of `app` so this module has no
# import-time dependency on it (avoids a cycle); at call time `app` is fully initialised.


def _config_provider_override() -> ScopeConfigProvider | None:
    """The scope-config provider override installed on the `app` module (or None)."""
    from . import app as _app

    return _app._SCOPE_CONFIG_PROVIDER_OVERRIDE


def _grants_reader_override() -> _ScopeGrantsReader | None:
    """The scope-grant reader override installed on the `app` module (or None)."""
    from . import app as _app

    return _app._SCOPE_GRANTS_READER_OVERRIDE


def _scope_config_provider() -> ScopeConfigProvider:
    """The active scope-config provider (resolved by `app`, which owns the override seam)."""
    from . import app as _app

    return _app._scope_config_provider()


def _scope_grants_reader() -> _ScopeGrantsReader:
    """The active scope-grant reader (resolved by `app`, which owns the override seam)."""
    from . import app as _app

    return _app._scope_grants_reader()
