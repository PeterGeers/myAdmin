"""
API tests for admin_routes.py

Tests user management endpoints (list, create, update, delete),
role management endpoints, and permission checks (401/403).

Pool resolution (bugfix ``cognito-admin-pool-resolution``, Task 3.3.4):
    admin_routes migrated off the legacy single-pool ``COGNITO_USER_POOL_ID`` var
    onto the shared registry-backed resolver in **token mode**
    (``admin_routes.resolve_pool_id_for_token``). The tests below patch that
    resolver to return a sentinel TEST-pool id and assert it is the value threaded
    into every ``UserPoolId=...`` admin call (proving the registry-resolved pool is
    used, not the legacy PROD var), and that a ``PoolResolutionError`` from the
    resolver maps to the same 500 the old ``COGNITO_USER_POOL_ID not configured``
    guard produced.

Requirements: 5.1, 5.5, 8.3, 8.4, 2.1, 2.3, 2.4, 2.7, 3.3
Reference: .kiro/specs/missing-py-tests/design.md,
           .kiro/specs/cognito-admin-pool-resolution/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime
from botocore.exceptions import ClientError

from auth.admin_pool_resolver import PoolResolutionError

# Sentinel registry-resolved (token-mode) pool id the resolver is patched to
# return in these tests. It is deliberately NOT the legacy ``mock_env``
# COGNITO_USER_POOL_ID value ('us-east-1_test'), so an assertion that this exact
# id reaches the Cognito call proves the op used the registry-resolved pool.
RESOLVED_POOL_ID = "eu-west-1_xyrlzfqbl"


@pytest.fixture
def mock_resolved_pool():
    """Patch admin_routes' token-mode resolver to return the sentinel pool id.

    Yields the patched resolver mock so tests can assert it was consulted and can
    override its behavior (e.g. raise PoolResolutionError for the error-mapping
    tests).
    """
    with patch(
        "admin_routes.resolve_pool_id_for_token", return_value=RESOLVED_POOL_ID
    ) as mock_resolve:
        yield mock_resolve


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestAdminAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_list_users_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list users should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/admin/users')
        assert response.status_code in (401, 403)

    def test_create_user_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create user should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/admin/users', json={
                'email': 'new@example.com',
                'password': 'Test1234!'
            })
        assert response.status_code in (401, 403)

    def test_list_users_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on admin endpoints."""
        # mock_auth returns TenantAdmin, not SysAdmin
        response = client.get(
            '/api/admin/users',
            headers=mock_auth
        )
        assert response.status_code == 403


# ============================================================================
# User Management Tests
# ============================================================================


