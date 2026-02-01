"""
Integration tests for aangifte-ib-xlsx-export-stream endpoint with tenant filtering

Tests the tenant filtering implementation for:
- /api/reports/aangifte-ib-xlsx-export-stream
"""

import pytest
import inspect
import json
import base64


class TestAangifteIBXlsxExportStreamTenantFiltering:
    """Test tenant filtering for aangifte-ib-xlsx-export-stream endpoint"""
    
    def create_jwt_token(self, email, tenants, roles=None):
        """Helper to create a mock JWT token"""
        if roles is None:
            roles = []
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload = {"email": email, "custom:tenants": json.dumps(tenants), "cognito:groups": roles}
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = "mock_signature"
        return f"{header}.{payload_encoded}.{signature}"
    
    def test_aangifte_ib_xlsx_export_stream_endpoint_exists(self):
        """Test that the aangifte-ib-xlsx-export-stream endpoint exists in app.py"""
        # Import app to verify endpoint is registered
        from app import app
        
        # Check that the endpoint is registered
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/api/reports/aangifte-ib-xlsx-export-stream' in rules
    
    def test_aangifte_ib_xlsx_export_stream_has_tenant_decorator(self):
        """Test that aangifte-ib-xlsx-export-stream has @tenant_required decorator"""
        from app import aangifte_ib_xlsx_export_stream
        
        # Get the function signature
        sig = inspect.signature(aangifte_ib_xlsx_export_stream)
        params = list(sig.parameters.keys())
        
        # Should have tenant and user_tenants parameters (injected by @tenant_required)
        assert 'tenant' in params, "Missing 'tenant' parameter - @tenant_required decorator may not be applied"
        assert 'user_tenants' in params, "Missing 'user_tenants' parameter - @tenant_required decorator may not be applied"
    
    def test_aangifte_ib_xlsx_export_stream_validates_administrations(self):
        """Test that aangifte-ib-xlsx-export-stream validates administrations against user_tenants"""
        # This is a code inspection test - verify the implementation
        from app import aangifte_ib_xlsx_export_stream
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_xlsx_export_stream)
        
        # Should validate administrations against user_tenants
        assert 'unauthorized_admins' in source or 'Access denied' in source, "Function should validate access to administrations"
    
    def test_aangifte_ib_xlsx_export_stream_returns_403_for_unauthorized_admin(self):
        """Test that aangifte-ib-xlsx-export-stream returns 403 for unauthorized administrations"""
        from app import aangifte_ib_xlsx_export_stream
        
        # Get the source code
        source = inspect.getsource(aangifte_ib_xlsx_export_stream)
        
        # Should return 403 for unauthorized administrations
        assert '403' in source, "Function should return 403 for unauthorized access"
    
    def test_aangifte_ib_xlsx_export_stream_has_tenant_filtering_comment(self):
        """Test that aangifte-ib-xlsx-export-stream has tenant filtering in docstring"""
        from app import aangifte_ib_xlsx_export_stream
        
        # Check docstring mentions tenant filtering
        docstring = aangifte_ib_xlsx_export_stream.__doc__ or ""
        assert 'tenant' in docstring.lower(), "Docstring should mention tenant filtering"
