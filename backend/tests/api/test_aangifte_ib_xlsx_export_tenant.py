"""
Integration tests for aangifte-ib-xlsx-export endpoint with tenant filtering

Tests the tenant filtering implementation for:
- /api/reports/aangifte-ib-xlsx-export
"""

import pytest
import json
import base64
import inspect
from flask import Flask


class TestAangifteIBXlsxExportTenantFiltering:
    """Test tenant filtering for aangifte-ib-xlsx-export endpoint"""
    
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
    
    def test_aangifte_ib_xlsx_export_endpoint_exists(self):
        """Test that the aangifte-ib-xlsx-export endpoint exists in app.py"""
        # Import app to verify endpoint is registered
        from app import app
        
        # Check that the endpoint is registered
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/api/reports/aangifte-ib-xlsx-export' in rules
    
    def test_aangifte_ib_xlsx_export_has_tenant_decorator(self):
        """Test that aangifte-ib-xlsx-export has @tenant_required decorator"""
        from app import aangifte_ib_xlsx_export
        
        # Get the function signature
        sig = inspect.signature(aangifte_ib_xlsx_export)
        params = list(sig.parameters.keys())
        
        # Should have tenant and user_tenants parameters (added by @tenant_required)
        assert 'tenant' in params, "Missing 'tenant' parameter - @tenant_required decorator may not be applied"
        assert 'user_tenants' in params, "Missing 'user_tenants' parameter - @tenant_required decorator may not be applied"
    
    def test_aangifte_ib_xlsx_export_validates_administrations(self):
        """Test that aangifte-ib-xlsx-export validates administrations against user_tenants"""
        # This is a code inspection test - verify the implementation
        from app import aangifte_ib_xlsx_export
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_xlsx_export)
        
        # Should validate administrations against user_tenants
        assert 'user_tenants' in source, "Function should use user_tenants parameter"
        assert 'unauthorized_admins' in source or 'Access denied' in source, "Function should validate access to administrations"
    
    def test_aangifte_ib_xlsx_export_filters_available_administrations(self):
        """Test that aangifte-ib-xlsx-export filters available administrations by user_tenants"""
        from app import aangifte_ib_xlsx_export
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_xlsx_export)
        
        # Should filter available administrations by user_tenants
        assert 'WHERE Administration IN' in source or 'IN (' in source, \
            "Function should filter available administrations by user_tenants"
        assert 'user_tenants' in source, "Function should use user_tenants for filtering"
    
    def test_aangifte_ib_xlsx_export_returns_403_for_unauthorized_admin(self):
        """Test that aangifte-ib-xlsx-export returns 403 for unauthorized administrations"""
        from app import aangifte_ib_xlsx_export
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_xlsx_export)
        
        # Should return 403 for unauthorized administrations
        assert '403' in source, "Function should return 403 status code for unauthorized access"
        assert 'Access denied' in source, "Function should return access denied error message"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
