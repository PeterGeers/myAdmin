"""
AWS Cognito Authentication Utilities for myAdmin

This module provides JWT token validation, role extraction, and permission checking
for AWS Cognito-based authentication in Flask applications.

Uses cryptographic JWT verification via JWTVerifier when Cognito environment variables
are configured. It prefers the multi-pool issuer->pool registry (COGNITO_POOL_KEYS,
S2 T3/T13a) so production Pool A and the standing test pool are both verified on the
live auth path; it falls back to the legacy single-pool env vars when the registry is
not declared. Falls back to base64 payload decoding only when no verifier can be
configured (e.g., local development without Cognito access).

Based on the implementation guide at .kiro/specs/Common/Cognito/implementation-guide.md
"""

import base64
import functools
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# --- JWT Verifier Singleton ---

_jwt_verifier_instance = None
_jwt_verifier_init_attempted = False


def _get_jwt_verifier():
    """
    Get or create the singleton JWTVerifier instance.

    Lazily initializes the verifier on first use. Selection order (S2 T13b, R3.2 —
    pools are configuration, not code; R1.2/R1.3/R6.1):

    1. **Multi-pool registry** — if ``COGNITO_POOL_KEYS`` is set and non-blank, build
       a verifier over the full issuer->pool registry (:func:`load_pool_registry`).
       This activates every registered pool, including the test pool and the T13a
       production **Pool A** entry, on the live auth path. If the registry is
       misconfigured (:class:`PoolRegistryError`), log the error and return ``None``
       — verification is unavailable, never a token-accepting fallback.
    2. **Legacy single pool** — else, if all of ``COGNITO_USER_POOL_ID`` /
       ``COGNITO_REGION`` / ``COGNITO_APP_CLIENT_ID`` are set, build a
       backward-compatible single-pool verifier (:meth:`JWTVerifier.from_single_pool`).
    3. **Neither** — return ``None``; the base64 fallback applies (local dev / tests
       without any Cognito config).

    No dangerous fallback: a misconfigured registry returns ``None`` (verification
    unavailable), it never returns a verifier that would accept unverified tokens.

    Returns:
        JWTVerifier instance, or None if no verifier could be configured.
    """
    global _jwt_verifier_instance, _jwt_verifier_init_attempted

    if _jwt_verifier_instance is not None:
        return _jwt_verifier_instance

    if _jwt_verifier_init_attempted:
        # Already tried and failed — don't retry every request
        return None

    _jwt_verifier_init_attempted = True

    from auth.jwt_verifier import JWTVerifier

    # (1) Multi-pool registry path — pools are configuration (R3.2). When
    # COGNITO_POOL_KEYS is declared, the registry is the source of truth; it
    # includes the test pool and the T13a production Pool A entry.
    pool_keys = os.environ.get("COGNITO_POOL_KEYS")
    if pool_keys is not None and pool_keys.strip() != "":
        from auth.pool_registry import PoolRegistryError, load_pool_registry

        try:
            registry = load_pool_registry()
        except PoolRegistryError as e:
            # Misconfigured registry: verification is UNAVAILABLE. Return None (no
            # verifier) rather than any token-accepting path (no-dangerous-fallbacks,
            # R1.3). This surfaces as the dev base64 fallback where no verifier was
            # ever configured; it never weakens verification where one was expected.
            logger.error(
                "JWT cryptographic verification unavailable: issuer->pool registry "
                "is misconfigured (%s). No verifier will be used.",
                str(e),
            )
            return None

        _jwt_verifier_instance = JWTVerifier(registry=registry)
        logger.info(
            "JWT verification enabled (registry: %s)",
            ", ".join(registry.issuers()),
        )
        return _jwt_verifier_instance

    # (2) Legacy single-pool path (backward compatible).
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    region = os.environ.get("COGNITO_REGION")
    app_client_id = os.environ.get("COGNITO_APP_CLIENT_ID")

    if all([user_pool_id, region, app_client_id]):
        _jwt_verifier_instance = JWTVerifier.from_single_pool(
            user_pool_id=user_pool_id,
            region=region,
            app_client_id=app_client_id,
        )
        logger.info("JWT cryptographic verification enabled (single-pool).")
        return _jwt_verifier_instance

    # (3) Neither configured — base64 fallback for local dev / tests.
    logger.warning(
        "JWT cryptographic verification disabled: neither COGNITO_POOL_KEYS nor the "
        "legacy single-pool env vars (COGNITO_USER_POOL_ID, COGNITO_REGION, "
        "COGNITO_APP_CLIENT_ID) are configured. Falling back to base64 payload decoding."
    )
    return None


