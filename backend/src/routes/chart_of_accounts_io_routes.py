"""
Chart of Accounts Import/Export Routes

Provides Excel export and import endpoints for the chart of accounts.
Split from chart_of_accounts_routes.py for file size management.

Endpoints:
- GET  /api/tenant-admin/chart-of-accounts/export - Export to Excel
- POST /api/tenant-admin/chart-of-accounts/import - Import from Excel
"""

import os
import logging

from flask import Blueprint, request, jsonify, send_file
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant, get_user_tenants, is_tenant_admin
from database import DatabaseManager

logger = logging.getLogger(__name__)

chart_of_accounts_io_bp = Blueprint('chart_of_accounts_io', __name__)


def _has_fin_module(tenant: str) -> bool:
    """Check if a tenant has the FIN module enabled."""
    from routes.chart_of_accounts_routes import has_fin_module
    return has_fin_module(tenant)


@chart_of_accounts_io_bp.route('/api/tenant-admin/chart-of-accounts/export', methods=['GET'])
@cognito_required(required_permissions=[])
def export_accounts(user_email, user_roles) -> ResponseReturnValue:
    """Export all accounts to Excel file.

    Returns:
        Excel file download with all accounts
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

        # Check FIN module access
        if not _has_fin_module(tenant):
            return jsonify({'error': 'FIN module not enabled'}), 403

        # Delegate to service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        from services.chart_of_accounts_io_service import ChartOfAccountsIOService
        io_service = ChartOfAccountsIOService(db=db)

        output, filename, count = io_service.export_to_excel(tenant)

        logger.info(f"EXPORT_ACCOUNTS: {user_email} exported {count} accounts for tenant {tenant}")

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Error exporting accounts: {e}")
        return jsonify({'error': 'Failed to export accounts', 'details': str(e)}), 500


@chart_of_accounts_io_bp.route('/api/tenant-admin/chart-of-accounts/import', methods=['POST'])
@cognito_required(required_permissions=[])
def import_accounts(user_email, user_roles) -> ResponseReturnValue:
    """Import accounts from Excel file.

    Request:
        - file: Excel file upload (.xlsx or .xls)

    Returns:
        { "success": true, "imported": 10, "updated": 5, "total": 15 }
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

        # Check FIN module access
        if not _has_fin_module(tenant):
            return jsonify({'error': 'FIN module not enabled'}), 403

        # Get uploaded file
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']

        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'error': 'Invalid file type. Must be Excel file (.xlsx or .xls)'}), 400

        # Delegate to service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        from services.chart_of_accounts_io_service import ChartOfAccountsIOService
        io_service = ChartOfAccountsIOService(db=db)

        result = io_service.import_from_excel(tenant, file)

        if not result.get('success'):
            return jsonify(result), 400

        logger.info(
            f"IMPORT_ACCOUNTS: {user_email} imported {result['imported']} "
            f"and updated {result['updated']} accounts for tenant {tenant}"
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error importing accounts: {e}")
        return jsonify({'error': 'Failed to import accounts', 'details': str(e)}), 500
