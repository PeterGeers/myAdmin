"""
Tenant Admin Member-Scope Authoring Routes (s5d task 5.2)

Tenant_Admin endpoints to author a member-user's SCOPE grant (which members a
user may see), per the current verified tenant + module. These routes are a THIN
wrapper over :class:`services.user_tenant_scope_service.UserTenantScopeService`
(task 5.1) — the service owns validation, canonicalization, atomic overwrite,
clear-to-delete, and the ``enqueue_sync`` projection trigger. The route does the
Tenant_Admin auth + tenant/user resolution (mirroring ``tenant_admin_roles.py``)
and maps ``ScopeValidationError`` to a 400.

Endpoints (all ``@cognito_required(required_roles=["Tenant_Admin"])``, tenant from
the verified context — NEVER a body value; Property 1):
- ``GET  /api/tenant-admin/users/<username>/scope/<module>``   — current grant
  (``{ "scopes": {...} }``; empty object when none).
- ``PUT  /api/tenant-admin/users/<username>/scope/<module>``   — atomic overwrite
  of the ``(email, administration, module)`` row; body
  ``{ "scopes": { "<dimension>": ["<value>", ...] | ["*"] } }``; unknown
  dimension/value → 400; clearing all → row deleted (deny); fires
  ``enqueue_sync(tenant)`` (done inside the service).
- ``GET  /api/tenant-admin/scope-dimensions/<module>``         — the enabled scope
  dimensions + canonical values for the current tenant + module, sourced DIRECTLY
  from the MySQL ``<module>.scope_dimensions`` param (D4/R5.1), for the picker.

**Module token (path vs stored).** The API path segment is lower-case (s5d serves
``members``). The projection builder filters on ``_SCOPEGRANT_MODULE = "MEMBERS"``
(``projection_sync.py``) and the service's ``_load_dimension_meta`` reads the param
namespace as ``module.lower()``. So this route normalizes the path token to the
CANONICAL stored token via :func:`_canonical_module` (``members`` -> ``MEMBERS``)
and passes that stored token to the service — keeping authoring, storage, and the
projection filter byte-for-byte consistent (a PUT via this route actually projects).
"""

import os

from botocore.exceptions import ClientError
from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant, get_user_tenants
from database import DatabaseManager
from routes.tenant_admin_users import (
    USER_POOL_ID,
    cognito_client,
    get_user_attribute,
)
from services.parameter_service import ParameterService
from services.projection_sync_trigger import get_default_trigger
from services.user_tenant_scope_service import (
    ScopeValidationError,
    UserTenantScopeService,
)

# Create blueprint (same url_prefix + registration pattern as tenant_admin_roles).
tenant_admin_scope_bp = Blueprint(
    "tenant_admin_scope", __name__, url_prefix="/api/tenant-admin"
)

# The module-namespaced parameter that is the SOURCE OF TRUTH for the enabled
# scope dimensions + their canonical values (design D4/R5.1).
_SCOPE_DIMENSIONS_PARAM_KEY = "scope_dimensions"

# Canonical stored/projected module tokens, keyed by their lower-cased path form.
# The projection builder filters on "MEMBERS" (projection_sync._SCOPEGRANT_MODULE);
# s5d serves only the MEMBERS slice. A future module adds its own entry here.
_CANONICAL_MODULES = {
    "members": "MEMBERS",
}


def _canonical_module(module: str) -> str | None:
    """Map a path ``<module>`` token to the CANONICAL stored/projected token.

    The API path is lower-case (``members``); the row + projection filter use the
    upper-case canonical token (``MEMBERS``). Returns ``None`` for an unknown
    module so the route can 404 rather than store an un-projectable token.
    """
    if not module:
        return None
    return _CANONICAL_MODULES.get(module.lower())


def _build_scope_service() -> UserTenantScopeService:
    """Construct the scope service with a test-aware DB + ParameterService.

    Mirrors how peer routes build ``DatabaseManager(test_mode=...)``; the
    ParameterService is read-only (used for dimension validation + the picker).
    """
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    parameter_service = ParameterService(db)
    return UserTenantScopeService(db, parameter_service)


def _resolve_verified_tenant():
    """Resolve + access-check the verified tenant (no target user involved).

    Returns ``(tenant, None)`` on success, or ``(None, (json_response, status))``
    on any auth/resolution failure — the caller returns that tuple directly. The
    tenant comes from the verified context (X-Tenant header or JWT), NEVER from a
    body value (Property 1); the caller must have access to it (403 otherwise).
    Mirrors the tenant half of :func:`_resolve_tenant_and_target` for routes that
    act on the current tenant itself (no per-user target).
    """
    tenant = get_current_tenant(request)
    if not tenant:
        return None, (jsonify({"error": "No tenant specified"}), 400)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_token = auth_header.replace("Bearer ", "").strip()
        user_tenants = get_user_tenants(jwt_token)
    else:
        return None, (jsonify({"error": "Invalid authorization"}), 401)

    if tenant not in user_tenants:
        return None, (
            jsonify(
                {
                    "error": "Access denied",
                    "message": f"You do not have access to tenant: {tenant}",
                }
            ),
            403,
        )

    return tenant, None


