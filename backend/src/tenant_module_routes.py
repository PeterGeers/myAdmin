"""
Tenant Module Routes

API endpoints for managing tenant-specific module access.
Handles which modules (FIN, STR) are available for each tenant.
"""

import logging

from flask import Blueprint, jsonify, request

from auth.cognito_utils import cognito_required
from database import DatabaseManager

logger = logging.getLogger(__name__)

# Create blueprint
tenant_module_bp = Blueprint("tenant_modules", __name__)

# Initialize database manager
db_manager = DatabaseManager()


def get_user_tenants_from_jwt(request):
    """Extract tenants from the VERIFIED JWT token in the request (R2.3).

    Delegates to :func:`auth.tenant_context.get_user_tenants`, which reads
    ``custom:tenants`` from the cryptographically verified token (base64 fallback
    only when the verifier is not configured, e.g. local dev/tests). This replaces
    the previous unverified base64 decode — the tenant list is never trusted from an
    unverified token, and headers are never a source for it.
    """
    from auth.tenant_context import get_user_tenants

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return []

    token = auth_header.replace("Bearer ", "").strip()
    return get_user_tenants(token)


def get_current_tenant(request):
    """Get the requested tenant SELECTOR from the X-Tenant header.

    R2 note: X-Tenant is only a *selector* — every caller in this module validates
    it against the user's VERIFIED tenant list (``get_user_tenants_from_jwt``) before
    granting access (``tenant not in user_tenants`` -> 403 / Tenant_Admin check). The
    header is never itself a source of truth for tenant authorization.
    """
    return request.headers.get("X-Tenant")


def get_user_module_roles(user_roles):
    """Extract module permissions from user roles"""
    modules = set()

    for role in user_roles:
        if role.startswith("Finance_"):
            modules.add("FIN")
        elif role.startswith("STR_"):
            modules.add("STR")
        elif role.startswith("ZZP_"):
            modules.add("ZZP")
        elif role.startswith("Members_"):
            modules.add("MEMBERS")

    return list(modules)