# Role-based permission mapping
# Official Cognito Groups only - no legacy roles
ROLE_PERMISSIONS = {
    # Super Admin - Full system access (wildcard permission)
    "Administrators": ["*"],  # Legacy admin role with full access
    "System_CRUD": ["*"],  # System-level CRUD with full access
    # Tenant Administration - tenant-level admin access
    "Tenant_Admin": [
        "tenant_admin",
        "tenant_config",
        "tenant_users",
        "tenant_modules",
        "tenant_settings",
        "tenant_credentials",
        "tenant_storage",
        "storage_manage",
        "storage_read",
        "storage_write",
    ],
    # System Administration - system config ONLY, NO user data access
    "SysAdmin": [
        "system_config",
        "system_logs",
        "system_audit",
        "system_read",
        "cache_manage",
        "templates_manage",
        "users_manage",
        "scalability_read",
        "performance_read",
        "debug_access",
        "admin_manage",
        "storage_manage",
        "storage_read",
        "storage_write",
    ],
    # Finance Module - Financial data access (invoices, transactions, banking, reports)
    "Finance_CRUD": [
        "finance_create",
        "finance_read",
        "finance_update",
        "finance_delete",
        "finance_list",
        "finance_export",
        "finance_write",
        "invoices_create",
        "invoices_read",
        "invoices_update",
        "invoices_delete",
        "invoices_list",
        "invoices_export",
        "transactions_create",
        "transactions_read",
        "transactions_update",
        "transactions_delete",
        "transactions_list",
        "transactions_export",
        "banking_read",
        "banking_process",
        "btw_read",
        "btw_process",
        "actuals_read",
        "actuals_update",
        "reports_read",
        "reports_list",
        "reports_export",
    ],
    "Finance_Read": [
        "finance_read",
        "finance_list",
        "invoices_read",
        "invoices_list",
        "transactions_read",
        "transactions_list",
        "banking_read",
        "actuals_read",
        "reports_read",
        "reports_list",
    ],
    "Finance_Export": [
        "finance_export",
        "invoices_export",
        "transactions_export",
        "reports_read",
        "reports_export",
        "actuals_read",
    ],
    # STR Module - Short-term rental data access (bookings, pricing, STR reports)
    "STR_CRUD": [
        "str_create",
        "str_read",
        "str_update",
        "str_delete",
        "str_list",
        "str_export",
        "bookings_create",
        "bookings_read",
        "bookings_update",
        "bookings_delete",
        "bookings_list",
        "bookings_export",
        "reports_read",
        "reports_list",
        "reports_export",
    ],
    "STR_Read": [
        "str_read",
        "str_list",
        "bookings_read",
        "bookings_list",
        "reports_read",
        "reports_list",
    ],
    "STR_Export": ["str_export", "bookings_export", "reports_read", "reports_export"],
    # ZZP Module - Freelancer administration (invoicing, contacts, time tracking, debtors)
    "ZZP_Read": [
        "zzp_read",
        "zzp_list",
    ],
    "ZZP_CRUD": [
        "zzp_read",
        "zzp_list",
        "zzp_crud",
        "zzp_export",
        "zzp_tenant",
    ],
    "ZZP_Export": [
        "zzp_read",
        "zzp_list",
        "zzp_export",
    ],
}


