"""
API tests for tenant_admin_details.py

Tests tenant details CRUD operations,
including authentication enforcement and input validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def tenant_admin_auth():
    """
    Mock authentication with Tenant_Admin role for tenant admin endpoints.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']):
        mock_creds.return_value = ('admin@example.com', ['Tenant_Admin'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTenantAdminDetailsAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_get_details_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get tenant details should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/details')
        assert response.status_code in (401, 403)

    def test_update_details_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to update tenant details should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.put(
                '/api/tenant-admin/details',
                json={'display_name': 'Test Company'}
            )
        assert response.status_code in (401, 403)


# ============================================================================
# Get Tenant Details Tests
# ============================================================================


class TestTenantAdminDetailsGet:
    """Tests for GET /api/tenant-admin/details."""

    @patch('routes.tenant_admin_details.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_details.DatabaseManager')
    def test_get_details_returns_tenant_info(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return tenant details."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [{
            'administration': 'test-tenant',
            'display_name': 'Test Company',
            'contact_email': 'contact@test.com',
            'phone_number': '+31612345678',
            'street': 'Main Street 1',
            'city': 'Amsterdam',
            'zipcode': '1012 AB',
            'country': 'Netherlands',
            'bank_account_number': 'NL12ABCD0123456789',
            'bank_name': 'ING Bank',
            'status': 'active',
            'created_at': '2024-01-01',
            'updated_at': '2024-01-02'
        }]

        response = client.get(
            '/api/tenant-admin/details',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['tenant']['display_name'] == 'Test Company'
        assert data['tenant']['city'] == 'Amsterdam'

    @patch('routes.tenant_admin_details.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_details.DatabaseManager')
    def test_get_details_tenant_not_found_returns_404(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Non-existent tenant should return 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.get(
            '/api/tenant-admin/details',
            headers=tenant_admin_auth
        )
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error'].lower()


# ============================================================================
# Update Tenant Details Tests
# ============================================================================


class TestTenantAdminDetailsUpdate:
    """Tests for PUT /api/tenant-admin/details."""

    @patch('routes.tenant_admin_details.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_details.DatabaseManager')
    def test_update_details_empty_body_returns_400(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Update with empty JSON body should return 400."""
        response = client.put(
            '/api/tenant-admin/details',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'no data' in data['error'].lower()

    @patch('routes.tenant_admin_details.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_details.DatabaseManager')
    def test_update_details_no_valid_fields_returns_400(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Update with no valid fields should return 400."""
        response = client.put(
            '/api/tenant-admin/details',
            headers=tenant_admin_auth,
            json={'invalid_field': 'value'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'no valid fields' in data['error'].lower()

    @patch('routes.tenant_admin_details.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_details.DatabaseManager')
    def test_update_details_valid_data_succeeds(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid update should return 200 with updated details."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [{
            'administration': 'test-tenant',
            'display_name': 'Updated Company',
            'contact_email': 'new@test.com',
            'phone_number': '+31612345678',
            'street': 'New Street 1',
            'city': 'Rotterdam',
            'zipcode': '3011 AB',
            'country': 'Netherlands',
            'bank_account_number': 'NL12ABCD0123456789',
            'bank_name': 'ING Bank',
            'status': 'active',
            'created_at': '2024-01-01',
            'updated_at': '2024-06-01'
        }]

        response = client.put(
            '/api/tenant-admin/details',
            headers=tenant_admin_auth,
            json={'display_name': 'Updated Company', 'city': 'Rotterdam'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'updated successfully' in data['message'].lower()
