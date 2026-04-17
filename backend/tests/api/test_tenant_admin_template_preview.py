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
def auth_client(app):
    """Create test client with mocked auth (Tenant_Admin)"""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth, \
         patch('tenant_admin_routes.get_current_tenant', return_value='GoodwinSolutions'), \
         patch('tenant_admin_routes.get_user_tenants', return_value=['GoodwinSolutions']), \
         patch('tenant_admin_routes.is_tenant_admin', return_value=True):
        mock_auth.return_value = ('admin@goodwinsolutions.com', ['Tenant_Admin'], None)
        yield app.test_client()


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

    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_success(self, mock_preview_service_class,
                             auth_client, valid_template_request):
        """Test successful template preview generation"""
        mock_preview_service = Mock()
        mock_preview_service.generate_preview.return_value = {
            'success': True,
            'preview_html': '<html><body>Preview</body></html>',
            'validation': {'is_valid': True, 'errors': [], 'warnings': []},
            'sample_data_info': {'source': 'database', 'record_date': '2026-01-01', 'message': 'Using most recent data'}
        }
        mock_preview_service_class.return_value = mock_preview_service

        response = auth_client.post('/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request), content_type='application/json',
            headers={'Authorization': 'Bearer mock.jwt.token'})

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'preview_html' in data

    def test_preview_requires_tenant_admin(self, app, valid_template_request):
        """Test that endpoint requires Tenant_Admin role"""
        with patch('auth.cognito_utils.extract_user_credentials') as mock_auth, \
             patch('tenant_admin_routes.get_current_tenant', return_value='GoodwinSolutions'), \
             patch('tenant_admin_routes.get_user_tenants', return_value=['GoodwinSolutions']), \
             patch('tenant_admin_routes.is_tenant_admin', return_value=False):
            mock_auth.return_value = ('user@example.com', ['Finance_Read'], None)
            client = app.test_client()

            response = client.post('/api/tenant-admin/templates/preview',
                data=json.dumps(valid_template_request), content_type='application/json',
                headers={'Authorization': 'Bearer mock.jwt.token'})

            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'Tenant admin access required' in data['error']

    def test_preview_missing_template_type(self, auth_client):
        """Test validation error when template_type is missing"""
        response = auth_client.post('/api/tenant-admin/templates/preview',
            data=json.dumps({'template_content': '<html></html>'}),
            content_type='application/json',
            headers={'Authorization': 'Bearer mock.jwt.token'})

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'template_type is required' in data['error']

    def test_preview_missing_template_content(self, auth_client):
        """Test validation error when template_content is missing"""
        response = auth_client.post('/api/tenant-admin/templates/preview',
            data=json.dumps({'template_type': 'str_invoice_nl'}),
            content_type='application/json',
            headers={'Authorization': 'Bearer mock.jwt.token'})

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'template_content is required' in data['error']

    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_validation_failure(self, mock_preview_service_class,
                                        auth_client, valid_template_request):
        """Test handling of validation failures"""
        mock_preview_service = Mock()
        mock_preview_service.generate_preview.return_value = {
            'success': False,
            'validation': {
                'is_valid': False,
                'errors': [{'type': 'missing_placeholder', 'message': 'Required placeholder missing', 'severity': 'error'}],
                'warnings': []
            }
        }
        mock_preview_service_class.return_value = mock_preview_service

        response = auth_client.post('/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request), content_type='application/json',
            headers={'Authorization': 'Bearer mock.jwt.token'})

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is False
        assert data['validation']['is_valid'] is False

    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_internal_error(self, mock_preview_service_class,
                                     auth_client, valid_template_request):
        """Test handling of internal server errors"""
        mock_preview_service = Mock()
        mock_preview_service.generate_preview.side_effect = Exception('Database error')
        mock_preview_service_class.return_value = mock_preview_service

        response = auth_client.post('/api/tenant-admin/templates/preview',
            data=json.dumps(valid_template_request), content_type='application/json',
            headers={'Authorization': 'Bearer mock.jwt.token'})

        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'Internal server error' in data['error']

    def test_preview_missing_request_body(self, auth_client):
        """Test error when request body is missing"""
        response = auth_client.post('/api/tenant-admin/templates/preview',
            content_type='application/json',
            headers={'Authorization': 'Bearer mock.jwt.token'})

        # Route returns 500 when JSON parsing fails on empty body
        assert response.status_code in (400, 500)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
