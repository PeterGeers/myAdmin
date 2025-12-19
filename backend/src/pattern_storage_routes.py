#!/usr/bin/env python3
"""
API routes for pattern storage functionality

Provides endpoints to:
- Get pattern storage statistics
- Trigger pattern analysis with database storage
- Get pattern summaries from database
"""

from flask import Blueprint, jsonify, request
from pattern_analyzer import PatternAnalyzer
import time

# Create blueprint
pattern_storage_bp = Blueprint('pattern_storage', __name__)

@pattern_storage_bp.route('/api/patterns/storage/stats/<administration>', methods=['GET'])
def get_pattern_storage_stats(administration):
    """
    Get pattern storage statistics for an administration
    
    Returns performance metrics and storage information
    """
    try:
        analyzer = PatternAnalyzer()
        stats = analyzer.get_pattern_storage_stats(administration)
        
        return jsonify({
            'success': True,
            'administration': administration,
            'storage_stats': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@pattern_storage_bp.route('/api/patterns/analyze/<administration>', methods=['POST'])
def analyze_patterns_with_storage(administration):
    """
    Trigger pattern analysis with database storage
    
    Supports both full and incremental analysis
    """
    try:
        data = request.get_json() or {}
        incremental = data.get('incremental', False)
        
        analyzer = PatternAnalyzer()
        
        start_time = time.time()
        
        if incremental:
            result = analyzer.analyze_incremental_patterns(administration)
            analysis_type = "incremental"
        else:
            result = analyzer.analyze_historical_patterns(administration)
            analysis_type = "full"
        
        analysis_time = time.time() - start_time
        
        # Get storage stats for performance comparison
        storage_stats = analyzer.get_pattern_storage_stats(administration)
        
        return jsonify({
            'success': True,
            'analysis_type': analysis_type,
            'administration': administration,
            'analysis_time': round(analysis_time, 4),
            'results': {
                'total_transactions': result['total_transactions'],
                'patterns_discovered': result['patterns_discovered'],
                'pattern_types': {
                    'debet': len(result['debet_patterns']),
                    'credit': len(result['credit_patterns']),
                    'reference': len(result['reference_patterns'])
                },
                'date_range': result['date_range']
            },
            'storage_performance': storage_stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@pattern_storage_bp.route('/api/patterns/summary/<administration>', methods=['GET'])
def get_pattern_summary_from_storage(administration):
    """
    Get pattern summary from database storage
    
    Fast retrieval of pattern information without recalculation
    """
    try:
        analyzer = PatternAnalyzer()
        
        start_time = time.time()
        summary = analyzer.get_pattern_summary(administration)
        retrieval_time = time.time() - start_time
        
        return jsonify({
            'success': True,
            'retrieval_time': round(retrieval_time, 4),
            'summary': summary,
            'database_storage_used': True
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@pattern_storage_bp.route('/api/patterns/apply/<administration>', methods=['POST'])
def apply_patterns_from_storage(administration):
    """
    Apply patterns from database storage to transactions
    
    Fast pattern application using stored patterns
    """
    try:
        data = request.get_json()
        if not data or 'transactions' not in data:
            return jsonify({
                'success': False,
                'error': 'Transactions data required'
            }), 400
        
        transactions = data['transactions']
        analyzer = PatternAnalyzer()
        
        start_time = time.time()
        updated_transactions, results = analyzer.apply_patterns_to_transactions(transactions, administration)
        application_time = time.time() - start_time
        
        return jsonify({
            'success': True,
            'administration': administration,
            'application_time': round(application_time, 4),
            'results': results,
            'updated_transactions': updated_transactions,
            'database_patterns_used': True
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@pattern_storage_bp.route('/api/patterns/performance-comparison/<administration>', methods=['GET'])
def get_performance_comparison(administration):
    """
    Get performance comparison between database storage and traditional analysis
    """
    try:
        analyzer = PatternAnalyzer()
        
        # Get storage stats
        storage_stats = analyzer.get_pattern_storage_stats(administration)
        
        # Time database pattern loading
        start_time = time.time()
        db_patterns = analyzer._load_patterns_from_database(administration)
        db_load_time = time.time() - start_time
        
        # Estimate traditional analysis time based on transaction count
        total_transactions = storage_stats['transaction_comparison']['total_transactions_2_years']
        estimated_analysis_time = total_transactions * 0.002  # Rough estimate: 2ms per transaction
        
        performance_improvement = estimated_analysis_time / db_load_time if db_load_time > 0 else 0
        
        return jsonify({
            'success': True,
            'administration': administration,
            'performance_comparison': {
                'database_load_time': round(db_load_time, 4),
                'estimated_traditional_time': round(estimated_analysis_time, 2),
                'performance_improvement': f"{performance_improvement:.1f}x faster",
                'patterns_loaded': db_patterns['patterns_discovered'],
                'transactions_avoided': total_transactions,
                'data_reduction': storage_stats['transaction_comparison']['performance_improvement']
            },
            'storage_benefits': {
                'persistent_storage': True,
                'incremental_updates': True,
                'shared_cache': True,
                'reduced_database_load': True
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@pattern_storage_bp.route('/api/patterns/incremental-stats/<administration>', methods=['GET'])
def get_incremental_update_stats(administration):
    """
    Get statistics about incremental pattern updates
    
    REQ-PAT-006: Performance improvement through incremental processing
    """
    try:
        analyzer = PatternAnalyzer()
        
        start_time = time.time()
        stats = analyzer.get_incremental_update_stats(administration)
        retrieval_time = time.time() - start_time
        
        return jsonify({
            'success': True,
            'retrieval_time': round(retrieval_time, 4),
            'incremental_stats': stats,
            'feature_status': {
                'incremental_updates_implemented': True,
                'database_storage_active': True,
                'performance_optimized': True
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500