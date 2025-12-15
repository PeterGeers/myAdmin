import time
import tracemalloc
from functools import wraps
from datetime import datetime
import gc
import os
from flask import request
from database import DatabaseManager
from database_migrations import QueryOptimizer

class PerformanceProfiler:
    """Performance profiling and optimization utilities"""

    def __init__(self):
        self.query_optimizer = QueryOptimizer()
        self.performance_logs = []
        self.memory_snapshots = []

    def profile_function(self, func):
        """Decorator to profile function performance"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Start memory tracking
            tracemalloc.start()
            memory_before = tracemalloc.take_snapshot()

            # Start timing
            start_time = time.time()

            try:
                # Execute function
                result = func(*args, **kwargs)

                # End timing
                end_time = time.time()
                execution_time = end_time - start_time

                # End memory tracking
                memory_after = tracemalloc.take_snapshot()
                tracemalloc.stop()

                # Calculate memory usage
                memory_diff = self._calculate_memory_diff(memory_before, memory_after)

                # Log performance
                self._log_performance(
                    func.__name__,
                    execution_time,
                    memory_diff,
                    args,
                    kwargs
                )

                return result

            except Exception as e:
                # End timing on error
                end_time = time.time()
                execution_time = end_time - start_time
                tracemalloc.stop()

                # Log error
                self._log_performance(
                    func.__name__,
                    execution_time,
                    None,
                    args,
                    kwargs,
                    error=str(e)
                )
                raise

        return wrapper

    def _calculate_memory_diff(self, snapshot_before, snapshot_after):
        """Calculate memory difference between snapshots"""
        top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')

        total_memory_diff = 0
        memory_details = []

        for stat in top_stats[:10]:  # Top 10 memory changes
            memory_diff = stat.size_diff
            total_memory_diff += memory_diff
            memory_details.append({
                'filename': stat.traceback[0].filename,
                'lineno': stat.traceback[0].lineno,
                'size_diff': memory_diff,
                'block_count_diff': stat.count_diff
            })

        return {
            'total_diff_bytes': total_memory_diff,
            'total_diff_mb': total_memory_diff / (1024 * 1024),
            'details': memory_details
        }

    def _log_performance(self, function_name, execution_time, memory_diff, args, kwargs, error=None):
        """Log performance metrics"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'function': function_name,
            'execution_time_seconds': execution_time,
            'memory_diff': memory_diff,
            'args': str(args),
            'kwargs': str(kwargs),
            'error': error
        }

        self.performance_logs.append(log_entry)

        # Print summary
        print(f"Performance: {function_name} - {execution_time:.4f}s")
        if memory_diff:
            print(f"Memory: {memory_diff['total_diff_mb']:.2f} MB change")

    def get_performance_report(self):
        """Generate performance report"""
        if not self.performance_logs:
            return {"message": "No performance data available"}

        # Calculate statistics
        total_time = sum(log['execution_time_seconds'] for log in self.performance_logs)
        avg_time = total_time / len(self.performance_logs)
        max_time = max(log['execution_time_seconds'] for log in self.performance_logs)
        min_time = min(log['execution_time_seconds'] for log in self.performance_logs)

        # Group by function
        function_stats = {}
        for log in self.performance_logs:
            func_name = log['function']
            if func_name not in function_stats:
                function_stats[func_name] = {
                    'count': 0,
                    'total_time': 0,
                    'errors': 0
                }
            function_stats[func_name]['count'] += 1
            function_stats[func_name]['total_time'] += log['execution_time_seconds']
            if log['error']:
                function_stats[func_name]['errors'] += 1

        return {
            'summary': {
                'total_calls': len(self.performance_logs),
                'total_time_seconds': total_time,
                'average_time_seconds': avg_time,
                'max_time_seconds': max_time,
                'min_time_seconds': min_time
            },
            'by_function': function_stats,
            'logs': self.performance_logs[-50:]  # Last 50 logs
        }

    def detect_n_plus_1_queries(self, db_manager, query_patterns):
        """Detect potential N+1 query patterns"""
        n_plus_1_report = {
            'potential_issues': [],
            'analysis_date': datetime.now().isoformat()
        }

        for pattern in query_patterns:
            # Analyze the query pattern
            analysis = self.query_optimizer.analyze_query(pattern['query'])

            # Check for N+1 patterns
            if self._is_potential_n_plus_1(analysis):
                n_plus_1_report['potential_issues'].append({
                    'query_pattern': pattern['name'],
                    'query': pattern['query'],
                    'analysis': analysis,
                    'recommendation': self._get_n_plus_1_fix_recommendation(pattern)
                })

        return n_plus_1_report

    def _is_potential_n_plus_1(self, analysis):
        """Check if query analysis suggests N+1 pattern"""
        if not analysis.get('explain_result'):
            return False

        for row in analysis['explain_result']:
            # Look for queries that scan many rows without proper joins
            if row.get('rows') and row['rows'] > 100 and row.get('type') not in ['eq_ref', 'const']:
                return True

        return False

    def _get_n_plus_1_fix_recommendation(self, query_pattern):
        """Get recommendation for fixing N+1 query"""
        recommendations = []

        # Common N+1 patterns and fixes
        if 'WHERE id IN' in query_pattern['query'].upper():
            recommendations.append(
                "Consider using JOIN instead of multiple queries with IN clauses"
            )

        if 'SELECT * FROM' in query_pattern['query'].upper() and 'WHERE' in query_pattern['query'].upper():
            recommendations.append(
                "Use JOIN to fetch related data in a single query instead of multiple queries"
            )

        recommendations.append(
            "Implement batch loading with proper JOINs to reduce query count"
        )

        return recommendations

    def optimize_batch_processing(self, items, batch_size=100, process_func=None):
        """Optimize batch processing with proper batching"""
        if not process_func:
            raise ValueError("process_func must be provided")

        start_time = time.time()
        total_items = len(items)
        processed_items = 0
        results = []

        # Process in batches
        for i in range(0, total_items, batch_size):
            batch = items[i:i + batch_size]
            batch_results = process_func(batch)
            results.extend(batch_results)
            processed_items += len(batch)

            # Progress reporting
            progress = (processed_items / total_items) * 100
            print(f"Batch processing: {progress:.1f}% complete ({processed_items}/{total_items})")

        end_time = time.time()
        processing_time = end_time - start_time

        return {
            'results': results,
            'total_items': total_items,
            'processing_time_seconds': processing_time,
            'items_per_second': total_items / processing_time if processing_time > 0 else 0
        }

    def check_memory_leaks(self):
        """Check for memory leaks by taking snapshots"""
        # Take initial snapshot
        tracemalloc.start()
        snapshot1 = tracemalloc.take_snapshot()

        # Force garbage collection
        gc.collect()

        # Take second snapshot
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare snapshots
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')

        memory_leak_report = {
            'timestamp': datetime.now().isoformat(),
            'potential_leaks': [],
            'memory_usage_summary': self._get_memory_summary()
        }

        # Analyze top memory differences
        for stat in top_stats[:20]:  # Top 20 potential leaks
            if stat.size_diff > 100000:  # More than 100KB difference
                memory_leak_report['potential_leaks'].append({
                    'filename': stat.traceback[0].filename,
                    'lineno': stat.traceback[0].lineno,
                    'size_diff_bytes': stat.size_diff,
                    'size_diff_mb': stat.size_diff / (1024 * 1024),
                    'block_count_diff': stat.count_diff,
                    'traceback': self._format_traceback(stat.traceback)
                })

        return memory_leak_report

    def _get_memory_summary(self):
        """Get current memory usage summary"""
        process = psutil.Process(os.getpid())
        return {
            'rss_mb': process.memory_info().rss / (1024 * 1024),
            'vms_mb': process.memory_info().vms / (1024 * 1024),
            'percent': process.memory_percent()
        }

    def _format_traceback(self, traceback):
        """Format traceback for reporting"""
        return "\n".join([
            f"  File: {frame.filename}:{frame.lineno}"
            for frame in traceback
        ])

    def implement_caching_strategies(self, cache_config):
        """Implement various caching strategies"""
        caching_strategies = {
            'query_caching': cache_config.get('query_caching', True),
            'result_caching': cache_config.get('result_caching', True),
            'ttl_seconds': cache_config.get('ttl_seconds', 300)
        }

        # Configure query optimizer caching
        if caching_strategies['query_caching']:
            self.query_optimizer.cache_ttl = caching_strategies['ttl_seconds']

        return {
            'status': 'Caching strategies implemented',
            'config': caching_strategies,
            'query_cache_ttl': self.query_optimizer.cache_ttl
        }

    def analyze_performance_bottlenecks(self, performance_data):
        """Analyze performance data for bottlenecks"""
        if not performance_data or not performance_data.get('logs'):
            return {"message": "No performance data to analyze"}

        bottlenecks = []
        slow_threshold = 1.0  # 1 second threshold for "slow" queries

        for log in performance_data['logs']:
            if log['execution_time_seconds'] > slow_threshold:
                bottleneck = {
                    'function': log['function'],
                    'execution_time': log['execution_time_seconds'],
                    'memory_usage': log.get('memory_diff', {}).get('total_diff_mb', 0),
                    'args': log['args'],
                    'recommendations': []
                }

                # Add recommendations based on function name
                if 'query' in log['function'].lower():
                    bottleneck['recommendations'].append(
                        "Consider adding database indexes for this query"
                    )
                    bottleneck['recommendations'].append(
                        "Review query structure for optimization opportunities"
                    )

                if 'process' in log['function'].lower() or 'parse' in log['function'].lower():
                    bottleneck['recommendations'].append(
                        "Check for inefficient loops or algorithms"
                    )
                    bottleneck['recommendations'].append(
                        "Consider batch processing for large datasets"
                    )

                bottlenecks.append(bottleneck)

        return {
            'bottlenecks_found': len(bottlenecks),
            'slow_threshold_seconds': slow_threshold,
            'bottlenecks': bottlenecks,
            'analysis_date': datetime.now().isoformat()
        }

