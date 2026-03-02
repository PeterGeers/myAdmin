"""
Year-End Configuration API Routes

Provides endpoints for managing year-end closure account configuration.
Uses "purpose" to identify which accounts serve special functions in year-end closure.
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.year_end_config import YearEndConfigService

year_end_config_bp = Blueprint('year_end_config', __name__)


@year_end_config_bp.route('/api/tenant-admin/year-end-config/validate', methods=['GET'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def validate_configuration(user_email, user_roles, tenant, user_tenants):
    """
    Validate year-end closure configuration for the tenant.
    
    Returns:
        {
            "valid": bool,
            "errors": [str],
            "warnings": [str],
            "configured_purposes": {
                "role_name": {
                    "account_code": str,
                    "account_name": str,
                    "vw": str
                }
            }
        }
    """
    try:
        service = YearEndConfigService()
        validation = service.validate_configuration(tenant)
        return jsonify(validation), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to validate configuration'
        }), 500


@year_end_config_bp.route('/api/tenant-admin/year-end-config/purposes', methods=['GET'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def get_configured_purposes(user_email, user_roles, tenant, user_tenants):
    """
    Get all configured account purposes for the tenant.
    
    Returns:
        {
            "purposes": {
                "purpose_name": {
                    "account_code": str,
                    "account_name": str,
                    "vw": str
                }
            },
            "required_purposes": {
                "purpose_name": {
                    "description": str,
                    "expected_vw": str,
                    "example": str
                }
            }
        }
    """
    try:
        service = YearEndConfigService()
        configured = service.get_all_configured_purposes(tenant)
        
        return jsonify({
            'purposes': configured,
            'required_purposes': service.REQUIRED_PURPOSES
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to get configured purposes'
        }), 500


@year_end_config_bp.route('/api/tenant-admin/year-end-config/accounts', methods=['POST'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def set_account_purpose(user_email, user_roles, tenant, user_tenants):
    """
    Set purpose for an account.
    
    Request body:
        {
            "account_code": str,
            "purpose": str  # or null to remove purpose
        }
    
    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        data = request.get_json()
        account_code = data.get('account_code')
        purpose = data.get('purpose')
        
        if not account_code:
            return jsonify({
                'error': 'account_code is required'
            }), 400
        
        service = YearEndConfigService()
        
        if purpose:
            # Set purpose
            service.set_account_purpose(tenant, account_code, purpose)
            message = f"Purpose '{purpose}' assigned to account {account_code}"
        else:
            # Remove purpose
            service.remove_account_purpose(tenant, account_code)
            message = f"Purpose removed from account {account_code}"
        
        return jsonify({
            'success': True,
            'message': message
        }), 200
        
    except ValueError as e:
        return jsonify({
            'error': str(e),
            'message': 'Invalid request'
        }), 400
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to set account purpose'
        }), 500


@year_end_config_bp.route('/api/tenant-admin/year-end-config/available-accounts', methods=['GET'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def get_available_accounts(user_email, user_roles, tenant, user_tenants):
    """
    Get available accounts for role assignment.
    
    Query params:
        vw: Optional VW filter ('Y' or 'N')
    
    Returns:
        {
            "accounts": [
                {
                    "Reknum": str,
                    "AccountName": str,
                    "VW": str,
                    "current_purpose": str | null
                }
            ]
        }
    """
    try:
        vw_filter = request.args.get('vw')
        
        service = YearEndConfigService()
        accounts = service.get_available_accounts(tenant, vw_filter)
        
        return jsonify({
            'accounts': accounts
        }), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to get available accounts'
        }), 500
