"""
Integration tests for function_guard on actual routes.

Tests the function_guard decorator behaviour via Flask test_client
using the asset_bp blueprint as the test target.

Requirements: 3.1, 3.2, 3.3, 3.4
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import json
import base64
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.asset_routes import asset_bp


def _make_jwt_token(email='admin@test.com', groups=None, tenants=None):
    """Create a fake JWT token with the given claims."""
    if groups is None:
        groups = ['Tenant_Admin', 'Finance_CRUD']
    if tenants is None:
        tenants = ['TestTenant']

    header = base64.urlsafe_b64encode(json.dumps({'alg': 'HS256'}).encode()).rstrip(b'=').decode()
    payload_data = {
        'email': email,
        'cognito:groups': groups,
        'custom:tenants': json.dumps(tenants),
        'sub': 'user-123',
        'exp': 9999999999,
    }
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b'=').decode()
    signature = base64.urlsafe_b64encode(b'fakesig').rstrip(b'=').decode()
    return f'{header}.{payload}.{signature}'


@pytest.fixture
def app():
    """Create a Flask app with asset_bp registered for integration testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(asset_bp)
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Headers with a valid JWT token for a Tenant_Admin with Finance_CRUD access."""
    token = _make_jwt_token()
    return {
        'Authorization': f'Bearer {token}',
        'X-Tenant': 'TestTenant',
    }


class TestGuardBlocksWhenFunctionDisabled:
    """Req 3.1: Guard returns 403 when function is disabled for tenant."""

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin', 'Finance_CRUD'])
    def test_guard_blocks_when_function_disabled(
        self, mock_roles, mock_db_class, client, auth_headers
    ):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # has_module returns True (FIN module is active)
        # get_function_state query returns disabled
        mock_db.execute_query = MagicMock(side_effect=[
            [{'is_active': True}],    # has_module check in function_guard
            [{'is_active': False}],   # get_function_state in function_guard
        ])

        response = client.get('/api/assets', headers=auth_headers)

        assert response.status_code == 403
        data = response.get_json()
        assert data['success'] is False
        assert data['error'] == "Function 'assets' is disabled for this tenant"

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin', 'Finance_CRUD'])
    def test_guard_blocks_post_when_function_disabled(
        self, mock_roles, mock_db_class, client, auth_headers
    ):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # has_module returns True, get_function_state returns disabled
        mock_db.execute_query = MagicMock(side_effect=[
            [{'is_active': True}],    # has_module in function_guard
            [{'is_active': False}],   # get_function_state
        ])

        response = client.post(
            '/api/assets',
            headers=auth_headers,
            json={'description': 'Test', 'ledger_account': '3060',
                  'purchase_date': '2024-01-01', 'purchase_amount': 1000}
        )

        assert response.status_code == 403
        data = response.get_json()
        assert "disabled" in data['error']


class TestGuardPassesWhenFunctionEnabled:
    """Req 3.2: Guard passes when function is enabled for the tenant."""

    @patch('routes.asset_routes._get_service')
    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin', 'Finance_CRUD'])
    def test_guard_passes_when_function_enabled(
        self, mock_roles, mock_db_class, mock_get_service, client, auth_headers
    ):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # has_module returns True, get_function_state returns True
        mock_db.execute_query = MagicMock(side_effect=[
            [{'is_active': True}],    # has_module in function_guard
            [{'is_active': True}],    # get_function_state in function_guard
        ])

        # Mock the service layer to return some data
        mock_service_instance = MagicMock()
        mock_service_instance.get_assets.return_value = [
            {'id': 1, 'description': 'Test Asset', 'purchase_amount': 1000, 'book_value': 800}
        ]
        mock_get_service.return_value = mock_service_instance

        response = client.get('/api/assets', headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] == 1


class TestGuardReturnsModuleError:
    """Req 3.3, 3.4: Guard returns module-specific 403 when parent module is inactive."""

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin', 'Finance_CRUD'])
    def test_guard_returns_module_error_when_module_inactive(
        self, mock_roles, mock_db_class, client, auth_headers
    ):
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # has_module returns empty (module inactive)
        mock_db.execute_query = MagicMock(return_value=[])

        response = client.get('/api/assets', headers=auth_headers)

        assert response.status_code == 403
        data = response.get_json()
        assert data['success'] is False
        assert data['error'] == "Module 'FIN' is not active for this tenant"

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin', 'Finance_CRUD'])
    def test_module_error_takes_priority_over_function_check(
        self, mock_roles, mock_db_class, client, auth_headers
    ):
        """When module is inactive, the function state should never be checked."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        # has_module returns empty (module inactive)
        mock_db.execute_query = MagicMock(return_value=[])

        response = client.get('/api/assets', headers=auth_headers)

        assert response.status_code == 403
        data = response.get_json()
        # Should mention module, not function
        assert "Module" in data['error']
        assert "Function" not in data['error']


class TestGuardReturnsTenantError:
    """Req 3.5: Guard returns 403 when tenant context is missing."""

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin', 'Finance_CRUD'])
    def test_guard_returns_tenant_error_when_no_tenant(
        self, mock_roles, mock_db_class, client
    ):
        """Without X-Tenant header and no tenant in JWT, guard rejects."""
        # JWT with no tenants claim
        token = _make_jwt_token(tenants=[])
        headers = {
            'Authorization': f'Bearer {token}',
            # No X-Tenant header
        }

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        response = client.get('/api/assets', headers=headers)

        # tenant_required should block before function_guard is reached
        assert response.status_code == 403
