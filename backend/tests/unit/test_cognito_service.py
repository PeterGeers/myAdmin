"""
Unit Tests for CognitoService

Tests the CognitoService methods for user management and invitation sending.
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
    def cognito_service(self):
        """Create CognitoService instance"""
        return CognitoService()
    
    @pytest.fixture
    def mock_cognito_client(self):
        """Mock Cognito client"""
        with patch('services.cognito_service.boto3.client') as mock_client:
            yield mock_client.return_value
    
    # Test 1: Initialize service
    def test_init_service(self, cognito_service):
        """Test CognitoService initialization"""
        assert cognito_service is not None
        assert hasattr(cognito_service, 'cognito_client')
        assert hasattr(cognito_service, 'user_pool_id')
    
    # Test 2: Create user successfully
    @patch('services.cognito_service.boto3.client')
    def test_create_user_success(self, mock_boto_client, cognito_service):
        """Test successful user creation"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.admin_create_user.return_value = {
            'User': {
                'Username': 'test-uuid',
                'UserStatus': 'FORCE_CHANGE_PASSWORD'
            }
        }
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.create_user(
            email='test@example.com',
            name='Test User',
            temporary_password='TempPass123!',
            tenants=['TestTenant']
        )
        
        assert result['success'] is True
        assert result['username'] == 'test-uuid'
        mock_client.admin_create_user.assert_called_once()
    
    # Test 3: Create user with existing email
    @patch('services.cognito_service.boto3.client')
    def test_create_user_already_exists(self, mock_boto_client, cognito_service):
        """Test creating user with existing email"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.admin_create_user.side_effect = ClientError(
            {'Error': {'Code': 'UsernameExistsException', 'Message': 'User exists'}},
            'AdminCreateUser'
        )
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.create_user(
            email='existing@example.com',
            name='Existing User',
            temporary_password='TempPass123!',
            tenants=['TestTenant']
        )
        
        assert result['success'] is False
        assert 'exists' in result['error'].lower()
    
    # Test 4: Get user details
    @patch('services.cognito_service.boto3.client')
    def test_get_user_success(self, mock_boto_client, cognito_service):
        """Test getting user details"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.admin_get_user.return_value = {
            'Username': 'test-uuid',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'test@example.com'},
                {'Name': 'name', 'Value': 'Test User'},
                {'Name': 'custom:tenants', 'Value': '["TestTenant"]'}
            ],
            'UserStatus': 'CONFIRMED',
            'Enabled': True
        }
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.get_user('test-uuid')
        
        assert result['success'] is True
        assert result['email'] == 'test@example.com'
        assert result['name'] == 'Test User'
        assert 'TestTenant' in result['tenants']
    
    # Test 5: Get user not found
    @patch('services.cognito_service.boto3.client')
    def test_get_user_not_found(self, mock_boto_client, cognito_service):
        """Test getting non-existent user"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.admin_get_user.side_effect = ClientError(
            {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}},
            'AdminGetUser'
        )
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.get_user('nonexistent-uuid')
        
        assert result['success'] is False
        assert 'not found' in result['error'].lower()
    
    # Test 6: Update user attributes
    @patch('services.cognito_service.boto3.client')
    def test_update_user_success(self, mock_boto_client, cognito_service):
        """Test updating user attributes"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.update_user(
            username='test-uuid',
            name='Updated Name'
        )
        
        assert result['success'] is True
        mock_client.admin_update_user_attributes.assert_called_once()
    
    # Test 7: Delete user
    @patch('services.cognito_service.boto3.client')
    def test_delete_user_success(self, mock_boto_client, cognito_service):
        """Test deleting user"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.delete_user('test-uuid')
        
        assert result['success'] is True
        mock_client.admin_delete_user.assert_called_once()
    
    # Test 8: Enable user
    @patch('services.cognito_service.boto3.client')
    def test_enable_user_success(self, mock_boto_client, cognito_service):
        """Test enabling user"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.enable_user('test-uuid')
        
        assert result['success'] is True
        mock_client.admin_enable_user.assert_called_once()
    
    # Test 9: Disable user
    @patch('services.cognito_service.boto3.client')
    def test_disable_user_success(self, mock_boto_client, cognito_service):
        """Test disabling user"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.disable_user('test-uuid')
        
        assert result['success'] is True
        mock_client.admin_disable_user.assert_called_once()
    
    # Test 10: Add user to group
    @patch('services.cognito_service.boto3.client')
    def test_add_user_to_group_success(self, mock_boto_client, cognito_service):
        """Test adding user to group"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.add_user_to_group('test-uuid', 'Tenant_Admin')
        
        assert result['success'] is True
        mock_client.admin_add_user_to_group.assert_called_once()
    
    # Test 11: Remove user from group
    @patch('services.cognito_service.boto3.client')
    def test_remove_user_from_group_success(self, mock_boto_client, cognito_service):
        """Test removing user from group"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.remove_user_from_group('test-uuid', 'Tenant_Admin')
        
        assert result['success'] is True
        mock_client.admin_remove_user_from_group.assert_called_once()
    
    # Test 12: List user groups
    @patch('services.cognito_service.boto3.client')
    def test_list_user_groups_success(self, mock_boto_client, cognito_service):
        """Test listing user groups"""
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        mock_client.admin_list_groups_for_user.return_value = {
            'Groups': [
                {'GroupName': 'Tenant_Admin'},
                {'GroupName': 'Finance_Read'}
            ]
        }
        
        cognito_service.cognito_client = mock_client
        
        result = cognito_service.list_user_groups('test-uuid')
        
        assert result['success'] is True
        assert 'Tenant_Admin' in result['groups']
        assert 'Finance_Read' in result['groups']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
