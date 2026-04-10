"""
Integration tests for cache invalidation flow and new endpoint parameters.

Tests:
- POST /api/cache/invalidate with actuals_read permission (was SysAdmin)
- GET /api/reports/actuals-balance?per_year=true returns year-bucketed data with closedYears
- GET /api/reports/actuals-profitloss?includeRef=true returns transaction-level data with ReferenceNumber
"""

import pytest
import json
import base64
import pandas as pd
from unittest.mock import patch, MagicMock
from flask import Flask
from actuals_routes import actuals_bp
from routes.cache_routes import cache_bp

ROLE_PATCH = 'auth.role_cache.get_tenant_roles'


def _jwt(email='test@example.com', tenants=None, roles=None):
    payload = {
        "email": email,
        "custom:tenants": tenants or ["TestTenant"],
        "cognito:groups": roles or []
    }
    h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return f"{h}.{p}.mock_signature"


def _headers(tenant='TestTenant'):
    return {
        'Authorization': f'Bearer {_jwt(tenants=[tenant])}',
        'X-Tenant': tenant,
        'Content-Type': 'application/json',
    }


def _make_df():
    """Test DataFrame with balance and P&L data."""
    return pd.DataFrame([
        {'Parent': '1000 Assets', 'Reknum': '1010', 'AccountName': 'Bank', 'VW': 'N',
         'Amount': 10000.0, 'jaar': 2024, 'administration': 'TestTenant'},
        {'Parent': '1000 Assets', 'Reknum': '1010', 'AccountName': 'Bank', 'VW': 'N',
         'Amount': 15000.0, 'jaar': 2025, 'administration': 'TestTenant'},
        {'Parent': '4000 Costs', 'Reknum': '4010', 'AccountName': 'Office', 'VW': 'Y',
         'Amount': 500.0, 'jaar': 2024, 'kwartaal': 1, 'maand': 1,
         'ReferenceNumber': 'INV-001', 'administration': 'TestTenant'},
        {'Parent': '4000 Costs', 'Reknum': '4010', 'AccountName': 'Office', 'VW': 'Y',
         'Amount': 300.0, 'jaar': 2024, 'kwartaal': 2, 'maand': 4,
         'ReferenceNumber': 'INV-002', 'administration': 'TestTenant'},
    ])


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(actuals_bp, url_prefix='/api/reports')
    app.register_blueprint(cache_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestCacheInvalidationPermission:
    """Test that cache invalidation now works with actuals_read permission."""

    @patch('routes.cache_routes.invalidate_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_invalidate_with_actuals_read(self, _roles, mock_invalidate, client):
        """User with actuals_read (via Finance_CRUD) can invalidate cache."""
        resp = client.post('/api/cache/invalidate', headers=_headers())
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        mock_invalidate.assert_called_once()

    @patch('routes.cache_routes.invalidate_cache')
    @patch(ROLE_PATCH, return_value=['Finance_Read'])
    def test_invalidate_with_finance_read(self, _roles, mock_invalidate, client):
        """User with Finance_Read role (has actuals_read) can invalidate cache."""
        resp = client.post('/api/cache/invalidate', headers=_headers())
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_invalidate_unauthenticated(self, client):
        """Unauthenticated user is rejected."""
        resp = client.post('/api/cache/invalidate')
        assert resp.status_code in [401, 403]

    @patch(ROLE_PATCH, return_value=['STR_Read'])
    def test_invalidate_without_actuals_read(self, _roles, client):
        """User without actuals_read permission is rejected."""
        resp = client.post('/api/cache/invalidate', headers=_headers())
        assert resp.status_code == 403


class TestBalancePerYearIntegration:
    """Test actuals-balance?per_year=true returns year-bucketed data with closedYears."""

    @patch('actuals_routes._get_closed_years', return_value=[2024])
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_per_year_response_shape(self, _r, mock_cache_fn, _db, _closed, client):
        cache = MagicMock(); cache.get_data.return_value = _make_df()
        mock_cache_fn.return_value = cache

        resp = client.get(
            '/api/reports/actuals-balance?years=2024,2025&per_year=true&administration=TestTenant',
            headers=_headers()
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        assert 'closedYears' in data
        assert isinstance(data['closedYears'], list)
        assert 2024 in data['closedYears']
        for rec in data['data']:
            assert 'jaar' in rec


class TestProfitLossIncludeRefIntegration:
    """Test actuals-profitloss?includeRef=true returns ReferenceNumber."""

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_include_ref_response_shape(self, _r, mock_cache_fn, _db, _schema, client):
        cache = MagicMock(); cache.get_data.return_value = _make_df()
        mock_cache_fn.return_value = cache

        resp = client.get(
            '/api/reports/actuals-profitloss?years=2024&includeRef=true&administration=TestTenant',
            headers=_headers()
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        for rec in data['data']:
            assert 'ReferenceNumber' in rec
        refs = [r['ReferenceNumber'] for r in data['data']]
        assert 'INV-001' in refs
        assert 'INV-002' in refs


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
