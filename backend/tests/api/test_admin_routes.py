"""
API tests for admin_routes.py

Tests user management endpoints (list, create, update, delete),
role management endpoints, and permission checks (401/403).

Requirements: 5.1, 5.5, 8.3, 8.4
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime
from botocore.exceptions import ClientError


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
    def test_list_users_success(self, mock_cognito, client, mock_auth_sysadmin):
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
    def test_create_user_success(self, mock_cognito, client, mock_auth_sysadmin):
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
    def test_list_groups_success(self, mock_cognito, client, mock_auth_sysadmin):
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


# ============================================================================
# User Actions Tests
# ============================================================================


class TestUserActions:
    """Tests for enable, disable, delete user endpoints."""

    @patch('admin_routes.cognito_client')
    def test_enable_user_success(self, mock_cognito, client, mock_auth_sysadmin):
        """SysAdmin can enable a user."""
        mock_cognito.admin_enable_user.return_value = {}

        response = client.post(
            '/api/admin/users/testuser/enable',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('admin_routes.cognito_client')
    def test_disable_user_success(self, mock_cognito, client, mock_auth_sysadmin):
        """SysAdmin can disable a user."""
        mock_cognito.admin_disable_user.return_value = {}

        response = client.post(
            '/api/admin/users/testuser/disable',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('admin_routes.cognito_client')
    def test_delete_user_success(self, mock_cognito, client, mock_auth_sysadmin):
        """SysAdmin can delete a user."""
        mock_cognito.admin_delete_user.return_value = {}

        response = client.delete(
            '/api/admin/users/testuser',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('admin_routes.cognito_client')
    def test_update_user_attributes_success(self, mock_cognito, client, mock_auth_sysadmin):
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
    def test_add_user_to_group_success(self, mock_cognito, client, mock_auth_sysadmin):
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
    def test_remove_user_from_group_success(self, mock_cognito, client, mock_auth_sysadmin):
        """SysAdmin can remove a user from a group."""
        mock_cognito.admin_remove_user_from_group.return_value = {}

        response = client.delete(
            '/api/admin/users/testuser/groups/TenantAdmin',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
