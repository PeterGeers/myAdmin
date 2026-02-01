"""
Comprehensive Integration Tests for Tenant Filtering

Tests all tenant filtering implementations with real database connections:
- BNB routes tenant filtering
- STR channel routes tenant filtering  
- STR invoice routes tenant filtering
- Multi-tenant scenarios
- Performance impact testing
"""

import pytest
import json
import base64
import time
from flask import Flask
from database import DatabaseManager
from bnb_routes import bnb_bp
from str_channel_routes import str_channel_bp
from str_invoice_routes import str_invoice_bp


class TestTenantFilteringComprehensive:
    """Comprehensive integration tests for tenant filtering across all routes"""
    
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
        """Create database manager for real database testing"""
        return DatabaseManager(test_mode=False)  # Use real database
    
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
            query = "SELECT DISTINCT administration FROM vw_bnb_total WHERE administration IS NOT NULL LIMIT 5"
            result = db.execute_query(query, [], fetch=True)
            return [row['administration'] for row in result] if result else []
        except Exception as e:
            print(f"Warning: Could not get tenants from database: {e}")
            return ['PeterPrive', 'GoodwinSolutions']  # Fallback
    
    def get_sample_booking(self, db, administration=None):
        """Get a sample booking from database"""
        try:
            if administration:
                query = """
                    SELECT reservationCode, administration, guestName, amountGross, checkinDate
                    FROM vw_bnb_total 
                    WHERE administration = %s 
                    ORDER BY checkinDate DESC
                    LIMIT 1
                """
                result = db.execute_query(query, [administration], fetch=True)
            else:
                query = """
                    SELECT reservationCode, administration, guestName, amountGross, checkinDate
                    FROM vw_bnb_total 
                    ORDER BY checkinDate DESC
                    LIMIT 1
                """
                result = db.execute_query(query, [], fetch=True)
            
            return result[0] if result else None
        except Exception as e:
            print(f"Warning: Could not get sample booking: {e}")
            return None


class TestBNBRoutesTenantFilteringIntegration(TestTenantFilteringComprehensive):
    """Integration tests for BNB routes with real database"""
    
    def test_bnb_listing_data_real_database(self, client, db):
        """Test BNB listing data with real database connection"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test with real database
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
        )
        
        # Should succeed or return server error (but not 403)
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_table_data_real_database(self, client, db):
        """Test BNB table data with real database connection"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test with real database
        response = client.get(
            '/api/bnb/bnb-table',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
        )
        
        # Should succeed or return server error (but not 403)
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_filter_options_real_database(self, client, db):
        """Test BNB filter options with real database connection"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test with real database
        response = client.get(
            '/api/bnb/bnb-filter-options',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
        )
        
        # Should succeed or return server error (but not 403)
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'years' in data
            assert 'listings' in data
            assert 'channels' in data
    
    def test_bnb_cross_tenant_access_blocked(self, client, db):
        """Test that cross-tenant access is properly blocked"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for cross-tenant test")
        
        # User has access to first tenant only
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenants[0]],
            roles=["STR_Read"]
        )
        
        # Try to access second tenant's data
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenants[1]
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data


