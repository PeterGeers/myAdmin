"""
Tax Rate Administration API

CRUD endpoints for managing tax rates via the TaxRateService.
Tenant_Admin can manage tenant rates, SysAdmin can manage system defaults.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
Reference: .kiro/specs/parameter-driven-config/design.md
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.tax_rate_service import TaxRateService
from datetime import date
import os
import logging

logger = logging.getLogger(__name__)

tax_rate_admin_bp = Blueprint('tax_rate_admin', __name__)

flag = os.getenv('TEST_MODE', 'false').lower() == 'true'


def _get_service():
    db = DatabaseManager(test_mode=flag)
    return TaxRateService(db)


def _is_sysadmin(user_roles):
    return 'SysAdmin' in (user_roles or [])


@tax_rate_admin_bp.route('/api/tenant-admin/tax-rates', methods=['GET'])
@cognito_required(required_permissions=[])
@tenant_required()
def list_tax_rates(user_email, user_roles, tenant, user_tenants):
    """List all rates for tenant + applicable system defaults."""
    try:
        db = DatabaseManager(test_mode=flag)
        query = """
            SELECT id, administration, tax_type, tax_code, rate, ledger_account,
                   effective_from, effective_to, description, calc_method, calc_params
            FROM tax_rates
            WHERE administration IN (%s, '_system_')
            ORDER BY tax_type, tax_code, effective_from
        """
        rows = db.execute_query(query, (tenant,), fetch=True)

        rates = []
        for r in rows:
            rates.append({
                'id': r['id'],
                'tax_type': r['tax_type'],
                'tax_code': r['tax_code'],
                'rate': float(r['rate']) if r['rate'] else 0,
                'ledger_account': r.get('ledger_account'),
                'effective_from': str(r['effective_from']) if r.get('effective_from') else None,
                'effective_to': str(r['effective_to']) if r.get('effective_to') else None,
                'source': 'system' if r['administration'] == '_system_' else 'tenant',
                'description': r.get('description'),
                'calc_method': r.get('calc_method', 'percentage'),
            })

        return jsonify({'success': True, 'tenant': tenant, 'tax_rates': rates})
    except Exception as e:
        logger.error("Error listing tax rates: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@tax_rate_admin_bp.route('/api/tenant-admin/tax-rates', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def create_tax_rate(user_email, user_roles, tenant, user_tenants):
    """Create a tax rate with date conflict validation and auto-close."""
    try:
        data = request.get_json()
        tax_type = data.get('tax_type')
        tax_code = data.get('tax_code')
        rate = data.get('rate')
        effective_from_str = data.get('effective_from')

        if not all([tax_type, tax_code, rate is not None, effective_from_str]):
            return jsonify({
                'success': False,
                'error': 'tax_type, tax_code, rate, and effective_from are required'
            }), 400

        administration = data.get('administration', tenant)
        if administration == '_system_' and not _is_sysadmin(user_roles):
            return jsonify({
                'success': False, 'error': 'SysAdmin required for system rates'
            }), 403

        eff_from = date.fromisoformat(effective_from_str)
        eff_to_str = data.get('effective_to')
        eff_to = date.fromisoformat(eff_to_str) if eff_to_str else None

        svc = _get_service()
        rate_id = svc.create_tax_rate(
            administration=administration,
            tax_type=tax_type, tax_code=tax_code,
            rate=float(rate), effective_from=eff_from, effective_to=eff_to,
            ledger_account=data.get('ledger_account'),
            description=data.get('description'),
            calc_method=data.get('calc_method', 'percentage'),
            calc_params=data.get('calc_params'),
            created_by=user_email,
        )

        return jsonify({'success': True, 'id': rate_id, 'message': 'Tax rate created'})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        if '1062' in str(e) or 'Duplicate' in str(e):
            return jsonify({'success': False, 'error': 'Duplicate tax rate'}), 409
        logger.error("Error creating tax rate: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@tax_rate_admin_bp.route('/api/tenant-admin/tax-rates/<int:rate_id>', methods=['PUT'])
@cognito_required(required_permissions=[])
@tenant_required()
def update_tax_rate(user_email, user_roles, tenant, user_tenants, rate_id):
    """Update a tax rate (fix typos on rate, description, ledger_account, dates)."""
    try:
        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT administration, tax_type, tax_code FROM tax_rates WHERE id = %s",
            (rate_id,), fetch=True
        )
        if not rows:
            return jsonify({'success': False, 'error': 'Tax rate not found'}), 404

        administration = rows[0]['administration']

        if administration == '_system_' and not _is_sysadmin(user_roles):
            return jsonify({
                'success': False, 'error': 'SysAdmin required for system rates'
            }), 403
        if administration != '_system_' and administration != tenant:
            return jsonify({
                'success': False, 'error': 'Tax rate not owned by this tenant'
            }), 404

        data = request.get_json()
        updates = []
        params = []

        if 'rate' in data:
            updates.append("rate = %s")
            params.append(float(data['rate']))
        if 'description' in data:
            updates.append("description = %s")
            params.append(data['description'])
        if 'ledger_account' in data:
            updates.append("ledger_account = %s")
            params.append(data['ledger_account'])
        if 'effective_from' in data:
            updates.append("effective_from = %s")
            params.append(data['effective_from'])
        if 'effective_to' in data:
            updates.append("effective_to = %s")
            params.append(data['effective_to'])
        if 'calc_method' in data:
            updates.append("calc_method = %s")
            params.append(data['calc_method'])

        if not updates:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400

        params.append(rate_id)
        sql = f"UPDATE tax_rates SET {', '.join(updates)} WHERE id = %s"
        db.execute_query(sql, tuple(params), fetch=False, commit=True)

        svc = _get_service()
        svc._invalidate_cache()

        return jsonify({'success': True, 'message': 'Tax rate updated'})
    except Exception as e:
        logger.error("Error updating tax rate %s: %s", rate_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@tax_rate_admin_bp.route('/api/tenant-admin/tax-rates/<int:rate_id>', methods=['DELETE'])
@cognito_required(required_permissions=[])
@tenant_required()
def delete_tax_rate(user_email, user_roles, tenant, user_tenants, rate_id):
    """Delete a tenant tax rate override. System defaults require SysAdmin."""
    try:
        db = DatabaseManager(test_mode=flag)
        rows = db.execute_query(
            "SELECT administration FROM tax_rates WHERE id = %s",
            (rate_id,), fetch=True
        )
        if not rows:
            return jsonify({'success': False, 'error': 'Tax rate not found'}), 404

        administration = rows[0]['administration']

        if administration == '_system_' and not _is_sysadmin(user_roles):
            return jsonify({
                'success': False, 'error': 'SysAdmin required to delete system rates'
            }), 403

        if administration != '_system_' and administration != tenant:
            return jsonify({
                'success': False, 'error': 'Tax rate not owned by this tenant'
            }), 404

        svc = _get_service()
        if administration == '_system_':
            db.execute_query(
                "DELETE FROM tax_rates WHERE id = %s", (rate_id,),
                fetch=False, commit=True
            )
            deleted = True
        else:
            deleted = svc.delete_tax_rate(rate_id, administration)

        if deleted:
            return jsonify({'success': True, 'message': 'Tax rate deleted'})
        return jsonify({'success': False, 'error': 'Delete failed'}), 500
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error("Error deleting tax rate %s: %s", rate_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500
