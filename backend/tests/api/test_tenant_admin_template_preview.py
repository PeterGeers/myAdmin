"""
Test suite for Tenant Admin Template Preview API endpoint

Tests the POST /api/tenant-admin/templates/preview endpoint
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from tenant_admin_routes import tenant_admin_bp


@pytest.fixture
def app():
    """Create Flask app for testing"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(tenant_admin_bp)
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def mock_auth_headers():
    """Mock authentication headers"""
    return {
        'Authorization': 'Bearer mock.jwt.token',
        'X-Tenant': 'GoodwinSolutions'
    }


@pytest.fixture
def valid_template_request():
    """Valid template preview request"""
    return {
        'template_type': 'str_invoice_nl',
        'template_content': '''
            <html>
                <body>
                    <h1>Invoice {{ invoice_number }}</h1>
                    <p>Guest: {{ guest_name }}</p>
                    <p>Check-in: {{ checkin_date }}</p>
                    <p>Check-out: {{ checkout_date }}</p>
                    <p>Amount: {{ amount_gross }}</p>
                    <p>Company: {{ company_name }}</p>
                </body>
            </html>
        ''',
        'field_mappings': {}
    }


class TestTemplatePreviewEndpoint:
    """Test cases for template preview endpoint"""
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('tenant_admin_routes.TemplatePreviewService')
    def test_preview_success(
        self,
        mock_preview_service_class,
        mock_db_manager,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers,
        valid_template_request
    ):
        """Test successful template preview generation"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = True
        
        # Mock preview service
        mock_preview_service = Mock()
        mock_preview_service.generate_preview.return_value = {
            'success': True,
            'preview_html': '<html><body>Preview</body></html>',
            'validation': {
                'is_valid': True,
                'errors': [],
                'warnings': []
            },
            'sample_data_info': {
                'source': 'database',
                'record_date': '2026-01-01',
                'message': 'Using most recent data'
            }
        }
        mock_preview_service_class.return_value = mock_preview_service
        
        # Make request
        response = client.post(
            '/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request),
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'preview_html' in data
        assert 'validation' in data
        assert data['validation']['is_valid'] is True
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    def test_preview_requires_tenant_admin(
        self,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers,
        valid_template_request
    ):
        """Test that endpoint requires Tenant_Admin role"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = False  # Not tenant admin
        
        # Make request
        response = client.post(
            '/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request),
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Tenant admin access required' in data['error']
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    def test_preview_missing_template_type(
        self,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers
    ):
        """Test validation error when template_type is missing"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = True
        
        # Request without template_type
        invalid_request = {
            'template_content': '<html></html>'
        }
        
        # Make request
        response = client.post(
            '/api/tenant-admin/templates/preview',
            data=json.dumps(invalid_request),
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'template_type is required' in data['error']
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    def test_preview_missing_template_content(
        self,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers
    ):
        """Test validation error when template_content is missing"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = True
        
        # Request without template_content
        invalid_request = {
            'template_type': 'str_invoice_nl'
        }
        
        # Make request
        response = client.post(
            '/api/tenant-admin/templates/preview',
            data=json.dumps(invalid_request),
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'template_content is required' in data['error']
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('tenant_admin_routes.TemplatePreviewService')
    def test_preview_validation_failure(
        self,
        mock_preview_service_class,
        mock_db_manager,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers,
        valid_template_request
    ):
        """Test handling of validation failures"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = True
        
        # Mock preview service with validation failure
        mock_preview_service = Mock()
        mock_preview_service.generate_preview.return_value = {
            'success': False,
            'validation': {
                'is_valid': False,
                'errors': [
                    {
                        'type': 'missing_placeholder',
                        'message': 'Required placeholder missing',
                        'severity': 'error'
                    }
                ],
                'warnings': []
            }
        }
        mock_preview_service_class.return_value = mock_preview_service
        
        # Make request
        response = client.post(
            '/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request),
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'validation' in data
        assert data['validation']['is_valid'] is False
        assert len(data['validation']['errors']) > 0
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    @patch('tenant_admin_routes.DatabaseManager')
    @patch('tenant_admin_routes.TemplatePreviewService')
    def test_preview_internal_error(
        self,
        mock_preview_service_class,
        mock_db_manager,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers,
        valid_template_request
    ):
        """Test handling of internal server errors"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = True
        
        # Mock preview service to raise exception
        mock_preview_service = Mock()
        mock_preview_service.generate_preview.side_effect = Exception('Database error')
        mock_preview_service_class.return_value = mock_preview_service
        
        # Make request
        response = client.post(
            '/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request),
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Internal server error' in data['error']
    
    @patch('tenant_admin_routes.cognito_required')
    @patch('tenant_admin_routes.get_current_tenant')
    @patch('tenant_admin_routes.get_user_tenants')
    @patch('tenant_admin_routes.is_tenant_admin')
    def test_preview_missing_request_body(
        self,
        mock_is_tenant_admin,
        mock_get_user_tenants,
        mock_get_current_tenant,
        mock_cognito_required,
        client,
        mock_auth_headers
    ):
        """Test error when request body is missing"""
        # Setup mocks
        mock_cognito_required.return_value = lambda f: f
        mock_get_current_tenant.return_value = 'GoodwinSolutions'
        mock_get_user_tenants.return_value = ['GoodwinSolutions']
        mock_is_tenant_admin.return_value = True
        
        # Make request without body
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=mock_auth_headers,
            content_type='application/json'
        )
        
        # Assertions
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Request body required' in data['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