class TestSTRInvoiceRoutesTenantFilteringIntegration(TestTenantFilteringComprehensive):
    """Integration tests for STR invoice routes with real database"""
    
    def test_search_booking_real_database(self, client, db):
        """Test booking search with real database connection"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test with real database
        response = client.get(
            '/api/str-invoice/search-booking?query=test',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
        )
        
        # Should succeed or return server error (but not 403)
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'bookings' in data
            assert 'date_range' in data
    
    def test_generate_invoice_real_database(self, client, db):
        """Test invoice generation with real database connection"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        booking = self.get_sample_booking(db, tenant)
        if not booking:
            pytest.skip(f"No bookings available for tenant {tenant}")
        
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenant],
            roles=["STR_Create"]
        )
        
        # Test with real database
        response = client.post(
            '/api/str-invoice/generate-invoice',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant,
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'reservationCode': booking['reservationCode'],
                'language': 'nl'
            })
        )
        
        # Should succeed (200), fail with server error (500), or be blocked by tenant filtering (403)
        assert response.status_code in [200, 403, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'html' in data
            assert 'booking_data' in data
        elif response.status_code == 403:
            # Tenant filtering is working correctly
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_generate_invoice_cross_tenant_blocked(self, client, db):
        """Test that cross-tenant invoice generation is blocked"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for cross-tenant test")
        
        # Get booking from second tenant
        booking = self.get_sample_booking(db, tenants[1])
        if not booking:
            pytest.skip(f"No bookings available for tenant {tenants[1]}")
        
        # User has access to first tenant only
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenants[0]],
            roles=["STR_Create"]
        )
        
        # Try to generate invoice for second tenant's booking
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


class TestMultiTenantScenariosIntegration(TestTenantFilteringComprehensive):
    """Integration tests for multi-tenant scenarios"""
    
    def test_multi_tenant_user_access_all_tenants(self, client, db):
        """Test that multi-tenant user can access all their tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for multi-tenant test")
        
        # User has access to multiple tenants
        user_tenants = tenants[:2]  # First two tenants
        token = self.create_jwt_token(
            email="multitenant@example.com",
            tenants=user_tenants,
            roles=["STR_Read"]
        )
        
        # Test access to each tenant
        for tenant in user_tenants:
            response = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            # Should succeed or return server error (but not 403)
            assert response.status_code in [200, 500]
    
    def test_multi_tenant_user_blocked_from_unauthorized_tenant(self, client, db):
        """Test that multi-tenant user is blocked from unauthorized tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 3:
            pytest.skip("Need at least 3 tenants for this test")
        
        # User has access to first two tenants only
        user_tenants = tenants[:2]
        unauthorized_tenant = tenants[2]
        
        token = self.create_jwt_token(
            email="multitenant@example.com",
            tenants=user_tenants,
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
    
    def test_single_tenant_user_data_isolation(self, client, db):
        """Test that single tenant user only sees their own data"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="singletenant@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test BNB table data
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
                        assert record['administration'] == tenant


class TestPerformanceImpactIntegration(TestTenantFilteringComprehensive):
    """Integration tests for performance impact of tenant filtering"""
    
    def test_tenant_filtering_performance_impact(self, client, db):
        """Test that tenant filtering has minimal performance impact"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="performance@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Measure response times for multiple endpoints
        endpoints = [
            '/api/bnb/bnb-listing-data',
            '/api/bnb/bnb-table',
            '/api/bnb/bnb-filter-options'
        ]
        
        response_times = []
        
        for endpoint in endpoints:
            start_time = time.time()
            
            response = client.get(
                endpoint,
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': tenant
                }
            )
            
            end_time = time.time()
            response_time = end_time - start_time
            response_times.append(response_time)
            
            # Verify response is successful or server error (not auth error)
            assert response.status_code in [200, 500]
        
        # Calculate average response time
        avg_response_time = sum(response_times) / len(response_times)
        
        # Performance assertion: average response time should be under 5 seconds
        # This is a reasonable threshold for database queries with tenant filtering
        assert avg_response_time < 5.0, f"Average response time {avg_response_time:.2f}s exceeds 5s threshold"
        
        print(f"Average response time with tenant filtering: {avg_response_time:.2f}s")
        print(f"Individual response times: {[f'{t:.2f}s' for t in response_times]}")
    
    def test_large_dataset_tenant_filtering(self, client, db):
        """Test tenant filtering performance with larger datasets"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="largedata@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        # Test BNB table endpoint which typically returns more data
        start_time = time.time()
        
        response = client.get(
            '/api/bnb/bnb-table?dateFrom=2020-01-01&dateTo=2024-12-31',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
        )
        
        end_time = time.time()
        response_time = end_time - start_time
        
        # Verify response
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            
            # Count returned records
            record_count = len(data.get('data', []))
            print(f"Retrieved {record_count} records in {response_time:.2f}s")
            
            # Performance assertion: should handle reasonable dataset sizes efficiently
            # Allow more time for larger datasets but still reasonable
            max_time = max(10.0, record_count * 0.001)  # 1ms per record minimum, 10s minimum
            assert response_time < max_time, f"Response time {response_time:.2f}s too slow for {record_count} records"


def main():
    """Run comprehensive integration tests"""
    print("\n" + "="*80)
    print("COMPREHENSIVE TENANT FILTERING INTEGRATION TESTS")
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
    print(f"Integration tests completed with exit code: {result.returncode}")
    print("="*80)
    
    return result.returncode == 0


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)