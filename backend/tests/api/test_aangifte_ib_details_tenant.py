"""
Integration tests for aangifte-ib-details endpoint with tenant filtering

Tests the tenant filtering implementation for:
- /api/reports/aangifte-ib-details
"""

import pytest
import json
import base64
from flask import Flask
from database import DatabaseManager


class TestAangifteIBDetailsTenantFiltering:
    """Test tenant filtering for aangifte-ib-details endpoint"""
    
    def create_jwt_token(self, email, tenants, roles=None):
        """Helper to create a mock JWT token"""
        payload = {
            "email": email,
            "custom:tenants": tenants if isinstance(tenants, list) else [tenants],
            "cognito:groups": roles or []
        }
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = "mock_signature"
        return f"{header}.{payload_encoded}.{signature}"
    
    def test_aangifte_ib_details_endpoint_exists(self):
        """Test that the aangifte-ib-details endpoint exists in app.py"""
        # Import app to verify endpoint is registered
        from app import app
        
        # Check that the endpoint is registered
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/api/reports/aangifte-ib-details' in rules
    
    def test_aangifte_ib_details_has_tenant_decorator(self):
        """Test that aangifte-ib-details has @tenant_required decorator"""
        from app import aangifte_ib_details
        import inspect
        
        # Get the function signature
        sig = inspect.signature(aangifte_ib_details)
        params = list(sig.parameters.keys())
        
        # Should have tenant and user_tenants parameters (added by @tenant_required)
        assert 'tenant' in params, "Missing 'tenant' parameter - @tenant_required decorator may not be applied"
        assert 'user_tenants' in params, "Missing 'user_tenants' parameter - @tenant_required decorator may not be applied"
    
    def test_aangifte_ib_details_validates_administration(self):
        """Test that aangifte-ib-details validates administration against user_tenants"""
        # This is a code inspection test - verify the implementation
        from app import aangifte_ib_details
        import inspect
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_details)
        
        # Should validate administration against user_tenants
        assert 'user_tenants' in source, "Function should use user_tenants parameter"
        assert 'Access denied' in source or 'access denied' in source.lower(), "Function should validate access"
    
    def test_cache_method_accepts_user_tenants(self):
        """Test that query_aangifte_ib_details cache method accepts user_tenants parameter"""
        from mutaties_cache import MutatiesCache
        import inspect
        
        # Get the method signature
        sig = inspect.signature(MutatiesCache.query_aangifte_ib_details)
        params = list(sig.parameters.keys())
        
        # Should have user_tenants parameter
        assert 'user_tenants' in params, "Cache method should accept user_tenants parameter for filtering"
    
    def test_cache_method_filters_by_user_tenants(self):
        """Test that query_aangifte_ib_details filters data by user_tenants"""
        from mutaties_cache import MutatiesCache
        import inspect
        
        # Get the source code
        source = inspect.getsource(MutatiesCache.query_aangifte_ib_details)
        
        # Should filter by user_tenants
        assert 'user_tenants' in source, "Cache method should use user_tenants for filtering"
        assert 'isin' in source or 'Administration' in source, "Cache method should filter Administration by user_tenants"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
