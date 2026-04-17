"""
Product Routes: Shared product/service registry CRUD endpoints.

Reusable by future modules. Gated by ZZP module for now.

Reference: .kiro/specs/zzp-module/design.md §4.2
"""

import logging
from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.module_registry import module_required
from database import DatabaseManager
from services.product_service import ProductService
from services.tax_rate_service import TaxRateService
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

product_bp = Blueprint('products', __name__)

# ── Service initialisation ──────────────────────────────────

_test_mode = False


def set_test_mode(flag: bool) -> None:
    global _test_mode
    _test_mode = flag


def _get_service() -> ProductService:
    db = DatabaseManager(test_mode=_test_mode)
    tax_svc = TaxRateService(db)
    param_svc = ParameterService(db)
    return ProductService(db=db, tax_rate_service=tax_svc, parameter_service=param_svc)


# ── Endpoints ───────────────────────────────────────────────


@product_bp.route('/api/products', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def list_products(user_email, user_roles, tenant, user_tenants):
    """List products for tenant."""
    try:
        svc = _get_service()
        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
        products = svc.list_products(tenant, include_inactive=include_inactive)
        return jsonify({'success': True, 'data': products})
    except Exception as e:
        logger.error("list_products error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@product_bp.route('/api/products/<int:product_id>', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_product(user_email, user_roles, tenant, user_tenants, product_id):
    """Get a single product by id."""
    try:
        svc = _get_service()
        product = svc.get_product(tenant, product_id)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        return jsonify({'success': True, 'data': product})
    except Exception as e:
        logger.error("get_product error for %s/%s: %s", tenant, product_id, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@product_bp.route('/api/products', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def create_product(user_email, user_roles, tenant, user_tenants):
    """Create a new product."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        svc = _get_service()
        product = svc.create_product(tenant, data, created_by=user_email)
        return jsonify({'success': True, 'data': product}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("create_product error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@product_bp.route('/api/products/<int:product_id>', methods=['PUT'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def update_product(user_email, user_roles, tenant, user_tenants, product_id):
    """Update an existing product."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        svc = _get_service()
        product = svc.update_product(tenant, product_id, data)
        return jsonify({'success': True, 'data': product})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("update_product error for %s/%s: %s", tenant, product_id, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@product_bp.route('/api/products/<int:product_id>', methods=['DELETE'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def delete_product(user_email, user_roles, tenant, user_tenants, product_id):
    """Soft-delete a product (deactivate)."""
    try:
        svc = _get_service()
        svc.soft_delete_product(tenant, product_id)
        return jsonify({'success': True, 'message': 'Product deactivated'})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("delete_product error for %s/%s: %s", tenant, product_id, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@product_bp.route('/api/products/types', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_product_types(user_email, user_roles, tenant, user_tenants):
    """Get configurable product types for this tenant."""
    try:
        svc = _get_service()
        types = svc.get_product_types(tenant)
        return jsonify({'success': True, 'data': types})
    except Exception as e:
        logger.error("get_product_types error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500
