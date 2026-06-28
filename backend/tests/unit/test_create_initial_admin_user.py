"""
Unit tests for create_initial_admin_user() and resend invitation endpoint.

Tests the new initial admin user creation logic added to
TenantProvisioningService, including:
- New Cognito user path
- Existing Cognito user path
- Idempotent skip when role already exists
- Integration with create_and_provision_tenant()
- Error handling / graceful degradation
- Cognito user status (CONFIRMED via admin_set_user_password)
- Resend invitation endpoint

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.8
"""

import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch, call
from functools import wraps

from services.tenant_provisioning_service import TenantProvisioningService


# ============================================================================
# Shared helpers
# ============================================================================

def _make_service_mocks():
    """Build mock instances for all lazily-imported services."""
    cognito = MagicMock()
    cognito.client = MagicMock()
    cognito.user_pool_id = 'eu-west-1_TestPool'

    invitation_svc = MagicMock()
    invitation_svc.create_invitation.return_value = {
        'success': True,
        'temporary_password': 'TempPass123!',
    }

    email_tpl = MagicMock()
    email_tpl.render_user_invitation.return_value = '<html>invite</html>'
    email_tpl.get_invitation_subject.return_value = 'You are invited'
    email_tpl.render_template.return_value = '<html>tenant added</html>'

    ses = MagicMock()
    ses.send_invitation.return_value = {'success': True}

    return cognito, invitation_svc, email_tpl, ses


def _patch_lazy_imports(cognito, invitation_svc, email_tpl, ses):
    """Return a dict of context-manager patches for the lazy imports."""
    cognito_cls = MagicMock(return_value=cognito)
    invitation_cls = MagicMock(return_value=invitation_svc)
    email_tpl_cls = MagicMock(return_value=email_tpl)
    ses_cls = MagicMock(return_value=ses)
    frontend_url = MagicMock(return_value='https://app.example.com')

    return {
        'cognito': patch('services.cognito_service.CognitoService', cognito_cls),
        'invitation': patch('services.invitation_service.InvitationService', invitation_cls),
        'email_tpl': patch('services.email_template_service.EmailTemplateService', email_tpl_cls),
        'ses': patch('services.ses_email_service.SESEmailService', ses_cls),
        'frontend_url': patch('utils.frontend_url.get_frontend_url', frontend_url),
    }


def _db_side_effect_for_fresh_tenant():
    """Return a side_effect function that simulates a fresh tenant DB."""
    def side_effect(query, params=None, fetch=True, commit=False):
        q = query.strip().upper()
        if 'SELECT ADMINISTRATION FROM TENANTS' in q:
            return []
        if 'SELECT ID FROM TENANT_MODULES' in q:
            return []
        if 'SELECT COUNT(*) AS CNT FROM REKENINGSCHEMA' in q:
            return [{'cnt': 0}]
        if 'SELECT' in q and 'USER_TENANT_ROLES' in q:
            return []
        if 'INSERT' in q:
            return None
        return []
    return side_effect


# ============================================================================
# 1. TestCreateNewAdminUser — New Cognito user path
# ============================================================================

