"""
API tests for pdf_validation_routes.py

Tests PDF URL validation endpoints including auth enforcement,
single URL validation, record updates, and administration listing.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for PDF validation endpoints."""
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


class TestPdfValidationAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_validate_urls_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to validate URLs should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/pdf/validate-urls')
        assert response.status_code in (401, 403)

    def test_update_record_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to update record should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/pdf/update-record', json={
                'old_ref3': 'https://old-url.com'
            })
        assert response.status_code in (401, 403)

    def test_validate_single_url_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to validate single URL should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/pdf/validate-single-url?url=https://test.com')
        assert response.status_code in (401, 403)

    def test_get_administrations_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get administrations should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/pdf/get-administrations')
        assert response.status_code in (401, 403)


# ============================================================================
# Validate Single URL Tests
# ============================================================================


class TestValidateSingleUrl:
    """Tests for GET /api/pdf/validate-single-url."""

    def test_validate_single_url_without_url_param_returns_400(self, client, finance_auth):
        """Missing url parameter returns 400."""
        response = client.get(
            '/api/pdf/validate-single-url',
            headers=finance_auth
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'URL parameter is required' in data['error']

    @patch('routes.pdf_validation_routes.PDFValidator')
    def test_validate_single_url_success(self, mock_validator_class,
                                         client, finance_auth):
        """Valid URL returns validation status."""
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator
        mock_validator._validate_single_record.return_value = {
            'status': 'ok'
        }

        response = client.get(
            '/api/pdf/validate-single-url?url=https://drive.google.com/file/d/abc123',
            headers=finance_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['status'] == 'ok'


# ============================================================================
# Update Record Tests
# ============================================================================


class TestUpdateRecord:
    """Tests for POST /api/pdf/update-record."""

    def test_update_record_without_old_ref3_returns_400(self, client, finance_auth):
        """Missing old_ref3 returns 400."""
        response = client.post(
            '/api/pdf/update-record',
            headers=finance_auth,
            json={'ref3': 'https://new-url.com'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Ref3 is required' in data['error']

    @patch('routes.pdf_validation_routes.PDFValidator')
    def test_update_record_success(self, mock_validator_class,
                                   client, finance_auth):
        """Valid update request succeeds."""
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator
        mock_validator.update_record.return_value = True

        response = client.post(
            '/api/pdf/update-record',
            headers=finance_auth,
            json={
                'old_ref3': 'https://old-url.com',
                'ref3': 'https://new-url.com',
                'ref4': 'new-filename.pdf'
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Get Administrations Tests
# ============================================================================


class TestGetAdministrations:
    """Tests for GET /api/pdf/get-administrations."""

    @patch('routes.pdf_validation_routes.PDFValidator')
    def test_get_administrations_success(self, mock_validator_class,
                                         client, finance_auth):
        """Returns list of administrations for year."""
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator
        mock_validator.get_administrations_for_year.return_value = [
            'Admin A', 'Admin B'
        ]

        response = client.get(
            '/api/pdf/get-administrations?year=2024',
            headers=finance_auth
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['administrations']) == 2
