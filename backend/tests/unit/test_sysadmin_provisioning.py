"""
Unit tests for SysAdmin Provisioning Endpoints

Tests the provisioning API with mocked dependencies:
- GET /api/sysadmin/provisioning/pending
- POST /api/sysadmin/provisioning/provision
- Helper functions: _generate_admin_name, _update_cognito_tenants
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

from routes.sysadmin_provisioning import (
    _generate_admin_name,
    _update_cognito_tenants,
    _send_admin_notification,
    _send_welcome_email,
)


# ============================================================================
# _generate_admin_name
# ============================================================================

class TestGenerateAdminName:

    def test_from_company_name(self):
        assert _generate_admin_name('Goodwin Solutions', 'user@example.com') == 'GoodwinSolutions'

    def test_from_email_when_no_company(self):
        assert _generate_admin_name('', 'peter@jabaki.nl') == 'Peter'

    def test_strips_special_chars(self):
        assert _generate_admin_name('My Company! #1', 'x@y.com') == 'MyCompany1'

    def test_empty_both_returns_default(self):
        assert _generate_admin_name('', '@') == 'NewTenant'

    def test_truncates_to_50(self):
        long_name = 'A' * 100
        result = _generate_admin_name(long_name, 'x@y.com')
        assert len(result) <= 50


# ============================================================================
# _update_cognito_tenants
#
# Bugfix cognito-admin-pool-resolution (task 3.3.7): the target pool is resolved per
# request via the shared registry-backed resolver in EMAIL mode (keyed to the target
# user's email), not read from the legacy COGNITO_USER_POOL_ID var. The explicit
# SIGNUP_COGNITO_USER_POOL_ID override is preserved (fast-path); only the former nested
# legacy fallback is replaced. Registry-absent -> resolver falls back to the legacy
# var, so single-pool deployments are observably unchanged.
# ============================================================================

class TestUpdateCognitoTenants:

    @patch('routes.sysadmin_provisioning.resolve_pool_id_for_email',
           return_value='eu-west-1_TestPool')
    @patch('routes.sysadmin_provisioning.boto3')
    @patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}, clear=False)
    def test_adds_tenant_to_empty_list(self, mock_boto3, mock_resolve):
        import os as _os
        _os.environ.pop('SIGNUP_COGNITO_USER_POOL_ID', None)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.admin_get_user.return_value = {
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '[]'}
            ]
        }

        result = _update_cognito_tenants('user@test.com', 'NewTenant')

        assert result is None
        # Resolver was consulted for the target user and its result was threaded in.
        mock_resolve.assert_called_once_with('user@test.com')
        assert mock_client.admin_get_user.call_args[1]['UserPoolId'] == 'eu-west-1_TestPool'
        mock_client.admin_update_user_attributes.assert_called_once()
        call_attrs = mock_client.admin_update_user_attributes.call_args[1]['UserAttributes']
        tenants = json.loads(call_attrs[0]['Value'])
        assert 'NewTenant' in tenants
        # The resolved pool id is also threaded into the update call.
        assert mock_client.admin_update_user_attributes.call_args[1]['UserPoolId'] == 'eu-west-1_TestPool'

    @patch('routes.sysadmin_provisioning.resolve_pool_id_for_email',
           return_value='eu-west-1_TestPool')
    @patch('routes.sysadmin_provisioning.boto3')
    @patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}, clear=False)
    def test_skips_if_tenant_already_present(self, mock_boto3, mock_resolve):
        import os as _os
        _os.environ.pop('SIGNUP_COGNITO_USER_POOL_ID', None)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.admin_get_user.return_value = {
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '["ExistingTenant"]'}
            ]
        }

        result = _update_cognito_tenants('user@test.com', 'ExistingTenant')

        assert result is None
        mock_client.admin_update_user_attributes.assert_not_called()

    @patch('routes.sysadmin_provisioning.resolve_pool_id_for_email',
           return_value='eu-west-1_TestPool')
    @patch('routes.sysadmin_provisioning.boto3')
    @patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}, clear=False)
    def test_returns_error_on_failure(self, mock_boto3, mock_resolve):
        import os as _os
        _os.environ.pop('SIGNUP_COGNITO_USER_POOL_ID', None)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.admin_get_user.side_effect = Exception('User not found')

        result = _update_cognito_tenants('user@test.com', 'NewTenant')

        assert result is not None
        assert 'User not found' in result

    @patch('routes.sysadmin_provisioning.resolve_pool_id_for_email')
    @patch('routes.sysadmin_provisioning.boto3')
    @patch.dict('os.environ', {
        'AWS_REGION': 'eu-west-1',
        'SIGNUP_COGNITO_USER_POOL_ID': 'eu-west-1_SignupPool',
    }, clear=False)
    def test_prefers_explicit_signup_override(self, mock_boto3, mock_resolve):
        """When SIGNUP_COGNITO_USER_POOL_ID is set it wins (fast-path); resolver unused."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.admin_get_user.return_value = {
            'UserAttributes': [{'Name': 'custom:tenants', 'Value': '[]'}]
        }

        result = _update_cognito_tenants('user@test.com', 'NewTenant')

        assert result is None
        mock_resolve.assert_not_called()
        assert mock_client.admin_get_user.call_args[1]['UserPoolId'] == 'eu-west-1_SignupPool'

    @patch('routes.sysadmin_provisioning.resolve_pool_id_for_email',
           side_effect=__import__('auth.admin_pool_resolver', fromlist=['UserPoolNotFoundError']).UserPoolNotFoundError('user@test.com'))
    @patch('routes.sysadmin_provisioning.boto3')
    @patch.dict('os.environ', {'AWS_REGION': 'eu-west-1'}, clear=False)
    def test_resolver_error_returns_warning_string_not_raise(self, mock_boto3, mock_resolve):
        """A resolver failure is caught and surfaced as the warning string (contract preserved)."""
        import os as _os
        _os.environ.pop('SIGNUP_COGNITO_USER_POOL_ID', None)
        mock_boto3.client.return_value = MagicMock()

        result = _update_cognito_tenants('user@test.com', 'NewTenant')

        assert result is not None
        assert 'user@test.com' in result


