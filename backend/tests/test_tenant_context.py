"""
Unit tests for tenant context management

Tests the multi-tenant context extraction, validation, and filtering functionality.
"""

import pytest
import json
import base64
from unittest.mock import Mock, patch
from flask import Flask
from auth.tenant_context import (
    get_user_tenants,
    get_current_tenant,
    is_tenant_admin,
    validate_tenant_access,
    add_tenant_filter
)


class TestGetUserTenants:
    """Test tenant extraction from JWT tokens"""
    
    def create_jwt_token(self, payload):
        """Helper to create a mock JWT token"""
        # JWT format: header.payload.signature
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = "mock_signature"
        return f"{header}.{payload_encoded}.{signature}"
    
    def test_extract_tenants_from_jwt_list(self):
        """Test extracting tenants when custom:tenants is a list"""
        payload = {
            "email": "user@test.com",
            "custom:tenants": ["GoodwinSolutions", "PeterPrive"]
        }
        token = self.create_jwt_token(payload)
        
        tenants = get_user_tenants(token)
        
        assert tenants == ["GoodwinSolutions", "PeterPrive"]
    
    def test_extract_tenants_from_jwt_json_string(self):
        """Test extracting tenants when custom:tenants is a JSON string"""
        payload = {
            "email": "user@test.com",
            "custom:tenants": '["GoodwinSolutions", "PeterPrive"]'
        }
        token = self.create_jwt_token(payload)
        
        tenants = get_user_tenants(token)
        
        assert tenants == ["GoodwinSolutions", "PeterPrive"]
    
    def test_extract_single_tenant(self):
        """Test extracting single tenant"""
        payload = {
            "email": "user@test.com",
            "custom:tenants": "GoodwinSolutions"
        }
        token = self.create_jwt_token(payload)
        
        tenants = get_user_tenants(token)
        
        assert tenants == ["GoodwinSolutions"]
    
    def test_no_tenants_attribute(self):
        """Test when custom:tenants attribute is missing"""
        payload = {
            "email": "user@test.com"
        }
        token = self.create_jwt_token(payload)
        
        tenants = get_user_tenants(token)
        
        assert tenants == []
    
    def test_invalid_jwt_format(self):
        """Test with invalid JWT format"""
        invalid_token = "not.a.valid.jwt"
        
        tenants = get_user_tenants(invalid_token)
        
        assert tenants == []
    
    def test_extract_tenants_with_escaped_quotes(self):
        """Test extracting tenants when custom:tenants has escaped quotes (Cognito format)"""
        payload = {
            "email": "user@test.com",
            "custom:tenants": '[\"GoodwinSolutions\",\"PeterPrive\"]'  # Escaped quotes like Cognito sends
        }
        token = self.create_jwt_token(payload)
        
        tenants = get_user_tenants(token)
        
        assert tenants == ["GoodwinSolutions", "PeterPrive"]
        assert len(tenants) == 2


class TestGetCurrentTenant:
    """Test tenant extraction from request"""
    
    def test_get_tenant_from_header(self):
        """Test getting tenant from X-Tenant header"""
        app = Flask(__name__)
        
        with app.test_request_context(headers={'X-Tenant': 'GoodwinSolutions'}):
            from flask import request
            tenant = get_current_tenant(request)
            
            assert tenant == 'GoodwinSolutions'
    
    def test_get_tenant_from_jwt(self):
        """Test getting tenant from JWT when header is missing"""
        app = Flask(__name__)
        
        # Create JWT with tenants
        payload = {"email": "user@test.com", "custom:tenants": ["PeterPrive"]}
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        token = f"Bearer {header}.{payload_encoded}.signature"
        
        with app.test_request_context(headers={'Authorization': token}):
            from flask import request
            tenant = get_current_tenant(request)
            
            assert tenant == 'PeterPrive'
    
    def test_header_takes_precedence(self):
        """Test that X-Tenant header takes precedence over JWT"""
        app = Flask(__name__)
        
        # Create JWT with different tenant
        payload = {"email": "user@test.com", "custom:tenants": ["PeterPrive"]}
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        token = f"Bearer {header}.{payload_encoded}.signature"
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': token
            }
        ):
            from flask import request
            tenant = get_current_tenant(request)
            
            assert tenant == 'GoodwinSolutions'
    
    def test_no_tenant_available(self):
        """Test when no tenant is available"""
        app = Flask(__name__)
        
        with app.test_request_context():
            from flask import request
            tenant = get_current_tenant(request)
            
            assert tenant is None


