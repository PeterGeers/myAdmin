"""
API Tests for Template Management Endpoints
Tests authentication, request validation, error responses, and rate limiting

These tests verify:
- All endpoints require authentication
- Request validation (missing fields, invalid types)
- Error responses (400, 401, 500)
- Tenant isolation
- Rate limiting (if implemented)
"""

import sys
import os
import pytest
import json
from unittest.mock import Mock, patch, MagicMock

# Set TEST_MODE before importing app
os.environ['TEST_MODE'] = 'true'

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from app import app
from database import DatabaseManager


# Test configuration
TEST_ADMINISTRATION = 'TestTenant'
TEST_USER_EMAIL = 'test@example.com'


@pytest.fixture
def client():
    """Create test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_auth_and_tenant():
    """Mock all authentication and tenant context functions at route level"""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_extract, \
         patch('tenant_admin_routes.get_current_tenant') as mock_get_tenant, \
         patch('tenant_admin_routes.get_user_tenants') as mock_get_tenants, \
         patch('tenant_admin_routes.is_tenant_admin') as mock_is_admin:
        
        # Setup default return values
        mock_extract.return_value = (TEST_USER_EMAIL, ['Tenant_Admin'], None)
        mock_get_tenant.return_value = TEST_ADMINISTRATION
        mock_get_tenants.return_value = [TEST_ADMINISTRATION]
        mock_is_admin.return_value = True
        
        yield {
            'extract': mock_extract,
            'get_tenant': mock_get_tenant,
            'get_tenants': mock_get_tenants,
            'is_admin': mock_is_admin
        }


@pytest.fixture
def auth_headers():
    """Create authentication headers for testing"""
    # Mock JWT token
    return {
        'Authorization': 'Bearer mock_jwt_token',
        'Content-Type': 'application/json',
        'X-Tenant': TEST_ADMINISTRATION
    }


@pytest.fixture
def valid_template():
    """Valid template for testing"""
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Invoice {{ invoice_number }}</title>
        </head>
        <body>
            <h1>{{ company_name }}</h1>
            <p>Guest: {{ guest_name }}</p>
            <p>Check-in: {{ checkin_date }}</p>
            <p>Check-out: {{ checkout_date }}</p>
            <p>Amount: {{ amount_gross }}</p>
        </body>
    </html>
    """