# Performance monitoring middleware
def performance_middleware(app):
    """Add performance monitoring to Flask app"""
    profiler = PerformanceProfiler()

    @app.before_request
    def start_performance_monitoring():
        # Start timing
        request.start_time = time.time()

        # Start memory tracking for API requests
        if request.path.startswith('/api/'):
            tracemalloc.start()

    @app.after_request
    def log_performance(response):
        # Calculate execution time
        if hasattr(request, 'start_time'):
            execution_time = time.time() - request.start_time
            response.headers['X-Execution-Time'] = f"{execution_time:.4f}s"

        # Log memory usage for API requests
        if request.path.startswith('/api/') and hasattr(tracemalloc, 'get_traced_memory'):
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            response.headers['X-Memory-Usage'] = f"{current / 1024:.2f} KB"
            response.headers['X-Memory-Peak'] = f"{peak / 1024:.2f} KB"

        return response

    # Add profiler to app context
    app.perf_profiler = profiler

    return profiler

# Batch processing utilities
class BatchProcessor:
    """Utilities for optimized batch processing"""

    def __init__(self, batch_size=100):
        self.batch_size = batch_size
        self.profiler = PerformanceProfiler()

    def process_in_batches(self, items, process_func, progress_callback=None):
        """Process items in optimized batches"""
        return self.profiler.optimize_batch_processing(
            items,
            self.batch_size,
            process_func
        )

    def find_optimal_batch_size(self, items, process_func, test_sizes=[50, 100, 200, 500]):
        """Find optimal batch size through testing"""
        batch_performance = []

        for size in test_sizes:
            start_time = time.time()
            result = self.process_in_batches(items[:size*3], process_func, size)  # Test with 3 batches
            end_time = time.time()

            batch_performance.append({
                'batch_size': size,
                'processing_time': end_time - start_time,
                'items_per_second': (size * 3) / (end_time - start_time) if (end_time - start_time) > 0 else 0
            })

        # Find optimal size (best items per second)
        optimal = max(batch_performance, key=lambda x: x['items_per_second'])

        return {
            'optimal_batch_size': optimal['batch_size'],
            'performance_by_size': batch_performance,
            'analysis_date': datetime.now().isoformat()
        }

    def parallel_batch_processing(self, items, process_func, max_workers=4):
        """Process batches in parallel using threading"""
        from concurrent.futures import ThreadPoolExecutor
        import math

        batch_size = self.batch_size
        total_items = len(items)
        num_batches = math.ceil(total_items / batch_size)

        results = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i in range(num_batches):
                batch = items[i*batch_size:(i+1)*batch_size]
                futures.append(executor.submit(process_func, batch))

            for future in futures:
                results.extend(future.result())

        end_time = time.time()

        return {
            'results': results,
            'total_items': total_items,
            'processing_time_seconds': end_time - start_time,
            'items_per_second': total_items / (end_time - start_time) if (end_time - start_time) > 0 else 0,
            'workers_used': max_workers
        }

