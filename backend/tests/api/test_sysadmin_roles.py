"""
API tests for routes/sysadmin_roles.py

Tests role management endpoints and authentication enforcement
for the SysAdmin roles blueprint.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestSysadminRolesAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

    def test_list_roles_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list roles should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/sysadmin/roles')
        assert response.status_code in (401, 403)

    def test_list_roles_non_sysadmin_returns_403(self, client, mock_auth):
        """Non-SysAdmin user should get 403 on list roles."""
        response = client.get(
            '/api/sysadmin/roles',
            headers=mock_auth
        )
        assert response.status_code == 403

    def test_create_role_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create role should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/sysadmin/roles',
                                   json={'name': 'TestRole'})
        assert response.status_code in (401, 403)

    def test_delete_role_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to delete role should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.delete('/api/sysadmin/roles/TestRole')
        assert response.status_code in (401, 403)


# ============================================================================
# List Roles Tests
# ============================================================================


class TestListRoles:
    """Tests for GET /api/sysadmin/roles."""

    @patch('routes.sysadmin_roles.cognito_client')
    def test_list_roles_returns_categorized_groups(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """List roles returns groups categorized by type."""
        mock_cognito.list_groups.return_value = {
            'Groups': [
                {
                    'GroupName': 'SysAdmin',
                    'Description': 'System administrators',
                    'CreationDate': datetime(2024, 1, 1)
                },
                {
                    'GroupName': 'Finance_CRUD',
                    'Description': 'Finance full access',
                    'CreationDate': datetime(2024, 1, 2)
                },
            ]
        }
        mock_cognito.list_users_in_group.return_value = {
            'Users': [{'Username': 'user1'}]
        }

        response = client.get(
            '/api/sysadmin/roles',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total'] == 2
        roles = data['roles']
        sysadmin_role = next(r for r in roles if r['name'] == 'SysAdmin')
        assert sysadmin_role['category'] == 'platform'
        finance_role = next(r for r in roles if r['name'] == 'Finance_CRUD')
        assert finance_role['category'] == 'module'


# ============================================================================
# Create Role Tests
# ============================================================================


class TestCreateRole:
    """Tests for POST /api/sysadmin/roles."""

    @patch('routes.sysadmin_roles.cognito_client')
    def test_create_role_missing_name_returns_400(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Create role without name returns 400."""
        response = client.post(
            '/api/sysadmin/roles',
            headers=mock_auth_sysadmin,
            json={'description': 'No name provided'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'name' in data['error'].lower()

    @patch('routes.sysadmin_roles.cognito_client')
    def test_create_role_success_returns_201(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Create role with valid data returns 201."""
        # Simulate group doesn't exist yet
        mock_cognito.exceptions = MagicMock()
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.get_group.side_effect = \
            mock_cognito.exceptions.ResourceNotFoundException('Not found')
        mock_cognito.create_group.return_value = {}

        response = client.post(
            '/api/sysadmin/roles',
            headers=mock_auth_sysadmin,
            json={'name': 'NewTestRole', 'description': 'A test role'}
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['name'] == 'NewTestRole'


# ============================================================================
# Update Role Tests
# ============================================================================


class TestUpdateRole:
    """Tests for PUT /api/sysadmin/roles/<role_name>."""

    @patch('routes.sysadmin_roles.cognito_client')
    def test_update_role_nonexistent_returns_404(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Update non-existent role returns 404."""
        mock_cognito.exceptions = MagicMock()
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.get_group.side_effect = \
            mock_cognito.exceptions.ResourceNotFoundException('Not found')

        response = client.put(
            '/api/sysadmin/roles/NonExistentRole',
            headers=mock_auth_sysadmin,
            json={'description': 'Updated description'}
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error'].lower()

    @patch('routes.sysadmin_roles.cognito_client')
    def test_update_role_success_returns_200(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Update existing role returns 200."""
        mock_cognito.exceptions = MagicMock()
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.get_group.return_value = {
            'Group': {'GroupName': 'ExistingRole'}
        }
        mock_cognito.update_group.return_value = {}

        response = client.put(
            '/api/sysadmin/roles/ExistingRole',
            headers=mock_auth_sysadmin,
            json={'description': 'Updated description', 'precedence': 10}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Delete Role Tests
# ============================================================================


class TestDeleteRole:
    """Tests for DELETE /api/sysadmin/roles/<role_name>."""

    @patch('routes.sysadmin_roles.cognito_client')
    def test_delete_role_with_users_returns_409(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Delete role that has active users returns 409."""
        mock_cognito.exceptions = MagicMock()
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.get_group.return_value = {
            'Group': {'GroupName': 'BusyRole'}
        }
        mock_cognito.list_users_in_group.return_value = {
            'Users': [{'Username': 'user1'}]
        }

        response = client.delete(
            '/api/sysadmin/roles/BusyRole',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 409
        data = json.loads(response.data)
        assert 'users' in data['error'].lower()

    @patch('routes.sysadmin_roles.cognito_client')
    def test_delete_role_nonexistent_returns_404(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Delete non-existent role returns 404."""
        mock_cognito.exceptions = MagicMock()
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.get_group.side_effect = \
            mock_cognito.exceptions.ResourceNotFoundException('Not found')

        response = client.delete(
            '/api/sysadmin/roles/GhostRole',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 404

    @patch('routes.sysadmin_roles.cognito_client')
    def test_delete_role_empty_group_success(
        self, mock_cognito, client, mock_auth_sysadmin
    ):
        """Delete role with no users succeeds."""
        mock_cognito.exceptions = MagicMock()
        mock_cognito.exceptions.ResourceNotFoundException = type(
            'ResourceNotFoundException', (Exception,), {}
        )
        mock_cognito.get_group.return_value = {
            'Group': {'GroupName': 'EmptyRole'}
        }
        mock_cognito.list_users_in_group.return_value = {
            'Users': []
        }
        mock_cognito.delete_group.return_value = {}

        response = client.delete(
            '/api/sysadmin/roles/EmptyRole',
            headers=mock_auth_sysadmin
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