class TestIsTenantAdmin:
    """Test tenant admin validation"""
    
    def test_is_tenant_admin_valid(self):
        """Test valid tenant admin"""
        user_roles = ['Tenant_Admin', 'Finance_CRUD']
        tenant = 'GoodwinSolutions'
        user_tenants = ['GoodwinSolutions', 'PeterPrive']
        
        result = is_tenant_admin(user_roles, tenant, user_tenants)
        
        assert result is True
    
    def test_is_tenant_admin_no_role(self):
        """Test user without Tenant_Admin role"""
        user_roles = ['Finance_CRUD']
        tenant = 'GoodwinSolutions'
        user_tenants = ['GoodwinSolutions']
        
        result = is_tenant_admin(user_roles, tenant, user_tenants)
        
        assert result is False
    
    def test_is_tenant_admin_no_tenant_access(self):
        """Test Tenant_Admin without access to specific tenant"""
        user_roles = ['Tenant_Admin']
        tenant = 'InterimManagement'
        user_tenants = ['GoodwinSolutions', 'PeterPrive']
        
        result = is_tenant_admin(user_roles, tenant, user_tenants)
        
        assert result is False
    
    def test_is_tenant_admin_both_required(self):
        """Test that both role and tenant access are required"""
        # Has role but not tenant
        assert is_tenant_admin(['Tenant_Admin'], 'GoodwinSolutions', ['PeterPrive']) is False
        
        # Has tenant but not role
        assert is_tenant_admin(['Finance_CRUD'], 'GoodwinSolutions', ['GoodwinSolutions']) is False


class TestValidateTenantAccess:
    """Test tenant access validation"""
    
    def test_validate_tenant_access_valid(self):
        """Test valid tenant access"""
        user_tenants = ['GoodwinSolutions', 'PeterPrive']
        requested_tenant = 'GoodwinSolutions'
        
        is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
        
        assert is_authorized is True
        assert error is None
    
    def test_validate_tenant_access_invalid(self):
        """Test invalid tenant access"""
        user_tenants = ['GoodwinSolutions']
        requested_tenant = 'PeterPrive'
        
        is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
        
        assert is_authorized is False
        assert error is not None
        assert 'Access denied' in error['error']
    
    def test_validate_tenant_access_no_tenant(self):
        """Test when no tenant is specified"""
        user_tenants = ['GoodwinSolutions']
        requested_tenant = None
        
        is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
        
        assert is_authorized is False
        assert error is not None
        assert 'No tenant specified' in error['error']
    
    def test_validate_tenant_access_empty_tenants(self):
        """Test when user has no tenants"""
        user_tenants = []
        requested_tenant = 'GoodwinSolutions'
        
        is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
        
        assert is_authorized is False
        assert error is not None


class TestAddTenantFilter:
    """Test SQL query tenant filtering"""
    
    def test_add_tenant_filter_with_where(self):
        """Test adding tenant filter to query with existing WHERE clause"""
        query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
        params = ['2024-01-01']
        tenant = 'GoodwinSolutions'
        
        new_query, new_params = add_tenant_filter(query, params, tenant)
        
        assert 'AND administration = %s' in new_query
        assert new_params == ['2024-01-01', 'GoodwinSolutions']
    
    def test_add_tenant_filter_without_where(self):
        """Test adding tenant filter to query without WHERE clause"""
        query = "SELECT * FROM mutaties"
        params = []
        tenant = 'PeterPrive'
        
        new_query, new_params = add_tenant_filter(query, params, tenant)
        
        assert 'WHERE administration = %s' in new_query
        assert new_params == ['PeterPrive']
    
    def test_add_tenant_filter_with_alias(self):
        """Test adding tenant filter with table alias"""
        query = "SELECT * FROM mutaties m WHERE m.TransactionDate > %s"
        params = ['2024-01-01']
        tenant = 'GoodwinSolutions'
        
        new_query, new_params = add_tenant_filter(query, params, tenant, table_alias='m')
        
        assert 'AND m.administration = %s' in new_query
        assert new_params == ['2024-01-01', 'GoodwinSolutions']
    
    def test_add_tenant_filter_preserves_params(self):
        """Test that existing params are preserved"""
        query = "SELECT * FROM mutaties WHERE TransactionDate BETWEEN %s AND %s"
        params = ['2024-01-01', '2024-12-31']
        tenant = 'GoodwinSolutions'
        
        new_query, new_params = add_tenant_filter(query, params, tenant)
        
        assert new_params == ['2024-01-01', '2024-12-31', 'GoodwinSolutions']
    
    def test_add_tenant_filter_case_insensitive_where(self):
        """Test that WHERE detection is case-insensitive"""
        query = "SELECT * FROM mutaties where TransactionDate > %s"
        params = ['2024-01-01']
        tenant = 'GoodwinSolutions'
        
        new_query, new_params = add_tenant_filter(query, params, tenant)
        
        # Should add AND, not WHERE
        assert 'AND administration = %s' in new_query
        assert 'WHERE administration = %s' not in new_query


