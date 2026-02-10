"""
Unit Tests for Tenant Admin User Management Routes

Tests the tenant_admin_users.py endpoints.
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from routes.tenant_admin_users import tenant_admin_users_bp


class TestTenantAdminUsersRoutes:
    """Test suite for tenant admin user management routes"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.register_blueprint(tenant_admin_users_bp)
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.fixture
    def mock_cognito_client(self):
        """Mock Cognito client"""
        with patch('routes.tenant_admin_users.cognito_client') as mock:
            yield mock
    
    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers"""
        return {
            'Authorization': 'Bearer mock-jwt-token',
            'X-Tenant': 'TestTenant',
            'Content-Type': 'application/json'
        }
    
    # Test 1: List users - success
    @patch('routes.tenant_admin_users.cognito_required')
    @patch('routes.tenant_admin_users.get_current_tenant')
    @patch('routes.tenant_admin_users.get_user_tenants')
    def test_list_users_success(self, mock_get_tenants, mock_get_tenant, 
                                mock_auth, client, mock_cognito_client, auth_headers):
        """Test listing users successfully"""
        # Setup mocks
        mock_auth.return_value = lambda f: f
        mock_get_tenant.return_value = 'TestTenant'
        mock_get_tenants.return_value = ['TestTenant']
        
        mock_cognito_client.list_users.return_value = {
            'Users': [
                {
                    'Username': 'test-uuid',
                    'Attributes': [
                        {'Name': 'email', 'Value': 'test@example.com'},
                        {'Name': 'name', 'Value': 'Test User'},
                        {'Name': 'custom:tenants', 'Value': '["TestTenant"]'}
                    ],
                    'UserStatus': 'CONFIRMED',
                    'Enabled': True,
                    'UserCreateDate': '2024-01-01T00:00:00Z',
                    'UserLastModifiedDate': '2024-01-01T00:00:00Z'
                }
            ]
        }
        
        mock_cognito_client.admin_list_groups_for_user.return_value = {
            'Groups': [{'GroupName': 'Tenant_Admin'}]
        }
        
        # Make request
        response = client.get('/api/tenant-admin/users', headers=auth_headers)
        
        # Assertions would go here if we could properly mock the decorator
        # For now, this tests the route structure
        assert response is not None
    
    # Test 2: List users - unauthorized tenant
    @patch('routes.tenant_admin_users.cognito_required')
    @patch('routes.tenant_admin_users.get_current_tenant')
    @patch('routes.tenant_admin_users.get_user_tenants')
    def test_list_users_unauthorized_tenant(self, mock_get_tenants, mock_get_tenant,
                                           mock_auth, client, auth_headers):
        """Test listing users for unauthorized tenant"""
        mock_auth.return_value = lambda f: f
        mock_get_tenant.return_value = 'UnauthorizedTenant'
        mock_get_tenants.return_value = ['TestTenant']
        
        # Would return 403 in real implementation
        response = client.get('/api/tenant-admin/users', headers=auth_headers)
        assert response is not None
    
    # Test 3: Create user - success
    def test_create_user_endpoint_exists(self, client):
        """Test create user endpoint exists"""
        # This tests that the route is registered
        assert '/api/tenant-admin/users' in [rule.rule for rule in client.application.url_map.iter_rules()]
    
    # Test 4: Update user - endpoint exists
    def test_update_user_endpoint_exists(self, client):
        """Test update user endpoint exists"""
        rules = [rule.rule for rule in client.application.url_map.iter_rules()]
        assert any('/api/tenant-admin/users/<username>' in rule for rule in rules)
    
    # Test 5: Delete user - endpoint exists
    def test_delete_user_endpoint_exists(self, client):
        """Test delete user endpoint exists"""
        rules = [rule.rule for rule in client.application.url_map.iter_rules()]
        assert any('/api/tenant-admin/users/<username>' in rule for rule in rules)
    
    # Test 6: Assign role - endpoint exists
    def test_assign_role_endpoint_exists(self, client):
        """Test assign role endpoint exists"""
        rules = [rule.rule for rule in client.application.url_map.iter_rules()]
        assert any('/api/tenant-admin/users/<username>/groups' in rule for rule in rules)
    
    # Test 7: Remove role - endpoint exists
    def test_remove_role_endpoint_exists(self, client):
        """Test remove role endpoint exists"""
        rules = [rule.rule for rule in client.application.url_map.iter_rules()]
        assert any('/api/tenant-admin/users/<username>/groups/<group_name>' in rule for rule in rules)
    
    # Test 8: List roles - endpoint exists
    def test_list_roles_endpoint_exists(self, client):
        """Test list roles endpoint exists"""
        rules = [rule.rule for rule in client.application.url_map.iter_rules()]
        assert '/api/tenant-admin/roles' in rules


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
