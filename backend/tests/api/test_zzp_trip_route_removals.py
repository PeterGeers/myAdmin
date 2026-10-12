"""
API tests for ZZP Rittenregistratie: trip-billing route removals (task 12.2).

Task 12.1 removed the trip-billing surface from the backend routes:
- POST /api/zzp/invoices/from-trips  (invoice-from-trips)  -> no longer registered
- GET  /api/zzp/trips/unbilled        (unbilled-trips)      -> no longer registered
- the `is_billed` / `contact_id` passthroughs on the list route were removed

These tests assert that the removed routes now 404, and that the list route
ignores legacy `is_billed` / `contact_id` query filters and returns the full,
unfiltered trip set with no error.

Uses the Flask test client with mocked auth decorators and a mocked service
layer, matching the harness in test_zzp_vehicle_api.py / test_zzp_routes.py.

Reference: .kiro/specs/rittenregistratie-tax-log-redesign/requirements.md
           Req 4.1, 4.2, 4.3, 10.7 (reinforces Property 7)
"""

import json
import os
import sys
from functools import wraps
from unittest.mock import Mock, patch

import pytest
from flask import Flask

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
def mock_trip_service():
    return Mock()


@pytest.fixture
def trip_client(mock_trip_service):
    """Flask test client with both ZZP trip blueprints registered.

    Registering both zzp_trip_bp (CRUD/list) and zzp_trip_io_bp
    (import/export) reproduces the real route surface so a request to a
    removed route resolves to a genuine 404 (route not registered on any
    ZZP trip blueprint), not a false 404 from a missing blueprint.
    """
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_trip_routes as tr
        import routes.zzp_trip_import_export_routes as tio
        importlib.reload(tr)
        importlib.reload(tio)
        tr._get_trip_service = lambda: mock_trip_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(tr.zzp_trip_bp)
        app.register_blueprint(tio.zzp_trip_io_bp)
        yield app.test_client()


# ── POST /api/zzp/invoices/from-trips removed (Req 4.1) ─────


@pytest.mark.api
class TestInvoiceFromTripsRemoved:
    """The invoice-from-trips route must no longer be registered."""

    def test_post_invoice_from_trips_returns_404(self, trip_client):
        resp = trip_client.post(
            '/api/zzp/invoices/from-trips',
            data=json.dumps({'trip_ids': [1, 2, 3]}),
            content_type='application/json',
        )
        assert resp.status_code == 404

    def test_get_invoice_from_trips_returns_404(self, trip_client):
        # No HTTP method should resolve the removed route.
        resp = trip_client.get('/api/zzp/invoices/from-trips')
        assert resp.status_code == 404


# ── GET /api/zzp/trips/unbilled removed (Req 4.2) ──────────


@pytest.mark.api
class TestUnbilledTripsRemoved:
    """The unbilled-trips route must no longer be registered."""

    def test_get_unbilled_trips_returns_404(self, trip_client):
        resp = trip_client.get('/api/zzp/trips/unbilled')
        assert resp.status_code == 404

    def test_unbilled_not_confused_with_trip_id_route(self, trip_client, mock_trip_service):
        # /api/zzp/trips/<int:trip_id> only matches integers, so the literal
        # "unbilled" segment must not fall through to get_trip.
        resp = trip_client.get('/api/zzp/trips/unbilled')
        assert resp.status_code == 404
        mock_trip_service.get_trip.assert_not_called()


# ── GET /api/zzp/trips ignores billing filters (Req 4.3) ───


@pytest.mark.api
class TestListTripsIgnoresBillingFilters:
    """Legacy is_billed / contact_id filters are ignored; full set returned.

    Reinforces Property 7 (billing filters ignored, metamorphic): listing
    with the legacy filters returns the same result set as listing without
    them, with no error.
    """

    _FULL_SET = {
        'data': [
            {'id': 1, 'start_address': 'A', 'end_address': 'B', 'client_name': 'Klant 1'},
            {'id': 2, 'start_address': 'C', 'end_address': 'D', 'client_name': None},
        ],
        'total': 2,
    }

    def test_list_trips_ignores_is_billed_filter(self, trip_client, mock_trip_service):
        mock_trip_service.list_trips.return_value = self._FULL_SET
        resp = trip_client.get('/api/zzp/trips?is_billed=true')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['total'] == 2
        assert len(body['data']) == 2
        # The removed passthrough must not forward is_billed to the service.
        filters = mock_trip_service.list_trips.call_args.kwargs['filters']
        assert 'is_billed' not in filters

    def test_list_trips_ignores_contact_id_filter(self, trip_client, mock_trip_service):
        mock_trip_service.list_trips.return_value = self._FULL_SET
        resp = trip_client.get('/api/zzp/trips?contact_id=42')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        assert body['total'] == 2
        filters = mock_trip_service.list_trips.call_args.kwargs['filters']
        assert 'contact_id' not in filters

    def test_list_trips_with_billing_filters_matches_unfiltered(
        self, trip_client, mock_trip_service
    ):
        # Metamorphic (Property 7): with and without the legacy filters yield
        # the same full set and no error.
        mock_trip_service.list_trips.return_value = self._FULL_SET

        resp_plain = trip_client.get('/api/zzp/trips')
        resp_filtered = trip_client.get(
            '/api/zzp/trips?is_billed=false&contact_id=7'
        )

        assert resp_plain.status_code == 200
        assert resp_filtered.status_code == 200
        assert resp_plain.get_json()['data'] == resp_filtered.get_json()['data']
        assert resp_plain.get_json()['total'] == resp_filtered.get_json()['total']

        # Neither legacy key should ever reach the service filter dict.
        for call in mock_trip_service.list_trips.call_args_list:
            filters = call.kwargs['filters']
            assert 'is_billed' not in filters
            assert 'contact_id' not in filters
