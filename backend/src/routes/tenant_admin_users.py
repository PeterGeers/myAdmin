"""
Tenant Admin User Management Routes

This module provides API endpoints for Tenant_Admin role to manage users within their tenant(s).
Tenant admins can only manage users who have access to their assigned tenants.

Endpoints:
- GET /api/tenant-admin/users - List users in current tenant
- POST /api/tenant-admin/users - Create user and assign to tenant
- PUT /api/tenant-admin/users/<username> - Update user (name, status)
- DELETE /api/tenant-admin/users/<username> - Delete user
- POST /api/tenant-admin/users/<username>/groups - Assign role to user
- DELETE /api/tenant-admin/users/<username>/groups/<group> - Remove role from user
- GET /api/tenant-admin/roles - List available roles for tenant
"""

from flask import Blueprint, jsonify, request
import os
import json
import boto3
from botocore.exceptions import ClientError

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant, get_user_tenants
from database import DatabaseManager
from services.cognito_service import CognitoService
from services.invitation_service import InvitationService
from services.email_template_service import EmailTemplateService

# Create blueprint
tenant_admin_users_bp = Blueprint('tenant_admin_users', __name__, url_prefix='/api/tenant-admin')

# Initialize Cognito client
AWS_REGION = os.getenv('AWS_REGION', 'eu-west-1')
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
cognito_client = boto3.client('cognito-idp', region_name=AWS_REGION)
cognito_service = CognitoService()


# ============================================================================
# Helper Functions
# ============================================================================


def get_user_attribute(user_attributes, attribute_name):
    """Extract attribute value from Cognito user attributes"""
    for attr in user_attributes:
        if attr['Name'] == attribute_name:
            value = attr['Value']
            # Handle JSON arrays (custom:tenants)
            if attribute_name == 'custom:tenants':
                try:
                    return json.loads(value) if value else []
                except:
                    return [value] if value else []
            return value
    return None


def is_tenant_admin(user_roles):
    """Check if user has Tenant_Admin role"""
    return 'Tenant_Admin' in user_roles