def cors_headers() -> dict[str, str]:
    """
    Standard CORS headers for all API responses

    Returns:
        dict: CORS headers
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE,PATCH",
        # R2 (S2): X-Enhanced-Groups is NOT accepted — roles come only from the
        # verified token's cognito:groups, never from a client-supplied header.
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Credentials": "false",
    }


def handle_options_request() -> dict[str, Any]:
    """
    Handle CORS preflight OPTIONS request

    Returns:
        dict: Response with CORS headers
    """
    return {"statusCode": 200, "headers": cors_headers(), "body": ""}


def create_error_response(
    status_code: int, message: str, details: str | None = None
) -> dict[str, Any]:
    """
    Create standardized error response

    Args:
        status_code: HTTP status code
        message: Error message
        details: Optional additional details

    Returns:
        dict: Error response with CORS headers
    """
    body = {"error": message}
    if details:
        body["details"] = details

    return {
        "statusCode": status_code,
        "headers": {**cors_headers(), "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def create_success_response(data: Any, status_code: int = 200) -> dict[str, Any]:
    """
    Create standardized success response

    Args:
        data: Response data
        status_code: HTTP status code (default 200)

    Returns:
        dict: Success response with CORS headers
    """
    return {
        "statusCode": status_code,
        "headers": {**cors_headers(), "Content-Type": "application/json"},
        "body": json.dumps(data) if not isinstance(data, str) else data,
    }


def extract_user_credentials(
    event: dict[str, Any],
) -> tuple[str | None, list[str] | None, dict[str, Any] | None]:
    """
    Extract user credentials from Lambda event or Flask request

    This function handles both AWS Lambda events and Flask requests.
    It extracts the JWT token from the Authorization header and either:
    - Verifies it cryptographically via JWTVerifier (when Cognito env vars are configured)
    - Falls back to base64 payload decoding (when env vars are missing)

    Args:
        event: Lambda event dict or Flask request object

    Returns:
        tuple: (user_email, user_roles, error_response)
            - user_email: User's email address
            - user_roles: List of Cognito groups (roles)
            - error_response: Error response dict if authentication fails, None otherwise
    """
    try:
        # Handle Flask request object
        if hasattr(event, "headers"):
            headers = dict(event.headers)
        # Handle Lambda event dict
        elif isinstance(event, dict):
            headers = event.get("headers", {})
        else:
            return None, None, create_error_response(400, "Invalid request format")

        # Normalize header keys to lowercase for case-insensitive lookup
        headers_lower = {k.lower(): v for k, v in headers.items()}

        # Extract Authorization header
        auth_header = headers_lower.get("authorization")

        if not auth_header:
            return (
                None,
                None,
                create_error_response(401, "Missing or invalid Authorization header"),
            )

        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            return (
                None,
                None,
                create_error_response(401, "Missing or invalid Authorization header"),
            )

        # Extract JWT token
        jwt_token = auth_header.replace("Bearer ", "").strip()

        if not jwt_token:
            return (
                None,
                None,
                create_error_response(401, "Missing or invalid Authorization header"),
            )

        # Try cryptographic verification first
        verifier = _get_jwt_verifier()
        if verifier is not None:
            return _extract_with_verifier(verifier, jwt_token)

        # Fallback: base64 payload decoding (no cryptographic verification)
        return _extract_with_base64(jwt_token)

    except Exception as e:
        logger.error(
            f"Error extracting user credentials: {type(e).__name__}", exc_info=False
        )
        return (
            None,
            None,
            create_error_response(500, "Internal server error during authentication"),
        )


def _extract_with_verifier(
    verifier, jwt_token: str
) -> tuple[str | None, list[str] | None, dict[str, Any] | None]:
    """
    Extract credentials using cryptographic JWT verification.

    Maps JWTVerifier exceptions to proper HTTP error responses.

    Args:
        verifier: JWTVerifier instance
        jwt_token: Raw JWT token string (without 'Bearer ' prefix)

    Returns:
        tuple: (user_email, user_roles, error_response)
    """
    from auth.jwt_verifier import (
        InvalidTokenError,
        ServiceUnavailableError,
        TokenExpiredError,
    )

    try:
        payload = verifier.verify_token(jwt_token)
    except TokenExpiredError:
        return None, None, create_error_response(401, "Token has expired")
    except InvalidTokenError as e:
        return None, None, create_error_response(401, e.message)
    except ServiceUnavailableError as e:
        return None, None, create_error_response(503, e.message)

    # Extract user email (try multiple fields for compatibility)
    user_email = payload.get("email") or payload.get("username") or payload.get("sub")

    if not user_email:
        return (
            None,
            None,
            create_error_response(401, "No user identifier found in JWT token"),
        )

    # Extract user roles from cognito:groups claim
    user_roles = payload.get("cognito:groups", [])

    # Ensure user_roles is a list
    if not isinstance(user_roles, list):
        user_roles = [user_roles] if user_roles else []

    return user_email, user_roles, None


def _normalize_tenants_claim(tenants: Any) -> list[str]:
    """Normalize a ``custom:tenants`` claim into a list of tenant names.

    Cognito may deliver ``custom:tenants`` as a real list, a JSON-encoded string,
    or a JSON string with escaped quotes (e.g. ``[\\"ExampleTenant\\"]``). This
    accepts all shapes and always returns a list. Purely a shape adapter — it does
    no trust decision (the caller is responsible for using a *verified* payload).
    """
    if isinstance(tenants, list):
        return tenants

    if isinstance(tenants, str):
        raw = tenants
        try:
            if raw.startswith("[") and "\\" in raw:
                raw = raw.replace('\\"', '"').replace("\\'", "'")
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            return [parsed] if parsed else []
        except json.JSONDecodeError:
            return [tenants] if tenants else []

    return [tenants] if tenants else []


def get_verified_tenants(jwt_token: str) -> list[str] | None:
    """Return the ``custom:tenants`` list from a **cryptographically verified** token.

    This is the R2.3 source of truth for tenant authorization on the Flask plane:
    the tenant list is read only after the token's signature, issuer, audience, and
    expiry are verified by :class:`JWTVerifier`. A client-supplied header is never a
    source for this list.

    Returns:
        - A list of tenant names when the verifier is configured and the token
          verifies (an empty list if the verified token carries no tenants).
        - ``None`` when the verifier is not configured (missing Cognito env vars),
          signalling the caller to use the base64 fallback used in local dev/tests.

    Raises:
        The underlying JWTVerifier exceptions (InvalidTokenError, TokenExpiredError,
        ServiceUnavailableError) when a token is present but fails verification — an
        unverified token must never yield a trusted tenant list.
    """
    verifier = _get_jwt_verifier()
    if verifier is None:
        # No cryptographic verification available (local dev / tests without
        # Cognito env vars). Signal the caller to use the base64 fallback.
        return None

    payload = verifier.verify_token(jwt_token)
    return _normalize_tenants_claim(payload.get("custom:tenants", []))


def _extract_with_base64(
    jwt_token: str,
) -> tuple[str | None, list[str] | None, dict[str, Any] | None]:
    """
    Extract credentials using base64 payload decoding (fallback, no cryptographic verification).

    Used when Cognito environment variables are not configured (e.g., local development).

    Args:
        jwt_token: Raw JWT token string (without 'Bearer ' prefix)

    Returns:
        tuple: (user_email, user_roles, error_response)
    """
    # Split JWT token into parts
    parts = jwt_token.split(".")
    if len(parts) != 3:
        return (
            None,
            None,
            create_error_response(401, "Missing or invalid Authorization header"),
        )

    # Decode payload (second part of JWT)
    payload_encoded = parts[1]

    # Add padding if necessary (base64 requires length to be multiple of 4)
    padding = 4 - (len(payload_encoded) % 4)
    if padding != 4:
        payload_encoded += "=" * padding

    # Decode base64
    try:
        payload_decoded = base64.urlsafe_b64decode(payload_encoded)
        payload = json.loads(payload_decoded)
    except Exception as e:
        logger.debug(f"JWT base64 decode error: {type(e).__name__}")
        return (
            None,
            None,
            create_error_response(401, "Missing or invalid Authorization header"),
        )

    # Extract user email (try multiple fields)
    user_email = payload.get("email") or payload.get("username") or payload.get("sub")

    if not user_email:
        return (
            None,
            None,
            create_error_response(401, "No user identifier found in JWT token"),
        )

    # Extract user roles from cognito:groups claim
    user_roles = payload.get("cognito:groups", [])

    # Ensure user_roles is a list
    if not isinstance(user_roles, list):
        user_roles = [user_roles] if user_roles else []

    # Check token expiration (optional but recommended for fallback)
    exp = payload.get("exp")
    if exp:
        # JWT `exp` is seconds since the Unix epoch in UTC (RFC 7519). Use a
        # timezone-aware UTC datetime so `.timestamp()` converts correctly
        # regardless of the server's local timezone. A naive `utcnow()` would
        # be interpreted as local time by `.timestamp()`, skewing the check.
        current_time = datetime.now(timezone.utc).timestamp()
        if current_time > exp:
            return None, None, create_error_response(401, "Token has expired")

    return user_email, user_roles, None


def get_permissions_for_roles(user_roles: list[str]) -> list[str]:
    """
    Get all permissions for given roles

    Args:
        user_roles: List of user's roles

    Returns:
        list: List of permissions
    """
    permissions = set()

    for role in user_roles:
        role_perms = ROLE_PERMISSIONS.get(role, [])

        # If role has wildcard permission, grant all access
        if "*" in role_perms:
            return ["*"]

        permissions.update(role_perms)

    return list(permissions)


def validate_permissions(
    user_roles: list[str], required_permissions: list[str]
) -> tuple[bool, dict[str, Any] | None]:
    """
    Validate user has required permissions based on their roles

    Args:
        user_roles: List of user's Cognito groups (roles)
        required_permissions: List of required permissions for the operation

    Returns:
        tuple: (is_authorized, error_response)
            - is_authorized: True if user has all required permissions
            - error_response: Error response dict if not authorized, None otherwise
    """
    if not user_roles:
        return False, create_error_response(403, "No roles assigned to user")

    if not required_permissions:
        # No specific permissions required, just need to be authenticated
        return True, None

    # Get all permissions for user's roles
    user_permissions = get_permissions_for_roles(user_roles)

    # Check for wildcard permission (full access)
    if "*" in user_permissions:
        return True, None

    # Check if user has all required permissions
    missing_permissions = [
        perm for perm in required_permissions if perm not in user_permissions
    ]

    if missing_permissions:
        return False, create_error_response(
            403,
            "Insufficient permissions",
            f"Missing permissions: {', '.join(missing_permissions)}",
        )

    return True, None


def log_successful_access(
    user_email: str,
    user_roles: list[str],
    operation: str,
    details: dict[str, Any] | None = None,
):
    """
    Log successful access for audit trail

    Args:
        user_email: User's email
        user_roles: User's roles
        operation: Operation being performed
        details: Optional additional details
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_email": user_email,
        "user_roles": user_roles,
        "operation": operation,
        "status": "success",
    }

    if details:
        log_entry["details"] = details

    # Print to CloudWatch Logs (or your logging system)
    print(f"ACCESS_LOG: {json.dumps(log_entry)}")


