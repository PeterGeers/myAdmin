"""
ZZP Time Tracking Routes

Provides CRUD and summary endpoints for ZZP time entries.
Split from zzp_routes.py for file size management.

Reference: .kiro/specs/zzp-module/design.md §11 (Time Tracking)
"""

import logging

from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.module_registry import module_required
from database import DatabaseManager
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

zzp_time_bp = Blueprint('zzp_time', __name__)

_test_mode = False


def set_test_mode(flag: bool) -> None:
    global _test_mode
    _test_mode = flag


def _get_time_service() -> "TimeTrackingService":
    from services.time_tracking_service import TimeTrackingService
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return TimeTrackingService(db=db, parameter_service=param_svc)


# ── Time Tracking Endpoints (Req 11) ───────────────────────


@zzp_time_bp.route('/api/zzp/time-entries', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def list_time_entries(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """List time entries with optional filters."""
    try:
        svc = _get_time_service()
        if not svc.is_enabled(tenant):
            return jsonify({'success': False, 'error': 'Time tracking is disabled'}), 404
        filters = {
            'contact_id': request.args.get('contact_id'),
            'project_name': request.args.get('project_name'),
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            'limit': int(request.args.get('limit', 50)),
            'offset': int(request.args.get('offset', 0)),
        }
        if request.args.get('is_billable') is not None:
            filters['is_billable'] = request.args.get('is_billable').lower() == 'true'
        if request.args.get('is_billed') is not None:
            filters['is_billed'] = request.args.get('is_billed').lower() == 'true'
        filters = {k: v for k, v in filters.items() if v is not None}
        entries = svc.list_entries(tenant, filters)
        entries = svc.enrich_with_contacts(tenant, entries)
        return jsonify({'success': True, 'data': entries})
    except Exception as e:
        logger.error("list_time_entries error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@zzp_time_bp.route('/api/zzp/time-entries', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def create_time_entry(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Create a time entry."""
    try:
        svc = _get_time_service()
        if not svc.is_enabled(tenant):
            return jsonify({'success': False, 'error': 'Time tracking is disabled'}), 404
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        entry = svc.create_entry(tenant, data, created_by=user_email)
        return jsonify({'success': True, 'data': entry}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("create_time_entry error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@zzp_time_bp.route('/api/zzp/time-entries/<int:entry_id>', methods=['PUT'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def update_time_entry(user_email, user_roles, tenant, user_tenants, entry_id) -> ResponseReturnValue:
    """Update a time entry."""
    try:
        svc = _get_time_service()
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        entry = svc.update_entry(tenant, entry_id, data)
        return jsonify({'success': True, 'data': entry})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("update_time_entry error for %s/%s: %s", tenant, entry_id, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@zzp_time_bp.route('/api/zzp/time-entries/<int:entry_id>', methods=['DELETE'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def delete_time_entry(user_email, user_roles, tenant, user_tenants, entry_id) -> ResponseReturnValue:
    """Delete a time entry."""
    try:
        svc = _get_time_service()
        svc.delete_entry(tenant, entry_id)
        return jsonify({'success': True, 'message': 'Time entry deleted'})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("delete_time_entry error for %s/%s: %s", tenant, entry_id, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500


@zzp_time_bp.route('/api/zzp/time-entries/summary', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_time_summary(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Get time entry summary grouped by contact, project, or period."""
    try:
        svc = _get_time_service()
        if not svc.is_enabled(tenant):
            return jsonify({'success': False, 'error': 'Time tracking is disabled'}), 404
        group_by = request.args.get('group_by', 'contact')
        period = request.args.get('period', 'month')
        summary = svc.get_summary(tenant, group_by=group_by, period=period)
        return jsonify({'success': True, 'data': summary})
    except Exception as e:
        logger.error("get_time_summary error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500
