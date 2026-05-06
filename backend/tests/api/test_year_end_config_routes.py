"""
API tests for year_end_config_routes.py

Tests year-end configuration endpoints including auth enforcement,
validation, purpose management, and VAT netting configuration.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for year-end config endpoints."""
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


class TestYearEndConfigAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_validate_config_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to validate config should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/year-end-config/validate')
        assert response.status_code in (401, 403)

    def test_get_purposes_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get purposes should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/year-end-config/purposes')
        assert response.status_code in (401, 403)

    def test_set_account_purpose_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to set purpose should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/tenant-admin/year-end-config/accounts',
                json={'account_code': '1000', 'purpose': 'profit_loss'}
            )
        assert response.status_code in (401, 403)

    def test_vat_netting_get_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get VAT netting should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/year-end-config/vat-netting')
        assert response.status_code in (401, 403)


# ============================================================================
# Validate Config Tests
# ============================================================================


class TestValidateConfig:
    """Tests for GET /api/tenant-admin/year-end-config/validate."""

    @patch('routes.year_end_config_routes.config_service')
    def test_validate_config_success(self, mock_service, client, finance_auth):
        """Validate config returns validation data."""
        mock_service.validate_configuration.return_value = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'configured_purposes': {'profit_loss': '9999'}
        }

        response = client.get(
            '/api/tenant-admin/year-end-config/validate',
            headers=finance_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['valid'] is True


# ============================================================================
# Account Purpose Tests
# ============================================================================


class TestSetAccountPurpose:
    """Tests for POST /api/tenant-admin/year-end-config/accounts."""

    @patch('routes.year_end_config_routes.config_service')
    def test_set_purpose_without_account_code_returns_400(
        self, mock_service, client, finance_auth
    ):
        """Missing account_code returns 400."""
        response = client.post(
            '/api/tenant-admin/year-end-config/accounts',
            headers=finance_auth,
            json={'purpose': 'profit_loss'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'account_code' in data['error']

    @patch('routes.year_end_config_routes.config_service')
    def test_set_purpose_no_body_returns_error(self, mock_service,
                                               client, finance_auth):
        """No request body returns error status."""
        response = client.post(
            '/api/tenant-admin/year-end-config/accounts',
            headers=finance_auth,
            content_type='application/json'
        )

        # Route catches JSON decode error, returns 400 or 500
        assert response.status_code in (400, 500)

    @patch('routes.year_end_config_routes.config_service')
    def test_set_purpose_success(self, mock_service, client, finance_auth):
        """Valid purpose assignment succeeds."""
        mock_service.set_account_purpose.return_value = None

        response = client.post(
            '/api/tenant-admin/year-end-config/accounts',
            headers=finance_auth,
            json={'account_code': '9999', 'purpose': 'profit_loss'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# VAT Netting Tests
# ============================================================================


class TestVatNetting:
    """Tests for /api/year-end-config/vat-netting endpoints."""

    @patch('routes.year_end_config_routes.config_service')
    def test_configure_vat_netting_missing_accounts_returns_400(
        self, mock_service, client, finance_auth
    ):
        """Missing vat_accounts returns 400."""
        response = client.post(
            '/api/year-end-config/vat-netting',
            headers=finance_auth,
            json={'primary_account': '1500'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.year_end_config_routes.config_service')
    def test_configure_vat_netting_missing_primary_returns_400(
        self, mock_service, client, finance_auth
    ):
        """Missing primary_account returns 400."""
        response = client.post(
            '/api/year-end-config/vat-netting',
            headers=finance_auth,
            json={'vat_accounts': ['1500', '1510']}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.year_end_config_routes.config_service')
    def test_configure_vat_netting_primary_not_in_accounts_returns_400(
        self, mock_service, client, finance_auth
    ):
        """Primary account not in vat_accounts returns 400."""
        response = client.post(
            '/api/year-end-config/vat-netting',
            headers=finance_auth,
            json={
                'vat_accounts': ['1500', '1510'],
                'primary_account': '9999'
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.year_end_config_routes.config_service')
    def test_configure_vat_netting_success(self, mock_service,
                                           client, finance_auth):
        """Valid VAT netting configuration succeeds."""
        mock_service.configure_vat_netting.return_value = None

        response = client.post(
            '/api/year-end-config/vat-netting',
            headers=finance_auth,
            json={
                'vat_accounts': ['1500', '1510'],
                'primary_account': '1500'
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
