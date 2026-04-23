"""
Bug Condition Exploration Tests — Initial Admin User During Provisioning

Property 1: Bug Condition — No Initial Admin User Created During Provisioning

These tests encode the EXPECTED (correct) behavior: after provisioning with an
initial_admin_email, the results dict should contain an 'initial_admin' key,
a user_tenant_roles row with Tenant_Admin should exist, and an invitation
record should be created.

On UNFIXED code these tests MUST FAIL — failure confirms the bug exists.
On FIXED code these tests MUST PASS — passing confirms the fix works.

DO NOT attempt to fix the test or the code when it fails.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import pytest
from unittest.mock import MagicMock, patch, call
from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

from services.tenant_provisioning_service import TenantProvisioningService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Administration names: PascalCase alphanumeric, 3-21 chars, starts uppercase
admin_names = st.from_regex(r'[A-Z][a-zA-Z0-9]{2,20}', fullmatch=True)

# Valid email addresses
emails = st.emails()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Create a mocked DatabaseManager that simulates a fresh tenant."""
    db = MagicMock()
    # Default: no existing data (fresh tenant scenario)
    db.execute_query.return_value = []
    return db


@pytest.fixture
def service(mock_db):
    """Create TenantProvisioningService with mocked DB."""
    return TenantProvisioningService(mock_db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configure_fresh_tenant_db(mock_db):
    """
    Configure mock_db.execute_query to simulate a fresh tenant:
    - No existing tenant record
    - No existing modules
    - No existing chart rows
    - No existing user_tenant_roles
    - No existing user_invitations

    The service makes these queries in order:
      1. SELECT administration FROM tenants WHERE ...  -> [] (no existing)
      2. INSERT INTO tenants ...                       -> None
      3. SELECT id FROM tenant_modules WHERE ... (×N)  -> [] per module
      4. INSERT INTO tenant_modules ... (×N)           -> None per module
      5. SELECT COUNT(*) FROM rekeningschema WHERE ... -> [{'cnt': 0}]
    """
    def side_effect(*args, **kwargs):
        query = args[0] if args else kwargs.get('query', '')
        if 'SELECT administration FROM tenants' in query:
            return []
        if 'SELECT id FROM tenant_modules' in query:
            return []
        if 'SELECT COUNT(*) as cnt FROM rekeningschema' in query:
            return [{'cnt': 0}]
        if 'SELECT' in query.upper() and 'user_tenant_roles' in query:
            return []
        if 'SELECT' in query.upper() and 'user_invitations' in query:
            return []
        return []

    mock_db.execute_query.side_effect = side_effect


def _build_service_patches():
    """
    Return a dict of ``patch`` objects that mock every service lazily
    imported inside ``create_initial_admin_user()``.

    Usage::

        patches, mocks = _build_service_patches()
        with patches['cognito'], patches['invitation'], \
             patches['email_template'], patches['ses'], patches['frontend_url']:
            ...
    """
    mock_cognito_cls = MagicMock()
    mock_cognito = MagicMock()
    # Simulate "new user" path: get_user returns None
    mock_cognito.get_user.return_value = None
    mock_cognito.client = MagicMock()
    mock_cognito_cls.return_value = mock_cognito

    mock_invitation_cls = MagicMock()
    mock_invitation = MagicMock()
    mock_invitation.create_invitation.return_value = {
        'success': True,
        'temporary_password': 'TempPass123!',
    }
    mock_invitation_cls.return_value = mock_invitation

    mock_email_template_cls = MagicMock()
    mock_email_template = MagicMock()
    mock_email_template.render_user_invitation.return_value = '<html>invite</html>'
    mock_email_template.get_invitation_subject.return_value = 'Invitation'
    mock_email_template_cls.return_value = mock_email_template

    mock_ses_cls = MagicMock()
    mock_ses = MagicMock()
    mock_ses.send_invitation.return_value = {'success': True}
    mock_ses_cls.return_value = mock_ses

    mock_frontend_url = MagicMock(return_value='https://app.example.com')

    patches = {
        'cognito': patch(
            'services.cognito_service.CognitoService',
            mock_cognito_cls,
        ),
        'invitation': patch(
            'services.invitation_service.InvitationService',
            mock_invitation_cls,
        ),
        'email_template': patch(
            'services.email_template_service.EmailTemplateService',
            mock_email_template_cls,
        ),
        'ses': patch(
            'services.ses_email_service.SESEmailService',
            mock_ses_cls,
        ),
        'frontend_url': patch(
            'utils.frontend_url.get_frontend_url',
            mock_frontend_url,
        ),
    }

    mocks = {
        'cognito': mock_cognito,
        'invitation': mock_invitation,
        'email_template': mock_email_template,
        'ses': mock_ses,
    }

    return patches, mocks


# ---------------------------------------------------------------------------
# Test 1: create_and_provision_tenant() should accept initial_admin_email
#          and return results with an 'initial_admin' key
# ---------------------------------------------------------------------------

class TestBugConditionInitialAdminInResults:
    """
    Bug Condition: create_and_provision_tenant() has no initial_admin_email
    parameter and returns results with no 'initial_admin' key.

    Expected Behavior: When initial_admin_email is provided, results dict
    must contain 'initial_admin' with status 'created' or 'existing_user'.
    """

    @given(email=emails, administration=admin_names)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_results_contain_initial_admin_key(self, email, administration):
        """
        For any valid (email, administration) pair, calling
        create_and_provision_tenant() with initial_admin_email should
        produce a results dict containing an 'initial_admin' key.

        WILL FAIL on unfixed code: method does not accept
        initial_admin_email parameter.
        """
        mock_db = MagicMock()
        _configure_fresh_tenant_db(mock_db)
        service = TenantProvisioningService(mock_db)

        patches, mocks = _build_service_patches()

        # Patch chart template to avoid filesystem dependency
        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir, \
             patches['cognito'], patches['invitation'], \
             patches['email_template'], patches['ses'], \
             patches['frontend_url']:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            results = service.create_and_provision_tenant(
                administration=administration,
                display_name=f'Test {administration}',
                contact_email=email,
                modules=['FIN'],
                created_by='sysadmin@system.com',
                locale='nl',
                initial_admin_email=email,
            )

        # Assert: results must contain 'initial_admin' key
        assert 'initial_admin' in results, (
            f"Bug confirmed: results dict has no 'initial_admin' key. "
            f"Keys present: {list(results.keys())}. "
            f"create_and_provision_tenant() does not create an initial admin user."
        )

        # Assert: status must be 'created' or 'existing_user'
        status = results['initial_admin']['status']
        assert status in ('created', 'existing_user'), (
            f"initial_admin status should be 'created' or 'existing_user', "
            f"got '{status}'"
        )


# ---------------------------------------------------------------------------
# Test 2: After provisioning, user_tenant_roles should have a Tenant_Admin row
# ---------------------------------------------------------------------------

class TestBugConditionTenantAdminRole:
    """
    Bug Condition: After provisioning, user_tenant_roles has 0 rows for the
    tenant — no user can operate as Tenant_Admin.

    Expected Behavior: After provisioning with initial_admin_email, a
    user_tenant_roles row with (email, administration, 'Tenant_Admin')
    must exist.
    """

    @given(email=emails, administration=admin_names)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_user_tenant_roles_has_tenant_admin_row(self, email, administration):
        """
        For any valid (email, administration) pair, after provisioning
        with initial_admin_email, the DB should have received an INSERT
        into user_tenant_roles with role 'Tenant_Admin'.

        WILL FAIL on unfixed code: no INSERT into user_tenant_roles
        is ever executed during provisioning.
        """
        mock_db = MagicMock()
        _configure_fresh_tenant_db(mock_db)
        service = TenantProvisioningService(mock_db)

        patches, mocks = _build_service_patches()

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir, \
             patches['cognito'], patches['invitation'], \
             patches['email_template'], patches['ses'], \
             patches['frontend_url']:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            try:
                results = service.create_and_provision_tenant(
                    administration=administration,
                    display_name=f'Test {administration}',
                    contact_email=email,
                    modules=['FIN'],
                    created_by='sysadmin@system.com',
                    locale='nl',
                    initial_admin_email=email,
                )
            except TypeError:
                # On unfixed code, initial_admin_email is not accepted
                pytest.fail(
                    "Bug confirmed: create_and_provision_tenant() does not "
                    "accept initial_admin_email parameter — no admin user "
                    "can be created during provisioning."
                )

        # Check all execute_query calls for a user_tenant_roles INSERT
        all_calls = mock_db.execute_query.call_args_list
        role_inserts = [
            c for c in all_calls
            if len(c.args) > 0
            and 'INSERT' in str(c.args[0]).upper()
            and 'user_tenant_roles' in str(c.args[0])
        ]

        assert len(role_inserts) > 0, (
            f"Bug confirmed: No INSERT into user_tenant_roles was executed "
            f"during provisioning for '{email}' in '{administration}'. "
            f"The tenant has 0 users with Tenant_Admin role. "
            f"Queries executed: {[str(c.args[0])[:80] for c in all_calls]}"
        )

        # Verify the inserted role is Tenant_Admin (may be in SQL string or params)
        for insert_call in role_inserts:
            query_str = str(insert_call.args[0])
            params = insert_call.args[1] if len(insert_call.args) > 1 else ()
            has_role = (
                'Tenant_Admin' in query_str
                or 'Tenant_Admin' in params
            )
            assert has_role, (
                f"user_tenant_roles INSERT found but role is not 'Tenant_Admin'. "
                f"Query: {query_str[:120]}, Params: {params}"
            )


# ---------------------------------------------------------------------------
# Test 3: After provisioning, user_invitations should have a record
# ---------------------------------------------------------------------------

class TestBugConditionInvitationRecord:
    """
    Bug Condition: After provisioning, user_invitations has 0 records for
    the admin email — no invitation email can be sent.

    Expected Behavior: After provisioning with initial_admin_email, an
    invitation record must exist in user_invitations for that email.
    """

    @given(email=emails, administration=admin_names)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_invitation_record_created(self, email, administration):
        """
        For any valid (email, administration) pair, after provisioning
        with initial_admin_email, the InvitationService.create_invitation()
        should have been called for that email.

        WILL FAIL on unfixed code: no invitation record is ever created
        during provisioning.
        """
        mock_db = MagicMock()
        _configure_fresh_tenant_db(mock_db)
        service = TenantProvisioningService(mock_db)

        patches, mocks = _build_service_patches()

        with patch(
            'services.tenant_provisioning_service._TEMPLATE_DIR'
        ) as mock_dir, \
             patches['cognito'], patches['invitation'], \
             patches['email_template'], patches['ses'], \
             patches['frontend_url']:
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)

            try:
                results = service.create_and_provision_tenant(
                    administration=administration,
                    display_name=f'Test {administration}',
                    contact_email=email,
                    modules=['FIN'],
                    created_by='sysadmin@system.com',
                    locale='nl',
                    initial_admin_email=email,
                )
            except TypeError:
                pytest.fail(
                    "Bug confirmed: create_and_provision_tenant() does not "
                    "accept initial_admin_email parameter — no invitation "
                    "record can be created during provisioning."
                )

            # Verify InvitationService.create_invitation() was called
            invitation_mock = mocks['invitation']
            assert invitation_mock.create_invitation.call_count > 0, (
                f"Bug confirmed: InvitationService.create_invitation() was "
                f"never called during provisioning for '{email}' in "
                f"'{administration}'. No invitation record exists — the "
                f"admin cannot receive an invitation email."
            )