def _resolve_tenant_and_target(username: str):
    """Resolve the verified tenant + target user's email, mirroring roles routes.

    Returns ``(tenant, target_email, None)`` on success, or ``(None, None,
    (json_response, status))`` on any auth/resolution failure — the caller returns
    that tuple directly. The tenant comes from the verified context (X-Tenant /
    JWT), NEVER from a body value (Property 1); the caller must have access to it
    (403 otherwise), and the target user must belong to it (403/404 otherwise).
    """
    # Tenant from verified context (X-Tenant header or JWT) — never a body value.
    tenant = get_current_tenant(request)
    if not tenant:
        return None, None, (jsonify({"error": "No tenant specified"}), 400)

    # Extract the caller's tenants from the verified JWT.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_token = auth_header.replace("Bearer ", "").strip()
        user_tenants = get_user_tenants(jwt_token)
    else:
        return None, None, (jsonify({"error": "Invalid authorization"}), 401)

    # Verify the caller has access to this tenant.
    if tenant not in user_tenants:
        return None, None, (
            jsonify(
                {
                    "error": "Access denied",
                    "message": f"You do not have access to tenant: {tenant}",
                }
            ),
            403,
        )

    # Resolve the target user and verify they belong to this tenant.
    try:
        user_response = cognito_client.admin_get_user(
            UserPoolId=USER_POOL_ID, Username=username
        )
        target_user_tenants = get_user_attribute(
            user_response.get("UserAttributes", []), "custom:tenants"
        )
    except ClientError:
        return None, None, (jsonify({"error": f"User not found: {username}"}), 404)

    if not target_user_tenants or tenant not in target_user_tenants:
        return None, None, (
            jsonify(
                {
                    "error": "User not in this tenant",
                    "message": f"User {username} does not have access to tenant {tenant}",
                }
            ),
            403,
        )

    target_email = (
        get_user_attribute(user_response.get("UserAttributes", []), "email")
        or username
    )
    return tenant, target_email, None


# ============================================================================
# Scope Authoring Endpoints
# ============================================================================


