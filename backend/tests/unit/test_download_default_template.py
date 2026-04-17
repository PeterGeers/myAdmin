"""
Unit tests for GET /api/tenant-admin/templates/<template_type>/default endpoint.

Validates:
- Requirement 1.3: Valid type returns 200 with correct content and filename
- Requirement 1.5: Type with no _LOCAL_DEFAULTS entry returns 404
- Requirement 1.6: Non-tenant-admin returns 403
- Requirement 4.1: Reuses _LOCAL_DEFAULTS and _get_local_default_metadata()
"""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tenant_admin_routes import tenant_admin_bp, _TEMPLATE_TYPE_TO_LOCAL_KEY


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
# Helper: common auth mocks for tenant admin access
# ---------------------------------------------------------------------------

def _auth_mocks_admin():
    """Return a list of patch decorators for an authenticated tenant admin."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('admin@test.com', ['Tenant_Admin'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']),
        patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant']),
        patch('tenant_admin_routes.is_tenant_admin', return_value=True),
        patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant'),
    ]


def _auth_mocks_non_admin():
    """Return a list of patch decorators for a non-admin user."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('user@test.com', ['Finance_Read'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Finance_Read']),
        patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant']),
        patch('tenant_admin_routes.is_tenant_admin', return_value=False),
        patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant'),
    ]


# ---------------------------------------------------------------------------
# Tests: valid type returns 200 (Requirement 1.3)
# ---------------------------------------------------------------------------

class TestDownloadDefaultTemplateSuccess:
    """Test that a valid template type returns 200 with correct content."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('services.template_service.TemplateService._get_local_default_metadata')
    def test_valid_type_returns_200_with_content(
        self, mock_get_meta, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client, tmp_path
    ):
        """GET /api/tenant-admin/templates/str_invoice_nl/default returns 200."""
        # Create a temporary template file
        template_file = tmp_path / 'template.html'
        template_file.write_text('<html><body>Default Template</body></html>')

        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance

        mock_get_meta.return_value = {
            'template_file_id': None,
            'field_mappings': {'company_name': '{{company}}'},
            'is_active': True,
            'local_path': str(template_file),
            'created_at': None,
            'updated_at': None,
        }

        response = client.get(
            '/api/tenant-admin/templates/str_invoice_nl/default',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['template_type'] == 'str_invoice_nl'
        assert data['template_content'] == '<html><body>Default Template</body></html>'
        assert data['filename'] == 'str_invoice_nl_default.html'
        assert data['field_mappings'] == {'company_name': '{{company}}'}
        assert data['message'] == 'Default template retrieved successfully'

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('services.template_service.TemplateService._get_local_default_metadata')
    def test_filename_follows_type_default_html_pattern(
        self, mock_get_meta, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client, tmp_path
    ):
        """Filename must be {type}_default.html."""
        template_file = tmp_path / 'template.html'
        template_file.write_text('<html>BTW</html>')

        mock_db_cls.return_value = MagicMock()
        mock_get_meta.return_value = {
            'template_file_id': None,
            'field_mappings': {},
            'is_active': True,
            'local_path': str(template_file),
            'created_at': None,
            'updated_at': None,
        }

        response = client.get(
            '/api/tenant-admin/templates/btw_aangifte/default',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['filename'] == 'btw_aangifte_default.html'


# ---------------------------------------------------------------------------
# Tests: invalid type returns 400
# ---------------------------------------------------------------------------

class TestDownloadDefaultTemplateInvalidType:
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
        response = client.get(
            '/api/tenant-admin/templates/nonexistent_type/default',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Invalid template type'
        assert 'valid_types' in data


# ---------------------------------------------------------------------------
# Tests: no _LOCAL_DEFAULTS entry returns 404 (Requirement 1.5)
# ---------------------------------------------------------------------------

class TestDownloadDefaultTemplateNotFound:
    """Test that a type with no local default returns 404."""

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('services.template_service.TemplateService._get_local_default_metadata')
    def test_no_local_default_returns_404(
        self, mock_get_meta, mock_db_cls, mock_tenant, mock_is_admin,
        mock_tenants, mock_roles, mock_creds, client
    ):
        """When _get_local_default_metadata returns None, endpoint returns 404."""
        mock_db_cls.return_value = MagicMock()
        mock_get_meta.return_value = None

        response = client.get(
            '/api/tenant-admin/templates/str_invoice_nl/default',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No default template available' in data['error']


# ---------------------------------------------------------------------------
# Tests: non-tenant-admin returns 403 (Requirement 1.6)
# ---------------------------------------------------------------------------

class TestDownloadDefaultTemplateAuth:
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
        response = client.get(
            '/api/tenant-admin/templates/str_invoice_nl/default',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['error'] == 'Tenant admin access required'


# ---------------------------------------------------------------------------
# Tests: _TEMPLATE_TYPE_TO_LOCAL_KEY mapping
# ---------------------------------------------------------------------------

class TestTemplateTypeToLocalKeyMapping:
    """Test the mapping constant covers all VALID_TEMPLATE_TYPES."""

    def test_mapping_covers_all_valid_types(self):
        """Every VALID_TEMPLATE_TYPES entry must have a mapping."""
        from tenant_admin_routes import VALID_TEMPLATE_TYPES
        for t in VALID_TEMPLATE_TYPES:
            assert t in _TEMPLATE_TYPE_TO_LOCAL_KEY, \
                f"Missing mapping for template type: {t}"

    def test_mapping_values_match_local_defaults(self):
        """Every mapping value must exist in TemplateService._LOCAL_DEFAULTS."""
        from services.template_service import TemplateService
        for valid_type, local_key in _TEMPLATE_TYPE_TO_LOCAL_KEY.items():
            assert local_key in TemplateService._LOCAL_DEFAULTS, \
                f"Mapping value '{local_key}' for '{valid_type}' not in _LOCAL_DEFAULTS"
