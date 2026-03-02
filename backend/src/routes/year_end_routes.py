"""
Year-End Closure API Routes

Provides endpoints for closing fiscal years and managing year-end closure process.

Endpoints:
- GET /api/year-end/available-years - Get years available to close
- POST /api/year-end/validate - Validate if year can be closed
- POST /api/year-end/close - Close a fiscal year
- GET /api/year-end/closed-years - Get list of closed years
- GET /api/year-end/status/<year> - Get closure status for specific year

Permissions:
- finance_read: View year-end data and validate
- year_end_close: Close fiscal years (restricted permission)
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.year_end_service import YearEndClosureService

year_end_bp = Blueprint('year_end', __name__)


@year_end_bp.route('/api/year-end/available-years', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_available_years(user_email, user_roles, tenant, user_tenants):
    """
    Get list of years that can be closed.
    
    Returns years with transactions that haven't been closed yet.
    
    Returns:
        [
            {
                "year": int
            }
        ]
    """
    try:
        service = YearEndClosureService()
        years = service.get_available_years(tenant)
        
        # Format as list of year objects
        return jsonify([{'year': year} for year in years]), 200
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to get available years'
        }), 500


@year_end_bp.route('/api/year-end/validate', methods=['POST'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def validate_year(user_email, user_roles, tenant, user_tenants):
    """
    Validate if a year is ready to be closed.
    
    Request body:
        {
            "year": int
        }
    
    Returns:
        {
            "can_close": bool,
            "errors": [str],
            "warnings": [str],
            "info": {
                "net_result": float,
                "net_result_formatted": str,
                "balance_sheet_accounts": int
            }
        }
    """
    try:
        data = request.get_json()
        year = data.get('year')
        
        if not year:
            return jsonify({
                'error': 'year is required'
            }), 400
        
        service = YearEndClosureService()
        validation = service.validate_year_closure(tenant, year)
        
        return jsonify(validation), 200
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to validate year'
        }), 500


@year_end_bp.route('/api/year-end/close', methods=['POST'])
@cognito_required(required_permissions=['year_end_close'])
@tenant_required()
def close_year(user_email, user_roles, tenant, user_tenants):
    """
    Close a fiscal year.
    
    This creates:
    1. Year-end closure transaction (P&L to equity)
    2. Opening balance transactions for next year
    3. Closure status record
    
    All operations are performed in a database transaction.
    
    Request body:
        {
            "year": int,
            "notes": str (optional)
        }
    
    Returns:
        {
            "success": bool,
            "year": int,
            "closure_transaction_number": str,
            "opening_transaction_number": str,
            "net_result": float,
            "net_result_formatted": str,
            "balance_sheet_accounts": int,
            "message": str
        }
    """
    try:
        data = request.get_json()
        year = data.get('year')
        notes = data.get('notes', '')
        
        if not year:
            return jsonify({
                'error': 'year is required'
            }), 400
        
        service = YearEndClosureService()
        result = service.close_year(tenant, year, user_email, notes)
        
        return jsonify(result), 200
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Failed to close year {data.get("year", "unknown")}'
        }), 500


@year_end_bp.route('/api/year-end/closed-years', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_closed_years(user_email, user_roles, tenant, user_tenants):
    """
    Get list of closed years with details.
    
    Returns:
        [
            {
                "year": int,
                "closed_date": str,
                "closed_by": str,
                "closure_transaction_number": str,
                "opening_balance_transaction_number": str,
                "notes": str
            }
        ]
    """
    try:
        service = YearEndClosureService()
        closed_years = service.get_closed_years(tenant)
        
        return jsonify(closed_years), 200
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Failed to get closed years'
        }), 500


@year_end_bp.route('/api/year-end/status/<int:year>', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_year_status(year, user_email, user_roles, tenant, user_tenants):
    """
    Get closure status for a specific year.
    
    Returns:
        {
            "year": int,
            "closed_date": str,
            "closed_by": str,
            "closure_transaction_number": str,
            "opening_balance_transaction_number": str,
            "notes": str
        }
        
        Or null if year is not closed.
    """
    try:
        service = YearEndClosureService()
        status = service.get_year_status(tenant, year)
        
        if status:
            return jsonify(status), 200
        else:
            return jsonify({
                'year': year,
                'closed': False,
                'message': f'Year {year} is not closed'
            }), 200
    
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': f'Failed to get status for year {year}'
        }), 500
