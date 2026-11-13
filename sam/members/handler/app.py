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
from typing import Any

from sam.members.domain.analytics_set import AnalyticsSetValidationError
from sam.members.domain.application_publish import (
    PublishNotReady,
    PublishPipelineNotWired,
    PublishSlugConflict,
    PublishSlugRejected,
)
from sam.members.domain.config_fields_crud_service import (
    SlugAuthorConflict,
    SlugAuthorRejected,
)
from sam.members.domain.config_status import ConfigStatusProvider
from sam.members.domain.default_page_size import DefaultPageSizeProvider
from sam.members.domain.error_codes import FieldError  # noqa: F401 (surface compat)
from sam.members.domain.execute_and_deliver import (
    AdHocMailInvalid,
    DeliveryNotConfigured,
    MailNotCertified,
)
from sam.members.domain.field_resolver import TenantOverlay, TenantOverlayProvider
from sam.members.domain.look_and_feel_settings_service import (
    CrossTenantCopyError,
    LookAndFeelValidationError,
)
from sam.members.domain.mail_config import MailConfigProvider
from sam.members.domain.mail_gate import MailGateProvider
from sam.members.domain.membership_service import (
    AnalyticsSetConflict,
    AnalyticsSetNotFound,
    MemberNotFound,
    MembershipService,
    MembershipTypeConflict,
    MembershipTypeNotFound,
    MemberValidationError,
    ScheduleNotFound,
    ScopeDenied,
)
from sam.members.domain.membership_type_catalog import MembershipTypeValidationError
from sam.members.domain.scope_dimensions import (
    ScopeConfigProvider,
)
from sam.members.domain.template import TemplateValidationError
from sam.members.domain.template_service import TemplateNotFound
from sam.members.domain.tenant_hooks import TenantHookRegistry

# ── Per-route dispatch (the generic membership engine delegation) — re-exported ────────
from sam.members.handler._dispatch import (
    ConfigFieldsCrudError,
    ConfigWriteValidationError,
    CursorError,
    MailRunNotFound,
    RouteNotImplemented,
    StaleClientBundleError,
    dispatch_route,
    get_config_fields_crud_service,  # noqa: F401 (surface compat: tests reach app.get_config_fields_crud_service)
    get_config_write_service,  # noqa: F401 (surface compat: tests reach app.get_config_write_service)
    get_execute_and_deliver_service,  # noqa: F401 (surface compat: tests reach app.get_execute_and_deliver_service)
    get_mail_run_status_service,  # noqa: F401 (surface compat: tests reach app.get_mail_run_status_service)
    get_template_service,  # noqa: F401 (surface compat: tests reach app.get_template_service)
)
from sam.members.handler._http import (
    AcceptedResult,
    ParsedRequest,
    _error,
    _field_errors_array,
    _json_default,  # noqa: F401 (surface compat: tests reach app._json_default)
    _parse_request,
    _response,
)
from sam.members.handler.authorization import (  # noqa: F401 (surface compat)
    AuthorizationError,
    RequestContext,
    TenantResolutionError,
    _any_capability_granted,
    _authenticate_and_authorize,
    _authorize_schedule_route,
    _establish_tenant_context,
    _gating_dimension_key,
    _new_projection_reader,
    _requested_tenant_from_request,
    _resolve_scope_access,
    _resolve_scope_access_for_admin,
    _resolve_scope_access_for_schedule,
    _route_required_capabilities,
    _scope_access_from_grant,
    _ScopeGrantsReader,
    _scopes_are_all_regions,
    get_entitlements_from_claims,
    get_groups,
    get_verified_claims,
    has_capability,
)
from sam.members.handler.router import (
    MethodNotAllowed,
    NoRouteMatch,
    RouteMatch,
    get_router,
)
from sam.members.handler.routes import (
    RouteSpec,
)

