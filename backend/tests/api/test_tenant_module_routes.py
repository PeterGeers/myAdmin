"""
API tests for tenant_module_routes.py

Tests module access control endpoints and verifies that unauthorized
tenants cannot access restricted modules.

Requirements: 5.4, 5.5, 8.3, 8.4
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTenantModuleAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_get_modules_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get modules should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant/modules')
        assert response.status_code in (401, 403)

    def test_update_module_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to update module should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/tenant/modules',
                json={'module_name': 'FIN', 'is_active': True}
            )
        assert response.status_code in (401, 403)


# ============================================================================
# Get Tenant Modules Tests
# ============================================================================


class TestGetTenantModules:
    """Tests for GET /api/tenant/modules."""

    @patch('tenant_module_routes.db_manager')
    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_get_modules_success(
        self, mock_get_tenants, mock_db, client, mock_auth
    ):
        """Authenticated user can get their tenant modules."""
        mock_get_tenants.return_value = ['test-tenant']

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {'module_name': 'FIN'},
            {'module_name': 'STR'}
        ]

        response = client.get(
            '/api/tenant/modules',
            headers=mock_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'available_modules' in data
        assert data['tenant'] == 'test-tenant'

    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_get_modules_no_tenant_header_returns_400(
        self, mock_get_tenants, client, mock_auth
    ):
        """Missing X-Tenant header should return 400."""
        # Remove X-Tenant from headers
        headers = {'Authorization': mock_auth['Authorization']}

        response = client.get(
            '/api/tenant/modules',
            headers=headers
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_get_modules_unauthorized_tenant_returns_403(
        self, mock_get_tenants, client, mock_auth
    ):
        """User without access to the tenant should get 403."""
        mock_get_tenants.return_value = ['other-tenant']

        response = client.get(
            '/api/tenant/modules',
            headers=mock_auth
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'Access denied' in data['error']


# ============================================================================
# Get All Tenant Modules Tests
# ============================================================================


class TestGetAllTenantModules:
    """Tests for GET /api/tenant/modules/all."""

    @patch('tenant_module_routes.db_manager')
    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_get_all_modules_success(
        self, mock_get_tenants, mock_db, client, mock_auth
    ):
        """Authenticated user can get modules for all their tenants."""
        mock_get_tenants.return_value = ['tenant-a', 'tenant-b']

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        # First call for tenant-a, second for tenant-b
        mock_cursor.fetchall.side_effect = [
            [{'module_name': 'FIN'}],
            [{'module_name': 'FIN'}, {'module_name': 'STR'}]
        ]

        response = client.get(
            '/api/tenant/modules/all',
            headers=mock_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'tenants' in data

    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_get_all_modules_no_tenants_returns_empty(
        self, mock_get_tenants, client, mock_auth
    ):
        """User with no tenants should get empty result."""
        mock_get_tenants.return_value = []

        response = client.get(
            '/api/tenant/modules/all',
            headers=mock_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['tenants'] == {}


# ============================================================================
# Update Tenant Module Tests
# ============================================================================


class TestUpdateTenantModule:
    """Tests for POST /api/tenant/modules."""

    @patch('tenant_module_routes.db_manager')
    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_update_module_non_admin_returns_403(
        self, mock_get_tenants, mock_db, client, mock_auth
    ):
        """Non-Tenant_Admin user should get 403 when updating modules."""
        mock_get_tenants.return_value = ['test-tenant']

        # mock_auth returns TenantAdmin role, but the route checks for
        # 'Tenant_Admin' specifically in user_roles
        response = client.post(
            '/api/tenant/modules',
            headers=mock_auth,
            json={'module_name': 'FIN', 'is_active': True}
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'Tenant_Admin' in data['error']

    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_update_module_no_tenant_header_returns_400(
        self, mock_get_tenants, client, mock_auth
    ):
        """Missing X-Tenant header should return 400."""
        headers = {'Authorization': mock_auth['Authorization']}

        response = client.post(
            '/api/tenant/modules',
            headers=headers,
            json={'module_name': 'FIN', 'is_active': True}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No tenant specified' in data['error']

    @patch('tenant_module_routes.db_manager')
    @patch('tenant_module_routes.get_user_tenants_from_jwt')
    def test_update_module_invalid_module_name_returns_400(
        self, mock_get_tenants, mock_db, client, mock_auth_sysadmin
    ):
        """Invalid module name should return 400."""
        mock_get_tenants.return_value = ['test-tenant']

        # Patch to simulate Tenant_Admin role
        with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
             patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
             patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
             patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']):
            mock_creds.return_value = ('admin@example.com', ['Tenant_Admin'], None)

            response = client.post(
                '/api/tenant/modules',
                headers={
                    'Authorization': 'Bearer test-token',
                    'X-Tenant': 'test-tenant'
                },
                json={'module_name': 'INVALID_MODULE', 'is_active': True}
            )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid module name' in data['error']


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions in tenant_module_routes."""

    def test_get_user_module_roles_finance_roles(self):
        """Finance roles should map to FIN module."""
        from tenant_module_routes import get_user_module_roles

        roles = ['Finance_Read', 'Finance_Write']
        result = get_user_module_roles(roles)
        assert 'FIN' in result

    def test_get_user_module_roles_str_roles(self):
        """STR roles should map to STR module."""
        from tenant_module_routes import get_user_module_roles

        roles = ['STR_Read', 'STR_Write']
        result = get_user_module_roles(roles)
        assert 'STR' in result

    def test_get_user_module_roles_zzp_roles(self):
        """ZZP roles should map to ZZP module."""
        from tenant_module_routes import get_user_module_roles

        roles = ['ZZP_Read']
        result = get_user_module_roles(roles)
        assert 'ZZP' in result

    def test_get_user_module_roles_mixed_roles(self):
        """Mixed roles should return multiple modules."""
        from tenant_module_routes import get_user_module_roles

        roles = ['Finance_Read', 'STR_Write', 'ZZP_Read', 'TenantAdmin']
        result = get_user_module_roles(roles)
        assert set(result) == {'FIN', 'STR', 'ZZP'}

    def test_get_user_module_roles_no_module_roles(self):
        """Roles without module prefix should return empty list."""
        from tenant_module_routes import get_user_module_roles

        roles = ['TenantAdmin', 'SysAdmin']
        result = get_user_module_roles(roles)
        assert result == []