class TestListUsers:
    """Tests for GET /api/admin/users."""

    @patch('admin_routes.cognito_client')
    def test_list_users_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can list users successfully."""
        mock_cognito.list_users.return_value = {
            'Users': [
                {
                    'Username': 'user1',
                    'Attributes': [
                        {'Name': 'email', 'Value': 'user1@example.com'},
                        {'Name': 'name', 'Value': 'User One'},
                    ],
                    'UserStatus': 'CONFIRMED',
                    'Enabled': True,
                    'UserCreateDate': datetime(2024, 1, 1),
                    'UserLastModifiedDate': datetime(2024, 6, 1),
                }
            ]
        }
        mock_cognito.admin_list_groups_for_user.return_value = {
            'Groups': [{'GroupName': 'TenantAdmin'}]
        }

        response = client.get(
            '/api/admin/users',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1
        assert data['users'][0]['email'] == 'user1@example.com'
        # The list_users AND the per-user group lookup must both act on the
        # registry-resolved (token-mode) pool, not the legacy var.
        assert mock_cognito.list_users.call_args.kwargs['UserPoolId'] == RESOLVED_POOL_ID
        assert (
            mock_cognito.admin_list_groups_for_user.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_list_users_cognito_error_returns_500(self, mock_cognito, client, mock_auth_sysadmin):
        """Cognito ClientError should return 500."""
        mock_cognito.list_users.side_effect = ClientError(
            {'Error': {'Code': 'InternalErrorException', 'Message': 'Service error'}},
            'ListUsers'
        )

        response = client.get(
            '/api/admin/users',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


class TestCreateUser:
    """Tests for POST /api/admin/users."""

    @patch('admin_routes.cognito_client')
    def test_create_user_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can create a user successfully."""
        mock_cognito.admin_create_user.return_value = {
            'User': {'Username': 'new-user-id'}
        }
        mock_cognito.admin_add_user_to_group.return_value = {}

        response = client.post(
            '/api/admin/users',
            headers=mock_auth_sysadmin,
            json={
                'email': 'newuser@example.com',
                'name': 'New User',
                'password': 'SecurePass123!',
                'groups': ['TenantAdmin']
            }
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['username'] == 'new-user-id'
        # Create AND the group-add must act on the registry-resolved pool.
        assert (
            mock_cognito.admin_create_user.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )
        assert (
            mock_cognito.admin_add_user_to_group.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_create_user_missing_email_returns_400(self, mock_cognito, client, mock_auth_sysadmin):
        """Missing email should return 400."""
        response = client.post(
            '/api/admin/users',
            headers=mock_auth_sysadmin,
            json={'password': 'SecurePass123!'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('admin_routes.cognito_client')
    def test_create_user_missing_password_returns_400(self, mock_cognito, client, mock_auth_sysadmin):
        """Missing password should return 400."""
        response = client.post(
            '/api/admin/users',
            headers=mock_auth_sysadmin,
            json={'email': 'user@example.com'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('admin_routes.cognito_client')
    def test_create_user_duplicate_returns_400(self, mock_cognito, client, mock_auth_sysadmin):
        """Duplicate user should return 400."""
        mock_cognito.admin_create_user.side_effect = ClientError(
            {'Error': {'Code': 'UsernameExistsException', 'Message': 'User exists'}},
            'AdminCreateUser'
        )

        response = client.post(
            '/api/admin/users',
            headers=mock_auth_sysadmin,
            json={
                'email': 'existing@example.com',
                'password': 'SecurePass123!'
            }
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'already exists' in data['error']


# ============================================================================
# Role Management Tests
# ============================================================================


class TestListGroups:
    """Tests for GET /api/admin/groups."""

    @patch('admin_routes.cognito_client')
    def test_list_groups_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can list groups successfully."""
        mock_cognito.list_groups.return_value = {
            'Groups': [
                {
                    'GroupName': 'SysAdmin',
                    'Description': 'System Administrator',
                    'Precedence': 1,
                    'CreationDate': datetime(2024, 1, 1),
                    'LastModifiedDate': datetime(2024, 1, 1),
                },
                {
                    'GroupName': 'TenantAdmin',
                    'Description': 'Tenant Administrator',
                    'Precedence': 2,
                    'CreationDate': datetime(2024, 1, 1),
                    'LastModifiedDate': datetime(2024, 1, 1),
                }
            ]
        }

        response = client.get(
            '/api/admin/groups',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 2
        assert (
            mock_cognito.list_groups.call_args.kwargs['UserPoolId'] == RESOLVED_POOL_ID
        )


# ============================================================================
# User Actions Tests
# ============================================================================


class TestUserActions:
    """Tests for enable, disable, delete user endpoints."""

    @patch('admin_routes.cognito_client')
    def test_enable_user_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can enable a user."""
        mock_cognito.admin_enable_user.return_value = {}

        response = client.post(
            '/api/admin/users/testuser/enable',
            headers={**mock_auth_sysadmin, 'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert (
            mock_cognito.admin_enable_user.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_disable_user_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can disable a user."""
        mock_cognito.admin_disable_user.return_value = {}

        response = client.post(
            '/api/admin/users/testuser/disable',
            headers={**mock_auth_sysadmin, 'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert (
            mock_cognito.admin_disable_user.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_delete_user_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can delete a user."""
        mock_cognito.admin_delete_user.return_value = {}

        response = client.delete(
            '/api/admin/users/testuser',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert (
            mock_cognito.admin_delete_user.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_update_user_attributes_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can update user attributes."""
        mock_cognito.admin_update_user_attributes.return_value = {}

        response = client.put(
            '/api/admin/users/testuser/attributes',
            headers=mock_auth_sysadmin,
            json={'name': 'Updated Name'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert (
            mock_cognito.admin_update_user_attributes.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_update_user_attributes_missing_name_returns_400(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Missing name attribute should return 400."""
        response = client.put(
            '/api/admin/users/testuser/attributes',
            headers=mock_auth_sysadmin,
            json={}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('admin_routes.cognito_client')
    def test_add_user_to_group_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can add a user to a group."""
        mock_cognito.admin_add_user_to_group.return_value = {}

        response = client.post(
            '/api/admin/users/testuser/groups',
            headers=mock_auth_sysadmin,
            json={'groupName': 'TenantAdmin'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert (
            mock_cognito.admin_add_user_to_group.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )

    @patch('admin_routes.cognito_client')
    def test_add_user_to_group_missing_group_returns_400(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Missing groupName should return 400."""
        response = client.post(
            '/api/admin/users/testuser/groups',
            headers=mock_auth_sysadmin,
            json={}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('admin_routes.cognito_client')
    def test_remove_user_from_group_success(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """SysAdmin can remove a user from a group."""
        mock_cognito.admin_remove_user_from_group.return_value = {}

        response = client.delete(
            '/api/admin/users/testuser/groups/TenantAdmin',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert (
            mock_cognito.admin_remove_user_from_group.call_args.kwargs['UserPoolId']
            == RESOLVED_POOL_ID
        )


# ============================================================================
# Pool Resolution — token-mode migration (bugfix cognito-admin-pool-resolution)
# ============================================================================


class TestAdminPoolResolutionTokenMode:
    """admin_routes resolves the target pool in TOKEN mode from the caller's raw JWT.

    Validates that each migrated op resolves its pool via
    ``resolve_pool_id_for_token`` keyed to the caller token (not the legacy
    ``COGNITO_USER_POOL_ID`` var), threading the resolved id into the Cognito call.

    Validates: Requirements 2.1, 2.3, 2.4, 3.3
    """

    @patch('admin_routes.cognito_client')
    def test_resolver_called_with_raw_caller_token(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """The resolver receives the raw caller JWT (Bearer prefix stripped).

        ``mock_auth_sysadmin`` sends ``Authorization: Bearer sysadmin-token``; the
        route must hand the raw ``sysadmin-token`` (no ``Bearer `` prefix) to the
        token-mode resolver.
        """
        mock_cognito.admin_enable_user.return_value = {}

        response = client.post(
            '/api/admin/users/testuser/enable',
            headers={**mock_auth_sysadmin, 'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        mock_resolved_pool.assert_called_once_with('sysadmin-token')

    @patch('admin_routes.cognito_client')
    def test_resolved_pool_not_legacy_var(
        self, mock_cognito, client, mock_auth_sysadmin, mock_resolved_pool
    ):
        """The op uses the registry-resolved pool, NOT the legacy mock_env pool id.

        ``mock_env`` sets ``COGNITO_USER_POOL_ID='us-east-1_test'``; the op must act
        on the resolver's sentinel id instead, proving no direct legacy read.
        """
        mock_cognito.admin_delete_user.return_value = {}

        response = client.delete(
            '/api/admin/users/testuser',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        used_pool = mock_cognito.admin_delete_user.call_args.kwargs['UserPoolId']
        assert used_pool == RESOLVED_POOL_ID
        assert used_pool != 'us-east-1_test'


class TestAdminPoolResolutionErrorMapping:
    """A PoolResolutionError maps to a clear 500 (replacing the old legacy guard).

    The removed guard returned 500 ``COGNITO_USER_POOL_ID not configured``. Per the
    design's not-found/error-mapping guidance, an unresolvable pool in token mode is
    a genuine misconfiguration (registry misconfigured, or registry-absent legacy
    fallback unset), so it maps to 500 — never a silent action on the legacy/PROD
    pool.

    Validates: Requirements 2.4, 2.7, 3.3
    """

    @pytest.mark.parametrize(
        "method,url,cognito_attr",
        [
            ("get", "/api/admin/users", "list_users"),
            ("get", "/api/admin/groups", "list_groups"),
            ("post", "/api/admin/users/testuser/enable", "admin_enable_user"),
            ("post", "/api/admin/users/testuser/disable", "admin_disable_user"),
            ("delete", "/api/admin/users/testuser", "admin_delete_user"),
            (
                "delete",
                "/api/admin/users/testuser/groups/TenantAdmin",
                "admin_remove_user_from_group",
            ),
        ],
    )
    @patch('admin_routes.cognito_client')
    def test_pool_resolution_error_returns_500_and_skips_cognito(
        self, mock_cognito, method, url, cognito_attr, client, mock_auth_sysadmin
    ):
        """Unresolvable pool -> 500 with a clear error, and no Cognito call is made."""
        with patch(
            'admin_routes.resolve_pool_id_for_token',
            side_effect=PoolResolutionError("registry misconfigured"),
        ):
            response = getattr(client, method)(
                url,
                headers={**mock_auth_sysadmin, 'Content-Type': 'application/json'},
            )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'registry misconfigured' in data['error']
        # The op must NOT fall through to a Cognito call on an unresolved pool.
        getattr(mock_cognito, cognito_attr).assert_not_called()

    @patch('admin_routes.cognito_client')
    def test_create_user_pool_resolution_error_returns_500(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """create_user maps a PoolResolutionError to 500 before creating anything."""
        with patch(
            'admin_routes.resolve_pool_id_for_token',
            side_effect=PoolResolutionError("legacy fallback unset"),
        ):
            response = client.post(
                '/api/admin/users',
                headers=mock_auth_sysadmin,
                json={'email': 'new@example.com', 'password': 'SecurePass123!'},
            )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'legacy fallback unset' in data['error']
        mock_cognito.admin_create_user.assert_not_called()

    @patch('admin_routes.cognito_client')
    def test_update_attributes_pool_resolution_error_returns_500(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """update_user_attributes maps a PoolResolutionError to 500."""
        with patch(
            'admin_routes.resolve_pool_id_for_token',
            side_effect=PoolResolutionError("no pool"),
        ):
            response = client.put(
                '/api/admin/users/testuser/attributes',
                headers=mock_auth_sysadmin,
                json={'name': 'Updated Name'},
            )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        mock_cognito.admin_update_user_attributes.assert_not_called()

    @patch('admin_routes.cognito_client')
    def test_add_user_to_group_pool_resolution_error_returns_500(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """add_user_to_group maps a PoolResolutionError to 500."""
        with patch(
            'admin_routes.resolve_pool_id_for_token',
            side_effect=PoolResolutionError("no pool"),
        ):
            response = client.post(
                '/api/admin/users/testuser/groups',
                headers=mock_auth_sysadmin,
                json={'groupName': 'TenantAdmin'},
            )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        mock_cognito.admin_add_user_to_group.assert_not_called()
