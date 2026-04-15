"""
Contact Routes: Shared contact registry CRUD endpoints.

Reusable by future modules. Gated by ZZP module for now.

Reference: .kiro/specs/zzp-module/design.md §4.1
"""

import logging
from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.module_registry import module_required
from database import DatabaseManager
from services.contact_service import ContactService
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

contact_bp = Blueprint('contacts', __name__)

# ── Service initialisation ──────────────────────────────────

_test_mode = False


def set_test_mode(flag: bool) -> None:
    global _test_mode
    _test_mode = flag


def _get_service() -> ContactService:
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return ContactService(db=db, parameter_service=param_svc)


# ── Endpoints ───────────────────────────────────────────────


@contact_bp.route('/api/contacts', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def list_contacts(user_email, user_roles, tenant, user_tenants):
    """List contacts for tenant, optionally filtered by contact_type."""
    try:
        svc = _get_service()
        contact_type = request.args.get('contact_type')
        include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
        contacts = svc.list_contacts(tenant, contact_type=contact_type,
                                     include_inactive=include_inactive)
        return jsonify({'success': True, 'data': contacts})
    except Exception as e:
        logger.error("list_contacts error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/contacts/<int:contact_id>', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_contact(user_email, user_roles, tenant, user_tenants, contact_id):
    """Get a single contact by id."""
    try:
        svc = _get_service()
        contact = svc.get_contact(tenant, contact_id)
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        return jsonify({'success': True, 'data': contact})
    except Exception as e:
        logger.error("get_contact error for %s/%s: %s", tenant, contact_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/contacts', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def create_contact(user_email, user_roles, tenant, user_tenants):
    """Create a new contact."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        svc = _get_service()
        contact = svc.create_contact(tenant, data, created_by=user_email)
        return jsonify({'success': True, 'data': contact}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("create_contact error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/contacts/<int:contact_id>', methods=['PUT'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def update_contact(user_email, user_roles, tenant, user_tenants, contact_id):
    """Update an existing contact."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        svc = _get_service()
        contact = svc.update_contact(tenant, contact_id, data)
        return jsonify({'success': True, 'data': contact})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("update_contact error for %s/%s: %s", tenant, contact_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def delete_contact(user_email, user_roles, tenant, user_tenants, contact_id):
    """Soft-delete a contact (deactivate)."""
    try:
        svc = _get_service()
        svc.soft_delete_contact(tenant, contact_id)
        return jsonify({'success': True, 'message': 'Contact deactivated'})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("delete_contact error for %s/%s: %s", tenant, contact_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/contacts/types', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_contact_types(user_email, user_roles, tenant, user_tenants):
    """Get configurable contact types for this tenant."""
    try:
        svc = _get_service()
        types = svc.get_contact_types(tenant)
        return jsonify({'success': True, 'data': types})
    except Exception as e:
        logger.error("get_contact_types error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500
