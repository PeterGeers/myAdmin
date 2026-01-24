"""
Tenant Module Routes

API endpoints for managing tenant-specific module access.
Handles which modules (FIN, STR) are available for each tenant.
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from auth.cognito_utils import cognito_required
from database import DatabaseManager
import logging

logger = logging.getLogger(__name__)

# Create blueprint
tenant_module_bp = Blueprint('tenant_modules', __name__)

# Initialize database manager
db_manager = DatabaseManager()


def get_user_tenants_from_jwt(request):
    """Extract tenants from JWT token in request"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return []
        
        token = auth_header.replace('Bearer ', '')
        
        # Decode JWT (simplified - in production use proper JWT library)
        import base64
        import json
        
        # Split token and get payload
        parts = token.split('.')
        if len(parts) != 3:
            return []
        
        # Decode payload
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.b64decode(payload)
        payload_data = json.loads(decoded)
        
        # Get custom:tenants attribute
        tenants_value = payload_data.get('custom:tenants', [])
        
        # Handle string (JSON encoded)
        if isinstance(tenants_value, str):
            # Unescape if needed
            if '\\"' in tenants_value:
                tenants_value = tenants_value.replace('\\"', '"')
            tenants_value = json.loads(tenants_value)
        
        return tenants_value if isinstance(tenants_value, list) else []
        
    except Exception as e:
        logger.error(f"Failed to extract tenants from JWT: {e}")
        return []


def get_current_tenant(request):
    """Get current tenant from X-Tenant header"""
    return request.headers.get('X-Tenant')


def get_user_module_roles(user_roles):
    """Extract module permissions from user roles"""
    modules = set()
    
    for role in user_roles:
        if role.startswith('Finance_'):
            modules.add('FIN')
        elif role.startswith('STR_'):
            modules.add('STR')
    
    return list(modules)


@tenant_module_bp.route('/api/tenant/modules', methods=['GET'])
@cognito_required(required_permissions=[])
def get_tenant_modules(user_email, user_roles):
    """
    Get available modules for current tenant
    
    Returns modules that:
    1. The tenant has enabled
    2. The user has permissions for
    
    Returns:
        {
            "tenant": "GoodwinSolutions",
            "available_modules": ["FIN", "STR"],
            "user_module_permissions": ["FIN", "STR"]
        }
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant specified'}), 400
        
        # Verify user has access to this tenant
        user_tenants = get_user_tenants_from_jwt(request)
        if tenant not in user_tenants:
            return jsonify({'error': 'Access denied to tenant'}), 403
        
        # Get tenant's enabled modules from database
        with db_manager.get_cursor() as (cursor, conn):
            cursor.execute("""
                SELECT module_name
                FROM tenant_modules
                WHERE administration = %s AND is_active = TRUE
                ORDER BY module_name
            """, (tenant,))
            
            results = cursor.fetchall()
            tenant_modules = [row['module_name'] for row in results]
        
        # Get user's module permissions
        user_module_permissions = get_user_module_roles(user_roles)
        
        # Return intersection (modules user has permission for AND tenant has enabled)
        available_modules = [m for m in user_module_permissions if m in tenant_modules]
        
        return jsonify({
            'tenant': tenant,
            'available_modules': available_modules,
            'user_module_permissions': user_module_permissions,
            'tenant_enabled_modules': tenant_modules
        })
        
    except Exception as e:
        logger.error(f"Error getting tenant modules: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@tenant_module_bp.route('/api/tenant/modules/all', methods=['GET'])
@cognito_required(required_permissions=[])
def get_all_tenant_modules(user_email, user_roles):
    """
    Get module configuration for all user's tenants
    
    Useful for displaying module availability when switching tenants.
    
    Returns:
        {
            "tenants": {
                "PeterPrive": ["FIN"],
                "GoodwinSolutions": ["FIN", "STR"]
            }
        }
    """
    try:
        # Get user's tenants
        user_tenants = get_user_tenants_from_jwt(request)
        if not user_tenants:
            return jsonify({'tenants': {}})
        
        # Get user's module permissions
        user_module_permissions = get_user_module_roles(user_roles)
        
        # Get modules for each tenant
        tenant_modules_map = {}
        
        with db_manager.get_cursor() as (cursor, conn):
            for tenant in user_tenants:
                cursor.execute("""
                    SELECT module_name
                    FROM tenant_modules
                    WHERE administration = %s AND is_active = TRUE
                    ORDER BY module_name
                """, (tenant,))
                
                results = cursor.fetchall()
                tenant_modules = [row['module_name'] for row in results]
                
                # Return intersection
                available = [m for m in user_module_permissions if m in tenant_modules]
                tenant_modules_map[tenant] = available
        
        return jsonify({
            'tenants': tenant_modules_map,
            'user_module_permissions': user_module_permissions
        })
        
    except Exception as e:
        logger.error(f"Error getting all tenant modules: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@tenant_module_bp.route('/api/tenant/modules', methods=['POST'])
@cognito_required(required_permissions=[])
def update_tenant_module(user_email, user_roles):
    """
    Enable or disable a module for a tenant (Tenant_Admin only)
    
    Request body:
        {
            "module_name": "FIN" or "STR",
            "is_active": true or false
        }
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant specified'}), 400
        
        # Check if user is Tenant_Admin
        user_tenants = get_user_tenants_from_jwt(request)
        is_tenant_admin = 'Tenant_Admin' in user_roles and tenant in user_tenants
        
        if not is_tenant_admin:
            return jsonify({'error': 'Tenant_Admin access required'}), 403
        
        # Get request data
        data = request.get_json()
        module_name = data.get('module_name')
        is_active = data.get('is_active', True)
        
        # Validate module name
        if module_name not in ['FIN', 'STR']:
            return jsonify({'error': 'Invalid module name. Must be FIN or STR'}), 400
        
        # Update or insert module
        with db_manager.get_cursor() as (cursor, conn):
            cursor.execute("""
                INSERT INTO tenant_modules (administration, module_name, is_active, created_by)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    is_active = %s,
                    updated_at = CURRENT_TIMESTAMP
            """, (tenant, module_name, is_active, user_email, is_active))
            conn.commit()
        
        logger.info(f"Tenant module updated: {tenant}.{module_name} = {is_active} by {user_email}")
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'module_name': module_name,
            'is_active': is_active
        })
        
    except Exception as e:
        logger.error(f"Error updating tenant module: {e}")
        return jsonify({'error': 'Internal server error'}), 500
