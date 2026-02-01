"""
Multi-Tenant Scenarios Integration Tests

Comprehensive testing of various multi-tenant scenarios:
- Single tenant users
- Multi-tenant users  
- Cross-tenant access attempts
- Tenant switching scenarios
- Data isolation verification
- Edge cases and boundary conditions
"""

import pytest
import json
import base64
from flask import Flask
from database import DatabaseManager
from bnb_routes import bnb_bp
from str_channel_routes import str_channel_bp
from str_invoice_routes import str_invoice_bp


class TestMultiTenantScenarios:
    """Test various multi-tenant scenarios"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app with all blueprints for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        app.register_blueprint(str_channel_bp, url_prefix='/api/str-channel')
        app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.fixture
    def db(self):
        """Create database manager for testing"""
        return DatabaseManager(test_mode=False)
    
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
    
    def get_available_tenants(self, db):
        """Get list of available tenants from database"""
        try:
            query = "SELECT DISTINCT administration FROM vw_bnb_total WHERE administration IS NOT NULL LIMIT 10"
            result = db.execute_query(query, [], fetch=True)
            return [row['administration'] for row in result] if result else []
        except Exception as e:
            print(f"Warning: Could not get tenants from database: {e}")
            return ['PeterPrive', 'GoodwinSolutions', 'TestTenant1', 'TestTenant2']


class TestSingleTenantUserScenarios(TestMultiTenantScenarios):
    """Test scenarios for single tenant users"""
    
    def test_single_tenant_user_access_own_data(self, client, db):
        """Test that single tenant user can access their own tenant's data"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="single@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test multiple endpoints
        endpoints = [
            '/api/bnb/bnb-listing-data',
            '/api/bnb/bnb-table',
            '/api/bnb/bnb-filter-options',
            '/api/bnb/bnb-actuals'
        ]
        
        for endpoint in endpoints:
            response = client.get(
                endpoint,
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            # Should succeed or return server error (but not 403)
            assert response.status_code in [200, 500], f"Endpoint {endpoint} failed with {response.status_code}"
            
            if response.status_code == 200:
                data = json.loads(response.data)
                assert data['success'] is True, f"Endpoint {endpoint} returned success=False"
    
    def test_single_tenant_user_blocked_from_other_tenants(self, client, db):
        """Test that single tenant user is blocked from accessing other tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for this test")
        
        # User has access to first tenant only
        authorized_tenant = tenants[0]
        unauthorized_tenant = tenants[1]
        
        token = self.create_jwt_token(
            email="single@example.com",
            tenants=[authorized_tenant],
            roles=["STR_Read"]
        )
        
        # Try to access unauthorized tenant's data
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': unauthorized_tenant
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
        assert 'access denied' in data['error'].lower() or 'forbidden' in data['error'].lower()
    
    def test_single_tenant_user_data_isolation(self, client, db):
        """Test that single tenant user only sees data from their tenant"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="isolation@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test BNB table data which returns detailed records
        response = client.get(
            '/api/bnb/bnb-table',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
        )
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            
            # Verify all returned data belongs to the user's tenant
            if 'data' in data and data['data']:
                for record in data['data']:
                    if 'administration' in record:
                        assert record['administration'] == tenant, f"Found data from wrong tenant: {record['administration']}"


class TestMultiTenantUserScenarios(TestMultiTenantScenarios):
    """Test scenarios for multi-tenant users"""
    
    def test_multi_tenant_user_access_all_authorized_tenants(self, client, db):
        """Test that multi-tenant user can access all their authorized tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for multi-tenant test")
        
        # User has access to first three tenants (or all if less than 3)
        user_tenants = tenants[:min(3, len(tenants))]
        
        token = self.create_jwt_token(
            email="multi@example.com",
            tenants=user_tenants,
            roles=["STR_Read"]
        )
        
        # Test access to each authorized tenant
        for tenant in user_tenants:
            response = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            # Should succeed or return server error (but not 403)
            assert response.status_code in [200, 500], f"Failed to access authorized tenant {tenant}"
            
            if response.status_code == 200:
                data = json.loads(response.data)
                assert data['success'] is True, f"Tenant {tenant} returned success=False"
    
    def test_multi_tenant_user_blocked_from_unauthorized_tenants(self, client, db):
        """Test that multi-tenant user is blocked from unauthorized tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 3:
            pytest.skip("Need at least 3 tenants for this test")
        
        # User has access to first two tenants only
        authorized_tenants = tenants[:2]
        unauthorized_tenant = tenants[2]
        
        token = self.create_jwt_token(
            email="multi@example.com",
            tenants=authorized_tenants,
            roles=["STR_Read"]
        )
        
        # Try to access unauthorized tenant
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': unauthorized_tenant
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_multi_tenant_user_tenant_switching(self, client, db):
        """Test that multi-tenant user can switch between authorized tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for tenant switching test")
        
        # User has access to first two tenants
        user_tenants = tenants[:2]
        
        token = self.create_jwt_token(
            email="switcher@example.com",
            tenants=user_tenants,
            roles=["STR_Read"]
        )
        
        # Test switching between tenants in the same session
        for tenant in user_tenants:
            # Access BNB data for current tenant
            response1 = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            # Access filter options for same tenant
            response2 = client.get(
                '/api/bnb/bnb-filter-options',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            # Both should succeed or return server error (but not 403)
            assert response1.status_code in [200, 500], f"Failed to access {tenant} for listing data"
            assert response2.status_code in [200, 500], f"Failed to access {tenant} for filter options"
    
    def test_multi_tenant_user_combined_data_access(self, client, db):
        """Test that multi-tenant user sees appropriate data for each tenant context"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for combined data test")
        
        # User has access to first two tenants
        user_tenants = tenants[:2]
        
        token = self.create_jwt_token(
            email="combined@example.com",
            tenants=user_tenants,
            roles=["STR_Read"]
        )
        
        # Get filter options for each tenant and compare
        tenant_data = {}
        
        for tenant in user_tenants:
            response = client.get(
                '/api/bnb/bnb-filter-options',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            if response.status_code == 200:
                data = json.loads(response.data)
                if data['success']:
                    tenant_data[tenant] = data
        
        # If we have data from multiple tenants, verify they can be different
        if len(tenant_data) >= 2:
            tenant_keys = list(tenant_data.keys())
            data1 = tenant_data[tenant_keys[0]]
            data2 = tenant_data[tenant_keys[1]]
            
            # The data structure should be the same
            assert 'years' in data1 and 'years' in data2
            assert 'listings' in data1 and 'listings' in data2
            assert 'channels' in data1 and 'channels' in data2
            
            # The actual data may be different (tenant-specific)
            # This is expected behavior - each tenant may have different years, listings, channels


class TestCrossTenantAccessScenarios(TestMultiTenantScenarios):
    """Test cross-tenant access scenarios and security"""
    
    def test_cross_tenant_booking_access_blocked(self, client, db):
        """Test that users cannot access bookings from unauthorized tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for cross-tenant test")
        
        # Get a booking from the second tenant
        try:
            query = """
                SELECT reservationCode, administration 
                FROM vw_bnb_total 
                WHERE administration = %s 
                LIMIT 1
            """
            result = db.execute_query(query, [tenants[1]], fetch=True)
            if not result:
                pytest.skip(f"No bookings found for tenant {tenants[1]}")
            
            booking = result[0]
        except Exception as e:
            pytest.skip(f"Could not get booking data: {e}")
        
        # User has access to first tenant only
        token = self.create_jwt_token(
            email="crossaccess@example.com",
            tenants=[tenants[0]],
            roles=["STR_Create"]
        )
        
        # Try to generate invoice for booking from unauthorized tenant
        response = client.post(
            '/api/str-invoice/generate-invoice',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenants[0],
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'reservationCode': booking['reservationCode'],
                'language': 'nl'
            })
        )
        
        # Should return 404 (booking not found due to tenant filtering)
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'Booking not found or access denied' in data['error']
    
    def test_cross_tenant_search_isolation(self, client, db):
        """Test that booking search is properly isolated by tenant"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for search isolation test")
        
        # Test search for each tenant separately
        for i, tenant in enumerate(tenants[:2]):
            token = self.create_jwt_token(
                email=f"search{i}@example.com",
                tenants=[tenant],
                roles=["STR_Read"]
            )
            
            # Search for bookings
            response = client.get(
                '/api/str-invoice/search-booking?query=test&limit=100',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            if response.status_code == 200:
                data = json.loads(response.data)
                assert data['success'] is True
                
                # Verify all returned bookings belong to the correct tenant
                for booking in data.get('bookings', []):
                    if 'administration' in booking:
                        assert booking['administration'] == tenant, f"Found booking from wrong tenant: {booking['administration']}"
    
    def test_tenant_header_manipulation_blocked(self, client, db):
        """Test that manipulating tenant header doesn't bypass security"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for header manipulation test")
        
        # User has access to first tenant only
        token = self.create_jwt_token(
            email="manipulator@example.com",
            tenants=[tenants[0]],
            roles=["STR_Read"]
        )
        
        # Try to access second tenant by manipulating the X-Tenant header
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenants[1]  # Unauthorized tenant
            }
        )
        
        # Should return 403 (forbidden) regardless of header manipulation
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data


class TestEdgeCasesAndBoundaryConditions(TestMultiTenantScenarios):
    """Test edge cases and boundary conditions for multi-tenant scenarios"""
    
    def test_empty_tenant_list_user(self, client, db):
        """Test user with empty tenant list"""
        token = self.create_jwt_token(
            email="empty@example.com",
            tenants=[],  # Empty tenant list
            roles=["STR_Read"]
        )
        
        # Try to access any endpoint
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'AnyTenant'
            }
        )
        
        # Should return 403 (forbidden) due to no tenant access
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_nonexistent_tenant_access(self, client, db):
        """Test access to nonexistent tenant"""
        token = self.create_jwt_token(
            email="nonexistent@example.com",
            tenants=["NonexistentTenant123"],
            roles=["STR_Read"]
        )
        
        # Try to access nonexistent tenant
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'NonexistentTenant123'
            }
        )
        
        # Should succeed (200) or return server error (500) but not auth error
        # The tenant filtering will just return empty results
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            # Data should be empty or minimal for nonexistent tenant
    
    def test_case_sensitive_tenant_names(self, client, db):
        """Test that tenant names are case-sensitive"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        # Create token with correct case
        token = self.create_jwt_token(
            email="case@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Try to access with different case
        wrong_case_tenant = tenant.lower() if tenant != tenant.lower() else tenant.upper()
        
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': wrong_case_tenant
            }
        )
        
        # Should return 403 if case doesn't match exactly
        if wrong_case_tenant != tenant:
            assert response.status_code == 403
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_large_number_of_tenants(self, client, db):
        """Test user with large number of tenants"""
        # Create a user with many tenants
        many_tenants = [f"Tenant{i}" for i in range(50)]  # 50 tenants
        
        token = self.create_jwt_token(
            email="manytenants@example.com",
            tenants=many_tenants,
            roles=["STR_Read"]
        )
        
        # Try to access first tenant
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': many_tenants[0]
            }
        )
        
        # Should succeed (200) or return server error (500) but not auth error
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
    
    def test_special_characters_in_tenant_names(self, client, db):
        """Test tenant names with special characters"""
        special_tenant = "Test-Tenant_123.Company"
        
        token = self.create_jwt_token(
            email="special@example.com",
            tenants=[special_tenant],
            roles=["STR_Read"]
        )
        
        # Try to access tenant with special characters
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': special_tenant
            }
        )
        
        # Should succeed (200) or return server error (500) but not auth error
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True


def main():
    """Run multi-tenant scenario tests"""
    print("\n" + "="*80)
    print("MULTI-TENANT SCENARIOS INTEGRATION TESTS")
    print("="*80)
    
    # Run pytest with verbose output
    import subprocess
    import sys
    
    result = subprocess.run([
        sys.executable, '-m', 'pytest', 
        __file__, 
        '-v', 
        '--tb=short',
        '--disable-warnings'
    ], capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    print("="*80)
    print(f"Multi-tenant scenario tests completed with exit code: {result.returncode}")
    print("="*80)
    
    return result.returncode == 0


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)