"""
Unit tests for CognitoService

Tests all Cognito operations with mocked boto3 client
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.cognito_service import CognitoService


@pytest.fixture
def mock_cognito_client():
    """Mock boto3 Cognito client"""
    with patch('boto3.client') as mock_client:
        yield mock_client.return_value


@pytest.fixture
def cognito_service(mock_cognito_client):
    """Create CognitoService instance with mocked client"""
    with patch.dict(os.environ, {
        'AWS_REGION': 'eu-west-1',
        'COGNITO_USER_POOL_ID': 'test-pool-id'
    }):
        service = CognitoService()
        service.client = mock_cognito_client
        return service


class TestUserManagement:
    """Test user management methods"""
    
    def test_create_user_success(self, cognito_service, mock_cognito_client):
        """Test successful user creation"""
        mock_cognito_client.admin_create_user.return_value = {
            'User': {
                'Username': 'test@example.com',
                'Attributes': [
                    {'Name': 'email', 'Value': 'test@example.com'}
                ]
            }
        }
        
        result = cognito_service.create_user(
            email='test@example.com',
            name='Test User',
            tenant='TestTenant',
            password='TempPass123!'
        )
        
        assert result['Username'] == 'test@example.com'
        mock_cognito_client.admin_create_user.assert_called_once()
    
    def test_create_user_with_minimal_params(self, cognito_service, mock_cognito_client):
        """Test user creation with minimal parameters"""
        mock_cognito_client.admin_create_user.return_value = {
            'User': {'Username': 'test@example.com'}
        }
        
        result = cognito_service.create_user(
            email='test@example.com',
            password='TempPass123!'
        )
        
        assert result['Username'] == 'test@example.com'
    
    def test_create_user_failure(self, cognito_service, mock_cognito_client):
        """Test user creation failure"""
        mock_cognito_client.admin_create_user.side_effect = ClientError(
            {'Error': {'Code': 'UsernameExistsException', 'Message': 'User exists'}},
            'admin_create_user'
        )
        
        with pytest.raises(ClientError):
            cognito_service.create_user(
                email='test@example.com',
                password='TempPass123!'
            )
    
    def test_get_user_success(self, cognito_service, mock_cognito_client):
        """Test successful user retrieval"""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'email', 'Value': 'test@example.com'},
                {'Name': 'name', 'Value': 'Test User'}
            ]
        }
        
        result = cognito_service.get_user('test@example.com')
        
        assert result['Username'] == 'test@example.com'
        mock_cognito_client.admin_get_user.assert_called_once()
    
    def test_get_user_not_found(self, cognito_service, mock_cognito_client):
        """Test user not found"""
        mock_cognito_client.admin_get_user.side_effect = ClientError(
            {'Error': {'Code': 'UserNotFoundException', 'Message': 'User not found'}},
            'admin_get_user'
        )
        
        result = cognito_service.get_user('nonexistent@example.com')
        
        assert result is None
    
    def test_list_users_no_filter(self, cognito_service, mock_cognito_client):
        """Test listing all users"""
        mock_cognito_client.list_users.return_value = {
            'Users': [
                {'Username': 'user1@example.com'},
                {'Username': 'user2@example.com'}
            ]
        }
        
        result = cognito_service.list_users()
        
        assert len(result) == 2
        assert result[0]['Username'] == 'user1@example.com'
    
    def test_list_users_with_tenant_filter(self, cognito_service, mock_cognito_client):
        """Test listing users filtered by tenant"""
        mock_cognito_client.list_users.return_value = {
            'Users': [
                {
                    'Username': 'user1@example.com',
                    'Attributes': [
                        {'Name': 'custom:tenants', 'Value': '["Tenant1", "Tenant2"]'}
                    ]
                },
                {
                    'Username': 'user2@example.com',
                    'Attributes': [
                        {'Name': 'custom:tenants', 'Value': '["Tenant2"]'}
                    ]
                }
            ]
        }
        
        result = cognito_service.list_users(tenant='Tenant1')
        
        assert len(result) == 1
        assert result[0]['Username'] == 'user1@example.com'
    
    def test_update_user_name(self, cognito_service, mock_cognito_client):
        """Test updating user name"""
        result = cognito_service.update_user(
            username='test@example.com',
            name='New Name'
        )
        
        assert result is True
        mock_cognito_client.admin_update_user_attributes.assert_called_once()
    
    def test_update_user_enable(self, cognito_service, mock_cognito_client):
        """Test enabling user"""
        result = cognito_service.update_user(
            username='test@example.com',
            enabled=True
        )
        
        assert result is True
        mock_cognito_client.admin_enable_user.assert_called_once()
    
    def test_update_user_disable(self, cognito_service, mock_cognito_client):
        """Test disabling user"""
        result = cognito_service.update_user(
            username='test@example.com',
            enabled=False
        )
        
        assert result is True
        mock_cognito_client.admin_disable_user.assert_called_once()
    
    def test_delete_user_success(self, cognito_service, mock_cognito_client):
        """Test successful user deletion"""
        result = cognito_service.delete_user('test@example.com')
        
        assert result is True
        mock_cognito_client.admin_delete_user.assert_called_once()


class TestRoleManagement:
    """Test role (group) management methods"""
    
    def test_assign_role_success(self, cognito_service, mock_cognito_client):
        """Test successful role assignment"""
        result = cognito_service.assign_role('test@example.com', 'Finance_Read')
        
        assert result is True
        mock_cognito_client.admin_add_user_to_group.assert_called_once()
    
    def test_remove_role_success(self, cognito_service, mock_cognito_client):
        """Test successful role removal"""
        result = cognito_service.remove_role('test@example.com', 'Finance_Read')
        
        assert result is True
        mock_cognito_client.admin_remove_user_from_group.assert_called_once()
    
    def test_list_user_groups(self, cognito_service, mock_cognito_client):
        """Test listing user groups"""
        mock_cognito_client.admin_list_groups_for_user.return_value = {
            'Groups': [
                {'GroupName': 'Finance_Read'},
                {'GroupName': 'Tenant_Admin'}
            ]
        }
        
        result = cognito_service.list_user_groups('test@example.com')
        
        assert len(result) == 2
        assert 'Finance_Read' in result
        assert 'Tenant_Admin' in result
    
    def test_list_groups(self, cognito_service, mock_cognito_client):
        """Test listing all groups"""
        mock_cognito_client.list_groups.return_value = {
            'Groups': [
                {'GroupName': 'SysAdmin', 'Description': 'System administrators'},
                {'GroupName': 'Tenant_Admin', 'Description': 'Tenant administrators'}
            ]
        }
        
        result = cognito_service.list_groups()
        
        assert len(result) == 2
        assert result[0]['GroupName'] == 'SysAdmin'
    
    def test_create_group_success(self, cognito_service, mock_cognito_client):
        """Test successful group creation"""
        mock_cognito_client.create_group.return_value = {
            'Group': {
                'GroupName': 'NewRole',
                'Description': 'New role description'
            }
        }
        
        result = cognito_service.create_group('NewRole', 'New role description')
        
        assert result['GroupName'] == 'NewRole'
        mock_cognito_client.create_group.assert_called_once()
    
    def test_update_group_success(self, cognito_service, mock_cognito_client):
        """Test successful group update"""
        mock_cognito_client.update_group.return_value = {
            'Group': {
                'GroupName': 'Finance_Read',
                'Description': 'Updated description'
            }
        }
        
        result = cognito_service.update_group(
            'Finance_Read',
            description='Updated description',
            precedence=10
        )
        
        assert result['Description'] == 'Updated description'
        mock_cognito_client.update_group.assert_called_once()
    
    def test_delete_group_success(self, cognito_service, mock_cognito_client):
        """Test successful group deletion"""
        result = cognito_service.delete_group('OldRole')
        
        assert result is True
        mock_cognito_client.delete_group.assert_called_once()
    
    def test_get_group_user_count(self, cognito_service, mock_cognito_client):
        """Test getting group user count"""
        mock_cognito_client.list_users_in_group.return_value = {
            'Users': [
                {'Username': 'user1@example.com'},
                {'Username': 'user2@example.com'},
                {'Username': 'user3@example.com'}
            ]
        }
        
        result = cognito_service.get_group_user_count('Finance_Read')
        
        assert result == 3


class TestTenantManagement:
    """Test tenant management methods"""
    
    def test_add_tenant_to_user_new_tenant(self, cognito_service, mock_cognito_client):
        """Test adding new tenant to user"""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '["Tenant1"]'}
            ]
        }
        
        result = cognito_service.add_tenant_to_user('test@example.com', 'Tenant2')
        
        assert result is True
        mock_cognito_client.admin_update_user_attributes.assert_called_once()
    
    def test_add_tenant_to_user_existing_tenant(self, cognito_service, mock_cognito_client):
        """Test adding tenant that user already has"""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '["Tenant1"]'}
            ]
        }
        
        result = cognito_service.add_tenant_to_user('test@example.com', 'Tenant1')
        
        assert result is True
        # Should not call update since tenant already exists
        mock_cognito_client.admin_update_user_attributes.assert_not_called()
    
    def test_remove_tenant_from_user_multiple_tenants(self, cognito_service, mock_cognito_client):
        """Test removing tenant when user has multiple tenants"""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '["Tenant1", "Tenant2"]'}
            ]
        }
        
        success, user_deleted = cognito_service.remove_tenant_from_user(
            'test@example.com',
            'Tenant1'
        )
        
        assert success is True
        assert user_deleted is False
        mock_cognito_client.admin_update_user_attributes.assert_called_once()
        mock_cognito_client.admin_delete_user.assert_not_called()
    
    def test_remove_tenant_from_user_last_tenant(self, cognito_service, mock_cognito_client):
        """Test removing last tenant (should delete user)"""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '["Tenant1"]'}
            ]
        }
        
        success, user_deleted = cognito_service.remove_tenant_from_user(
            'test@example.com',
            'Tenant1'
        )
        
        assert success is True
        assert user_deleted is True
        mock_cognito_client.admin_delete_user.assert_called_once()
        mock_cognito_client.admin_update_user_attributes.assert_not_called()
    
    def test_get_user_tenants(self, cognito_service, mock_cognito_client):
        """Test getting user's tenants"""
        mock_cognito_client.admin_get_user.return_value = {
            'Username': 'test@example.com',
            'UserAttributes': [
                {'Name': 'custom:tenants', 'Value': '["Tenant1", "Tenant2", "Tenant3"]'}
            ]
        }
        
        result = cognito_service.get_user_tenants('test@example.com')
        
        assert len(result) == 3
        assert 'Tenant1' in result
        assert 'Tenant2' in result
        assert 'Tenant3' in result


