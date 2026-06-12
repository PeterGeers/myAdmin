"""
Unit tests for Tenant Function Admin API routes.

Tests the POST /api/tenant/functions endpoint for toggling optional functions.

Requirements: 5.3, 5.5, 5.7
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.tenant_function_routes import tenant_function_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal Flask app with the tenant_function blueprint."""
    app = Flask(__name__)
    app.register_blueprint(tenant_function_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _admin_auth_mocks():
    """Patch stack for an authenticated Tenant_Admin user."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('admin@test.com', ['Tenant_Admin'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']),
        patch('auth.tenant_context.get_user_tenants', return_value=['TestTenant']),
        patch('auth.tenant_context.is_tenant_admin', return_value=True),
        patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'),
    ]


def _non_admin_auth_mocks():
    """Patch stack for an authenticated non-admin user (Finance_CRUD only)."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('user@test.com', ['Finance_CRUD'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Finance_CRUD']),
        patch('auth.tenant_context.get_user_tenants', return_value=['TestTenant']),
        patch('auth.tenant_context.is_tenant_admin', return_value=False),
        patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'),
    ]


def _headers():
    """Standard request headers for authenticated requests."""
    return {
        'Authorization': 'Bearer fake-jwt-token',
        'X-Tenant': 'TestTenant',
        'Content-Type': 'application/json',
    }


# ---------------------------------------------------------------------------
# TestTenantFunctionRoutes
# ---------------------------------------------------------------------------

class TestTenantFunctionRoutes:
    """Unit tests for tenant function toggle API endpoints."""

    # ------------------------------------------------------------------
    # Test 1: Non-admin user gets 403 on POST
    # Validates: Requirement 5.3
    # ------------------------------------------------------------------
    def test_non_admin_returns_403(self, client):
        """Non-Tenant_Admin user attempting toggle receives HTTP 403."""
        mocks = _non_admin_auth_mocks() + [
            patch('routes.tenant_function_routes.DatabaseManager'),
        ]

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.post(
                '/api/tenant/functions',
                json={'function_name': 'assets', 'is_active': False},
                headers=_headers(),
            )
            data = resp.get_json()
            assert resp.status_code == 403
            assert data['success'] is False
            assert 'Access denied' in data['error']

    # ------------------------------------------------------------------
    # Test 2: Missing request body returns 400
    # Validates: Requirement 5.7
    # ------------------------------------------------------------------
    def test_missing_request_body_returns_400(self, client):
        """POST with no JSON body returns 400 with descriptive message."""
        mocks = _admin_auth_mocks() + [
            patch('routes.tenant_function_routes.DatabaseManager'),
        ]

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.post(
                '/api/tenant/functions',
                headers={
                    'Authorization': 'Bearer fake-jwt-token',
                    'X-Tenant': 'TestTenant',
                },
                # No json body, no Content-Type: application/json
            )
            data = resp.get_json()
            assert resp.status_code == 400
            assert data['success'] is False
            assert 'function_name' in data['error']
            assert 'is_active' in data['error']

    # ------------------------------------------------------------------
    # Test 3: Invalid function name returns 400 with valid names
    # Validates: Requirement 5.4 (referenced by 5.5 context)
    # ------------------------------------------------------------------
    def test_invalid_function_name_returns_400(self, client):
        """POST with unknown function_name returns 400 listing valid names."""
        mocks = _admin_auth_mocks() + [
            patch('routes.tenant_function_routes.DatabaseManager'),
        ]

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.post(
                '/api/tenant/functions',
                json={'function_name': 'nonexistent', 'is_active': True},
                headers=_headers(),
            )
            data = resp.get_json()
            assert resp.status_code == 400
            assert data['success'] is False
            assert 'assets' in data['error']
            assert 'str_channel_revenue' in data['error']
            assert 'generate_invoice' in data['error']

    # ------------------------------------------------------------------
    # Test 4: Parent module inactive during toggle returns 400
    # Validates: Requirement 5.5
    # ------------------------------------------------------------------
    def test_parent_module_inactive_returns_400(self, client):
        """POST toggle when parent module is inactive returns 400."""
        mock_db_instance = MagicMock()
        mocks = _admin_auth_mocks() + [
            patch('routes.tenant_function_routes.DatabaseManager',
                  return_value=mock_db_instance),
            patch('routes.tenant_function_routes.has_module', return_value=False),
        ]

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = client.post(
                '/api/tenant/functions',
                json={'function_name': 'assets', 'is_active': False},
                headers=_headers(),
            )
            data = resp.get_json()
            assert resp.status_code == 400
            assert data['success'] is False
            assert 'FIN' in data['error']
            assert 'activated first' in data['error']

    # ------------------------------------------------------------------
    # Test 5: Successful toggle returns updated state
    # Validates: Requirement 5.5 (happy path)
    # ------------------------------------------------------------------
    def test_successful_toggle_returns_updated_state(self, client):
        """Successful POST toggle returns 200 with function_name and is_active."""
        mock_db_instance = MagicMock()
        mock_service = MagicMock()
        mock_service.set_function_state.return_value = {
            'success': True,
            'data': {
                'function_name': 'assets',
                'is_active': False,
            },
        }

        mocks = _admin_auth_mocks() + [
            patch('routes.tenant_function_routes.DatabaseManager',
                  return_value=mock_db_instance),
            patch('routes.tenant_function_routes.has_module', return_value=True),
            patch('routes.tenant_function_routes._get_service',
                  return_value=mock_service),
        ]

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             mocks[6], mocks[7]:
            resp = client.post(
                '/api/tenant/functions',
                json={'function_name': 'assets', 'is_active': False},
                headers=_headers(),
            )
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['success'] is True
            assert data['data']['function_name'] == 'assets'
            assert data['data']['is_active'] is False
