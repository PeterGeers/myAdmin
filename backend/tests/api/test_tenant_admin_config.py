"""
API tests for tenant_admin_config.py

Tests CRUD operations for tenant configuration entries,
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
    Patches cognito auth, tenant validation, and role cache.
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


class TestTenantAdminConfigAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_list_configs_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list configs should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/config')
        assert response.status_code in (401, 403)

    def test_create_config_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create config should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/tenant-admin/config',
                json={'config_key': 'test_key', 'config_value': 'test_value'}
            )
        assert response.status_code in (401, 403)


# ============================================================================
# Config List Tests
# ============================================================================


class TestTenantAdminConfigList:
    """Tests for GET /api/tenant-admin/config."""

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    def test_list_configs_returns_configs(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return list of configs."""
        from datetime import datetime
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [
            {
                'id': 1,
                'config_key': 'api_key',
                'config_value': 'secret123',
                'is_secret': 1,
                'created_at': datetime(2024, 1, 1),
                'updated_at': datetime(2024, 1, 2),
                'created_by': 'admin@example.com'
            }
        ]

        response = client.get(
            '/api/tenant-admin/config',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1
        assert data['configs'][0]['config_key'] == 'api_key'

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    def test_list_configs_empty_returns_empty_list(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """No configs should return empty list."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.get(
            '/api/tenant-admin/config',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 0
        assert data['configs'] == []


# ============================================================================
# Config Create Tests
# ============================================================================


class TestTenantAdminConfigCreate:
    """Tests for POST /api/tenant-admin/config."""

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    def test_create_config_missing_config_key_returns_400(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Missing config_key should return 400."""
        response = client.post(
            '/api/tenant-admin/config',
            headers=tenant_admin_auth,
            json={'config_value': 'some_value'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'config_key' in data['error'].lower()

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    @patch('auth.tenant_context._map_config_key_to_param', return_value=('ns', 'key'))
    @patch('services.parameter_service.ParameterService')
    def test_create_config_success_returns_201(
        self, mock_ps_class, mock_map, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid config creation should return 201."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_ps = MagicMock()
        mock_ps_class.return_value = mock_ps

        response = client.post(
            '/api/tenant-admin/config',
            headers=tenant_admin_auth,
            json={'config_key': 'new_key', 'config_value': 'new_value', 'is_secret': False}
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Config Update Tests
# ============================================================================


class TestTenantAdminConfigUpdate:
    """Tests for PUT /api/tenant-admin/config/<id>."""

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    def test_update_config_nonexistent_returns_404(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Updating non-existent config should return 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.put(
            '/api/tenant-admin/config/999',
            headers=tenant_admin_auth,
            json={'config_value': 'updated_value'}
        )
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error'].lower()

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    @patch('auth.tenant_context._map_config_key_to_param', return_value=('ns', 'key'))
    @patch('services.parameter_service.ParameterService')
    def test_update_config_success(
        self, mock_ps_class, mock_map, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid config update should return 200."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [{'id': 1, 'config_key': 'test_key'}]
        mock_ps = MagicMock()
        mock_ps_class.return_value = mock_ps

        response = client.put(
            '/api/tenant-admin/config/1',
            headers=tenant_admin_auth,
            json={'config_value': 'updated_value', 'is_secret': False}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Config Delete Tests
# ============================================================================


class TestTenantAdminConfigDelete:
    """Tests for DELETE /api/tenant-admin/config/<id>."""

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    def test_delete_config_nonexistent_returns_404(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Deleting non-existent config should return 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.delete(
            '/api/tenant-admin/config/999',
            headers=tenant_admin_auth
        )
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error'].lower()

    @patch('routes.tenant_admin_config.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_config.DatabaseManager')
    @patch('auth.tenant_context._map_config_key_to_param', return_value=('ns', 'key'))
    @patch('services.parameter_service.ParameterService')
    def test_delete_config_success(
        self, mock_ps_class, mock_map, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid config deletion should return 200."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [{'config_key': 'test_key'}]
        mock_ps = MagicMock()
        mock_ps_class.return_value = mock_ps

        response = client.delete(
            '/api/tenant-admin/config/1',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
