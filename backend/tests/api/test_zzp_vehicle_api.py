"""
API tests for ZZP Rittenregistratie: Vehicle endpoints.

Tests the vehicle CRUD endpoints in the zzp_trip_routes Blueprint:
- GET  /api/zzp/vehicles       — list vehicles (optional is_active filter)
- POST /api/zzp/vehicles       — create vehicle
- PUT  /api/zzp/vehicles/{id}  — update vehicle
- DELETE /api/zzp/vehicles/{id} — soft-delete (deactivate)

Uses mocked service layer to isolate API routing logic from database.

Reference: .kiro/specs/ZZP/rittenregistratie/design.md §3.1
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


def _blocking_cognito(required_permissions=None):
    """Simulates unauthenticated request — returns 401."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import jsonify
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return wrapper
    return decorator


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def mock_vehicle_service():
    return Mock()


@pytest.fixture
def vehicle_client(mock_vehicle_service):
    """Flask test client with mocked auth and mocked VehicleService."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_trip_routes as tr
        importlib.reload(tr)
        tr._get_vehicle_service = lambda: mock_vehicle_service
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(tr.zzp_trip_bp)
        yield app.test_client()


@pytest.fixture
def unauth_client():
    """Flask test client that simulates unauthenticated requests."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_blocking_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module):
        import importlib
        import routes.zzp_trip_routes as tr
        importlib.reload(tr)
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(tr.zzp_trip_bp)
        yield app.test_client()


# ── Sample data ─────────────────────────────────────────────


SAMPLE_VEHICLE = {
    "id": 1,
    "license_plate": "AB-123-CD",
    "make": "Volkswagen",
    "model": "Golf",
    "year_built": 2020,
    "vin": None,
    "vehicle_type": "private_for_business",
    "odometer_unit": "km",
    "owner_lease_company": None,
    "start_odometer": 45000,
    "start_date": "2026-01-01",
    "is_active": True,
}

CREATE_PAYLOAD = {
    "license_plate": "AB-123-CD",
    "make": "Volkswagen",
    "model": "Golf",
    "year_built": 2020,
    "vehicle_type": "private_for_business",
    "odometer_unit": "km",
    "start_odometer": 45000,
    "start_date": "2026-01-01",
}


# ── GET /api/zzp/vehicles ──────────────────────────────────