def cognito_required(
    required_roles: list[str] | None = None,
    required_permissions: list[str] | None = None,
):
    """
    Decorator to protect Flask routes with Cognito authentication

    This decorator:
    1. Extracts JWT token from Authorization header
    2. Validates the token and extracts user credentials
    3. Checks if user has required roles (if specified)
    4. Checks if user has required permissions (if specified)
    5. Injects user_email and user_roles into the route function

    Args:
        required_roles: List of required Cognito groups (roles). User must have at least one.
        required_permissions: List of required permissions. User must have all.

    Usage:
        @app.route('/api/invoices', methods=['GET'])
        @cognito_required(required_roles=['Administrators', 'Accountants'])
        def get_invoices(user_email, user_roles):
            # Only admins and accountants can access
            pass

        @app.route('/api/reports', methods=['GET'])
        @cognito_required(required_permissions=['reports_read'])
        def get_reports(user_email, user_roles):
            # Anyone with reports_read permission can access
            pass
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import jsonify, request

            # Debug: Log request info
            logger.debug(f"Request to {f.__name__}: {request.method} {request.path}")

            # Extract user credentials from request
            user_email, user_roles, auth_error = extract_user_credentials(request)

            if auth_error:
                # Return Flask JSON response
                logger.debug(
                    f"Auth error for {f.__name__}: {auth_error.get('statusCode')}"
                )
                return jsonify(json.loads(auth_error["body"])), auth_error["statusCode"]

            # Split: global roles from JWT, per-tenant roles from DB
            from auth.role_cache import get_tenant_roles
            from auth.tenant_context import get_current_tenant
            from database import DatabaseManager

            global_roles = [
                r
                for r in user_roles
                if r in ("SysAdmin", "Administrators", "System_CRUD")
            ]
            tenant = get_current_tenant(request)
            if tenant:
                test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"
                db = DatabaseManager(test_mode=test_mode)
                tenant_roles = get_tenant_roles(user_email, tenant, db)
            else:
                tenant_roles = []
            user_roles = list(set(global_roles + tenant_roles))

            logger.debug(
                f"Auth success for {f.__name__}: {user_email} with roles {user_roles}"
            )

            # Check required roles (if specified)
            if required_roles and not any(
                role in user_roles for role in required_roles
            ):
                logger.debug(
                    f"Role check failed for {f.__name__}. Required: {required_roles}, User has: {user_roles}"
                )
                return jsonify(
                    {
                        "error": "Insufficient permissions",
                        "details": f"Required roles: {', '.join(required_roles)}",
                    }
                ), 403

            # Check required permissions (if specified)
            if required_permissions:
                is_authorized, error_response = validate_permissions(
                    user_roles, required_permissions
                )
                if not is_authorized:
                    return jsonify(json.loads(error_response["body"])), error_response[
                        "statusCode"
                    ]

            # Log successful access
            log_successful_access(user_email, user_roles, f.__name__)

            # Inject user credentials into route function
            kwargs["user_email"] = user_email
            kwargs["user_roles"] = user_roles

            return f(*args, **kwargs)

        # Sentinel marker so route-coverage audits/tests (S2 T6, R1.1) can
        # detect verified-JWT protection by introspection. functools.wraps
        # above copied f's attributes onto the wrapper (including any inner
        # marker); we set this AFTER wraps so it always reflects THIS layer.
        decorated_function._cognito_required = True

        return decorated_function

    return decorator