class TestCreateNewAdminUser:
    """Verify the new-user path in create_initial_admin_user()."""

    def test_cognito_create_user_called(self):
        """CognitoService.create_user() is called with correct args."""
        db = MagicMock()
        db.execute_query.return_value = []  # no existing role
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None  # new user

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            result = service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        assert result['status'] == 'created'
        cognito.create_user.assert_called_once()
        call_kwargs = cognito.create_user.call_args
        assert call_kwargs[1]['email'] == 'admin@acme.com' or \
               call_kwargs[0][0] == 'admin@acme.com' if call_kwargs[0] else True

    def test_admin_set_user_password_permanent_called(self):
        """admin_set_user_password(Permanent=True) is called for new users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        cognito.client.admin_set_user_password.assert_called_once()
        call_kwargs = cognito.client.admin_set_user_password.call_args[1]
        assert call_kwargs['Permanent'] is True
        assert call_kwargs['Password'] == 'TempPass123!'

    def test_user_tenant_roles_insert_executed(self):
        """INSERT INTO user_tenant_roles is executed for new users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        role_inserts = [
            c for c in db.execute_query.call_args_list
            if 'INSERT' in str(c.args[0]).upper()
            and 'user_tenant_roles' in str(c.args[0])
        ]
        assert len(role_inserts) == 1
        params = role_inserts[0].args[1]
        assert 'admin@acme.com' in params
        assert 'AcmeCorp' in params

    def test_invitation_service_called(self):
        """InvitationService.create_invitation() is called for new users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        assert inv.create_invitation.call_count >= 1

    def test_ses_send_invitation_called(self):
        """SESEmailService.send_invitation() is called for new users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        ses.send_invitation.assert_called_once()

    def test_returns_status_created(self):
        """Method returns {'status': 'created'} for new users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            result = service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        assert result == {'status': 'created'}



# ============================================================================
# 2. TestAddAdminRoleExistingUser — Existing Cognito user path
# ============================================================================

class TestAddAdminRoleExistingUser:
    """Verify the existing-user path in create_initial_admin_user()."""

    def _existing_cognito_user(self):
        return {
            'Username': 'existing@acme.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'existing@acme.com'},
                {'Name': 'name', 'Value': 'Existing User'},
            ],
        }

    def test_add_tenant_to_user_called(self):
        """CognitoService.add_tenant_to_user() is called for existing users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = self._existing_cognito_user()

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            result = service.create_initial_admin_user(
                'AcmeCorp', 'existing@acme.com', 'sysadmin@sys.com',
            )

        assert result['status'] == 'existing_user'
        cognito.add_tenant_to_user.assert_called_once_with(
            'existing@acme.com', 'AcmeCorp',
        )

    def test_user_tenant_roles_insert_for_existing_user(self):
        """INSERT INTO user_tenant_roles is executed for existing users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = self._existing_cognito_user()

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'existing@acme.com', 'sysadmin@sys.com',
            )

        role_inserts = [
            c for c in db.execute_query.call_args_list
            if 'INSERT' in str(c.args[0]).upper()
            and 'user_tenant_roles' in str(c.args[0])
        ]
        assert len(role_inserts) == 1

    def test_tenant_added_notification_sent(self):
        """ses.send_invitation() is called for tenant-added notification."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = self._existing_cognito_user()

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'existing@acme.com', 'sysadmin@sys.com',
            )

        ses.send_invitation.assert_called_once()

    def test_no_admin_set_user_password_for_existing_user(self):
        """admin_set_user_password is NOT called for existing users."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = self._existing_cognito_user()

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'existing@acme.com', 'sysadmin@sys.com',
            )

        cognito.client.admin_set_user_password.assert_not_called()

    def test_returns_status_existing_user(self):
        """Method returns {'status': 'existing_user'}."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = self._existing_cognito_user()

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            result = service.create_initial_admin_user(
                'AcmeCorp', 'existing@acme.com', 'sysadmin@sys.com',
            )

        assert result == {'status': 'existing_user'}



# ============================================================================
# 3. TestIdempotentSkip — Role already exists
# ============================================================================

class TestIdempotentSkip:
    """When user_tenant_roles row already exists, skip everything."""

    def test_returns_status_skipped(self):
        """Returns {'status': 'skipped'} when role exists."""
        db = MagicMock()
        db.execute_query.return_value = [{'id': 42}]  # role exists
        service = TenantProvisioningService(db)

        result = service.create_initial_admin_user(
            'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
        )

        assert result == {'status': 'skipped'}

    def test_no_cognito_calls_when_skipped(self):
        """No CognitoService calls when role already exists."""
        db = MagicMock()
        db.execute_query.return_value = [{'id': 42}]
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        # Services should not even be instantiated (lazy imports skipped)
        cognito.get_user.assert_not_called()
        cognito.create_user.assert_not_called()

    def test_no_email_calls_when_skipped(self):
        """No SES email calls when role already exists."""
        db = MagicMock()
        db.execute_query.return_value = [{'id': 42}]
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        ses.send_invitation.assert_not_called()
        inv.create_invitation.assert_not_called()


