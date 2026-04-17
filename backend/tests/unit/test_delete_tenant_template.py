"""
Unit tests for DELETE /api/tenant-admin/templates/<template_type> endpoint.

Validates:
- Requirement 2.4: Deactivate tenant template (is_active=FALSE, status='archived')
- Requirement 2.5: Return 200 with success message
- Requirement 2.7: Audit log entry with user email, tenant, template type, file ID
- Requirement 2.8: Return 404 when no active template exists
- Requirement 2.9: Return 403 for non-tenant-admin
- Requirement 2.10: Soft-delete preserves template history
"""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock, call

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tenant_admin_routes import tenant_admin_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal Flask app with the tenant_admin blueprint."""
    import flask
    app = flask.Flask(__name__)
    app.register_blueprint(tenant_admin_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Tests: successful deactivation returns 200 (Requirement 2.4, 2.5, 2.10)
# ---------------------------------------------------------------------------

class TestDeleteTenantTemplateSuccess:
    """Test successful template deactivation returns 200."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    def test_successful_deactivation_returns_200(
        self, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client
    ):
        """DELETE /api/tenant-admin/templates/str_invoice_nl returns 200."""
        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance

        # First call (SELECT) returns active template, second call (UPDATE) returns None
        mock_db_instance.execute_query.side_effect = [
            [{'template_file_id': '1abc_test_file_xyz'}],  # SELECT
            None,  # UPDATE
        ]

        response = client.delete(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['template_type'] == 'str_invoice_nl'
        assert data['deactivated_file_id'] == '1abc_test_file_xyz'
        assert data['message'] == 'Template deactivated successfully. System will use default template.'

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    def test_update_query_sets_inactive_and_archived(
        self, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client
    ):
        """Verify the UPDATE query sets is_active=FALSE and status='archived'."""
        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance

        mock_db_instance.execute_query.side_effect = [
            [{'template_file_id': 'file123'}],  # SELECT
            None,  # UPDATE
        ]

        client.delete(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        # The second call should be the UPDATE query
        update_call = mock_db_instance.execute_query.call_args_list[1]
        update_query = update_call[0][0]
        update_params = update_call[0][1]

        assert 'is_active = FALSE' in update_query
        assert "status = 'archived'" in update_query
        assert 'updated_at = NOW()' in update_query
        assert update_params == ('TestTenant', 'str_invoice_nl')
        assert update_call[1] == {'fetch': False, 'commit': True}


# ---------------------------------------------------------------------------
# Tests: no active template returns 404 (Requirement 2.8)
# ---------------------------------------------------------------------------

class TestDeleteTenantTemplateNotFound:
    """Test delete when no active template returns 404."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    def test_no_active_template_returns_404(
        self, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client
    ):
        """DELETE returns 404 when no active template exists."""
        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance

        # SELECT returns empty list
        mock_db_instance.execute_query.return_value = []

        response = client.delete(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No active tenant template found for type: str_invoice_nl' in data['error']


# ---------------------------------------------------------------------------
# Tests: non-tenant-admin returns 403 (Requirement 2.9)
# ---------------------------------------------------------------------------

class TestDeleteTenantTemplateAuth:
    """Test that non-tenant-admin users get 403."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('user@test.com', ['Finance_Read'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Finance_Read'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=False)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    def test_non_admin_returns_403(
        self, mock_tenant, mock_is_admin, mock_tenants,
        mock_roles, mock_creds, client
    ):
        """A non-Tenant_Admin user must receive 403."""
        response = client.delete(
            '/api/tenant-admin/templates/str_invoice_nl',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['error'] == 'Tenant admin access required'


# ---------------------------------------------------------------------------
# Tests: audit log entry (Requirement 2.7)
# ---------------------------------------------------------------------------

class TestDeleteTenantTemplateAudit:
    """Test audit log entry is written on successful deactivation."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('tenant_admin_routes.logger')
    def test_audit_log_contains_required_fields(
        self, mock_logger, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client
    ):
        """Audit log must contain user_email, tenant, template_type, and file_id."""
        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance

        mock_db_instance.execute_query.side_effect = [
            [{'template_file_id': 'audit_file_id_123'}],  # SELECT
            None,  # UPDATE
        ]

        response = client.delete(
            '/api/tenant-admin/templates/btw_aangifte',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 200

        # Verify logger.info was called with AUDIT message
        audit_calls = [
            c for c in mock_logger.info.call_args_list
            if 'AUDIT' in str(c)
        ]
        assert len(audit_calls) >= 1

        audit_message = str(audit_calls[0])
        assert 'admin@test.com' in audit_message
        assert 'TestTenant' in audit_message
        assert 'btw_aangifte' in audit_message
        assert 'audit_file_id_123' in audit_message


# ---------------------------------------------------------------------------
# Tests: invalid template type returns 400
# ---------------------------------------------------------------------------

class TestDeleteTenantTemplateInvalidType:
    """Test that an invalid template type returns 400."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    def test_invalid_type_returns_400(
        self, mock_tenant, mock_is_admin, mock_tenants,
        mock_roles, mock_creds, client
    ):
        """An unknown template type must return 400."""
        response = client.delete(
            '/api/tenant-admin/templates/nonexistent_type',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Invalid template type'
        assert 'valid_types' in data