# Memory management utilities
class MemoryManager:
    """Memory management and leak detection"""

    def __init__(self):
        self.memory_snapshots = []
        self.leak_threshold_mb = 10  # 10MB threshold for leak detection

    def take_memory_snapshot(self, label="manual"):
        """Take a memory snapshot with label"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()

            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'label': label,
                'rss_mb': mem_info.rss / (1024 * 1024),
                'vms_mb': mem_info.vms / (1024 * 1024),
                'percent': process.memory_percent(),
                'threads': process.num_threads()
            }

            self.memory_snapshots.append(snapshot)
            return snapshot

        except ImportError:
            return {
                'error': 'psutil not available for detailed memory monitoring',
                'timestamp': datetime.now().isoformat(),
                'label': label
            }

    def detect_memory_leaks(self, min_snapshots=3):
        """Detect memory leaks by comparing snapshots"""
        if len(self.memory_snapshots) < min_snapshots:
            return {"message": f"Need at least {min_snapshots} snapshots for leak detection"}

        leak_report = {
            'snapshots_analyzed': len(self.memory_snapshots),
            'potential_leaks': [],
            'memory_trend': []
        }

        # Calculate memory trend
        for i, snapshot in enumerate(self.memory_snapshots):
            if i > 0:
                prev_snapshot = self.memory_snapshots[i-1]
                rss_diff = snapshot['rss_mb'] - prev_snapshot['rss_mb']
                leak_report['memory_trend'].append({
                    'from': prev_snapshot['timestamp'],
                    'to': snapshot['timestamp'],
                    'rss_diff_mb': rss_diff,
                    'rss_diff_percent': (rss_diff / prev_snapshot['rss_mb']) * 100 if prev_snapshot['rss_mb'] > 0 else 0
                })

                # Check for potential leaks
                if rss_diff > self.leak_threshold_mb:
                    leak_report['potential_leaks'].append({
                        'timestamp': snapshot['timestamp'],
                        'label': snapshot['label'],
                        'rss_increase_mb': rss_diff,
                        'from_rss_mb': prev_snapshot['rss_mb'],
                        'to_rss_mb': snapshot['rss_mb'],
                        'severity': 'high' if rss_diff > self.leak_threshold_mb * 2 else 'medium'
                    })

        return leak_report

    def force_garbage_collection(self):
        """Force garbage collection and report results"""
        collected = gc.collect()

        return {
            'timestamp': datetime.now().isoformat(),
            'objects_collected': collected,
            'garbage_count': len(gc.garbage),
            'generation_counts': [len(gc.get_objects(gen)) for gen in range(gc.get_threshold()[0])]
        }

    def get_memory_usage_report(self):
        """Get current memory usage report"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()

            return {
                'timestamp': datetime.now().isoformat(),
                'process_id': os.getpid(),
                'rss_mb': mem_info.rss / (1024 * 1024),
                'vms_mb': mem_info.vms / (1024 * 1024),
                'percent': process.memory_percent(),
                'threads': process.num_threads(),
                'open_files': len(process.open_files()) if hasattr(process, 'open_files') else 'N/A',
                'connections': len(process.connections()) if hasattr(process, 'connections') else 'N/A'
            }

        except ImportError:
            return {
                'error': 'psutil not available for detailed memory monitoring',
                'timestamp': datetime.now().isoformat()
            }

