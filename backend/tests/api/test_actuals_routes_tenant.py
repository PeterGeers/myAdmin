"""
Integration tests for actuals routes with tenant filtering

Tests the tenant filtering implementation for:
- /api/reports/actuals-balance
- /api/reports/actuals-profitloss

These tests verify that:
1. Unauthenticated requests are rejected
2. Users cannot access administrations outside their tenant list
3. Authorized users can access their own tenant data
4. Multi-tenant users can access all their tenants
"""

import pytest
import json
import base64
import pandas as pd
from unittest.mock import patch, MagicMock
from flask import Flask
from actuals_routes import actuals_bp

# Patch target for tenant role resolution (imported locally in cognito_utils)
ROLE_PATCH = 'auth.role_cache.get_tenant_roles'


def _make_test_dataframe(administrations=None):
    """Create a test DataFrame mimicking the vw_mutaties cache structure."""
    if administrations is None:
        administrations = ['GoodwinSolutions']
    data = []
    for admin in administrations:
        data.extend([
            {'Parent': '1000 Assets', 'Reknum': '1010', 'AccountName': 'Bank', 'VW': 'N',
             'Amount': 10000.0, 'jaar': 2025, 'administration': admin},
            {'Parent': '4000 Revenue', 'Reknum': '4010', 'AccountName': 'Sales', 'VW': 'Y',
             'Amount': 5000.0, 'jaar': 2025, 'kwartaal': 1, 'maand': 1,
             'ReferenceNumber': 'REF001', 'administration': admin},
        ])
    return pd.DataFrame(data)


def _create_jwt_token(email, tenants, roles=None):
    """Helper to create a mock JWT token."""
    payload = {
        "email": email,
        "custom:tenants": tenants if isinstance(tenants, list) else [tenants],
        "cognito:groups": roles or []
    }
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256"}).encode()
    ).decode().rstrip('=')
    payload_encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip('=')
    return f"{header}.{payload_encoded}.mock_signature"


def _get_auth_headers(tenant='GoodwinSolutions'):
    """Helper to create auth headers for a single-tenant user."""
    token = _create_jwt_token("test@example.com", [tenant], ["Finance_CRUD"])
    return {'Authorization': f'Bearer {token}', 'X-Tenant': tenant}


def _get_multi_tenant_headers(tenants, active_tenant=None):
    """Helper to create auth headers for a multi-tenant user."""
    active = active_tenant or tenants[0]
    token = _create_jwt_token("test@example.com", tenants, ["Finance_CRUD"])
    return {'Authorization': f'Bearer {token}', 'X-Tenant': active}