@tenant_module_bp.route("/api/tenant/modules", methods=["GET"])
@cognito_required(required_permissions=[])
def get_tenant_modules(user_email, user_roles):
    """
    Get available modules for current tenant

    Returns modules that:
    1. The tenant has enabled
    2. The user has permissions for

    Returns:
        {
            "tenant": "ExampleTenant",
            "available_modules": ["FIN", "STR"],
            "user_module_permissions": ["FIN", "STR"]
        }
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({"error": "No tenant specified"}), 400

        # Verify user has access to this tenant
        user_tenants = get_user_tenants_from_jwt(request)
        if tenant not in user_tenants:
            return jsonify({"error": "Access denied to tenant"}), 403

        # Get tenant's enabled modules from database
        with db_manager.get_cursor_only() as cursor:
            cursor.execute(
                """
                SELECT module_name
                FROM tenant_modules
                WHERE administration = %s AND is_active = TRUE
                ORDER BY module_name
            """,
                (tenant,),
            )

            results = cursor.fetchall()
            tenant_modules = [row["module_name"] for row in results]

        # Get user's module permissions
        user_module_permissions = get_user_module_roles(user_roles)

        # Return intersection (modules user has permission for AND tenant has enabled)
        available_modules = [m for m in user_module_permissions if m in tenant_modules]

        return jsonify(
            {
                "tenant": tenant,
                "available_modules": available_modules,
                "user_module_permissions": user_module_permissions,
                "tenant_enabled_modules": tenant_modules,
            }
        )

    except Exception as e:
        logger.error(f"Error getting tenant modules: {e}")
        return jsonify({"error": "Internal server error"}), 500


@tenant_module_bp.route("/api/tenant/modules/all", methods=["GET"])
@cognito_required(required_permissions=[])
def get_all_tenant_modules(user_email, user_roles):
    """
    Get module configuration for all user's tenants

    Useful for displaying module availability when switching tenants.

    Returns:
        {
            "tenants": {
                "MyTenant": ["FIN"],
                "ExampleTenant": ["FIN", "STR"]
            }
        }
    """
    try:
        # Get user's tenants
        user_tenants = get_user_tenants_from_jwt(request)
        if not user_tenants:
            return jsonify({"tenants": {}})

        # Get user's module permissions
        user_module_permissions = get_user_module_roles(user_roles)

        # Get modules for each tenant
        tenant_modules_map = {}

        with db_manager.get_cursor_only() as cursor:
            for tenant in user_tenants:
                cursor.execute(
                    """
                    SELECT module_name
                    FROM tenant_modules
                    WHERE administration = %s AND is_active = TRUE
                    ORDER BY module_name
                """,
                    (tenant,),
                )

                results = cursor.fetchall()
                tenant_modules = [row["module_name"] for row in results]

                # Return intersection
                available = [m for m in user_module_permissions if m in tenant_modules]
                tenant_modules_map[tenant] = available

        return jsonify(
            {
                "tenants": tenant_modules_map,
                "user_module_permissions": user_module_permissions,
            }
        )

    except Exception as e:
        logger.error(f"Error getting all tenant modules: {e}")
        return jsonify({"error": "Internal server error"}), 500


@tenant_module_bp.route("/api/tenant/modules", methods=["POST"])
@cognito_required(required_permissions=[])
def update_tenant_module(user_email, user_roles):
    """
    Enable or disable a module for a tenant (Tenant_Admin only)

    Request body:
        {
            "module_name": "FIN", "STR", "ZZP", etc.,
            "is_active": true or false
        }
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({"error": "No tenant specified"}), 400

        # Check if user is Tenant_Admin
        user_tenants = get_user_tenants_from_jwt(request)
        is_tenant_admin = "Tenant_Admin" in user_roles and tenant in user_tenants

        if not is_tenant_admin:
            return jsonify({"error": "Tenant_Admin access required"}), 403

        # Get request data
        data = request.get_json()
        module_name = data.get("module_name")
        is_active = data.get("is_active", True)

        # Validate module name
        from services.module_registry import MODULE_REGISTRY, activate_module

        if module_name not in MODULE_REGISTRY:
            valid = ", ".join(MODULE_REGISTRY.keys())
            return jsonify(
                {"error": f"Invalid module name. Must be one of: {valid}"}
            ), 400

        if is_active:
            # Use activate_module for dependency enforcement
            try:
                activate_module(
                    db_manager, tenant, module_name, activated_by=user_email
                )
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
        else:
            # Deactivation — no dependency check needed
            with db_manager.get_cursor() as (cursor, conn):
                cursor.execute(
                    """
                    INSERT INTO tenant_modules (administration, module_name, is_active, created_by)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        is_active = %s,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    (tenant, module_name, is_active, user_email, is_active),
                )
                conn.commit()

        logger.info(
            f"Tenant module updated: {tenant}.{module_name} = {is_active} by {user_email}"
        )

        return jsonify(
            {
                "success": True,
                "tenant": tenant,
                "module_name": module_name,
                "is_active": is_active,
            }
        )

    except Exception as e:
        logger.error(f"Error updating tenant module: {e}")
        return jsonify({"error": "Internal server error"}), 500


@tenant_module_bp.route("/api/tenant/admin-surfaces", methods=["GET"])
@cognito_required(required_permissions=[])
def get_admin_surfaces(user_email, user_roles):
    """Derived Tenant-Admin surfaces for the current tenant.

    Registry-driven replacement for the dashboard's hardcoded tab list: the Flask
    plane derives which surfaces apply and the frontend just renders them.

    The tenant is resolved from the ``X-Tenant`` *selector* and validated against the
    caller's VERIFIED tenant list (``custom:tenants``, ADR 0004/0005) — never the
    module edge's capability-scoped ``tenant_keys`` (ADR 0007), and the header never
    grants a tenant. Entitlement_Truth is ``tenant_modules`` for that tenant (ADR 0005);
    the caller's roles come from the verified request context.

    Returns:
        {
            "tenant": "h-dcn",
            "admin_surfaces": [{"id", "kind", "order", "label_key"}, ...]
        }
    """
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({"error": "No tenant specified"}), 400

        # X-Tenant selects among the caller's verified tenants; unlisted -> 403.
        user_tenants = get_user_tenants_from_jwt(request)
        if tenant not in user_tenants:
            return jsonify({"error": "Access denied to tenant"}), 403

        # Entitlement_Truth: the tenant's ACTIVE modules (not the caller's module roles).
        with db_manager.get_cursor() as (cursor, conn):
            cursor.execute(
                """
                SELECT module_name
                FROM tenant_modules
                WHERE administration = %s AND is_active = TRUE
                """,
                (tenant,),
            )
            rows = cursor.fetchall()
            entitled_modules = [row["module_name"] for row in rows]

        from services.admin_surface_registry import derive_admin_surfaces

        derived = derive_admin_surfaces(entitled_modules, list(user_roles or []))
        # Public contract only: never leak internal registry descriptor fields
        # (owning module, role lists) into the response.
        surfaces = [
            {
                "id": surface["id"],
                "kind": surface["kind"],
                "order": surface["order"],
                "label_key": surface["label_key"],
            }
            for surface in derived
        ]

        response = jsonify({"tenant": tenant, "admin_surfaces": surfaces})
        # A tenant switch must never replay a previous tenant's surface list.
        response.headers["Cache-Control"] = "no-store"
        return response

    except Exception as e:
        logger.error(f"Error deriving admin surfaces for tenant: {e}")
        return jsonify({"error": "Internal server error"}), 500