@tenant_admin_scope_bp.route("/users/<username>/scope/<module>", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
def get_user_scope(username, module, user_email, user_roles) -> ResponseReturnValue:
    """Return the user's current scope grant for the current tenant + module.

    ``{ "scopes": {...} }`` — an empty object when no grant exists (R1.1).
    """
    canonical_module = _canonical_module(module)
    if canonical_module is None:
        return jsonify({"error": f"Unknown module: {module}"}), 404

    tenant, target_email, err = _resolve_tenant_and_target(username)
    if err is not None:
        return err

    service = _build_scope_service()
    scopes = service.get_scope(target_email, tenant, canonical_module)
    return jsonify(
        {
            "success": True,
            "tenant": tenant,
            "module": canonical_module,
            "username": username,
            "scopes": scopes,
        }
    )


@tenant_admin_scope_bp.route("/users/<username>/scope/<module>", methods=["PUT"])
@cognito_required(required_roles=["Tenant_Admin"])
def set_user_scope(username, module, user_email, user_roles) -> ResponseReturnValue:
    """Atomically overwrite the user's scope grant for the current tenant + module.

    Body ``{ "scopes": { "<dimension>": ["<value>", ...] | ["*"] } }``. The service
    validates + canonicalizes each dimension/value (unknown → ``ScopeValidationError``
    → 400 here), overwrites the row (or DELETES it when the grant clears to empty —
    deny), and fires ``enqueue_sync(tenant)``. Returns the normalized scopes (R4.5).
    """
    canonical_module = _canonical_module(module)
    if canonical_module is None:
        return jsonify({"error": f"Unknown module: {module}"}), 404

    tenant, target_email, err = _resolve_tenant_and_target(username)
    if err is not None:
        return err

    data = request.get_json(silent=True) or {}
    scopes = data.get("scopes")
    if scopes is None:
        return jsonify(
            {"success": False, "error": "scopes is required"}
        ), 400

    service = _build_scope_service()
    try:
        normalized = service.set_scope(
            target_email,
            tenant,
            canonical_module,
            scopes,
            created_by=user_email,
        )
    except ScopeValidationError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    print(
        f"AUDIT: Scope for {module} set on {username} by {user_email} "
        f"in tenant {tenant}: {normalized}",
        flush=True,
    )

    return jsonify(
        {
            "success": True,
            "tenant": tenant,
            "module": canonical_module,
            "username": username,
            "scopes": normalized,
        }
    )


@tenant_admin_scope_bp.route("/scope-dimensions/<module>", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
def get_scope_dimensions(module, user_email, user_roles) -> ResponseReturnValue:
    """Return the enabled scope dimensions + canonical values for the picker.

    Sourced DIRECTLY from the MySQL ``<module>.scope_dimensions`` param for the
    current tenant (D4/R5.1) — NOT the DynamoDB projection. Each returned dimension
    carries ``key``, ``label``, ``values`` (canonical), and ``field`` when present.
    """
    canonical_module = _canonical_module(module)
    if canonical_module is None:
        return jsonify({"error": f"Unknown module: {module}"}), 404

    # Tenant from the verified context (never a body value) — the picker is
    # tenant-scoped like every other read (Property 1).
    tenant = get_current_tenant(request)
    if not tenant:
        return jsonify({"error": "No tenant specified"}), 400

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_token = auth_header.replace("Bearer ", "").strip()
        user_tenants = get_user_tenants(jwt_token)
    else:
        return jsonify({"error": "Invalid authorization"}), 401

    if tenant not in user_tenants:
        return jsonify(
            {
                "error": "Access denied",
                "message": f"You do not have access to tenant: {tenant}",
            }
        ), 403

    # Read the dimensions param directly (namespace = module token lower-cased,
    # matching the service's _load_dimension_meta / the projection builder).
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    parameter_service = ParameterService(db)
    raw_dimensions = parameter_service.get_param(
        canonical_module.lower(),
        _SCOPE_DIMENSIONS_PARAM_KEY,
        tenant=tenant,
    )

    dimensions = []
    if isinstance(raw_dimensions, list):
        for entry in raw_dimensions:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            if not key:
                continue
            if not entry.get("enabled", True):
                continue
            values = [v for v in (entry.get("values") or []) if isinstance(v, str)]
            dimension = {
                "key": key,
                "label": entry.get("label", key),
                "values": values,
            }
            if entry.get("field"):
                dimension["field"] = entry["field"]
            dimensions.append(dimension)

    return jsonify(
        {
            "success": True,
            "tenant": tenant,
            "module": canonical_module,
            "dimensions": dimensions,
            "count": len(dimensions),
        }
    )


# ============================================================================
# Manual "Re-sync now" (s5d task 5.3)
# ============================================================================


@tenant_admin_scope_bp.route("/projection/resync", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
def resync_projection(user_email, user_roles) -> ResponseReturnValue:
    """Force a full re-projection of the CURRENT tenant (convenience + recovery).

    A manual "Re-sync now" action (design → "Projection invocation + freshness"):
    it runs the trigger's forced/synchronous re-projection path — a GUARANTEED
    diff-and-replace (ODx4b) via ``ProjectionSync.sync_administration`` — for the
    current verified tenant ONLY (Property 1), and returns a small summary of the
    ``SyncResult`` (``written`` / ``removed`` counts).

    This is NOT the primary trigger: auto-on-write ``enqueue_sync`` remains the
    default so the projection is never silently stale. This surface is a recovery/
    convenience path (post-bulk-edit, or retry after a failed background sync).

    Unlike the best-effort auto-trigger (which swallows failures so a governance
    write is never broken), this is an EXPLICIT user action — a sync failure is
    surfaced as a 500 so the operator sees it.

    Tenant comes from the verified context (X-Tenant / JWT), NEVER a body value;
    the caller must have access to it (403 otherwise).
    """
    tenant, err = _resolve_verified_tenant()
    if err is not None:
        return err

    # Resolve the production-configured ProjectionSync the same way the on-change
    # trigger does (lazily-built DatabaseSourceProvider + ProjectionSync, steering
    # 31 fail-fast env), then run the FORCED full re-projection for this tenant
    # only — a guaranteed diff-and-replace that returns real written/removed counts
    # (NOT the debounced/best-effort enqueue).
    try:
        sync = get_default_trigger()._resolve_sync()
        result = sync.sync_administration(tenant)
    except Exception as e:  # noqa: BLE001 — explicit action: surface the failure
        print(
            f"AUDIT: Projection resync FAILED for tenant {tenant} "
            f"by {user_email}: {e}",
            flush=True,
        )
        return jsonify(
            {
                "success": False,
                "tenant": tenant,
                "error": str(e),
            }
        ), 500

    written = getattr(result, "written", 0)
    removed = getattr(result, "deleted", 0)

    print(
        f"AUDIT: Projection resync for tenant {tenant} by {user_email}: "
        f"written={written} removed={removed}",
        flush=True,
    )

    return jsonify(
        {
            "success": True,
            "tenant": tenant,
            "written": written,
            "removed": removed,
        }
    )
