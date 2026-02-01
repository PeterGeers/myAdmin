"""
Unit tests for AWS Cognito authentication utilities

Tests the core authentication functions:
- extract_user_credentials: JWT token extraction and validation
- validate_permissions: Role-based permission checking
- cognito_required: Flask route decorator
"""

import pytest
import json
import base64
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from src.auth.cognito_utils import (
    extract_user_credentials,
    validate_permissions,
    get_permissions_for_roles,
    cognito_required,
    cors_headers,
    handle_options_request,
    create_error_response,
    create_success_response,
    log_successful_access
)


class TestCORSHelpers:
    """Test CORS helper functions"""
    
    def test_cors_headers(self):
        """Test CORS headers are correctly formatted"""
        headers = cors_headers()
        
        assert headers['Access-Control-Allow-Origin'] == '*'
        assert 'GET' in headers['Access-Control-Allow-Methods']
        assert 'POST' in headers['Access-Control-Allow-Methods']
        assert 'Authorization' in headers['Access-Control-Allow-Headers']
    
    def test_handle_options_request(self):
        """Test OPTIONS request handler"""
        response = handle_options_request()
        
        assert response['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in response['headers']
        assert response['body'] == ''


class TestResponseHelpers:
    """Test response helper functions"""
    
    def test_create_error_response(self):
        """Test error response creation"""
        response = create_error_response(404, 'Not found')
        
        assert response['statusCode'] == 404
        assert 'Access-Control-Allow-Origin' in response['headers']
        body = json.loads(response['body'])
        assert body['error'] == 'Not found'
    
    def test_create_error_response_with_details(self):
        """Test error response with additional details"""
        response = create_error_response(403, 'Forbidden', 'Missing role: Admin')
        
        body = json.loads(response['body'])
        assert body['error'] == 'Forbidden'
        assert body['details'] == 'Missing role: Admin'
    
    def test_create_success_response(self):
        """Test success response creation"""
        data = {'message': 'Success', 'count': 42}
        response = create_success_response(data)
        
        assert response['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in response['headers']
        body = json.loads(response['body'])
        assert body['message'] == 'Success'
        assert body['count'] == 42
    
    def test_create_success_response_custom_status(self):
        """Test success response with custom status code"""
        response = create_success_response({'created': True}, status_code=201)
        
        assert response['statusCode'] == 201


class TestExtractUserCredentials:
    """Test JWT token extraction and validation"""
    
    def create_jwt_token(self, payload):
        """Helper to create a mock JWT token"""
        # JWT format: header.payload.signature
        header = base64.urlsafe_b64encode(json.dumps({'alg': 'RS256'}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = 'mock_signature'
        return f"{header}.{payload_encoded}.{signature}"
    
    def test_extract_valid_token_lambda_event(self):
        """Test extracting credentials from valid Lambda event"""
        payload = {
            'email': 'user@example.com',
            'cognito:groups': ['Administrators', 'Finance_CRUD'],
            'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = self.create_jwt_token(payload)
        
        event = {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email == 'user@example.com'
        assert 'Administrators' in user_roles
        assert 'Finance_CRUD' in user_roles
        assert error is None
    
    def test_extract_valid_token_flask_request(self):
        """Test extracting credentials from Flask request object"""
        payload = {
            'email': 'accountant@example.com',
            'cognito:groups': ['Accountants'],
            'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = self.create_jwt_token(payload)
        
        # Mock Flask request
        mock_request = Mock()
        mock_request.headers = {
            'Authorization': f'Bearer {token}'
        }
        
        user_email, user_roles, error = extract_user_credentials(mock_request)
        
        assert user_email == 'accountant@example.com'
        assert user_roles == ['Accountants']
        assert error is None
    
    def test_extract_missing_authorization_header(self):
        """Test error when Authorization header is missing"""
        event = {'headers': {}}
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email is None
        assert user_roles is None
        assert error is not None
        assert error['statusCode'] == 401
        body = json.loads(error['body'])
        assert 'Missing Authorization header' in body['error']
    
    def test_extract_invalid_bearer_format(self):
        """Test error when Authorization header doesn't start with 'Bearer '"""
        event = {
            'headers': {
                'Authorization': 'InvalidFormat token123'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email is None
        assert user_roles is None
        assert error is not None
        assert error['statusCode'] == 401
    
    def test_extract_empty_token(self):
        """Test error when token is empty"""
        event = {
            'headers': {
                'Authorization': 'Bearer '
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email is None
        assert user_roles is None
        assert error is not None
        assert error['statusCode'] == 401
    
    def test_extract_malformed_jwt(self):
        """Test error when JWT doesn't have 3 parts"""
        event = {
            'headers': {
                'Authorization': 'Bearer invalid.token'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email is None
        assert user_roles is None
        assert error is not None
        assert error['statusCode'] == 401
    
    def test_extract_expired_token(self):
        """Test error when JWT token is expired"""
        payload = {
            'email': 'user@example.com',
            'cognito:groups': ['Viewers'],
            'exp': (datetime.utcnow() - timedelta(hours=1)).timestamp()  # Expired 1 hour ago
        }
        token = self.create_jwt_token(payload)
        
        event = {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email is None
        assert user_roles is None
        assert error is not None
        assert error['statusCode'] == 401
        body = json.loads(error['body'])
        assert 'expired' in body['error'].lower()
    
    def test_extract_username_fallback(self):
        """Test extracting username when email is not present"""
        payload = {
            'username': 'testuser',
            'cognito:groups': ['Viewers'],
            'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = self.create_jwt_token(payload)
        
        event = {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email == 'testuser'
        assert error is None
    
    def test_extract_sub_fallback(self):
        """Test extracting sub when email and username are not present"""
        payload = {
            'sub': '12345-67890',
            'cognito:groups': ['Viewers'],
            'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = self.create_jwt_token(payload)
        
        event = {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email == '12345-67890'
        assert error is None
    
    def test_extract_no_groups(self):
        """Test extracting credentials when user has no groups"""
        payload = {
            'email': 'user@example.com',
            'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = self.create_jwt_token(payload)
        
        event = {
            'headers': {
                'Authorization': f'Bearer {token}'
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email == 'user@example.com'
        assert user_roles == []
        assert error is None
    
    def test_extract_case_insensitive_header(self):
        """Test that Authorization header lookup is case-insensitive"""
        payload = {
            'email': 'user@example.com',
            'cognito:groups': ['Viewers'],
            'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        token = self.create_jwt_token(payload)
        
        event = {
            'headers': {
                'authorization': f'Bearer {token}'  # lowercase
            }
        }
        
        user_email, user_roles, error = extract_user_credentials(event)
        
        assert user_email == 'user@example.com'
        assert error is None


class TestGetPermissionsForRoles:
    """Test permission extraction from roles"""
    
    def test_get_permissions_single_role(self):
        """Test getting permissions for a single role"""
        permissions = get_permissions_for_roles(['Finance_Read'])
        
        assert 'finance_read' in permissions
        assert 'finance_list' in permissions
        assert 'finance_create' not in permissions  # Read-only role
    
    def test_get_permissions_multiple_roles(self):
        """Test getting permissions for multiple roles"""
        permissions = get_permissions_for_roles(['Finance_Read', 'STR_Read'])
        
        assert 'finance_read' in permissions
        assert 'str_read' in permissions
    
    def test_get_permissions_unknown_role(self):
        """Test getting permissions for unknown role"""
        permissions = get_permissions_for_roles(['UnknownRole'])
        
        assert permissions == []
    
    def test_get_permissions_empty_roles(self):
        """Test getting permissions for empty role list"""
        permissions = get_permissions_for_roles([])
        
        assert permissions == []


class TestValidatePermissions:
    """Test permission validation logic"""
    
    def test_validate_with_sufficient_permissions(self):
        """Test validation when user has all required permissions"""
        is_authorized, error = validate_permissions(
            ['Finance_Read'],
            ['finance_read', 'finance_list']
        )
        
        assert is_authorized is True
        assert error is None
    
    def test_validate_with_insufficient_permissions(self):
        """Test validation when user lacks required permissions"""
        is_authorized, error = validate_permissions(
            ['Finance_Read'],
            ['finance_create', 'finance_delete']
        )
        
        assert is_authorized is False
        assert error is not None
        assert error['statusCode'] == 403
        body = json.loads(error['body'])
        assert 'Insufficient permissions' in body['error']
    
    def test_validate_no_roles(self):
        """Test validation when user has no roles"""
        is_authorized, error = validate_permissions(
            [],
            ['finance_read']
        )
        
        assert is_authorized is False
        assert error is not None
        assert error['statusCode'] == 403
    
    def test_validate_no_required_permissions(self):
        """Test validation when no specific permissions are required"""
        is_authorized, error = validate_permissions(
            ['Viewers'],
            []
        )
        
        assert is_authorized is True
        assert error is None
    
    def test_validate_multiple_roles_combined_permissions(self):
        """Test that permissions from multiple roles are combined"""
        is_authorized, error = validate_permissions(
            ['Finance_Read', 'STR_Read'],
            ['finance_read', 'str_read']
        )
        
        assert is_authorized is True
        assert error is None
    


class TestCognitoRequiredDecorator:
    """Test the cognito_required decorator for Flask routes
    
    Note: Full decorator testing requires Flask app context and is better suited
    for integration tests. These unit tests verify the decorator can be applied
    and that the underlying authentication functions work correctly.
    """
    
    def test_decorator_can_be_applied(self):
        """Test that decorator can be applied to a function"""
        @cognito_required()
        def test_route(user_email, user_roles):
            return {'email': user_email, 'roles': user_roles}
        
        # Verify decorator was applied
        assert hasattr(test_route, '__wrapped__')
        assert test_route.__name__ == 'test_route'
    
    def test_decorator_with_required_roles_parameter(self):
        """Test decorator accepts required_roles parameter"""
        @cognito_required(required_roles=['Administrators'])
        def admin_route(user_email, user_roles):
            return {'success': True}
        
        assert hasattr(admin_route, '__wrapped__')
    
    def test_decorator_with_required_permissions_parameter(self):
        """Test decorator accepts required_permissions parameter"""
        @cognito_required(required_permissions=['finance_read'])
        def read_route(user_email, user_roles):
            return {'success': True}
        
        assert hasattr(read_route, '__wrapped__')


class TestLogSuccessfulAccess:
    """Test audit logging functionality"""
    
    def test_log_successful_access_basic(self, capsys):
        """Test basic access logging"""
        log_successful_access('user@example.com', ['Administrators'], 'get_invoices')
        
        captured = capsys.readouterr()
        assert 'ACCESS_LOG' in captured.out
        assert 'user@example.com' in captured.out
        assert 'get_invoices' in captured.out
    
    def test_log_successful_access_with_details(self, capsys):
        """Test access logging with additional details"""
        details = {'resource_id': '12345', 'action': 'update'}
        log_successful_access('admin@example.com', ['Administrators'], 'update_invoice', details)
        
        captured = capsys.readouterr()
        assert 'ACCESS_LOG' in captured.out
        assert 'admin@example.com' in captured.out
        assert '12345' in captured.out


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
