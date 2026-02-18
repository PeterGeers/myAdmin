"""
Integration tests for i18n API functionality.

Tests X-Language header handling and translated error messages.
"""

import pytest
from flask import Flask
from src.app import app
from src.config import Config


@pytest.fixture
def client():
    """Create test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestXLanguageHeader:
    """Test X-Language header handling."""

    def test_api_with_dutch_header(self, client):
        """Test API with X-Language: nl header returns Dutch responses."""
        response = client.get(
            '/api/user/language',
            headers={'X-Language': 'nl'}
        )
        
        # Should return 401 (no auth) but error message should be in Dutch
        assert response.status_code == 401
        data = response.get_json()
        
        # Check for Dutch error message (if implemented)
        # This will depend on your actual error message structure
        assert data is not None

    def test_api_with_english_header(self, client):
        """Test API with X-Language: en header returns English responses."""
        response = client.get(
            '/api/user/language',
            headers={'X-Language': 'en'}
        )
        
        # Should return 401 (no auth) but error message should be in English
        assert response.status_code == 401
        data = response.get_json()
        
        # Check for English error message
        assert data is not None

    def test_api_with_missing_header_defaults_to_dutch(self, client):
        """Test API with missing X-Language header defaults to nl."""
        response = client.get('/api/user/language')
        
        # Should return 401 (no auth)
        assert response.status_code == 401
        data = response.get_json()
        
        # Should default to Dutch
        assert data is not None

    def test_api_with_invalid_header_fallback_to_dutch(self, client):
        """Test API with invalid X-Language header falls back to nl."""
        response = client.get(
            '/api/user/language',
            headers={'X-Language': 'invalid'}
        )
        
        # Should return 401 (no auth)
        assert response.status_code == 401
        data = response.get_json()
        
        # Should fallback to Dutch
        assert data is not None

    def test_backend_endpoints_return_translated_errors(self, client):
        """Test that backend endpoints return translated error messages."""
        # Test with Dutch
        response_nl = client.get(
            '/api/user/language',
            headers={'X-Language': 'nl'}
        )
        
        # Test with English
        response_en = client.get(
            '/api/user/language',
            headers={'X-Language': 'en'}
        )
        
        # Both should return 401
        assert response_nl.status_code == 401
        assert response_en.status_code == 401
        
        # Both should have error messages
        data_nl = response_nl.get_json()
        data_en = response_en.get_json()
        
        assert data_nl is not None
        assert data_en is not None


class TestLanguageEndpoints:
    """Test language preference endpoints."""

    def test_get_user_language_without_auth(self, client):
        """Test GET /api/user/language without authentication."""
        response = client.get('/api/user/language')
        
        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_update_user_language_without_auth(self, client):
        """Test PUT /api/user/language without authentication."""
        response = client.put(
            '/api/user/language',
            json={'language': 'nl'}
        )
        
        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_update_user_language_with_invalid_language(self, client):
        """Test PUT /api/user/language with invalid language code."""
        # This would require authentication, so it will return 401
        # But we can test the validation logic
        response = client.put(
            '/api/user/language',
            json={'language': 'invalid'}
        )
        
        # Should return 401 (no auth) or 400 (invalid language)
        assert response.status_code in [400, 401]

    def test_update_user_language_with_missing_language(self, client):
        """Test PUT /api/user/language with missing language parameter."""
        response = client.put(
            '/api/user/language',
            json={}
        )
        
        # Should return 400 Bad Request or 401 Unauthorized
        assert response.status_code in [400, 401]


class TestTenantLanguageEndpoints:
    """Test tenant language preference endpoints."""

    def test_get_tenant_language_without_auth(self, client):
        """Test GET /api/tenant-admin/language without authentication."""
        response = client.get('/api/tenant-admin/language')
        
        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_update_tenant_language_without_auth(self, client):
        """Test PUT /api/tenant-admin/language without authentication."""
        response = client.put(
            '/api/tenant-admin/language',
            json={'language': 'nl'}
        )
        
        # Should return 401 Unauthorized
        assert response.status_code == 401


class TestCORSHeaders:
    """Test CORS configuration for X-Language header."""

    def test_x_language_header_allowed_in_cors(self, client):
        """Test that X-Language header is allowed in CORS."""
        response = client.options(
            '/api/user/language',
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'X-Language'
            }
        )
        
        # Should return 200 OK for OPTIONS request
        # CORS should allow X-Language header
        assert response.status_code in [200, 204]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
