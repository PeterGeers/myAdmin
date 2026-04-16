"""
API tests for ZZP Phase 12: Invoice ledger account endpoint.

Tests the GET /api/zzp/accounts/invoice-ledgers endpoint which returns
accounts flagged with zzp_invoice_ledger in the chart of accounts,
with fallback to the zzp.revenue_account parameter.

Reference: .kiro/specs/zzp-module/design-parameter-enhancements.md §14.2
"""

import pytest
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
def mock_db():
    return Mock()


@pytest.fixture
def mock_param_service():
    return Mock()


@pytest.fixture
def zzp_client(mock_db, mock_param_service):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module), \
         patch('database.DatabaseManager', return_value=mock_db):
        import importlib
        import routes.zzp_routes as zr
        importlib.reload(zr)
        zr._get_param_service = lambda: mock_param_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(zr.zzp_bp)
        yield app.test_client()


# ── Invoice Ledger Account Tests (Req 17.3, 17.4) ──────────


def test_get_invoice_ledgers_returns_flagged_accounts(zzp_client, mock_db):
    """Accounts flagged with zzp_invoice_ledger should be returned."""
    mock_db.execute_query.return_value = [
        {'nummer': '8001', 'naam': 'Omzet dienstverlening'},
        {'nummer': '8002', 'naam': 'Omzet producten'},
    ]
    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert len(data['data']) == 2
    assert data['data'][0] == {'account_code': '8001', 'account_name': 'Omzet dienstverlening'}
    assert data['data'][1] == {'account_code': '8002', 'account_name': 'Omzet producten'}


def test_get_invoice_ledgers_ordered_by_nummer(zzp_client, mock_db):
    """Verify the query orders by nummer (account code)."""
    mock_db.execute_query.return_value = [
        {'nummer': '8001', 'naam': 'First'},
        {'nummer': '8010', 'naam': 'Second'},
    ]
    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    # Verify the SQL query includes ORDER BY nummer
    call_args = mock_db.execute_query.call_args
    query = call_args[0][0]
    assert 'ORDER BY nummer' in query


def test_get_invoice_ledgers_filters_by_tenant(zzp_client, mock_db):
    """Verify the primary query filters by the authenticated tenant."""
    mock_db.execute_query.return_value = [
        {'nummer': '8001', 'naam': 'Omzet'},
    ]
    zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    first_call = mock_db.execute_query.call_args_list[0]
    params = first_call[0][1]
    assert params == ('TestTenant',)


def test_get_invoice_ledgers_uses_json_extract(zzp_client, mock_db):
    """Verify the query uses JSON_EXTRACT for zzp_invoice_ledger flag."""
    mock_db.execute_query.return_value = [
        {'nummer': '8001', 'naam': 'Omzet'},
    ]
    zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    first_call = mock_db.execute_query.call_args_list[0]
    query = first_call[0][0]
    assert "JSON_EXTRACT(parameters, '$.zzp_invoice_ledger')" in query


def test_get_invoice_ledgers_fallback_to_revenue_account_param(
    zzp_client, mock_db, mock_param_service
):
    """When no accounts are flagged, fall back to zzp.revenue_account parameter."""
    # First call: no flagged accounts; second call: fallback lookup
    mock_db.execute_query.side_effect = [
        [],  # No flagged accounts
        [{'nummer': '8001', 'naam': 'Omzet'}],  # Fallback account
    ]
    mock_param_service.get_param.return_value = '8001'

    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert len(data['data']) == 1
    assert data['data'][0] == {'account_code': '8001', 'account_name': 'Omzet'}
    mock_param_service.get_param.assert_called_once_with(
        'zzp', 'revenue_account', tenant='TestTenant'
    )


def test_get_invoice_ledgers_fallback_default_8001(
    zzp_client, mock_db, mock_param_service
):
    """When no param is configured, default to account 8001."""
    mock_db.execute_query.side_effect = [
        [],  # No flagged accounts
        [{'nummer': '8001', 'naam': 'Omzet standaard'}],  # Default 8001
    ]
    mock_param_service.get_param.return_value = None  # No param configured

    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['data']) == 1
    assert data['data'][0]['account_code'] == '8001'

    # Verify the fallback query used '8001'
    second_call = mock_db.execute_query.call_args_list[1]
    assert second_call[0][1] == ('TestTenant', '8001')


def test_get_invoice_ledgers_fallback_account_not_found(
    zzp_client, mock_db, mock_param_service
):
    """When fallback account doesn't exist in chart, return empty list."""
    mock_db.execute_query.side_effect = [
        [],  # No flagged accounts
        [],  # Fallback account not found
    ]
    mock_param_service.get_param.return_value = '9999'

    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] == []


def test_get_invoice_ledgers_no_fallback_when_flagged_accounts_exist(
    zzp_client, mock_db, mock_param_service
):
    """When flagged accounts exist, don't query the fallback."""
    mock_db.execute_query.return_value = [
        {'nummer': '8001', 'naam': 'Omzet'},
    ]

    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    # Only one DB call (the flagged accounts query), no fallback
    assert mock_db.execute_query.call_count == 1
    mock_param_service.get_param.assert_not_called()


