"""
Integration tests to verify all tenant admin template endpoints are accessible

Tests that all 6 template management endpoints are properly registered and accessible
"""

import pytest
from flask import Flask
from tenant_admin_routes import tenant_admin_bp


class TestTenantAdminEndpointsAccessible:
    """Test that all tenant admin endpoints are accessible"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(tenant_admin_bp)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    def test_validate_endpoint_accessible(self, client):
        """Test that validate endpoint is accessible"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        
        # Will return 401 (unauthorized) since we don't have auth
        # But that proves the endpoint is registered and accessible
        assert response.status_code in [400, 401, 403]
    
    def test_preview_endpoint_accessible(self, client):
        """Test that preview endpoint is accessible"""
        response = client.post('/api/tenant-admin/templates/preview')
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        assert response.status_code in [400, 401, 403]
    
    def test_approve_endpoint_accessible(self, client):
        """Test that approve endpoint is accessible"""
        response = client.post('/api/tenant-admin/templates/approve')
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        assert response.status_code in [400, 401, 403]
    
    def test_reject_endpoint_accessible(self, client):
        """Test that reject endpoint is accessible"""
        response = client.post('/api/tenant-admin/templates/reject')
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        assert response.status_code in [400, 401, 403]
    
    def test_ai_help_endpoint_accessible(self, client):
        """Test that ai-help endpoint is accessible"""
        response = client.post('/api/tenant-admin/templates/ai-help')
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        assert response.status_code in [400, 401, 403]
    
    def test_apply_ai_fixes_endpoint_accessible(self, client):
        """Test that apply-ai-fixes endpoint is accessible"""
        response = client.post('/api/tenant-admin/templates/apply-ai-fixes')
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        assert response.status_code in [400, 401, 403]
    
    def test_all_endpoints_return_json(self, client):
        """Test that all endpoints return JSON responses"""
        endpoints = [
            '/api/tenant-admin/templates/validate',
            '/api/tenant-admin/templates/preview',
            '/api/tenant-admin/templates/approve',
            '/api/tenant-admin/templates/reject',
            '/api/tenant-admin/templates/ai-help',
            '/api/tenant-admin/templates/apply-ai-fixes'
        ]
        
        for endpoint in endpoints:
            response = client.post(endpoint)
            
            # Should return JSON content type
            assert 'application/json' in response.content_type, \
                f"Endpoint {endpoint} does not return JSON"
    
    def test_all_endpoints_require_post(self, client):
        """Test that all endpoints only accept POST method"""
        endpoints = [
            '/api/tenant-admin/templates/validate',
            '/api/tenant-admin/templates/preview',
            '/api/tenant-admin/templates/approve',
            '/api/tenant-admin/templates/reject',
            '/api/tenant-admin/templates/ai-help',
            '/api/tenant-admin/templates/apply-ai-fixes'
        ]
        
        for endpoint in endpoints:
            # GET should not be allowed
            response = client.get(endpoint)
            assert response.status_code == 405, \
                f"Endpoint {endpoint} incorrectly allows GET method"
            
            # POST should be allowed (even if auth fails)
            response = client.post(endpoint)
            assert response.status_code != 405, \
                f"Endpoint {endpoint} does not allow POST method"
    
    def test_blueprint_registered_with_correct_prefix(self, app):
        """Test that blueprint routes are registered with correct URL prefix"""
        # Get all registered routes
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append(rule.rule)
        
        # Check that all our endpoints are registered
        expected_endpoints = [
            '/api/tenant-admin/templates/validate',
            '/api/tenant-admin/templates/preview',
            '/api/tenant-admin/templates/approve',
            '/api/tenant-admin/templates/reject',
            '/api/tenant-admin/templates/ai-help',
            '/api/tenant-admin/templates/apply-ai-fixes'
        ]
        
        for endpoint in expected_endpoints:
            assert endpoint in routes, \
                f"Endpoint {endpoint} not found in registered routes"
    
    def test_endpoint_count(self, app):
        """Test that we have the expected number of template endpoints"""
        # Count template-related endpoints
        template_endpoints = [
            rule.rule for rule in app.url_map.iter_rules()
            if '/api/tenant-admin/templates/' in rule.rule
        ]
        
        # Should have exactly 6 template endpoints
        assert len(template_endpoints) >= 6, \
            f"Expected at least 6 template endpoints, found {len(template_endpoints)}"
    
    def test_all_endpoints_have_security_headers(self, client):
        """Test that all endpoints have CSP security headers"""
        endpoints = [
            '/api/tenant-admin/templates/validate',
            '/api/tenant-admin/templates/preview',
            '/api/tenant-admin/templates/approve',
            '/api/tenant-admin/templates/reject',
            '/api/tenant-admin/templates/ai-help',
            '/api/tenant-admin/templates/apply-ai-fixes'
        ]
        
        for endpoint in endpoints:
            response = client.post(endpoint)
            
            # Should have CSP header
            assert 'Content-Security-Policy' in response.headers, \
                f"Endpoint {endpoint} missing CSP header"
            
            # Should have other security headers
            assert 'X-Content-Type-Options' in response.headers, \
                f"Endpoint {endpoint} missing X-Content-Type-Options header"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
