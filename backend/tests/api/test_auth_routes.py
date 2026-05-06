"""
API tests for auth_routes.py

Tests forgot-password flow, confirm-reset code validation, and /me endpoint
authentication enforcement. Verifies anti-enumeration behavior, code expiry,
max attempts, and input validation.

Requirements: 6.1, 6.2, 6.5, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestAuthRoutesAuthEnforcement:
    """Verify /me endpoint requires authentication."""

    def test_me_unauthenticated_returns_401(self, client):
        """GET /api/auth/me without token should return 401."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Missing Authorization header"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/auth/me')
        assert response.status_code == 401

    def test_me_authenticated_returns_user_info(self, client, mock_auth):
        """GET /api/auth/me with valid token should return email and roles."""
        response = client.get('/api/auth/me', headers=mock_auth)
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'email' in data
        assert 'roles' in data


# ============================================================================
# Forgot Password Tests
# ============================================================================


class TestForgotPassword:
    """Tests for POST /api/auth/forgot-password."""

    def test_forgot_password_missing_email_returns_400(self, client, mock_env):
        """Missing email field should return 400."""
        response = client.post(
            '/api/auth/forgot-password',
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'email' in data['error'].lower()

    def test_forgot_password_empty_email_returns_400(self, client, mock_env):
        """Empty email string should return 400."""
        response = client.post(
            '/api/auth/forgot-password',
            json={'email': ''}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('services.ses_email_service.SESEmailService')
    @patch('services.email_template_service.EmailTemplateService')
    @patch('routes.auth_routes._get_db')
    @patch('routes.auth_routes.boto3.client')
    def test_forgot_password_nonexistent_user_returns_success(
        self, mock_boto_client, mock_get_db, mock_email_tmpl, mock_ses,
        client, mock_env
    ):
        """Non-existent user should still return success (anti-enumeration)."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_get_user.side_effect = ClientError(
            {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}},
            'AdminGetUser'
        )

        response = client.post(
            '/api/auth/forgot-password',
            json={'email': 'nonexistent@example.com'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'if an account exists' in data['message'].lower()

    @patch('services.ses_email_service.SESEmailService')
    @patch('services.email_template_service.EmailTemplateService')
    @patch('routes.auth_routes._get_db')
    @patch('routes.auth_routes.boto3.client')
    def test_forgot_password_existing_user_returns_success(
        self, mock_boto_client, mock_get_db, mock_email_tmpl, mock_ses,
        client, mock_env
    ):
        """Existing user should return success and send email."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_get_user.return_value = {
            'Username': 'user@example.com',
            'UserStatus': 'CONFIRMED',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ]
        }

        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance

        mock_ses_instance = MagicMock()
        mock_ses.return_value = mock_ses_instance

        mock_tmpl_instance = MagicMock()
        mock_email_tmpl.return_value = mock_tmpl_instance
        mock_tmpl_instance.render_template.return_value = '<html>Reset code</html>'

        response = client.post(
            '/api/auth/forgot-password',
            json={'email': 'user@example.com'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify DB operations: delete old code + insert new code
        assert mock_db_instance.execute_query.call_count >= 2
        # Verify email was sent
        mock_ses_instance.send_email.assert_called_once()

    @patch('services.ses_email_service.SESEmailService')
    @patch('services.email_template_service.EmailTemplateService')
    @patch('routes.auth_routes._get_db')
    @patch('routes.auth_routes.boto3.client')
    def test_forgot_password_force_change_password_user_returns_success(
        self, mock_boto_client, mock_get_db, mock_email_tmpl, mock_ses,
        client, mock_env
    ):
        """User in FORCE_CHANGE_PASSWORD status should get success but no email."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_get_user.return_value = {
            'Username': 'newuser@example.com',
            'UserStatus': 'FORCE_CHANGE_PASSWORD',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'newuser@example.com'},
            ]
        }

        response = client.post(
            '/api/auth/forgot-password',
            json={'email': 'newuser@example.com'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        # No email should be sent for FORCE_CHANGE_PASSWORD users
        mock_ses.assert_not_called()

    @patch('services.ses_email_service.SESEmailService')
    @patch('services.email_template_service.EmailTemplateService')
    @patch('routes.auth_routes._get_db')
    @patch('routes.auth_routes.boto3.client')
    def test_forgot_password_anti_enumeration_same_response(
        self, mock_boto_client, mock_get_db, mock_email_tmpl, mock_ses,
        client, mock_env
    ):
        """Response message should be identical for existing and non-existing users."""
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        # First request: user doesn't exist
        mock_cognito.admin_get_user.side_effect = ClientError(
            {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}},
            'AdminGetUser'
        )
        response_nonexistent = client.post(
            '/api/auth/forgot-password',
            json={'email': 'nobody@example.com'}
        )

        # Second request: user exists
        mock_cognito.admin_get_user.side_effect = None
        mock_cognito.admin_get_user.return_value = {
            'Username': 'real@example.com',
            'UserStatus': 'CONFIRMED',
            'UserAttributes': [{'Name': 'email', 'Value': 'real@example.com'}]
        }
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        mock_ses_instance = MagicMock()
        mock_ses.return_value = mock_ses_instance
        mock_tmpl_instance = MagicMock()
        mock_email_tmpl.return_value = mock_tmpl_instance
        mock_tmpl_instance.render_template.return_value = '<html></html>'

        response_existing = client.post(
            '/api/auth/forgot-password',
            json={'email': 'real@example.com'}
        )

        # Both should have same message
        data_nonexistent = json.loads(response_nonexistent.data)
        data_existing = json.loads(response_existing.data)
        assert data_nonexistent['message'] == data_existing['message']


# ============================================================================
# Confirm Reset Password Tests
# ============================================================================


class TestConfirmResetPassword:
    """Tests for POST /api/auth/confirm-reset."""

    def test_confirm_reset_missing_email_returns_400(self, client, mock_env):
        """Missing email should return 400."""
        response = client.post(
            '/api/auth/confirm-reset',
            json={'code': '123456', 'new_password': 'NewPass123!'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_confirm_reset_missing_code_returns_400(self, client, mock_env):
        """Missing code should return 400."""
        response = client.post(
            '/api/auth/confirm-reset',
            json={'email': 'user@example.com', 'new_password': 'NewPass123!'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_confirm_reset_missing_password_returns_400(self, client, mock_env):
        """Missing new_password should return 400."""
        response = client.post(
            '/api/auth/confirm-reset',
            json={'email': 'user@example.com', 'code': '123456'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('routes.auth_routes.boto3.client')
    @patch('routes.auth_routes._get_db')
    def test_confirm_reset_no_code_found_returns_400(
        self, mock_get_db, mock_boto_client, client, mock_env
    ):
        """No reset code in DB should return 400."""
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        mock_db_instance.execute_query.return_value = []

        response = client.post(
            '/api/auth/confirm-reset',
            json={
                'email': 'user@example.com',
                'code': '123456',
                'new_password': 'NewPass123!'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'no reset code' in data['error'].lower()

    @patch('routes.auth_routes.boto3.client')
    @patch('routes.auth_routes._get_db')
    def test_confirm_reset_expired_code_returns_400(
        self, mock_get_db, mock_boto_client, client, mock_env
    ):
        """Expired code should return 400 and be deleted."""
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        # Return expired code
        expired_time = datetime.utcnow() - timedelta(minutes=15)
        mock_db_instance.execute_query.return_value = [
            {'code': '123456', 'expires_at': expired_time, 'attempts': 0}
        ]

        response = client.post(
            '/api/auth/confirm-reset',
            json={
                'email': 'user@example.com',
                'code': '123456',
                'new_password': 'NewPass123!'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'expired' in data['error'].lower()

    @patch('routes.auth_routes.boto3.client')
    @patch('routes.auth_routes._get_db')
    def test_confirm_reset_max_attempts_returns_429(
        self, mock_get_db, mock_boto_client, client, mock_env
    ):
        """Exceeding max attempts should return 429 and delete code."""
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        future_time = datetime.utcnow() + timedelta(minutes=5)
        mock_db_instance.execute_query.return_value = [
            {'code': '123456', 'expires_at': future_time, 'attempts': 3}
        ]

        response = client.post(
            '/api/auth/confirm-reset',
            json={
                'email': 'user@example.com',
                'code': '999999',
                'new_password': 'NewPass123!'
            }
        )
        assert response.status_code == 429
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'too many attempts' in data['error'].lower()

    @patch('routes.auth_routes.boto3.client')
    @patch('routes.auth_routes._get_db')
    def test_confirm_reset_invalid_code_increments_attempts(
        self, mock_get_db, mock_boto_client, client, mock_env
    ):
        """Wrong code should increment attempts and return 400."""
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        future_time = datetime.utcnow() + timedelta(minutes=5)
        mock_db_instance.execute_query.return_value = [
            {'code': '123456', 'expires_at': future_time, 'attempts': 1}
        ]

        response = client.post(
            '/api/auth/confirm-reset',
            json={
                'email': 'user@example.com',
                'code': '999999',
                'new_password': 'NewPass123!'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'invalid code' in data['error'].lower()
        assert '1 attempt(s) remaining' in data['error'].lower()

    @patch('routes.auth_routes.boto3.client')
    @patch('routes.auth_routes._get_db')
    def test_confirm_reset_valid_code_sets_password(
        self, mock_get_db, mock_boto_client, client, mock_env
    ):
        """Valid code should set password via Cognito and return success."""
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        future_time = datetime.utcnow() + timedelta(minutes=5)
        mock_db_instance.execute_query.return_value = [
            {'code': '123456', 'expires_at': future_time, 'attempts': 0}
        ]

        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        response = client.post(
            '/api/auth/confirm-reset',
            json={
                'email': 'user@example.com',
                'code': '123456',
                'new_password': 'NewSecurePass123!'
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # Verify Cognito was called to set password
        mock_cognito.admin_set_user_password.assert_called_once_with(
            UserPoolId='us-east-1_test',
            Username='user@example.com',
            Password='NewSecurePass123!',
            Permanent=True,
        )

    @patch('routes.auth_routes.boto3.client')
    @patch('routes.auth_routes._get_db')
    def test_confirm_reset_cognito_error_returns_400(
        self, mock_get_db, mock_boto_client, client, mock_env
    ):
        """Cognito password set failure should return 400."""
        mock_db_instance = MagicMock()
        mock_get_db.return_value = mock_db_instance
        future_time = datetime.utcnow() + timedelta(minutes=5)
        mock_db_instance.execute_query.return_value = [
            {'code': '123456', 'expires_at': future_time, 'attempts': 0}
        ]

        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito
        mock_cognito.admin_set_user_password.side_effect = ClientError(
            {'Error': {'Code': 'InvalidPasswordException', 'Message': 'Password too weak'}},
            'AdminSetUserPassword'
        )

        response = client.post(
            '/api/auth/confirm-reset',
            json={
                'email': 'user@example.com',
                'code': '123456',
                'new_password': 'weak'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'password' in data['error'].lower()
