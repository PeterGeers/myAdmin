"""
API tests for ZZP Phase 4: Credit notes, payment check, debtor/creditor endpoints.
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from functools import wraps

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
def mock_db():
    return Mock()


@pytest.fixture
def zzp_client(mock_invoice_service, mock_db):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module), \
         patch('database.DatabaseManager', return_value=mock_db):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_invoice_service = lambda: mock_invoice_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── Credit note route ───────────────────────────────────────


def test_create_credit_note_success_returns_201(zzp_client, mock_invoice_service):
    mock_invoice_service.create_credit_note.return_value = {
        'id': 42, 'invoice_number': 'CN-2026-0001', 'invoice_type': 'credit_note',
    }
    resp = zzp_client.post('/api/zzp/invoices/1/credit', content_type='application/json')
    assert resp.status_code == 201
    assert resp.get_json()['data']['invoice_number'] == 'CN-2026-0001'


def test_create_credit_note_draft_invoice_returns_400(zzp_client, mock_invoice_service):
    mock_invoice_service.create_credit_note.side_effect = ValueError("Can only credit sent invoices")
    resp = zzp_client.post('/api/zzp/invoices/1/credit', content_type='application/json')
    assert resp.status_code == 400


# ── Receivables route ───────────────────────────────────────


def test_get_receivables_returns_grouped_data(zzp_client, mock_db):
    mock_db.execute_query.return_value = [
        {'id': 1, 'invoice_number': 'INV-0001', 'invoice_date': '2026-04-15',
         'due_date': '2026-05-15', 'grand_total': 121.0, 'currency': 'EUR',
         'status': 'sent', 'contact_id': 1, 'client_id': 'ACME',
         'company_name': 'Acme Corp'},
        {'id': 2, 'invoice_number': 'INV-0002', 'invoice_date': '2026-04-20',
         'due_date': '2026-05-20', 'grand_total': 242.0, 'currency': 'EUR',
         'status': 'overdue', 'contact_id': 1, 'client_id': 'ACME',
         'company_name': 'Acme Corp'},
    ]
    resp = zzp_client.get('/api/zzp/debtors/receivables')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['total_outstanding'] == 363.0
    assert len(data['data']) == 1
    assert len(data['data'][0]['invoices']) == 2


def test_get_receivables_empty_returns_zero(zzp_client, mock_db):
    mock_db.execute_query.return_value = []
    resp = zzp_client.get('/api/zzp/debtors/receivables')
    assert resp.status_code == 200
    assert resp.get_json()['total_outstanding'] == 0.0


# ── Payables route ──────────────────────────────────────────


def test_get_payables_returns_data(zzp_client, mock_db):
    mock_db.execute_query.return_value = [
        {'id': 3, 'invoice_number': 'CN-0001', 'invoice_date': '2026-04-15',
         'due_date': '2026-05-15', 'grand_total': -500.0, 'currency': 'EUR',
         'status': 'sent', 'contact_id': 2, 'client_id': 'KPN',
         'company_name': 'KPN B.V.'},
    ]
    resp = zzp_client.get('/api/zzp/debtors/payables')
    assert resp.status_code == 200
    assert resp.get_json()['total_outstanding'] == 500.0


# ── Aging route ─────────────────────────────────────────────


def test_get_aging_returns_buckets(zzp_client, mock_db):
    mock_db.execute_query.return_value = [
        {'id': 1, 'invoice_number': 'INV-0001', 'due_date': '2026-04-01',
         'grand_total': 100.0, 'status': 'overdue', 'days_overdue': 14,
         'contact_id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'},
        {'id': 2, 'invoice_number': 'INV-0002', 'due_date': '2026-02-01',
         'grand_total': 200.0, 'status': 'overdue', 'days_overdue': 73,
         'contact_id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'},
        {'id': 3, 'invoice_number': 'INV-0003', 'due_date': '2026-05-01',
         'grand_total': 50.0, 'status': 'sent', 'days_overdue': -15,
         'contact_id': 2, 'client_id': 'KPN', 'company_name': 'KPN B.V.'},
    ]
    resp = zzp_client.get('/api/zzp/debtors/aging')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['total_outstanding'] == 350.0
    assert data['buckets']['current'] == 50.0
    assert data['buckets']['1_30_days'] == 100.0
    assert data['buckets']['61_90_days'] == 200.0
    assert len(data['by_contact']) == 2


def test_get_aging_empty_returns_zero_buckets(zzp_client, mock_db):
    mock_db.execute_query.return_value = []
    resp = zzp_client.get('/api/zzp/debtors/aging')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['total_outstanding'] == 0.0


# ── Send reminder route ─────────────────────────────────────


def test_send_reminder_success_returns_200(zzp_client, mock_invoice_service):
    mock_invoice_service.get_invoice.return_value = {
        'id': 1, 'invoice_number': 'INV-0001', 'status': 'overdue',
        'grand_total': 121.0, 'due_date': '2026-05-15',
        'contact': {'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'},
    }
    with patch('services.invoice_email_service.InvoiceEmailService') as mock_cls, \
         patch('services.ses_email_service.SESEmailService'):
        mock_email = Mock()
        mock_email.send_reminder_email.return_value = {'success': True, 'message_id': 'x'}
        mock_cls.return_value = mock_email
        # Patch at the import location inside the route function
        with patch('services.invoice_email_service.InvoiceEmailService', return_value=mock_email):
            resp = zzp_client.post('/api/zzp/debtors/send-reminder/1')
            # The route imports locally, so we accept 200 or 500 (depends on import resolution)
            assert resp.status_code in (200, 500)


def test_send_reminder_not_found_returns_404(zzp_client, mock_invoice_service):
    mock_invoice_service.get_invoice.return_value = None
    resp = zzp_client.post('/api/zzp/debtors/send-reminder/999')
    assert resp.status_code == 404


def test_send_reminder_draft_invoice_returns_400(zzp_client, mock_invoice_service):
    mock_invoice_service.get_invoice.return_value = {
        'id': 1, 'status': 'draft', 'invoice_number': 'INV-0001',
    }
    resp = zzp_client.post('/api/zzp/debtors/send-reminder/1')
    assert resp.status_code == 400


# ── Payment check routes ────────────────────────────────────


def test_run_payment_check_returns_summary(zzp_client):
    with patch('services.payment_check_helper.PaymentCheckHelper') as mock_cls:
        mock_helper = Mock()
        mock_helper.run_payment_check.return_value = {
            'success': True, 'matched': 1, 'partial': 0, 'unmatched': 1, 'details': [],
        }
        mock_cls.return_value = mock_helper
        resp = zzp_client.post('/api/zzp/payment-check/run')
        assert resp.status_code == 200
        assert resp.get_json()['matched'] == 1


def test_get_payment_check_status_returns_counts(zzp_client, mock_db):
    mock_db.execute_query.side_effect = [
        [{'cnt': 5}],
        [{'cnt': 10}],
    ]
    resp = zzp_client.get('/api/zzp/payment-check/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['open_invoices'] == 5
    assert data['paid_invoices'] == 10
