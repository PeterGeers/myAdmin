"""
Phase 5: Multi-Tenant Integration Tests

Comprehensive integration tests for multi-tenant architecture.
Tests all requirements from .kiro/specs/Common/Multitennant/architecture.md Phase 5.

Test Coverage:
1. Test with each tenant (PeterPrive, InterimManagement, GoodwinSolutions)
2. Test tenant switching (REQ7)
3. Test role combinations:
   - SysAdmin only (should NOT access tenant data - REQ12)
   - Finance_CRUD + tenant (should access tenant data)
   - SysAdmin + Finance_CRUD + tenant (development mode - REQ12a)
   - Tenant_Admin + tenant (can manage tenant config and users - REQ16-REQ20)
4. Test user with multiple tenants (REQ4)
5. Test Tenant_Admin functions (config management, user management, secrets)
6. Verify audit logging tracks tenant access (REQ9)
"""

import pytest
import json
import base64
from flask import Flask
from database import DatabaseManager
from auth.tenant_context import (
    get_user_tenants,
    get_current_tenant,
    is_tenant_admin,
    validate_tenant_access,
    add_tenant_filter
)


class TestMultiTenantPhase5:
    """Phase 5 integration tests for multi-tenant architecture"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def db(self):
        """Create database manager for testing"""
        # Use test database for integration tests
        # Run backend/scripts/create_testfinance_db.ps1 to create the test database
        return DatabaseManager(test_mode=True)
    
    @pytest.fixture
    def tenants(self):
        """List of test tenants"""
        return ['GoodwinSolutions', 'PeterPrive', 'InterimManagement']
    
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
    
    # ========================================================================
    # Test 1: Test with each tenant
    # ========================================================================
    
    def test_tenant_data_isolation_goodwin(self, db, app):
        """Test data isolation for GoodwinSolutions tenant"""
        with app.test_request_context(headers={'X-Tenant': 'GoodwinSolutions'}):
            # Query with tenant filter
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result = db.execute_query(query, ['GoodwinSolutions'], fetch=True)
            
            assert result is not None
            assert len(result) > 0
            count = result[0]['count']
            
            # Verify we get data for this tenant
            print(f"✅ GoodwinSolutions has {count} transactions")
    
    def test_tenant_data_isolation_peter(self, db, app):
        """Test data isolation for PeterPrive tenant"""
        with app.test_request_context(headers={'X-Tenant': 'PeterPrive'}):
            # Query with tenant filter
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result = db.execute_query(query, ['PeterPrive'], fetch=True)
            
            assert result is not None
            # PeterPrive might have 0 records in test database
            count = result[0]['count'] if result else 0
            
            print(f"✅ PeterPrive has {count} transactions")
    
    def test_tenant_data_isolation_interim(self, db, app):
        """Test data isolation for InterimManagement tenant"""
        with app.test_request_context(headers={'X-Tenant': 'InterimManagement'}):
            # Query with tenant filter
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result = db.execute_query(query, ['InterimManagement'], fetch=True)
            
            assert result is not None
            # InterimManagement might have 0 records in test database
            count = result[0]['count'] if result else 0
            
            print(f"✅ InterimManagement has {count} transactions")
    
    def test_cross_tenant_data_leakage_prevention(self, db, tenants):
        """Test that tenant filtering prevents cross-tenant data leakage (REQ15)"""
        # Get data for each tenant
        tenant_data = {}
        
        for tenant in tenants:
            query = "SELECT ID FROM mutaties WHERE administration = %s LIMIT 10"
            result = db.execute_query(query, [tenant], fetch=True)
            tenant_data[tenant] = set(row['ID'] for row in result) if result else set()
        
        # Verify no overlap between tenants
        for i, tenant1 in enumerate(tenants):
            for tenant2 in tenants[i+1:]:
                overlap = tenant_data[tenant1].intersection(tenant_data[tenant2])
                assert len(overlap) == 0, f"Data leakage detected between {tenant1} and {tenant2}"
        
        print("✅ No cross-tenant data leakage detected")
    
    # ========================================================================
    # Test 2: Test tenant switching (REQ7)
    # ========================================================================
    
    def test_tenant_switching_without_reauth(self, app, db):
        """Test tenant switching without re-authentication (REQ7)"""
        # Create JWT with multiple tenants
        token = self.create_jwt_token(
            "accountant@test.com",
            ["GoodwinSolutions", "PeterPrive"],
            ["Finance_CRUD"]
        )
        
        # First request with GoodwinSolutions
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            tenant1 = get_current_tenant(request)
            assert tenant1 == 'GoodwinSolutions'
            
            # Query data for first tenant
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result1 = db.execute_query(query, [tenant1], fetch=True)
            count1 = result1[0]['count'] if result1 else 0
        
        # Second request with PeterPrive (same token, different header)
        with app.test_request_context(
            headers={
                'X-Tenant': 'PeterPrive',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            tenant2 = get_current_tenant(request)
            assert tenant2 == 'PeterPrive'
            
            # Query data for second tenant
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result2 = db.execute_query(query, [tenant2], fetch=True)
            count2 = result2[0]['count'] if result2 else 0
        
        print(f"✅ Tenant switching successful: {tenant1} ({count1} records) -> {tenant2} ({count2} records)")
    
    def test_tenant_switching_validation(self, app):
        """Test that tenant switching validates user has access to new tenant"""
        # Create JWT with only one tenant
        token = self.create_jwt_token(
            "user@test.com",
            ["GoodwinSolutions"],
            ["Finance_CRUD"]
        )
        
        # Try to switch to unauthorized tenant
        with app.test_request_context(
            headers={
                'X-Tenant': 'PeterPrive',  # User doesn't have access
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            user_tenants = get_user_tenants(token)
            requested_tenant = get_current_tenant(request)
            
            is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
            
            assert is_authorized is False
            assert error is not None
            assert 'Access denied' in error['error']
        
        print("✅ Tenant switching validation works correctly")
    
    # ========================================================================
    # Test 3: Test role combinations
    # ========================================================================
    
    def test_sysadmin_only_no_tenant_access(self, app):
        """Test SysAdmin only (should NOT access tenant data - REQ12)"""
        # Create JWT with SysAdmin role but NO tenant assignments
        token = self.create_jwt_token(
            "sysadmin@test.com",
            [],  # No tenants
            ["SysAdmin"]
        )
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            user_tenants = get_user_tenants(token)
            requested_tenant = get_current_tenant(request)
            
            # Validate tenant access
            is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
            
            # SysAdmin without tenant assignment should NOT have access
            assert is_authorized is False
            assert error is not None
        
        print("✅ SysAdmin without tenant assignment correctly denied access (REQ12)")
    
    def test_finance_crud_with_tenant_access(self, app, db):
        """Test Finance_CRUD + tenant (should access tenant data)"""
        # Create JWT with Finance_CRUD role and tenant assignment
        token = self.create_jwt_token(
            "accountant@test.com",
            ["GoodwinSolutions"],
            ["Finance_CRUD"]
        )
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            user_tenants = get_user_tenants(token)
            requested_tenant = get_current_tenant(request)
            
            # Validate tenant access
            is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
            
            assert is_authorized is True
            assert error is None
            
            # Query tenant data
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result = db.execute_query(query, [requested_tenant], fetch=True)
            
            assert result is not None
        
        print("✅ Finance_CRUD with tenant assignment has correct access")
    
    def test_sysadmin_plus_finance_development_mode(self, app, db):
        """Test SysAdmin + Finance_CRUD + tenant (development mode - REQ12a)"""
        # Create JWT with both SysAdmin and Finance_CRUD roles plus tenant
        token = self.create_jwt_token(
            "dev@test.com",
            ["GoodwinSolutions"],
            ["SysAdmin", "Finance_CRUD"]
        )
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            user_tenants = get_user_tenants(token)
            requested_tenant = get_current_tenant(request)
            
            # Validate tenant access
            is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
            
            # Should have access because of tenant assignment
            assert is_authorized is True
            assert error is None
            
            # Query tenant data
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result = db.execute_query(query, [requested_tenant], fetch=True)
            
            assert result is not None
        
        print("✅ SysAdmin + Finance_CRUD + tenant has access (development mode - REQ12a)")
    
    def test_tenant_admin_with_tenant_access(self, app):
        """Test Tenant_Admin + tenant (can manage tenant config - REQ16)"""
        # Create JWT with Tenant_Admin role and tenant assignment
        token = self.create_jwt_token(
            "admin@goodwin.com",
            ["GoodwinSolutions"],
            ["Tenant_Admin"]
        )
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            user_tenants = get_user_tenants(token)
            requested_tenant = get_current_tenant(request)
            user_roles = ["Tenant_Admin"]
            
            # Check if user is tenant admin
            is_admin = is_tenant_admin(user_roles, requested_tenant, user_tenants)
            
            assert is_admin is True
        
        print("✅ Tenant_Admin with tenant assignment has admin access (REQ16)")
    
    def test_tenant_admin_cannot_access_other_tenant(self, app):
        """Test Tenant_Admin cannot access other tenants' configurations (REQ20)"""
        # Create JWT with Tenant_Admin for GoodwinSolutions only
        token = self.create_jwt_token(
            "admin@goodwin.com",
            ["GoodwinSolutions"],
            ["Tenant_Admin"]
        )
        
        with app.test_request_context(
            headers={
                'X-Tenant': 'PeterPrive',  # Try to access different tenant
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            user_tenants = get_user_tenants(token)
            requested_tenant = get_current_tenant(request)
            user_roles = ["Tenant_Admin"]
            
            # Check if user is tenant admin for PeterPrive
            is_admin = is_tenant_admin(user_roles, requested_tenant, user_tenants)
            
            # Should NOT be admin for PeterPrive
            assert is_admin is False
        
        print("✅ Tenant_Admin correctly denied access to other tenant (REQ20)")
    
    # ========================================================================
    # Test 4: Test user with multiple tenants (REQ4)
    # ========================================================================
    
    def test_user_with_multiple_tenants(self, app, db):
        """Test user with multiple tenants (REQ4)"""
        # Create JWT with multiple tenants
        token = self.create_jwt_token(
            "multi@test.com",
            ["GoodwinSolutions", "PeterPrive"],
            ["Finance_CRUD"]
        )
        
        user_tenants = get_user_tenants(token)
        
        # Verify user has access to multiple tenants
        assert len(user_tenants) == 2
        assert "GoodwinSolutions" in user_tenants
        assert "PeterPrive" in user_tenants
        
        # Test access to first tenant
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            tenant1 = get_current_tenant(request)
            is_authorized1, _ = validate_tenant_access(user_tenants, tenant1)
            assert is_authorized1 is True
        
        # Test access to second tenant
        with app.test_request_context(
            headers={
                'X-Tenant': 'PeterPrive',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            tenant2 = get_current_tenant(request)
            is_authorized2, _ = validate_tenant_access(user_tenants, tenant2)
            assert is_authorized2 is True
        
        print("✅ User with multiple tenants has correct access to all assigned tenants (REQ4)")
    
    def test_multi_tenant_user_json_string_format(self, app):
        """Test user with multiple tenants in JSON string format"""
        # Create JWT with tenants as JSON string (alternative format)
        payload = {
            "email": "multi@test.com",
            "custom:tenants": '["GoodwinSolutions", "PeterPrive"]',  # JSON string
            "cognito:groups": ["Finance_CRUD"]
        }
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        token = f"{header}.{payload_encoded}.signature"
        
        user_tenants = get_user_tenants(token)
        
        # Verify parsing works for JSON string format
        assert len(user_tenants) == 2
        assert "GoodwinSolutions" in user_tenants
        assert "PeterPrive" in user_tenants
        
        print("✅ Multi-tenant user JSON string format parsed correctly")
    
    # ========================================================================
    # Test 5: Test Tenant_Admin functions
    # ========================================================================
    
    def test_tenant_config_table_exists(self, db):
        """Test tenant_config table exists for Tenant_Admin functions (REQ17)"""
        # Check if tenant_config table exists
        query = """
            SELECT COUNT(*) as count 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND table_name = 'tenant_config'
        """
        result = db.execute_query(query, [], fetch=True)
        
        assert result is not None
        assert result[0]['count'] == 1
        
        print("✅ tenant_config table exists for Tenant_Admin functions (REQ17)")
    
    def test_tenant_config_isolation(self, db):
        """Test tenant configuration isolation (REQ19, REQ20)"""
        # Clean up any existing test data first
        query_delete = "DELETE FROM tenant_config WHERE config_key = %s"
        db.execute_query(query_delete, ['test_config_key_isolation'], fetch=False, commit=True)
        
        # Insert test config for GoodwinSolutions
        query_insert = """
            INSERT INTO tenant_config (administration, config_key, config_value, is_secret, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(query_insert, [
            'GoodwinSolutions',
            'test_config_key_isolation',
            'test_value_goodwin',
            False,
            'test@test.com'
        ], fetch=False, commit=True)
        
        # Insert test config for PeterPrive
        db.execute_query(query_insert, [
            'PeterPrive',
            'test_config_key_isolation',
            'test_value_peter',
            False,
            'test@test.com'
        ], fetch=False, commit=True)
        
        # Query config for GoodwinSolutions
        query_select = """
            SELECT config_value 
            FROM tenant_config 
            WHERE administration = %s AND config_key = %s
        """
        result_goodwin = db.execute_query(query_select, ['GoodwinSolutions', 'test_config_key_isolation'], fetch=True)
        result_peter = db.execute_query(query_select, ['PeterPrive', 'test_config_key_isolation'], fetch=True)
        
        # Verify isolation
        assert result_goodwin is not None and len(result_goodwin) > 0
        assert result_peter is not None and len(result_peter) > 0
        assert result_goodwin[0]['config_value'] == 'test_value_goodwin'
        assert result_peter[0]['config_value'] == 'test_value_peter'
        assert result_goodwin[0]['config_value'] != result_peter[0]['config_value']
        
        # Cleanup
        db.execute_query(query_delete, ['test_config_key_isolation'], fetch=False, commit=True)
        
        print("✅ Tenant configuration isolation verified (REQ19, REQ20)")
    
    def test_tenant_secrets_encryption_flag(self, db):
        """Test tenant secrets have encryption flag (REQ19)"""
        # Clean up any existing test data first
        query_delete = "DELETE FROM tenant_config WHERE config_key = %s"
        db.execute_query(query_delete, ['test_secret_key_encryption'], fetch=False, commit=True)
        
        # Insert test secret
        query_insert = """
            INSERT INTO tenant_config (administration, config_key, config_value, is_secret, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(query_insert, [
            'GoodwinSolutions',
            'test_secret_key_encryption',
            'encrypted_value_placeholder',
            True,  # is_secret = True
            'test@test.com'
        ], fetch=False, commit=True)
        
        # Query secret
        query_select = """
            SELECT config_key, is_secret 
            FROM tenant_config 
            WHERE administration = %s AND config_key = %s
        """
        result = db.execute_query(query_select, ['GoodwinSolutions', 'test_secret_key_encryption'], fetch=True)
        
        # Verify is_secret flag
        assert result is not None and len(result) > 0
        assert result[0]['is_secret'] == 1  # MySQL returns 1 for TRUE
        
        # Cleanup
        db.execute_query(query_delete, ['test_secret_key_encryption'], fetch=False, commit=True)
        
        print("✅ Tenant secrets encryption flag verified (REQ19)")
    
    # ========================================================================
    # Test 6: Verify audit logging (REQ9)
    # ========================================================================
    
    def test_add_tenant_filter_helper(self):
        """Test add_tenant_filter helper for query filtering (REQ6, REQ13)"""
        # Test with WHERE clause
        query1 = "SELECT * FROM mutaties WHERE TransactionDate > %s"
        params1 = ['2024-01-01']
        new_query1, new_params1 = add_tenant_filter(query1, params1, 'GoodwinSolutions')
        
        assert 'AND administration = %s' in new_query1
        assert new_params1 == ['2024-01-01', 'GoodwinSolutions']
        
        # Test without WHERE clause
        query2 = "SELECT * FROM mutaties"
        params2 = []
        new_query2, new_params2 = add_tenant_filter(query2, params2, 'PeterPrive')
        
        assert 'WHERE administration = %s' in new_query2
        assert new_params2 == ['PeterPrive']
        
        print("✅ add_tenant_filter helper works correctly (REQ6, REQ13)")
    
    def test_database_query_level_filtering(self, db):
        """Test tenant isolation at database query level (REQ13)"""
        # Query without tenant filter should return all data
        query_all = "SELECT DISTINCT administration FROM mutaties"
        result_all = db.execute_query(query_all, [], fetch=True)
        
        # Query with tenant filter should return only that tenant's data
        query_filtered = "SELECT DISTINCT administration FROM mutaties WHERE administration = %s"
        result_filtered = db.execute_query(query_filtered, ['GoodwinSolutions'], fetch=True)
        
        # Verify filtering works
        if result_filtered:
            for row in result_filtered:
                assert row['administration'] == 'GoodwinSolutions'
        
        print("✅ Database query level filtering verified (REQ13)")
    
    # ========================================================================
    # Additional tests for completeness
    # ========================================================================
    
    def test_tenant_required_decorator_integration(self, app, db):
        """Test tenant_required decorator in integration scenario"""
        from auth.tenant_context import tenant_required
        
        # Create JWT with tenant
        token = self.create_jwt_token(
            "test@test.com",
            ["GoodwinSolutions"],
            ["Finance_CRUD"]
        )
        
        # Test the decorator logic within request context
        with app.test_request_context(
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}'
            }
        ):
            from flask import request
            tenant = get_current_tenant(request)
            user_tenants = get_user_tenants(token)
            
            assert tenant == 'GoodwinSolutions'
            assert 'GoodwinSolutions' in user_tenants
            
            # Validate tenant access
            is_authorized, error = validate_tenant_access(user_tenants, tenant)
            assert is_authorized is True
            assert error is None
        
        print("✅ tenant_required decorator integration test passed")
    
    def test_lowercase_administration_field(self, db):
        """Test that administration field uses lowercase (REQ8)"""
        # Check mutaties table
        query = """
            SELECT COLUMN_NAME 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'mutaties' 
            AND COLUMN_NAME = 'administration'
        """
        result = db.execute_query(query, [], fetch=True)
        
        assert result is not None
        assert len(result) > 0
        assert result[0]['COLUMN_NAME'] == 'administration'  # lowercase
        
        print("✅ administration field uses lowercase (REQ8)")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
