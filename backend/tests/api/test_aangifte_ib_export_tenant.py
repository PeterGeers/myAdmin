"""
Integration tests for aangifte-ib-export endpoint with tenant filtering

Tests the tenant filtering implementation for:
- /api/reports/aangifte-ib-export
"""

import pytest
import json
import base64
import inspect
from flask import Flask


class TestAangifteIBExportTenantFiltering:
    """Test tenant filtering for aangifte-ib-export endpoint"""
    
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
    
    def test_aangifte_ib_export_endpoint_exists(self):
        """Test that the aangifte-ib-export endpoint exists in app.py"""
        # Import app to verify endpoint is registered
        from app import app
        
        # Check that the endpoint is registered
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/api/reports/aangifte-ib-export' in rules
    
    def test_aangifte_ib_export_has_tenant_decorator(self):
        """Test that aangifte-ib-export has @tenant_required decorator"""
        from app import aangifte_ib_export
        
        # Get the function signature
        sig = inspect.signature(aangifte_ib_export)
        params = list(sig.parameters.keys())
        
        # Should have tenant and user_tenants parameters (added by @tenant_required)
        assert 'tenant' in params, "Missing 'tenant' parameter - @tenant_required decorator may not be applied"
        assert 'user_tenants' in params, "Missing 'user_tenants' parameter - @tenant_required decorator may not be applied"
    
    def test_aangifte_ib_export_validates_administration(self):
        """Test that aangifte-ib-export validates administration against user_tenants"""
        # This is a code inspection test - verify the implementation
        from app import aangifte_ib_export
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_export)
        
        # Should validate administration against user_tenants
        assert 'user_tenants' in source, "Function should use user_tenants parameter"
        assert 'Access denied' in source or 'access denied' in source.lower(), "Function should validate access"
    
    def test_aangifte_ib_export_defaults_to_tenant(self):
        """Test that aangifte-ib-export defaults administration to current tenant"""
        from app import aangifte_ib_export
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_export)
        
        # Should default administration to tenant
        assert "administration = data.get('administration', tenant)" in source, \
            "Function should default administration to current tenant"
    
    def test_aangifte_ib_export_passes_user_tenants_to_cache(self):
        """Test that aangifte-ib-export passes user_tenants to generate_table_rows"""
        from app import aangifte_ib_export
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_export)
        
        # Should pass user_tenants to generate_table_rows (which internally passes to cache)
        assert 'generate_table_rows' in source, "Function should call generate_table_rows"
        assert 'user_tenants=user_tenants' in source, "Function should pass user_tenants to generate_table_rows"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