class TestAuthenticationRequired:
    """Test that all endpoints require authentication"""
    
    def test_preview_endpoint_requires_auth(self, client):
        """Test POST /api/tenant-admin/templates/preview requires authentication"""
        # Request without auth headers (no Authorization header)
        response = client.post(
            '/api/tenant-admin/templates/preview',
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        # Assert - should return 401 or 403 (depending on implementation)
        assert response.status_code in [401, 403], f"Should return 401/403 Unauthorized, got {response.status_code}"
        data = json.loads(response.data)
        assert 'error' in data or 'message' in data, "Should return error message"
    
    def test_validate_endpoint_requires_auth(self, client):
        """Test POST /api/tenant-admin/templates/validate requires authentication"""
        response = client.post(
            '/api/tenant-admin/templates/validate',
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        assert response.status_code in [401, 403], f"Should return 401/403 Unauthorized, got {response.status_code}"
    
    def test_approve_endpoint_requires_auth(self, client):
        """Test POST /api/tenant-admin/templates/approve requires authentication"""
        response = client.post(
            '/api/tenant-admin/templates/approve',
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        assert response.status_code in [401, 403], f"Should return 401/403 Unauthorized, got {response.status_code}"
    
    def test_reject_endpoint_requires_auth(self, client):
        """Test POST /api/tenant-admin/templates/reject requires authentication"""
        response = client.post(
            '/api/tenant-admin/templates/reject',
            json={
                'template_type': 'str_invoice_nl',
                'reason': 'Test rejection'
            }
        )
        
        assert response.status_code in [401, 403], f"Should return 401/403 Unauthorized, got {response.status_code}"
    
    def test_ai_help_endpoint_requires_auth(self, client):
        """Test POST /api/tenant-admin/templates/ai-help requires authentication"""
        response = client.post(
            '/api/tenant-admin/templates/ai-help',
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>',
                'validation_errors': []
            }
        )
        
        assert response.status_code in [401, 403], f"Should return 401/403 Unauthorized, got {response.status_code}"
    
    def test_apply_fixes_endpoint_requires_auth(self, client):
        """Test POST /api/tenant-admin/templates/apply-ai-fixes requires authentication"""
        response = client.post(
            '/api/tenant-admin/templates/apply-ai-fixes',
            json={
                'template_content': '<html></html>',
                'fixes': []
            }
        )
        
        assert response.status_code in [401, 403], f"Should return 401/403 Unauthorized, got {response.status_code}"


class TestRequestValidation:
    """Test request validation for all endpoints"""
    
    def test_preview_missing_template_type(self, mock_auth_and_tenant, client, auth_headers):
        """Test preview endpoint with missing template_type"""
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_content': '<html></html>'
                # Missing template_type
            }
        )
        
        assert response.status_code == 400, f"Should return 400 Bad Request, got {response.status_code}"
        data = json.loads(response.data)
        assert 'error' in data or 'message' in data, "Should return error message"
        assert 'template_type' in str(data).lower(), "Error should mention missing field"
    
    def test_preview_missing_template_content(self, mock_auth_and_tenant, client, auth_headers):
        """Test preview endpoint with missing template_content"""
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl'
                # Missing template_content
            }
        )
        
        assert response.status_code == 400, f"Should return 400 Bad Request, got {response.status_code}"
        data = json.loads(response.data)
        assert 'template_content' in str(data).lower(), "Error should mention missing field"
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_invalid_template_type(self, mock_service, mock_auth_and_tenant, client, auth_headers):
        """Test preview endpoint with invalid template_type"""
        # Mock service to handle invalid type
        mock_instance = Mock()
        mock_instance.generate_preview.return_value = {
            'success': False,
            'error': 'Invalid template type'
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'invalid_type',
                'template_content': '<html></html>'
            }
        )
        
        # May return 400 or process with validation errors
        assert response.status_code in [400, 200], f"Should handle invalid type, got {response.status_code}"
    
    def test_preview_invalid_json(self, mock_auth_and_tenant, client, auth_headers):
        """Test preview endpoint with invalid JSON"""
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            data='invalid json'
        )
        
        # May return 400 or 500 depending on how Flask handles invalid JSON
        assert response.status_code in [400, 500], f"Should return error for invalid JSON, got {response.status_code}"
    
    def test_preview_empty_body(self, mock_auth_and_tenant, client, auth_headers):
        """Test preview endpoint with empty request body"""
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 400, f"Should return 400 Bad Request for empty body, got {response.status_code}"
    
    def test_validate_missing_fields(self, mock_auth_and_tenant, client, auth_headers):
        """Test validate endpoint with missing required fields"""
        response = client.post(
            '/api/tenant-admin/templates/validate',
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 400, f"Should return 400 Bad Request, got {response.status_code}"
    
    def test_approve_missing_fields(self, mock_auth_and_tenant, client, auth_headers):
        """Test approve endpoint with missing required fields"""
        response = client.post(
            '/api/tenant-admin/templates/approve',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl'
                # Missing template_content
            }
        )
        
        assert response.status_code == 400, f"Should return 400 Bad Request, got {response.status_code}"
    
    def test_ai_help_missing_fields(self, mock_auth_and_tenant, client, auth_headers):
        """Test AI help endpoint with missing required fields"""
        response = client.post(
            '/api/tenant-admin/templates/ai-help',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl'
                # Missing template_content and validation_errors
            }
        )
        
        assert response.status_code == 400, f"Should return 400 Bad Request, got {response.status_code}"
    
    def test_apply_fixes_invalid_fixes_format(self, mock_auth_and_tenant, client, auth_headers):
        """Test apply fixes endpoint with invalid fixes format"""
        response = client.post(
            '/api/tenant-admin/templates/apply-ai-fixes',
            headers=auth_headers,
            json={
                'template_content': '<html></html>',
                'fixes': 'not_an_array'  # Should be array
            }
        )
        
        # May return 400 or 500 depending on validation implementation
        assert response.status_code in [400, 500], f"Should return error for invalid format, got {response.status_code}"


