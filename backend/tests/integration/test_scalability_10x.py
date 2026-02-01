#!/usr/bin/env python3
"""
Scalability Testing for 10x Concurrent User Support

This test validates that the system can handle 10x more concurrent users
without performance degradation compared to the baseline system.

Requirements addressed:
- REQ-PAT-006: Scalability - System supports 10x more concurrent users without performance degradation

Test Scenarios:
1. Baseline Performance (10 concurrent users)
2. 10x Scale Performance (100 concurrent users)
3. Sustained Load Testing (10 minutes at 10x scale)
4. Resource Utilization Monitoring
5. Performance Degradation Analysis
"""

import pytest

# Skip scalability tests in CI - they require a running server and are too slow
pytestmark = [
    pytest.mark.performance,
    pytest.mark.skip_ci
]
import time
import statistics
import threading
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import sys
import os
import psutil
import logging

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager
from scalability_manager import ScalabilityManager, ScalabilityConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScalabilityTestConfig:
    """Configuration for scalability testing"""
    
    # Test server configuration
    BASE_URL = "http://localhost:5000"
    
    # Baseline test configuration (1x scale)
    BASELINE_CONCURRENT_USERS = 10
    BASELINE_REQUESTS_PER_USER = 20
    BASELINE_MAX_RESPONSE_TIME = 2.0  # seconds
    
    # 10x scale test configuration
    SCALE_10X_CONCURRENT_USERS = 100
    SCALE_10X_REQUESTS_PER_USER = 20
    SCALE_10X_MAX_RESPONSE_TIME = 2.5  # Allow slight increase for 10x load
    
    # Sustained load test configuration
    SUSTAINED_LOAD_DURATION = 600  # 10 minutes
    SUSTAINED_LOAD_USERS = 100
    SUSTAINED_LOAD_RPS = 50  # requests per second
    
    # Performance thresholds
    SUCCESS_RATE_THRESHOLD = 0.95  # 95% success rate
    RESOURCE_USAGE_THRESHOLD = 0.85  # 85% max resource usage
    PERFORMANCE_DEGRADATION_THRESHOLD = 1.5  # Max 50% performance degradation


class LoadTestResult:
    """Container for load test results"""
    
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.start_time = datetime.now()
        self.end_time = None
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.errors = []
        self.resource_usage = []
        
    def add_request_result(self, response_time: float, success: bool, error: Optional[str] = None):
        """Add result from a single request"""
        self.total_requests += 1
        self.response_times.append(response_time)
        
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if error:
                self.errors.append(error)
    
    def add_resource_sample(self, cpu_percent: float, memory_percent: float, timestamp: datetime):
        """Add resource usage sample"""
        self.resource_usage.append({
            'timestamp': timestamp,
            'cpu_percent': cpu_percent,
            'memory_percent': memory_percent
        })
    
    def finalize(self):
        """Finalize test results"""
        self.end_time = datetime.now()
    
    def get_statistics(self) -> Dict:
        """Get comprehensive test statistics"""
        if not self.response_times:
            return {'error': 'No response times recorded'}
        
        duration = (self.end_time - self.start_time).total_seconds()
        success_rate = self.successful_requests / self.total_requests if self.total_requests > 0 else 0
        
        stats = {
            'test_name': self.test_name,
            'duration_seconds': duration,
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': success_rate,
            'throughput_rps': self.total_requests / duration if duration > 0 else 0,
            'response_times': {
                'min': min(self.response_times),
                'max': max(self.response_times),
                'mean': statistics.mean(self.response_times),
                'median': statistics.median(self.response_times),
                'p95': statistics.quantiles(self.response_times, n=20)[18] if len(self.response_times) >= 20 else max(self.response_times),
                'p99': statistics.quantiles(self.response_times, n=100)[98] if len(self.response_times) >= 100 else max(self.response_times)
            }
        }
        
        # Resource usage statistics
        if self.resource_usage:
            cpu_values = [r['cpu_percent'] for r in self.resource_usage]
            memory_values = [r['memory_percent'] for r in self.resource_usage]
            
            stats['resource_usage'] = {
                'cpu': {
                    'min': min(cpu_values),
                    'max': max(cpu_values),
                    'mean': statistics.mean(cpu_values)
                },
                'memory': {
                    'min': min(memory_values),
                    'max': max(memory_values),
                    'mean': statistics.mean(memory_values)
                }
            }
        
        # Error analysis
        if self.errors:
            error_counts = {}
            for error in self.errors:
                error_counts[error] = error_counts.get(error, 0) + 1
            stats['error_analysis'] = error_counts
        
        return stats