def get_tenant_enabled_modules(tenant):
    """Get enabled modules for tenant from database"""
    try:
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            SELECT module_name 
            FROM tenant_modules 
            WHERE administration = %s AND is_active = TRUE
        """
        result = db.execute_query(query, [tenant], fetch=True)
        return [row['module_name'] for row in (result or [])]
    except Exception as e:
        print(f"Error getting tenant modules: {e}", flush=True)
        return []


def get_available_roles_for_tenant(tenant):
    """Get list of roles available for tenant based on enabled modules.

    Reads required_roles from MODULE_REGISTRY so new modules are picked up
    automatically without changing this function.
    """
    from services.module_registry import MODULE_REGISTRY

    enabled_modules = get_tenant_enabled_modules(tenant)

    roles = ['Tenant_Admin']  # Always available

    # Add module-specific roles dynamically from MODULE_REGISTRY
    for module_name in enabled_modules:
        module_def = MODULE_REGISTRY.get(module_name)
        if module_def:
            roles.extend(module_def.get('required_roles', []))

    # Deduplicate while preserving order
    seen = set()
    available_roles = []
    for r in roles:
        if r not in seen:
            seen.add(r)
            available_roles.append(r)

    return available_roles


# ============================================================================
# User Management Endpoints
# ============================================================================


@tenant_admin_users_bp.route('/users', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def list_tenant_users(user_email, user_roles):
    """
    List all users who have access to the current tenant
    
    Returns users with their roles, status, and tenant assignments
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
        
        # Get all users from Cognito
        response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Limit=60
        )
        
        tenant_users = []
        
        for user in response.get('Users', []):
            # Get user's tenants
            user_tenant_list = get_user_attribute(user.get('Attributes', []), 'custom:tenants')
            
            # Only include users who have access to this tenant
            if user_tenant_list and tenant in user_tenant_list:
                username = user.get('Username')
                
                # Get user's roles from DB (per-tenant)
                user_email_addr = get_user_attribute(user.get('Attributes', []), 'email')
                try:
                    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
                    db = DatabaseManager(test_mode=test_mode)
                    role_rows = db.execute_query(
                        "SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s",
                        (user_email_addr, tenant),
                        fetch=True
                    )
                    user_groups = [r['role'] for r in (role_rows or [])]
                except Exception:
                    user_groups = []
                
                tenant_users.append({
                    'username': username,
                    'email': get_user_attribute(user.get('Attributes', []), 'email'),
                    'name': get_user_attribute(user.get('Attributes', []), 'name'),
                    'status': user.get('UserStatus'),
                    'enabled': user.get('Enabled'),
                    'groups': user_groups,
                    'tenants': [tenant],
                    'created': user.get('UserCreateDate').isoformat() if user.get('UserCreateDate') else None,
                    'modified': user.get('UserLastModifiedDate').isoformat() if user.get('UserLastModifiedDate') else None
                })
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'users': tenant_users,
            'count': len(tenant_users)
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tenant_admin_users_bp.route('/users', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def create_tenant_user(user_email, user_roles):
    """
    Create a new user and assign to current tenant
    
    If user already exists, adds the current tenant to their tenant list.
    
    Request body:
    {
        "email": "user@example.com",
        "name": "User Name",
        "password": "TempPassword123!",  # Only required for new users
        "groups": ["Finance_Read"]
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
        
        # Get request data
        data = request.get_json()
        email = data.get('email')
        name = data.get('name')
        password = data.get('password')
        groups = data.get('groups', [])
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Normalize email to lowercase for Cognito case-sensitivity
        email = email.strip().lower()
        
        # Validate groups are allowed for this tenant
        available_roles = get_available_roles_for_tenant(tenant)
        invalid_groups = [g for g in groups if g not in available_roles and g != 'SysAdmin']
        
        if invalid_groups:
            return jsonify({
                'success': False,
                'error': f'Invalid groups for this tenant: {", ".join(invalid_groups)}',
                'available_roles': available_roles
            }), 400
        
        # Check if user already exists
        user_exists = False
        existing_user_tenants = []
        username = email
        
        try:
            user_response = cognito_client.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=email
            )
            user_exists = True
            existing_user_tenants = get_user_attribute(user_response.get('UserAttributes', []), 'custom:tenants')
            
            # Check if user already has this tenant
            if existing_user_tenants and tenant in existing_user_tenants:
                return jsonify({
                    'success': False,
                    'error': f'User {email} already has access to tenant {tenant}',
                    'message': 'This user already exists in this tenant. Use the Edit button to modify their roles.'
                }), 409
            
        except ClientError as e:
            if e.response['Error']['Code'] != 'UserNotFoundException':
                raise
        
        if user_exists:
            # User exists but doesn't have this tenant - add tenant to their list
            updated_tenants = existing_user_tenants + [tenant] if existing_user_tenants else [tenant]
            
            cognito_client.admin_update_user_attributes(
                UserPoolId=USER_POOL_ID,
                Username=username,
                UserAttributes=[
                    {'Name': 'custom:tenants', 'Value': json.dumps(updated_tenants)}
                ]
            )
            
            # Add user roles to DB
            test_mode_flag = os.getenv('TEST_MODE', 'false').lower() == 'true'
            db = DatabaseManager(test_mode=test_mode_flag)
            for group_name in groups:
                try:
                    db.execute_query(
                        """INSERT INTO user_tenant_roles (email, administration, role, created_by)
                           VALUES (%s, %s, %s, %s)""",
                        (email, tenant, group_name, user_email),
                        fetch=False, commit=True
                    )
                except Exception as e:
                    print(f"Warning: Failed to add role {group_name} for user in tenant: {e}", flush=True)

            from auth.role_cache import invalidate_cache
            invalidate_cache(email, tenant)
            
            print(f"AUDIT: Existing user {email} added to tenant {tenant} by {user_email}", flush=True)
            
            # Send notification email (no password — user already has credentials)
            try:
                from services.ses_email_service import SESEmailService
                from utils.frontend_url import get_frontend_url
                
                email_service = EmailTemplateService(administration=tenant)
                ses = SESEmailService()
                login_url = get_frontend_url()
                
                # Get user's display name
                user_name = email.split('@')[0]
                for attr in user_response.get('UserAttributes', []):
                    if attr['Name'] == 'name':
                        user_name = attr['Value']
                        break
                
                html_content = email_service.render_template(
                    template_name='tenant_added',
                    variables={
                        'email': email,
                        'tenant': tenant,
                        'name': user_name,
                        'login_url': login_url,
                    },
                    format='html'
                )
                
                text_content = (
                    f"Hi {user_name},\n\n"
                    f"You have been added to the {tenant} tenant in myAdmin.\n\n"
                    f"You can log in with your existing credentials at: {login_url}\n\n"
                    f"Regards,\nmyAdmin"
                )
                
                subject = f"You've been added to {tenant} in myAdmin"
                
                result = ses.send_invitation(
                    to_email=email,
                    subject=subject,
                    html_body=html_content or text_content,
                    text_body=text_content,
                    administration=tenant,
                    sent_by=user_email,
                )
                
                if result['success']:
                    print(f"AUDIT: Tenant-added notification sent to {email} for tenant {tenant}", flush=True)
                else:
                    print(f"WARNING: Failed to send tenant-added notification to {email}: {result.get('error')}", flush=True)
                    
            except Exception as e:
                # Don't fail the operation if email fails
                print(f"WARNING: Failed to send tenant-added notification to {email}: {e}", flush=True)
            
            return jsonify({
                'success': True,
                'message': f'User {email} added to tenant {tenant}',
                'username': username,
                'tenant': tenant,
                'existing_user': True
            })
        
        else:
            # User doesn't exist - create new user
            
            # Initialize invitation service
            test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
            invitation_service = InvitationService(test_mode=test_mode)
            email_service = EmailTemplateService(administration=tenant)
            
            # Create invitation record and generate temporary password
            invitation_result = invitation_service.create_invitation(
                administration=tenant,
                email=email,
                created_by=user_email,
                template_type='user_invitation'
            )
            
            if not invitation_result.get('success'):
                return jsonify({
                    'success': False,
                    'error': 'Failed to create invitation',
                    'details': invitation_result.get('error')
                }), 500
            
            # Use generated temporary password
            temp_password = invitation_result['temporary_password']
            
            # Build user attributes
            user_attributes = [
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'custom:tenants', 'Value': json.dumps([tenant])}
            ]
            
            if name:
                user_attributes.append({'Name': 'name', 'Value': name})
            
            # Create user
            try:
                response = cognito_client.admin_create_user(
                    UserPoolId=USER_POOL_ID,
                    Username=email,
                    UserAttributes=user_attributes,
                    TemporaryPassword=temp_password,
                    MessageAction='SUPPRESS'
                )
                
                username = response['User']['Username']
                
                # Update invitation with username
                invitation_service.create_invitation(
                    administration=tenant,
                    email=email,
                    username=username,
                    created_by=user_email,
                    template_type='user_invitation'
                )
                
            except ClientError as e:
                # Mark invitation as failed
                invitation_service.mark_invitation_failed(
                    administration=tenant,
                    email=email,
                    error_message=str(e)
                )
                raise
            
            # Add user roles to DB
            test_mode_new = os.getenv('TEST_MODE', 'false').lower() == 'true'
            db_new = DatabaseManager(test_mode=test_mode_new)
            for group_name in groups:
                try:
                    db_new.execute_query(
                        """INSERT INTO user_tenant_roles (email, administration, role, created_by)
                           VALUES (%s, %s, %s, %s)""",
                        (email, tenant, group_name, user_email),
                        fetch=False, commit=True
                    )
                except Exception as e:
                    print(f"Warning: Failed to add role {group_name} for new user: {e}", flush=True)

            from auth.role_cache import invalidate_cache as invalidate_new
            invalidate_new(email, tenant)
            
            # Send invitation email
            try:
                # Render email templates using render_user_invitation which detects language
                from utils.frontend_url import get_frontend_url
                login_url = get_frontend_url()
                
                html_content = email_service.render_user_invitation(
                    email=email,
                    temporary_password=temp_password,
                    tenant=tenant,
                    login_url=login_url,
                    format='html'
                )
                
                text_content = email_service.render_user_invitation(
                    email=email,
                    temporary_password=temp_password,
                    tenant=tenant,
                    login_url=login_url,
                    format='txt'
                )
                
                # Send via SES (direct to recipient)
                from services.ses_email_service import SESEmailService
                ses = SESEmailService()
                # Get subject with detected language
                subject = email_service.get_invitation_subject(
                    tenant,
                    language=email_service._detect_user_language(email, tenant)
                )
                
                result = ses.send_invitation(
                    to_email=email,
                    subject=subject,
                    html_body=html_content,
                    text_body=text_content or f"Welcome to {tenant}! Your temporary password: {temp_password}",
                    administration=tenant,
                    sent_by=user_email,
                )
                
                if result['success']:
                    # Mark invitation as sent
                    invitation_service.mark_invitation_sent(
                        administration=tenant,
                        email=email
                    )
                    print(f"AUDIT: Invitation email sent to {email} by {user_email} for tenant {tenant}", flush=True)
                else:
                    print(f"WARNING: SES failed to send invitation to {email}: {result.get('error')}", flush=True)
                    invitation_service.mark_invitation_failed(
                        administration=tenant,
                        email=email,
                        error_message=f"SES send failed: {result.get('error')}"
                    )
                    
            except Exception as e:
                # Don't fail user creation if email fails, but log it
                print(f"WARNING: Failed to send invitation email to {email}: {e}", flush=True)
                invitation_service.mark_invitation_failed(
                    administration=tenant,
                    email=email,
                    error_message=f"Email send failed: {str(e)}"
                )
            
            print(f"AUDIT: User {email} created by {user_email} for tenant {tenant}", flush=True)
            
            return jsonify({
                'success': True,
                'message': f'User {email} created successfully. Invitation email sent.',
                'username': username,
                'tenant': tenant,
                'existing_user': False,
                'invitation_sent': True
            })
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'InvalidPasswordException':
            return jsonify({
                'success': False,
                'error': 'Password does not meet requirements (minimum 8 characters)'
            }), 400
        else:
            return jsonify({
                'success': False,
                'error': error_message
            }), 500


@tenant_admin_users_bp.route('/users/<username>', methods=['PUT'])
@cognito_required(required_roles=['Tenant_Admin'])
def update_tenant_user(username, user_email, user_roles):
    """
    Update user attributes (name, status)
    
    Request body:
    {
        "name": "Updated Name",
        "enabled": true
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
        name = data.get('name')
        enabled = data.get('enabled')
        
        # Update name if provided
        if name is not None:
            user_attributes = [{'Name': 'name', 'Value': name}]
            cognito_client.admin_update_user_attributes(
                UserPoolId=USER_POOL_ID,
                Username=username,
                UserAttributes=user_attributes
            )
        
        # Update enabled status if provided
        if enabled is not None:
            if enabled:
                cognito_client.admin_enable_user(
                    UserPoolId=USER_POOL_ID,
                    Username=username
                )
            else:
                cognito_client.admin_disable_user(
                    UserPoolId=USER_POOL_ID,
                    Username=username
                )
        
        print(f"AUDIT: User {username} updated by {user_email} in tenant {tenant}", flush=True)
        
        return jsonify({
            'success': True,
            'message': f'User {username} updated successfully'
        })
        
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tenant_admin_users_bp.route('/users/<username>', methods=['DELETE'])
@cognito_required(required_roles=['Tenant_Admin'])
def delete_tenant_user(username, user_email, user_roles):
    """
    Delete user from current tenant. Uses CognitoService.remove_tenant_from_user()
    as the single code path for tenant removal / user deletion.
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
        
        # Verify target user belongs to this tenant before proceeding
        try:
            target_tenants = cognito_service.get_user_tenants(username)
        except Exception:
            return jsonify({'error': f'User not found: {username}'}), 404
        
        if not target_tenants or tenant not in target_tenants:
            return jsonify({
                'error': 'User not in this tenant',
                'message': f'User {username} does not have access to tenant {tenant}'
            }), 403
        
        # Delegate to CognitoService — single code path with safety guard
        success, user_deleted = cognito_service.remove_tenant_from_user(username, tenant)

        # Clean up per-tenant roles from DB
        target_email = username  # username is the email in Cognito
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        db.execute_query(
            "DELETE FROM user_tenant_roles WHERE email = %s AND administration = %s",
            (target_email, tenant),
            fetch=False, commit=True
        )
        from auth.role_cache import invalidate_cache
        invalidate_cache(target_email, tenant)
        
        if user_deleted:
            message = f'User {username} deleted (was only in this tenant)'
        else:
            message = f'User {username} removed from tenant {tenant}'
        
        print(f"AUDIT: {message} by {user_email}", flush=True)
        
        return jsonify({
            'success': True,
            'message': message,
            'user_deleted': user_deleted
        })
        
    except ValueError as e:
        # Safety guard triggered (malformed tenants) or user not found
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except ClientError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@tenant_admin_users_bp.route('/users/<username>/groups', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def assign_user_group(username, user_email, user_roles):
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


@tenant_admin_users_bp.route('/users/<username>/groups/<group_name>', methods=['DELETE'])
@cognito_required(required_roles=['Tenant_Admin'])
def remove_user_group(username, group_name, user_email, user_roles):
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


@tenant_admin_users_bp.route('/roles', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_available_roles(user_email, user_roles):
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
