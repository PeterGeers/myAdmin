"""
API tests for ZZP Phase 1: Contact, Product, and Field Config routes.

Uses Flask test client with mocked auth decorators and service layer.
"""

import pytest
import json
import sys
import os
from unittest.mock import Mock, patch
from flask import Flask
from functools import wraps

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
def mock_contact_service():
    return Mock()


@pytest.fixture
def mock_product_service():
    return Mock()


@pytest.fixture
def contact_client(mock_contact_service):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.contact_routes as cr
        importlib.reload(cr)
        cr._get_service = lambda: mock_contact_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(cr.contact_bp)
        yield app.test_client()


@pytest.fixture
def product_client(mock_product_service):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.product_routes as pr
        importlib.reload(pr)
        pr._get_service = lambda: mock_product_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(pr.product_bp)
        yield app.test_client()


@pytest.fixture
def zzp_client():
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── Contact route tests ─────────────────────────────────────


def test_list_contacts_valid_tenant_returns_contacts(contact_client, mock_contact_service):
    mock_contact_service.list_contacts.return_value = [
        {'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}
    ]
    resp = contact_client.get('/api/contacts')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert len(data['data']) == 1


def test_list_contacts_type_filter_passes_param_to_service(contact_client, mock_contact_service):
    mock_contact_service.list_contacts.return_value = []
    contact_client.get('/api/contacts?contact_type=supplier')
    mock_contact_service.list_contacts.assert_called_once_with(
        'TestTenant', contact_type='supplier', include_inactive=False
    )


def test_get_contact_found_returns_200(contact_client, mock_contact_service):
    mock_contact_service.get_contact.return_value = {'id': 1, 'client_id': 'ACME'}
    resp = contact_client.get('/api/contacts/1')
    assert resp.status_code == 200
    assert resp.get_json()['data']['client_id'] == 'ACME'


def test_get_contact_not_found_returns_404(contact_client, mock_contact_service):
    mock_contact_service.get_contact.return_value = None
    resp = contact_client.get('/api/contacts/999')
    assert resp.status_code == 404


def test_create_contact_valid_data_returns_201(contact_client, mock_contact_service):
    mock_contact_service.create_contact.return_value = {'id': 1, 'client_id': 'NEW'}
    resp = contact_client.post('/api/contacts',
                               data=json.dumps({'client_id': 'NEW', 'company_name': 'New Co'}),
                               content_type='application/json')
    assert resp.status_code == 201
    assert resp.get_json()['success'] is True


def test_create_contact_validation_error_returns_400(contact_client, mock_contact_service):
    mock_contact_service.create_contact.side_effect = ValueError("client_id already exists")
    resp = contact_client.post('/api/contacts',
                               data=json.dumps({'client_id': 'DUP'}),
                               content_type='application/json')
    assert resp.status_code == 400
    assert 'already exists' in resp.get_json()['error']


def test_create_contact_no_body_returns_error(contact_client):
    resp = contact_client.post('/api/contacts', content_type='application/json')
    assert resp.status_code in (400, 500)


def test_update_contact_valid_data_returns_200(contact_client, mock_contact_service):
    mock_contact_service.update_contact.return_value = {'id': 1, 'company_name': 'Updated'}
    resp = contact_client.put('/api/contacts/1',
                              data=json.dumps({'company_name': 'Updated'}),
                              content_type='application/json')
    assert resp.status_code == 200


def test_delete_contact_unused_returns_200(contact_client, mock_contact_service):
    mock_contact_service.soft_delete_contact.return_value = True
    resp = contact_client.delete('/api/contacts/1')
    assert resp.status_code == 200


def test_delete_contact_in_use_returns_400(contact_client, mock_contact_service):
    mock_contact_service.soft_delete_contact.side_effect = ValueError("referenced by existing invoices")
    resp = contact_client.delete('/api/contacts/1')
    assert resp.status_code == 400
    assert 'referenced' in resp.get_json()['error']


def test_get_contact_types_returns_types(contact_client, mock_contact_service):
    mock_contact_service.get_contact_types.return_value = ['client', 'supplier', 'both']
    resp = contact_client.get('/api/contacts/types')
    assert resp.status_code == 200
    assert 'client' in resp.get_json()['data']


# ── Product route tests ──────────────────────────────────────


def test_list_products_valid_tenant_returns_products(product_client, mock_product_service):
    mock_product_service.list_products.return_value = [
        {'id': 1, 'product_code': 'DEV-HR', 'name': 'Development'}
    ]
    resp = product_client.get('/api/products')
    assert resp.status_code == 200
    assert len(resp.get_json()['data']) == 1


def test_get_product_found_returns_200(product_client, mock_product_service):
    mock_product_service.get_product.return_value = {'id': 1, 'product_code': 'DEV-HR'}
    resp = product_client.get('/api/products/1')
    assert resp.status_code == 200


def test_get_product_not_found_returns_404(product_client, mock_product_service):
    mock_product_service.get_product.return_value = None
    resp = product_client.get('/api/products/999')
    assert resp.status_code == 404


def test_create_product_valid_data_returns_201(product_client, mock_product_service):
    mock_product_service.create_product.return_value = {'id': 1, 'product_code': 'NEW'}
    resp = product_client.post('/api/products',
                               data=json.dumps({'product_code': 'NEW', 'name': 'New'}),
                               content_type='application/json')
    assert resp.status_code == 201


def test_create_product_invalid_vat_returns_400(product_client, mock_product_service):
    mock_product_service.create_product.side_effect = ValueError("Invalid vat_code")
    resp = product_client.post('/api/products',
                               data=json.dumps({'vat_code': 'bad'}),
                               content_type='application/json')
    assert resp.status_code == 400


def test_update_product_valid_data_returns_200(product_client, mock_product_service):
    mock_product_service.update_product.return_value = {'id': 1, 'name': 'Updated'}
    resp = product_client.put('/api/products/1',
                              data=json.dumps({'name': 'Updated'}),
                              content_type='application/json')
    assert resp.status_code == 200


def test_delete_product_unused_returns_200(product_client, mock_product_service):
    mock_product_service.soft_delete_product.return_value = True
    resp = product_client.delete('/api/products/1')
    assert resp.status_code == 200


def test_delete_product_in_use_returns_400(product_client, mock_product_service):
    mock_product_service.soft_delete_product.side_effect = ValueError("referenced by existing invoice lines")
    resp = product_client.delete('/api/products/1')
    assert resp.status_code == 400


def test_get_product_types_returns_types(product_client, mock_product_service):
    mock_product_service.get_product_types.return_value = ['service', 'product', 'hours']
    resp = product_client.get('/api/products/types')
    assert resp.status_code == 200
    assert 'service' in resp.get_json()['data']


# ── Field config route tests ────────────────────────────────


@patch('routes.zzp_routes._get_param_service')
def test_get_field_config_contacts_no_override_returns_defaults(mock_param_factory, zzp_client):
    mock_svc = Mock()
    mock_svc.get_param.return_value = None
    mock_param_factory.return_value = mock_svc
    resp = zzp_client.get('/api/zzp/field-config/contacts')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['client_id'] == 'required'
    assert data['company_name'] == 'required'


@patch('routes.zzp_routes._get_param_service')
def test_get_field_config_tenant_override_enforces_always_required(mock_param_factory, zzp_client):
    mock_svc = Mock()
    mock_svc.get_param.return_value = {
        'client_id': 'hidden',
        'company_name': 'required',
        'vat_number': 'hidden',
    }
    mock_param_factory.return_value = mock_svc
    resp = zzp_client.get('/api/zzp/field-config/contacts')
    data = resp.get_json()['data']
    assert data['client_id'] == 'required'
    assert data['vat_number'] == 'hidden'


def test_get_field_config_invalid_entity_returns_400(zzp_client):
    resp = zzp_client.get('/api/zzp/field-config/invalid')
    assert resp.status_code == 400


@patch('routes.zzp_routes._get_param_service')
def test_put_field_config_valid_data_returns_200(mock_param_factory, zzp_client):
    mock_svc = Mock()
    mock_param_factory.return_value = mock_svc
    resp = zzp_client.put('/api/zzp/field-config/contacts',
                          data=json.dumps({'vat_number': 'hidden', 'phone': 'optional'}),
                          content_type='application/json')
    assert resp.status_code == 200
    mock_svc.set_param.assert_called_once()


@patch('routes.zzp_routes._get_param_service')
def test_put_field_config_hiding_required_returns_400(mock_param_factory, zzp_client):
    mock_svc = Mock()
    mock_param_factory.return_value = mock_svc
    resp = zzp_client.put('/api/zzp/field-config/contacts',
                          data=json.dumps({'client_id': 'hidden'}),
                          content_type='application/json')
    assert resp.status_code == 400
    assert 'cannot be set to hidden' in resp.get_json()['error']


def test_put_field_config_invalid_entity_returns_400(zzp_client):
    resp = zzp_client.put('/api/zzp/field-config/bogus',
                          data=json.dumps({'x': 'required'}),
                          content_type='application/json')
    assert resp.status_code == 400


@patch('routes.zzp_routes._get_param_service')
def test_put_field_config_invalid_level_returns_400(mock_param_factory, zzp_client):
    mock_svc = Mock()
    mock_param_factory.return_value = mock_svc
    resp = zzp_client.put('/api/zzp/field-config/contacts',
                          data=json.dumps({'phone': 'visible'}),
                          content_type='application/json')
    assert resp.status_code == 400
    assert 'Invalid level' in resp.get_json()['error']


# ── Module gating test ───────────────────────────────────────


def test_contact_route_zzp_not_enabled_returns_403():
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
        import importlib
        import routes.contact_routes as cr
        importlib.reload(cr)
        with patch('database.DatabaseManager') as mock_db_cls:
            mock_db = Mock()
            mock_db.execute_query.return_value = []
            mock_db_cls.return_value = mock_db
            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(cr.contact_bp)
            client = app.test_client()
            resp = client.get('/api/contacts')
            assert resp.status_code == 403
            assert 'not enabled' in resp.get_json()['error']


# ── Invoice route tests (Phase 2) ───────────────────────────


@pytest.fixture
def mock_invoice_service():
    return Mock()


@pytest.fixture
def invoice_client(mock_invoice_service):
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


def test_list_invoices_valid_tenant_returns_invoices(invoice_client, mock_invoice_service):
    mock_invoice_service.list_invoices.return_value = [
        {'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft'}
    ]
    resp = invoice_client.get('/api/zzp/invoices')
    assert resp.status_code == 200
    assert len(resp.get_json()['data']) == 1


def test_list_invoices_status_filter_passes_to_service(invoice_client, mock_invoice_service):
    mock_invoice_service.list_invoices.return_value = []
    invoice_client.get('/api/zzp/invoices?status=draft')
    call_args = mock_invoice_service.list_invoices.call_args
    assert call_args[0][1]['status'] == 'draft'


def test_get_invoice_found_returns_200(invoice_client, mock_invoice_service):
    mock_invoice_service.get_invoice.return_value = {
        'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
        'lines': [], 'vat_summary': [],
    }
    resp = invoice_client.get('/api/zzp/invoices/1')
    assert resp.status_code == 200
    assert resp.get_json()['data']['invoice_number'] == 'INV-2026-0001'


def test_get_invoice_not_found_returns_404(invoice_client, mock_invoice_service):
    mock_invoice_service.get_invoice.return_value = None
    resp = invoice_client.get('/api/zzp/invoices/999')
    assert resp.status_code == 404


def test_create_invoice_valid_data_returns_201(invoice_client, mock_invoice_service):
    mock_invoice_service.create_invoice.return_value = {
        'id': 1, 'invoice_number': 'INV-2026-0001', 'status': 'draft',
    }
    resp = invoice_client.post('/api/zzp/invoices',
                               data=json.dumps({
                                   'contact_id': 1,
                                   'invoice_date': '2026-04-15',
                                   'lines': [{'description': 'Dev', 'quantity': 160,
                                              'unit_price': 95.0, 'vat_code': 'high'}],
                               }),
                               content_type='application/json')
    assert resp.status_code == 201
    assert resp.get_json()['success'] is True


def test_create_invoice_invalid_contact_returns_400(invoice_client, mock_invoice_service):
    mock_invoice_service.create_invoice.side_effect = ValueError("Contact 999 not found")
    resp = invoice_client.post('/api/zzp/invoices',
                               data=json.dumps({'contact_id': 999, 'invoice_date': '2026-04-15'}),
                               content_type='application/json')
    assert resp.status_code == 400
    assert 'not found' in resp.get_json()['error']


def test_create_invoice_no_body_returns_error(invoice_client):
    resp = invoice_client.post('/api/zzp/invoices', content_type='application/json')
    assert resp.status_code in (400, 500)


def test_update_invoice_draft_returns_200(invoice_client, mock_invoice_service):
    mock_invoice_service.update_invoice.return_value = {
        'id': 1, 'notes': 'Updated', 'status': 'draft',
    }
    resp = invoice_client.put('/api/zzp/invoices/1',
                              data=json.dumps({'notes': 'Updated'}),
                              content_type='application/json')
    assert resp.status_code == 200


def test_update_invoice_sent_returns_400(invoice_client, mock_invoice_service):
    mock_invoice_service.update_invoice.side_effect = ValueError("Only draft invoices can be edited")
    resp = invoice_client.put('/api/zzp/invoices/1',
                              data=json.dumps({'notes': 'Nope'}),
                              content_type='application/json')
    assert resp.status_code == 400
    assert 'draft' in resp.get_json()['error']
