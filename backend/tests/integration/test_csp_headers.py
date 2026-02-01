"""
Integration tests for Content Security Policy (CSP) headers

Tests that CSP headers are properly applied to tenant admin endpoints
"""

import pytest
from flask import Flask
from tenant_admin_routes import tenant_admin_bp


class TestCSPHeaders:
    """Test Content Security Policy headers on tenant admin routes"""
    
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
    
    def test_csp_header_present(self, client):
        """Test that CSP header is present in responses"""
        # Make a request to any tenant admin endpoint
        # Note: This will fail auth, but we just want to check headers
        response = client.post('/api/tenant-admin/templates/validate')
        
        # Check that CSP header is present
        assert 'Content-Security-Policy' in response.headers
    
    def test_csp_blocks_scripts(self, client):
        """Test that CSP policy blocks scripts"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should contain script-src 'none'
        assert "script-src 'none'" in csp
    
    def test_csp_allows_inline_styles(self, client):
        """Test that CSP policy allows inline styles (needed for templates)"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should allow inline styles for template previews
        assert "style-src 'self' 'unsafe-inline'" in csp
    
    def test_csp_restricts_default_src(self, client):
        """Test that CSP restricts default source to self"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should restrict default source to same origin
        assert "default-src 'self'" in csp
    
    def test_csp_prevents_framing(self, client):
        """Test that CSP prevents clickjacking"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should prevent framing
        assert "frame-ancestors 'none'" in csp
    
    def test_additional_security_headers(self, client):
        """Test that additional security headers are present"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        # Check for additional security headers
        assert 'X-Content-Type-Options' in response.headers
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        
        assert 'X-Frame-Options' in response.headers
        assert response.headers['X-Frame-Options'] == 'DENY'
        
        assert 'X-XSS-Protection' in response.headers
        assert '1; mode=block' in response.headers['X-XSS-Protection']
        
        assert 'Referrer-Policy' in response.headers
        assert 'strict-origin-when-cross-origin' in response.headers['Referrer-Policy']
    
    def test_csp_on_all_endpoints(self, client):
        """Test that CSP is applied to all tenant admin endpoints"""
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
            
            # All should have CSP header
            assert 'Content-Security-Policy' in response.headers, \
                f"CSP header missing on {endpoint}"
            
            csp = response.headers['Content-Security-Policy']
            assert "script-src 'none'" in csp, \
                f"Script blocking missing on {endpoint}"
    
    def test_csp_policy_structure(self, client):
        """Test that CSP policy has all required directives"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Check for all required directives
        required_directives = [
            "default-src 'self'",
            "script-src 'none'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        
        for directive in required_directives:
            assert directive in csp, f"Missing CSP directive: {directive}"
    
    def test_csp_blocks_external_resources(self, client):
        """Test that CSP blocks external resources"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should not allow external resources
        assert "'unsafe-eval'" not in csp
        assert "https://*" not in csp
        assert "http://*" not in csp
    
    def test_csp_allows_data_uris_for_images(self, client):
        """Test that CSP allows data URIs for images (needed for inline images)"""
        response = client.post('/api/tenant-admin/templates/validate')
        
        csp = response.headers.get('Content-Security-Policy', '')
        
        # Should allow data URIs for images
        assert "img-src 'self' data:" in csp


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
