"""
API tests for routes/system_health_routes.py

Tests health/monitoring endpoints including public endpoints
and authentication enforcement on protected endpoints.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Public Endpoint Tests
# ============================================================================


class TestPublicEndpoints:
    """Verify public endpoints respond without authentication."""

    def test_status_responds_without_auth(self, client):
        """GET /api/status is public and returns status info."""
        with patch.dict('os.environ', {
            'TEST_MODE': 'false',
            'DB_NAME': 'finance',
            'FACTUREN_FOLDER_NAME': 'Facturen'
        }, clear=False):
            response = client.get('/api/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ok'
        assert 'mode' in data
        assert 'database' in data

    def test_health_responds_without_auth(self, client):
        """GET /api/health is public and returns health info."""
        response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert 'scalability' in data

    def test_db_config_responds_without_auth(self, client):
        """GET /api/db-config is public and returns config info."""
        with patch.dict('os.environ', {
            'DB_HOST': 'localhost',
            'DB_PORT': '3306',
            'DB_USER': 'testuser',
            'DB_NAME': 'testdb',
            'TEST_MODE': 'false'
        }, clear=False):
            response = client.get('/api/db-config')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'DB_HOST' in data
        assert 'computed_host' in data


# ============================================================================
# Status Endpoint Tests
# ============================================================================


class TestStatusEndpoint:
    """Tests for GET /api/status."""

    def test_status_production_mode(self, client):
        """Status returns Production mode when TEST_MODE is false."""
        with patch.dict('os.environ', {
            'TEST_MODE': 'false',
            'DB_NAME': 'finance',
            'FACTUREN_FOLDER_NAME': 'Facturen'
        }, clear=False):
            response = client.get('/api/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['mode'] == 'Production'
        assert data['database'] == 'finance'

    def test_status_test_mode(self, client):
        """Status returns Test mode when TEST_MODE is true."""
        with patch.dict('os.environ', {
            'TEST_MODE': 'true',
            'TEST_DB_NAME': 'testfinance',
            'TEST_FACTUREN_FOLDER_NAME': 'testFacturen'
        }, clear=False):
            response = client.get('/api/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['mode'] == 'Test'
        assert data['database'] == 'testfinance'


# ============================================================================
# Health Endpoint Tests
# ============================================================================


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_without_scalability_manager(self, client):
        """Health returns baseline info when scalability manager is None."""
        with patch('routes.system_health_routes.scalability_manager', None):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['scalability']['manager_active'] is False
        assert data['scalability']['concurrent_user_capacity'] == '1x baseline'

    def test_health_with_scalability_manager(self, client):
        """Health returns enhanced info when scalability manager is active."""
        mock_manager = MagicMock()
        mock_manager.get_health_status.return_value = {
            'health_score': 95,
            'status': 'healthy',
            'scalability_ready': True
        }

        with patch('routes.system_health_routes.scalability_manager', mock_manager):
            response = client.get('/api/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['scalability']['manager_active'] is True
        assert data['scalability']['concurrent_user_capacity'] == '10x baseline'
        assert data['scalability']['health_score'] == 95


# ============================================================================
# Authentication Enforcement Tests (Protected Endpoints)
# ============================================================================


class TestProtectedEndpointsAuth:
    """Verify auth enforcement on protected endpoints."""

    def test_api_test_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to /api/test should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/test')
        assert response.status_code in (401, 403)

    def test_str_test_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to /api/str/test should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/str/test')
        assert response.status_code in (401, 403)

    def test_google_drive_token_health_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to token-health should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/google-drive/token-health')
        assert response.status_code in (401, 403)

    def test_api_test_authenticated_returns_200(self, client, mock_auth):
        """Authenticated request to /api/test returns 200."""
        response = client.get(
            '/api/test',
            headers=mock_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'Server is working'

    def test_str_test_authenticated_returns_200(self, client, mock_auth):
        """Authenticated request to /api/str/test returns 200."""
        response = client.get(
            '/api/str/test',
            headers=mock_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'STR endpoints working'

    @patch('database.DatabaseManager')
    @patch('services.credential_service.CredentialService')
    def test_google_drive_token_health_sysadmin_returns_200(
        self, mock_cred_service_class, mock_db_class, client, mock_auth_sysadmin
    ):
        """SysAdmin can access token-health endpoint."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_cred_service = MagicMock()
        mock_cred_service_class.return_value = mock_cred_service
        mock_cred_service.get_credential.return_value = {
            'expiry': '2025-12-31T00:00:00Z'
        }

        response = client.get(
            '/api/google-drive/token-health',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'overall_status' in data
        assert 'tenants' in data