class TestNotifications:
    """Test notification methods"""
    
    @patch('boto3.client')
    def test_send_invitation_success(self, mock_boto_client, cognito_service):
        """Test successful invitation email"""
        mock_sns_client = Mock()
        mock_boto_client.return_value = mock_sns_client
        
        with patch.dict(os.environ, {
            'SNS_TOPIC_ARN': 'arn:aws:sns:eu-west-1:123456789:test-topic',
            'FRONTEND_URL': 'http://localhost:3000'
        }):
            result = cognito_service.send_invitation(
                'test@example.com',
                'TempPass123!',
                'TestTenant'
            )
        
        assert result is True
        mock_sns_client.publish.assert_called_once()
    
    def test_send_invitation_no_sns_configured(self, cognito_service):
        """Test invitation when SNS not configured"""
        with patch.dict(os.environ, {}, clear=True):
            result = cognito_service.send_invitation(
                'test@example.com',
                'TempPass123!',
                'TestTenant'
            )
        
        assert result is False


class TestHelperMethods:
    """Test helper methods"""
    
    def test_get_user_attribute_string(self, cognito_service):
        """Test extracting string attribute"""
        attributes = [
            {'Name': 'email', 'Value': 'test@example.com'},
            {'Name': 'name', 'Value': 'Test User'}
        ]
        
        result = cognito_service._get_user_attribute(attributes, 'name')
        
        assert result == 'Test User'
    
    def test_get_user_attribute_json_array(self, cognito_service):
        """Test extracting JSON array attribute"""
        attributes = [
            {'Name': 'custom:tenants', 'Value': '["Tenant1", "Tenant2"]'}
        ]
        
        result = cognito_service._get_user_attribute(attributes, 'custom:tenants')
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert 'Tenant1' in result
    
    def test_get_user_attribute_not_found(self, cognito_service):
        """Test extracting non-existent attribute"""
        attributes = [
            {'Name': 'email', 'Value': 'test@example.com'}
        ]
        
        result = cognito_service._get_user_attribute(attributes, 'nonexistent')
        
        assert result is None
    
    def test_get_user_attribute_tenants_not_found(self, cognito_service):
        """Test extracting non-existent tenants attribute"""
        attributes = [
            {'Name': 'email', 'Value': 'test@example.com'}
        ]
        
        result = cognito_service._get_user_attribute(attributes, 'custom:tenants')
        
        assert result == []
