"""
Unit tests for Verification API routes.

Tests the sender verification endpoints:
- GET  /api/tenant-admin/sender-verification
- POST /api/tenant-admin/sender-verification/resend
- PUT  /api/tenant-admin/sender-verification/email

Covers:
- Permission checks (admin_manage required)
- Tenant isolation (only own administration)
- Request validation (missing/invalid email in PUT)
- Rate limit response (429) on resend

Requirements: 8.1–8.5, 3.4
Reference: .kiro/specs/ses-email-verification/design.md
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.verification_routes import verification_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal Flask app with the verification blueprint."""
    app = Flask(__name__)
    app.register_blueprint(verification_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


def _admin_auth_mocks(tenant='TestTenant'):
    """Patch stack for an authenticated Tenant_Admin user with admin_manage permission."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('admin@test.com', ['Tenant_Admin'], None)),
        patch('auth.cognito_utils.validate_permissions', return_value=(True, None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']),
        patch('auth.tenant_context.get_user_tenants', return_value=[tenant]),
        patch('auth.tenant_context.is_tenant_admin', return_value=True),
        patch('auth.tenant_context.get_current_tenant', return_value=tenant),
    ]


def _no_permission_auth_mocks(tenant='TestTenant'):
    """Patch stack for an authenticated user WITHOUT admin_manage permission."""
    error_response = {
        'statusCode': 403,
        'headers': {'Content-Type': 'application/json'},
        'body': '{"error": "Insufficient permissions", "details": "Missing permissions: admin_manage"}',
    }
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('user@test.com', ['Finance_Read'], None)),
        patch('auth.cognito_utils.validate_permissions',
              return_value=(False, error_response)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Finance_Read']),
        patch('auth.tenant_context.get_user_tenants', return_value=[tenant]),
        patch('auth.tenant_context.is_tenant_admin', return_value=False),
        patch('auth.tenant_context.get_current_tenant', return_value=tenant),
    ]


def _no_tenant_auth_mocks():
    """Patch stack for an authenticated user with admin_manage but no tenant access."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('admin@test.com', ['Tenant_Admin'], None)),
        patch('auth.cognito_utils.validate_permissions', return_value=(True, None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']),
        patch('auth.tenant_context.get_user_tenants', return_value=[]),
        patch('auth.tenant_context.is_tenant_admin', return_value=False),
        patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'),
    ]


def _headers(tenant='TestTenant'):
    """Standard request headers with auth and tenant."""
    return {
        'Authorization': 'Bearer fake-jwt-token',
        'X-Tenant': tenant,
        'Content-Type': 'application/json',
    }


# ---------------------------------------------------------------------------
# Tests: Permission checks (admin_manage required)
# Requirements: 8.4
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerificationRoutesPermissions:
    """Test that all verification endpoints require admin_manage permission."""

    def test_get_status_requires_admin_manage(self, client):
        """GET /sender-verification returns 403 for user without admin_manage."""
        mocks = _no_permission_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.get(
                '/api/tenant-admin/sender-verification',
                headers=_headers(),
            )
            assert resp.status_code == 403

    def test_resend_requires_admin_manage(self, client):
        """POST /sender-verification/resend returns 403 for user without admin_manage."""
        mocks = _no_permission_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.post(
                '/api/tenant-admin/sender-verification/resend',
                headers=_headers(),
            )
            assert resp.status_code == 403

    def test_update_email_requires_admin_manage(self, client):
        """PUT /sender-verification/email returns 403 for user without admin_manage."""
        mocks = _no_permission_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={'email': 'new@example.com'},
            )
            assert resp.status_code == 403

    def test_unauthenticated_request_returns_401(self, client):
        """Request without Authorization header returns 401."""
        resp = client.get(
            '/api/tenant-admin/sender-verification',
            headers={'X-Tenant': 'TestTenant'},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: Tenant isolation (only own administration)
# Requirements: 8.5
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerificationRoutesTenantIsolation:
    """Test that endpoints enforce tenant isolation."""

    def test_get_status_no_tenant_access_returns_403(self, client):
        """GET returns 403 when user has no access to the requested tenant."""
        mocks = _no_tenant_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.get(
                '/api/tenant-admin/sender-verification',
                headers=_headers(),
            )
            assert resp.status_code == 403

    def test_resend_no_tenant_access_returns_403(self, client):
        """POST resend returns 403 when user has no access to the requested tenant."""
        mocks = _no_tenant_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.post(
                '/api/tenant-admin/sender-verification/resend',
                headers=_headers(),
            )
            assert resp.status_code == 403

    def test_update_email_no_tenant_access_returns_403(self, client):
        """PUT email returns 403 when user has no access to the requested tenant."""
        mocks = _no_tenant_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={'email': 'new@example.com'},
            )
            assert resp.status_code == 403

    def test_service_called_with_correct_tenant(self, client):
        """Service is called with the authenticated tenant identifier."""
        tenant = 'GoodwinSolutions'
        mock_service = MagicMock()
        mock_service.check_status.return_value = {
            'email': 'admin@goodwin.com',
            'status': 'verified',
            'last_checked': '2025-01-15T10:30:00Z',
        }

        mocks = _admin_auth_mocks(tenant=tenant)
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.get(
                '/api/tenant-admin/sender-verification',
                headers=_headers(tenant=tenant),
            )
            assert resp.status_code == 200
            mock_service.check_status.assert_called_once_with(tenant)


# ---------------------------------------------------------------------------
# Tests: Request validation (missing/invalid email in PUT)
# Requirements: 8.3, 5.5
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerificationRoutesValidation:
    """Test request validation for the PUT email endpoint."""

    def test_put_missing_body_returns_400(self, client):
        """PUT with empty JSON object (no email field) returns 400."""
        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService'):
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={},
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['success'] is False
            assert 'email is required' in data['error']

    def test_put_empty_email_returns_400(self, client):
        """PUT with empty email string returns 400."""
        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService'):
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={'email': ''},
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['success'] is False
            assert 'email is required' in data['error']

    def test_put_missing_email_key_returns_400(self, client):
        """PUT with JSON body but no email key returns 400."""
        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService'):
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={'name': 'test'},
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['success'] is False
            assert 'email is required' in data['error']

    def test_put_invalid_email_returns_400_from_service(self, client):
        """PUT with invalid email returns 400 when service rejects it."""
        mock_service = MagicMock()
        mock_service.update_email.return_value = {
            'success': False,
            'error': 'Invalid email format',
        }

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={'email': 'not-an-email'},
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['success'] is False
            assert 'Invalid email format' in data['error']

    def test_put_valid_email_returns_200(self, client):
        """PUT with valid email returns 200 with pending status."""
        mock_service = MagicMock()
        mock_service.update_email.return_value = {
            'success': True,
            'status': 'pending',
        }

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.put(
                '/api/tenant-admin/sender-verification/email',
                headers=_headers(),
                json={'email': 'valid@example.com'},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['data']['email'] == 'valid@example.com'
            assert data['data']['status'] == 'pending'


# ---------------------------------------------------------------------------
# Tests: Rate limit response (429) on resend
# Requirements: 3.4
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerificationRoutesRateLimit:
    """Test rate limiting on the resend endpoint."""

    def test_resend_rate_limited_returns_429(self, client):
        """POST resend returns 429 when rate limited."""
        mock_service = MagicMock()
        mock_service.resend_verification.return_value = {
            'success': False,
            'error': 'Please wait 60 seconds before resending',
        }

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.post(
                '/api/tenant-admin/sender-verification/resend',
                headers=_headers(),
            )
            assert resp.status_code == 429
            data = resp.get_json()
            assert data['success'] is False
            assert '60 seconds' in data['error']

    def test_resend_success_returns_200(self, client):
        """POST resend returns 200 on success."""
        mock_service = MagicMock()
        mock_service.resend_verification.return_value = {
            'success': True,
        }

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.post(
                '/api/tenant-admin/sender-verification/resend',
                headers=_headers(),
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['message'] == 'Verification email resent'

    def test_resend_non_rate_limit_error_returns_400(self, client):
        """POST resend returns 400 for non-rate-limit errors."""
        mock_service = MagicMock()
        mock_service.resend_verification.return_value = {
            'success': False,
            'error': 'No verification record found',
        }

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.post(
                '/api/tenant-admin/sender-verification/resend',
                headers=_headers(),
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['success'] is False


# ---------------------------------------------------------------------------
# Tests: GET endpoint success responses
# Requirements: 8.1
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerificationRoutesGetStatus:
    """Test the GET status endpoint response format."""

    def test_get_status_returns_complete_response(self, client):
        """GET returns full status data including fallback sender."""
        mock_service = MagicMock()
        mock_service.check_status.return_value = {
            'email': 'tenant@example.com',
            'status': 'pending',
            'last_checked': '2025-01-15T10:30:00Z',
        }

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.get(
                '/api/tenant-admin/sender-verification',
                headers=_headers(),
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['data']['email'] == 'tenant@example.com'
            assert data['data']['status'] == 'pending'
            assert data['data']['last_checked'] == '2025-01-15T10:30:00Z'
            assert data['data']['fallback_sender'] == 'myAdmin <support@jabaki.nl>'

    def test_get_status_handles_service_error(self, client):
        """GET returns 500 when service raises an exception."""
        mock_service = MagicMock()
        mock_service.check_status.side_effect = Exception('Database connection failed')

        mocks = _admin_auth_mocks()
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], \
             patch('routes.verification_routes.DatabaseManager'), \
             patch('routes.verification_routes.EmailVerificationService', return_value=mock_service):
            resp = client.get(
                '/api/tenant-admin/sender-verification',
                headers=_headers(),
            )
            assert resp.status_code == 500
            data = resp.get_json()
            assert data['success'] is False
            assert 'Database connection failed' in data['error']
