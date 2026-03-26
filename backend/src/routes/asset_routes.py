"""
Asset Administration Routes

API endpoints for managing assets:
- GET    /api/assets          — List assets with book values
- POST   /api/assets          — Create asset
- GET    /api/assets/<id>     — Asset detail with transactions
- PUT    /api/assets/<id>     — Update asset metadata
- POST   /api/assets/<id>/dispose — Dispose asset
"""

import os
import logging
from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager
from services.asset_service import AssetService

logger = logging.getLogger(__name__)

asset_bp = Blueprint('assets', __name__, url_prefix='/api/assets')


def _get_service():
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    db = DatabaseManager(test_mode=test_mode)
    return AssetService(db)


@asset_bp.route('', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
def list_assets(user_email, user_roles):
    """List assets with current book values."""
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        service = _get_service()
        assets = service.get_assets(
            administration=tenant,
            status=request.args.get('status'),
            category=request.args.get('category'),
            ledger_account=request.args.get('ledger_account'),
        )
        return jsonify({'success': True, 'assets': assets, 'count': len(assets)})
    except Exception as e:
        logger.error(f"Error listing assets: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
def create_asset(user_email, user_roles):
    """
    Create a new asset.

    Request body:
    {
        "description": "Toyota Yaris 2024",
        "category": "vehicle",
        "ledger_account": "3060",
        "depreciation_account": "4017",
        "purchase_date": "2024-06-15",
        "purchase_amount": 25000.00,
        "depreciation_method": "straight_line",
        "depreciation_frequency": "quarterly",
        "useful_life_years": 5,
        "residual_value": 5000.00,
        "reference_number": "INV-2024-0042",
        "credit_account": "1002",
        "notes": "Company car"
    }
    """
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        required = ['description', 'ledger_account', 'purchase_date', 'purchase_amount']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400

        service = _get_service()
        result = service.create_asset(administration=tenant, data=data)
        return jsonify(result), 201
    except Exception as e:
        logger.error(f"Error creating asset: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/<int:asset_id>', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
def get_asset(user_email, user_roles, asset_id):
    """Get single asset with transaction history."""
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        service = _get_service()
        asset = service.get_asset(administration=tenant, asset_id=asset_id)
        if not asset:
            return jsonify({'error': 'Asset not found'}), 404
        return jsonify({'success': True, 'asset': asset})
    except Exception as e:
        logger.error(f"Error getting asset {asset_id}: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/<int:asset_id>', methods=['PUT'])
@cognito_required(required_permissions=['finance_write'])
def update_asset(user_email, user_roles, asset_id):
    """
    Update asset metadata.

    Financial fields (purchase_amount, purchase_date, ledger_account)
    are locked after the first depreciation entry.
    """
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        service = _get_service()
        result = service.update_asset(
            administration=tenant, asset_id=asset_id, data=data
        )
        if not result.get('success'):
            return jsonify(result), 400 if result.get('error') == 'Asset not found' else 422
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error updating asset {asset_id}: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/<int:asset_id>/dispose', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
def dispose_asset(user_email, user_roles, asset_id):
    """
    Dispose an asset.

    Request body:
    {
        "disposal_date": "2026-03-26",
        "disposal_amount": 8000.00,
        "credit_account": "1002"
    }
    """
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        data = request.get_json()
        if not data or not data.get('disposal_date'):
            return jsonify({'error': 'disposal_date is required'}), 400

        service = _get_service()
        result = service.dispose_asset(
            administration=tenant,
            asset_id=asset_id,
            disposal_date=data['disposal_date'],
            disposal_amount=float(data.get('disposal_amount', 0)),
            credit_account=data.get('credit_account'),
        )
        if not result.get('success'):
            status = 404 if result.get('error') == 'Asset not found' else 400
            return jsonify(result), status
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error disposing asset {asset_id}: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/generate-depreciation', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
def generate_depreciation(user_email, user_roles):
    """
    Generate depreciation entries for a period.

    Request body:
    {
        "year": 2026,
        "period": "Q1"    // "annual", "Q1"-"Q4", "M01"-"M12"
    }
    """
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        data = request.get_json()
        if not data or not data.get('year') or not data.get('period'):
            return jsonify({'error': 'year and period are required'}), 400

        service = _get_service()
        result = service.generate_depreciation(
            administration=tenant,
            period=data['period'],
            year=int(data['year']),
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error generating depreciation: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/reports/register', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
def asset_register_report(user_email, user_roles):
    """Asset register report — all assets with current book values."""
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        service = _get_service()
        assets = service.get_assets(administration=tenant)

        # Summary by category
        categories: dict = {}
        total_purchase = 0
        total_book = 0
        total_depreciation = 0
        for a in assets:
            cat = a.get('category') or 'uncategorized'
            if cat not in categories:
                categories[cat] = {'count': 0, 'purchase': 0, 'book_value': 0, 'depreciation': 0}
            categories[cat]['count'] += 1
            categories[cat]['purchase'] += a['purchase_amount']
            categories[cat]['book_value'] += a['book_value']
            categories[cat]['depreciation'] += a['total_depreciation']
            total_purchase += a['purchase_amount']
            total_book += a['book_value']
            total_depreciation += a['total_depreciation']

        return jsonify({
            'success': True,
            'assets': assets,
            'summary': {
                'total_assets': len(assets),
                'total_purchase': round(total_purchase, 2),
                'total_book_value': round(total_book, 2),
                'total_depreciation': round(total_depreciation, 2),
                'by_category': categories,
            }
        })
    except Exception as e:
        logger.error(f"Error generating asset register: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/reports/depreciation-schedule', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
def depreciation_schedule_report(user_email, user_roles):
    """Depreciation schedule — per asset, per year."""
    try:
        tenant = get_current_tenant(request)
        if not tenant:
            return jsonify({'error': 'No tenant selected'}), 400

        year = request.args.get('year', str(import_datetime().year))

        service = _get_service()
        assets = service.get_assets(administration=tenant, status='active')

        schedule = []
        for a in assets:
            if a.get('depreciation_method') == 'none' or not a.get('useful_life_years'):
                continue

            purchase = a['purchase_amount']
            residual = a.get('residual_value', 0)
            life = a['useful_life_years']
            annual = (purchase - residual) / life if life > 0 else 0

            schedule.append({
                'asset_id': a['id'],
                'description': a['description'],
                'category': a.get('category'),
                'purchase_amount': purchase,
                'residual_value': residual,
                'useful_life_years': life,
                'depreciation_method': a['depreciation_method'],
                'annual_depreciation': round(annual, 2),
                'total_depreciation': a['total_depreciation'],
                'book_value': a['book_value'],
            })

        return jsonify({
            'success': True,
            'year': year,
            'schedule': schedule,
            'total_annual_depreciation': round(sum(s['annual_depreciation'] for s in schedule), 2),
        })
    except Exception as e:
        logger.error(f"Error generating depreciation schedule: {e}")
        return jsonify({'error': str(e)}), 500


def import_datetime():
    from datetime import datetime
    return datetime.now()
