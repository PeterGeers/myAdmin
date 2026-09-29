"""
Unit Tests for CognitoService

Tests the CognitoService methods for user management.
Updated for the ``cognito-admin-pool-resolution`` bugfix: CognitoService no longer
reads the legacy ``COGNITO_USER_POOL_ID`` var in ``__init__``. Each op resolves its
target pool through the shared registry-backed resolver (email mode), and callers may
pass an explicit ``user_pool_id`` (constructor or per call) to supply an
already-resolved pool. These tests exercise the explicit-pool-id path and assert the
resolved pool id is threaded into every Cognito admin call.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.cognito_service import CognitoService

# Explicit pool id passed to the service under test. With an explicit pool id set,
# resolve_pool_id returns it directly (no registry probe needed), and every admin
# call must pass it as UserPoolId.
EXPLICIT_POOL_ID = "eu-west-1_TestPoolAbc"


class TestCognitoService:
    """Test suite for CognitoService"""

    @pytest.fixture
    def mock_boto_client(self):
        """Mock boto3 client before CognitoService is instantiated"""
        with patch('services.cognito_service.boto3.client') as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def cognito_service(self, mock_boto_client):
        """Create CognitoService with mocked boto3 client and an explicit pool id.

        The explicit pool id makes resolve_pool_id deterministic (no registry probe),
        so each op passes EXPLICIT_POOL_ID as UserPoolId — which the tests assert.
        """
        svc = CognitoService(user_pool_id=EXPLICIT_POOL_ID)
        return svc

    def _last_pool_id(self, mock_call):
        """Return the UserPoolId kwarg from a mock's most recent call."""
        return mock_call.call_args.kwargs.get("UserPoolId")

    # Test 1: Initialize service
    def test_init_service(self, cognito_service):
        """Test CognitoService initialization"""
        assert cognito_service is not None
        assert hasattr(cognito_service, 'client')
        assert hasattr(cognito_service, 'user_pool_id')

    # Test 1b: __init__ does NOT read the legacy COGNITO_USER_POOL_ID var
    def test_init_does_not_read_legacy_pool_var(self, mock_boto_client):
        """CognitoService() with no pool id leaves user_pool_id None even when the
        legacy var is set — the legacy read was removed in the pool-resolution fix."""
        with patch.dict(os.environ, {"COGNITO_USER_POOL_ID": "eu-west-1_LegacyProd"}):
            svc = CognitoService()
        assert svc.user_pool_id is None

    # Test 1c: explicit pool id resolves directly
    def test_resolve_pool_id_uses_explicit_override(self, cognito_service):
        """An instance-level explicit pool id is returned without a registry probe."""
        assert cognito_service.resolve_pool_id(username="anyone@example.com") == EXPLICIT_POOL_ID
        # A per-call user_pool_id overrides even the instance-level one.
        assert (
            cognito_service.resolve_pool_id(user_pool_id="eu-west-1_PerCall")
            == "eu-west-1_PerCall"
        )

    # Test 2: Create user successfully
    def test_create_user_success(self, cognito_service, mock_boto_client):
        """Test successful user creation"""
        mock_boto_client.admin_create_user.return_value = {
            'User': {
                'Username': 'test@example.com',
                'UserStatus': 'FORCE_CHANGE_PASSWORD'
            }
        }

        result = cognito_service.create_user(
            email='test@example.com',
            name='Test User',
            password='TempPass123!',
            tenant='TestTenant'
        )

        assert result['Username'] == 'test@example.com'
        mock_boto_client.admin_create_user.assert_called_once()
        # The resolved pool id is threaded into the admin call.
        assert self._last_pool_id(mock_boto_client.admin_create_user) == EXPLICIT_POOL_ID

    # Test 3: Create user with existing email
    def test_create_user_already_exists(self, cognito_service, mock_boto_client):
        """Test creating user with existing email"""
        mock_boto_client.admin_create_user.side_effect = ClientError(
            {'Error': {'Code': 'UsernameExistsException', 'Message': 'User exists'}},
            'AdminCreateUser'
        )

        with pytest.raises(ClientError) as exc_info:
            cognito_service.create_user(
                email='existing@example.com',
                name='Existing User',
                password='TempPass123!',
                tenant='TestTenant'
            )

        assert exc_info.value.response['Error']['Code'] == 'UsernameExistsException'

    # Test 4: Get user details
    def test_get_user_success(self, cognito_service, mock_boto_client):
        """Test getting user details"""
        mock_boto_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'test@example.com'},
                {'Name': 'name', 'Value': 'Test User'},
                {'Name': 'custom:tenants', 'Value': '["TestTenant"]'}
            ],
            'UserStatus': 'CONFIRMED',
            'Enabled': True
        }

        result = cognito_service.get_user('test@example.com')

        assert result is not None
        assert result['Username'] == 'test@example.com'
        assert result['UserStatus'] == 'CONFIRMED'
        assert self._last_pool_id(mock_boto_client.admin_get_user) == EXPLICIT_POOL_ID

    # Test 5: Get user not found
    def test_get_user_not_found(self, cognito_service, mock_boto_client):
        """Test getting non-existent user"""
        mock_boto_client.admin_get_user.side_effect = ClientError(
            {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}},
            'AdminGetUser'
        )

        result = cognito_service.get_user('nonexistent@example.com')

        assert result is None

    # Test 6: Update user attributes
    def test_update_user_success(self, cognito_service, mock_boto_client):
        """Test updating user attributes"""
        result = cognito_service.update_user(
            username='test@example.com',
            name='Updated Name'
        )

        assert result is True
        mock_boto_client.admin_update_user_attributes.assert_called_once()
        assert (
            self._last_pool_id(mock_boto_client.admin_update_user_attributes)
            == EXPLICIT_POOL_ID
        )

    # Test 7: Delete user
    def test_delete_user_success(self, cognito_service, mock_boto_client):
        """Test deleting user"""
        result = cognito_service.delete_user('test@example.com')

        assert result is True
        mock_boto_client.admin_delete_user.assert_called_once()
        assert self._last_pool_id(mock_boto_client.admin_delete_user) == EXPLICIT_POOL_ID

    # Test 8: Enable user via update_user
    def test_enable_user_success(self, cognito_service, mock_boto_client):
        """Test enabling user via update_user"""
        result = cognito_service.update_user(
            username='test@example.com',
            enabled=True
        )

        assert result is True
        mock_boto_client.admin_enable_user.assert_called_once()
        assert self._last_pool_id(mock_boto_client.admin_enable_user) == EXPLICIT_POOL_ID

    # Test 9: Disable user via update_user
    def test_disable_user_success(self, cognito_service, mock_boto_client):
        """Test disabling user via update_user"""
        result = cognito_service.update_user(
            username='test@example.com',
            enabled=False
        )

        assert result is True
        mock_boto_client.admin_disable_user.assert_called_once()
        assert self._last_pool_id(mock_boto_client.admin_disable_user) == EXPLICIT_POOL_ID

    # Test 10: Add user to group (now assign_role)
    def test_add_user_to_group_success(self, cognito_service, mock_boto_client):
        """Test adding user to group via assign_role"""
        result = cognito_service.assign_role('test@example.com', 'Tenant_Admin')

        assert result is True
        mock_boto_client.admin_add_user_to_group.assert_called_once()
        assert (
            self._last_pool_id(mock_boto_client.admin_add_user_to_group)
            == EXPLICIT_POOL_ID
        )

    # Test 11: Remove user from group (now remove_role)
    def test_remove_user_from_group_success(self, cognito_service, mock_boto_client):
        """Test removing user from group via remove_role"""
        result = cognito_service.remove_role('test@example.com', 'Tenant_Admin')

        assert result is True
        mock_boto_client.admin_remove_user_from_group.assert_called_once()
        assert (
            self._last_pool_id(mock_boto_client.admin_remove_user_from_group)
            == EXPLICIT_POOL_ID
        )

    # Test 12: List user groups
    def test_list_user_groups_success(self, cognito_service, mock_boto_client):
        """Test listing user groups"""
        mock_boto_client.admin_list_groups_for_user.return_value = {
            'Groups': [
                {'GroupName': 'Tenant_Admin'},
                {'GroupName': 'Finance_Read'}
            ]
        }

        result = cognito_service.list_user_groups('test@example.com')

        assert 'Tenant_Admin' in result
        assert 'Finance_Read' in result
        assert (
            self._last_pool_id(mock_boto_client.admin_list_groups_for_user)
            == EXPLICIT_POOL_ID
        )

    # Test 13: Per-call user_pool_id overrides the instance pool id
    def test_per_call_user_pool_id_overrides_instance(self, cognito_service, mock_boto_client):
        """A per-call user_pool_id is threaded into the admin call over the instance one."""
        mock_boto_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [],
            'UserStatus': 'CONFIRMED',
        }

        per_call_pool = "eu-west-1_PerCallPool"
        cognito_service.get_user('test@example.com', user_pool_id=per_call_pool)

        assert self._last_pool_id(mock_boto_client.admin_get_user) == per_call_pool

    # Test 14: Email-mode resolution threads the registry-resolved pool
    def test_email_mode_resolution_threads_registry_pool(self, mock_boto_client):
        """With no explicit pool id and a registry configured for one pool, the op
        resolves that pool (email mode) and passes it to the admin call."""
        registry_pool_id = "eu-west-1_xyrlzfqbl"
        issuer = f"https://cognito-idp.eu-west-1.amazonaws.com/{registry_pool_id}"
        registry_env = {
            "COGNITO_POOL_KEYS": "TEST",
            "TEST_COGNITO_ISSUER": issuer,
            "TEST_COGNITO_JWKS_URI": f"{issuer}/.well-known/jwks.json",
            "TEST_COGNITO_CLIENT_ID": "test-client-id",
            "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
            "AWS_REGION": "eu-west-1",
        }
        # The shared client both probes (admin_get_user during resolution) and creates.
        mock_boto_client.admin_get_user.return_value = {
            'Username': 'peter@pgeers.nl',
            'UserAttributes': [],
            'UserStatus': 'CONFIRMED',
        }
        mock_boto_client.admin_create_user.return_value = {
            'User': {'Username': 'peter@pgeers.nl'}
        }

        with patch.dict(os.environ, registry_env, clear=False):
            # No explicit pool id -> resolve per user via the registry probe.
            svc = CognitoService()
            svc.create_user(
                email='peter@pgeers.nl',
                name='Peter',
                tenant='ExampleTenant',
                password='TempPass123!',
            )

        assert self._last_pool_id(mock_boto_client.admin_create_user) == registry_pool_id


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
