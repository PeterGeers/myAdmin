"""
SysAdmin Role Management Endpoints

API endpoints for managing Cognito groups (roles)
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
import os
import boto3
import logging

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Cognito client
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')

# Create blueprint
sysadmin_roles_bp = Blueprint('sysadmin_roles', __name__)


@sysadmin_roles_bp.route('', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def list_roles(user_email, user_roles):
    """
    List all Cognito groups (roles)
    
    Authorization: SysAdmin role required
    
    Returns groups categorized by type:
    - platform: SysAdmin, Tenant_Admin
    - module: Finance_Read, Finance_CRUD, Finance_Export, STR_Read, STR_CRUD, STR_Export
    """
    try:
        # List all groups
        response = cognito_client.list_groups(
            UserPoolId=USER_POOL_ID,
            Limit=60
        )
        
        groups = []
        for group in response.get('Groups', []):
            group_name = group['GroupName']
            
            # Get user count for this group
            users_response = cognito_client.list_users_in_group(
                UserPoolId=USER_POOL_ID,
                GroupName=group_name,
                Limit=60
            )
            user_count = len(users_response.get('Users', []))
            
            # Categorize group
            if group_name in ['SysAdmin', 'Tenant_Admin']:
                category = 'platform'
            elif any(module in group_name for module in ['Finance', 'STR']):
                category = 'module'
            else:
                category = 'other'
            
            groups.append({
                'name': group_name,
                'description': group.get('Description', ''),
                'user_count': user_count,
                'category': category,
                'created_date': group.get('CreationDate').isoformat() if group.get('CreationDate') else None
            })
        
        # Handle pagination if needed
        while 'NextToken' in response:
            response = cognito_client.list_groups(
                UserPoolId=USER_POOL_ID,
                Limit=60,
                NextToken=response['NextToken']
            )
            for group in response.get('Groups', []):
                group_name = group['GroupName']
                users_response = cognito_client.list_users_in_group(
                    UserPoolId=USER_POOL_ID,
                    GroupName=group_name,
                    Limit=60
                )
                user_count = len(users_response.get('Users', []))
                
                if group_name in ['SysAdmin', 'Tenant_Admin']:
                    category = 'platform'
                elif any(module in group_name for module in ['Finance', 'STR']):
                    category = 'module'
                else:
                    category = 'other'
                
                groups.append({
                    'name': group_name,
                    'description': group.get('Description', ''),
                    'user_count': user_count,
                    'category': category,
                    'created_date': group.get('CreationDate').isoformat() if group.get('CreationDate') else None
                })
        
        return jsonify({
            'success': True,
            'roles': groups,
            'total': len(groups)
        })
        
    except Exception as e:
        logger.error(f"Error listing roles: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_roles_bp.route('', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def create_role(user_email, user_roles):
    """
    Create new Cognito group (role)
    
    Authorization: SysAdmin role required
    
    Request body:
    {
        "name": "NewRole",
        "description": "Description of the role"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Missing required field: name'}), 400
        
        group_name = data['name']
        description = data.get('description', '')
        
        # Check if group already exists
        try:
            cognito_client.get_group(
                UserPoolId=USER_POOL_ID,
                GroupName=group_name
            )
            return jsonify({'error': f'Role {group_name} already exists'}), 400
        except cognito_client.exceptions.ResourceNotFoundException:
            pass  # Group doesn't exist, we can create it
        
        # Create group
        cognito_client.create_group(
            UserPoolId=USER_POOL_ID,
            GroupName=group_name,
            Description=description
        )
        
        logger.info(f"Role {group_name} created by {user_email}")
        
        return jsonify({
            'success': True,
            'name': group_name,
            'description': description,
            'message': f'Role {group_name} created successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating role: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sysadmin_roles_bp.route('/<role_name>', methods=['DELETE'])
@cognito_required(required_roles=['SysAdmin'])
def delete_role(user_email, user_roles, role_name):
    """
    Delete Cognito group (role)
    
    Authorization: SysAdmin role required
    
    Note: Group must have zero users before deletion
    """
    try:
        # Check if group exists
        try:
            cognito_client.get_group(
                UserPoolId=USER_POOL_ID,
                GroupName=role_name
            )
        except cognito_client.exceptions.ResourceNotFoundException:
            return jsonify({'error': f'Role {role_name} not found'}), 404
        
        # Check for users in group
        users_response = cognito_client.list_users_in_group(
            UserPoolId=USER_POOL_ID,
            GroupName=role_name,
            Limit=1
        )
        
        if users_response.get('Users'):
            return jsonify({
                'error': f'Cannot delete role with active users. Please remove all users from {role_name} first.'
            }), 409
        
        # Delete group
        cognito_client.delete_group(
            UserPoolId=USER_POOL_ID,
            GroupName=role_name
        )
        
        logger.info(f"Role {role_name} deleted by {user_email}")
        
        return jsonify({
            'success': True,
            'name': role_name,
            'message': f'Role {role_name} deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting role: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
