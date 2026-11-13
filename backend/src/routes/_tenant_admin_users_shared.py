"""Shared Cognito clients and user/role lookup helpers for tenant-admin routes.

Extracted from ``routes.tenant_admin_users`` (task 15 split). Both
``routes.tenant_admin_users`` and ``routes.tenant_admin_roles`` depend on these
symbols; the former re-exports them so its public import surface — and the
existing patch points (``routes.tenant_admin_users.cognito_client``,
``.cognito_service``, ``.get_available_roles_for_tenant``, ...) — stay unchanged.
"""

import json
import os

import boto3

from database import DatabaseManager
from services.cognito_service import CognitoService

# Initialize Cognito client
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")
cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)
cognito_service = CognitoService()


def get_user_attribute(user_attributes, attribute_name) -> str | None:
    """Extract attribute value from Cognito user attributes"""
    for attr in user_attributes:
        if attr["Name"] == attribute_name:
            value = attr["Value"]
            # Handle JSON arrays (custom:tenants)
            if attribute_name == "custom:tenants":
                try:
                    return json.loads(value) if value else []
                except Exception:
                    return [value] if value else []
            return value
    return None


def get_tenant_enabled_modules(tenant) -> list[str]:
    """Get enabled modules for tenant from database"""
    try:
        db = DatabaseManager()

        query = """
            SELECT module_name
            FROM tenant_modules
            WHERE administration = %s AND is_active = TRUE
        """
        result = db.execute_query(query, [tenant], fetch=True)
        return [row["module_name"] for row in (result or [])]
    except Exception as e:
        print(f"Error getting tenant modules: {e}", flush=True)
        return []


def get_available_roles_for_tenant(tenant) -> list[dict[str, str]]:
    """Get list of roles available for tenant based on enabled modules.

    Reads required_roles from MODULE_REGISTRY so new modules are picked up
    automatically without changing this function.
    """
    from services.module_registry import MODULE_REGISTRY

    enabled_modules = get_tenant_enabled_modules(tenant)

    roles = ["Tenant_Admin"]  # Always available

    # Add module-specific roles dynamically from MODULE_REGISTRY
    for module_name in enabled_modules:
        module_def = MODULE_REGISTRY.get(module_name)
        if module_def:
            roles.extend(module_def.get("required_roles", []))

    # Deduplicate while preserving order
    seen = set()
    available_roles = []
    for r in roles:
        if r not in seen:
            seen.add(r)
            available_roles.append(r)

    return available_roles
