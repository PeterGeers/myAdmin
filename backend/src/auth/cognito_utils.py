"""
AWS Cognito Authentication Utilities for myAdmin

This module provides JWT token validation, role extraction, and permission checking
for AWS Cognito-based authentication in Flask applications.

Uses cryptographic JWT verification via JWTVerifier when Cognito environment variables
are configured. Falls back to base64 payload decoding only when env vars are missing
(e.g., local development without Cognito access).

Based on the implementation guide at .kiro/specs/Common/Cognito/implementation-guide.md
"""

import os
import json
import base64
import functools
import logging
from typing import Tuple, List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


# --- JWT Verifier Singleton ---

_jwt_verifier_instance = None
_jwt_verifier_init_attempted = False


def _get_jwt_verifier():
    """
    Get or create the singleton JWTVerifier instance.

    Lazily initializes the verifier on first use using environment variables:
    - COGNITO_USER_POOL_ID
    - COGNITO_REGION
    - COGNITO_APP_CLIENT_ID

    Returns:
        JWTVerifier instance, or None if env vars are not configured.
    """
    global _jwt_verifier_instance, _jwt_verifier_init_attempted

    if _jwt_verifier_instance is not None:
        return _jwt_verifier_instance

    if _jwt_verifier_init_attempted:
        # Already tried and failed — don't retry every request
        return None

    _jwt_verifier_init_attempted = True

    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    region = os.environ.get("COGNITO_REGION")
    app_client_id = os.environ.get("COGNITO_APP_CLIENT_ID")

    if not all([user_pool_id, region, app_client_id]):
        logger.warning(
            "JWT cryptographic verification disabled: missing one or more env vars "
            "(COGNITO_USER_POOL_ID, COGNITO_REGION, COGNITO_APP_CLIENT_ID). "
            "Falling back to base64 payload decoding."
        )
        return None

    from auth.jwt_verifier import JWTVerifier

    _jwt_verifier_instance = JWTVerifier(
        user_pool_id=user_pool_id,
        region=region,
        app_client_id=app_client_id,
    )
    logger.info("JWT cryptographic verification enabled.")
    return _jwt_verifier_instance


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


def cors_headers() -> Dict[str, str]:
    """
    Standard CORS headers for all API responses

    Returns:
        dict: CORS headers
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE,PATCH",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Enhanced-Groups",
        "Access-Control-Allow-Credentials": "false",
    }


def handle_options_request() -> Dict[str, Any]:
    """
    Handle CORS preflight OPTIONS request

    Returns:
        dict: Response with CORS headers
    """
    return {"statusCode": 200, "headers": cors_headers(), "body": ""}


def create_error_response(
    status_code: int, message: str, details: Optional[str] = None
) -> Dict[str, Any]:
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


def create_success_response(data: Any, status_code: int = 200) -> Dict[str, Any]:
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
    event: Dict[str, Any],
) -> Tuple[Optional[str], Optional[List[str]], Optional[Dict[str, Any]]]:
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
) -> Tuple[Optional[str], Optional[List[str]], Optional[Dict[str, Any]]]:
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
        TokenExpiredError,
        ServiceUnavailableError,
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


def _extract_with_base64(
    jwt_token: str,
) -> Tuple[Optional[str], Optional[List[str]], Optional[Dict[str, Any]]]:
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
        current_time = datetime.utcnow().timestamp()
        if current_time > exp:
            return None, None, create_error_response(401, "Token has expired")

    return user_email, user_roles, None


def get_permissions_for_roles(user_roles: List[str]) -> List[str]:
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
    user_roles: List[str], required_permissions: List[str]
) -> Tuple[bool, Optional[Dict[str, Any]]]:
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
    user_roles: List[str],
    operation: str,
    details: Optional[Dict[str, Any]] = None,
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
        "timestamp": datetime.utcnow().isoformat(),
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
    required_roles: Optional[List[str]] = None,
    required_permissions: Optional[List[str]] = None,
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
            from flask import request, jsonify

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
            from auth.tenant_context import get_current_tenant
            from auth.role_cache import get_tenant_roles
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
            if required_roles:
                if not any(role in user_roles for role in required_roles):
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

        return decorated_function

    return decorator