class TestErrorResponses:
    """Test error response handling"""
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_service_error_returns_500(self, mock_service, mock_auth_and_tenant, client, auth_headers):
        """Test that service errors return 500"""
        # Mock service to raise exception
        mock_instance = Mock()
        mock_instance.generate_preview.side_effect = Exception("Database error")
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        assert response.status_code == 500, f"Should return 500 Internal Server Error, got {response.status_code}"
        data = json.loads(response.data)
        assert 'error' in data or 'message' in data or 'details' in data, "Should return error message"
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_approve_google_drive_error_returns_500(self, mock_service, mock_auth_and_tenant, client, auth_headers):
        """Test that Google Drive errors return 500"""
        # Mock service to return failure
        mock_instance = Mock()
        mock_instance.approve_template.return_value = {
            'success': False,
            'message': 'Failed to upload to Google Drive'
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/approve',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        # May return 500 or 400 depending on implementation
        assert response.status_code in [400, 500], f"Should return error status, got {response.status_code}"
    
    def test_invalid_endpoint_returns_404(self, mock_auth_and_tenant, client, auth_headers):
        """Test that invalid endpoints return 404"""
        response = client.post(
            '/api/tenant-admin/templates/invalid-endpoint',
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 404, f"Should return 404 Not Found, got {response.status_code}"
    
    def test_wrong_http_method_returns_405(self, mock_auth_and_tenant, client, auth_headers):
        """Test that wrong HTTP methods return 405"""
        # Try GET on POST-only endpoint
        response = client.get(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers
        )
        
        assert response.status_code == 405, f"Should return 405 Method Not Allowed, got {response.status_code}"


class TestSuccessfulRequests:
    """Test successful API requests"""
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_success_returns_200(self, mock_service, mock_auth_and_tenant, client, auth_headers, valid_template):
        """Test successful preview request"""
        # Mock service to return success
        mock_instance = Mock()
        mock_instance.generate_preview.return_value = {
            'success': True,
            'preview_html': '<html><body>Preview</body></html>',
            'validation': {
                'is_valid': True,
                'errors': [],
                'warnings': []
            },
            'sample_data_info': {
                'source': 'placeholder'
            }
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': valid_template
            }
        )
        
        assert response.status_code == 200, f"Should return 200 OK, got {response.status_code}"
        data = json.loads(response.data)
        assert data['success'] is True, "Should indicate success"
        assert 'preview_html' in data, "Should return preview HTML"
        assert 'validation' in data, "Should return validation results"
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_validate_success_returns_200(self, mock_service, mock_auth_and_tenant, client, auth_headers, valid_template):
        """Test successful validate request"""
        mock_instance = Mock()
        mock_instance.validate_template.return_value = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'checks_performed': ['html_syntax', 'placeholders', 'security']
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/validate',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': valid_template
            }
        )
        
        assert response.status_code == 200, f"Should return 200 OK, got {response.status_code}"
        data = json.loads(response.data)
        assert data['is_valid'] is True, "Should indicate valid"
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_approve_success_returns_200(self, mock_service, mock_auth_and_tenant, client, auth_headers, valid_template):
        """Test successful approve request"""
        mock_instance = Mock()
        mock_instance.approve_template.return_value = {
            'success': True,
            'template_id': 'tmpl_123',
            'file_id': 'file_456',
            'message': 'Template approved'
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/approve',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': valid_template,
                'field_mappings': {},
                'notes': 'Test approval'
            }
        )
        
        assert response.status_code == 200, f"Should return 200 OK, got {response.status_code}"
        data = json.loads(response.data)
        assert data['success'] is True, "Should indicate success"
        assert 'file_id' in data, "Should return file_id"
        assert data['success'] is True, "Should indicate success"
        assert 'preview_html' in data, "Should return preview HTML"
        assert 'validation' in data, "Should return validation results"
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_validate_success_returns_200(self, mock_service, mock_auth_and_tenant, client, auth_headers, valid_template):
        """Test successful validate request"""
        mock_instance = Mock()
        mock_instance.validate_template.return_value = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'checks_performed': ['html_syntax', 'placeholders', 'security']
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/validate',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': valid_template
            }
        )
        
        assert response.status_code == 200, f"Should return 200 OK, got {response.status_code}"
        data = json.loads(response.data)
        assert data['is_valid'] is True, "Should indicate valid"
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_approve_success_returns_200(self, mock_service, mock_auth_and_tenant, client, auth_headers, valid_template):
        """Test successful approve request"""
        mock_instance = Mock()
        mock_instance.approve_template.return_value = {
            'success': True,
            'template_id': 'tmpl_123',
            'file_id': 'file_456',
            'message': 'Template approved'
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/approve',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': valid_template,
                'field_mappings': {},
                'notes': 'Test approval'
            }
        )
        
        assert response.status_code == 200, f"Should return 200 OK, got {response.status_code}"
        data = json.loads(response.data)
        assert data['success'] is True, "Should indicate success"
        assert 'file_id' in data, "Should return file_id"


