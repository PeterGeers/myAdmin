"""
Performance Monitoring and Optimization for Duplicate Detection System

This module provides comprehensive performance monitoring, metrics collection,
and optimization capabilities specifically for the duplicate invoice detection system.

Requirements: 5.5, 6.4
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from functools import wraps
import json

logger = logging.getLogger(__name__)


class DuplicateDetectionMetrics:
    """
    Collects and manages metrics for duplicate detection operations.
    
    Tracks performance metrics including:
    - Query execution times
    - Detection accuracy
    - Cache hit rates
    - Error rates
    - System load
    """
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.aggregated_metrics = {}
        self.start_time = datetime.now()
        
        # Performance thresholds (from requirements)
        self.query_time_threshold = 2.0  # 2 seconds max (Requirement 5.5)
        self.cache_hit_target = 0.7  # 70% cache hit rate target
        
    def record_duplicate_check(
        self,
        execution_time: float,
        duplicates_found: int,
        cache_hit: bool = False,
        error: Optional[str] = None
    ) -> None:
        """
        Record metrics for a duplicate check operation.
        
        Args:
            execution_time: Time taken to execute the check in seconds
            duplicates_found: Number of duplicates found
            cache_hit: Whether the result was served from cache
            error: Error message if operation failed
        """
        metric_entry = {
            'timestamp': datetime.now().isoformat(),
            'execution_time': execution_time,
            'duplicates_found': duplicates_found,
            'cache_hit': cache_hit,
            'error': error,
            'threshold_exceeded': execution_time > self.query_time_threshold
        }
        
        self.metrics['duplicate_checks'].append(metric_entry)
        
        # Log performance warnings
        if execution_time > self.query_time_threshold:
            logger.warning(
                f"Duplicate check exceeded threshold: {execution_time:.3f}s > {self.query_time_threshold}s"
            )
    
    def record_file_cleanup(
        self,
        execution_time: float,
        success: bool,
        file_size_bytes: Optional[int] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Record metrics for file cleanup operations.
        
        Args:
            execution_time: Time taken to cleanup file in seconds
            success: Whether cleanup was successful
            file_size_bytes: Size of file cleaned up
            error: Error message if operation failed
        """
        metric_entry = {
            'timestamp': datetime.now().isoformat(),
            'execution_time': execution_time,
            'success': success,
            'file_size_bytes': file_size_bytes,
            'file_size_mb': file_size_bytes / (1024 * 1024) if file_size_bytes else None,
            'error': error
        }
        
        self.metrics['file_cleanups'].append(metric_entry)
    
    def record_decision_log(
        self,
        execution_time: float,
        decision: str,
        success: bool,
        retry_count: int = 0,
        error: Optional[str] = None
    ) -> None:
        """
        Record metrics for decision logging operations.
        
        Args:
            execution_time: Time taken to log decision in seconds
            decision: User decision ('continue' or 'cancel')
            success: Whether logging was successful
            retry_count: Number of retries attempted
            error: Error message if operation failed
        """
        metric_entry = {
            'timestamp': datetime.now().isoformat(),
            'execution_time': execution_time,
            'decision': decision,
            'success': success,
            'retry_count': retry_count,
            'error': error
        }
        
        self.metrics['decision_logs'].append(metric_entry)
    
    def record_database_query(
        self,
        query_type: str,
        execution_time: float,
        rows_returned: int,
        cache_hit: bool = False,
        error: Optional[str] = None
    ) -> None:
        """
        Record metrics for database query operations.
        
        Args:
            query_type: Type of query (e.g., 'duplicate_check', 'decision_log')
            execution_time: Time taken to execute query in seconds
            rows_returned: Number of rows returned
            cache_hit: Whether result was served from cache
            error: Error message if query failed
        """
        metric_entry = {
            'timestamp': datetime.now().isoformat(),
            'query_type': query_type,
            'execution_time': execution_time,
            'rows_returned': rows_returned,
            'cache_hit': cache_hit,
            'error': error,
            'slow_query': execution_time > 1.0  # Queries over 1 second are slow
        }
        
        self.metrics['database_queries'].append(metric_entry)
        
        # Log slow queries
        if execution_time > 1.0:
            logger.warning(
                f"Slow database query detected: {query_type} took {execution_time:.3f}s"
            )
    
    def get_summary_statistics(self) -> Dict:
        """
        Calculate summary statistics for all collected metrics.
        
        Returns:
            Dictionary containing aggregated statistics
        """
        summary = {
            'collection_period': {
                'start': self.start_time.isoformat(),
                'end': datetime.now().isoformat(),
                'duration_hours': (datetime.now() - self.start_time).total_seconds() / 3600
            },
            'duplicate_checks': self._summarize_duplicate_checks(),
            'file_cleanups': self._summarize_file_cleanups(),
            'decision_logs': self._summarize_decision_logs(),
            'database_queries': self._summarize_database_queries(),
            'performance_health': self._calculate_performance_health()
        }
        
        return summary
    
    def _summarize_duplicate_checks(self) -> Dict:
        """Summarize duplicate check metrics."""
        checks = self.metrics.get('duplicate_checks', [])
        
        if not checks:
            return {'total_checks': 0}
        
        execution_times = [c['execution_time'] for c in checks]
        cache_hits = sum(1 for c in checks if c['cache_hit'])
        errors = sum(1 for c in checks if c['error'])
        threshold_exceeded = sum(1 for c in checks if c['threshold_exceeded'])
        duplicates_found = sum(c['duplicates_found'] for c in checks)
        
        return {
            'total_checks': len(checks),
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'min_execution_time': min(execution_times),
            'max_execution_time': max(execution_times),
            'cache_hit_rate': cache_hits / len(checks) if checks else 0,
            'error_rate': errors / len(checks) if checks else 0,
            'threshold_exceeded_count': threshold_exceeded,
            'threshold_exceeded_rate': threshold_exceeded / len(checks) if checks else 0,
            'total_duplicates_found': duplicates_found,
            'avg_duplicates_per_check': duplicates_found / len(checks) if checks else 0
        }
    
    def _summarize_file_cleanups(self) -> Dict:
        """Summarize file cleanup metrics."""
        cleanups = self.metrics.get('file_cleanups', [])
        
        if not cleanups:
            return {'total_cleanups': 0}
        
        execution_times = [c['execution_time'] for c in cleanups]
        successes = sum(1 for c in cleanups if c['success'])
        total_size_mb = sum(c['file_size_mb'] for c in cleanups if c['file_size_mb'])
        
        return {
            'total_cleanups': len(cleanups),
            'success_rate': successes / len(cleanups) if cleanups else 0,
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'total_space_freed_mb': total_size_mb,
            'avg_file_size_mb': total_size_mb / len(cleanups) if cleanups else 0
        }
    
    def _summarize_decision_logs(self) -> Dict:
        """Summarize decision logging metrics."""
        logs = self.metrics.get('decision_logs', [])
        
        if not logs:
            return {'total_decisions': 0}
        
        execution_times = [l['execution_time'] for l in logs]
        successes = sum(1 for l in logs if l['success'])
        continue_decisions = sum(1 for l in logs if l['decision'] == 'continue')
        cancel_decisions = sum(1 for l in logs if l['decision'] == 'cancel')
        total_retries = sum(l['retry_count'] for l in logs)
        
        return {
            'total_decisions': len(logs),
            'success_rate': successes / len(logs) if logs else 0,
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'continue_count': continue_decisions,
            'cancel_count': cancel_decisions,
            'continue_rate': continue_decisions / len(logs) if logs else 0,
            'cancel_rate': cancel_decisions / len(logs) if logs else 0,
            'total_retries': total_retries,
            'avg_retries_per_decision': total_retries / len(logs) if logs else 0
        }
    
    def _summarize_database_queries(self) -> Dict:
        """Summarize database query metrics."""
        queries = self.metrics.get('database_queries', [])
        
        if not queries:
            return {'total_queries': 0}
        
        execution_times = [q['execution_time'] for q in queries]
        cache_hits = sum(1 for q in queries if q['cache_hit'])
        slow_queries = sum(1 for q in queries if q['slow_query'])
        errors = sum(1 for q in queries if q['error'])
        
        # Group by query type
        by_type = defaultdict(list)
        for q in queries:
            by_type[q['query_type']].append(q['execution_time'])
        
        type_stats = {
            qtype: {
                'count': len(times),
                'avg_time': sum(times) / len(times),
                'max_time': max(times)
            }
            for qtype, times in by_type.items()
        }
        
        return {
            'total_queries': len(queries),
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'max_execution_time': max(execution_times),
            'cache_hit_rate': cache_hits / len(queries) if queries else 0,
            'slow_query_count': slow_queries,
            'slow_query_rate': slow_queries / len(queries) if queries else 0,
            'error_rate': errors / len(queries) if queries else 0,
            'by_query_type': type_stats
        }
    
    def _calculate_performance_health(self) -> Dict:
        """
        Calculate overall performance health score.
        
        Returns:
            Dictionary with health score and status
        """
        checks = self.metrics.get('duplicate_checks', [])
        
        if not checks:
            return {
                'score': 100,
                'status': 'healthy',
                'message': 'No data collected yet'
            }
        
        # Calculate health factors
        factors = []
        
        # Factor 1: Query performance (40% weight)
        threshold_exceeded_rate = sum(1 for c in checks if c['threshold_exceeded']) / len(checks)
        query_health = max(0, 100 - (threshold_exceeded_rate * 100))
        factors.append(('query_performance', query_health, 0.4))
        
        # Factor 2: Error rate (30% weight)
        error_rate = sum(1 for c in checks if c['error']) / len(checks)
        error_health = max(0, 100 - (error_rate * 100))
        factors.append(('error_rate', error_health, 0.3))
        
        # Factor 3: Cache efficiency (20% weight)
        cache_hits = sum(1 for c in checks if c['cache_hit'])
        cache_rate = cache_hits / len(checks)
        cache_health = (cache_rate / self.cache_hit_target) * 100
        cache_health = min(100, cache_health)  # Cap at 100
        factors.append(('cache_efficiency', cache_health, 0.2))
        
        # Factor 4: Decision logging success (10% weight)
        logs = self.metrics.get('decision_logs', [])
        if logs:
            log_success_rate = sum(1 for l in logs if l['success']) / len(logs)
            log_health = log_success_rate * 100
        else:
            log_health = 100  # No failures if no logs
        factors.append(('decision_logging', log_health, 0.1))
        
        # Calculate weighted score
        total_score = sum(score * weight for _, score, weight in factors)
        
        # Determine status
        if total_score >= 90:
            status = 'healthy'
        elif total_score >= 70:
            status = 'degraded'
        elif total_score >= 50:
            status = 'warning'
        else:
            status = 'critical'
        
        return {
            'score': round(total_score, 2),
            'status': status,
            'factors': {
                name: {'score': round(score, 2), 'weight': weight}
                for name, score, weight in factors
            },
            'recommendations': self._get_health_recommendations(factors)
        }
    
    def _get_health_recommendations(self, factors: List[Tuple[str, float, float]]) -> List[str]:
        """Generate recommendations based on health factors."""
        recommendations = []
        
        for name, score, _ in factors:
            if score < 70:
                if name == 'query_performance':
                    recommendations.append(
                        "Query performance is below target. Consider optimizing database indexes "
                        "or implementing query caching."
                    )
                elif name == 'error_rate':
                    recommendations.append(
                        "High error rate detected. Review error logs and implement additional "
                        "error handling or retry logic."
                    )
                elif name == 'cache_efficiency':
                    recommendations.append(
                        "Cache hit rate is below target. Review caching strategy and consider "
                        "increasing cache TTL or improving cache key design."
                    )
                elif name == 'decision_logging':
                    recommendations.append(
                        "Decision logging failures detected. Check database connectivity and "
                        "audit log table configuration."
                    )
        
        if not recommendations:
            recommendations.append("System is performing well. Continue monitoring.")
        
        return recommendations
    
    def export_metrics(self, filepath: str) -> bool:
        """
        Export metrics to JSON file for analysis.
        
        Args:
            filepath: Path to export file
            
        Returns:
            Boolean indicating success
        """
        try:
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'summary': self.get_summary_statistics(),
                'raw_metrics': dict(self.metrics)
            }
            
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"Metrics exported to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return False
    
    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        self.metrics.clear()
        self.aggregated_metrics.clear()
        self.start_time = datetime.now()
        logger.info("Metrics reset")