class ScalabilityTester:
    """Main scalability testing class"""
    
    def __init__(self, config: ScalabilityTestConfig):
        self.config = config
        self.db_manager = DatabaseManager(test_mode=True)
        self.resource_monitor_active = False
        self.resource_monitor_thread = None
        
    def make_test_request(self, endpoint: str = "/api/health") -> Tuple[float, bool, Optional[str]]:
        """Make a single test request and measure response time"""
        start_time = time.time()
        
        try:
            response = requests.get(f"{self.config.BASE_URL}{endpoint}", timeout=10)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                return response_time, True, None
            else:
                return response_time, False, f"HTTP {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            response_time = time.time() - start_time
            return response_time, False, str(e)
    
    def start_resource_monitoring(self, result: LoadTestResult):
        """Start monitoring system resources"""
        self.resource_monitor_active = True
        
        def monitor_resources():
            while self.resource_monitor_active:
                try:
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory = psutil.virtual_memory()
                    
                    result.add_resource_sample(
                        cpu_percent=cpu_percent,
                        memory_percent=memory.percent,
                        timestamp=datetime.now()
                    )
                    
                    time.sleep(5)  # Sample every 5 seconds
                    
                except Exception as e:
                    logger.error(f"Resource monitoring error: {e}")
                    time.sleep(5)
        
        self.resource_monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
        self.resource_monitor_thread.start()
    
    def stop_resource_monitoring(self):
        """Stop resource monitoring"""
        self.resource_monitor_active = False
        if self.resource_monitor_thread:
            self.resource_monitor_thread.join(timeout=10)
    
    def run_concurrent_load_test(self, concurrent_users: int, requests_per_user: int, 
                                test_name: str) -> LoadTestResult:
        """Run concurrent load test with specified parameters"""
        result = LoadTestResult(test_name)
        
        logger.info(f"🚀 Starting {test_name}: {concurrent_users} users × {requests_per_user} requests")
        
        # Start resource monitoring
        self.start_resource_monitoring(result)
        
        try:
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                # Submit all requests
                futures = []
                for user_id in range(concurrent_users):
                    for request_id in range(requests_per_user):
                        future = executor.submit(self.make_test_request)
                        futures.append(future)
                
                # Collect results
                for future in as_completed(futures):
                    response_time, success, error = future.result()
                    result.add_request_result(response_time, success, error)
                    
                    # Log progress every 100 requests
                    if result.total_requests % 100 == 0:
                        logger.info(f"   Progress: {result.total_requests}/{len(futures)} requests completed")
        
        finally:
            # Stop resource monitoring
            self.stop_resource_monitoring()
            result.finalize()
        
        stats = result.get_statistics()
        logger.info(f"✅ {test_name} completed:")
        logger.info(f"   Duration: {stats['duration_seconds']:.1f}s")
        logger.info(f"   Success Rate: {stats['success_rate']:.1%}")
        logger.info(f"   Throughput: {stats['throughput_rps']:.1f} req/s")
        logger.info(f"   Response Time - Mean: {stats['response_times']['mean']:.3f}s, P95: {stats['response_times']['p95']:.3f}s")
        
        return result
    
    def run_sustained_load_test(self) -> LoadTestResult:
        """Run sustained load test for extended duration"""
        result = LoadTestResult("Sustained Load Test (10 minutes)")
        
        logger.info(f"🚀 Starting sustained load test: {self.config.SUSTAINED_LOAD_DURATION}s duration")
        
        # Start resource monitoring
        self.start_resource_monitoring(result)
        
        start_time = time.time()
        end_time = start_time + self.config.SUSTAINED_LOAD_DURATION
        
        try:
            with ThreadPoolExecutor(max_workers=self.config.SUSTAINED_LOAD_USERS) as executor:
                while time.time() < end_time:
                    batch_start = time.time()
                    
                    # Submit batch of requests to maintain target RPS
                    batch_size = min(self.config.SUSTAINED_LOAD_RPS, 
                                   self.config.SUSTAINED_LOAD_USERS)
                    
                    futures = []
                    for _ in range(batch_size):
                        future = executor.submit(self.make_test_request)
                        futures.append(future)
                    
                    # Collect batch results
                    for future in as_completed(futures):
                        response_time, success, error = future.result()
                        result.add_request_result(response_time, success, error)
                    
                    # Maintain target rate
                    batch_duration = time.time() - batch_start
                    if batch_duration < 1.0:
                        time.sleep(1.0 - batch_duration)
                    
                    # Log progress every minute
                    elapsed = time.time() - start_time
                    if int(elapsed) % 60 == 0 and elapsed > 0:
                        logger.info(f"   Progress: {elapsed/60:.0f} minutes, "
                                  f"{result.total_requests} requests, "
                                  f"{result.successful_requests/result.total_requests:.1%} success rate")
        
        finally:
            self.stop_resource_monitoring()
            result.finalize()
        
        stats = result.get_statistics()
        logger.info(f"✅ Sustained load test completed:")
        logger.info(f"   Duration: {stats['duration_seconds']:.1f}s")
        logger.info(f"   Total Requests: {stats['total_requests']}")
        logger.info(f"   Success Rate: {stats['success_rate']:.1%}")
        logger.info(f"   Average Throughput: {stats['throughput_rps']:.1f} req/s")
        
        return result
    
    def validate_scalability_requirements(self, baseline_result: LoadTestResult, 
                                        scale_10x_result: LoadTestResult) -> Dict:
        """Validate that 10x scalability requirements are met"""
        baseline_stats = baseline_result.get_statistics()
        scale_stats = scale_10x_result.get_statistics()
        
        validation_results = {
            'scalability_achieved': True,
            'issues': [],
            'metrics_comparison': {
                'baseline': baseline_stats,
                'scale_10x': scale_stats
            }
        }
        
        # Check success rate
        if scale_stats['success_rate'] < self.config.SUCCESS_RATE_THRESHOLD:
            validation_results['scalability_achieved'] = False
            validation_results['issues'].append(
                f"Success rate {scale_stats['success_rate']:.1%} below threshold {self.config.SUCCESS_RATE_THRESHOLD:.1%}"
            )
        
        # Check response time degradation
        baseline_p95 = baseline_stats['response_times']['p95']
        scale_p95 = scale_stats['response_times']['p95']
        degradation_ratio = scale_p95 / baseline_p95 if baseline_p95 > 0 else float('inf')
        
        if degradation_ratio > self.config.PERFORMANCE_DEGRADATION_THRESHOLD:
            validation_results['scalability_achieved'] = False
            validation_results['issues'].append(
                f"Performance degradation {degradation_ratio:.1f}x exceeds threshold {self.config.PERFORMANCE_DEGRADATION_THRESHOLD}x"
            )
        
        # Check absolute response time
        if scale_stats['response_times']['p95'] > self.config.SCALE_10X_MAX_RESPONSE_TIME:
            validation_results['scalability_achieved'] = False
            validation_results['issues'].append(
                f"P95 response time {scale_stats['response_times']['p95']:.3f}s exceeds limit {self.config.SCALE_10X_MAX_RESPONSE_TIME}s"
            )
        
        # Check resource usage
        if 'resource_usage' in scale_stats:
            max_cpu = scale_stats['resource_usage']['cpu']['max']
            max_memory = scale_stats['resource_usage']['memory']['max']
            
            if max_cpu > self.config.RESOURCE_USAGE_THRESHOLD * 100:
                validation_results['issues'].append(
                    f"Peak CPU usage {max_cpu:.1f}% exceeds threshold {self.config.RESOURCE_USAGE_THRESHOLD * 100:.1f}%"
                )
            
            if max_memory > self.config.RESOURCE_USAGE_THRESHOLD * 100:
                validation_results['issues'].append(
                    f"Peak memory usage {max_memory:.1f}% exceeds threshold {self.config.RESOURCE_USAGE_THRESHOLD * 100:.1f}%"
                )
        
        # Calculate improvement metrics
        throughput_improvement = scale_stats['throughput_rps'] / baseline_stats['throughput_rps'] if baseline_stats['throughput_rps'] > 0 else 0
        user_capacity_improvement = self.config.SCALE_10X_CONCURRENT_USERS / self.config.BASELINE_CONCURRENT_USERS
        
        validation_results['improvements'] = {
            'throughput_improvement': f"{throughput_improvement:.1f}x",
            'user_capacity_improvement': f"{user_capacity_improvement:.1f}x",
            'performance_degradation': f"{degradation_ratio:.1f}x",
            'scalability_efficiency': f"{(throughput_improvement / user_capacity_improvement) * 100:.1f}%"
        }
        
        return validation_results


