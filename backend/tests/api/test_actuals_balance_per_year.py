"""
Tests for actuals-balance per_year=true functionality.

Tests the year-bucketed balance data with year-end closure awareness:
- per_year=true returns one row per (Parent, Reknum, AccountName, jaar)
- closedYears array is populated from year_closure_status
- Closed year balance uses only that year's transactions
- Open year balance is cumulative through that year
- Backward compatibility: no per_year param returns existing format
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


def _make_test_dataframe():
    """Create a test DataFrame mimicking the vw_mutaties cache structure."""
    data = [
        {'Parent': '1000 Assets', 'Reknum': '1010', 'AccountName': 'Bank', 'VW': 'N',
         'Amount': 10000.0, 'jaar': 2023, 'administration': 'TestTenant'},
        {'Parent': '1000 Assets', 'Reknum': '1020', 'AccountName': 'Cash', 'VW': 'N',
         'Amount': 5000.0, 'jaar': 2023, 'administration': 'TestTenant'},
        {'Parent': '2000 Liabilities', 'Reknum': '2010', 'AccountName': 'Loan', 'VW': 'N',
         'Amount': -8000.0, 'jaar': 2023, 'administration': 'TestTenant'},
        {'Parent': '1000 Assets', 'Reknum': '1010', 'AccountName': 'Bank', 'VW': 'N',
         'Amount': 15000.0, 'jaar': 2024, 'administration': 'TestTenant'},
        {'Parent': '1000 Assets', 'Reknum': '1020', 'AccountName': 'Cash', 'VW': 'N',
         'Amount': 3000.0, 'jaar': 2024, 'administration': 'TestTenant'},
        {'Parent': '2000 Liabilities', 'Reknum': '2010', 'AccountName': 'Loan', 'VW': 'N',
         'Amount': -2000.0, 'jaar': 2024, 'administration': 'TestTenant'},
        {'Parent': '1000 Assets', 'Reknum': '1010', 'AccountName': 'Bank', 'VW': 'N',
         'Amount': 20000.0, 'jaar': 2025, 'administration': 'TestTenant'},
        # P&L account (should be excluded from balance)
        {'Parent': '4000 Costs', 'Reknum': '4010', 'AccountName': 'Office', 'VW': 'Y',
         'Amount': 1200.0, 'jaar': 2024, 'administration': 'TestTenant'},
    ]
    return pd.DataFrame(data)


def _create_jwt_token(email, tenants, roles=None):
    """Helper to create a mock JWT token"""
    payload = {
        "email": email,
        "custom:tenants": tenants if isinstance(tenants, list) else [tenants],
        "cognito:groups": roles or []
    }
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return f"{header}.{payload_encoded}.mock_signature"


def _get_auth_headers(tenant='TestTenant'):
    """Helper to create auth headers"""
    token = _create_jwt_token("test@example.com", [tenant], ["Finance_CRUD"])
    return {'Authorization': f'Bearer {token}', 'X-Tenant': tenant}


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(actuals_bp, url_prefix='/api/reports')
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestActualsBalancePerYear:
    """Test per_year=true balance endpoint behavior"""

    @patch('actuals_routes._get_closed_years')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_per_year_returns_year_bucketed_data(self, _r, mock_cache_fn, _db, mock_closed, client):
        """per_year=true returns rows with jaar field"""
        cache = MagicMock(); cache.get_data.return_value = _make_test_dataframe()
        mock_cache_fn.return_value = cache; mock_closed.return_value = []

        resp = client.get('/api/reports/actuals-balance?years=2024,2025&per_year=true&administration=TestTenant',
                          headers=_get_auth_headers())
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        assert 'closedYears' in data
        for rec in data['data']:
            assert 'jaar' in rec
            assert rec['jaar'] in [2024, 2025]

    @patch('actuals_routes._get_closed_years')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_closed_years_populated(self, _r, mock_cache_fn, _db, mock_closed, client):
        """closedYears array comes from year_closure_status"""
        cache = MagicMock(); cache.get_data.return_value = _make_test_dataframe()
        mock_cache_fn.return_value = cache; mock_closed.return_value = [2023, 2024]

        resp = client.get('/api/reports/actuals-balance?years=2024,2025&per_year=true&administration=TestTenant',
                          headers=_get_auth_headers())
        assert resp.status_code == 200
        assert json.loads(resp.data)['closedYears'] == [2023, 2024]

    @patch('actuals_routes._get_closed_years')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_closed_year_excludes_prior(self, _r, mock_cache_fn, _db, mock_closed, client):
        """Closed year balance = only that year's transactions"""
        cache = MagicMock(); cache.get_data.return_value = _make_test_dataframe()
        mock_cache_fn.return_value = cache; mock_closed.return_value = [2023, 2024]

        resp = client.get('/api/reports/actuals-balance?years=2024&per_year=true&administration=TestTenant',
                          headers=_get_auth_headers())
        data = json.loads(resp.data)
        bank = [r for r in data['data'] if r['Reknum'] == '1010' and r['jaar'] == 2024]
        assert len(bank) == 1
        assert bank[0]['Amount'] == 15000.0  # Only 2024, not 2023+2024

    @patch('actuals_routes._get_closed_years')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_open_year_is_cumulative(self, _r, mock_cache_fn, _db, mock_closed, client):
        """Open year balance = cumulative from start through that year"""
        cache = MagicMock(); cache.get_data.return_value = _make_test_dataframe()
        mock_cache_fn.return_value = cache; mock_closed.return_value = [2023]  # 2024 is open

        resp = client.get('/api/reports/actuals-balance?years=2024&per_year=true&administration=TestTenant',
                          headers=_get_auth_headers())
        data = json.loads(resp.data)
        bank = [r for r in data['data'] if r['Reknum'] == '1010' and r['jaar'] == 2024]
        assert len(bank) == 1
        assert bank[0]['Amount'] == 25000.0  # 2023 (10000) + 2024 (15000)

    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_backward_compat_no_per_year(self, _r, mock_cache_fn, _db, client):
        """Without per_year, returns aggregated format without closedYears or jaar"""
        cache = MagicMock(); cache.get_data.return_value = _make_test_dataframe()
        mock_cache_fn.return_value = cache

        resp = client.get('/api/reports/actuals-balance?years=2024&administration=TestTenant',
                          headers=_get_auth_headers())
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'closedYears' not in data
        for rec in data['data']:
            assert 'jaar' not in rec

    @patch('actuals_routes._get_closed_years')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_excludes_pl_accounts(self, _r, mock_cache_fn, _db, mock_closed, client):
        """per_year mode only returns VW=N, not VW=Y"""
        cache = MagicMock(); cache.get_data.return_value = _make_test_dataframe()
        mock_cache_fn.return_value = cache; mock_closed.return_value = []

        resp = client.get('/api/reports/actuals-balance?years=2024&per_year=true&administration=TestTenant',
                          headers=_get_auth_headers())
        data = json.loads(resp.data)
        assert all(not r['Parent'].startswith('4') for r in data['data'])

    @patch('actuals_routes._get_closed_years')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_filters_zero_amounts(self, _r, mock_cache_fn, _db, mock_closed, client):
        """Zero-amount records are excluded"""
        df = _make_test_dataframe()
        df = pd.concat([df, pd.DataFrame([{
            'Parent': '3000 Equity', 'Reknum': '3010', 'AccountName': 'Equity',
            'VW': 'N', 'Amount': 0.0, 'jaar': 2024, 'administration': 'TestTenant'
        }])], ignore_index=True)
        cache = MagicMock(); cache.get_data.return_value = df
        mock_cache_fn.return_value = cache; mock_closed.return_value = []

        resp = client.get('/api/reports/actuals-balance?years=2024&per_year=true&administration=TestTenant',
                          headers=_get_auth_headers())
        data = json.loads(resp.data)
        assert all(r['Amount'] != 0 for r in data['data'])


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
