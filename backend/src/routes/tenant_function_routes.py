"""
Tenant Function Routes

API endpoints for managing tenant-specific optional function toggles.
Allows Tenant Admins to enable/disable optional functions within active modules.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.5
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import logging
import os

from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.function_registry import FUNCTION_REGISTRY
from services.module_registry import has_module
from services.tenant_function_service import TenantFunctionService

logger = logging.getLogger(__name__)

tenant_function_bp = Blueprint("tenant_functions", __name__)


def _get_service() -> "TenantFunctionService":
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    db = DatabaseManager(test_mode=test_mode)
    return TenantFunctionService(db)


@tenant_function_bp.route("/api/tenant/functions", methods=["GET"])
@cognito_required(required_permissions=[])
@tenant_required()
def get_tenant_functions(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Get all optional functions with their activation state for the current tenant.

    Returns the full list of functions from FUNCTION_REGISTRY, each annotated
    with toggle state, parent module activity, and effective state.

    Any authenticated user with tenant access can call this endpoint.
    """
    try:
        service = _get_service()
        functions = service.get_all_functions(tenant)
        return jsonify({"success": True, "data": functions})
    except Exception as e:
        logger.error(f"Error getting tenant functions: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@tenant_function_bp.route("/api/tenant/functions", methods=["POST"])
@cognito_required(required_permissions=[])
@tenant_required()
def toggle_tenant_function(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """
    Toggle an optional function for the current tenant.

    Restricted to Tenant_Admin role. Validates that:
    - User has Tenant_Admin role
    - Request body contains valid JSON with function_name and is_active
    - function_name exists in FUNCTION_REGISTRY
    - is_active is a boolean
    - Parent module is active for the tenant
    """
    try:
        # Step 1: Check Tenant_Admin role
        if "Tenant_Admin" not in user_roles:
            return jsonify({"success": False, "error": "Access denied"}), 403

        # Step 2: Parse request body
        data = request.get_json(silent=True)
        if not data:
            return jsonify(
                {
                    "success": False,
                    "error": "Request body must be valid JSON with "
                    '"function_name" and "is_active" fields',
                }
            ), 400

        function_name = data.get("function_name")
        is_active = data.get("is_active")

        # Step 3: Validate function_name in FUNCTION_REGISTRY
        if not function_name or function_name not in FUNCTION_REGISTRY:
            valid_names = list(FUNCTION_REGISTRY.keys())
            return jsonify(
                {
                    "success": False,
                    "error": f"Invalid function_name. Must be one of: {valid_names}",
                }
            ), 400

        # Step 4: Validate is_active is a boolean
        if is_active is None or not isinstance(is_active, bool):
            return jsonify(
                {
                    "success": False,
                    "error": 'Missing or invalid "is_active" field: must be a boolean',
                }
            ), 400

        # Step 5: Check parent module is active
        parent_module = FUNCTION_REGISTRY[function_name]["parent_module"]
        db = DatabaseManager(
            test_mode=os.getenv("TEST_MODE", "false").lower() == "true"
        )
        if not has_module(db, tenant, parent_module):
            return jsonify(
                {
                    "success": False,
                    "error": f"Parent module '{parent_module}' must be activated first",
                }
            ), 400

        # Step 6: Persist the toggle state
        service = _get_service()
        result = service.set_function_state(
            tenant, function_name, is_active, user_email
        )

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"Error toggling tenant function: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
