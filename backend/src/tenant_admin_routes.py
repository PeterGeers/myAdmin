"""
Tenant Administration Routes for myAdmin

This module provides API endpoints for Tenant_Admin role to manage:
- Tenant configuration (integrations, settings)
- Tenant secrets (API keys, credentials)
- Tenant users and role assignments
- Tenant audit logs
- Template preview and validation (for template customization)

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
import logging
from typing import Dict, Any, List, Optional

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint for tenant admin routes
# Note: Routes define their own full paths (e.g., /api/tenant/config, /api/tenant-admin/templates/preview)
tenant_admin_bp = Blueprint('tenant_admin', __name__)

# Initialize Cognito client
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')


# ============================================================================
# Security: Content Security Policy Headers
# ============================================================================


@tenant_admin_bp.after_request
def add_security_headers(response):
    """
    Add Content Security Policy headers to all tenant admin responses.
    
    This provides defense-in-depth security for template preview and validation:
    - Prevents execution of inline scripts
    - Restricts resource loading to same origin
    - Blocks external resources
    - Prevents clickjacking
    
    Applied to all routes in this blueprint.
    """
    # Content Security Policy
    # - default-src 'self': Only load resources from same origin
    # - script-src 'none': No JavaScript execution allowed
    # - style-src 'self' 'unsafe-inline': Allow inline styles (needed for template previews)
    # - img-src 'self' data:: Allow images from same origin and data URIs
    # - font-src 'self': Only fonts from same origin
    # - connect-src 'self': Only API calls to same origin
    # - frame-ancestors 'none': Prevent clickjacking
    # - base-uri 'self': Restrict base tag URLs
    # - form-action 'self': Only submit forms to same origin
    csp_policy = (
        "default-src 'self'; "
        "script-src 'none'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers['Content-Security-Policy'] = csp_policy
    
    # Additional security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    return response


# ============================================================================
# Helper Functions
# ============================================================================


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


# ============================================================================
# Template Preview and Validation Routes
# ============================================================================


@tenant_admin_bp.route('/api/tenant-admin/templates/<template_type>', methods=['GET'])
@cognito_required(required_permissions=[])
def get_current_template_endpoint(template_type, user_email, user_roles):
    """
    Get current active template (Tenant_Admin only)
    
    Returns the currently active template content and metadata for the specified type.
    
    Path parameters:
        template_type: Type of template (str_invoice_nl, btw_aangifte, etc.)
    
    Returns:
    {
        "success": true,
        "template_type": "str_invoice_nl",
        "template_content": "<html>...</html>",
        "field_mappings": {},
        "metadata": {
            "file_id": "1abc...xyz",
            "version": 2,
            "approved_by": "admin@example.com",
            "approved_at": "2026-02-01T12:00:00",
            "is_active": true
        }
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate template type
        valid_types = [
            'str_invoice_nl', 'str_invoice_en', 
            'btw_aangifte', 'aangifte_ib', 
            'toeristenbelasting', 'financial_report',
            'user_invitation'  # Email template for user invitations
        ]
        if template_type not in valid_types:
            return jsonify({
                'error': 'Invalid template type',
                'valid_types': valid_types
            }), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Get template metadata from database
        query = """
            SELECT template_file_id, field_mappings, version, approved_by, 
                   approved_at, is_active, status
            FROM tenant_template_config
            WHERE administration = %s AND template_type = %s AND is_active = TRUE
            ORDER BY version DESC
            LIMIT 1
        """
        result = db.execute_query(query, [tenant, template_type], fetch=True)
        
        if not result or len(result) == 0:
            return jsonify({
                'success': False,
                'error': 'No active template found',
                'message': f'No active template found for type: {template_type}',
                'template_type': template_type
            }), 404
        
        template_metadata = result[0]
        file_id = template_metadata.get('template_file_id')
        
        # Fetch template content from Google Drive
        try:
            from google_drive_service import GoogleDriveService
            drive_service = GoogleDriveService(administration=tenant)
            template_content = drive_service.download_file_content(file_id)
        except Exception as e:
            logger.error(f"Error fetching template from Google Drive: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to fetch template from Google Drive',
                'details': str(e)
            }), 500
        
        # Parse field mappings (stored as JSON)
        field_mappings = template_metadata.get('field_mappings')
        if isinstance(field_mappings, str):
            try:
                field_mappings = json.loads(field_mappings)
            except:
                field_mappings = {}
        
        # Audit log
        logger.info(
            f"AUDIT: Template retrieved by {user_email} for {tenant}, "
            f"type={template_type}, file_id={file_id}"
        )
        
        # Return template data
        return jsonify({
            'success': True,
            'template_type': template_type,
            'template_content': template_content,
            'field_mappings': field_mappings or {},
            'metadata': {
                'file_id': file_id,
                'version': template_metadata.get('version', 1),
                'approved_by': template_metadata.get('approved_by'),
                'approved_at': str(template_metadata.get('approved_at')) if template_metadata.get('approved_at') else None,
                'is_active': template_metadata.get('is_active', True),
                'status': template_metadata.get('status', 'active')
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting current template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_bp.route('/api/tenant-admin/templates/preview', methods=['POST'])
@cognito_required(required_permissions=[])
def preview_template_endpoint(user_email, user_roles):
    """
    Generate template preview with sample data (Tenant_Admin only)
    
    Request body:
    {
        "template_type": "str_invoice_nl",
        "template_content": "<html>...</html>",
        "field_mappings": {}  // optional
    }
    
    Returns:
    {
        "success": true,
        "preview_html": "<html>...</html>",
        "validation": {
            "is_valid": true,
            "errors": [],
            "warnings": []
        },
        "sample_data_info": {
            "source": "database",
            "record_date": "2026-01-01",
            "message": "Using most recent data"
        }
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        template_type = data.get('template_type')
        template_content = data.get('template_content')
        field_mappings = data.get('field_mappings', {})
        
        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400
        
        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Initialize TemplatePreviewService
        from services.template_preview_service import TemplatePreviewService
        preview_service = TemplatePreviewService(db, tenant)
        
        # Generate preview
        result = preview_service.generate_preview(
            template_type=template_type,
            template_content=template_content,
            field_mappings=field_mappings
        )
        
        # Audit log
        logger.info(
            f"AUDIT: Template preview generated by {user_email} for {tenant}, "
            f"type={template_type}, success={result.get('success')}"
        )
        
        # Return appropriate status code based on success
        if result.get('success'):
            return jsonify(result), 200
        else:
            # Validation failed or preview generation failed
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Error generating template preview: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_bp.route('/api/tenant-admin/templates/validate', methods=['POST'])
@cognito_required(required_permissions=[])
def validate_template_endpoint(user_email, user_roles):
    """
    Validate template without generating preview (Tenant_Admin only)
    
    This endpoint is faster than preview as it only validates the template
    without fetching sample data or generating the full preview HTML.
    
    Request body:
    {
        "template_type": "str_invoice_nl",
        "template_content": "<html>...</html>"
    }
    
    Returns:
    {
        "is_valid": true,
        "errors": [],
        "warnings": [],
        "checks_performed": ["html_syntax", "required_placeholders", "security_scan", "file_size"]
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        template_type = data.get('template_type')
        template_content = data.get('template_content')
        
        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400
        
        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Initialize TemplatePreviewService
        from services.template_preview_service import TemplatePreviewService
        preview_service = TemplatePreviewService(db, tenant)
        
        # Validate template (no preview generation)
        result = preview_service.validate_template(
            template_type=template_type,
            template_content=template_content
        )
        
        # Audit log
        logger.info(
            f"AUDIT: Template validation by {user_email} for {tenant}, "
            f"type={template_type}, valid={result.get('is_valid')}"
        )
        
        # Return validation results
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error validating template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_bp.route('/api/tenant-admin/templates/approve', methods=['POST'])
@cognito_required(required_permissions=[])
def approve_template_endpoint(user_email, user_roles):
    """
    Approve and activate template (Tenant_Admin only)
    
    This endpoint:
    1. Validates the template
    2. Saves template to Google Drive
    3. Updates database metadata
    4. Archives previous version
    5. Logs approval
    
    Request body:
    {
        "template_type": "str_invoice_nl",
        "template_content": "<html>...</html>",
        "field_mappings": {},  // optional
        "notes": "Updated invoice layout"  // optional
    }
    
    Returns:
    {
        "success": true,
        "template_id": "tmpl_str_invoice_nl_2",
        "file_id": "1abc...xyz",
        "message": "Template approved and activated",
        "previous_version": {
            "file_id": "1def...uvw",
            "archived_at": "2026-02-01T12:00:00"
        }
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        template_type = data.get('template_type')
        template_content = data.get('template_content')
        field_mappings = data.get('field_mappings', {})
        notes = data.get('notes', '')
        
        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400
        
        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Initialize TemplatePreviewService
        from services.template_preview_service import TemplatePreviewService
        preview_service = TemplatePreviewService(db, tenant)
        
        # Approve template (validates, saves to Drive, updates DB, archives previous)
        result = preview_service.approve_template(
            template_type=template_type,
            template_content=template_content,
            field_mappings=field_mappings,
            user_email=user_email,
            notes=notes
        )
        
        # Audit log
        if result.get('success'):
            logger.info(
                f"AUDIT: Template approved by {user_email} for {tenant}, "
                f"type={template_type}, file_id={result.get('file_id')}"
            )
        else:
            logger.warning(
                f"AUDIT: Template approval failed by {user_email} for {tenant}, "
                f"type={template_type}, reason={result.get('message')}"
            )
        
        # Return appropriate status code based on success
        if result.get('success'):
            return jsonify(result), 200
        else:
            # Approval failed (validation or save error)
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Error approving template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_bp.route('/api/tenant-admin/templates/reject', methods=['POST'])
@cognito_required(required_permissions=[])
def reject_template_endpoint(user_email, user_roles):
    """
    Reject template with reason (Tenant_Admin only)
    
    This endpoint logs template rejection for audit purposes.
    No changes are made to the database or Google Drive.
    
    Request body:
    {
        "template_type": "str_invoice_nl",
        "reason": "Template does not meet brand guidelines"
    }
    
    Returns:
    {
        "success": true,
        "message": "Template rejection logged"
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        template_type = data.get('template_type')
        reason = data.get('reason', 'No reason provided')
        
        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400
        
        # Log rejection with reason
        logger.info(
            f"AUDIT: Template rejected by {user_email} for {tenant}, "
            f"type={template_type}, reason={reason}"
        )
        
        # Return success message
        return jsonify({
            'success': True,
            'message': 'Template rejection logged'
        }), 200
        
    except Exception as e:
        logger.error(f"Error rejecting template: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


@tenant_admin_bp.route('/api/tenant-admin/templates/ai-help', methods=['POST'])
@cognito_required(required_permissions=[])
def ai_help_template_endpoint(user_email, user_roles):
    """
    Get AI-powered fix suggestions for template errors (Tenant_Admin only)
    
    This endpoint uses OpenRouter AI to analyze template validation errors
    and provide intelligent fix suggestions with code examples.
    
    Request body:
    {
        "template_type": "str_invoice_nl",
        "template_content": "<html>...</html>",
        "validation_errors": [
            {
                "type": "missing_placeholder",
                "message": "Required placeholder missing",
                "placeholder": "invoice_number"
            }
        ],
        "required_placeholders": ["invoice_number", "guest_name", ...]
    }
    
    Returns:
    {
        "success": true,
        "ai_suggestions": {
            "analysis": "The template is missing required placeholders...",
            "fixes": [
                {
                    "issue": "Missing placeholder: invoice_number",
                    "suggestion": "Add {{ invoice_number }} to display the invoice number",
                    "code_example": "<h1>Invoice {{ invoice_number }}</h1>",
                    "location": "header section",
                    "confidence": "high"
                }
            ],
            "auto_fixable": true
        },
        "tokens_used": 1234,
        "cost_estimate": 0.001
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        template_type = data.get('template_type')
        template_content = data.get('template_content')
        validation_errors = data.get('validation_errors', [])
        required_placeholders = data.get('required_placeholders', [])
        
        if not template_type:
            return jsonify({'error': 'template_type is required'}), 400
        
        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400
        
        if not validation_errors:
            return jsonify({'error': 'validation_errors is required'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Initialize AITemplateAssistant
        from services.ai_template_assistant import AITemplateAssistant
        ai_assistant = AITemplateAssistant(db)
        
        # Get AI fix suggestions
        result = ai_assistant.get_fix_suggestions(
            template_type=template_type,
            template_content=template_content,
            validation_errors=validation_errors,
            required_placeholders=required_placeholders,
            administration=tenant
        )
        
        # Log AI usage for cost tracking
        if result.get('success') and result.get('tokens_used'):
            logger.info(
                f"AUDIT: AI assistance used by {user_email} for {tenant}, "
                f"type={template_type}, tokens={result.get('tokens_used')}, "
                f"cost=${result.get('cost_estimate', 0):.4f}"
            )
        else:
            logger.warning(
                f"AUDIT: AI assistance failed for {user_email} in {tenant}, "
                f"type={template_type}, error={result.get('error', 'unknown')}"
            )
        
        # Return AI suggestions or fallback to generic help
        if result.get('success'):
            return jsonify(result), 200
        else:
            # AI service unavailable - return generic help
            generic_help = _get_generic_help(validation_errors, required_placeholders)
            return jsonify({
                'success': True,
                'ai_suggestions': generic_help,
                'fallback': True,
                'message': 'AI service unavailable, showing generic help'
            }), 200
        
    except Exception as e:
        logger.error(f"Error getting AI help: {e}")
        
        # Try to provide generic help even on error
        try:
            generic_help = _get_generic_help(
                data.get('validation_errors', []),
                data.get('required_placeholders', [])
            )
            return jsonify({
                'success': True,
                'ai_suggestions': generic_help,
                'fallback': True,
                'message': 'Error occurred, showing generic help'
            }), 200
        except:
            return jsonify({
                'error': 'Internal server error',
                'details': str(e)
            }), 500


def _get_generic_help(validation_errors: List[Dict], required_placeholders: List[str]) -> Dict[str, Any]:
    """
    Generate generic help when AI service is unavailable.
    
    Args:
        validation_errors: List of validation error dictionaries
        required_placeholders: List of required placeholder names
        
    Returns:
        Dictionary with generic fix suggestions
    """
    fixes = []
    
    # Generate fixes for each error type
    for error in validation_errors:
        error_type = error.get('type', 'unknown')
        
        if error_type == 'missing_placeholder':
            placeholder = error.get('placeholder', 'unknown')
            fixes.append({
                'issue': f"Missing placeholder: {placeholder}",
                'suggestion': f"Add {{{{ {placeholder} }}}} to your template where you want to display this value",
                'code_example': f"<p>{{{{ {placeholder} }}}}</p>",
                'location': 'anywhere in template body',
                'confidence': 'high'
            })
        
        elif error_type == 'security_error':
            fixes.append({
                'issue': error.get('message', 'Security issue detected'),
                'suggestion': 'Remove script tags and event handlers from your template. Use CSS for styling instead.',
                'code_example': '<!-- Remove: <script>...</script> and onclick="..." -->',
                'location': 'throughout template',
                'confidence': 'high'
            })
        
        elif error_type == 'syntax_error':
            fixes.append({
                'issue': error.get('message', 'HTML syntax error'),
                'suggestion': 'Check for unclosed or mismatched HTML tags. Ensure all opening tags have corresponding closing tags.',
                'code_example': '<!-- Correct: <div>content</div> -->',
                'location': error.get('line', 'unknown line'),
                'confidence': 'medium'
            })
        
        else:
            fixes.append({
                'issue': error.get('message', 'Validation error'),
                'suggestion': 'Review the error message and fix the issue in your template',
                'code_example': '',
                'location': 'see error details',
                'confidence': 'low'
            })
    
    return {
        'analysis': f"Found {len(validation_errors)} validation error(s). Here are generic suggestions to fix them.",
        'fixes': fixes,
        'auto_fixable': False,
        'note': 'These are generic suggestions. For more intelligent help, ensure AI service is configured.'
    }


@tenant_admin_bp.route('/api/tenant-admin/templates/apply-ai-fixes', methods=['POST'])
@cognito_required(required_permissions=[])
def apply_ai_fixes_endpoint(user_email, user_roles):
    """
    Apply AI-suggested fixes to template (Tenant_Admin only)
    
    This endpoint applies auto-fixes suggested by the AI to the template content.
    
    Request body:
    {
        "template_content": "<html>...</html>",
        "fixes": [
            {
                "issue": "Missing placeholder: invoice_number",
                "code_to_add": "{{ invoice_number }}",
                "location": "header"
            }
        ]
    }
    
    Returns:
    {
        "success": true,
        "fixed_template": "<html>...fixed content...</html>",
        "fixes_applied": 3,
        "message": "Successfully applied 3 fixes"
    }
    """
    try:
        # Get tenant from request
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
        
        # Validate request body
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400
        
        template_content = data.get('template_content')
        fixes = data.get('fixes', [])
        
        if not template_content:
            return jsonify({'error': 'template_content is required'}), 400
        
        if not fixes:
            return jsonify({'error': 'fixes is required'}), 400
        
        # Get database connection
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Initialize AITemplateAssistant
        from services.ai_template_assistant import AITemplateAssistant
        ai_assistant = AITemplateAssistant(db)
        
        # Apply auto-fixes
        result = ai_assistant.apply_auto_fixes(
            template_content=template_content,
            fixes=fixes
        )
        
        # The apply_auto_fixes method returns the fixed template string
        # We need to wrap it in a response structure
        fixes_applied = len([f for f in fixes if f.get('auto_fixable', False)])
        
        response = {
            'success': True,
            'fixed_template': result,
            'fixes_applied': fixes_applied,
            'message': f'Successfully applied {fixes_applied} fixes'
        }
        
        # Log fix application
        logger.info(
            f"AUDIT: AI fixes applied by {user_email} for {tenant}, "
            f"fixes_applied={fixes_applied}"
        )
        
        # Return fixed template content
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error applying AI fixes: {e}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500