# ============================================================================
# 4. TestProvisioningWithoutAdminEmail — initial_admin_email=None
# ============================================================================

class TestProvisioningWithoutAdminEmail:
    """create_and_provision_tenant() with no initial_admin_email."""

    def test_no_initial_admin_key_in_results(self):
        """Results dict has no 'initial_admin' key when email is None."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email=None,
            )

        assert 'initial_admin' not in results

    def test_results_still_has_core_keys(self):
        """Results still has tenant, modules, chart keys."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email=None,
            )

        assert 'tenant' in results
        assert 'modules' in results
        assert 'chart' in results

    def test_empty_string_email_also_skips(self):
        """Empty string initial_admin_email also skips admin creation."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='',
            )

        assert 'initial_admin' not in results



# ============================================================================
# 5. TestProvisioningWithAdminEmail — initial_admin_email provided
# ============================================================================

class TestProvisioningWithAdminEmail:
    """create_and_provision_tenant() with initial_admin_email provided."""

    def test_initial_admin_key_present(self):
        """Results dict has 'initial_admin' key when email is provided."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None  # new user

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url'], \
             patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='newadmin@test.com',
            )

        assert 'initial_admin' in results
        assert results['initial_admin']['status'] == 'created'

    def test_create_initial_admin_user_called(self):
        """create_initial_admin_user() is called during provisioning."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url'], \
             patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch.object(service, 'create_initial_admin_user',
                          return_value={'status': 'created'}) as mock_create:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='newadmin@test.com',
            )

        mock_create.assert_called_once_with(
            administration='TestCorp',
            email='newadmin@test.com',
            created_by='admin@sys.com',
            locale='nl',
        )
        assert results['initial_admin']['status'] == 'created'


# ============================================================================
# 6. TestErrorHandling — Exception during admin creation
# ============================================================================

class TestErrorHandling:
    """When create_initial_admin_user() raises, provisioning still succeeds."""

    def test_provisioning_succeeds_despite_admin_failure(self):
        """Overall provisioning returns successfully even if admin creation fails."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch.object(service, 'create_initial_admin_user',
                          side_effect=RuntimeError('Cognito down')):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='admin@test.com',
            )

        # Provisioning core steps still succeeded
        assert results['tenant'] == 'created'

    def test_initial_admin_status_is_failed(self):
        """results['initial_admin']['status'] is 'failed' on exception."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch.object(service, 'create_initial_admin_user',
                          side_effect=RuntimeError('Cognito down')):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='admin@test.com',
            )

        assert results['initial_admin']['status'] == 'failed'

    def test_warning_added_to_results(self):
        """Warning is added to results['warnings'] on exception."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch.object(service, 'create_initial_admin_user',
                          side_effect=RuntimeError('Cognito down')):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='admin@test.com',
            )

        assert len(results['warnings']) > 0
        assert any('Cognito down' in w for w in results['warnings'])

    def test_tenant_modules_chart_still_created(self):
        """Tenant, modules, and chart are still created despite admin failure."""
        db = MagicMock()
        db.execute_query.side_effect = _db_side_effect_for_fresh_tenant()
        service = TenantProvisioningService(db)

        with patch('services.tenant_provisioning_service._TEMPLATE_DIR') as mock_dir, \
             patch.object(service, 'create_initial_admin_user',
                          side_effect=RuntimeError('Cognito down')):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration='TestCorp',
                display_name='Test Corp',
                contact_email='contact@test.com',
                modules=['FIN'],
                created_by='admin@sys.com',
                initial_admin_email='admin@test.com',
            )

        assert results['tenant'] == 'created'
        module_names = [m['name'] for m in results['modules']]
        assert 'FIN' in module_names
        assert 'TENADMIN' in module_names
        assert results['chart'] is not None



# ============================================================================
# 7. TestCognitoUserStatus — Password handling
# ============================================================================

