"""
Unit tests for VALID_TEMPLATE_TYPES constant and zzp_invoice support.

Validates:
- Requirement 3.1: GET endpoint accepts all 7 template types including zzp_invoice
- Requirement 3.3: zzp_invoice is processed identically to other valid types
"""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tenant_admin_routes import VALID_TEMPLATE_TYPES, tenant_admin_bp


# ---------------------------------------------------------------------------
# Tests for VALID_TEMPLATE_TYPES constant (Requirement 3.1, 3.2)
# ---------------------------------------------------------------------------

class TestValidTemplateTypes:
    """Test the shared VALID_TEMPLATE_TYPES constant."""

    def test_contains_all_seven_types(self):
        """VALID_TEMPLATE_TYPES must contain exactly the 7 expected types."""
        expected = {
            'str_invoice_nl', 'str_invoice_en',
            'btw_aangifte', 'aangifte_ib',
            'toeristenbelasting', 'financial_report',
            'zzp_invoice',
        }
        assert set(VALID_TEMPLATE_TYPES) == expected

    def test_contains_zzp_invoice(self):
        """zzp_invoice must be present (the bug that was fixed)."""
        assert 'zzp_invoice' in VALID_TEMPLATE_TYPES

    def test_has_seven_entries(self):
        """Constant must have exactly 7 entries."""
        assert len(VALID_TEMPLATE_TYPES) == 7

    def test_no_duplicates(self):
        """No duplicate entries in the list."""
        assert len(VALID_TEMPLATE_TYPES) == len(set(VALID_TEMPLATE_TYPES))


# ---------------------------------------------------------------------------
# Tests for GET /api/tenant-admin/templates/<template_type> (Requirement 3.3)
# ---------------------------------------------------------------------------

class TestGetCurrentTemplateEndpointValidation:
    """Test that the GET endpoint accepts zzp_invoice and rejects invalid types."""

    @pytest.fixture
    def app(self):
        """Create a minimal Flask app with the tenant_admin blueprint."""
        import flask
        app = flask.Flask(__name__)
        app.register_blueprint(tenant_admin_bp)
        app.config['TESTING'] = True
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    def test_zzp_invoice_not_rejected_as_invalid(
        self, mock_db_cls, mock_tenant, mock_is_admin, mock_tenants,
        mock_roles, mock_creds, client
    ):
        """GET /api/tenant-admin/templates/zzp_invoice must NOT return 400.

        Before the fix, zzp_invoice was missing from valid_types and the
        endpoint returned 400. After the fix it should proceed past validation.
        """
        mock_db_instance = MagicMock()
        mock_db_instance.execute_query.return_value = []
        mock_db_cls.return_value = mock_db_instance

        response = client.get(
            '/api/tenant-admin/templates/zzp_invoice',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        # Must NOT be 400 "Invalid template type"
        if response.status_code == 400:
            data = json.loads(response.data)
            assert data.get('error') != 'Invalid template type', \
                "zzp_invoice should be accepted as a valid template type"

    @patch('auth.cognito_utils.extract_user_credentials',
           return_value=('admin@test.com', ['Tenant_Admin'], None))
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    @patch('tenant_admin_routes.get_user_tenants', return_value=['TestTenant'])
    @patch('tenant_admin_routes.is_tenant_admin', return_value=True)
    @patch('tenant_admin_routes.get_current_tenant', return_value='TestTenant')
    @patch('tenant_admin_routes.DatabaseManager')
    def test_invalid_type_returns_400(
        self, mock_db_cls, mock_tenant, mock_is_admin, mock_tenants,
        mock_roles, mock_creds, client
    ):
        """An unknown template type must still return 400."""
        mock_db_instance = MagicMock()
        mock_db_cls.return_value = mock_db_instance

        response = client.get(
            '/api/tenant-admin/templates/nonexistent_type',
            headers={'Authorization': 'Bearer fake.jwt.token'},
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['error'] == 'Invalid template type'
        assert 'zzp_invoice' in data['valid_types']
