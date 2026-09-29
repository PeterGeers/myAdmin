"""
API tests for tenant_admin_email.py

Tests email sending, template listing, and invitation resend endpoints,
including authentication enforcement and input validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def tenant_admin_auth():
    """
    Mock authentication with Tenant_Admin role for tenant admin endpoints.
    """
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']):
        mock_creds.return_value = ('admin@example.com', ['Tenant_Admin'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTenantAdminEmailAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_send_email_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to send email should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/tenant-admin/send-email',
                json={'email': 'user@example.com', 'template_type': 'user_invitation'}
            )
        assert response.status_code in (401, 403)

    def test_list_templates_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list templates should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/email-templates')
        assert response.status_code in (401, 403)


# ============================================================================
# Send Email Tests
# ============================================================================


class TestTenantAdminEmailSend:
    """Tests for POST /api/tenant-admin/send-email."""

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    def test_send_email_no_data_returns_400(
        self, mock_tenant, client, tenant_admin_auth
    ):
        """Send email with empty body should return 400."""
        response = client.post(
            '/api/tenant-admin/send-email',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'no data' in data['error'].lower()

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    def test_send_email_missing_email_returns_400(
        self, mock_tenant, client, tenant_admin_auth
    ):
        """Send email without recipient email should return 400."""
        response = client.post(
            '/api/tenant-admin/send-email',
            headers=tenant_admin_auth,
            json={'template_type': 'user_invitation'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'email' in data['error'].lower()

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    def test_send_email_invalid_template_returns_400(
        self, mock_tenant, client, tenant_admin_auth
    ):
        """Send email with invalid template type should return 400."""
        response = client.post(
            '/api/tenant-admin/send-email',
            headers=tenant_admin_auth,
            json={'email': 'user@example.com', 'template_type': 'invalid_template'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'invalid template' in data['error'].lower()

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_email.EmailTemplateService')
    @patch('routes.tenant_admin_email.CognitoService')
    @patch('services.ses_email_service.SESEmailService')
    @patch('utils.frontend_url.get_frontend_url', return_value='http://localhost:3000')
    def test_send_email_success(
        self, mock_url, mock_ses_class, mock_cognito_class, mock_email_class,
        mock_tenant, client, tenant_admin_auth
    ):
        """Valid email send should return 200."""
        mock_email_service = MagicMock()
        mock_email_class.return_value = mock_email_service
        mock_email_service.render_template.return_value = '<html>Email</html>'
        mock_email_service.get_invitation_subject.return_value = 'Welcome'

        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {'success': True, 'message_id': 'test-123'}

        with patch('services.ses_email_service.SESEmailService', return_value=mock_ses), \
             patch('builtins.__import__', wraps=__import__):
            # Patch the SES import inside the function
            import services.ses_email_service
            with patch.object(services.ses_email_service, 'SESEmailService', return_value=mock_ses):
                response = client.post(
                    '/api/tenant-admin/send-email',
                    headers=tenant_admin_auth,
                    json={
                        'email': 'user@example.com',
                        'template_type': 'user_invitation',
                        'user_data': {'name': 'Test User'}
                    }
                )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# List Email Templates Tests
# ============================================================================


class TestTenantAdminEmailTemplates:
    """Tests for GET /api/tenant-admin/email-templates."""

    def test_list_templates_returns_data(self, client, tenant_admin_auth):
        """Authenticated request should return list of templates."""
        response = client.get(
            '/api/tenant-admin/email-templates',
            headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'templates' in data
        assert len(data['templates']) == 3
        template_types = [t['template_type'] for t in data['templates']]
        assert 'user_invitation' in template_types
        assert 'password_reset' in template_types
        assert 'account_update' in template_types


# ============================================================================
# Resend Invitation Tests
# ============================================================================


class TestTenantAdminResendInvitation:
    """Tests for POST /api/tenant-admin/resend-invitation."""

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    def test_resend_invitation_no_data_returns_400(
        self, mock_tenant, client, tenant_admin_auth
    ):
        """Resend invitation with empty body should return 400."""
        response = client.post(
            '/api/tenant-admin/resend-invitation',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'no data' in data['error'].lower()

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    def test_resend_invitation_missing_email_returns_400(
        self, mock_tenant, client, tenant_admin_auth
    ):
        """Resend invitation without email should return 400."""
        response = client.post(
            '/api/tenant-admin/resend-invitation',
            headers=tenant_admin_auth,
            json={'username': 'test-uuid'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'email' in data['error'].lower()


# ============================================================================
# Pool Resolution Tests (cognito-admin-pool-resolution, Task 3.3.10)
# ============================================================================


class TestTenantAdminEmailPoolResolution:
    """Verify admin Cognito ops thread the registry-resolved pool id (token mode).

    Both legacy ``COGNITO_USER_POOL_ID`` sites (the send-email best-effort lookup
    and the resend-invitation password-set) now resolve the target pool via the
    shared registry-backed resolver keyed to the caller token's verified ``iss``.

    Validates: Requirements 2.1, 2.3, 2.4, 3.3
    """

    RESOLVED_POOL = 'eu-west-1_xyrlzfqbl'

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_email._resolve_pool_id')
    @patch('routes.tenant_admin_email.EmailTemplateService')
    @patch('routes.tenant_admin_email.CognitoService')
    @patch('boto3.client')
    @patch('utils.frontend_url.get_frontend_url', return_value='http://localhost:3000')
    def test_send_email_uses_resolved_pool_for_admin_get_user(
        self, mock_url, mock_boto, mock_cognito_class, mock_email_class,
        mock_resolve, mock_tenant, client, tenant_admin_auth
    ):
        """send-email must pass the registry-resolved pool to admin_get_user."""
        mock_resolve.return_value = self.RESOLVED_POOL

        mock_cognito_client = MagicMock()
        mock_cognito_client.admin_get_user.return_value = {
            'UserAttributes': [{'Name': 'name', 'Value': 'Resolved Name'}]
        }
        mock_boto.return_value = mock_cognito_client

        mock_email_service = MagicMock()
        mock_email_class.return_value = mock_email_service
        mock_email_service.render_template.return_value = '<html>Email</html>'
        mock_email_service.get_invitation_subject.return_value = 'Welcome'

        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {'success': True, 'message_id': 'test-123'}

        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            response = client.post(
                '/api/tenant-admin/send-email',
                headers=tenant_admin_auth,
                # No 'name' in user_data => triggers the admin_get_user lookup.
                json={
                    'email': 'user@example.com',
                    'template_type': 'user_invitation',
                    'user_data': {'username': 'user-uuid'},
                }
            )

        assert response.status_code == 200
        mock_resolve.assert_called()
        # The resolved pool id must be threaded into the admin call.
        _, kwargs = mock_cognito_client.admin_get_user.call_args
        assert kwargs['UserPoolId'] == self.RESOLVED_POOL

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_email._resolve_pool_id')
    @patch('routes.tenant_admin_email.InvitationService')
    @patch('routes.tenant_admin_email.EmailTemplateService')
    @patch('boto3.client')
    @patch('utils.frontend_url.get_frontend_url', return_value='http://localhost:3000')
    def test_resend_invitation_uses_resolved_pool_for_password_set(
        self, mock_url, mock_boto, mock_email_class, mock_inv_class,
        mock_resolve, mock_tenant, client, tenant_admin_auth
    ):
        """resend-invitation must pass the resolved pool to admin_set_user_password."""
        mock_resolve.return_value = self.RESOLVED_POOL

        mock_inv = MagicMock()
        mock_inv_class.return_value = mock_inv
        mock_inv.resend_invitation.return_value = {
            'success': True,
            'temporary_password': 'TempPass123!',
            'expires_at': '2030-01-01',
            'expiry_days': 7,
        }

        mock_cognito_client = MagicMock()
        mock_cognito_client.admin_get_user.return_value = {
            'UserAttributes': [{'Name': 'name', 'Value': 'Resolved Name'}]
        }
        mock_boto.return_value = mock_cognito_client

        mock_email_service = MagicMock()
        mock_email_class.return_value = mock_email_service
        mock_email_service.render_template.return_value = '<html>Email</html>'
        mock_email_service.get_invitation_subject.return_value = 'Welcome'

        mock_ses = MagicMock()
        mock_ses.send_invitation.return_value = {'success': True, 'message_id': 'x'}

        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            response = client.post(
                '/api/tenant-admin/resend-invitation',
                headers=tenant_admin_auth,
                json={'email': 'user@example.com', 'username': 'user-uuid'}
            )

        assert response.status_code == 200
        # Both admin ops must act on the registry-resolved pool.
        _, set_kwargs = mock_cognito_client.admin_set_user_password.call_args
        assert set_kwargs['UserPoolId'] == self.RESOLVED_POOL
        _, get_kwargs = mock_cognito_client.admin_get_user.call_args
        assert get_kwargs['UserPoolId'] == self.RESOLVED_POOL

    @patch('routes.tenant_admin_email.get_current_tenant', return_value='test-tenant')
    @patch('routes.tenant_admin_email._resolve_pool_id')
    @patch('routes.tenant_admin_email.InvitationService')
    @patch('routes.tenant_admin_email.EmailTemplateService')
    @patch('boto3.client')
    def test_resend_invitation_pool_resolution_failure_returns_500(
        self, mock_boto, mock_email_class, mock_inv_class,
        mock_resolve, mock_tenant, client, tenant_admin_auth
    ):
        """A genuine pool-resolution misconfig maps to the 500 password-fail contract."""
        from auth.admin_pool_resolver import PoolResolutionError
        mock_resolve.side_effect = PoolResolutionError('registry misconfigured')

        mock_inv = MagicMock()
        mock_inv_class.return_value = mock_inv
        mock_inv.resend_invitation.return_value = {
            'success': True,
            'temporary_password': 'TempPass123!',
        }

        mock_boto.return_value = MagicMock()
        mock_email_class.return_value = MagicMock()

        response = client.post(
            '/api/tenant-admin/resend-invitation',
            headers=tenant_admin_auth,
            json={'email': 'user@example.com', 'username': 'user-uuid'}
        )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['error'] == 'Failed to update user password'
        mock_inv.mark_invitation_failed.assert_called()
