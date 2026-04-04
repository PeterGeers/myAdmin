"""
Unit Tests for CognitoService

Tests the CognitoService methods for user management.
Updated to match current API signatures.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.cognito_service import CognitoService


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
        """Create CognitoService with mocked boto3 client"""
        svc = CognitoService()
        return svc

    # Test 1: Initialize service
    def test_init_service(self, cognito_service):
        """Test CognitoService initialization"""
        assert cognito_service is not None
        assert hasattr(cognito_service, 'client')
        assert hasattr(cognito_service, 'user_pool_id')

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

    # Test 7: Delete user
    def test_delete_user_success(self, cognito_service, mock_boto_client):
        """Test deleting user"""
        result = cognito_service.delete_user('test@example.com')

        assert result is True
        mock_boto_client.admin_delete_user.assert_called_once()

    # Test 8: Enable user via update_user
    def test_enable_user_success(self, cognito_service, mock_boto_client):
        """Test enabling user via update_user"""
        result = cognito_service.update_user(
            username='test@example.com',
            enabled=True
        )

        assert result is True
        mock_boto_client.admin_enable_user.assert_called_once()

    # Test 9: Disable user via update_user
    def test_disable_user_success(self, cognito_service, mock_boto_client):
        """Test disabling user via update_user"""
        result = cognito_service.update_user(
            username='test@example.com',
            enabled=False
        )

        assert result is True
        mock_boto_client.admin_disable_user.assert_called_once()

    # Test 10: Add user to group (now assign_role)
    def test_add_user_to_group_success(self, cognito_service, mock_boto_client):
        """Test adding user to group via assign_role"""
        result = cognito_service.assign_role('test@example.com', 'Tenant_Admin')

        assert result is True
        mock_boto_client.admin_add_user_to_group.assert_called_once()

    # Test 11: Remove user from group (now remove_role)
    def test_remove_user_from_group_success(self, cognito_service, mock_boto_client):
        """Test removing user from group via remove_role"""
        result = cognito_service.remove_role('test@example.com', 'Tenant_Admin')

        assert result is True
        mock_boto_client.admin_remove_user_from_group.assert_called_once()

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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
