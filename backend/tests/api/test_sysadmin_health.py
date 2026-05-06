"""
API tests for routes/sysadmin_health.py

Tests health check endpoints and authentication enforcement
for the SysAdmin health monitoring blueprint.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestSysadminHealthAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_health_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to sysadmin health should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/sysadmin/health')
        assert response.status_code in (401, 403)

    def test_health_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on health endpoint."""
        response = client.get(
            '/api/sysadmin/health',
            headers=mock_auth
        )
        assert response.status_code == 403


# ============================================================================
# Happy Path Tests
# ============================================================================


class TestSysadminHealthHappyPath:
    """Tests for GET /api/sysadmin/health with valid SysAdmin auth."""

    @patch('routes.sysadmin_health.check_openrouter_health')
    @patch('routes.sysadmin_health.check_sns_health')
    @patch('routes.sysadmin_health.check_cognito_health')
    @patch('routes.sysadmin_health.check_database_health')
    def test_health_all_healthy_returns_overall_healthy(
        self, mock_db_health, mock_cognito_health, mock_sns_health,
        mock_openrouter_health, client, mock_auth_sysadmin
    ):
        """Health endpoint returns overall healthy when all services are healthy."""
        mock_db_health.return_value = {
            'service': 'database',
            'status': 'healthy',
            'responseTime': 10,
            'message': 'Connected to MySQL 8.0',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_cognito_health.return_value = {
            'service': 'cognito',
            'status': 'healthy',
            'responseTime': 50,
            'message': 'AWS Cognito accessible',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_sns_health.return_value = {
            'service': 'sns',
            'status': 'healthy',
            'responseTime': 30,
            'message': 'AWS SNS accessible',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_openrouter_health.return_value = {
            'service': 'openrouter',
            'status': 'healthy',
            'responseTime': 100,
            'message': 'OpenRouter API accessible',
            'lastChecked': '2024-01-01T00:00:00Z'
        }

        response = client.get(
            '/api/sysadmin/health',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['overall'] == 'healthy'
        assert len(data['services']) == 4
        assert 'timestamp' in data

    @patch('routes.sysadmin_health.check_openrouter_health')
    @patch('routes.sysadmin_health.check_sns_health')
    @patch('routes.sysadmin_health.check_cognito_health')
    @patch('routes.sysadmin_health.check_database_health')
    def test_health_one_degraded_returns_overall_degraded(
        self, mock_db_health, mock_cognito_health, mock_sns_health,
        mock_openrouter_health, client, mock_auth_sysadmin
    ):
        """Health endpoint returns overall degraded when one service is degraded."""
        mock_db_health.return_value = {
            'service': 'database',
            'status': 'healthy',
            'responseTime': 10,
            'message': 'Connected',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_cognito_health.return_value = {
            'service': 'cognito',
            'status': 'degraded',
            'responseTime': 1500,
            'message': 'Slow response',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_sns_health.return_value = {
            'service': 'sns',
            'status': 'healthy',
            'responseTime': 30,
            'message': 'OK',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_openrouter_health.return_value = {
            'service': 'openrouter',
            'status': 'healthy',
            'responseTime': 100,
            'message': 'OK',
            'lastChecked': '2024-01-01T00:00:00Z'
        }

        response = client.get(
            '/api/sysadmin/health',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['overall'] == 'degraded'

    @patch('routes.sysadmin_health.check_openrouter_health')
    @patch('routes.sysadmin_health.check_sns_health')
    @patch('routes.sysadmin_health.check_cognito_health')
    @patch('routes.sysadmin_health.check_database_health')
    def test_health_one_unhealthy_returns_overall_unhealthy(
        self, mock_db_health, mock_cognito_health, mock_sns_health,
        mock_openrouter_health, client, mock_auth_sysadmin
    ):
        """Health endpoint returns overall unhealthy when one service is unhealthy."""
        mock_db_health.return_value = {
            'service': 'database',
            'status': 'unhealthy',
            'responseTime': 5000,
            'message': 'Connection failed',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_cognito_health.return_value = {
            'service': 'cognito',
            'status': 'healthy',
            'responseTime': 50,
            'message': 'OK',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_sns_health.return_value = {
            'service': 'sns',
            'status': 'healthy',
            'responseTime': 30,
            'message': 'OK',
            'lastChecked': '2024-01-01T00:00:00Z'
        }
        mock_openrouter_health.return_value = {
            'service': 'openrouter',
            'status': 'healthy',
            'responseTime': 100,
            'message': 'OK',
            'lastChecked': '2024-01-01T00:00:00Z'
        }

        response = client.get(
            '/api/sysadmin/health',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['overall'] == 'unhealthy'

    @patch('routes.sysadmin_health.check_openrouter_health')
    @patch('routes.sysadmin_health.check_sns_health')
    @patch('routes.sysadmin_health.check_cognito_health')
    @patch('routes.sysadmin_health.check_database_health')
    def test_health_services_array_contains_all_services(
        self, mock_db_health, mock_cognito_health, mock_sns_health,
        mock_openrouter_health, client, mock_auth_sysadmin
    ):
        """Health endpoint returns services array with all 4 services."""
        for mock_fn, svc_name in [
            (mock_db_health, 'database'),
            (mock_cognito_health, 'cognito'),
            (mock_sns_health, 'sns'),
            (mock_openrouter_health, 'openrouter'),
        ]:
            mock_fn.return_value = {
                'service': svc_name,
                'status': 'healthy',
                'responseTime': 10,
                'message': f'{svc_name} OK',
                'lastChecked': '2024-01-01T00:00:00Z'
            }

        response = client.get(
            '/api/sysadmin/health',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        service_names = [s['service'] for s in data['services']]
        assert 'database' in service_names
        assert 'cognito' in service_names
        assert 'sns' in service_names
        assert 'openrouter' in service_names