# Performance optimization API endpoints
def register_performance_endpoints(app):
    """Register performance monitoring and optimization endpoints"""

    profiler = PerformanceProfiler()
    memory_manager = MemoryManager()

    @app.route('/api/performance/status', methods=['GET'])
    def performance_status():
        """Get current performance status"""
        report = profiler.get_performance_report()
        memory_report = memory_manager.get_memory_usage_report()

        return {
            'success': True,
            'performance': report,
            'memory': memory_report,
            'timestamp': datetime.now().isoformat()
        }

    @app.route('/api/performance/analyze', methods=['POST'])
    def analyze_performance():
        """Analyze performance data"""
        data = request.get_json()
        analysis = profiler.analyze_performance_bottlenecks(data)

        return {
            'success': True,
            'analysis': analysis
        }

    @app.route('/api/performance/memory-check', methods=['GET'])
    def memory_check():
        """Check for memory leaks"""
        leak_report = profiler.check_memory_leaks()

        return {
            'success': True,
            'memory_report': leak_report
        }

    @app.route('/api/performance/optimize', methods=['POST'])
    def optimize_performance():
        """Run performance optimization"""
        data = request.get_json()
        cache_config = data.get('caching', {})

        # Implement caching strategies
        caching_result = profiler.implement_caching_strategies(cache_config)

        # Check for N+1 queries
        query_patterns = data.get('query_patterns', [])
        n_plus_1_report = profiler.detect_n_plus_1_queries(app.db, query_patterns)

        return {
            'success': True,
            'caching': caching_result,
            'n_plus_1_analysis': n_plus_1_report,
            'recommendations': self._get_performance_recommendations()
        }

    def _get_performance_recommendations():
        """Get general performance recommendations"""
        return [
            "Implement query caching for frequent database queries",
            "Use batch processing for large datasets",
            "Optimize database indexes for common query patterns",
            "Monitor memory usage regularly to detect leaks",
            "Profile critical functions to identify bottlenecks",
            "Consider using connection pooling for database connections",
            "Implement proper pagination for API endpoints",
            "Use asynchronous processing for I/O-bound operations"
        ]
