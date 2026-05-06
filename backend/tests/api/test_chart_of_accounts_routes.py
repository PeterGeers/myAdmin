"""
API tests for chart_of_accounts_routes.py

Tests chart of accounts CRUD endpoints including auth enforcement,
listing, creation, retrieval, and deletion.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestChartOfAccountsAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_list_accounts_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list accounts should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/chart-of-accounts')
        assert response.status_code in (401, 403)

    def test_create_account_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create account should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/tenant-admin/chart-of-accounts',
                json={'account': '1000', 'accountName': 'Test'}
            )
        assert response.status_code in (401, 403)

    def test_get_account_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get single account should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/chart-of-accounts/1000')
        assert response.status_code in (401, 403)

    def test_delete_account_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to delete account should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.delete('/api/tenant-admin/chart-of-accounts/1000')
        assert response.status_code in (401, 403)


# ============================================================================
# List Accounts Tests
# ============================================================================


class TestListAccounts:
    """Tests for GET /api/tenant-admin/chart-of-accounts."""

    @patch('routes.chart_of_accounts_routes.DatabaseManager')
    @patch('routes.chart_of_accounts_routes.has_fin_module', return_value=True)
    @patch('routes.chart_of_accounts_routes.is_tenant_admin', return_value=True)
    @patch('routes.chart_of_accounts_routes.get_user_tenants', return_value=['test-tenant'])
    @patch('routes.chart_of_accounts_routes.get_current_tenant', return_value='test-tenant')
    def test_list_accounts_success(self, mock_tenant, mock_user_tenants,
                                   mock_is_admin, mock_fin, mock_db_class,
                                   client, mock_auth):
        """Authenticated user can list accounts."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.side_effect = [
            [{'AccountID': 1, 'Account': '1000', 'AccountName': 'Kas',
              'AccountLookup': 'CASH', 'SubParent': '', 'Parent': '',
              'VW': 'N', 'Belastingaangifte': 'Activa',
              'administration': 'test-tenant', 'purpose': None,
              'bank_account': 'false', 'iban': None, 'parameters': None}],
            [{'total': 1}]
        ]

        response = client.get(
            '/api/tenant-admin/chart-of-accounts',
            headers=mock_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['accounts']) == 1


# ============================================================================
# Create Account Tests
# ============================================================================


class TestCreateAccount:
    """Tests for POST /api/tenant-admin/chart-of-accounts."""

    @patch('routes.chart_of_accounts_routes.DatabaseManager')
    @patch('routes.chart_of_accounts_routes.has_fin_module', return_value=True)
    @patch('routes.chart_of_accounts_routes.is_tenant_admin', return_value=True)
    @patch('routes.chart_of_accounts_routes.get_user_tenants', return_value=['test-tenant'])
    @patch('routes.chart_of_accounts_routes.get_current_tenant', return_value='test-tenant')
    def test_create_account_missing_account_number_returns_400(
        self, mock_tenant, mock_user_tenants, mock_is_admin,
        mock_fin, mock_db_class, client, mock_auth
    ):
        """Creating account without account number returns 400."""
        response = client.post(
            '/api/tenant-admin/chart-of-accounts',
            headers=mock_auth,
            json={'accountName': 'Test Account'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('routes.chart_of_accounts_routes.DatabaseManager')
    @patch('routes.chart_of_accounts_routes.has_fin_module', return_value=True)
    @patch('routes.chart_of_accounts_routes.is_tenant_admin', return_value=True)
    @patch('routes.chart_of_accounts_routes.get_user_tenants', return_value=['test-tenant'])
    @patch('routes.chart_of_accounts_routes.get_current_tenant', return_value='test-tenant')
    def test_create_account_missing_name_returns_400(
        self, mock_tenant, mock_user_tenants, mock_is_admin,
        mock_fin, mock_db_class, client, mock_auth
    ):
        """Creating account without name returns 400."""
        response = client.post(
            '/api/tenant-admin/chart-of-accounts',
            headers=mock_auth,
            json={'account': '1000'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


# ============================================================================
# Get Single Account Tests
# ============================================================================


class TestGetAccount:
    """Tests for GET /api/tenant-admin/chart-of-accounts/<account>."""

    @patch('routes.chart_of_accounts_routes.DatabaseManager')
    @patch('routes.chart_of_accounts_routes.has_fin_module', return_value=True)
    @patch('routes.chart_of_accounts_routes.is_tenant_admin', return_value=True)
    @patch('routes.chart_of_accounts_routes.get_user_tenants', return_value=['test-tenant'])
    @patch('routes.chart_of_accounts_routes.get_current_tenant', return_value='test-tenant')
    def test_get_nonexistent_account_returns_404(
        self, mock_tenant, mock_user_tenants, mock_is_admin,
        mock_fin, mock_db_class, client, mock_auth
    ):
        """Getting non-existent account returns 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.get(
            '/api/tenant-admin/chart-of-accounts/9999',
            headers=mock_auth
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data
