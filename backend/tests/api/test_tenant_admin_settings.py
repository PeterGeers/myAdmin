"""
API tests for tenant_admin_settings.py

Tests settings CRUD, activity stats, and language preference endpoints,
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


class TestTenantAdminSettingsAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_get_settings_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get settings should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/settings')
        assert response.status_code in (401, 403)

    def test_update_settings_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to update settings should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.put(
                '/api/tenant-admin/settings',
                json={'notifications': {'email_enabled': True}}
            )
        assert response.status_code in (401, 403)


# ============================================================================
# Get Settings Tests
# ============================================================================


class TestTenantAdminSettingsGet:
    """Tests for GET /api/tenant-admin/settings."""

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.DatabaseManager')
    @patch('routes.tenant_admin_settings.TenantSettingsService')
    def test_get_settings_returns_data(
        self, mock_service_class, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return settings."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_settings.return_value = {
            'notifications': {'email_enabled': True, 'sms_enabled': False},
            'preferences': {'language': 'nl', 'timezone': 'Europe/Amsterdam'}
        }

        response = client.get(
            '/api/tenant-admin/settings',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['settings']['notifications']['email_enabled'] is True
        assert data['tenant'] == 'test-tenant'


# ============================================================================
# Update Settings Tests
# ============================================================================


class TestTenantAdminSettingsUpdate:
    """Tests for PUT /api/tenant-admin/settings."""

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.DatabaseManager')
    @patch('routes.tenant_admin_settings.TenantSettingsService')
    def test_update_settings_no_data_returns_400(
        self, mock_service_class, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Update with empty data should return 400."""
        response = client.put(
            '/api/tenant-admin/settings',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'no settings' in data['error'].lower() or 'no data' in data['error'].lower()

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.DatabaseManager')
    @patch('routes.tenant_admin_settings.TenantSettingsService')
    def test_update_settings_success(
        self, mock_service_class, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid settings update should return 200."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_settings.return_value = {
            'notifications': {'email_enabled': False, 'sms_enabled': True}
        }

        response = client.put(
            '/api/tenant-admin/settings',
            headers=tenant_admin_auth,
            json={'notifications': {'email_enabled': False, 'sms_enabled': True}}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'updated successfully' in data['message'].lower()


# ============================================================================
# Activity Stats Tests
# ============================================================================


class TestTenantAdminActivity:
    """Tests for GET /api/tenant-admin/activity."""

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.DatabaseManager')
    @patch('routes.tenant_admin_settings.TenantSettingsService')
    def test_get_activity_returns_stats(
        self, mock_service_class, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return activity statistics."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_activity.return_value = {
            'total_logins': 42,
            'active_users': 5,
            'last_activity': '2024-01-15'
        }

        response = client.get(
            '/api/tenant-admin/activity',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['activity']['total_logins'] == 42


# ============================================================================
# Language Preference Tests
# ============================================================================


class TestTenantAdminLanguage:
    """Tests for GET/PUT /api/tenant-admin/language."""

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.get_tenant_language', return_value='nl')
    def test_get_language_returns_preference(
        self, mock_get_lang, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return language preference."""
        response = client.get(
            '/api/tenant-admin/language',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['default_language'] == 'nl'

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.validate_language_code', return_value=True)
    @patch('routes.tenant_admin_settings.update_tenant_language', return_value=True)
    def test_update_language_valid_code_succeeds(
        self, mock_update, mock_validate, mock_tenant, client, tenant_admin_auth
    ):
        """Valid language code update should return 200."""
        response = client.put(
            '/api/tenant-admin/language',
            headers=tenant_admin_auth,
            json={'default_language': 'en'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['default_language'] == 'en'

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_settings.validate_language_code', return_value=False)
    def test_update_language_invalid_code_returns_400(
        self, mock_validate, mock_tenant, client, tenant_admin_auth
    ):
        """Invalid language code should return 400."""
        response = client.put(
            '/api/tenant-admin/language',
            headers=tenant_admin_auth,
            json={'default_language': 'xx'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'invalid' in data['error'].lower()

    @patch('routes.tenant_admin_settings.get_current_tenant', return_value='test-tenant')
    def test_update_language_missing_field_returns_400(
        self, mock_tenant, client, tenant_admin_auth
    ):
        """Missing default_language field should return 400."""
        response = client.put(
            '/api/tenant-admin/language',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'missing' in data['error'].lower() or 'required' in data['error'].lower()
