"""
API tests for asset_routes.py

Tests asset management endpoints including auth enforcement,
listing, creation, retrieval, update, and deletion.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for asset endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Finance_CRUD']):
        mock_creds.return_value = ('test@example.com', ['Finance_CRUD'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestAssetAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_list_assets_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list assets should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/assets')
        assert response.status_code in (401, 403)

    def test_create_asset_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create asset should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/assets', json={
                'description': 'Test Asset',
                'ledger_account': '3060',
                'purchase_date': '2024-01-01',
                'purchase_amount': 10000
            })
        assert response.status_code in (401, 403)

    def test_get_asset_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get asset should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/assets/1')
        assert response.status_code in (401, 403)

    def test_delete_asset_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to delete asset should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.delete('/api/assets/1')
        assert response.status_code in (401, 403)

    def test_reports_register_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to asset register should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/assets/reports/register')
        assert response.status_code in (401, 403)


# ============================================================================
# List Assets Tests
# ============================================================================


class TestListAssets:
    """Tests for GET /api/assets."""

    @patch('routes.asset_routes.get_current_tenant', return_value='test-tenant')
    @patch('routes.asset_routes._get_service')
    def test_list_assets_success(self, mock_get_service, mock_tenant,
                                 client, finance_auth):
        """Authenticated user can list assets."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_assets.return_value = [
            {'id': 1, 'description': 'Laptop', 'purchase_amount': 1500,
             'book_value': 1200, 'status': 'active'}
        ]

        response = client.get(
            '/api/assets',
            headers=finance_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1

    @patch('routes.asset_routes.get_current_tenant', return_value=None)
    def test_list_assets_no_tenant_returns_400(self, mock_tenant,
                                               client, finance_auth):
        """Request without tenant returns 400."""
        response = client.get(
            '/api/assets',
            headers=finance_auth
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


# ============================================================================
# Create Asset Tests
# ============================================================================


class TestCreateAsset:
    """Tests for POST /api/assets."""

    @patch('routes.asset_routes.get_current_tenant', return_value='test-tenant')
    @patch('routes.asset_routes._get_service')
    def test_create_asset_missing_fields_returns_400(self, mock_get_service,
                                                     mock_tenant,
                                                     client, finance_auth):
        """Creating asset without required fields returns 400."""
        response = client.post(
            '/api/assets',
            headers=finance_auth,
            json={'description': 'Test Asset'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Missing required field' in data['error']

    @patch('routes.asset_routes.get_current_tenant', return_value='test-tenant')
    @patch('routes.asset_routes._get_service')
    def test_create_asset_success(self, mock_get_service, mock_tenant,
                                  client, finance_auth):
        """Valid asset creation succeeds."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_asset.return_value = {
            'success': True, 'asset_id': 1
        }

        response = client.post(
            '/api/assets',
            headers=finance_auth,
            json={
                'description': 'Toyota Yaris 2024',
                'ledger_account': '3060',
                'purchase_date': '2024-06-15',
                'purchase_amount': 25000.00
            }
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Get Single Asset Tests
# ============================================================================


class TestGetAsset:
    """Tests for GET /api/assets/<id>."""

    @patch('routes.asset_routes.get_current_tenant', return_value='test-tenant')
    @patch('routes.asset_routes._get_service')
    def test_get_nonexistent_asset_returns_404(self, mock_get_service,
                                               mock_tenant,
                                               client, finance_auth):
        """Getting non-existent asset returns 404."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_asset.return_value = None

        response = client.get(
            '/api/assets/9999',
            headers=finance_auth
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data

    @patch('routes.asset_routes.get_current_tenant', return_value='test-tenant')
    @patch('routes.asset_routes._get_service')
    def test_get_asset_success(self, mock_get_service, mock_tenant,
                               client, finance_auth):
        """Getting existing asset returns asset data."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_asset.return_value = {
            'id': 1, 'description': 'Laptop',
            'purchase_amount': 1500, 'book_value': 1200
        }

        response = client.get(
            '/api/assets/1',
            headers=finance_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['asset']['id'] == 1
