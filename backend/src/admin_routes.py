"""
System Administration Routes
Handles user and role management for SysAdmin users
"""

from flask import Blueprint, jsonify, request
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth.cognito_utils import cognito_required
import boto3
from botocore.exceptions import ClientError

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# Initialize Cognito client
AWS_REGION = os.getenv('AWS_REGION', 'eu-west-1')
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')

print(f"🔧 Admin Routes - AWS Region: {AWS_REGION}", flush=True)
print(f"🔧 Admin Routes - User Pool ID: {USER_POOL_ID}", flush=True)

if not USER_POOL_ID:
    print("⚠️ WARNING: COGNITO_USER_POOL_ID not set in environment variables!", flush=True)

cognito_client = boto3.client('cognito-idp', region_name=AWS_REGION)


@admin_bp.route('/test', methods=['GET'])
@cognito_required(required_permissions=[])
def test_auth(user_email, user_roles):
    """Test endpoint to verify authentication is working"""
    return jsonify({
        'success': True,
        'message': 'Authentication working',
        'user_email': user_email,
        'user_roles': user_roles,
        'has_sysadmin': 'SysAdmin' in user_roles
    })


@admin_bp.route('/users', methods=['GET', 'OPTIONS'])
@cognito_required(required_roles=['SysAdmin'])
def list_users(user_email, user_roles):
    """List all users in the Cognito User Pool"""
    print(f"📋 List users called by: {user_email} with roles: {user_roles}", flush=True)
    
    # Handle OPTIONS request for CORS
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        if not USER_POOL_ID:
            return jsonify({
                'success': False,
                'error': 'COGNITO_USER_POOL_ID not configured'
            }), 500
        
        response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Limit=60
        )
        
        users = []
        for user in response.get('Users', []):
            user_data = {
                'username': user.get('Username'),
                'email': next((attr['Value'] for attr in user.get('Attributes', []) if attr['Name'] == 'email'), None),
                'status': user.get('UserStatus'),
                'enabled': user.get('Enabled'),
                'created': user.get('UserCreateDate').isoformat() if user.get('UserCreateDate') else None,
                'modified': user.get('UserLastModifiedDate').isoformat() if user.get('UserLastModifiedDate') else None,
            }
            
            # Get user's groups
            try:
                groups_response = cognito_client.admin_list_groups_for_user(
                    Username=user.get('Username'),
                    UserPoolId=USER_POOL_ID
                )
                user_data['groups'] = [g['GroupName'] for g in groups_response.get('Groups', [])]
            except:
                user_data['groups'] = []
            
            users.append(user_data)
        
        return jsonify({
            'success': True,
            'users': users,
            'count': len(users)
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/users', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def create_user(user_email, user_roles):
    """Create a new user in the Cognito User Pool"""
    print(f"➕ Create user called by: {user_email} with roles: {user_roles}", flush=True)
    
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        groups = data.get('groups', [])
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        # Create user
        response = cognito_client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ],
            TemporaryPassword=password,
            MessageAction='SUPPRESS'  # Don't send welcome email
        )
        
        username = response['User']['Username']
        
        # Add user to groups
        for group_name in groups:
            try:
                cognito_client.admin_add_user_to_group(
                    UserPoolId=USER_POOL_ID,
                    Username=username,
                    GroupName=group_name
                )
            except ClientError as e:
                print(f"⚠️ Failed to add user to group {group_name}: {e}", flush=True)
        
        return jsonify({
            'success': True,
            'message': f'User {email} created successfully',
            'username': username
        })
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'UsernameExistsException':
            return jsonify({
                'success': False,
                'error': 'A user with this email already exists'
            }), 400
        elif error_code == 'InvalidPasswordException':
            return jsonify({
                'success': False,
                'error': 'Password does not meet requirements (minimum 8 characters)'
            }), 400
        else:
            return jsonify({
                'success': False,
                'error': error_message
            }), 500


@admin_bp.route('/groups', methods=['GET', 'OPTIONS'])
@cognito_required(required_roles=['SysAdmin'])
def list_groups(user_email, user_roles):
    """List all groups (roles) in the Cognito User Pool"""
    # Handle OPTIONS request for CORS
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        response = cognito_client.list_groups(
            UserPoolId=USER_POOL_ID,
            Limit=60
        )
        
        groups = []
        for group in response.get('Groups', []):
            groups.append({
                'name': group.get('GroupName'),
                'description': group.get('Description'),
                'precedence': group.get('Precedence'),
                'created': group.get('CreationDate').isoformat() if group.get('CreationDate') else None,
                'modified': group.get('LastModifiedDate').isoformat() if group.get('LastModifiedDate') else None,
            })
        
        return jsonify({
            'success': True,
            'groups': groups,
            'count': len(groups)
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/users/<username>/groups', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def add_user_to_group(username, user_email, user_roles):
    """Add a user to a group (assign role)"""
    try:
        data = request.get_json()
        group_name = data.get('groupName')
        
        if not group_name:
            return jsonify({
                'success': False,
                'error': 'groupName is required'
            }), 400
        
        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )
        
        return jsonify({
            'success': True,
            'message': f'User {username} added to group {group_name}'
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/users/<username>/groups/<group_name>', methods=['DELETE'])
@cognito_required(required_roles=['SysAdmin'])
def remove_user_from_group(username, group_name, user_email, user_roles):
    """Remove a user from a group (revoke role)"""
    try:
        cognito_client.admin_remove_user_from_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )
        
        return jsonify({
            'success': True,
            'message': f'User {username} removed from group {group_name}'
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/users/<username>/enable', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def enable_user(username, user_email, user_roles):
    """Enable a user account"""
    try:
        cognito_client.admin_enable_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        return jsonify({
            'success': True,
            'message': f'User {username} enabled'
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/users/<username>/disable', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def disable_user(username, user_email, user_roles):
    """Disable a user account"""
    try:
        cognito_client.admin_disable_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        return jsonify({
            'success': True,
            'message': f'User {username} disabled'
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/users/<username>', methods=['DELETE'])
@cognito_required(required_roles=['SysAdmin'])
def delete_user(username, user_email, user_roles):
    """Delete a user account"""
    try:
        cognito_client.admin_delete_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        return jsonify({
            'success': True,
            'message': f'User {username} deleted'
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
