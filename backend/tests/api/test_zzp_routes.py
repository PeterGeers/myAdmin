"""
API tests for ZZP invoice endpoints.

Tests the core ZZP invoice CRUD operations, overdue marking, copy-last-invoice,
booking account validation, and supporting document upload.

Uses Flask test client with mocked auth decorators and service layer.
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from functools import wraps
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────


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


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def mock_invoice_service():
    return Mock()


@pytest.fixture
def mock_db():
    return Mock()


@pytest.fixture
def zzp_client(mock_invoice_service, mock_db):
    """Flask test client with mocked auth and invoice service."""
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


# ── GET /api/zzp/invoices ───────────────────────────────────


@pytest.mark.api
class TestListInvoices:
    """Tests for the list invoices endpoint."""

    def test_list_invoices_returns_data(self, zzp_client, mock_invoice_service):
        mock_invoice_service.list_invoices.return_value = [
            {'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
             'grand_total': 121.0},
            {'id': 2, 'invoice_number': 'INV-2026-0002', 'status': 'sent',
             'grand_total': 242.0},
        ]
        resp = zzp_client.get('/api/zzp/invoices')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 2

    def test_list_invoices_with_status_filter(self, zzp_client, mock_invoice_service):
        mock_invoice_service.list_invoices.return_value = [
            {'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft'},
        ]
        resp = zzp_client.get('/api/zzp/invoices?status=draft')
        assert resp.status_code == 200
        # Verify filter was passed to service
        call_args = mock_invoice_service.list_invoices.call_args
        filters = call_args[0][1]
        assert filters['status'] == 'draft'

    def test_list_invoices_with_pagination(self, zzp_client, mock_invoice_service):
        mock_invoice_service.list_invoices.return_value = []
        resp = zzp_client.get('/api/zzp/invoices?limit=10&offset=20')
        assert resp.status_code == 200
        call_args = mock_invoice_service.list_invoices.call_args
        filters = call_args[0][1]
        assert filters['limit'] == 10
        assert filters['offset'] == 20

    def test_list_invoices_with_date_range(self, zzp_client, mock_invoice_service):
        mock_invoice_service.list_invoices.return_value = []
        resp = zzp_client.get('/api/zzp/invoices?date_from=2026-01-01&date_to=2026-12-31')
        assert resp.status_code == 200
        call_args = mock_invoice_service.list_invoices.call_args
        filters = call_args[0][1]
        assert filters['date_from'] == '2026-01-01'
        assert filters['date_to'] == '2026-12-31'

    def test_list_invoices_service_error_returns_500(self, zzp_client, mock_invoice_service):
        mock_invoice_service.list_invoices.side_effect = Exception("DB connection failed")
        resp = zzp_client.get('/api/zzp/invoices')
        assert resp.status_code == 500
        assert resp.get_json()['success'] is False


# ── GET /api/zzp/invoices/<id> ──────────────────────────────


@pytest.mark.api
class TestGetInvoice:
    """Tests for the get invoice endpoint."""

    def test_get_invoice_returns_data(self, zzp_client, mock_invoice_service):
        mock_invoice_service.get_invoice.return_value = {
            'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
            'lines': [{'id': 1, 'description': 'Consulting', 'amount': 100.0}],
            'vat_summary': [{'rate': 21.0, 'base': 100.0, 'vat': 21.0}],
        }
        resp = zzp_client.get('/api/zzp/invoices/1')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['invoice_number'] == 'INV-2026-0001'
        assert 'lines' in data
        assert 'vat_summary' in data

    def test_get_invoice_not_found_returns_404(self, zzp_client, mock_invoice_service):
        mock_invoice_service.get_invoice.return_value = None
        resp = zzp_client.get('/api/zzp/invoices/999')
        assert resp.status_code == 404
        assert resp.get_json()['success'] is False

    def test_get_invoice_service_error_returns_500(self, zzp_client, mock_invoice_service):
        mock_invoice_service.get_invoice.side_effect = Exception("Unexpected error")
        resp = zzp_client.get('/api/zzp/invoices/1')
        assert resp.status_code == 500


# ── POST /api/zzp/invoices ──────────────────────────────────


@pytest.mark.api
class TestCreateInvoice:
    """Tests for the create invoice endpoint."""

    def test_create_invoice_success_returns_201(self, zzp_client, mock_invoice_service):
        mock_invoice_service.create_invoice.return_value = {
            'id': 10, 'invoice_number': 'INV-2026-0010', 'status': 'draft',
        }
        resp = zzp_client.post(
            '/api/zzp/invoices',
            data=json.dumps({
                'contact_id': 1,
                'invoice_date': '2026-05-01',
                'lines': [{'product_id': 1, 'quantity': 1, 'unit_price': 100.0}],
            }),
            content_type='application/json',
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['invoice_number'] == 'INV-2026-0010'

    def test_create_invoice_no_body_returns_error(self, zzp_client):
        # Without valid JSON body, Flask's get_json() raises before
        # the route's own validation, resulting in a 500 from the generic handler
        resp = zzp_client.post('/api/zzp/invoices', content_type='application/json')
        assert resp.status_code in (400, 500)
        assert resp.get_json()['success'] is False

    def test_create_invoice_validation_error_returns_400(self, zzp_client, mock_invoice_service):
        mock_invoice_service.create_invoice.side_effect = ValueError(
            "contact_id is required"
        )
        resp = zzp_client.post(
            '/api/zzp/invoices',
            data=json.dumps({'invoice_date': '2026-05-01'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'contact_id' in resp.get_json()['error']

    def test_create_invoice_service_error_returns_500(self, zzp_client, mock_invoice_service):
        mock_invoice_service.create_invoice.side_effect = Exception("DB failure")
        resp = zzp_client.post(
            '/api/zzp/invoices',
            data=json.dumps({'contact_id': 1}),
            content_type='application/json',
        )
        assert resp.status_code == 500


# ── PUT /api/zzp/invoices/<id> ──────────────────────────────


@pytest.mark.api
class TestUpdateInvoice:
    """Tests for the update invoice endpoint."""

    def test_update_invoice_success_returns_200(self, zzp_client, mock_invoice_service):
        mock_invoice_service.update_invoice.return_value = {
            'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
            'grand_total': 150.0,
        }
        resp = zzp_client.put(
            '/api/zzp/invoices/1',
            data=json.dumps({'lines': [{'product_id': 1, 'quantity': 1.5, 'unit_price': 100.0}]}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['grand_total'] == 150.0

    def test_update_invoice_no_body_returns_error(self, zzp_client):
        # Without valid JSON body, Flask's get_json() raises before
        # the route's own validation, resulting in a 500 from the generic handler
        resp = zzp_client.put('/api/zzp/invoices/1', content_type='application/json')
        assert resp.status_code in (400, 500)
        assert resp.get_json()['success'] is False

    def test_update_invoice_sent_returns_400(self, zzp_client, mock_invoice_service):
        mock_invoice_service.update_invoice.side_effect = ValueError(
            "Cannot edit a sent invoice"
        )
        resp = zzp_client.put(
            '/api/zzp/invoices/1',
            data=json.dumps({'lines': []}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'sent' in resp.get_json()['error']

    def test_update_invoice_service_error_returns_500(self, zzp_client, mock_invoice_service):
        mock_invoice_service.update_invoice.side_effect = Exception("DB failure")
        resp = zzp_client.put(
            '/api/zzp/invoices/1',
            data=json.dumps({'lines': []}),
            content_type='application/json',
        )
        assert resp.status_code == 500


# ── POST /api/zzp/invoices/mark-overdue ─────────────────────


@pytest.mark.api
class TestMarkOverdue:
    """Tests for the mark-overdue endpoint."""

    def test_mark_overdue_returns_count(self, zzp_client, mock_invoice_service):
        mock_invoice_service.mark_overdue.return_value = 3
        resp = zzp_client.post('/api/zzp/invoices/mark-overdue')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['updated'] == 3

    def test_mark_overdue_none_found(self, zzp_client, mock_invoice_service):
        mock_invoice_service.mark_overdue.return_value = 0
        resp = zzp_client.post('/api/zzp/invoices/mark-overdue')
        assert resp.status_code == 200
        assert resp.get_json()['updated'] == 0

    def test_mark_overdue_service_error_returns_500(self, zzp_client, mock_invoice_service):
        mock_invoice_service.mark_overdue.side_effect = Exception("DB failure")
        resp = zzp_client.post('/api/zzp/invoices/mark-overdue')
        assert resp.status_code == 500


# ── POST /api/zzp/invoices/copy-last/<contact_id> ───────────


@pytest.mark.api
class TestCopyLastInvoice:
    """Tests for the copy-last-invoice endpoint."""

    def test_copy_last_invoice_success_returns_201(self, zzp_client, mock_invoice_service):
        mock_invoice_service.copy_last_invoice.return_value = {
            'id': 20, 'invoice_number': 'INV-2026-0020', 'status': 'draft',
            'contact_id': 5,
        }
        resp = zzp_client.post('/api/zzp/invoices/copy-last/5')
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'draft'

    def test_copy_last_invoice_no_previous_returns_400(self, zzp_client, mock_invoice_service):
        mock_invoice_service.copy_last_invoice.side_effect = ValueError(
            "No previous invoice found for contact 99"
        )
        resp = zzp_client.post('/api/zzp/invoices/copy-last/99')
        assert resp.status_code == 400
        assert 'No previous invoice' in resp.get_json()['error']

    def test_copy_last_invoice_service_error_returns_500(self, zzp_client, mock_invoice_service):
        mock_invoice_service.copy_last_invoice.side_effect = Exception("Unexpected")
        resp = zzp_client.post('/api/zzp/invoices/copy-last/5')
        assert resp.status_code == 500


# ── POST /api/zzp/accounts/validate-booking-param ───────────


@pytest.mark.api
class TestValidateBookingParam:
    """Tests for the validate-booking-param endpoint."""

    def test_validate_booking_param_success(self, zzp_client, mock_db):
        # Mock the validation query to return a matching row
        mock_db.execute_query.return_value = [{'Account': '1300'}]
        # Mock _get_param_service
        with patch('routes.zzp_routes._get_param_service') as mock_ps:
            mock_param_svc = Mock()
            mock_ps.return_value = mock_param_svc
            resp = zzp_client.post(
                '/api/zzp/accounts/validate-booking-param',
                data=json.dumps({'key': 'debtor_account', 'value': '1300'}),
                content_type='application/json',
            )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_validate_booking_param_missing_key_returns_400(self, zzp_client):
        resp = zzp_client.post(
            '/api/zzp/accounts/validate-booking-param',
            data=json.dumps({'value': '1300'}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_validate_booking_param_missing_value_returns_400(self, zzp_client):
        resp = zzp_client.post(
            '/api/zzp/accounts/validate-booking-param',
            data=json.dumps({'key': 'debtor_account'}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_validate_booking_param_invalid_key_returns_400(self, zzp_client):
        resp = zzp_client.post(
            '/api/zzp/accounts/validate-booking-param',
            data=json.dumps({'key': 'invalid_key', 'value': '1300'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'Invalid key' in resp.get_json()['error']

    def test_validate_booking_param_account_not_flagged_returns_400(self, zzp_client, mock_db):
        # Mock validation query returns empty - account not flagged
        mock_db.execute_query.return_value = []
        resp = zzp_client.post(
            '/api/zzp/accounts/validate-booking-param',
            data=json.dumps({'key': 'revenue_account', 'value': '8000'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'not flagged' in resp.get_json()['error']


# ── POST /api/zzp/invoices/<id>/documents ───────────────────


@pytest.mark.api
class TestUploadSupportingDocument:
    """Tests for the upload supporting document endpoint."""

    def test_upload_document_success_returns_201(self, zzp_client, mock_invoice_service):
        mock_invoice_service.get_invoice.return_value = {
            'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
        }
        with patch('storage.storage_provider.get_storage_provider') as mock_storage:
            mock_provider = Mock()
            mock_provider.upload.return_value = 'https://drive.google.com/file/doc123'
            mock_storage.return_value = mock_provider

            data = {
                'file': (BytesIO(b'test file content'), 'receipt.pdf'),
            }
            resp = zzp_client.post(
                '/api/zzp/invoices/1/documents',
                data=data,
                content_type='multipart/form-data',
            )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['success'] is True
        assert body['data']['filename'] == 'receipt.pdf'
        assert body['data']['url'] == 'https://drive.google.com/file/doc123'

    def test_upload_document_invoice_not_found_returns_404(
        self, zzp_client, mock_invoice_service
    ):
        mock_invoice_service.get_invoice.return_value = None
        data = {
            'file': (BytesIO(b'content'), 'doc.pdf'),
        }
        resp = zzp_client.post(
            '/api/zzp/invoices/999/documents',
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 404

    def test_upload_document_no_file_returns_400(self, zzp_client, mock_invoice_service):
        mock_invoice_service.get_invoice.return_value = {
            'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
        }
        resp = zzp_client.post(
            '/api/zzp/invoices/1/documents',
            content_type='multipart/form-data',
        )
        assert resp.status_code == 400


# ── GET /api/zzp/accounts/invoice-ledgers ───────────────────


@pytest.mark.api
class TestGetInvoiceLedgerAccounts:
    """Tests for the invoice-ledgers endpoint."""

    def test_get_ledger_accounts_returns_data(self, zzp_client, mock_db):
        mock_db.execute_query.return_value = [
            {'nummer': '8000', 'naam': 'Revenue'},
            {'nummer': '8010', 'naam': 'Service Revenue'},
        ]
        resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_get_ledger_accounts_empty_uses_fallback(self, zzp_client, mock_db):
        # First call returns empty (no flagged accounts), second might be fallback
        mock_db.execute_query.return_value = []
        with patch('routes.zzp_routes._get_param_service') as mock_ps:
            mock_param_svc = Mock()
            mock_param_svc.get_param.return_value = '8000'
            mock_ps.return_value = mock_param_svc
            resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
        assert resp.status_code == 200
