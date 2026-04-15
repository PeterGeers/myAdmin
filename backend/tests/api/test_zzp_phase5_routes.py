"""
API tests for ZZP Phase 5: Time tracking endpoints.
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch
from flask import Flask
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['ZZP_Read', 'ZZP_Write']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_module(module_name):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


@pytest.fixture
def mock_time_service():
    svc = Mock()
    svc.is_enabled.return_value = True
    return svc


@pytest.fixture
def zzp_client(mock_time_service):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module), \
         patch('database.DatabaseManager'):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_time_service = lambda: mock_time_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── GET /api/zzp/time-entries ───────────────────────────────


def test_list_time_entries_returns_data(zzp_client, mock_time_service):
    mock_time_service.list_entries.return_value = [
        {'id': 1, 'hours': 8.0, 'entry_date': '2026-04-15'},
    ]
    resp = zzp_client.get('/api/zzp/time-entries')
    assert resp.status_code == 200
    assert len(resp.get_json()['data']) == 1


def test_list_time_entries_disabled_returns_404(zzp_client, mock_time_service):
    mock_time_service.is_enabled.return_value = False
    resp = zzp_client.get('/api/zzp/time-entries')
    assert resp.status_code == 404


# ── POST /api/zzp/time-entries ──────────────────────────────


def test_create_time_entry_success_returns_201(zzp_client, mock_time_service):
    mock_time_service.create_entry.return_value = {'id': 5, 'hours': 8.0}
    resp = zzp_client.post('/api/zzp/time-entries',
                           data=json.dumps({'contact_id': 1, 'entry_date': '2026-04-15',
                                            'hours': 8.0, 'hourly_rate': 95.0}),
                           content_type='application/json')
    assert resp.status_code == 201


def test_create_time_entry_validation_error_returns_400(zzp_client, mock_time_service):
    mock_time_service.create_entry.side_effect = ValueError("Required fields missing")
    resp = zzp_client.post('/api/zzp/time-entries',
                           data=json.dumps({'contact_id': 1}),
                           content_type='application/json')
    assert resp.status_code == 400


# ── PUT /api/zzp/time-entries/<id> ──────────────────────────


def test_update_time_entry_success_returns_200(zzp_client, mock_time_service):
    mock_time_service.update_entry.return_value = {'id': 1, 'hours': 10.0}
    resp = zzp_client.put('/api/zzp/time-entries/1',
                          data=json.dumps({'hours': 10.0}),
                          content_type='application/json')
    assert resp.status_code == 200


def test_update_time_entry_billed_returns_400(zzp_client, mock_time_service):
    mock_time_service.update_entry.side_effect = ValueError("Cannot edit a billed time entry")
    resp = zzp_client.put('/api/zzp/time-entries/1',
                          data=json.dumps({'hours': 10.0}),
                          content_type='application/json')
    assert resp.status_code == 400


# ── DELETE /api/zzp/time-entries/<id> ───────────────────────


def test_delete_time_entry_success_returns_200(zzp_client, mock_time_service):
    mock_time_service.delete_entry.return_value = True
    resp = zzp_client.delete('/api/zzp/time-entries/1')
    assert resp.status_code == 200


def test_delete_time_entry_billed_returns_400(zzp_client, mock_time_service):
    mock_time_service.delete_entry.side_effect = ValueError("Cannot delete a billed time entry")
    resp = zzp_client.delete('/api/zzp/time-entries/1')
    assert resp.status_code == 400


# ── GET /api/zzp/time-entries/summary ───────────────────────


def test_get_time_summary_returns_data(zzp_client, mock_time_service):
    mock_time_service.get_summary.return_value = [
        {'contact_id': 1, 'total_hours': 40.0, 'total_amount': 3800.0},
    ]
    resp = zzp_client.get('/api/zzp/time-entries/summary?group_by=contact')
    assert resp.status_code == 200
    assert len(resp.get_json()['data']) == 1


def test_get_time_summary_disabled_returns_404(zzp_client, mock_time_service):
    mock_time_service.is_enabled.return_value = False
    resp = zzp_client.get('/api/zzp/time-entries/summary')
    assert resp.status_code == 404
