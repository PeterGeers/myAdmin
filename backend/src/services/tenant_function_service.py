"""
TenantFunctionService: Manages per-tenant function activation state.

Reads and writes function toggle overrides in the `tenant_functions` table,
merging with FUNCTION_REGISTRY defaults and checking parent module state
via has_module().

Requirements: 2.3, 2.4, 2.5, 6.1, 6.2, 6.3, 6.4
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from database import DatabaseManager
from db_exceptions import DatabaseError
from services.function_registry import FUNCTION_REGISTRY
from services.module_registry import has_module

logger = logging.getLogger(__name__)


class TenantFunctionService:
    """Service for managing per-tenant optional function activation state."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_function_state(self, tenant: str, function_name: str) -> bool:
        """
        Returns the effective enabled state for a single function.

        Queries the tenant_functions table for an override. If no row exists,
        falls back to the registry's default_enabled value.
        On DB read failure, falls back to registry default (graceful degradation).

        Args:
            tenant: The tenant administration name.
            function_name: The function identifier from FUNCTION_REGISTRY.

        Returns:
            True if the function is enabled (toggle state only, does not check module).
        """
        registry_entry = FUNCTION_REGISTRY.get(function_name)
        if not registry_entry:
            logger.warning(
                "Unknown function '%s' requested for tenant '%s'",
                function_name, tenant
            )
            return False

        default = registry_entry['default_enabled']

        try:
            query = """
                SELECT is_active
                FROM tenant_functions
                WHERE administration = %s AND function_name = %s
            """
            result = self.db.execute_query(query, (tenant, function_name))
            if result:
                return bool(result[0]['is_active'])
            return default
        except Exception as e:
            logger.error(
                "DB read failed for function '%s', tenant '%s': %s. "
                "Falling back to registry default.",
                function_name, tenant, e
            )
            return default

    def get_all_functions(self, tenant: str) -> List[Dict[str, Any]]:
        """
        Returns all functions with effective state, respecting module activation.

        Merges FUNCTION_REGISTRY with any tenant-specific overrides from the
        tenant_functions table, and checks has_module() for each function's
        parent module.

        On DB read failure, returns registry defaults with module state checks.

        Args:
            tenant: The tenant administration name.

        Returns:
            List of dicts with function_name, parent_module, label, is_active,
            module_active, and effective fields.
        """
        # Load all overrides for this tenant
        overrides = {}
        try:
            query = """
                SELECT function_name, is_active
                FROM tenant_functions
                WHERE administration = %s
            """
            rows = self.db.execute_query(query, (tenant,))
            if rows:
                for row in rows:
                    overrides[row['function_name']] = bool(row['is_active'])
        except Exception as e:
            logger.error(
                "DB read failed for tenant '%s' functions: %s. "
                "Using registry defaults only.",
                tenant, e
            )

        # Build the merged function list
        functions = []
        for func_name, definition in FUNCTION_REGISTRY.items():
            parent_module = definition['parent_module']

            # Determine toggle state: override if available, else registry default
            is_active = overrides.get(func_name, definition['default_enabled'])

            # Check parent module activation
            module_active = has_module(self.db, tenant, parent_module)

            # Effective state: both function toggle AND parent module must be active
            effective = is_active and module_active

            functions.append({
                'function_name': func_name,
                'parent_module': parent_module,
                'label': definition['label'],
                'is_active': is_active,
                'module_active': module_active,
                'effective': effective,
            })

        return functions

    def set_function_state(self, tenant: str, function_name: str,
                           is_active: bool, user_email: str) -> Dict[str, Any]:
        """
        Persists toggle state using INSERT ... ON DUPLICATE KEY UPDATE.

        Args:
            tenant: The tenant administration name.
            function_name: The function identifier from FUNCTION_REGISTRY.
            is_active: The desired activation state.
            user_email: Email of the user making the change (audit).

        Returns:
            Dict with success status and data on success, or error on failure.

        Requirement 2.4: On DB write failure, returns error response indicating
        persistence failure without modifying existing state.
        """
        registry_entry = FUNCTION_REGISTRY.get(function_name)
        if not registry_entry:
            return {
                'success': False,
                'error': f"Unknown function '{function_name}'",
            }

        try:
            query = """
                INSERT INTO tenant_functions
                    (administration, function_name, is_active, created_by)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    is_active = VALUES(is_active),
                    updated_at = CURRENT_TIMESTAMP
            """
            self.db.execute_query(
                query,
                (tenant, function_name, is_active, user_email),
                fetch=False,
                commit=True,
            )

            return {
                'success': True,
                'data': {
                    'function_name': function_name,
                    'is_active': is_active,
                },
            }
        except Exception as e:
            logger.error(
                "DB write failed for function '%s', tenant '%s': %s",
                function_name, tenant, e
            )
            return {
                'success': False,
                'error': f"Failed to persist function state: {e}",
            }

    def is_function_enabled(self, tenant: str, function_name: str,
                            module_name: str) -> Tuple[bool, Optional[str]]:
        """
        Checks module + function state.

        Returns a tuple of (enabled: bool, error_reason: str | None).
        - If the parent module is inactive, returns (False, module error message).
        - If the function toggle is off, returns (False, function error message).
        - If both are active, returns (True, None).

        Args:
            tenant: The tenant administration name.
            function_name: The function identifier.
            module_name: The parent module name to check.

        Returns:
            Tuple of (enabled, error_reason).
        """
        # Check parent module first
        if not has_module(self.db, tenant, module_name):
            return (
                False,
                f"Module '{module_name}' is not active for this tenant",
            )

        # Check function toggle state
        function_active = self.get_function_state(tenant, function_name)
        if not function_active:
            return (
                False,
                f"Function '{function_name}' is disabled for this tenant",
            )

        return (True, None)
