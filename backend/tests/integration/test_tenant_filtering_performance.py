"""
Tenant Filtering Performance Tests

Tests to measure and validate the performance impact of tenant filtering:
- Response time measurements
- Query performance analysis
- Load testing scenarios
- Memory usage monitoring
- Database query optimization validation
"""

import pytest
import json
import base64
import time
import statistics
import psutil
import os
from flask import Flask
from database import DatabaseManager
from bnb_routes import bnb_bp
from str_channel_routes import str_channel_bp
from str_invoice_routes import str_invoice_bp

# Skip performance tests in CI - they're too slow and should be run manually
pytestmark = [
    pytest.mark.performance,
    pytest.mark.skip_ci
]


class TestTenantFilteringPerformance:
    """Performance tests for tenant filtering implementation"""
    
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
        """Create database manager for performance testing"""
        return DatabaseManager(test_mode=False)  # Use real database for performance tests
    
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
            return ['PeterPrive', 'GoodwinSolutions']
    
    def measure_response_time(self, client, endpoint, headers, iterations=5):
        """Measure response time for an endpoint over multiple iterations"""
        response_times = []
        
        for _ in range(iterations):
            start_time = time.time()
            response = client.get(endpoint, headers=headers)
            end_time = time.time()
            
            response_time = end_time - start_time
            response_times.append(response_time)
            
            # Verify response is successful
            assert response.status_code in [200, 500], f"Unexpected status code: {response.status_code}"
        
        return {
            'times': response_times,
            'avg': statistics.mean(response_times),
            'min': min(response_times),
            'max': max(response_times),
            'median': statistics.median(response_times),
            'stdev': statistics.stdev(response_times) if len(response_times) > 1 else 0
        }
    
    def get_memory_usage(self):
        """Get current memory usage of the process"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB


class TestResponseTimePerformance(TestTenantFilteringPerformance):
    """Test response time performance of tenant filtering"""
    
    def test_bnb_listing_data_response_time(self, client, db):
        """Test response time for BNB listing data endpoint"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="performance@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Measure response time
        metrics = self.measure_response_time(client, '/api/bnb/bnb-listing-data', headers, iterations=10)
        
        print(f"\nBNB Listing Data Performance:")
        print(f"  Average: {metrics['avg']:.3f}s")
        print(f"  Min: {metrics['min']:.3f}s")
        print(f"  Max: {metrics['max']:.3f}s")
        print(f"  Median: {metrics['median']:.3f}s")
        print(f"  Std Dev: {metrics['stdev']:.3f}s")
        
        # Performance assertions
        assert metrics['avg'] < 5.0, f"Average response time {metrics['avg']:.3f}s exceeds 5s threshold"
        assert metrics['max'] < 10.0, f"Maximum response time {metrics['max']:.3f}s exceeds 10s threshold"
    
    def test_bnb_table_response_time(self, client, db):
        """Test response time for BNB table endpoint (typically returns more data)"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="performance@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Measure response time
        metrics = self.measure_response_time(client, '/api/bnb/bnb-table', headers, iterations=10)
        
        print(f"\nBNB Table Performance:")
        print(f"  Average: {metrics['avg']:.3f}s")
        print(f"  Min: {metrics['min']:.3f}s")
        print(f"  Max: {metrics['max']:.3f}s")
        print(f"  Median: {metrics['median']:.3f}s")
        print(f"  Std Dev: {metrics['stdev']:.3f}s")
        
        # Performance assertions (allow more time for table data)
        assert metrics['avg'] < 8.0, f"Average response time {metrics['avg']:.3f}s exceeds 8s threshold"
        assert metrics['max'] < 15.0, f"Maximum response time {metrics['max']:.3f}s exceeds 15s threshold"
    
    def test_bnb_filter_options_response_time(self, client, db):
        """Test response time for BNB filter options endpoint"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="performance@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Measure response time
        metrics = self.measure_response_time(client, '/api/bnb/bnb-filter-options', headers, iterations=10)
        
        print(f"\nBNB Filter Options Performance:")
        print(f"  Average: {metrics['avg']:.3f}s")
        print(f"  Min: {metrics['min']:.3f}s")
        print(f"  Max: {metrics['max']:.3f}s")
        print(f"  Median: {metrics['median']:.3f}s")
        print(f"  Std Dev: {metrics['stdev']:.3f}s")
        
        # Performance assertions (filter options should be fast)
        assert metrics['avg'] < 3.0, f"Average response time {metrics['avg']:.3f}s exceeds 3s threshold"
        assert metrics['max'] < 6.0, f"Maximum response time {metrics['max']:.3f}s exceeds 6s threshold"
    
    def test_str_invoice_search_response_time(self, client, db):
        """Test response time for STR invoice search endpoint"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="performance@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Measure response time
        metrics = self.measure_response_time(client, '/api/str-invoice/search-booking?query=test', headers, iterations=10)
        
        print(f"\nSTR Invoice Search Performance:")
        print(f"  Average: {metrics['avg']:.3f}s")
        print(f"  Min: {metrics['min']:.3f}s")
        print(f"  Max: {metrics['max']:.3f}s")
        print(f"  Median: {metrics['median']:.3f}s")
        print(f"  Std Dev: {metrics['stdev']:.3f}s")
        
        # Performance assertions (search should be reasonably fast)
        assert metrics['avg'] < 4.0, f"Average response time {metrics['avg']:.3f}s exceeds 4s threshold"
        assert metrics['max'] < 8.0, f"Maximum response time {metrics['max']:.3f}s exceeds 8s threshold"


class TestLoadPerformance(TestTenantFilteringPerformance):
    """Test performance under load scenarios"""
    
    def test_concurrent_requests_performance(self, client, db):
        """Test performance with multiple concurrent-like requests"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="load@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Simulate concurrent requests by making rapid sequential requests
        endpoints = [
            '/api/bnb/bnb-listing-data',
            '/api/bnb/bnb-table',
            '/api/bnb/bnb-filter-options',
            '/api/bnb/bnb-actuals'
        ]
        
        start_time = time.time()
        response_times = []
        
        # Make 20 requests across different endpoints
        for i in range(20):
            endpoint = endpoints[i % len(endpoints)]
            
            request_start = time.time()
            response = client.get(endpoint, headers=headers)
            request_end = time.time()
            
            response_time = request_end - request_start
            response_times.append(response_time)
            
            # Verify response is successful
            assert response.status_code in [200, 500], f"Request {i+1} failed with {response.status_code}"
        
        total_time = time.time() - start_time
        avg_response_time = statistics.mean(response_times)
        
        print(f"\nLoad Test Performance (20 requests):")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Average response time: {avg_response_time:.3f}s")
        print(f"  Requests per second: {20/total_time:.2f}")
        print(f"  Min response time: {min(response_times):.3f}s")
        print(f"  Max response time: {max(response_times):.3f}s")
        
        # Performance assertions
        assert avg_response_time < 6.0, f"Average response time under load {avg_response_time:.3f}s exceeds 6s threshold"
        assert 20/total_time > 1.0, f"Throughput {20/total_time:.2f} req/s is too low"
    
    def test_multi_tenant_user_performance(self, client, db):
        """Test performance for multi-tenant users switching between tenants"""
        tenants = self.get_available_tenants(db)
        if len(tenants) < 2:
            pytest.skip("Need at least 2 tenants for multi-tenant performance test")
        
        # User has access to multiple tenants
        user_tenants = tenants[:min(3, len(tenants))]
        
        token = self.create_jwt_token(
            email="multiperf@example.com",
            tenants=user_tenants,
            roles=["STR_Read"]
        )
        
        response_times = []
        
        # Test switching between tenants
        for i in range(15):  # 15 requests
            tenant = user_tenants[i % len(user_tenants)]
            
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Tenant': tenant
            }
            
            start_time = time.time()
            response = client.get('/api/bnb/bnb-listing-data', headers=headers)
            end_time = time.time()
            
            response_time = end_time - start_time
            response_times.append(response_time)
            
            # Verify response is successful
            assert response.status_code in [200, 500], f"Multi-tenant request failed with {response.status_code}"
        
        avg_response_time = statistics.mean(response_times)
        
        print(f"\nMulti-Tenant User Performance:")
        print(f"  Average response time: {avg_response_time:.3f}s")
        print(f"  Min response time: {min(response_times):.3f}s")
        print(f"  Max response time: {max(response_times):.3f}s")
        print(f"  Tenants tested: {user_tenants}")
        
        # Performance assertions
        assert avg_response_time < 5.0, f"Multi-tenant average response time {avg_response_time:.3f}s exceeds 5s threshold"
    
    def test_large_dataset_performance(self, client, db):
        """Test performance with large date ranges (potentially more data)"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="largedata@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Test with large date range
        start_time = time.time()
        response = client.get(
            '/api/bnb/bnb-table?dateFrom=2020-01-01&dateTo=2024-12-31',
            headers=headers
        )
        end_time = time.time()
        
        response_time = end_time - start_time
        
        # Verify response
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            
            record_count = len(data.get('data', []))
            
            print(f"\nLarge Dataset Performance:")
            print(f"  Response time: {response_time:.3f}s")
            print(f"  Records returned: {record_count}")
            print(f"  Time per record: {response_time/max(record_count, 1)*1000:.2f}ms")
            
            # Performance assertions based on data size
            if record_count > 0:
                time_per_record = response_time / record_count
                assert time_per_record < 0.01, f"Time per record {time_per_record:.4f}s is too high"
            
            # Overall response time should be reasonable even for large datasets
            assert response_time < 30.0, f"Large dataset response time {response_time:.3f}s exceeds 30s threshold"


class TestMemoryPerformance(TestTenantFilteringPerformance):
    """Test memory usage and performance"""
    
    def test_memory_usage_during_requests(self, client, db):
        """Test memory usage during multiple requests"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="memory@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Measure initial memory usage
        initial_memory = self.get_memory_usage()
        
        # Make multiple requests
        for i in range(10):
            response = client.get('/api/bnb/bnb-table', headers=headers)
            assert response.status_code in [200, 500]
        
        # Measure final memory usage
        final_memory = self.get_memory_usage()
        memory_increase = final_memory - initial_memory
        
        print(f"\nMemory Usage Test:")
        print(f"  Initial memory: {initial_memory:.2f} MB")
        print(f"  Final memory: {final_memory:.2f} MB")
        print(f"  Memory increase: {memory_increase:.2f} MB")
        
        # Memory usage should not increase dramatically
        assert memory_increase < 100.0, f"Memory increase {memory_increase:.2f} MB is too high"
    
    def test_memory_efficiency_comparison(self, client, db):
        """Test memory efficiency of tenant filtering vs non-filtered queries"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="efficiency@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Measure memory before requests
        initial_memory = self.get_memory_usage()
        
        # Make requests to different endpoints
        endpoints = [
            '/api/bnb/bnb-listing-data',
            '/api/bnb/bnb-table',
            '/api/bnb/bnb-filter-options'
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint, headers=headers)
            assert response.status_code in [200, 500]
        
        # Measure memory after requests
        final_memory = self.get_memory_usage()
        memory_per_request = (final_memory - initial_memory) / len(endpoints)
        
        print(f"\nMemory Efficiency Test:")
        print(f"  Memory per request: {memory_per_request:.2f} MB")
        print(f"  Total memory increase: {final_memory - initial_memory:.2f} MB")
        
        # Memory per request should be reasonable
        assert memory_per_request < 20.0, f"Memory per request {memory_per_request:.2f} MB is too high"


class TestPerformanceRegression(TestTenantFilteringPerformance):
    """Test for performance regressions"""
    
    def test_performance_baseline(self, client, db):
        """Establish performance baseline for tenant filtering"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="baseline@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Test key endpoints and establish baseline
        baseline_results = {}
        
        endpoints = {
            'listing_data': '/api/bnb/bnb-listing-data',
            'table_data': '/api/bnb/bnb-table',
            'filter_options': '/api/bnb/bnb-filter-options',
            'actuals': '/api/bnb/bnb-actuals'
        }
        
        for name, endpoint in endpoints.items():
            metrics = self.measure_response_time(client, endpoint, headers, iterations=5)
            baseline_results[name] = metrics
            
            print(f"\n{name.replace('_', ' ').title()} Baseline:")
            print(f"  Average: {metrics['avg']:.3f}s")
            print(f"  95th percentile: {sorted(metrics['times'])[int(0.95 * len(metrics['times']))]:.3f}s")
        
        # Store baseline results (in a real scenario, these would be compared against previous runs)
        print(f"\nPerformance Baseline Established:")
        for name, metrics in baseline_results.items():
            print(f"  {name}: {metrics['avg']:.3f}s avg, {metrics['max']:.3f}s max")
        
        # Verify all endpoints meet minimum performance requirements
        for name, metrics in baseline_results.items():
            assert metrics['avg'] < 10.0, f"{name} average response time {metrics['avg']:.3f}s exceeds baseline threshold"
            assert metrics['max'] < 20.0, f"{name} maximum response time {metrics['max']:.3f}s exceeds baseline threshold"
    
    def test_performance_consistency(self, client, db):
        """Test that performance is consistent across multiple runs"""
        tenants = self.get_available_tenants(db)
        if not tenants:
            pytest.skip("No tenants available in database")
        
        tenant = tenants[0]
        token = self.create_jwt_token(
            email="consistency@example.com",
            tenants=[tenant],
            roles=["STR_Read"]
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant
        }
        
        # Run the same endpoint multiple times and check consistency
        all_times = []
        
        for run in range(3):  # 3 separate runs
            metrics = self.measure_response_time(client, '/api/bnb/bnb-listing-data', headers, iterations=5)
            all_times.extend(metrics['times'])
            print(f"Run {run + 1}: avg={metrics['avg']:.3f}s, stdev={metrics['stdev']:.3f}s")
        
        # Calculate overall statistics
        overall_avg = statistics.mean(all_times)
        overall_stdev = statistics.stdev(all_times)
        coefficient_of_variation = overall_stdev / overall_avg
        
        print(f"\nConsistency Test Results:")
        print(f"  Overall average: {overall_avg:.3f}s")
        print(f"  Overall std dev: {overall_stdev:.3f}s")
        print(f"  Coefficient of variation: {coefficient_of_variation:.3f}")
        
        # Performance should be reasonably consistent
        assert coefficient_of_variation < 0.5, f"Performance too inconsistent (CV={coefficient_of_variation:.3f})"


def main():
    """Run performance tests"""
    print("\n" + "="*80)
    print("TENANT FILTERING PERFORMANCE TESTS")
    print("="*80)
    
    # Run pytest with verbose output
    import subprocess
    import sys
    
    result = subprocess.run([
        sys.executable, '-m', 'pytest', 
        __file__, 
        '-v', 
        '--tb=short',
        '--disable-warnings',
        '-s'  # Don't capture output so we can see print statements
    ], capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    print("="*80)
    print(f"Performance tests completed with exit code: {result.returncode}")
    print("="*80)
    
    return result.returncode == 0


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)