# ── HTTP adapter helpers (request parsing + response shaping) — re-exported ────────────
from sam.members.handler.stale_bundle import stale_client_bundle_rejection
from sam.members.repository.members_repository import (
    DynamoDbMembersRepository,
)
from sam.members.repository.projection_config_write_repository import StaleVersionError
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks
from sam.shared.auth_utils import (
    InvalidTokenError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

# ── Projection-backed config/overlay providers (S5b task 8.2 — design C6) ─────────────
#
# The tenant scope config (:class:`ScopeConfigProvider`) and the per-tenant field overlay
# (:class:`TenantOverlayProvider`) now come from the S5b **governance projection**, read via
# :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`, instead
# of the S5 in-memory ``Static*`` reference providers. This is the swap the S5 seams always
# documented ("a later step swaps in a DynamoDB-backed provider behind the same seam") — no
# domain code changes; the reader already duck-types both Protocols.
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

#: Test-only override for the mail-gate provider (``None`` in production → fresh reader).
#: Mirrors :data:`_OVERLAY_PROVIDER_OVERRIDE` — a test injects a
#: ``StaticMailGateProvider`` (or a ``MembersProjectionReader`` over a fake table) so the
#: field-config endpoint's ``mail_enabled`` flag (pivot-output-actions R0/R1, design §6.3)
#: can be driven without an AWS round-trip. When unset (production), each read builds a fresh
#: projection reader (see :class:`_ProjectionMailGateProvider`).
_MAIL_GATE_PROVIDER_OVERRIDE: MailGateProvider | None = None

#: Test-only override for the mail-config provider (``None`` in production → fresh reader).
#: Mirrors :data:`_MAIL_GATE_PROVIDER_OVERRIDE` — a test injects a ``StaticMailConfigProvider``
#: (or a ``MembersProjectionReader`` over a fake table) so the field-config endpoint's
#: ``mail_config`` body (spec 02 task 7.1 fix — the typed Mail authoring read) can be driven
#: without an AWS round-trip. When unset (production), each read builds a fresh projection
#: reader (see :class:`_ProjectionMailConfigProvider`).
_MAIL_CONFIG_PROVIDER_OVERRIDE: MailConfigProvider | None = None

#: Test-only override for the config-status provider (``None`` in production → fresh reader).
#: Mirrors :data:`_MAIL_GATE_PROVIDER_OVERRIDE` — a test injects a ``StaticConfigStatusProvider``
#: (or a ``MembersProjectionReader`` over a fake table) so the field-config endpoint's
#: ``config_status`` block (Phase 0 step 3 — projection delivered/loaded status) can be driven
#: without an AWS round-trip. When unset (production), each read builds a fresh projection
#: reader (see :class:`_ProjectionConfigStatusProvider`).
_CONFIG_STATUS_PROVIDER_OVERRIDE: ConfigStatusProvider | None = None

#: Test-only override for the default-page-size provider (``None`` in production → fresh reader).
#: Mirrors :data:`_CONFIG_STATUS_PROVIDER_OVERRIDE` — a test injects a
#: ``StaticDefaultPageSizeProvider`` (or a ``MembersProjectionReader`` over a fake table) so the
#: field-config endpoint's ``default_page_size`` scalar (Phase 2 step (a) — the
#: ``view_contexts.page_size`` re-home, R2.1) can be driven without an AWS round-trip. When
#: unset (production), each read builds a fresh projection reader (see
#: :class:`_ProjectionDefaultPageSizeProvider`).
_DEFAULT_PAGE_SIZE_PROVIDER_OVERRIDE: DefaultPageSizeProvider | None = None


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


class _ProjectionMailGateProvider:
    """A thin :class:`MailGateProvider` indirection over a per-call fresh reader (§6.3).

    pivot-output-actions R0/R1 task 1.3 — the mail-enabled gate seam wired at the module edge,
    EXACTLY mirroring :class:`_ProjectionOverlayProvider`. The :class:`MembershipService`
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


class _ProjectionMailConfigProvider:
    """A thin :class:`MailConfigProvider` indirection over a per-call fresh reader.

    spec 02 task 7.1 fix — the mail-config (authoring read) seam wired at the module edge,
    EXACTLY mirroring :class:`_ProjectionMailGateProvider`. The :class:`MembershipService` is a
    lazy module-level singleton that captures its providers once; to reflect a freshly
    re-projected ``config#mail`` edit (a tenant saves through the typed Mail function, the SAM
    write updates the row) without rebuilding the service per request, its mail-config provider
    is this stable indirection: every ``get_mail_config`` call delegates to a FRESH
    :class:`MembersProjectionReader` (or the test override), so the field-config endpoint's
    ``mail_config`` always reflects the current projection while the domain and the service
    singleton stay UNCHANGED. Empty-is-valid / fail-closed is owned by the reader (missing row →
    the safe minimal body).
    """

    def get_mail_config(self, tenant_id: str) -> dict:
        if _MAIL_CONFIG_PROVIDER_OVERRIDE is not None:
            return dict(_MAIL_CONFIG_PROVIDER_OVERRIDE.get_mail_config(tenant_id))
        return _new_projection_reader().get_mail_config(tenant_id)


#: The mail-config provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionMailConfigProvider`).
_MAIL_CONFIG_PROVIDER: MailConfigProvider = _ProjectionMailConfigProvider()


#: Test-only override for the consent-notice provider (``None`` in production → fresh reader).
#: Mirrors :data:`_MAIL_CONFIG_PROVIDER_OVERRIDE` — a test injects a ``StaticConsentNoticeProvider``
#: (or a ``MembersProjectionReader`` over a fake table) so the publish / public field-config /
#: submit consent stamp can be driven without an AWS round-trip.
_CONSENT_NOTICE_PROVIDER_OVERRIDE: Any | None = None


class _ProjectionConsentNoticeProvider:
    """A thin consent-notice provider indirection over a per-call fresh reader.

    Round 3 (bugfix-published-form-submit, WIRING): ``_get_membership_service`` previously built
    the service WITHOUT a ``consent_notice_provider``, so the empty static default was used in
    production and publish, the public field-config GET and the submit consent stamp all saw no
    notice. EXACTLY mirrors :class:`_ProjectionMailConfigProvider`: every call delegates to a
    FRESH :class:`MembersProjectionReader` (or the test override) so a re-projected
    ``config#mail`` ``consent_notice`` is reflected without rebuilding the service singleton.
    Empty-is-valid (no notice → ``None``) is owned by the reader. ``_new_projection_reader`` is
    looked up by module global at call time.
    """

    def _source(self) -> Any:
        if _CONSENT_NOTICE_PROVIDER_OVERRIDE is not None:
            return _CONSENT_NOTICE_PROVIDER_OVERRIDE
        return _new_projection_reader()

    def get_consent_notice_version(self, tenant_id: str) -> str | None:
        return self._source().get_consent_notice_version(tenant_id)

    def get_consent_notice(self, tenant_id: str) -> dict | None:
        return self._source().get_consent_notice(tenant_id)


#: The consent-notice provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionConsentNoticeProvider`).
_CONSENT_NOTICE_PROVIDER = _ProjectionConsentNoticeProvider()


class _ProjectionConfigStatusProvider:
    """A thin :class:`ConfigStatusProvider` indirection over a per-call fresh reader.

    Phase 0 step 3 — the config delivered/loaded status seam wired at the module edge, EXACTLY
    mirroring :class:`_ProjectionMailGateProvider`. The :class:`MembershipService` is a lazy
    module-level singleton that captures its providers once; to reflect a freshly re-projected
    ``config#*`` edit without rebuilding the service per request, its config-status provider is
    this stable indirection: every ``get_config_status`` call delegates to a FRESH
    :class:`MembersProjectionReader` (or the test override), so the field-config endpoint's
    ``config_status`` always reflects the current projection while the domain and the service
    singleton stay UNCHANGED. Empty-is-valid is owned by the reader (missing row → ``None``).
    """

    def get_config_status(self, tenant_id: str) -> dict:
        if _CONFIG_STATUS_PROVIDER_OVERRIDE is not None:
            return dict(_CONFIG_STATUS_PROVIDER_OVERRIDE.get_config_status(tenant_id))
        return _new_projection_reader().get_config_status(tenant_id)


#: The config-status provider handed to the domain service — a stable indirection that reads a
#: fresh projection each call (see :class:`_ProjectionConfigStatusProvider`).
_CONFIG_STATUS_PROVIDER: ConfigStatusProvider = _ProjectionConfigStatusProvider()


class _ProjectionDefaultPageSizeProvider:
    """A thin :class:`DefaultPageSizeProvider` indirection over a per-call fresh reader.

    Phase 2 step (a) — the default-page-size seam wired at the module edge, EXACTLY mirroring
    :class:`_ProjectionConfigStatusProvider`. The :class:`MembershipService` is a lazy
    module-level singleton that captures its providers once; to reflect a freshly re-projected
    ``config#fields`` edit (the tenant re-authors ``members.default_page_size``, it
    re-projects) without rebuilding the service per request, its default-page-size provider is
    this stable indirection: every ``get_default_page_size`` call delegates to a FRESH
    :class:`MembersProjectionReader` (or the test override), so the field-config endpoint's
    ``default_page_size`` always reflects the current projection while the domain and the
    service singleton stay UNCHANGED. Empty-is-valid is owned by the reader (missing row /
    unset / non-positive → ``None``, R2.4).
    """

    def get_default_page_size(self, tenant_id: str) -> int | None:
        if _DEFAULT_PAGE_SIZE_PROVIDER_OVERRIDE is not None:
            return _DEFAULT_PAGE_SIZE_PROVIDER_OVERRIDE.get_default_page_size(tenant_id)
        return _new_projection_reader().get_default_page_size(tenant_id)


class _ProjectionFormSlugProvider:
    """A thin form-slug / public-prefix read indirection over a per-call fresh reader.

    slug-prefix SAM-owned — the form-slug + public-prefix read seam wired at the module edge,
    mirroring :class:`_ProjectionDefaultPageSizeProvider`. The :class:`MembershipService` is a lazy
    module-level singleton; to reflect a freshly re-projected ``config#fields`` edit (the admin
    authors the form slug or the public prefix via the SAM Change-Ops, the row re-projects) without
    rebuilding the service per request, its form-slug provider is this stable indirection: every
    ``get_form_slug`` / ``get_public_prefix`` call delegates to a FRESH
    :class:`MembersProjectionReader` (both read the ``config#fields`` row), so the field-config
    endpoint's ``slug`` + ``public_prefix`` always reflect the current projection while the service
    singleton stays UNCHANGED. Honours the overlay test override seam (a test injecting a
    ``MembersProjectionReader`` over a fake table drives both reads without an AWS round-trip).
    Empty-is-valid is owned by the reader (missing row / absent attr → ``None``).
    """

    def get_form_slug(self, tenant_id: str):
        if _OVERLAY_PROVIDER_OVERRIDE is not None and hasattr(
            _OVERLAY_PROVIDER_OVERRIDE, "get_form_slug"
        ):
            return _OVERLAY_PROVIDER_OVERRIDE.get_form_slug(tenant_id)
        return _new_projection_reader().get_form_slug(tenant_id)

    def get_public_prefix(self, tenant_id: str):
        if _OVERLAY_PROVIDER_OVERRIDE is not None and hasattr(
            _OVERLAY_PROVIDER_OVERRIDE, "get_public_prefix"
        ):
            return _OVERLAY_PROVIDER_OVERRIDE.get_public_prefix(tenant_id)
        return _new_projection_reader().get_public_prefix(tenant_id)

    def get_published_state(self, tenant_id: str):
        if _OVERLAY_PROVIDER_OVERRIDE is not None and hasattr(
            _OVERLAY_PROVIDER_OVERRIDE, "get_published_state"
        ):
            return _OVERLAY_PROVIDER_OVERRIDE.get_published_state(tenant_id)
        return _new_projection_reader().get_published_state(tenant_id)


#: The form-slug / public-prefix provider handed to the domain service — a stable indirection that
#: reads a fresh projection each call (see :class:`_ProjectionFormSlugProvider`).
_FORM_SLUG_PROVIDER = _ProjectionFormSlugProvider()


#: The default-page-size provider handed to the domain service — a stable indirection that
#: reads a fresh projection each call (see :class:`_ProjectionDefaultPageSizeProvider`).
_DEFAULT_PAGE_SIZE_PROVIDER: DefaultPageSizeProvider = (
    _ProjectionDefaultPageSizeProvider()
)


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
    "MailRunNotFound",
    "RouteNotImplemented",
    "TenantResolutionError",
    "handler",
]


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
            tenant_hooks=_TENANT_HOOKS,
            scope_config_provider=_SCOPE_CONFIG_PROVIDER_FOR_SERVICE,
            mail_gate_provider=_MAIL_GATE_PROVIDER,
            mail_config_provider=_MAIL_CONFIG_PROVIDER,
            consent_notice_provider=_CONSENT_NOTICE_PROVIDER,
            config_status_provider=_CONFIG_STATUS_PROVIDER,
            default_page_size_provider=_DEFAULT_PAGE_SIZE_PROVIDER,
            form_slug_provider=_FORM_SLUG_PROVIDER,
            scheduler_port=EventBridgeSchedulerApi(),
        )
    return _SERVICE


# NOTE (spec 12, redesign C / R3): the one-shot `build_application_preview_service` that backed the
# retired `POST /members/application-preview` route has been removed — preview is now in-browser
# (task 5.2). The production `MembershipService` + its `get_public_field_config` (used by the public
# edge and the publish path) are unchanged.


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
    except PublishNotReady as exc:
        # The application-form publish (spec 12 Task 2.1, R5.4) was REFUSED by the readiness gate
        # BEFORE any write: a precondition (slug / certified sender / ≥1 on-form field) is missing,
        # so NO artifact was emitted. Unlike the NEUTRAL public 409 (ApplicationNotAvailable), this
        # is the verified Tenant_Admin publishing their OWN form — "show, don't silently block"
        # (spec 11 R6): the TYPED reason is surfaced so the frontend Publish button (task 6.2) can
        # explain exactly what to fix. Mapped to a 409 (the request is well-formed + authorized,
        # but the form is not in a publishable state — distinct from a 422 malformed body / a 404).
        return _error(
            409,
            "The application form is not ready to publish",
            code=exc.code,
            reason=exc.reason.value,
        )
    except PublishSlugRejected as exc:
        # spec 14 Task 8.1: the tenant is ready and the artifact rendered, but the stored slug is
        # malformed/reserved or violates the SEC-4 prefix-ownership rule (it does not sit under the
        # tenant's own public prefix). NO marker was claimed and no write reached. Mapped to a 422
        # (a well-formed, authorized request whose slug value is invalid — distinct from the 409
        # readiness refusal and the 409 foreign-owned conflict) carrying the validator's own
        # caller-safe detail (no internals, steering 30/37).
        return _error(
            422,
            exc.detail,
            code=exc.code,
            route=spec.name,
        )
    except PublishSlugConflict:
        # spec 14 Task 8.1 (clobber backstop, R4.4): the slug is already claimed by a FOREIGN owner
        # (a different plane / kind / tenant), so the publish REFUSES to overwrite it and performs
        # no write. Mapped to a 409 (conflict with existing state) carrying a GENERIC, no-internals
        # message — never the raw SlugTaken / str(e). A same-owner re-publish is idempotent and
        # never reaches here.
        return _error(
            409,
            "That page address is already in use",
            code="errors.application.publishSlugConflict",
            route=spec.name,
        )
    except PublishPipelineNotWired:
        # The tenant PASSED the readiness gate but the live publish pipeline is task 2.2 — the
        # route + readiness gate are REAL (task 2.1) and only the live S3 render/write + CloudFront
        # invalidation is dormant (additionally gated on the owner-run hosting migration, task 0.1
        # / R6.4). Mapped to a caller-safe 501 (the route resolved + the tenant is ready, but the
        # behaviour is not built yet) — never a 500, never str(e). Task 2.2 removes this seam.
        logger.info(
            "Members application-form publish reached the ready seam but the live pipeline "
            "is not wired yet (task 2.2, migration-gated)"
        )
        return _error(
            501,
            "Publish pipeline not yet wired",
            code="errors.application.publishNotWired",
            route=spec.name,
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
    except MailRunNotFound:
        # A send-run (R9.2) that is absent in the tenant, OR exists but was triggered by
        # ANOTHER user and the caller is not a Tenant_Admin (R9.3) → 404, deliberately
        # indistinguishable so a scoped caller cannot probe for another user's runs (mirrors
        # the member-read not-found policy).
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
    except AdHocMailInvalid as exc:
        # The ad-hoc send body (POST /members/mail/send, mail-spec task 2.1) is malformed — an
        # unknown `mode`, a `to_fixed` with no recipients, or a `per_recipient` with no result
        # rows. There is no entity validate() behind an ad-hoc compose (unlike a saved set), so
        # the shared send service validates the body SHAPE and raises this; mapped to a 422 so
        # the SPA can tell "fix the compose" apart from a not-certified refusal (Property 6 —
        # never a silent enqueue-of-nothing). Carries the service's detail for the message.
        return _error(
            422,
            "The mail compose is invalid",
            code="errors.mail.adHocInvalid",
            detail=exc.detail,
        )
    except MailNotCertified as exc:
        # The pre-send certification gate (mail-spec task 1.3, R4.2/R5.2) refused BEFORE enqueue:
        # the tenant's mail is not enabled / not certified / has no projected domain, so there is
        # no usable verified From — NOTHING was queued and NO substitute sender was used (the
        # jabaki.nl regression stays dead; Property 2/4/6). Mapped to a 422 carrying the TYPED
        # machine reason so the SPA renders the right bilingual message + action (R8.1/R8.6a)
        # rather than string-sniffing — "your tenant's mail is not certified — contact your
        # administrator".
        return _error(
            422,
            "The tenant mail sender is not certified",
            code="errors.mail.notCertified",
            reason=exc.reason.value,
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
    except MemberValidationError as exc:
        # A well-formed write that violates the fixed-field or tenant validate_member rules
        # (design C2/C5) → 422 Unprocessable, carrying the per-field errors as an RFC 9457 array.
        return _error(
            422,
            "Validation failed",
            code="errors.validation.failed",
            errors=_field_errors_array(exc.errors),
        )
    except ConfigWriteValidationError as exc:
        # A DELIBERATE, caller-safe config-write validation error (spec 02, Task 1.6): a
        # `configId` outside the closed {fields, scope, mail} set (incl. `views`/unknown), or a
        # malformed per-`configId` body. The write path was NOT entered. Mapped to a 400 with the
        # explicit, caller-safe message (SAM-plane conventions, steering 35: a deliberate
        # validation error keeps its message — only the caught-exception path below echoes
        # nothing). This precedes the generic `except Exception` so a validation 400 is never
        # mis-shaped as a 500.
        return _error(
            400,
            str(exc),
            code="errors.validation.failed",
        )
    except SlugAuthorRejected as exc:
        # bugfix-slug-lifecycle task 3.1: the authored application-form slug is malformed/reserved
        # or violates the SEC-4 prefix-ownership rule (it does not sit under the tenant's own
        # public prefix). NO marker was claimed and config#fields.slug was NOT persisted. Mapped to
        # a 422 (a well-formed, authorized request whose slug VALUE is invalid — distinct from the
        # 409 foreign-owner conflict and the generic 400 ops-validation) carrying the validator's
        # own caller-safe detail (no internals, steering 30/37). A ConfigFieldsCrudError subclass,
        # so this branch MUST precede the generic `except ConfigFieldsCrudError` 400 to be mapped
        # as a 422.
        return _error(
            422,
            exc.detail,
            code="errors.validation.failed",
            route=spec.name,
        )
    except SlugAuthorConflict:
        # bugfix-slug-lifecycle task 3.1 (clobber backstop, R4.4): the authored slug is already
        # claimed by a FOREIGN owner (a different plane / kind / tenant), so the op REFUSES to
        # overwrite it and persists NOTHING. Mapped to a 409 (conflict with existing state)
        # carrying a GENERIC, no-internals message — never the raw SlugTaken / str(e). A same-owner
        # re-author is idempotent and never reaches here.
        return _error(
            409,
            "That page address is already in use",
            code="errors.application.slugConflict",
            route=spec.name,
        )
    except ConfigFieldsCrudError as exc:
        # A DELIBERATE, caller-safe config#fields Change-Op validation error (spec 03 Task 2.7):
        # a malformed ops envelope (empty/absent ops list, an op that is not an object, an unknown
        # op token, a missing identity / attrs), or an out-of-surface attribute the disjoint op
        # surfaces reject (an `application_*` attr on `set_field`, a definition attr on
        # `set_field_application`). No write was committed (the service raises before `apply_ops`,
        # or `apply_ops` rejects atomically). Mapped to a 400 with the explicit, caller-safe
        # message (SAM-plane conventions, steering 35/39 — a deliberate validation error keeps its
        # message; it carries no raw internals). Precedes the generic `except Exception` so a
        # validation 400 is never mis-shaped as a 500.
        return _error(
            400,
            str(exc),
            code="errors.validation.failed",
        )
    except CrossTenantCopyError:
        # spec 15 Task 8.1 (Req 9.4): a Layer-1 look-and-feel COPY whose source page belongs to a
        # DIFFERENT tenant than the verified target. The service rejects it BEFORE any read or
        # write, so neither tenant's state is touched. Mapped to a caller-safe 403 ("not
        # permitted") with a GENERIC message — it must NOT confirm whether the other tenant/page
        # exists (no cross-tenant information leak, never str(e)). A PermissionError subclass,
        # DISTINCT from the LookAndFeelValidationError 422 below, so it is a 403 not a 422; placed
        # before the generic `except Exception` so it is never mis-shaped as a 500.
        return _error(
            403,
            "Forbidden",
            code="errors.api.forbidden",
            route=spec.name,
        )
    except LookAndFeelValidationError as exc:
        # spec 15 Task 8.1 (Req 3.4 / Req 4.5): a DELIBERATE, caller-safe Layer-1 look-and-feel
        # rejection — an unsupported attribute, a value outside its permitted set, an unknown page
        # id, or a missing `attribute` on the author action. The service raises BEFORE any write,
        # so the Page's previously stored values are UNCHANGED by construction. Mapped to a 422
        # identifying the rejected setting (the message names only the client's own key/value —
        # safe to surface, no internals, steering 30/37, never str of an internal fault). A
        # ValueError subclass; placed before the generic `except Exception` so a deliberate
        # validation 422 is never mis-shaped as a 500.
        return _error(
            422,
            str(exc),
            code="errors.validation.failed",
            route=spec.name,
        )
    except StaleClientBundleError as exc:
        # STALE-SPA-BUNDLE guard (spec 03 Task 5.3a — design "Migration/rollout Slice 3"): a
        # `PUT /members/config/fields` write arrived in the RETIRED whole-overlay shape (a whole
        # record keyed by `fields`/`overrides`/`fixed_overrides`/`functional_groups`/
        # `field_overlay`, no `ops` list) — i.e. a CACHED OLD SPA bundle that has not reloaded
        # since the Change-Op switch. NO write was attempted (the guard fires at the edge before
        # any op is derived). Mapped to a caller-safe 409 with a DISTINCT, stable machine code
        # `errors.api.staleClient` — intentionally NOT the generic validation 400 and NOT the
        # data-conflict `errors.api.conflict`, so the SPA can tell this apart and render a
        # dedicated "a newer version is available — reload the app" prompt (the message is the
        # actionable remedy; it carries NO raw internals, steering 39). 409 fits the existing
        # error envelope (same "reload" family as the StaleVersionError 409) and keeps the
        # response intelligible rather than silently broken. A RuntimeError subclass, so it MUST
        # precede the generic `except Exception` to be caught as a 409, not a 500.
        status, message, code = stale_client_bundle_rejection(exc)
        return _error(status, message, code=code)
    except StaleVersionError:
        # The config#fields Change-Op version-conditional write was REJECTED because the row
        # changed under the caller (spec 03 design D5 / R6): the base version read no longer
        # matches, so the atomic `update_item` failed its ConditionExpression and NO partial
        # change was made. Mapped to a caller-safe 409 "reload and retry" with a stable code and
        # NO internals (steering 39). By the time this fires the service (task 4.1) has ALREADY
        # made its guarded one-shot auto-retry (re-read + re-derive + retry once for a shared-row
        # conflict from an UNRELATED edit) and the client_op_id idempotency path has been checked
        # in the repository — so a StaleVersionError reaching here is a genuine, repeated conflict
        # on the SAME identity. A RuntimeError subclass, so it must precede the generic
        # `except Exception` to be caught as a 409, not a 500.
        return _error(
            409,
            "Config was changed by another edit — reload and retry",
            code="errors.api.conflict",
        )
    except CursorError:
        # A client-supplied paging cursor (Req 25) that is malformed, stale, or does not belong
        # to the active tenant (a tampered cursor that tries to resume in another tenant's
        # partition — Property 1). It is a BAD REQUEST, not a server fault, and never a silent
        # cross-tenant read: a caller-safe 400 with a stable code, no internals.
        return _error(400, "Invalid paging cursor", code="errors.api.badRequest")
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
