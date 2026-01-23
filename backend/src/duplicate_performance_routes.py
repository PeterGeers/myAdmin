"""
API Routes for Duplicate Detection Performance Monitoring

Provides REST API endpoints for monitoring and optimizing duplicate detection performance.

Requirements: 5.5, 6.4
"""

from flask import Blueprint, jsonify, request
import logging
from datetime import datetime
from duplicate_performance_monitor import (
    get_metrics_collector,
    get_performance_summary,
    export_performance_metrics,
    reset_performance_metrics
)
from duplicate_query_optimizer import get_query_optimizer
from database import DatabaseManager
from auth.cognito_utils import cognito_required

logger = logging.getLogger(__name__)

# Create Blueprint for performance routes
duplicate_performance_bp = Blueprint('duplicate_performance', __name__)


@duplicate_performance_bp.route('/api/duplicate-detection/performance/status', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_performance_status(user_email, user_roles):
    """
    Get current performance status for duplicate detection system.
    
    Returns:
        JSON response with performance metrics and health status
    """
    try:
        summary = get_performance_summary()
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'performance': summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting performance status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve performance status'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/metrics', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_detailed_metrics(user_email, user_roles):
    """
    Get detailed performance metrics for duplicate detection.
    
    Query Parameters:
        - metric_type: Type of metrics to retrieve (checks, cleanups, logs, queries, all)
        - time_range: Time range in hours (default: 24)
    
    Returns:
        JSON response with detailed metrics
    """
    try:
        metric_type = request.args.get('metric_type', 'all')
        time_range = int(request.args.get('time_range', 24))
        
        metrics_collector = get_metrics_collector()
        summary = metrics_collector.get_summary_statistics()
        
        # Filter metrics based on type
        if metric_type != 'all':
            filtered_summary = {
                'collection_period': summary['collection_period'],
                metric_type: summary.get(metric_type, {}),
                'performance_health': summary['performance_health']
            }
        else:
            filtered_summary = summary
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'metric_type': metric_type,
            'time_range_hours': time_range,
            'metrics': filtered_summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting detailed metrics: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve detailed metrics'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/health', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_health_status(user_email, user_roles):
    """
    Get health status and recommendations for duplicate detection system.
    
    Returns:
        JSON response with health score and recommendations
    """
    try:
        summary = get_performance_summary()
        health = summary.get('performance_health', {})
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'health': health
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting health status: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve health status'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/cache-stats', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_cache_statistics(user_email, user_roles):
    """
    Get query cache statistics.
    
    Returns:
        JSON response with cache performance metrics
    """
    try:
        db = DatabaseManager()
        optimizer = get_query_optimizer(db)
        
        query_stats = optimizer.get_query_statistics()
        cache_stats = query_stats['cache_stats']
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'cache_stats': cache_stats,
            'cache_efficiency': query_stats['cache_efficiency'],
            'recommendations': optimizer.get_optimization_recommendations()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting cache statistics: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve cache statistics'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/query-stats', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_query_statistics(user_email, user_roles):
    """
    Get database query statistics for duplicate detection.
    
    Returns:
        JSON response with query performance metrics
    """
    try:
        db = DatabaseManager()
        optimizer = get_query_optimizer(db)
        
        query_stats = optimizer.get_query_statistics()
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'query_statistics': query_stats
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting query statistics: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve query statistics'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/optimize', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def optimize_performance(user_email, user_roles):
    """
    Run performance optimization operations.
    
    Request Body:
        - cleanup_cache: Boolean to cleanup expired cache entries
        - reset_stats: Boolean to reset statistics
        - analyze_queries: Boolean to analyze query performance
    
    Returns:
        JSON response with optimization results
    """
    try:
        data = request.get_json() or {}
        
        cleanup_cache = data.get('cleanup_cache', False)
        reset_stats = data.get('reset_stats', False)
        analyze_queries = data.get('analyze_queries', False)
        
        results = {
            'operations_performed': []
        }
        
        db = DatabaseManager()
        optimizer = get_query_optimizer(db)
        
        # Cleanup expired cache entries
        if cleanup_cache:
            cleaned = optimizer.cleanup_cache()
            results['cache_cleanup'] = {
                'entries_removed': cleaned,
                'status': 'completed'
            }
            results['operations_performed'].append('cache_cleanup')
        
        # Reset statistics
        if reset_stats:
            optimizer.reset_statistics()
            reset_performance_metrics()
            results['stats_reset'] = {
                'status': 'completed'
            }
            results['operations_performed'].append('stats_reset')
        
        # Analyze query performance
        if analyze_queries:
            # Analyze the main duplicate check query
            sample_query = """
                SELECT * FROM mutaties
                WHERE ReferenceNumber = %s
                AND TransactionDate = %s
                AND ABS(TransactionAmount - %s) < 0.01
                AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
                ORDER BY ID DESC
            """
            
            analysis = optimizer.analyze_query_performance(
                sample_query,
                ('SampleRef', '2024-01-01', 100.00)
            )
            
            results['query_analysis'] = analysis
            results['operations_performed'].append('query_analysis')
        
        # Get recommendations
        results['recommendations'] = optimizer.get_optimization_recommendations()
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'optimization_results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Error optimizing performance: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to optimize performance'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/export', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def export_metrics(user_email, user_roles):
    """
    Export performance metrics to file.
    
    Request Body:
        - filepath: Path to export file (optional, defaults to timestamped file)
    
    Returns:
        JSON response with export status
    """
    try:
        data = request.get_json() or {}
        
        # Generate default filepath if not provided
        filepath = data.get('filepath')
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f'logs/duplicate_detection_metrics_{timestamp}.json'
        
        success = export_performance_metrics(filepath)
        
        if success:
            return jsonify({
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'filepath': filepath,
                'message': 'Metrics exported successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to export metrics'
            }), 500
        
    except Exception as e:
        logger.error(f"Error exporting metrics: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to export metrics'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/recommendations', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_recommendations(user_email, user_roles):
    """
    Get performance optimization recommendations.
    
    Returns:
        JSON response with recommendations
    """
    try:
        db = DatabaseManager()
        optimizer = get_query_optimizer(db)
        
        recommendations = optimizer.get_optimization_recommendations()
        summary = get_performance_summary()
        health = summary.get('performance_health', {})
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'recommendations': {
                'query_optimization': recommendations,
                'health_recommendations': health.get('recommendations', []),
                'priority': 'high' if health.get('score', 100) < 70 else 'medium'
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to retrieve recommendations'
        }), 500


@duplicate_performance_bp.route('/api/duplicate-detection/performance/test', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def test_performance(user_email, user_roles):
    """
    Run performance test for duplicate detection.
    
    Request Body:
        - test_count: Number of test queries to run (default: 10)
        - use_cache: Whether to use cache (default: true)
    
    Returns:
        JSON response with test results
    """
    try:
        data = request.get_json() or {}
        
        test_count = data.get('test_count', 10)
        use_cache = data.get('use_cache', True)
        
        db = DatabaseManager()
        optimizer = get_query_optimizer(db)
        
        # Run test queries
        test_results = []
        total_time = 0
        cache_hits = 0
        
        # Sample test data
        test_data = [
            ('TestRef1', '2024-01-01', 100.00),
            ('TestRef2', '2024-01-15', 250.50),
            ('TestRef3', '2024-02-01', 75.25),
        ]
        
        for i in range(test_count):
            test_item = test_data[i % len(test_data)]
            ref, date, amount = test_item
            
            results, perf_info = optimizer.check_duplicates_optimized(
                reference_number=ref,
                transaction_date=date,
                transaction_amount=amount,
                use_cache=use_cache
            )
            
            total_time += perf_info['execution_time']
            if perf_info['cache_hit']:
                cache_hits += 1
            
            test_results.append({
                'test_number': i + 1,
                'reference_number': ref,
                'execution_time': perf_info['execution_time'],
                'cache_hit': perf_info['cache_hit'],
                'rows_returned': perf_info['rows_returned']
            })
        
        avg_time = total_time / test_count if test_count > 0 else 0
        cache_hit_rate = (cache_hits / test_count * 100) if test_count > 0 else 0
        
        # Performance assessment
        performance_grade = 'excellent' if avg_time < 0.5 else \
                          'good' if avg_time < 1.0 else \
                          'acceptable' if avg_time < 2.0 else \
                          'poor'
        
        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'test_summary': {
                'total_tests': test_count,
                'total_time': total_time,
                'average_time': avg_time,
                'cache_hit_rate': cache_hit_rate,
                'performance_grade': performance_grade,
                'meets_requirement': avg_time < 2.0  # Requirement 5.5: 2 second threshold
            },
            'test_results': test_results
        }), 200
        
    except Exception as e:
        logger.error(f"Error running performance test: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to run performance test'
        }), 500


def register_performance_routes(app):
    """
    Register performance monitoring routes with Flask app.
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(duplicate_performance_bp)
    logger.info("Duplicate detection performance routes registered")