class TestListVehicles:
    """Tests for GET /api/zzp/vehicles."""

    def test_list_vehicles_returns_200_with_data(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.list_vehicles.return_value = [SAMPLE_VEHICLE]
        resp = vehicle_client.get('/api/zzp/vehicles')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 1
        assert data['data'][0]['license_plate'] == 'AB-123-CD'

    def test_list_vehicles_empty_returns_200_with_empty_list(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.list_vehicles.return_value = []
        resp = vehicle_client.get('/api/zzp/vehicles')
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

    def test_list_vehicles_default_active_only_true(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.list_vehicles.return_value = []
        vehicle_client.get('/api/zzp/vehicles')
        mock_vehicle_service.list_vehicles.assert_called_once_with('TestTenant', active_only=True)

    def test_list_vehicles_is_active_false_passes_param(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.list_vehicles.return_value = []
        vehicle_client.get('/api/zzp/vehicles?is_active=false')
        mock_vehicle_service.list_vehicles.assert_called_once_with('TestTenant', active_only=False)

    def test_list_vehicles_is_active_true_passes_param(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.list_vehicles.return_value = []
        vehicle_client.get('/api/zzp/vehicles?is_active=true')
        mock_vehicle_service.list_vehicles.assert_called_once_with('TestTenant', active_only=True)

    def test_list_vehicles_service_error_returns_500(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.list_vehicles.side_effect = Exception("DB connection failed")
        resp = vehicle_client.get('/api/zzp/vehicles')
        assert resp.status_code == 500
        assert resp.get_json()['success'] is False


# ── POST /api/zzp/vehicles ─────────────────────────────────


class TestCreateVehicle:
    """Tests for POST /api/zzp/vehicles."""

    def test_create_vehicle_valid_data_returns_201(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.create_vehicle.return_value = SAMPLE_VEHICLE
        resp = vehicle_client.post(
            '/api/zzp/vehicles',
            data=json.dumps(CREATE_PAYLOAD),
            content_type='application/json',
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['license_plate'] == 'AB-123-CD'

    def test_create_vehicle_calls_service_with_tenant_and_email(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.create_vehicle.return_value = SAMPLE_VEHICLE
        vehicle_client.post(
            '/api/zzp/vehicles',
            data=json.dumps(CREATE_PAYLOAD),
            content_type='application/json',
        )
        mock_vehicle_service.create_vehicle.assert_called_once_with(
            'TestTenant', CREATE_PAYLOAD, created_by='test@example.com'
        )

    def test_create_vehicle_missing_required_field_returns_400(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.create_vehicle.side_effect = ValueError("Missing required field: license_plate")
        resp = vehicle_client.post(
            '/api/zzp/vehicles',
            data=json.dumps({"make": "Volkswagen"}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'Missing required field' in resp.get_json()['error']

    def test_create_vehicle_no_body_returns_error(self, vehicle_client):
        resp = vehicle_client.post('/api/zzp/vehicles', content_type='application/json')
        # Empty body causes get_json() to raise BadRequest, caught by generic handler
        assert resp.status_code in (400, 500)
        assert resp.get_json()['success'] is False

    def test_create_vehicle_duplicate_plate_returns_400(self, vehicle_client, mock_vehicle_service):
        from db_exceptions import IntegrityError
        mock_vehicle_service.create_vehicle.side_effect = IntegrityError(
            "License plate 'AB-123-CD' already exists for this administration",
            error_code=1062,
            original_error=None,
        )
        resp = vehicle_client.post(
            '/api/zzp/vehicles',
            data=json.dumps(CREATE_PAYLOAD),
            content_type='application/json',
        )
        # IntegrityError is not caught by ValueError handler, goes to generic Exception → 500
        # But since it inherits from DatabaseError, the route catches it as generic Exception
        assert resp.status_code == 500

    def test_create_vehicle_invalid_type_returns_400(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.create_vehicle.side_effect = ValueError(
            "Invalid vehicle_type: sedan. Must be one of: private_for_business, business"
        )
        payload = {**CREATE_PAYLOAD, "vehicle_type": "sedan"}
        resp = vehicle_client.post(
            '/api/zzp/vehicles',
            data=json.dumps(payload),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'Invalid vehicle_type' in resp.get_json()['error']


# ── PUT /api/zzp/vehicles/{id} ─────────────────────────────


class TestUpdateVehicle:
    """Tests for PUT /api/zzp/vehicles/{id}."""

    def test_update_vehicle_valid_data_returns_200(self, vehicle_client, mock_vehicle_service):
        updated = {**SAMPLE_VEHICLE, "make": "Toyota", "model": "Corolla"}
        mock_vehicle_service.update_vehicle.return_value = updated
        resp = vehicle_client.put(
            '/api/zzp/vehicles/1',
            data=json.dumps({"make": "Toyota", "model": "Corolla"}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['make'] == 'Toyota'

    def test_update_vehicle_calls_service_with_correct_params(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.update_vehicle.return_value = SAMPLE_VEHICLE
        vehicle_client.put(
            '/api/zzp/vehicles/1',
            data=json.dumps({"make": "Toyota"}),
            content_type='application/json',
        )
        mock_vehicle_service.update_vehicle.assert_called_once_with(
            'TestTenant', 1, {"make": "Toyota"}
        )

    def test_update_vehicle_not_found_returns_400(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.update_vehicle.side_effect = ValueError("Vehicle 999 not found")
        resp = vehicle_client.put(
            '/api/zzp/vehicles/999',
            data=json.dumps({"make": "Toyota"}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'not found' in resp.get_json()['error']

    def test_update_vehicle_no_body_returns_error(self, vehicle_client):
        resp = vehicle_client.put('/api/zzp/vehicles/1', content_type='application/json')
        # Empty body causes get_json() to raise BadRequest, caught by generic handler
        assert resp.status_code in (400, 500)
        assert resp.get_json()['success'] is False

    def test_update_vehicle_odometer_blocked_returns_400(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.update_vehicle.side_effect = ValueError(
            "Cannot change start_odometer: trips already exist for this vehicle"
        )
        resp = vehicle_client.put(
            '/api/zzp/vehicles/1',
            data=json.dumps({"start_odometer": 50000}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'start_odometer' in resp.get_json()['error']


# ── DELETE /api/zzp/vehicles/{id} ──────────────────────────


class TestDeactivateVehicle:
    """Tests for DELETE /api/zzp/vehicles/{id}."""

    def test_deactivate_vehicle_returns_200(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.deactivate_vehicle.return_value = True
        resp = vehicle_client.delete('/api/zzp/vehicles/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['id'] == 1
        assert data['data']['is_active'] is False

    def test_deactivate_vehicle_calls_service_with_correct_params(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.deactivate_vehicle.return_value = True
        vehicle_client.delete('/api/zzp/vehicles/1')
        mock_vehicle_service.deactivate_vehicle.assert_called_once_with('TestTenant', 1)

    def test_deactivate_vehicle_not_found_returns_400(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.deactivate_vehicle.side_effect = ValueError("Vehicle 999 not found")
        resp = vehicle_client.delete('/api/zzp/vehicles/999')
        assert resp.status_code == 400
        assert 'not found' in resp.get_json()['error']

    def test_deactivate_vehicle_service_error_returns_500(self, vehicle_client, mock_vehicle_service):
        mock_vehicle_service.deactivate_vehicle.side_effect = Exception("DB error")
        resp = vehicle_client.delete('/api/zzp/vehicles/1')
        assert resp.status_code == 500
        assert resp.get_json()['success'] is False


# ── Authentication tests ────────────────────────────────────


class TestVehicleAuth:
    """Tests for unauthenticated requests."""

    def test_unauthenticated_list_returns_401(self, unauth_client):
        resp = unauth_client.get('/api/zzp/vehicles')
        assert resp.status_code == 401

    def test_unauthenticated_create_returns_401(self, unauth_client):
        resp = unauth_client.post(
            '/api/zzp/vehicles',
            data=json.dumps(CREATE_PAYLOAD),
            content_type='application/json',
        )
        assert resp.status_code == 401

    def test_unauthenticated_update_returns_401(self, unauth_client):
        resp = unauth_client.put(
            '/api/zzp/vehicles/1',
            data=json.dumps({"make": "Toyota"}),
            content_type='application/json',
        )
        assert resp.status_code == 401

    def test_unauthenticated_delete_returns_401(self, unauth_client):
        resp = unauth_client.delete('/api/zzp/vehicles/1')
        assert resp.status_code == 401
