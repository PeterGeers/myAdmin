"""
Parameter Administration API

CRUD endpoints for managing parameters via the ParameterService.
Tenant_Admin can manage tenant-scope, SysAdmin can manage system-scope.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
Reference: .kiro/specs/parameter-driven-config/design.md
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.parameter_service import ParameterService
import os
import logging

logger = logging.getLogger(__name__)

parameter_admin_bp = Blueprint('parameter_admin', __name__)

flag = os.getenv('TEST_MODE', 'false').lower() == 'true'


def _get_service():
    db = DatabaseManager(test_mode=flag)
    return ParameterService(db)


def _is_sysadmin(user_roles):
    return 'SysAdmin' in (user_roles or [])


@parameter_admin_bp.route('/api/tenant-admin/parameters', methods=['GET'])
@cognito_required(required_permissions=[])
@tenant_required()
def list_parameters(user_email, user_roles, tenant, user_tenants):
    """List all parameters for tenant, grouped by namespace, with scope origin."""
    try:
        svc = _get_service()
        ns_filter = request.args.get('namespace')
        is_admin = _is_sysadmin(user_roles)

        if ns_filter:
            params = svc.get_params_by_namespace(ns_filter, tenant)
        else:
            all_params = []
            db = DatabaseManager(test_mode=flag)
            rows = db.execute_query(
                "SELECT DISTINCT namespace FROM parameters "
                "WHERE (scope = 'tenant' AND scope_id = %s) OR scope = 'system' "
                "ORDER BY namespace",
                (tenant,), fetch=True
            )
            for row in rows:
                ns_params = svc.get_params_by_namespace(row['namespace'], tenant)
                all_params.extend(ns_params)
            params = all_params

        # Mask secrets for non-SysAdmin
        for p in params:
            if p.get('is_secret') and not is_admin:
                p['value'] = '********'

        # Group by namespace
        grouped = {}
        for p in params:
            ns = p['namespace']
            if ns not in grouped:
                grouped[ns] = []
            grouped[ns].append(p)

        return jsonify({
            'success': True,
            'tenant': tenant,
            'parameters': grouped
        })
    except Exception as e:
        logger.error("Error listing parameters: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@parameter_admin_bp.route('/api/tenant-admin/parameters', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def create_parameter(user_email, user_roles, tenant, user_tenants):
    """Create a parameter with value_type validation."""
    try:
        data = request.get_json()
        scope = data.get('scope', 'tenant')
        namespace = data.get('namespace')
        key = data.get('key')
        value = data.get('value')
        value_type = data.get('value_type', 'string')
        is_secret = data.get('is_secret', False)

        if not namespace or not key:
            return jsonify({'success': False, 'error': 'namespace and key are required'}), 400

        if scope == 'system' and not _is_sysadmin(user_roles):
            return jsonify({'success': False, 'error': 'SysAdmin required for system scope'}), 403

        scope_id = '_system_' if scope == 'system' else tenant

        svc = _get_service()
        svc.set_param(scope, scope_id, namespace, key, value,
                       value_type=value_type, is_secret=is_secret,
                       created_by=user_email)

        return jsonify({'success': True, 'message': f'Parameter {namespace}.{key} created'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error("Error creating parameter: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@parameter_admin_bp.route('/api/tenant-admin/parameters/<int:param_id>', methods=['PUT'])
@cognito_required(required_permissions=[])
@tenant_required()
def update_parameter(user_email, user_roles, tenant, user_tenants, param_id):
    """Update a parameter value, invalidate cache."""
    try:
        data = request.get_json()
        value = data.get('value')
        value_type = data.get('value_type')

        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT scope, scope_id, namespace, `key`, value_type, is_secret "
            "FROM parameters WHERE id = %s", (param_id,), fetch=True
        )
        if not rows:
            return jsonify({'success': False, 'error': 'Parameter not found'}), 404

        row = rows[0]
        if row['scope'] == 'system' and not _is_sysadmin(user_roles):
            return jsonify({'success': False, 'error': 'SysAdmin required for system scope'}), 403
        if row['scope'] == 'tenant' and row['scope_id'] != tenant:
            return jsonify({'success': False, 'error': 'Parameter not owned by this tenant'}), 404

        svc = _get_service()
        svc.set_param(
            row['scope'], row['scope_id'], row['namespace'], row['key'],
            value, value_type=value_type or row['value_type'],
            is_secret=row['is_secret'], created_by=user_email
        )

        return jsonify({'success': True, 'message': f'Parameter updated'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error("Error updating parameter %s: %s", param_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@parameter_admin_bp.route('/api/tenant-admin/parameters/<int:param_id>', methods=['DELETE'])
@cognito_required(required_permissions=[])
@tenant_required()
def delete_parameter(user_email, user_roles, tenant, user_tenants, param_id):
    """Delete a parameter override at specified scope."""
    try:
        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT scope, scope_id, namespace, `key` FROM parameters WHERE id = %s",
            (param_id,), fetch=True
        )
        if not rows:
            return jsonify({'success': False, 'error': 'Parameter not found'}), 404

        row = rows[0]
        if row['scope'] == 'system' and not _is_sysadmin(user_roles):
            return jsonify({'success': False, 'error': 'SysAdmin required for system scope'}), 403
        if row['scope'] == 'tenant' and row['scope_id'] != tenant:
            return jsonify({'success': False, 'error': 'Parameter not owned by this tenant'}), 404

        svc = _get_service()
        deleted = svc.delete_param(row['scope'], row['scope_id'], row['namespace'], row['key'])

        if deleted:
            return jsonify({'success': True, 'message': 'Parameter deleted'})
        return jsonify({'success': False, 'error': 'Delete failed'}), 500
    except Exception as e:
        logger.error("Error deleting parameter %s: %s", param_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@parameter_admin_bp.route('/api/tenant-admin/parameters/schema', methods=['GET'])
@cognito_required(required_permissions=[])
@tenant_required()
def get_parameter_schema(user_email, user_roles, tenant, user_tenants):
    """Return parameter schema filtered by tenant's active modules, with current values."""
    try:
        from services.parameter_schema import get_schema_for_tenant
        import copy

        db = DatabaseManager(test_mode=flag)

        module_rows = db.execute_query(
            "SELECT module_name FROM tenant_modules "
            "WHERE administration = %s AND is_active = TRUE",
            (tenant,), fetch=True
        )
        active_modules = [r['module_name'] for r in module_rows] if module_rows else []

        schema = get_schema_for_tenant(active_modules)

        svc = _get_service()
        result = copy.deepcopy(schema)
        for ns, section in result.items():
            for key, param_def in section.get('params', {}).items():
                current = svc.get_param(ns, key, tenant=tenant)
                param_def['current_value'] = current
                if param_def.get('required') and current is None:
                    param_def['missing'] = True

        return jsonify({
            'success': True,
            'tenant': tenant,
            'active_modules': active_modules,
            'schema': result,
        })
    except Exception as e:
        logger.error("Error getting parameter schema: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