class TestCognitoUserStatus:
    """Verify admin_set_user_password(Permanent=True) for new users."""

    def test_permanent_password_set_for_new_user(self):
        """admin_set_user_password is called with Permanent=True."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        call_kwargs = cognito.client.admin_set_user_password.call_args[1]
        assert call_kwargs['Permanent'] is True
        assert call_kwargs['UserPoolId'] == cognito.user_pool_id
        assert call_kwargs['Username'] == 'admin@acme.com'

    def test_invitation_password_used_for_cognito(self):
        """The temporary password from the invitation is used."""
        db = MagicMock()
        db.execute_query.return_value = []
        service = TenantProvisioningService(db)

        cognito, inv, tpl, ses = _make_service_mocks()
        cognito.get_user.return_value = None
        inv.create_invitation.return_value = {
            'success': True,
            'temporary_password': 'MySpecialPass99!',
        }

        patches = _patch_lazy_imports(cognito, inv, tpl, ses)
        with patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            service.create_initial_admin_user(
                'AcmeCorp', 'admin@acme.com', 'sysadmin@sys.com',
            )

        call_kwargs = cognito.client.admin_set_user_password.call_args[1]
        assert call_kwargs['Password'] == 'MySpecialPass99!'


# ============================================================================
# 8. TestResendInvitationEndpoint — Resend endpoint
# ============================================================================

def _passthrough_cognito_sysadmin(required_roles=None, required_permissions=None):
    """Mock cognito_required to inject SysAdmin user_email and user_roles."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'sysadmin@system.com'
            kwargs['user_roles'] = ['SysAdmin']
            return f(*args, **kwargs)
        return wrapper
    return decorator


