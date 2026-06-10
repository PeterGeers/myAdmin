"""
API tests for tenant_admin_users.py

Tests user management endpoints: list, create, update, delete users,
role assignment/removal, and available roles listing.

Requirements: 20.8
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


@pytest.fixture
def tenant_admin_auth():
    """Mock authentication with Tenant_Admin role for tenant admin user endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']):
        mock_creds.return_value = ('admin@example.com', ['Tenant_Admin'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


@pytest.fixture
def mock_cognito_client():
    """Mock the cognito_client used in tenant_admin_users module."""
    with patch('routes.tenant_admin_users.cognito_client') as mock_client:
        yield mock_client


@pytest.fixture
def mock_get_tenant():
    """Mock get_current_tenant to return test-tenant."""
    with patch('routes.tenant_admin_users.get_current_tenant', return_value='test-tenant'):
        yield


@pytest.fixture
def mock_user_tenants():
    """Mock get_user_tenants to return test-tenant."""
    with patch('routes.tenant_admin_users.get_user_tenants', return_value=['test-tenant']):
        yield


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTenantAdminUsersAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_list_users_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list users should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/tenant-admin/users')
        assert response.status_code in (401, 403)

    def test_create_user_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create user should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/tenant-admin/users',
                json={'email': 'new@example.com', 'name': 'New User'}
            )
        assert response.status_code in (401, 403)

    def test_delete_user_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to delete user should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.delete('/api/tenant-admin/users/someuser')
        assert response.status_code in (401, 403)


# ============================================================================
# List Users Tests
# ============================================================================


class TestListTenantUsers:
    """Tests for GET /api/tenant-admin/users."""

    def test_list_users_returns_tenant_users(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Should return users belonging to the current tenant."""
        mock_cognito_client.list_users.return_value = {
            'Users': [
                {
                    'Username': 'user1@example.com',
                    'Attributes': [
                        {'Name': 'email', 'Value': 'user1@example.com'},
                        {'Name': 'name', 'Value': 'User One'},
                        {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
                    ],
                    'UserStatus': 'CONFIRMED',
                    'Enabled': True,
                    'UserCreateDate': MagicMock(isoformat=lambda: '2024-01-01T00:00:00'),
                    'UserLastModifiedDate': MagicMock(isoformat=lambda: '2024-01-02T00:00:00'),
                },
                {
                    'Username': 'user2@example.com',
                    'Attributes': [
                        {'Name': 'email', 'Value': 'user2@example.com'},
                        {'Name': 'name', 'Value': 'User Two'},
                        {'Name': 'custom:tenants', 'Value': '["other-tenant"]'},
                    ],
                    'UserStatus': 'CONFIRMED',
                    'Enabled': True,
                    'UserCreateDate': MagicMock(isoformat=lambda: '2024-01-01T00:00:00'),
                    'UserLastModifiedDate': MagicMock(isoformat=lambda: '2024-01-02T00:00:00'),
                },
            ],
            'PaginationToken': None,
        }

        with patch('routes.tenant_admin_users.DatabaseManager') as mock_db_class:
            mock_db = MagicMock()
            mock_db_class.return_value = mock_db
            mock_db.execute_query.return_value = [{'role': 'Finance_Read'}]

            response = client.get(
                '/api/tenant-admin/users',
                headers=tenant_admin_auth
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1
        assert data['users'][0]['email'] == 'user1@example.com'

    def test_list_users_access_denied_wrong_tenant(
        self, client, tenant_admin_auth, mock_cognito_client
    ):
        """Should return 403 if user doesn't have access to requested tenant."""
        with patch('routes.tenant_admin_users.get_current_tenant', return_value='other-tenant'), \
             patch('routes.tenant_admin_users.get_user_tenants', return_value=['test-tenant']):
            response = client.get(
                '/api/tenant-admin/users',
                headers=tenant_admin_auth
            )
        assert response.status_code == 403


# ============================================================================
# Create User Tests
# ============================================================================


class TestCreateTenantUser:
    """Tests for POST /api/tenant-admin/users."""

    def test_create_user_missing_email_returns_400(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants
    ):
        """Creating a user without email should return 400."""
        response = client.post(
            '/api/tenant-admin/users',
            headers=tenant_admin_auth,
            json={'name': 'No Email User'}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'email' in data['error'].lower()

    def test_create_user_invalid_groups_returns_400(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Creating a user with invalid groups should return 400."""
        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read']):
            response = client.post(
                '/api/tenant-admin/users',
                headers=tenant_admin_auth,
                json={
                    'email': 'new@example.com',
                    'name': 'New User',
                    'groups': ['NonExistentRole']
                }
            )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'invalid' in data['error'].lower()

    def test_create_user_already_in_tenant_returns_409(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Creating a user who already exists in tenant should return 409."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'existing@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'existing@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read']):
            response = client.post(
                '/api/tenant-admin/users',
                headers=tenant_admin_auth,
                json={
                    'email': 'existing@example.com',
                    'name': 'Existing User',
                    'groups': []
                }
            )
        assert response.status_code == 409

    def test_create_new_user_success(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Creating a new user should succeed with 200."""
        # User does not exist in Cognito
        error_response = {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}}
        mock_cognito_client.admin_get_user.side_effect = ClientError(error_response, 'AdminGetUser')
        mock_cognito_client.admin_create_user.return_value = {
            'User': {
                'Username': 'newuser@example.com',
                'Attributes': [
                    {'Name': 'email', 'Value': 'newuser@example.com'},
                ],
                'UserStatus': 'FORCE_CHANGE_PASSWORD',
                'Enabled': True,
            }
        }

        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read']), \
             patch('routes.tenant_admin_users.DatabaseManager') as mock_db_class, \
             patch('routes.tenant_admin_users.InvitationService') as mock_inv_class, \
             patch('routes.tenant_admin_users.EmailTemplateService') as mock_email_class, \
             patch('auth.role_cache.invalidate_cache'), \
             patch('services.ses_email_service.SESEmailService') as mock_ses_class, \
             patch('utils.frontend_url.get_frontend_url', return_value='https://app.example.com'):
            mock_db = MagicMock()
            mock_db_class.return_value = mock_db
            mock_inv = MagicMock()
            mock_inv_class.return_value = mock_inv
            mock_inv.create_invitation.return_value = {
                'success': True,
                'invitation_id': 'inv-123',
                'temporary_password': 'TempPass123!'
            }
            mock_email = MagicMock()
            mock_email_class.return_value = mock_email
            mock_email.render_user_invitation.return_value = '<html>Welcome</html>'
            mock_email.get_invitation_subject.return_value = 'Welcome to test-tenant'
            mock_email._detect_user_language.return_value = 'en'
            mock_ses = MagicMock()
            mock_ses_class.return_value = mock_ses
            mock_ses.send_invitation.return_value = {'success': True}

            response = client.post(
                '/api/tenant-admin/users',
                headers=tenant_admin_auth,
                json={
                    'email': 'newuser@example.com',
                    'name': 'New User',
                    'password': 'TempPass123!',
                    'groups': ['Finance_Read']
                }
            )

        assert response.status_code == 200 or response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Update User Tests
# ============================================================================


class TestUpdateTenantUser:
    """Tests for PUT /api/tenant-admin/users/<username>."""

    def test_update_user_not_found_returns_404(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Updating a non-existent user should return 404."""
        error_response = {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}}
        mock_cognito_client.admin_get_user.side_effect = ClientError(error_response, 'AdminGetUser')

        response = client.put(
            '/api/tenant-admin/users/nonexistent@example.com',
            headers=tenant_admin_auth,
            json={'name': 'Updated Name'}
        )
        assert response.status_code == 404

    def test_update_user_not_in_tenant_returns_403(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Updating a user who isn't in the current tenant should return 403."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'other@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'other@example.com'},
                {'Name': 'custom:tenants', 'Value': '["other-tenant"]'},
            ],
        }

        response = client.put(
            '/api/tenant-admin/users/other@example.com',
            headers=tenant_admin_auth,
            json={'name': 'Updated Name'}
        )
        assert response.status_code == 403

    def test_update_user_name_success(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Updating user name should succeed."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'user1@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user1@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        response = client.put(
            '/api/tenant-admin/users/user1@example.com',
            headers=tenant_admin_auth,
            json={'name': 'Updated Name'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        mock_cognito_client.admin_update_user_attributes.assert_called_once()

    def test_update_user_disable_success(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Disabling a user should call admin_disable_user."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'user1@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user1@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        response = client.put(
            '/api/tenant-admin/users/user1@example.com',
            headers=tenant_admin_auth,
            json={'enabled': False}
        )
        assert response.status_code == 200
        mock_cognito_client.admin_disable_user.assert_called_once()


# ============================================================================
# Delete User Tests
# ============================================================================


class TestDeleteTenantUser:
    """Tests for DELETE /api/tenant-admin/users/<username>."""

    def test_delete_user_not_found_returns_404(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants
    ):
        """Deleting a non-existent user should return 404."""
        with patch('routes.tenant_admin_users.cognito_service') as mock_svc:
            mock_svc.get_user_tenants.side_effect = Exception('User not found')

            response = client.delete(
                '/api/tenant-admin/users/nonexistent@example.com',
                headers=tenant_admin_auth
            )
        assert response.status_code == 404

    def test_delete_user_not_in_tenant_returns_403(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants
    ):
        """Deleting a user not in current tenant should return 403."""
        with patch('routes.tenant_admin_users.cognito_service') as mock_svc:
            mock_svc.get_user_tenants.return_value = ['other-tenant']

            response = client.delete(
                '/api/tenant-admin/users/other@example.com',
                headers=tenant_admin_auth
            )
        assert response.status_code == 403

    def test_delete_user_success(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants
    ):
        """Deleting a user from tenant should succeed."""
        with patch('routes.tenant_admin_users.cognito_service') as mock_svc, \
             patch('routes.tenant_admin_users.DatabaseManager') as mock_db_class:
            mock_svc.get_user_tenants.return_value = ['test-tenant']
            mock_svc.remove_tenant_from_user.return_value = (True, False)
            mock_db = MagicMock()
            mock_db_class.return_value = mock_db

            response = client.delete(
                '/api/tenant-admin/users/user1@example.com',
                headers=tenant_admin_auth
            )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Assign User Group Tests
# ============================================================================


class TestAssignUserGroup:
    """Tests for POST /api/tenant-admin/users/<username>/groups."""

    def test_assign_group_missing_group_name_returns_400(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Assigning without groupName should return 400."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'user1@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user1@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        response = client.post(
            '/api/tenant-admin/users/user1@example.com/groups',
            headers=tenant_admin_auth,
            json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'groupName' in data['error'] or 'required' in data['error'].lower()

    def test_assign_group_invalid_role_returns_403(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Assigning an invalid role should return 403."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'user1@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user1@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read']):
            response = client.post(
                '/api/tenant-admin/users/user1@example.com/groups',
                headers=tenant_admin_auth,
                json={'groupName': 'NonExistentRole'}
            )
        assert response.status_code == 403

    def test_assign_group_success(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Assigning a valid role should succeed."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'user1@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user1@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read']), \
             patch('routes.tenant_admin_users.DatabaseManager') as mock_db_class, \
             patch('auth.role_cache.invalidate_cache'):
            mock_db = MagicMock()
            mock_db_class.return_value = mock_db

            response = client.post(
                '/api/tenant-admin/users/user1@example.com/groups',
                headers=tenant_admin_auth,
                json={'groupName': 'Finance_Read'}
            )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'Finance_Read' in data['message']


# ============================================================================
# Remove User Group Tests
# ============================================================================


class TestRemoveUserGroup:
    """Tests for DELETE /api/tenant-admin/users/<username>/groups/<group_name>."""

    def test_remove_group_user_not_found_returns_404(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Removing a group from non-existent user should return 404."""
        error_response = {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}}
        mock_cognito_client.admin_get_user.side_effect = ClientError(error_response, 'AdminGetUser')

        response = client.delete(
            '/api/tenant-admin/users/nonexistent@example.com/groups/Finance_Read',
            headers=tenant_admin_auth
        )
        assert response.status_code == 404

    def test_remove_group_success(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants,
        mock_cognito_client
    ):
        """Removing a valid role should succeed."""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'user1@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user1@example.com'},
                {'Name': 'custom:tenants', 'Value': '["test-tenant"]'},
            ],
        }

        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read']), \
             patch('routes.tenant_admin_users.DatabaseManager') as mock_db_class, \
             patch('auth.role_cache.invalidate_cache'):
            mock_db = MagicMock()
            mock_db_class.return_value = mock_db

            response = client.delete(
                '/api/tenant-admin/users/user1@example.com/groups/Finance_Read',
                headers=tenant_admin_auth
            )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Get Available Roles Tests
# ============================================================================


class TestGetAvailableRoles:
    """Tests for GET /api/tenant-admin/roles."""

    def test_get_roles_returns_available_roles(
        self, client, tenant_admin_auth, mock_get_tenant, mock_user_tenants
    ):
        """Should return the list of roles available for the tenant."""
        with patch('routes.tenant_admin_users.get_available_roles_for_tenant',
                   return_value=['Tenant_Admin', 'Finance_Read', 'STR_Read']):
            response = client.get(
                '/api/tenant-admin/roles',
                headers=tenant_admin_auth
            )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 3
        role_names = [r['name'] for r in data['roles']]
        assert 'Tenant_Admin' in role_names
        assert 'Finance_Read' in role_names

    def test_get_roles_access_denied_wrong_tenant(
        self, client, tenant_admin_auth, mock_cognito_client
    ):
        """Should return 403 if user doesn't have access to requested tenant."""
        with patch('routes.tenant_admin_users.get_current_tenant', return_value='other-tenant'), \
             patch('routes.tenant_admin_users.get_user_tenants', return_value=['test-tenant']):
            response = client.get(
                '/api/tenant-admin/roles',
                headers=tenant_admin_auth
            )
        assert response.status_code == 403
