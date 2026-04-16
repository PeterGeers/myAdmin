"""
API tests for ZZP Phase 3: Invoice send and PDF download endpoints.

Uses Flask test client with mocked auth decorators and service layer.
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch
from flask import Flask
from functools import wraps
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['ZZP_Read', 'ZZP_CRUD']
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
def mock_invoice_service():
    return Mock()


@pytest.fixture
def zzp_client(mock_invoice_service):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_invoice_service = lambda: mock_invoice_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── POST /api/zzp/invoices/<id>/send ────────────────────────


def test_send_invoice_success_returns_200(zzp_client, mock_invoice_service):
    mock_invoice_service.send_invoice.return_value = {
        'success': True, 'invoice_number': 'INV-2026-0001',
    }
    resp = zzp_client.post('/api/zzp/invoices/1/send',
                           data=json.dumps({'send_email': True, 'output_destination': 'gdrive'}),
                           content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_send_invoice_not_draft_returns_400(zzp_client, mock_invoice_service):
    mock_invoice_service.send_invoice.side_effect = ValueError("Only draft invoices can be sent")
    resp = zzp_client.post('/api/zzp/invoices/1/send',
                           data=json.dumps({}),
                           content_type='application/json')
    assert resp.status_code == 400
    assert 'draft' in resp.get_json()['error']


def test_send_invoice_email_failure_returns_400(zzp_client, mock_invoice_service):
    mock_invoice_service.send_invoice.return_value = {
        'success': False, 'error': 'email failed',
    }
    resp = zzp_client.post('/api/zzp/invoices/1/send',
                           data=json.dumps({}),
                           content_type='application/json')
    assert resp.status_code == 400


def test_send_invoice_not_found_returns_400(zzp_client, mock_invoice_service):
    mock_invoice_service.send_invoice.side_effect = ValueError("Invoice 999 not found")
    resp = zzp_client.post('/api/zzp/invoices/999/send',
                           data=json.dumps({}),
                           content_type='application/json')
    assert resp.status_code == 400


# ── GET /api/zzp/invoices/<id>/pdf ──────────────────────────


def test_get_invoice_pdf_stored_returns_url(zzp_client, mock_invoice_service):
    mock_invoice_service.get_invoice_pdf.return_value = {
        'url': 'https://drive.google.com/file/abc',
        'filename': 'INV-2026-0001.pdf',
    }
    resp = zzp_client.get('/api/zzp/invoices/1/pdf')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'drive.google.com' in data['data']['url']


def test_get_invoice_pdf_regenerated_returns_file(zzp_client, mock_invoice_service):
    mock_invoice_service.get_invoice_pdf.return_value = {
        'content': BytesIO(b'%PDF-fake'),
        'filename': 'INV-2026-0001_COPY.pdf',
        'content_type': 'application/pdf',
    }
    resp = zzp_client.get('/api/zzp/invoices/1/pdf')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'


def test_get_invoice_pdf_not_found_returns_404(zzp_client, mock_invoice_service):
    mock_invoice_service.get_invoice_pdf.return_value = None
    resp = zzp_client.get('/api/zzp/invoices/999/pdf')
    assert resp.status_code == 404
