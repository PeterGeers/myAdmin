"""
Tenant Admin Settings Routes

This module provides API endpoints for Tenant_Admin role to manage
tenant settings and view activity.

Endpoints:
- GET /api/tenant-admin/settings - Get tenant settings
- PUT /api/tenant-admin/settings - Update tenant settings
- GET /api/tenant-admin/activity - Get tenant activity statistics
"""

from flask import Blueprint, jsonify, request
import os
import logging

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager
from services.tenant_settings_service import TenantSettingsService

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_settings_bp = Blueprint('tenant_admin_settings', __name__, url_prefix='/api/tenant-admin')


@tenant_admin_settings_bp.route('/settings', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_settings(user_email, user_roles):
    """
    Get tenant settings
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with tenant settings
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Initialize service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        settings_service = TenantSettingsService(db)
        
        # Get settings
        settings = settings_service.get_settings(tenant)
        
        logger.info(f"Retrieved settings for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'settings': settings
        })
        
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_settings_bp.route('/settings', methods=['PUT'])
@cognito_required(required_roles=['Tenant_Admin'])
def update_settings(user_email, user_roles):
    """
    Update tenant settings
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "notifications": {
            "email_enabled": true,
            "sms_enabled": false
        },
        "preferences": {
            "language": "en",
            "timezone": "Europe/Amsterdam"
        }
    }
    
    Returns:
        JSON with success status
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No settings data provided'}), 400
        
        # Initialize service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        settings_service = TenantSettingsService(db)
        
        # Update settings
        settings_service.update_settings(tenant, data)
        
        # Get updated settings
        updated_settings = settings_service.get_settings(tenant)
        
        logger.info(f"Updated settings for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'message': 'Settings updated successfully',
            'tenant': tenant,
            'settings': updated_settings
        })
        
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_settings_bp.route('/activity', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_activity(user_email, user_roles):
    """
    Get tenant activity statistics
    
    Authorization: Tenant_Admin role required
    
    Query parameters:
    - start_date: ISO format date (optional)
    - end_date: ISO format date (optional)
    
    Returns:
        JSON with activity statistics
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get date range from query params
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        date_range = None
        if start_date or end_date:
            date_range = {}
            if start_date:
                date_range['start_date'] = start_date
            if end_date:
                date_range['end_date'] = end_date
        
        # Initialize service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        settings_service = TenantSettingsService(db)
        
        # Get activity
        activity = settings_service.get_activity(tenant, date_range)
        
        logger.info(f"Retrieved activity for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'activity': activity
        })
        
    except Exception as e:
        logger.error(f"Error getting activity: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Tenant Language Endpoints (i18n)
# ============================================================================

from services.tenant_language_service import (
    get_tenant_language,
    update_tenant_language,
    validate_language_code
)


@tenant_admin_settings_bp.route('/language', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_tenant_language_preference(user_email, user_roles):
    """
    Get tenant's default language
    
    Returns:
        JSON response with language code
        
    Example response:
        {
            "default_language": "nl"
        }
    """
    try:
        # Get current tenant from header
        tenant = get_current_tenant()
        
        if not tenant:
            return jsonify({
                'error': 'Missing X-Tenant header'
            }), 400
        
        # Get tenant's default language
        language = get_tenant_language(tenant)
        
        return jsonify({
            'default_language': language
        }), 200
        
    except Exception as e:
        logger.error(f"Error in get_tenant_language_preference: {e}")
        return jsonify({
            'error': 'Failed to retrieve tenant language preference',
            'details': str(e)
        }), 500


@tenant_admin_settings_bp.route('/language', methods=['PUT'])
@cognito_required(required_roles=['Tenant_Admin'])
def update_tenant_language_preference(user_email, user_roles):
    """
    Update tenant's default language (Tenant Admin only)
    
    Request body:
        {
            "default_language": "nl" | "en"
        }
        
    Returns:
        JSON response with success message
        
    Example response:
        {
            "message": "Tenant default language updated successfully",
            "default_language": "en"
        }
    """
    try:
        # Get current tenant from header
        tenant = get_current_tenant()
        
        if not tenant:
            return jsonify({
                'error': 'Missing X-Tenant header'
            }), 400
        
        # Get request data
        data = request.get_json()
        
        if not data or 'default_language' not in data:
            return jsonify({
                'error': 'Missing required field: default_language'
            }), 400
        
        language = data['default_language']
        
        # Validate language code
        if not validate_language_code(language):
            return jsonify({
                'error': 'Invalid language code',
                'details': 'Language must be "nl" or "en"'
            }), 400
        
        # Update tenant's default language
        success = update_tenant_language(tenant, language)
        
        if not success:
            return jsonify({
                'error': 'Failed to update tenant language preference'
            }), 500
        
        return jsonify({
            'message': 'Tenant default language updated successfully',
            'default_language': language
        }), 200
        
    except Exception as e:
        logger.error(f"Error in update_tenant_language_preference: {e}")
        return jsonify({
            'error': 'Failed to update tenant language preference',
            'details': str(e)
        }), 500
