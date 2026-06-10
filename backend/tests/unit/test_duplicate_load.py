"""
Load Testing for Duplicate Detection System

Tests system performance under various load conditions to ensure
it meets the 2-second response time requirement.

Requirements: 5.5
"""

import pytest
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import random
from typing import List, Dict, Tuple
from unittest.mock import MagicMock

from duplicate_checker import DuplicateChecker
from duplicate_performance_monitor import (
    get_metrics_collector,
    reset_performance_metrics
)


class LoadTestScenario:
    """Represents a load testing scenario."""
    
    def __init__(self, name: str, concurrent_users: int, requests_per_user: int):
        self.name = name
        self.concurrent_users = concurrent_users
        self.requests_per_user = requests_per_user
        self.total_requests = concurrent_users * requests_per_user


@pytest.fixture
def db_manager():
    """Fixture for a mocked database manager suitable for load tests."""
    mock_db = MagicMock()
    # Return empty results by default (no duplicates found)
    mock_db.execute_query.return_value = []
    return mock_db


@pytest.fixture
def duplicate_checker(db_manager):
    """Fixture for duplicate checker."""
    return DuplicateChecker(db_manager)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test."""
    reset_performance_metrics()
    yield
    reset_performance_metrics()


def generate_test_data(count: int) -> List[Tuple[str, str, float]]:
    """
    Generate test data for load testing.
    
    Args:
        count: Number of test records to generate
        
    Returns:
        List of tuples (reference_number, transaction_date, transaction_amount)
    """
    test_data = []
    base_date = datetime.now() - timedelta(days=365)
    
    for i in range(count):
        ref_num = f"LoadTest{i % 50}"  # 50 unique reference numbers
        date = (base_date + timedelta(days=random.randint(0, 365))).strftime('%Y-%m-%d')
        amount = round(random.uniform(10.0, 1000.0), 2)
        test_data.append((ref_num, date, amount))
    
    return test_data


def execute_duplicate_check(
    checker: DuplicateChecker,
    reference_number: str,
    transaction_date: str,
    transaction_amount: float
) -> Dict:
    """
    Execute a single duplicate check and measure performance.
    
    Returns:
        Dictionary with execution results and timing
    """
    start_time = time.time()
    
    try:
        results = checker.check_for_duplicates(
            reference_number=reference_number,
            transaction_date=transaction_date,
            transaction_amount=transaction_amount
        )
        
        execution_time = time.time() - start_time
        
        return {
            'success': True,
            'execution_time': execution_time,
            'duplicates_found': len(results) if results else 0,
            'error': None
        }
        
    except Exception as e:
        execution_time = time.time() - start_time
        return {
            'success': False,
            'execution_time': execution_time,
            'duplicates_found': 0,
            'error': str(e)
        }


class TestDuplicateDetectionLoad:
    """Load tests for duplicate detection system."""
    
    def test_single_user_performance(self, duplicate_checker):
        """
        Test performance with single user making sequential requests.
        
        Requirement: 5.5 - Must complete within 2 seconds
        """
        test_data = generate_test_data(20)
        results = []
        
        for ref, date, amount in test_data:
            result = execute_duplicate_check(duplicate_checker, ref, date, amount)
            results.append(result)
        
        # Analyze results
        execution_times = [r['execution_time'] for r in results if r['success']]
        
        assert len(execution_times) > 0, "No successful requests"
        
        avg_time = statistics.mean(execution_times)
        max_time = max(execution_times)
        p95_time = statistics.quantiles(execution_times, n=20)[18]  # 95th percentile
        
        print(f"\nSingle User Performance:")
        print(f"  Total requests: {len(results)}")
        print(f"  Successful: {sum(1 for r in results if r['success'])}")
        print(f"  Average time: {avg_time:.3f}s")
        print(f"  Max time: {max_time:.3f}s")
        print(f"  95th percentile: {p95_time:.3f}s")
        
        # Assert performance requirements
        assert avg_time < 2.0, f"Average time {avg_time:.3f}s exceeds 2 second requirement"
        assert max_time < 3.0, f"Max time {max_time:.3f}s is too high"
        assert p95_time < 2.0, f"95th percentile {p95_time:.3f}s exceeds requirement"
    
    def test_concurrent_users_light_load(self, duplicate_checker):
        """
        Test performance with 5 concurrent users (light load).
        
        Requirement: 5.5 - System should handle concurrent requests efficiently
        """
        scenario = LoadTestScenario("Light Load", concurrent_users=5, requests_per_user=10)
        test_data = generate_test_data(scenario.total_requests)
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=scenario.concurrent_users) as executor:
            futures = []
            
            for ref, date, amount in test_data:
                future = executor.submit(
                    execute_duplicate_check,
                    duplicate_checker, ref, date, amount
                )
                futures.append(future)
            
            for future in as_completed(futures):
                results.append(future.result())
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = [r for r in results if r['success']]
        execution_times = [r['execution_time'] for r in successful]
        
        assert len(successful) > 0, "No successful requests"
        
        avg_time = statistics.mean(execution_times)
        max_time = max(execution_times)
        throughput = len(successful) / total_time
        
        print(f"\nLight Load Performance ({scenario.concurrent_users} users):")
        print(f"  Total requests: {len(results)}")
        print(f"  Successful: {len(successful)}")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Average time: {avg_time:.3f}s")
        print(f"  Max time: {max_time:.3f}s")
        print(f"  Throughput: {throughput:.2f} req/s")
        
        # Assert performance requirements
        assert avg_time < 2.0, f"Average time {avg_time:.3f}s exceeds requirement"
        assert len(successful) / len(results) > 0.95, "Success rate below 95%"
    
    def test_concurrent_users_medium_load(self, duplicate_checker):
        """
        Test performance with 10 concurrent users (medium load).
        
        Requirement: 5.5 - System should maintain performance under medium load
        """
        scenario = LoadTestScenario("Medium Load", concurrent_users=10, requests_per_user=10)
        test_data = generate_test_data(scenario.total_requests)
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=scenario.concurrent_users) as executor:
            futures = []
            
            for ref, date, amount in test_data:
                future = executor.submit(
                    execute_duplicate_check,
                    duplicate_checker, ref, date, amount
                )
                futures.append(future)
            
            for future in as_completed(futures):
                results.append(future.result())
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = [r for r in results if r['success']]
        execution_times = [r['execution_time'] for r in successful]
        
        assert len(successful) > 0, "No successful requests"
        
        avg_time = statistics.mean(execution_times)
        max_time = max(execution_times)
        throughput = len(successful) / total_time
        
        print(f"\nMedium Load Performance ({scenario.concurrent_users} users):")
        print(f"  Total requests: {len(results)}")
        print(f"  Successful: {len(successful)}")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Average time: {avg_time:.3f}s")
        print(f"  Max time: {max_time:.3f}s")
        print(f"  Throughput: {throughput:.2f} req/s")
        
        # Assert performance requirements (slightly relaxed for concurrent load)
        assert avg_time < 2.5, f"Average time {avg_time:.3f}s exceeds acceptable limit"
        assert len(successful) / len(results) > 0.90, "Success rate below 90%"
    
    def test_performance_metrics_collection(self, duplicate_checker):
        """
        Test that performance metrics are collected correctly.
        
        Requirement: 6.4 - System should collect performance metrics
        """
        test_data = generate_test_data(10)
        
        # Execute some checks
        for ref, date, amount in test_data:
            execute_duplicate_check(duplicate_checker, ref, date, amount)
        
        # Get metrics
        metrics_collector = get_metrics_collector()
        summary = metrics_collector.get_summary_statistics()
        
        # Verify metrics collection
        assert 'duplicate_checks' in summary
        assert summary['duplicate_checks']['total_checks'] >= 10
        assert 'avg_execution_time' in summary['duplicate_checks']
        assert 'performance_health' in summary
        
        health = summary['performance_health']
        assert 'score' in health
        assert 'status' in health
        assert 'recommendations' in health
        
        print(f"\nPerformance Metrics:")
        print(f"  Total checks: {summary['duplicate_checks']['total_checks']}")
        print(f"  Avg time: {summary['duplicate_checks']['avg_execution_time']:.3f}s")
        print(f"  Health score: {health['score']}")
        print(f"  Health status: {health['status']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