def test_get_invoice_ledgers_db_error_returns_500(zzp_client, mock_db):
    """Database errors should return 500 with error message."""
    mock_db.execute_query.side_effect = Exception("DB connection failed")
    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False
    assert 'DB connection failed' in data['error']


def test_get_invoice_ledgers_none_result_treated_as_empty(zzp_client, mock_db, mock_param_service):
    """When execute_query returns None, treat as empty list and trigger fallback."""
    mock_db.execute_query.side_effect = [
        None,  # None from first query
        [{'nummer': '8001', 'naam': 'Omzet'}],  # Fallback
    ]
    mock_param_service.get_param.return_value = '8001'

    resp = zzp_client.get('/api/zzp/accounts/invoice-ledgers')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['data']) == 1


# ── Booking Account Validation Tests (Req 19.6, Design §14.4) ──


def test_validate_booking_param_debtor_account_valid(zzp_client, mock_db, mock_param_service):
    """Valid debtor account with zzp_debtor_account flag should succeed."""
    mock_db.execute_query.return_value = [{'nummer': '1300'}]
    mock_param_service.set_param.return_value = None

    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'debtor_account', 'value': '1300'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'zzp.debtor_account' in data['message']

    # Verify the validation query checked the correct flag
    call_args = mock_db.execute_query.call_args
    query = call_args[0][0]
    params = call_args[0][1]
    assert '$.zzp_debtor_account' in str(params)
    assert 'JSON_EXTRACT' in query


def test_validate_booking_param_creditor_account_valid(zzp_client, mock_db, mock_param_service):
    """Valid creditor account with zzp_creditor_account flag should succeed."""
    mock_db.execute_query.return_value = [{'nummer': '1600'}]
    mock_param_service.set_param.return_value = None

    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'creditor_account', 'value': '1600'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'zzp.creditor_account' in data['message']


def test_validate_booking_param_revenue_account_valid(zzp_client, mock_db, mock_param_service):
    """Valid revenue account with zzp_invoice_ledger flag should succeed."""
    mock_db.execute_query.return_value = [{'nummer': '8001'}]
    mock_param_service.set_param.return_value = None

    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'revenue_account', 'value': '8001'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True


def test_validate_booking_param_unflagged_account_returns_400(zzp_client, mock_db):
    """Account without the required flag should return 400."""
    mock_db.execute_query.return_value = []  # No matching flagged account

    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'debtor_account', 'value': '1300'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'zzp_debtor_account' in data['error']
    assert '1300' in data['error']


def test_validate_booking_param_creditor_unflagged_returns_400(zzp_client, mock_db):
    """Creditor account without zzp_creditor_account flag should return 400."""
    mock_db.execute_query.return_value = []

    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'creditor_account', 'value': '1600'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'zzp_creditor_account' in data['error']


def test_validate_booking_param_saves_on_success(zzp_client, mock_db, mock_param_service):
    """After validation passes, the parameter should be saved via ParameterService."""
    mock_db.execute_query.return_value = [{'nummer': '1300'}]
    mock_param_service.set_param.return_value = None

    zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'debtor_account', 'value': '1300'},
    )
    mock_param_service.set_param.assert_called_once_with(
        'tenant', 'TestTenant', 'zzp', 'debtor_account', '1300',
        value_type='string', created_by='test@example.com',
    )


def test_validate_booking_param_does_not_save_on_failure(zzp_client, mock_db, mock_param_service):
    """When validation fails, the parameter should NOT be saved."""
    mock_db.execute_query.return_value = []  # Validation fails

    zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'debtor_account', 'value': '9999'},
    )
    mock_param_service.set_param.assert_not_called()


def test_validate_booking_param_missing_key_returns_400(zzp_client):
    """Missing key in request body should return 400."""
    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'value': '1300'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'key and value are required' in data['error']


def test_validate_booking_param_missing_value_returns_400(zzp_client):
    """Missing value in request body should return 400."""
    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'debtor_account'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'key and value are required' in data['error']


def test_validate_booking_param_invalid_key_returns_400(zzp_client):
    """Invalid key (not in the allowed set) should return 400."""
    resp = zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'invalid_key', 'value': '1300'},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'Invalid key' in data['error']


def test_validate_booking_param_filters_by_tenant(zzp_client, mock_db, mock_param_service):
    """Validation query should filter by the authenticated tenant."""
    mock_db.execute_query.return_value = [{'nummer': '1300'}]
    mock_param_service.set_param.return_value = None

    zzp_client.post(
        '/api/zzp/accounts/validate-booking-param',
        json={'key': 'debtor_account', 'value': '1300'},
    )
    call_args = mock_db.execute_query.call_args
    params = call_args[0][1]
    assert params[0] == 'TestTenant'
    assert params[1] == '1300'
