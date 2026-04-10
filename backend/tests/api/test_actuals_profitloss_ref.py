"""
Tests for actuals-profitloss includeRef=true functionality.

Tests that includeRef=true returns individual transactions with ReferenceNumber,
and that without includeRef the response is grouped (no ReferenceNumber).
"""

import pytest
import json
import base64
import pandas as pd
from unittest.mock import patch, MagicMock
from flask import Flask
from actuals_routes import actuals_bp

ROLE_PATCH = 'auth.role_cache.get_tenant_roles'


def _make_pl_dataframe():
    """Create a test DataFrame with P&L data including ReferenceNumber."""
    data = [
        {'Parent': '4000 Costs', 'Reknum': '4010', 'AccountName': 'Office',
         'VW': 'Y', 'Amount': 500.0, 'jaar': 2024, 'kwartaal': 1, 'maand': 1,
         'ReferenceNumber': 'INV-001', 'administration': 'TestTenant'},
        {'Parent': '4000 Costs', 'Reknum': '4010', 'AccountName': 'Office',
         'VW': 'Y', 'Amount': 300.0, 'jaar': 2024, 'kwartaal': 1, 'maand': 2,
         'ReferenceNumber': 'INV-002', 'administration': 'TestTenant'},
        {'Parent': '4000 Costs', 'Reknum': '4010', 'AccountName': 'Office',
         'VW': 'Y', 'Amount': 200.0, 'jaar': 2024, 'kwartaal': 2, 'maand': 4,
         'ReferenceNumber': 'INV-003', 'administration': 'TestTenant'},
        {'Parent': '8000 Revenue', 'Reknum': '8010', 'AccountName': 'Sales',
         'VW': 'Y', 'Amount': 5000.0, 'jaar': 2024, 'kwartaal': 1, 'maand': 1,
         'ReferenceNumber': 'REV-001', 'administration': 'TestTenant'},
    ]
    return pd.DataFrame(data)


def _get_auth_headers(tenant='TestTenant'):
    payload = {
        "email": "test@example.com",
        "custom:tenants": [tenant],
        "cognito:groups": ["Finance_CRUD"]
    }
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    token = f"{header}.{payload_encoded}.mock_signature"
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


class TestActualsProfitLossIncludeRef:
    """Test includeRef=true profitloss endpoint behavior"""

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_include_ref_returns_reference_numbers(self, _r, mock_cache_fn, _db, _schema, client):
        """includeRef=true returns rows with ReferenceNumber field"""
        cache = MagicMock(); cache.get_data.return_value = _make_pl_dataframe()
        mock_cache_fn.return_value = cache

        resp = client.get(
            '/api/reports/actuals-profitloss?years=2024&includeRef=true&administration=TestTenant',
            headers=_get_auth_headers()
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

        # Each record should have ReferenceNumber
        for rec in data['data']:
            assert 'ReferenceNumber' in rec
            assert rec['ReferenceNumber'] != ''

        # Should have 4 individual rows (not grouped)
        assert len(data['data']) == 4

    @patch('actuals_routes.validate_response_schema')
    @patch('actuals_routes.DatabaseManager')
    @patch('actuals_routes.get_cache')
    @patch(ROLE_PATCH, return_value=['Finance_CRUD'])
    def test_without_include_ref_is_grouped(self, _r, mock_cache_fn, _db, _schema, client):
        """Without includeRef, response is grouped (no ReferenceNumber column)"""
        cache = MagicMock(); cache.get_data.return_value = _make_pl_dataframe()
        mock_cache_fn.return_value = cache

        resp = client.get(
            '/api/reports/actuals-profitloss?years=2024&administration=TestTenant',
            headers=_get_auth_headers()
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)

        # Should be grouped: Office (4010) has 3 transactions summed into 1 row for 2024
        office_rows = [r for r in data['data'] if r['Reknum'] == '4010']
        assert len(office_rows) == 1
        assert office_rows[0]['Amount'] == 1000.0  # 500 + 300 + 200

        # Records should NOT have ReferenceNumber
        for rec in data['data']:
            assert 'ReferenceNumber' not in rec


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
