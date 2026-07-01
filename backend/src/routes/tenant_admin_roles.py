"""
Tenant Admin Role Management Routes

This module provides API endpoints for Tenant_Admin role to manage user roles
(group assignments) within their tenant(s).

Endpoints:
- POST /api/tenant-admin/users/<username>/groups - Assign role to user
- DELETE /api/tenant-admin/users/<username>/groups/<group> - Remove role from user
- GET /api/tenant-admin/roles - List available roles for tenant
- POST /api/tenant/users/<username>/roles - Assign role (legacy)
- DELETE /api/tenant/users/<username>/roles/<role> - Remove role (legacy)
- GET /api/tenant/users - List users (legacy)
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
import os
from botocore.exceptions import ClientError

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant, get_user_tenants
from database import DatabaseManager
from routes.tenant_admin_users import (
    get_user_attribute,
    get_available_roles_for_tenant,
    cognito_client,
    USER_POOL_ID,
)

# Create blueprint
tenant_admin_roles_bp = Blueprint('tenant_admin_roles', __name__, url_prefix='/api/tenant-admin')


# ============================================================================
# Role Assignment Endpoints
# ============================================================================


@tenant_admin_roles_bp.route('/users/<username>/groups', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def assign_user_group(username, user_email, user_roles) -> ResponseReturnValue:
    """
    Assign role (group) to user

    Request body:
    {
        "groupName": "Finance_Read"
    }
    """
    try:
        # Get current tenant from request header
        tenant = get_current_tenant(request)

        # Extract user's tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        # Verify user has access to this tenant
        if tenant not in user_tenants:
            return jsonify({
                'error': 'Access denied',
                'message': f'You do not have access to tenant: {tenant}'
            }), 403

        # Get target user and verify they belong to this tenant
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=username
            )
            target_user_tenants = get_user_attribute(user_response.get('UserAttributes', []), 'custom:tenants')
        except ClientError:
            return jsonify({'error': f'User not found: {username}'}), 404

        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'message': f'User {username} does not have access to tenant {tenant}'
            }), 403

        # Get request data
        data = request.get_json()
        group_name = data.get('groupName')

        if not group_name:
            return jsonify({
                'success': False,
                'error': 'groupName is required'
            }), 400

        # Validate group is allowed for this tenant
        available_roles = get_available_roles_for_tenant(tenant)
        if group_name not in available_roles and group_name != 'SysAdmin':
            return jsonify({
                'success': False,
                'error': f'Cannot assign role {group_name} in this tenant',
                'available_roles': available_roles
            }), 403

        # Assign role — write to DB instead of Cognito group
        target_email = get_user_attribute(user_response.get('UserAttributes', []), 'email') or username
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        try:
            db.execute_query(
                """INSERT INTO user_tenant_roles (email, administration, role, created_by)
                   VALUES (%s, %s, %s, %s)""",
                (target_email, tenant, group_name, user_email),
                fetch=False, commit=True
            )
        except Exception as e:
            if 'Duplicate entry' in str(e):
                return jsonify({
                    'success': False,
                    'error': f'User {username} already has role {group_name} in tenant {tenant}'
                }), 409
            raise

        from auth.role_cache import invalidate_cache
        invalidate_cache(target_email, tenant)

        print(f"AUDIT: Role {group_name} assigned to {username} by {user_email} in tenant {tenant}", flush=True)

        return jsonify({
            'success': True,
            'message': f'Role {group_name} assigned to {username}'
        })

    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tenant_admin_roles_bp.route('/users/<username>/groups/<group_name>', methods=['DELETE'])
@cognito_required(required_roles=['Tenant_Admin'])
def remove_user_group(username, group_name, user_email, user_roles) -> ResponseReturnValue:
    """
    Remove role (group) from user
    """
    try:
        # Get current tenant from request header
        tenant = get_current_tenant(request)

        # Extract user's tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        # Verify user has access to this tenant
        if tenant not in user_tenants:
            return jsonify({
                'error': 'Access denied',
                'message': f'You do not have access to tenant: {tenant}'
            }), 403

        # Get target user and verify they belong to this tenant
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=username
            )
            target_user_tenants = get_user_attribute(user_response.get('UserAttributes', []), 'custom:tenants')
        except ClientError:
            return jsonify({'error': f'User not found: {username}'}), 404

        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'message': f'User {username} does not have access to tenant {tenant}'
            }), 403

        # Validate group is allowed for this tenant
        available_roles = get_available_roles_for_tenant(tenant)
        if group_name not in available_roles and group_name != 'SysAdmin':
            return jsonify({
                'success': False,
                'error': f'Cannot remove role {group_name} in this tenant',
                'available_roles': available_roles
            }), 403

        # Remove role — delete from DB instead of Cognito group
        target_email = get_user_attribute(user_response.get('UserAttributes', []), 'email') or username
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        db.execute_query(
            "DELETE FROM user_tenant_roles WHERE email = %s AND administration = %s AND role = %s",
            (target_email, tenant, group_name),
            fetch=False, commit=True
        )

        from auth.role_cache import invalidate_cache
        invalidate_cache(target_email, tenant)

        print(f"AUDIT: Role {group_name} removed from {username} by {user_email} in tenant {tenant}", flush=True)

        return jsonify({
            'success': True,
            'message': f'Role {group_name} removed from {username}'
        })

    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tenant_admin_roles_bp.route('/roles', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_available_roles(user_email, user_roles) -> ResponseReturnValue:
    """
    Get list of roles available for current tenant

    Returns roles based on tenant's enabled modules
    """
    try:
        # Get current tenant from request header
        tenant = get_current_tenant(request)

        # Extract user's tenants from JWT
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            jwt_token = auth_header.replace('Bearer ', '').strip()
            user_tenants = get_user_tenants(jwt_token)
        else:
            return jsonify({'error': 'Invalid authorization'}), 401

        # Verify user has access to this tenant
        if tenant not in user_tenants:
            return jsonify({
                'error': 'Access denied',
                'message': f'You do not have access to tenant: {tenant}'
            }), 403

        # Get available roles for tenant
        available_roles = get_available_roles_for_tenant(tenant)

        # Return roles with basic details (no Cognito group lookup needed)
        roles_with_details = [{'name': role_name, 'description': '', 'precedence': None} for role_name in available_roles]

        return jsonify({
            'success': True,
            'tenant': tenant,
            'roles': roles_with_details,
            'count': len(roles_with_details)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# Legacy User/Role Endpoints (from original tenant_admin_routes.py)
# These use the older /api/tenant/users URL pattern.
# ============================================================================


@tenant_admin_roles_bp.route('/api/tenant/users', methods=['GET'], endpoint='legacy_get_tenant_users')
@cognito_required(required_permissions=[])
def get_tenant_users_legacy(user_email, user_roles) -> ResponseReturnValue:
    """
    Get users in tenant (Tenant_Admin only) — legacy endpoint.

    Returns list of users with their roles who have access to this tenant.
    Uses the older /api/tenant/users URL pattern.
    """
    from auth.tenant_context import is_tenant_admin as check_tenant_admin
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

        users_response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Limit=60
        )

        tenant_users = []

        for user in users_response.get('Users', []):
            user_tenant_list = get_user_attribute(user.get('Attributes', []), 'custom:tenants')

            if user_tenant_list and tenant in user_tenant_list:
                username = user.get('Username')
                # Get user's groups from Cognito
                try:
                    groups_response = cognito_client.admin_list_groups_for_user(
                        UserPoolId=USER_POOL_ID,
                        Username=username
                    )
                    user_groups = [group['GroupName'] for group in groups_response.get('Groups', [])]
                except Exception:
                    user_groups = []

                tenant_users.append({
                    'username': username,
                    'email': get_user_attribute(user.get('Attributes', []), 'email'),
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


@tenant_admin_roles_bp.route('/api/tenant/users/<username>/roles', methods=['POST'], endpoint='legacy_assign_role')
@cognito_required(required_permissions=[])
def assign_tenant_role_legacy(username, user_email, user_roles) -> ResponseReturnValue:
    """
    Assign role to user within tenant (Tenant_Admin only) — legacy endpoint.

    Uses the older /api/tenant/users/<username>/roles URL pattern.
    """
    from auth.tenant_context import is_tenant_admin as check_tenant_admin
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
        role = data.get('role')

        if not role:
            return jsonify({'error': 'role required'}), 400

        allowed_roles = [
            'Finance_CRUD', 'Finance_Read', 'Finance_Export',
            'STR_CRUD', 'STR_Read', 'STR_Export'
        ]

        if role not in allowed_roles:
            return jsonify({
                'error': 'Cannot assign this role',
                'details': f'Allowed roles: {", ".join(allowed_roles)}'
            }), 403

        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=username
            )
            target_user_tenants = get_user_attribute(user_response.get('UserAttributes', []), 'custom:tenants')
        except Exception:
            return jsonify({'error': f'User not found: {username}'}), 404

        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'details': f'User {username} does not have access to tenant {tenant}'
            }), 403

        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=role
        )

        print(f"AUDIT: Tenant admin {user_email} assigned {role} to {username} in {tenant}", flush=True)

        return jsonify({
            'success': True,
            'message': f'Role {role} assigned to {username} successfully'
        })

    except Exception as e:
        print(f"Error assigning tenant role: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@tenant_admin_roles_bp.route('/api/tenant/users/<username>/roles/<role>', methods=['DELETE'], endpoint='legacy_remove_role')
@cognito_required(required_permissions=[])
def remove_tenant_role_legacy(username, role, user_email, user_roles) -> ResponseReturnValue:
    """
    Remove role from user within tenant (Tenant_Admin only) — legacy endpoint.

    Uses the older /api/tenant/users/<username>/roles/<role> URL pattern.
    """
    from auth.tenant_context import is_tenant_admin as check_tenant_admin
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

        allowed_roles = [
            'Finance_CRUD', 'Finance_Read', 'Finance_Export',
            'STR_CRUD', 'STR_Read', 'STR_Export'
        ]

        if role not in allowed_roles:
            return jsonify({
                'error': 'Cannot remove this role',
                'details': f'Allowed roles: {", ".join(allowed_roles)}'
            }), 403

        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=username
            )
            target_user_tenants = get_user_attribute(user_response.get('UserAttributes', []), 'custom:tenants')
        except Exception:
            return jsonify({'error': f'User not found: {username}'}), 404

        if not target_user_tenants or tenant not in target_user_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'details': f'User {username} does not have access to tenant {tenant}'
            }), 403

        cognito_client.admin_remove_user_from_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=role
        )

        print(f"AUDIT: Tenant admin {user_email} removed {role} from {username} in {tenant}", flush=True)

        return jsonify({
            'success': True,
            'message': f'Role {role} removed from {username} successfully'
        })

    except Exception as e:
        print(f"Error removing tenant role: {e}", flush=True)
        return jsonify({'error': str(e)}), 500