@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(actuals_bp, url_prefix='/api/reports')
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestActualsRoutesTenantFiltering:
    """Test tenant filtering for actuals-balance route."""

    def test_actuals_balance_requires_tenant(self, client):
        """Unauthenticated request is rejected."""
        response = client.get('/api/reports/actuals-balance')
        assert response.status_code in [401, 403]

    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_balance_validates_administration_access(self, _r, client):
        """User cannot access an administration outside their tenant list."""
        token = _create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        response = client.get(
            '/api/reports/actuals-balance?administration=PeterPrive',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data

    @patch('actuals_routes._get_closed_years', return_value=[])
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_balance_allows_authorized_tenant(
        self, _r, mock_cache_fn, _db, _closed, client
    ):
        """Authorized user can access their own tenant data."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(['GoodwinSolutions'])
        mock_cache_fn.return_value = cache

        response = client.get(
            '/api/reports/actuals-balance?administration=GoodwinSolutions',
            headers=_get_auth_headers('GoodwinSolutions')
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('actuals_routes._get_closed_years', return_value=[])
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_balance_defaults_to_current_tenant(
        self, _r, mock_cache_fn, _db, _closed, client
    ):
        """Without administration param, defaults to X-Tenant header value."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(['GoodwinSolutions'])
        mock_cache_fn.return_value = cache

        response = client.get(
            '/api/reports/actuals-balance',
            headers=_get_auth_headers('GoodwinSolutions')
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('actuals_routes._get_closed_years', return_value=[])
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_balance_multi_tenant_user(
        self, _r, mock_cache_fn, _db, _closed, client
    ):
        """Multi-tenant user can access each of their tenants."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(
            ['GoodwinSolutions', 'PeterPrive']
        )
        mock_cache_fn.return_value = cache

        headers = _get_multi_tenant_headers(
            ['GoodwinSolutions', 'PeterPrive'], 'GoodwinSolutions'
        )
        resp1 = client.get(
            '/api/reports/actuals-balance?administration=GoodwinSolutions',
            headers=headers
        )
        assert resp1.status_code == 200

        headers2 = _get_multi_tenant_headers(
            ['GoodwinSolutions', 'PeterPrive'], 'PeterPrive'
        )
        resp2 = client.get(
            '/api/reports/actuals-balance?administration=PeterPrive',
            headers=headers2
        )
        assert resp2.status_code == 200


class TestActualsProfitLossTenantFiltering:
    """Test tenant filtering for actuals-profitloss route."""

    def test_actuals_profitloss_requires_tenant(self, client):
        """Unauthenticated request is rejected."""
        response = client.get('/api/reports/actuals-profitloss')
        assert response.status_code in [401, 403]

    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_profitloss_validates_administration_access(self, _r, client):
        """User cannot access an administration outside their tenant list."""
        token = _create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        response = client.get(
            '/api/reports/actuals-profitloss?administration=PeterPrive',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_profitloss_allows_authorized_tenant(
        self, _r, mock_cache_fn, _db, _validate, client
    ):
        """Authorized user can access their own tenant data."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(['GoodwinSolutions'])
        mock_cache_fn.return_value = cache

        response = client.get(
            '/api/reports/actuals-profitloss?administration=GoodwinSolutions',
            headers=_get_auth_headers('GoodwinSolutions')
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_profitloss_defaults_to_current_tenant(
        self, _r, mock_cache_fn, _db, _validate, client
    ):
        """Without administration param, defaults to X-Tenant header value."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(['GoodwinSolutions'])
        mock_cache_fn.return_value = cache

        response = client.get(
            '/api/reports/actuals-profitloss',
            headers=_get_auth_headers('GoodwinSolutions')
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_profitloss_multi_tenant_user(
        self, _r, mock_cache_fn, _db, _validate, client
    ):
        """Multi-tenant user can access each of their tenants."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(
            ['GoodwinSolutions', 'PeterPrive']
        )
        mock_cache_fn.return_value = cache

        headers = _get_multi_tenant_headers(
            ['GoodwinSolutions', 'PeterPrive'], 'GoodwinSolutions'
        )
        resp1 = client.get(
            '/api/reports/actuals-profitloss?administration=GoodwinSolutions',
            headers=headers
        )
        assert resp1.status_code == 200

        headers2 = _get_multi_tenant_headers(
            ['GoodwinSolutions', 'PeterPrive'], 'PeterPrive'
        )
        resp2 = client.get(
            '/api/reports/actuals-profitloss?administration=PeterPrive',
            headers=headers2
        )
        assert resp2.status_code == 200

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_actuals_profitloss_filters_cached_data_by_tenant(
        self, _r, mock_cache_fn, _db, _validate, client
    ):
        """When administration=all, cached data is filtered to user's tenants only."""
        cache = MagicMock()
        cache.get_data.return_value = _make_test_dataframe(
            ['GoodwinSolutions', 'PeterPrive', 'OtherTenant']
        )
        mock_cache_fn.return_value = cache

        # User only has access to GoodwinSolutions
        response = client.get(
            '/api/reports/actuals-profitloss?administration=all',
            headers=_get_auth_headers('GoodwinSolutions')
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        # All returned records should belong to user's tenants only
        for record in data['data']:
            assert record.get('administration', 'GoodwinSolutions') in ['GoodwinSolutions']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