class TestScalability10x:
    """Test suite for 10x scalability validation"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.config = ScalabilityTestConfig()
        self.tester = ScalabilityTester(self.config)
        
        # Verify server is running
        try:
            response = requests.get(f"{self.config.BASE_URL}/api/health", timeout=5)
            assert response.status_code == 200, "Test server is not running"
        except requests.exceptions.RequestException:
            pytest.skip("Test server is not running - start the application first")
    
    def test_baseline_performance(self):
        """Test baseline performance with 10 concurrent users"""
        result = self.tester.run_concurrent_load_test(
            concurrent_users=self.config.BASELINE_CONCURRENT_USERS,
            requests_per_user=self.config.BASELINE_REQUESTS_PER_USER,
            test_name="Baseline Performance (10 users)"
        )
        
        stats = result.get_statistics()
        
        # Validate baseline performance
        assert stats['success_rate'] >= self.config.SUCCESS_RATE_THRESHOLD, \
            f"Baseline success rate {stats['success_rate']:.1%} below threshold"
        
        assert stats['response_times']['p95'] <= self.config.BASELINE_MAX_RESPONSE_TIME, \
            f"Baseline P95 response time {stats['response_times']['p95']:.3f}s exceeds limit"
        
        # Store baseline for comparison
        self.baseline_result = result
    
    def test_10x_scale_performance(self):
        """Test 10x scale performance with 100 concurrent users"""
        # Ensure baseline test ran first
        if not hasattr(self, 'baseline_result'):
            self.test_baseline_performance()
        
        result = self.tester.run_concurrent_load_test(
            concurrent_users=self.config.SCALE_10X_CONCURRENT_USERS,
            requests_per_user=self.config.SCALE_10X_REQUESTS_PER_USER,
            test_name="10x Scale Performance (100 users)"
        )
        
        stats = result.get_statistics()
        
        # Validate 10x scale performance
        assert stats['success_rate'] >= self.config.SUCCESS_RATE_THRESHOLD, \
            f"10x scale success rate {stats['success_rate']:.1%} below threshold"
        
        assert stats['response_times']['p95'] <= self.config.SCALE_10X_MAX_RESPONSE_TIME, \
            f"10x scale P95 response time {stats['response_times']['p95']:.3f}s exceeds limit"
        
        # Store for validation
        self.scale_10x_result = result
    
    def test_scalability_validation(self):
        """Validate that 10x scalability requirements are met"""
        # Ensure both baseline and scale tests ran
        if not hasattr(self, 'baseline_result'):
            self.test_baseline_performance()
        if not hasattr(self, 'scale_10x_result'):
            self.test_10x_scale_performance()
        
        validation = self.tester.validate_scalability_requirements(
            self.baseline_result, self.scale_10x_result
        )
        
        # Print detailed validation results
        print("\n" + "="*80)
        print("SCALABILITY VALIDATION RESULTS")
        print("="*80)
        print(f"Scalability Achieved: {'✅ YES' if validation['scalability_achieved'] else '❌ NO'}")
        print(f"User Capacity Improvement: {validation['improvements']['user_capacity_improvement']}")
        print(f"Throughput Improvement: {validation['improvements']['throughput_improvement']}")
        print(f"Performance Degradation: {validation['improvements']['performance_degradation']}")
        print(f"Scalability Efficiency: {validation['improvements']['scalability_efficiency']}")
        
        if validation['issues']:
            print("\nIssues Found:")
            for issue in validation['issues']:
                print(f"  ❌ {issue}")
        else:
            print("\n✅ All scalability requirements met!")
        
        print("="*80)
        
        # Assert scalability requirements
        assert validation['scalability_achieved'], \
            f"Scalability requirements not met: {validation['issues']}"
    
    def test_sustained_load_performance(self):
        """Test sustained load performance over 10 minutes"""
        result = self.tester.run_sustained_load_test()
        stats = result.get_statistics()
        
        # Validate sustained performance
        assert stats['success_rate'] >= self.config.SUCCESS_RATE_THRESHOLD, \
            f"Sustained load success rate {stats['success_rate']:.1%} below threshold"
        
        assert stats['response_times']['p95'] <= self.config.SCALE_10X_MAX_RESPONSE_TIME, \
            f"Sustained load P95 response time {stats['response_times']['p95']:.3f}s exceeds limit"
        
        # Validate throughput consistency
        target_throughput = self.config.SUSTAINED_LOAD_RPS
        actual_throughput = stats['throughput_rps']
        throughput_efficiency = actual_throughput / target_throughput
        
        assert throughput_efficiency >= 0.8, \
            f"Sustained throughput efficiency {throughput_efficiency:.1%} below 80%"
    
    def test_scalability_manager_health(self):
        """Test scalability manager health and status"""
        try:
            response = requests.get(f"{self.config.BASE_URL}/api/scalability/status", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                assert data['scalability_active'], "Scalability manager not active"
                assert data['concurrent_capacity'] == '10x baseline', "Incorrect concurrent capacity"
                assert data['performance_ready'], "System not performance ready"
                
                health = data['health']
                assert health['health_score'] >= 70, f"Health score {health['health_score']} below threshold"
                assert health['scalability_ready'], "System not scalability ready"
                
                print(f"\n✅ Scalability Manager Health: {health['status']} (Score: {health['health_score']})")
                print(f"✅ Concurrent Capacity: {data['concurrent_capacity']}")
                
            else:
                pytest.skip("Scalability manager not available")
                
        except requests.exceptions.RequestException:
            pytest.skip("Cannot connect to scalability status endpoint")


if __name__ == '__main__':
    # Run scalability tests
    print("🚀 Starting 10x Scalability Validation Tests")
    print("="*80)
    
    # Run with verbose output
    pytest.main([__file__, '-v', '-s', '--tb=short'])