# ============================================================================
# _send_welcome_email
# ============================================================================

class TestSendWelcomeEmail:

    @patch('services.ses_email_service.SESEmailService')
    @patch('utils.frontend_url.get_frontend_url', return_value='https://example.com/myAdmin')
    def test_sends_nl_email(self, mock_url, mock_ses_cls):
        mock_ses = MagicMock()
        mock_ses.is_enabled.return_value = True
        mock_ses_cls.return_value = mock_ses

        _send_welcome_email('user@test.com', 'TestTenant', 'Peter', 'nl')

        mock_ses.send_email.assert_called_once()
        call_args = mock_ses.send_email.call_args
        assert call_args[1]['to_email'] == 'user@test.com'
        assert 'Welkom' in call_args[1]['subject']
        assert 'TestTenant' in call_args[1]['html_body']

    @patch('services.ses_email_service.SESEmailService')
    @patch('utils.frontend_url.get_frontend_url', return_value='https://example.com/myAdmin')
    def test_sends_en_email(self, mock_url, mock_ses_cls):
        mock_ses = MagicMock()
        mock_ses.is_enabled.return_value = True
        mock_ses_cls.return_value = mock_ses

        _send_welcome_email('user@test.com', 'TestTenant', 'Peter', 'en')

        call_args = mock_ses.send_email.call_args
        assert 'Welcome' in call_args[1]['subject']

    @patch('services.ses_email_service.SESEmailService')
    def test_skips_when_ses_disabled(self, mock_ses_cls):
        mock_ses = MagicMock()
        mock_ses.is_enabled.return_value = False
        mock_ses_cls.return_value = mock_ses

        _send_welcome_email('user@test.com', 'TestTenant', 'Peter', 'nl')

        mock_ses.send_email.assert_not_called()

    @patch('services.ses_email_service.SESEmailService', side_effect=Exception('SES init failed'))
    def test_does_not_raise_on_failure(self, mock_ses_cls):
        # Should not raise — welcome email is non-critical
        _send_welcome_email('user@test.com', 'TestTenant', 'Peter', 'nl')


# ============================================================================
# _send_admin_notification
# ============================================================================

class TestSendAdminNotification:

    @patch('aws_notifications.get_notification_service')
    def test_sends_notification(self, mock_get_service):
        mock_service = MagicMock()
        mock_service.is_enabled.return_value = True
        mock_get_service.return_value = mock_service

        _send_admin_notification('user@test.com', 'TestTenant', 'Peter')

        mock_service.send_business_notification.assert_called_once()

    @patch('aws_notifications.get_notification_service', side_effect=Exception('SNS failed'))
    def test_does_not_raise_on_failure(self, mock_get_service):
        # Should not raise — notification is non-critical
        _send_admin_notification('user@test.com', 'TestTenant', 'Peter')