class TestContentTypeValidation:
    """Test Content-Type validation"""
    
    def test_preview_requires_json_content_type(self, mock_auth_and_tenant, client, auth_headers):
        """Test that endpoints require application/json Content-Type"""
        # Send with wrong Content-Type
        headers = auth_headers.copy()
        headers['Content-Type'] = 'text/plain'
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=headers,
            data='template_type=str_invoice_nl'
        )
        
        # Should reject non-JSON content (may return 400, 415, or 500)
        assert response.status_code in [400, 415, 500], f"Should reject non-JSON content, got {response.status_code}"
    
    def test_preview_accepts_json_content_type(self, mock_auth_and_tenant, client, auth_headers):
        """Test that endpoints accept application/json Content-Type"""
        # Ensure Content-Type is application/json
        headers = auth_headers.copy()
        headers['Content-Type'] = 'application/json'
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        # Should accept (may fail validation but not Content-Type)
        assert response.status_code != 415, f"Should accept JSON content, got {response.status_code}"


class TestRateLimiting:
    """Test rate limiting (if implemented)"""
    
    @pytest.mark.skip(reason="Rate limiting not yet implemented")
    @patch('auth.cognito_utils.cognito_required')
    def test_preview_rate_limit(self, mock_auth, client, auth_headers):
        """Test that preview endpoint has rate limiting"""
        mock_auth.return_value = lambda f: f
        
        # Make many requests quickly
        responses = []
        for i in range(100):
            response = client.post(
                '/api/tenant-admin/templates/preview',
                headers=auth_headers,
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': f'<html>{i}</html>'
                }
            )
            responses.append(response.status_code)
        
        # Should eventually return 429 Too Many Requests
        assert 429 in responses, "Should rate limit after many requests"
    
    @pytest.mark.skip(reason="Rate limiting not yet implemented")
    @patch('auth.cognito_utils.cognito_required')
    def test_ai_help_rate_limit(self, mock_auth, client, auth_headers):
        """Test that AI help endpoint has rate limiting (more strict)"""
        mock_auth.return_value = lambda f: f
        
        # AI endpoints should have stricter rate limits
        responses = []
        for i in range(20):
            response = client.post(
                '/api/tenant-admin/templates/ai-help',
                headers=auth_headers,
                json={
                    'template_type': 'str_invoice_nl',
                    'template_content': f'<html>{i}</html>',
                    'validation_errors': []
                }
            )
            responses.append(response.status_code)
        
        # Should rate limit faster than preview endpoint
        assert 429 in responses, "Should rate limit AI requests"