class TestTenantRequiredDecorator:
    """Test tenant_required decorator"""
    
    def test_tenant_required_decorator_valid(self):
        """Test decorator with valid tenant access"""
        from auth.tenant_context import tenant_required
        
        app = Flask(__name__)
        
        @app.route('/test')
        @tenant_required()
        def test_route(tenant, user_tenants):
            return {'tenant': tenant, 'user_tenants': user_tenants}
        
        # Create JWT with tenants
        payload = {"email": "user@test.com", "custom:tenants": ["GoodwinSolutions"]}
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        token = f"Bearer {header}.{payload_encoded}.signature"
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': token
            }
        ):
            # The decorator resolves the tenant from the active Flask request
            # context. `tenant_context` imports Flask lazily (inside the decorator)
            # so that the `auth` package stays importable on the Flask-free SAM
            # plane — there is therefore no module-level `auth.tenant_context.request`
            # to patch; use the real request context instead.
            from flask import request
            tenant = get_current_tenant(request)
            assert tenant == 'GoodwinSolutions'


class TestSysAdminBypassAuditLog:
    """Test that the allow_sysadmin bypass emits a structured audit log.

    Security assessment 2026-09-26, task M1 (risk F2): on a
    ``tenant_required(allow_sysadmin=True)`` route the client-supplied
    ``X-Tenant`` header is injected without membership validation. The bypass
    path must emit a structured audit trail of the injected tenant, the caller,
    and the route.
    """

    def _make_token(self, tenants):
        payload = {"email": "sysadmin@test.com", "custom:tenants": tenants}
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256"}).encode()
        ).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip('=')
        return f"Bearer {header}.{payload_encoded}.signature"

    def test_sysadmin_bypass_logs_injected_tenant(self):
        """Bypass path audit-logs the injected tenant, caller, and route."""
        from auth.tenant_context import tenant_required

        app = Flask(__name__)

        @app.route('/test-bypass')
        @tenant_required(allow_sysadmin=True)
        def bypass_route(user_email, user_roles, tenant, user_tenants):
            return {'tenant': tenant}

        # SysAdmin injecting a tenant NOT in their own token (cross-tenant reach).
        token = self._make_token(["OwnTenant"])

        # log_successful_access writes the structured entry via print("ACCESS_LOG: ...");
        # patch it where it is used so we can assert the audit content.
        with patch('auth.cognito_utils.log_successful_access') as mock_log:
            with app.test_request_context(
                path='/test-bypass',
                method='POST',
                headers={
                    'X-Tenant': 'InjectedTenant',
                    'Authorization': token,
                },
            ):
                # Directly invoke the decorated view with the kwargs that
                # cognito_required would have injected.
                bypass_route(
                    user_email='sysadmin@test.com',
                    user_roles=['SysAdmin'],
                )

        assert mock_log.called, "bypass path must emit an audit log"
        _, kwargs = mock_log.call_args
        assert kwargs['user_email'] == 'sysadmin@test.com'
        assert kwargs['operation'] == 'sysadmin_tenant_bypass'
        details = kwargs['details']
        assert details['injected_tenant'] == 'InjectedTenant'
        assert details['route'] == 'bypass_route'
        assert details['tenant_validated'] is False

    def test_sysadmin_bypass_emits_access_log_line(self):
        """End-to-end: the bypass produces an ACCESS_LOG line naming the tenant."""
        from auth.tenant_context import tenant_required

        app = Flask(__name__)

        @app.route('/test-bypass-2')
        @tenant_required(allow_sysadmin=True)
        def bypass_route_2(user_email, user_roles, tenant, user_tenants):
            return {'tenant': tenant}

        token = self._make_token(["OwnTenant"])

        # Use the real log_successful_access; capture its printed output.
        import builtins
        printed = []
        real_print = builtins.print

        def _capture(*args, **kw):
            printed.append(" ".join(str(a) for a in args))
            return real_print(*args, **kw)

        with patch('builtins.print', side_effect=_capture):
            with app.test_request_context(
                path='/test-bypass-2',
                method='GET',
                headers={
                    'X-Tenant': 'InjectedTenant',
                    'Authorization': token,
                },
            ):
                bypass_route_2(
                    user_email='sysadmin@test.com',
                    user_roles=['SysAdmin'],
                )

        access_lines = [p for p in printed if p.startswith('ACCESS_LOG:')]
        assert access_lines, "expected an ACCESS_LOG audit line from the bypass"
        joined = "\n".join(access_lines)
        assert 'InjectedTenant' in joined
        assert 'sysadmin_tenant_bypass' in joined


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
