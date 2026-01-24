"""
Tenant Administration Routes for myAdmin

This module provides API endpoints for Tenant_Admin role to manage:
- Tenant configuration (integrations, settings)
- Tenant secrets (API keys, credentials)
- Tenant users and role assignments
- Tenant audit logs

Based on the architecture at .kiro/specs/Common/Multitennant/architecture.md
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import (
    get_current_tenant,
    get_user_tenants,
    is_tenant_admin,
    get_tenant_config,
    set_tenant_config
)
from database import DatabaseManager
import os
import json
import boto3
from typing import Dict, Any, List

tenant_admin_bp = Blueprint('tenant_admin', __name__)

# Initialize Cognito client
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')


def get_user_attribute(user: Dict[str, Any], attribute_name: str) -> Any:
    """Extract attribute value from Cognito user object"""
    for attr in user.get('Attributes', []):
        if attr['Name'] == attribute_name:
            value = attr['Value']
            # Handle JSON arrays
            if attribute_name == 'custom:tenants':
                try:
                    return json.loads(value)
                except:
                    return [value] if value else []
            return value
    return None


def get_user_groups(username: str) -> List[str]:
    """Get Cognito groups for a user"""
    try:
        response = cognito_client.admin_list_groups_for_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        return [group['GroupName'] for group in response.get('Groups', [])]
    except Exception as e:
        print(f"Error getting user groups: {e}", flush=True)
        return []


@tenant_admin_bp.route('/api/tenant/config', methods=['GET'], endpoint='get_tenant_config')
@cognito_required(required_permissions=[])
def get_tenant_config_endpoint(user_email, user_roles):
    """
    Get tenant configuration (Tenant_Admin only)
    
    Returns non-secret configs with values and secret configs with keys only
    """
    try:
        tenant = get_current_tenant(request)
        
        # Extract user tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401
        
        # Check if user is tenant admin
        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Get non-secret configs
        query = """
            SELECT config_key, config_value, created_at, updated_at, created_by
            FROM tenant_config 
            WHERE administration = %s AND is_secret = FALSE
            ORDER BY config_key
        """
        configs = db.execute_query(query, [tenant], fetch=True)
        
        # Get secret keys (but not values)
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


@tenant_admin_bp.route('/api/tenant/config', methods=['POST'], endpoint='set_tenant_config')
@cognito_required(required_permissions=[])
def set_tenant_config_endpoint(user_email, user_roles):
    """
    Set tenant configuration (Tenant_Admin only)
    
    Request body:
    {
        "config_key": "google_drive_folder_id",
        "config_value": "abc123",
        "is_secret": true
    }
    """
    try:
        tenant = get_current_tenant(request)
        
        # Extract user tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401
        
        # Check if user is tenant admin
        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403
        
        # Get request data
        data = request.get_json()
        config_key = data.get('config_key')
        config_value = data.get('config_value')
        is_secret = data.get('is_secret', False)
        
        if not config_key or config_value is None:
            return jsonify({'error': 'config_key and config_value required'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Set config
        success = set_tenant_config(db, tenant, config_key, config_value, is_secret, user_email)
        
        if success:
            # Audit log
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


@tenant_admin_bp.route('/api/tenant/config/<config_key>', methods=['DELETE'], endpoint='delete_tenant_config')
@cognito_required(required_permissions=[])
def delete_tenant_config_endpoint(config_key, user_email, user_roles):
    """
    Delete tenant configuration (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)
        
        # Extract user tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401
        
        # Check if user is tenant admin
        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Delete config
        query = """
            DELETE FROM tenant_config 
            WHERE administration = %s AND config_key = %s
        """
        db.execute_query(query, [tenant, config_key])
        
        # Audit log
        print(f"AUDIT: Tenant config deleted: {tenant}.{config_key} by {user_email}", flush=True)
        
        return jsonify({
            'success': True,
            'message': f'Configuration {config_key} deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting tenant config: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@tenant_admin_bp.route('/api/tenant/users', methods=['GET'])
@cognito_required(required_permissions=[])
def get_tenant_users_endpoint(user_email, user_roles):
    """
    Get users in tenant (Tenant_Admin only)
    
    Returns list of users with their roles who have access to this tenant
    """
    try:
        tenant = get_current_tenant(request)
        
        # Extract user tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401
        
        # Check if user is tenant admin
        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403
        
        # Get all users from Cognito
        users_response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Limit=60  # Maximum allowed by Cognito
        )
        
        tenant_users = []
        
        for user in users_response.get('Users', []):
            # Get user's tenants
            user_tenant_list = get_user_attribute(user, 'custom:tenants')
            
            # Check if user has access to this tenant
            if user_tenant_list and tenant in user_tenant_list:
                username = user.get('Username')
                user_groups = get_user_groups(username)
                
                tenant_users.append({
                    'username': username,
                    'email': get_user_attribute(user, 'email'),
                    'roles': user_groups,
                    'tenants': user_tenant_list,
                    'enabled': user.get('Enabled', True),
                    'status': user.get('UserStatus', 'UNKNOWN')
                })
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'users': tenant_users,
            'count': len(tenant_users)
        })
        
    except Exception as e:
        print(f"Error getting tenant users: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@tenant_admin_bp.route('/api/tenant/users/<username>/roles', methods=['POST'])
@cognito_required(required_permissions=[])
def assign_tenant_role_endpoint(username, user_email, user_roles):
    """
    Assign role to user within tenant (Tenant_Admin only)
    
    Request body:
    {
        "role": "Finance_CRUD"
    }
    
    Allowed roles: Finance_CRUD, Finance_Read, Finance_Export, STR_CRUD, STR_Read, STR_Export
    """
    try:
        tenant = get_current_tenant(request)
        
        # Extract user tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401
        
        # Check if user is tenant admin
        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403
        
        # Get request data
        data = request.get_json()
        role = data.get('role')
        
        if not role:
            return jsonify({'error': 'role required'}), 400
        
        # Only allow assigning module roles (not SysAdmin or Tenant_Admin)
        allowed_roles = [
            'Finance_CRUD', 'Finance_Read', 'Finance_Export',
            'STR_CRUD', 'STR_Read', 'STR_Export'
        ]
        
        if role not in allowed_roles:
            return jsonify({
                'error': 'Cannot assign this role',
                'details': f'Allowed roles: {", ".join(allowed_roles)}'
            }), 403
        
        # Get target user's tenants
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=username
            )
            target_user_tenants = get_user_attribute(user_response, 'custom:tenants')
        except Exception as e:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        # Verify user belongs to this tenant
        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'details': f'User {username} does not have access to tenant {tenant}'
            }), 403
        
        # Assign role
        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=role
        )
        
        # Audit log
        print(f"AUDIT: Tenant admin {user_email} assigned {role} to {username} in {tenant}", flush=True)
        
        return jsonify({
            'success': True,
            'message': f'Role {role} assigned to {username} successfully'
        })
        
    except Exception as e:
        print(f"Error assigning tenant role: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@tenant_admin_bp.route('/api/tenant/users/<username>/roles/<role>', methods=['DELETE'])
@cognito_required(required_permissions=[])
def remove_tenant_role_endpoint(username, role, user_email, user_roles):
    """
    Remove role from user within tenant (Tenant_Admin only)
    """
    try:
        tenant = get_current_tenant(request)
        
        # Extract user tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401
        
        # Check if user is tenant admin
        if not is_tenant_admin(user_roles, tenant, user_tenants):
            return jsonify({'error': 'Tenant admin access required'}), 403
        
        # Only allow removing module roles (not SysAdmin or Tenant_Admin)
        allowed_roles = [
            'Finance_CRUD', 'Finance_Read', 'Finance_Export',
            'STR_CRUD', 'STR_Read', 'STR_Export'
        ]
        
        if role not in allowed_roles:
            return jsonify({
                'error': 'Cannot remove this role',
                'details': f'Allowed roles: {", ".join(allowed_roles)}'
            }), 403
        
        # Get target user's tenants
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=username
            )
            target_user_tenants = get_user_attribute(user_response, 'custom:tenants')
        except Exception as e:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        # Verify user belongs to this tenant
        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'details': f'User {username} does not have access to tenant {tenant}'
            }), 403
        
        # Remove role
        cognito_client.admin_remove_user_from_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=role
        )
        
        # Audit log
        print(f"AUDIT: Tenant admin {user_email} removed {role} from {username} in {tenant}", flush=True)
        
        return jsonify({
            'success': True,
            'message': f'Role {role} removed from {username} successfully'
        })
        
    except Exception as e:
        print(f"Error removing tenant role: {e}", flush=True)
        return jsonify({'error': str(e)}), 500
