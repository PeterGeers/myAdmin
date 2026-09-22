"""
Parameter Administration API

CRUD endpoints for managing parameters via the ParameterService.
Tenant_Admin can manage tenant-scope, SysAdmin can manage system-scope.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import logging
import os

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

parameter_admin_bp = Blueprint("parameter_admin", __name__)

flag = os.getenv("TEST_MODE", "false").lower() == "true"


def _get_service() -> "ParameterService":
    db = DatabaseManager(test_mode=flag)
    from services.credential_service import CredentialService

    credential_service = CredentialService(db)
    return ParameterService(db, credential_service=credential_service)


def _is_sysadmin(user_roles) -> bool:
    return "SysAdmin" in (user_roles or [])


def _validate_members_config(svc, namespace, key, value, tenant) -> None:
    """Fail-fast save-time validation for members.* config (s5c 2.4; no-op otherwise).

    Delegates to services.members_config_validation. For members.view_contexts the
    resolvable field set is widened by the tenant's sibling members.field_overlay and
    members.scope_dimensions (read via the ParameterService), so a context may reference
    the tenant's own parameter/overlay fields and scope dimensions. Raises
    MembersConfigError (a ValueError → 400) if the config is invalid.
    """
    if namespace != "members":
        return
    from services.members_config_validation import validate_members_param

    sibling_overlay = None
    sibling_scope = None
    if key == "view_contexts":
        # Read the tenant's sibling members.* values so the tenant's added fields resolve.
        sibling_overlay = svc.get_param("members", "field_overlay", tenant=tenant)
        sibling_scope = svc.get_param("members", "scope_dimensions", tenant=tenant)

    validate_members_param(
        key,
        value,
        sibling_field_overlay=sibling_overlay,
        sibling_scope_dimensions=sibling_scope,
    )


@parameter_admin_bp.route("/api/tenant-admin/parameters", methods=["GET"])
@cognito_required(required_permissions=[])
@tenant_required()
def list_parameters(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List all parameters for tenant, grouped by namespace, with scope origin."""
    try:
        svc = _get_service()
        ns_filter = request.args.get("namespace")
        is_admin = _is_sysadmin(user_roles)

        # Get tenant's active modules for filtering
        db = DatabaseManager(test_mode=flag)
        module_rows = db.execute_query(
            "SELECT module_name FROM tenant_modules "
            "WHERE administration = %s AND is_active = TRUE",
            (tenant,),
            fetch=True,
        )
        active_modules = [r["module_name"] for r in module_rows] if module_rows else []

        # Build set of allowed namespaces based on active modules
        from services.parameter_schema import PARAMETER_SCHEMA

        excluded_namespaces = set()
        for ns, section in PARAMETER_SCHEMA.items():
            module = section.get("module")
            if module and module not in active_modules:
                excluded_namespaces.add(ns)

        if ns_filter:
            if ns_filter in excluded_namespaces:
                params = []
            else:
                params = svc.get_params_by_namespace(ns_filter, tenant)
        else:
            all_params = []

            # Discover namespaces from DB rows
            rows = db.execute_query(
                "SELECT DISTINCT namespace FROM parameters "
                "WHERE (scope = 'tenant' AND scope_id = %s) OR scope = 'system' "
                "ORDER BY namespace",
                (tenant,),
                fetch=True,
            )
            db_namespaces = {row["namespace"] for row in rows}

            # Also discover namespaces from CODE_DEFAULTS
            from services.parameter_service import CODE_DEFAULTS

            for ns, _key in CODE_DEFAULTS:
                db_namespaces.add(ns)

            # Filter out namespaces belonging to inactive modules
            db_namespaces -= excluded_namespaces

            for ns in sorted(db_namespaces):
                ns_params = svc.get_params_by_namespace(ns, tenant)
                all_params.extend(ns_params)
            params = all_params

        # Mask secrets for non-SysAdmin
        for p in params:
            if p.get("is_secret") and not is_admin:
                p["value"] = "********"

        # Group by namespace
        grouped = {}
        for p in params:
            ns = p["namespace"]
            if ns not in grouped:
                grouped[ns] = []
            grouped[ns].append(p)

        return jsonify({"success": True, "tenant": tenant, "parameters": grouped})
    except Exception as e:
        logger.error("Error listing parameters: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@parameter_admin_bp.route("/api/tenant-admin/parameters", methods=["POST"])
@cognito_required(required_permissions=[])
@tenant_required()
def create_parameter(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Create a parameter with value_type validation."""
    try:
        data = request.get_json()
        scope = data.get("scope", "tenant")
        namespace = data.get("namespace")
        key = data.get("key")
        value = data.get("value")
        value_type = data.get("value_type", "string")
        is_secret = data.get("is_secret", False)

        if not namespace or not key:
            return jsonify(
                {"success": False, "error": "namespace and key are required"}
            ), 400

        if scope == "system" and not _is_sysadmin(user_roles):
            return jsonify(
                {"success": False, "error": "SysAdmin required for system scope"}
            ), 403

        scope_id = "_system_" if scope == "system" else tenant

        svc = _get_service()

        # s5c R5.1a/R4.9 (Property 7) — authoritative save-time validation for members.*
        # config (fail-fast, before the write, so a dangling reference / invalid overlay
        # never corrupts the stored config or the projection). No-op for other namespaces.
        _validate_members_config(svc, namespace, key, value, tenant)

        svc.set_param(
            scope,
            scope_id,
            namespace,
            key,
            value,
            value_type=value_type,
            is_secret=is_secret,
            created_by=user_email,
        )

        # S3 R5.1 — on-change projection sync trigger. A tenant-scope config
        # parameter committed above; signal a projection sync for the affected
        # tenant (the write's own scope, never a default). Only tenant-scope
        # writes touch the tenant projection — system scope is not tenant-specific.
        # Best-effort: never breaks the parameter write (reconciliation backstops).
        if scope == "tenant":
            from services.projection_sync_trigger import enqueue_sync

            enqueue_sync(scope_id)

        return jsonify(
            {"success": True, "message": f"Parameter {namespace}.{key} created"}
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Error creating parameter: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@parameter_admin_bp.route(
    "/api/tenant-admin/parameters/<int:param_id>", methods=["PUT"]
)
@cognito_required(required_permissions=[])
@tenant_required()
def update_parameter(
    user_email, user_roles, tenant, user_tenants, param_id
) -> ResponseReturnValue:
    """Update a parameter value, invalidate cache."""
    try:
        data = request.get_json()
        value = data.get("value")
        value_type = data.get("value_type")

        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT scope, scope_id, namespace, `key`, value_type, is_secret "
            "FROM parameters WHERE id = %s",
            (param_id,),
            fetch=True,
        )
        if not rows:
            return jsonify({"success": False, "error": "Parameter not found"}), 404

        row = rows[0]
        if row["scope"] == "system" and not _is_sysadmin(user_roles):
            return jsonify(
                {"success": False, "error": "SysAdmin required for system scope"}
            ), 403
        if row["scope"] == "tenant" and row["scope_id"] != tenant:
            return jsonify(
                {"success": False, "error": "Parameter not owned by this tenant"}
            ), 404

        svc = _get_service()

        # s5c R5.1a/R4.9 (Property 7) — authoritative save-time validation for members.*
        # config on update (fail-fast, before the write). No-op for other namespaces.
        _validate_members_config(
            svc, row["namespace"], row["key"], value, row["scope_id"]
        )

        svc.set_param(
            row["scope"],
            row["scope_id"],
            row["namespace"],
            row["key"],
            value,
            value_type=value_type or row["value_type"],
            is_secret=row["is_secret"],
            created_by=user_email,
        )

        # S3 R5.1 — on-change projection sync trigger. A tenant-scope config
        # parameter committed above; signal a projection sync for the affected
        # tenant (the row's own scope_id, verified to equal this tenant above).
        # Only tenant-scope writes touch the tenant projection — system scope is
        # not tenant-specific. Best-effort: never breaks the parameter write
        # (reconciliation backstops a missed signal).
        if row["scope"] == "tenant":
            from services.projection_sync_trigger import enqueue_sync

            enqueue_sync(row["scope_id"])

        return jsonify({"success": True, "message": "Parameter updated"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Error updating parameter %s: %s", param_id, e)
        return jsonify({"success": False, "error": str(e)}), 500


@parameter_admin_bp.route(
    "/api/tenant-admin/parameters/<int:param_id>", methods=["DELETE"]
)
@cognito_required(required_permissions=[])
@tenant_required()
def delete_parameter(
    user_email, user_roles, tenant, user_tenants, param_id
) -> ResponseReturnValue:
    """Delete a parameter override at specified scope."""
    try:
        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT scope, scope_id, namespace, `key` FROM parameters WHERE id = %s",
            (param_id,),
            fetch=True,
        )
        if not rows:
            return jsonify({"success": False, "error": "Parameter not found"}), 404

        row = rows[0]
        if row["scope"] == "system" and not _is_sysadmin(user_roles):
            return jsonify(
                {"success": False, "error": "SysAdmin required for system scope"}
            ), 403
        if row["scope"] == "tenant" and row["scope_id"] != tenant:
            return jsonify(
                {"success": False, "error": "Parameter not owned by this tenant"}
            ), 404

        svc = _get_service()
        deleted = svc.delete_param(
            row["scope"], row["scope_id"], row["namespace"], row["key"]
        )

        if deleted:
            # S3 R5.1 — on-change projection sync trigger. A tenant-scope config
            # parameter override was deleted and committed above; signal a
            # projection sync for the affected tenant (the row's own scope_id,
            # verified to equal this tenant above). Only tenant-scope writes touch
            # the tenant projection — system scope is not tenant-specific.
            # Best-effort: never breaks the delete (reconciliation backstops).
            if row["scope"] == "tenant":
                from services.projection_sync_trigger import enqueue_sync

                enqueue_sync(row["scope_id"])

            return jsonify({"success": True, "message": "Parameter deleted"})
        return jsonify({"success": False, "error": "Delete failed"}), 500
    except Exception as e:
        logger.error("Error deleting parameter %s: %s", param_id, e)
        return jsonify({"success": False, "error": str(e)}), 500


@parameter_admin_bp.route("/api/tenant-admin/parameters/default", methods=["GET"])
@cognito_required(required_permissions=[])
@tenant_required()
def get_parameter_default(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Return the default value for a parameter (CODE_DEFAULT or system-scope DB row).

    Query params: namespace, key
    Resolution order: CODE_DEFAULTS → system-scope DB row → has_default: false
    Secret values are masked for non-SysAdmin users.

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    Reference: .kiro/specs/parameter-reset-to-default/design.md
    """
    namespace = request.args.get("namespace")
    key = request.args.get("key")

    if not namespace or not key:
        return jsonify(
            {"success": False, "error": "namespace and key are required"}
        ), 400

    try:
        is_admin = _is_sysadmin(user_roles)

        # 1. Check CODE_DEFAULTS
        from services.parameter_service import CODE_DEFAULTS

        code_default = CODE_DEFAULTS.get((namespace, key))
        if code_default is not None:
            value = code_default["value"]
            if code_default.get("is_secret", False) and not is_admin:
                value = "********"
            return jsonify(
                {
                    "success": True,
                    "has_default": True,
                    "value": value,
                    "value_type": code_default["value_type"],
                    "source": "code_default",
                }
            )

        # 2. Check system-scope DB row
        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT value, value_type, is_secret FROM parameters "
            "WHERE scope = 'system' AND namespace = %s AND `key` = %s LIMIT 1",
            (namespace, key),
            fetch=True,
        )
        if rows:
            row = rows[0]
            parsed = ParameterService._parse_json_value(row["value"])
            if row["is_secret"] and not is_admin:
                parsed = "********"
            return jsonify(
                {
                    "success": True,
                    "has_default": True,
                    "value": parsed,
                    "value_type": row["value_type"],
                    "source": "system",
                }
            )

        # 3. No default
        return jsonify({"success": True, "has_default": False})
    except Exception as e:
        logger.error("Error fetching parameter default: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


@parameter_admin_bp.route("/api/tenant-admin/parameters/schema", methods=["GET"])
@cognito_required(required_permissions=[])
@tenant_required()
def get_parameter_schema(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Return parameter schema filtered by tenant's active modules, with current values."""
    try:
        import copy

        from services.parameter_schema import get_schema_for_tenant

        db = DatabaseManager(test_mode=flag)

        module_rows = db.execute_query(
            "SELECT module_name FROM tenant_modules "
            "WHERE administration = %s AND is_active = TRUE",
            (tenant,),
            fetch=True,
        )
        active_modules = [r["module_name"] for r in module_rows] if module_rows else []

        schema = get_schema_for_tenant(active_modules)

        svc = _get_service()
        result = copy.deepcopy(schema)
        for ns, section in result.items():
            for key, param_def in section.get("params", {}).items():
                current = svc.get_param(ns, key, tenant=tenant)
                param_def["current_value"] = current
                if param_def.get("required") and current is None:
                    param_def["missing"] = True

        return jsonify(
            {
                "success": True,
                "tenant": tenant,
                "active_modules": active_modules,
                "schema": result,
            }
        )
    except Exception as e:
        logger.error("Error getting parameter schema: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500