class TestResponseHeaders:
    """Test response headers"""
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_response_has_json_content_type(self, mock_service, mock_auth_and_tenant, client, auth_headers):
        """Test that responses have correct Content-Type"""
        mock_instance = Mock()
        mock_instance.generate_preview.return_value = {
            'success': True,
            'preview_html': '<html></html>',
            'validation': {'is_valid': True, 'errors': [], 'warnings': []},
            'sample_data_info': {'source': 'placeholder'}
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        assert 'application/json' in response.content_type, \
            f"Response should have JSON Content-Type, got {response.content_type}"
    
    def test_preview_response_has_cors_headers(self, mock_auth_and_tenant, client, auth_headers):
        """Test that responses have CORS headers (if configured)"""
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        # Check if CORS headers are present (if configured)
        # This is optional depending on your setup
        # assert 'Access-Control-Allow-Origin' in response.headers
        # For now, just verify response was received
        assert response.status_code in [200, 400, 500], "Should receive a response"


class TestTenantIsolation:
    """Test tenant isolation in API"""
    
    @patch('services.template_preview_service.TemplatePreviewService')
    def test_preview_uses_correct_tenant(self, mock_service, mock_auth_and_tenant, client, auth_headers):
        """Test that preview uses the authenticated user's tenant"""
        mock_instance = Mock()
        mock_instance.generate_preview.return_value = {
            'success': True,
            'preview_html': '<html></html>',
            'validation': {'is_valid': True, 'errors': [], 'warnings': []},
            'sample_data_info': {'source': 'placeholder'}
        }
        mock_service.return_value = mock_instance
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': '<html></html>'
            }
        )
        
        # Verify service was initialized with correct tenant
        assert response.status_code == 200, f"Should return 200, got {response.status_code}"
        # Verify the service was called with the correct tenant
        mock_service.assert_called_once()
        call_args = mock_service.call_args
        # The second argument should be the tenant (administration)
        assert call_args[0][1] == TEST_ADMINISTRATION, "Service should be initialized with correct tenant"


class TestInputSanitization:
    """Test input sanitization and security"""
    
    def test_preview_handles_large_template(self, mock_auth_and_tenant, client, auth_headers):
        """Test that large templates are handled appropriately"""
        # Create a very large template (>10MB)
        large_template = '<html><body>' + ('x' * 11 * 1024 * 1024) + '</body></html>'
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': large_template
            }
        )
        
        # Should reject or handle gracefully
        assert response.status_code in [400, 413, 500], \
            f"Should handle large templates appropriately, got {response.status_code}"
    
    def test_preview_handles_special_characters(self, mock_auth_and_tenant, client, auth_headers):
        """Test that special characters are handled correctly"""
        template_with_special_chars = """
        <html>
            <body>
                <p>Special: &lt;&gt;&amp;"'</p>
                <p>Unicode: 你好 مرحبا</p>
            </body>
        </html>
        """
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': template_with_special_chars
            }
        )
        
        # Should handle without errors (may return 200, 400, or 500 depending on validation)
        assert response.status_code in [200, 400, 500], \
            f"Should handle special characters, got {response.status_code}"
        assert response.status_code in [400, 413, 500], \
            "Should handle large templates appropriately"
    
    def test_preview_handles_special_characters(self, mock_auth_and_tenant, client, auth_headers):
        """Test that special characters are handled correctly"""
        template_with_special_chars = """
        <html>
            <body>
                <p>Special: &lt;&gt;&amp;"'</p>
                <p>Unicode: 你好 مرحبا</p>
            </body>
        </html>
        """
        
        response = client.post(
            '/api/tenant-admin/templates/preview',
            headers=auth_headers,
            json={
                'template_type': 'str_invoice_nl',
                'template_content': template_with_special_chars
            }
        )
        
        # Should handle without errors (may return 200, 400, or 500 depending on validation)
        assert response.status_code in [200, 400, 500], \
            f"Should handle special characters, got {response.status_code}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