class PerformanceMonitor:
    """
    Performance monitoring decorator and utilities for duplicate detection.
    
    Provides decorators and context managers for automatic performance tracking.
    """
    
    def __init__(self, metrics_collector: DuplicateDetectionMetrics):
        self.metrics = metrics_collector
    
    def monitor_duplicate_check(self, func):
        """
        Decorator to monitor duplicate check operations.
        
        Usage:
            @monitor.monitor_duplicate_check
            def check_for_duplicates(...):
                ...
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            error = None
            duplicates_found = 0
            cache_hit = False
            
            try:
                result = func(*args, **kwargs)
                
                # Extract metrics from result
                if isinstance(result, list):
                    duplicates_found = len(result)
                elif isinstance(result, dict):
                    duplicates_found = result.get('duplicate_count', 0)
                    cache_hit = result.get('cache_hit', False)
                
                return result
                
            except Exception as e:
                error = str(e)
                raise
                
            finally:
                execution_time = time.time() - start_time
                self.metrics.record_duplicate_check(
                    execution_time=execution_time,
                    duplicates_found=duplicates_found,
                    cache_hit=cache_hit,
                    error=error
                )
        
        return wrapper
    
    def monitor_file_cleanup(self, func):
        """
        Decorator to monitor file cleanup operations.
        
        Usage:
            @monitor.monitor_file_cleanup
            def cleanup_uploaded_file(...):
                ...
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            error = None
            success = False
            file_size = None
            
            try:
                result = func(*args, **kwargs)
                success = bool(result)
                
                # Try to get file size if available
                if len(args) > 0 and hasattr(args[0], 'file_size'):
                    file_size = args[0].file_size
                
                return result
                
            except Exception as e:
                error = str(e)
                raise
                
            finally:
                execution_time = time.time() - start_time
                self.metrics.record_file_cleanup(
                    execution_time=execution_time,
                    success=success,
                    file_size_bytes=file_size,
                    error=error
                )
        
        return wrapper
    
    def monitor_decision_log(self, func):
        """
        Decorator to monitor decision logging operations.
        
        Usage:
            @monitor.monitor_decision_log
            def log_duplicate_decision(...):
                ...
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            error = None
            success = False
            decision = kwargs.get('decision', 'unknown')
            retry_count = 0
            
            try:
                result = func(*args, **kwargs)
                success = bool(result)
                
                # Extract retry count if available
                if isinstance(result, dict):
                    retry_count = result.get('retry_count', 0)
                
                return result
                
            except Exception as e:
                error = str(e)
                raise
                
            finally:
                execution_time = time.time() - start_time
                self.metrics.record_decision_log(
                    execution_time=execution_time,
                    decision=decision,
                    success=success,
                    retry_count=retry_count,
                    error=error
                )
        
        return wrapper
    
    def monitor_database_query(self, query_type: str):
        """
        Decorator factory to monitor database query operations.
        
        Usage:
            @monitor.monitor_database_query('duplicate_check')
            def execute_duplicate_query(...):
                ...
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                error = None
                rows_returned = 0
                cache_hit = False
                
                try:
                    result = func(*args, **kwargs)
                    
                    # Extract metrics from result
                    if isinstance(result, list):
                        rows_returned = len(result)
                    elif isinstance(result, dict):
                        rows_returned = result.get('row_count', 0)
                        cache_hit = result.get('cache_hit', False)
                    
                    return result
                    
                except Exception as e:
                    error = str(e)
                    raise
                    
                finally:
                    execution_time = time.time() - start_time
                    self.metrics.record_database_query(
                        query_type=query_type,
                        execution_time=execution_time,
                        rows_returned=rows_returned,
                        cache_hit=cache_hit,
                        error=error
                    )
            
            return wrapper
        return decorator


# Global metrics collector instance
_global_metrics = DuplicateDetectionMetrics()


def get_metrics_collector() -> DuplicateDetectionMetrics:
    """Get the global metrics collector instance."""
    return _global_metrics


def get_performance_monitor() -> PerformanceMonitor:
    """Get a performance monitor instance with the global metrics collector."""
    return PerformanceMonitor(_global_metrics)


def get_performance_summary() -> Dict:
    """Get current performance summary statistics."""
    return _global_metrics.get_summary_statistics()


def export_performance_metrics(filepath: str) -> bool:
    """Export performance metrics to file."""
    return _global_metrics.export_metrics(filepath)


def reset_performance_metrics() -> None:
    """Reset all performance metrics."""
    _global_metrics.reset_metrics()
