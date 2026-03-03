"""
Year-End Configuration Routes

API endpoints for managing year-end closure configuration including
account purposes and VAT netting parameters.
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.year_end_config import YearEndConfigService
import os

year_end_config_bp = Blueprint('year_end_config', __name__)

# Initialize service
test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
config_service = YearEndConfigService(test_mode=test_mode)


# ============================================================================
# TENANT ADMIN ROUTES - Account Purpose Configuration
# ============================================================================

@year_end_config_bp.route('/api/tenant-admin/year-end-config/validate', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def validate_tenant_config(user_email, user_roles, tenant, user_tenants):
    """
    Validate year-end closure configuration for the tenant.
    
    Returns:
        - valid: Boolean indicating if configuration is complete
        - errors: List of validation errors
        - warnings: List of warnings
        - configured_purposes: Dict of configured account purposes
    """
    try:
        validation = config_service.validate_configuration(tenant)
        
        return jsonify({
            'success': True,
            'valid': validation['valid'],
            'errors': validation['errors'],
            'warnings': validation['warnings'],
            'configured_purposes': validation['configured_purposes']
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@year_end_config_bp.route('/api/tenant-admin/year-end-config/purposes', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_tenant_purposes(user_email, user_roles, tenant, user_tenants):
    """
    Get all configured account purposes for the tenant.
    
    Returns:
        - purposes: Dict of configured purposes with account details
        - required_purposes: Dict of required purpose definitions
    """
    try:
        configured = config_service.get_all_configured_purposes(tenant)
        
        return jsonify({
            'success': True,
            'purposes': configured,
            'required_purposes': config_service.REQUIRED_PURPOSES
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@year_end_config_bp.route('/api/tenant-admin/year-end-config/accounts', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
@tenant_required()
def set_tenant_account_purpose(user_email, user_roles, tenant, user_tenants):
    """
    Set purpose for an account.
    
    Request body:
        - account_code: Account code to configure
        - purpose: Purpose to assign (or null to remove)
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        account_code = data.get('account_code')
        purpose = data.get('purpose')
        
        if not account_code:
            return jsonify({
                'success': False,
                'error': 'account_code is required'
            }), 400
        
        if purpose:
            config_service.set_account_purpose(tenant, account_code, purpose)
            message = f'Purpose "{purpose}" set for account {account_code}'
        else:
            config_service.remove_account_purpose(tenant, account_code)
            message = f'Purpose removed from account {account_code}'
        
        return jsonify({
            'success': True,
            'message': message
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@year_end_config_bp.route('/api/tenant-admin/year-end-config/available-accounts', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_tenant_available_accounts(user_email, user_roles, tenant, user_tenants):
    """
    Get available accounts for purpose assignment.
    
    Query params:
        - vw: Optional filter by VW value ('Y' or 'N')
    
    Returns:
        - accounts: List of available accounts with current purposes
    """
    try:
        vw_filter = request.args.get('vw')
        
        if vw_filter and vw_filter not in ['Y', 'N']:
            return jsonify({
                'success': False,
                'error': 'vw parameter must be "Y" or "N"'
            }), 400
        
        accounts = config_service.get_available_accounts(tenant, vw_filter)
        
        return jsonify({
            'success': True,
            'accounts': accounts
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# VAT NETTING ROUTES
# ============================================================================


@year_end_config_bp.route('/api/year-end-config/vat-netting', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_vat_netting_config(user_email, user_roles, tenant, user_tenants):
    """
    Get VAT netting configuration for the tenant.
    
    Returns:
        - vat_accounts: List of accounts with VAT netting enabled
        - primary_account: Primary account for net balance
    """
    try:
        # Get all accounts with VAT netting flag
        vat_accounts = config_service.get_vat_netting_accounts(tenant)
        
        # Get primary account
        primary_account = config_service.get_vat_primary_account(tenant)
        
        return jsonify({
            'success': True,
            'vat_accounts': vat_accounts,
            'primary_account': primary_account
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@year_end_config_bp.route('/api/year-end-config/vat-netting', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
@tenant_required()
def configure_vat_netting(user_email, user_roles, tenant, user_tenants):
    """
    Configure VAT netting for specified accounts.
    
    Request body:
        - vat_accounts: List of account codes to net together
        - primary_account: Primary account for net balance
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400
        
        vat_accounts = data.get('vat_accounts', [])
        primary_account = data.get('primary_account')
        
        if not vat_accounts:
            return jsonify({
                'success': False,
                'error': 'vat_accounts is required'
            }), 400
        
        if not primary_account:
            return jsonify({
                'success': False,
                'error': 'primary_account is required'
            }), 400
        
        if primary_account not in vat_accounts:
            return jsonify({
                'success': False,
                'error': 'primary_account must be one of the vat_accounts'
            }), 400
        
        # Configure VAT netting
        config_service.configure_vat_netting(
            tenant,
            vat_accounts,
            primary_account
        )
        
        return jsonify({
            'success': True,
            'message': 'VAT netting configured successfully'
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@year_end_config_bp.route('/api/year-end-config/vat-netting', methods=['DELETE'])
@cognito_required(required_permissions=['finance_write'])
@tenant_required()
def remove_vat_netting(user_email, user_roles, tenant, user_tenants):
    """
    Remove VAT netting configuration.
    
    Removes vat_netting and vat_primary parameters from all accounts.
    """
    try:
        config_service.remove_vat_netting(tenant)
        
        return jsonify({
            'success': True,
            'message': 'VAT netting configuration removed'
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@year_end_config_bp.route('/api/year-end-config/balance-sheet-accounts', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_balance_sheet_accounts(user_email, user_roles, tenant, user_tenants):
    """
    Get all balance sheet accounts (VW='N') for the tenant.
    
    Used for VAT netting account selection.
    """
    try:
        accounts = config_service.get_available_accounts(tenant, vw_filter='N')
        
        return jsonify({
            'success': True,
            'accounts': accounts
        }), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
