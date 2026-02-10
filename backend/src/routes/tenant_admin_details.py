"""
Tenant Admin Details Routes

This module provides API endpoints for Tenant_Admin role to manage
their own tenant details (profile information).

Endpoints:
- GET /api/tenant-admin/details - Get tenant details
- PUT /api/tenant-admin/details - Update tenant details
"""

from flask import Blueprint, jsonify, request
import os
import logging

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_details_bp = Blueprint('tenant_admin_details', __name__, url_prefix='/api/tenant-admin/details')


@tenant_admin_details_bp.route('', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_tenant_details(user_email, user_roles):
    """
    Get tenant details
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with tenant details
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get tenant details from database
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            SELECT 
                administration,
                display_name,
                contact_email,
                phone_number,
                street,
                city,
                zipcode,
                country,
                bank_account_number,
                bank_name,
                status,
                created_at,
                updated_at
            FROM tenants
            WHERE administration = %s
        """
        
        results = db.execute_query(query, (tenant,))
        
        if not results:
            return jsonify({'error': 'Tenant not found'}), 404
        
        tenant_details = results[0]
        
        logger.info(f"Retrieved tenant details for {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'tenant': tenant_details
        })
        
    except Exception as e:
        logger.error(f"Error getting tenant details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_details_bp.route('', methods=['PUT'])
@cognito_required(required_roles=['Tenant_Admin'])
def update_tenant_details(user_email, user_roles):
    """
    Update tenant details
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "display_name": "Company Name",
        "contact_email": "contact@example.com",
        "phone_number": "+31 6 12345678",
        "street": "Main Street 123",
        "city": "Amsterdam",
        "zipcode": "1012 AB",
        "country": "Netherlands",
        "bank_account_number": "NL12ABCD0123456789",
        "bank_name": "ING Bank"
    }
    
    Returns:
        JSON with success status and updated tenant details
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Build update query dynamically based on provided fields
        allowed_fields = [
            'display_name', 'contact_email', 'phone_number',
            'street', 'city', 'zipcode', 'country',
            'bank_account_number', 'bank_name'
        ]
        
        update_fields = []
        update_values = []
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                update_values.append(data[field])
        
        if not update_fields:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Add updated_by and tenant to values
        update_values.extend([user_email, tenant])
        
        # Update tenant details
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = f"""
            UPDATE tenants
            SET {', '.join(update_fields)}, updated_by = %s, updated_at = CURRENT_TIMESTAMP
            WHERE administration = %s
        """
        
        db.execute_query(query, tuple(update_values), fetch=False, commit=True)
        
        logger.info(f"Updated tenant details for {tenant} by {user_email}: {list(data.keys())}")
        
        # Get updated tenant details
        query = """
            SELECT 
                administration,
                display_name,
                contact_email,
                phone_number,
                street,
                city,
                zipcode,
                country,
                bank_account_number,
                bank_name,
                status,
                created_at,
                updated_at
            FROM tenants
            WHERE administration = %s
        """
        
        results = db.execute_query(query, (tenant,))
        tenant_details = results[0] if results else None
        
        return jsonify({
            'success': True,
            'message': 'Tenant details updated successfully',
            'tenant': tenant_details
        })
        
    except Exception as e:
        logger.error(f"Error updating tenant details: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