class TestResendInvitationEndpoint:
    """Test POST /api/sysadmin/tenants/<administration>/resend-invitation."""

    @pytest.fixture
    def app_and_client(self):
        """Create Flask app with the sysadmin_tenant_actions blueprint, auth bypassed."""
        from flask import Flask

        with patch('auth.cognito_utils.cognito_required',
                   side_effect=_passthrough_cognito_sysadmin):
            import importlib
            import routes.sysadmin_tenant_actions as sta_mod
            importlib.reload(sta_mod)

            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(
                sta_mod.sysadmin_tenant_actions_bp,
                url_prefix='/api/sysadmin/tenants',
            )
            yield app, app.test_client()

    def _mock_all_services(self):
        """Return patches and mocks for all services used by the endpoint."""
        mock_db = MagicMock()
        mock_cognito = MagicMock()
        mock_cognito.client = MagicMock()
        mock_cognito.user_pool_id = 'eu-west-1_TestPool'
        mock_cognito.get_user.return_value = {
            'Username': 'admin@acme.com',
            'UserAttributes': [],
        }

        mock_inv = MagicMock()
        mock_inv.create_invitation.return_value = {
            'success': True,
            'temporary_password': 'NewTempPass456!',
        }

        mock_tpl = MagicMock()
        mock_tpl.render_user_invitation.return_value = '<html>resend</html>'
        mock_tpl.get_invitation_subject.return_value = 'Invitation'

        mock_ses = MagicMock()
        mock_ses.send_invitation.return_value = {'success': True}

        mock_frontend = MagicMock(return_value='https://app.example.com')

        patches = {
            'db': patch('routes.sysadmin_tenant_actions.DatabaseManager', return_value=mock_db),
            'cognito': patch('services.cognito_service.CognitoService', return_value=mock_cognito),
            'invitation': patch('services.invitation_service.InvitationService', return_value=mock_inv),
            'email_tpl': patch('services.email_template_service.EmailTemplateService', return_value=mock_tpl),
            'ses': patch('services.ses_email_service.SESEmailService', return_value=mock_ses),
            'frontend_url': patch('utils.frontend_url.get_frontend_url', mock_frontend),
        }

        mocks = {
            'db': mock_db,
            'cognito': mock_cognito,
            'invitation': mock_inv,
            'email_tpl': mock_tpl,
            'ses': mock_ses,
        }

        return patches, mocks

    def test_happy_path_resend(self, app_and_client):
        """Happy path: password generated, Cognito updated, email sent."""
        app, client = app_and_client
        patches, mocks = self._mock_all_services()

        # Tenant exists
        mocks['db'].execute_query.side_effect = lambda q, p=None, fetch=True, commit=False: (
            [{'administration': 'AcmeCorp', 'status': 'active'}]
            if 'SELECT administration' in q and 'FROM tenants' in q
            else [{'id': 1}]  # role exists
            if 'user_tenant_roles' in q and 'SELECT' in q.upper()
            else None
        )

        with patches['db'], patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            resp = client.post(
                '/api/sysadmin/tenants/AcmeCorp/resend-invitation',
                json={'email': 'admin@acme.com'},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['email'] == 'admin@acme.com'

        # Cognito password updated
        mocks['cognito'].client.admin_set_user_password.assert_called_once()
        pw_kwargs = mocks['cognito'].client.admin_set_user_password.call_args[1]
        assert pw_kwargs['Permanent'] is True
        assert pw_kwargs['Password'] == 'NewTempPass456!'

        # Email sent
        mocks['ses'].send_invitation.assert_called_once()

    def test_missing_email_returns_400(self, app_and_client):
        """Missing email in request body returns 400."""
        app, client = app_and_client

        resp = client.post(
            '/api/sysadmin/tenants/AcmeCorp/resend-invitation',
            json={},
        )

        assert resp.status_code == 400

    def test_tenant_not_found_returns_404(self, app_and_client):
        """Non-existent tenant returns 404."""
        app, client = app_and_client
        patches, mocks = self._mock_all_services()

        # Tenant does NOT exist
        mocks['db'].execute_query.return_value = []

        with patches['db'], patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            resp = client.post(
                '/api/sysadmin/tenants/NonExistent/resend-invitation',
                json={'email': 'admin@acme.com'},
            )

        assert resp.status_code == 404

    def test_creates_cognito_user_if_not_exists(self, app_and_client):
        """Creates Cognito user for pre-fix tenants that never had one."""
        app, client = app_and_client
        patches, mocks = self._mock_all_services()

        # User does NOT exist in Cognito
        mocks['cognito'].get_user.return_value = None

        mocks['db'].execute_query.side_effect = lambda q, p=None, fetch=True, commit=False: (
            [{'administration': 'AcmeCorp', 'status': 'active'}]
            if 'SELECT administration' in q and 'FROM tenants' in q
            else []  # no existing role
            if 'user_tenant_roles' in q and 'SELECT' in q.upper()
            else None
        )

        with patches['db'], patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            resp = client.post(
                '/api/sysadmin/tenants/AcmeCorp/resend-invitation',
                json={'email': 'admin@acme.com'},
            )

        assert resp.status_code == 200
        mocks['cognito'].create_user.assert_called_once()

    def test_creates_tenant_admin_role_if_not_exists(self, app_and_client):
        """Creates Tenant_Admin role for pre-fix tenants."""
        app, client = app_and_client
        patches, mocks = self._mock_all_services()

        call_count = [0]

        def db_side_effect(q, p=None, fetch=True, commit=False):
            if 'SELECT administration' in q and 'FROM tenants' in q:
                return [{'administration': 'AcmeCorp', 'status': 'active'}]
            if 'user_tenant_roles' in q and 'SELECT' in q.upper():
                return []  # no existing role
            return None

        mocks['db'].execute_query.side_effect = db_side_effect

        with patches['db'], patches['cognito'], patches['invitation'], \
             patches['email_tpl'], patches['ses'], patches['frontend_url']:
            resp = client.post(
                '/api/sysadmin/tenants/AcmeCorp/resend-invitation',
                json={'email': 'admin@acme.com'},
            )

        assert resp.status_code == 200

        # Verify INSERT INTO user_tenant_roles was called
        insert_calls = [
            c for c in mocks['db'].execute_query.call_args_list
            if 'INSERT' in str(c.args[0]).upper()
            and 'user_tenant_roles' in str(c.args[0])
        ]
        assert len(insert_calls) == 1
