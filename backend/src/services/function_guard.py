"""
Function Guard: Route decorator that enforces function-level access control.

Checks (in order):
1. Tenant context is available (from @tenant_required())
2. Parent module is active for the tenant (via has_module())
3. Function toggle is enabled for the tenant (via TenantFunctionService)

Returns HTTP 403 with appropriate JSON error messages for each failure case.

Must be placed after @tenant_required() in the decorator stack.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import functools
import os

from flask import jsonify


def function_guard(function_name: str, module_name: str):
    """
    Decorator that checks function activation for the current tenant.
    Must be placed after @tenant_required() in the decorator stack.

    Usage:
        @route_bp.route('/api/fin/assets', methods=['GET'])
        @cognito_required(required_permissions=['finance_read'])
        @tenant_required()
        @function_guard('assets', 'FIN')
        def get_assets(user_email, user_roles, tenant, user_tenants):
            ...

    Args:
        function_name: The function identifier from FUNCTION_REGISTRY.
        module_name: The parent module name to check (e.g. 'FIN', 'STR').

    Returns:
        Decorated function that enforces function-level access control.
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Step 1: Check tenant context is available
            tenant = kwargs.get("tenant")
            if not tenant:
                return jsonify(
                    {"success": False, "error": "Tenant context required"}
                ), 403

            # Create DatabaseManager instance
            from database import DatabaseManager

            test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
            db = DatabaseManager(test_mode=test_mode)

            # Step 2: Check parent module is active
            from services.module_registry import has_module

            if not has_module(db, tenant, module_name):
                return jsonify(
                    {
                        "success": False,
                        "error": f"Module '{module_name}' is not active for this tenant",
                    }
                ), 403

            # Step 3: Check function toggle is enabled
            from services.tenant_function_service import TenantFunctionService

            service = TenantFunctionService(db)
            if not service.get_function_state(tenant, function_name):
                return jsonify(
                    {
                        "success": False,
                        "error": f"Function '{function_name}' is disabled for this tenant",
                    }
                ), 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator
