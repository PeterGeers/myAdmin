"""
Tenant Admin Config Routes

CRUD operations for tenant_config table entries.

Endpoints:
- GET /api/tenant-admin/config - List all config entries
- POST /api/tenant-admin/config - Create new config entry
- PUT /api/tenant-admin/config/<id> - Update config entry
- DELETE /api/tenant-admin/config/<id> - Delete config entry
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
import os
import logging

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_config_bp = Blueprint('tenant_admin_config', __name__, url_prefix='/api/tenant-admin')


@tenant_admin_config_bp.route('/config', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def list_configs(user_email, user_roles) -> ResponseReturnValue:
    """
    List all configuration entries for tenant
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with list of config entries
    """
    try:
        tenant = get_current_tenant(request)
        
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            SELECT id, config_key, config_value, is_secret, created_at, updated_at, created_by
            FROM tenant_config
            WHERE administration = %s
            ORDER BY config_key
        """
        
        results = db.execute_query(query, (tenant,))
        
        # Convert datetime to ISO format
        configs = []
        for row in results:
            configs.append({
                'id': row['id'],
                'config_key': row['config_key'],
                'config_value': row['config_value'],
                'is_secret': bool(row['is_secret']),
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                'created_by': row.get('created_by')
            })
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'configs': configs,
            'count': len(configs)
        })
        
    except Exception as e:
        logger.error(f"Error listing configs: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_config_bp.route('/config', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def create_config(user_email, user_roles) -> ResponseReturnValue:
    """
    Create new configuration entry
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "config_key": "key_name",
        "config_value": "value",
        "is_secret": false
    }
    
    Returns:
        JSON with created config entry
    """
    try:
        tenant = get_current_tenant(request)
        data = request.get_json()
        
        config_key = data.get('config_key')
        config_value = data.get('config_value', '')
        is_secret = data.get('is_secret', False)
        
        if not config_key:
            return jsonify({'error': 'config_key is required'}), 400
        
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            INSERT INTO tenant_config (administration, config_key, config_value, is_secret, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """
        
        db.execute_query(
            query,
            (tenant, config_key, config_value, is_secret, user_email),
            fetch=False,
            commit=True
        )
        
        # Also write to parameters table (migration dual-write)
        from auth.tenant_context import _map_config_key_to_param
        from services.parameter_service import ParameterService
        ps = ParameterService(db)
        namespace, pkey = _map_config_key_to_param(config_key)
        ps.set_param('tenant', tenant, namespace, pkey, config_value,
                     value_type='string', is_secret=is_secret, created_by=user_email)
        
        logger.info(f"Created config {config_key} for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'message': 'Configuration created successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating config: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_config_bp.route('/config/<int:config_id>', methods=['PUT'])
@cognito_required(required_roles=['Tenant_Admin'])
def update_config(user_email, user_roles, config_id) -> ResponseReturnValue:
    """
    Update configuration entry
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "config_value": "new_value",
        "is_secret": false
    }
    
    Returns:
        JSON with success status
    """
    try:
        tenant = get_current_tenant(request)
        data = request.get_json()
        
        config_value = data.get('config_value', '')
        is_secret = data.get('is_secret', False)
        
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Verify config belongs to tenant
        verify_query = """
            SELECT id, config_key FROM tenant_config
            WHERE id = %s AND administration = %s
        """
        
        results = db.execute_query(verify_query, (config_id, tenant))
        
        if not results:
            return jsonify({'error': 'Configuration not found'}), 404
        
        config_key = results[0]['config_key']
        
        # Update config
        query = """
            UPDATE tenant_config
            SET config_value = %s, is_secret = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND administration = %s
        """
        
        db.execute_query(
            query,
            (config_value, is_secret, config_id, tenant),
            fetch=False,
            commit=True
        )
        
        # Also update parameters table (migration dual-write)
        from auth.tenant_context import _map_config_key_to_param
        from services.parameter_service import ParameterService
        ps = ParameterService(db)
        namespace, pkey = _map_config_key_to_param(config_key)
        ps.set_param('tenant', tenant, namespace, pkey, config_value,
                     value_type='string', is_secret=is_secret, created_by=user_email)
        
        logger.info(f"Updated config {config_id} for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_config_bp.route('/config/<int:config_id>', methods=['DELETE'])
@cognito_required(required_roles=['Tenant_Admin'])
def delete_config(user_email, user_roles, config_id) -> ResponseReturnValue:
    """
    Delete configuration entry
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with success status
    """
    try:
        tenant = get_current_tenant(request)
        
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Verify config belongs to tenant
        verify_query = """
            SELECT config_key FROM tenant_config
            WHERE id = %s AND administration = %s
        """
        
        results = db.execute_query(verify_query, (config_id, tenant))
        
        if not results:
            return jsonify({'error': 'Configuration not found'}), 404
        
        config_key = results[0]['config_key']
        
        # Delete config
        query = """
            DELETE FROM tenant_config
            WHERE id = %s AND administration = %s
        """
        
        db.execute_query(
            query,
            (config_id, tenant),
            fetch=False,
            commit=True
        )
        
        # Also delete from parameters table (migration dual-write)
        from auth.tenant_context import _map_config_key_to_param
        from services.parameter_service import ParameterService
        ps = ParameterService(db)
        namespace, pkey = _map_config_key_to_param(config_key)
        ps.delete_param('tenant', tenant, namespace, pkey)
        
        logger.info(f"Deleted config {config_key} (id={config_id}) for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'message': 'Configuration deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting config: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Legacy Config Endpoints (from original tenant_admin_routes.py)
# These use the older /api/tenant/config URL pattern.
# ============================================================================


@tenant_admin_config_bp.route('/api/tenant/config', methods=['GET'], endpoint='legacy_get_config')
@cognito_required(required_permissions=[])
def get_tenant_config_legacy(user_email, user_roles) -> ResponseReturnValue:
    """
    Get tenant configuration (Tenant_Admin only) — legacy endpoint.

    Returns non-secret configs with values and secret configs with keys only.
    Uses the older /api/tenant/config URL pattern.
    """
    from auth.tenant_context import get_user_tenants, is_tenant_admin as check_tenant_admin
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not check_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        query = """
            SELECT config_key, config_value, created_at, updated_at, created_by
            FROM tenant_config
            WHERE administration = %s AND is_secret = FALSE
            ORDER BY config_key
        """
        configs = db.execute_query(query, [tenant], fetch=True)

        secret_query = """
            SELECT config_key, created_at, updated_at, created_by
            FROM tenant_config
            WHERE administration = %s AND is_secret = TRUE
            ORDER BY config_key
        """
        secrets = db.execute_query(secret_query, [tenant], fetch=True)

        return jsonify({
            'success': True,
            'tenant': tenant,
            'configs': configs or [],
            'secrets': secrets or []
        })

    except Exception as e:
        print(f"Error getting tenant config: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@tenant_admin_config_bp.route('/api/tenant/config', methods=['POST'], endpoint='legacy_set_config')
@cognito_required(required_permissions=[])
def set_tenant_config_legacy(user_email, user_roles) -> ResponseReturnValue:
    """
    Set tenant configuration (Tenant_Admin only) — legacy endpoint.

    Uses the older /api/tenant/config URL pattern.
    """
    from auth.tenant_context import get_user_tenants, is_tenant_admin as check_tenant_admin, set_tenant_config
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not check_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        data = request.get_json()
        config_key = data.get('config_key')
        config_value = data.get('config_value')
        is_secret = data.get('is_secret', False)

        if not config_key or config_value is None:
            return jsonify({'error': 'config_key and config_value required'}), 400

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        success = set_tenant_config(db, tenant, config_key, config_value, is_secret, user_email)

        if success:
            print(f"AUDIT: Tenant config updated: {tenant}.{config_key} by {user_email}", flush=True)
            return jsonify({
                'success': True,
                'message': f'Configuration {config_key} updated successfully'
            })
        else:
            return jsonify({'error': 'Failed to update configuration'}), 500

    except Exception as e:
        print(f"Error setting tenant config: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@tenant_admin_config_bp.route('/api/tenant/config/<config_key>', methods=['DELETE'], endpoint='legacy_delete_config')
@cognito_required(required_permissions=[])
def delete_tenant_config_legacy(config_key, user_email, user_roles) -> ResponseReturnValue:
    """
    Delete tenant configuration (Tenant_Admin only) — legacy endpoint.

    Uses the older /api/tenant/config/<config_key> URL pattern.
    """
    from auth.tenant_context import get_user_tenants, is_tenant_admin as check_tenant_admin
    try:
        tenant = get_current_tenant(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        if not check_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403

        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)

        query = """
            DELETE FROM tenant_config
            WHERE administration = %s AND config_key = %s
        """
        db.execute_query(query, [tenant, config_key])

        print(f"AUDIT: Tenant config deleted: {tenant}.{config_key} by {user_email}", flush=True)

        return jsonify({
            'success': True,
            'message': f'Configuration {config_key} deleted successfully'
        })

    except Exception as e:
        print(f"Error deleting tenant config: {e}", flush=True)
        return jsonify({'error': str(e)}), 500
