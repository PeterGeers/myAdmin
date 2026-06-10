#!/usr/bin/env python3
"""
Pattern Storage Module for Banking Transactions

Extracted from pattern_analyzer.py — contains database storage/loading logic:
- Store verb patterns to database
- Load patterns from database
- Check if patterns need refresh
- Build cache keys
- Get cache performance stats
- Get pattern storage stats

These functions manage persistence of patterns.
They do NOT detect patterns or score/rank them.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from database import DatabaseManager
from dialect_helpers import dialect
from pattern_cache import get_pattern_cache
from pattern_scoring import calculate_statistics_from_db_patterns


def build_cache_key(
    administration: str,
    reference_number: Optional[str] = None,
    debet_account: Optional[str] = None,
    credit_account: Optional[str] = None
) -> str:
    """Build cache key for filtered patterns"""
    key_parts = [administration]
    if reference_number:
        key_parts.append(f"ref:{reference_number}")
    if debet_account:
        key_parts.append(f"deb:{debet_account}")
    if credit_account:
        key_parts.append(f"cred:{credit_account}")
    return "_".join(key_parts)


def store_verb_patterns_to_database(
    db: DatabaseManager,
    administration: str,
    verb_patterns: Dict,
    analysis_metadata: Dict,
    is_incremental: bool = False
) -> None:
    """
    Store discovered verb patterns in unified database table

    REQ-PAT-005: Store discovered patterns in optimized database structure
    REQ-PAT-006: Support incremental pattern updates
    Uses single table for ReferenceNumber, Debet, and Credit predictions

    Args:
        db: Database manager instance
        administration: The administration to store patterns for
        verb_patterns: Dictionary of discovered patterns
        analysis_metadata: Metadata about the analysis
        is_incremental: Whether this is an incremental update (accumulates transaction count)
    """
    print(f"💾 Storing {len(verb_patterns)} verb patterns to database...")

    try:
        # Store verb patterns (unified approach for all predictions)
        for pattern_key, pattern in verb_patterns.items():
            db.execute_query("""
                INSERT INTO pattern_verb_patterns 
                (administration, bank_account, verb, verb_company, verb_reference, is_compound,
                 reference_number, debet_account, credit_account, occurrences, confidence, 
                 last_seen, sample_description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                verb_company = VALUES(verb_company),
                verb_reference = VALUES(verb_reference),
                is_compound = VALUES(is_compound),
                reference_number = VALUES(reference_number),
                debet_account = VALUES(debet_account),
                credit_account = VALUES(credit_account),
                occurrences = occurrences + VALUES(occurrences),
                confidence = VALUES(confidence),
                last_seen = VALUES(last_seen),
                sample_description = VALUES(sample_description),
                updated_at = CURRENT_TIMESTAMP
            """, (
                pattern.get('administration'), pattern.get('bank_account'),
                pattern.get('verb'), pattern.get('verb_company'), pattern.get('verb_reference'),
                pattern.get('is_compound', False), pattern.get('reference_number'),
                pattern.get('debet_account'), pattern.get('credit_account'),
                pattern.get('occurrences', 1), pattern.get('confidence', 1.0),
                pattern.get('last_seen'), pattern.get('sample_description')
            ), fetch=False, commit=True)

        # Get current pattern count from database for accurate reporting
        pattern_count_result = db.execute_query("""
            SELECT COUNT(*) as count FROM pattern_verb_patterns 
            WHERE administration = %s
        """, (administration,))
        total_patterns = pattern_count_result[0]['count'] if pattern_count_result else len(verb_patterns)

        # Store analysis metadata
        if is_incremental:
            # For incremental updates, accumulate transaction count
            db.execute_query(f"""
                INSERT INTO pattern_analysis_metadata 
                (administration, last_analysis_date, transactions_analyzed, patterns_discovered,
                 date_range_from, date_range_to)
                VALUES (%s, {dialect.current_timestamp()}, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                last_analysis_date = {dialect.current_timestamp()},
                transactions_analyzed = transactions_analyzed + VALUES(transactions_analyzed),
                patterns_discovered = %s,
                date_range_to = VALUES(date_range_to),
                updated_at = CURRENT_TIMESTAMP
            """, (
                administration, analysis_metadata.get('total_transactions', 0),
                total_patterns,
                analysis_metadata.get('date_range', {}).get('from'),
                analysis_metadata.get('date_range', {}).get('to'),
                total_patterns
            ), fetch=False, commit=True)
        else:
            # For full analysis, replace transaction count
            db.execute_query(f"""
                INSERT INTO pattern_analysis_metadata 
                (administration, last_analysis_date, transactions_analyzed, patterns_discovered,
                 date_range_from, date_range_to)
                VALUES (%s, {dialect.current_timestamp()}, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                last_analysis_date = {dialect.current_timestamp()},
                transactions_analyzed = VALUES(transactions_analyzed),
                patterns_discovered = VALUES(patterns_discovered),
                date_range_from = VALUES(date_range_from),
                date_range_to = VALUES(date_range_to),
                updated_at = CURRENT_TIMESTAMP
            """, (
                administration, analysis_metadata.get('total_transactions', 0),
                len(verb_patterns),
                analysis_metadata.get('date_range', {}).get('from'),
                analysis_metadata.get('date_range', {}).get('to')
            ), fetch=False, commit=True)

        print(f"✅ Verb patterns stored successfully in database")

    except Exception as e:
        print(f"❌ Error storing verb patterns to database: {e}")
        raise


def load_patterns_from_database(db: DatabaseManager, administration: str) -> Dict[str, Any]:
    """
    Load patterns from database storage using unified pattern_verb_patterns table

    REQ-PAT-005: Store discovered patterns in optimized database structure
    REQ-PAT-006: Implement pattern caching for performance
    """
    print(f"📖 Loading patterns from database for {administration}...")

    try:
        # Load verb patterns (unified approach - contains all prediction data)
        verb_results = db.execute_query("""
            SELECT administration, bank_account, verb, verb_company, verb_reference, 
                   is_compound, reference_number, debet_account, credit_account, 
                   occurrences, confidence, last_seen, sample_description
            FROM pattern_verb_patterns 
            WHERE administration = %s
            ORDER BY last_seen DESC, occurrences DESC
        """, (administration,))

        reference_patterns = {}
        for row in verb_results:
            pattern_key = f"{row['administration']}_{row['bank_account']}_{row['verb']}"
            reference_patterns[pattern_key] = {
                'administration': row['administration'],
                'bank_account': row['bank_account'],
                'verb': row['verb'],
                'verb_company': row['verb_company'],
                'verb_reference': row['verb_reference'],
                'is_compound': bool(row['is_compound']),
                'reference_number': row['reference_number'],
                'debet_account': row['debet_account'],
                'credit_account': row['credit_account'],
                'occurrences': row['occurrences'],
                'confidence': float(row['confidence']) if row['confidence'] else 1.0,
                'last_seen': row['last_seen'],
                'sample_description': row['sample_description']
            }

        # Load metadata
        metadata_results = db.execute_query("""
            SELECT last_analysis_date, transactions_analyzed, patterns_discovered,
                   date_range_from, date_range_to
            FROM pattern_analysis_metadata 
            WHERE administration = %s
        """, (administration,))

        metadata = {}
        if metadata_results:
            meta = metadata_results[0]
            metadata = {
                'analysis_date': meta['last_analysis_date'].isoformat() if meta['last_analysis_date'] else None,
                'total_transactions': meta['transactions_analyzed'] or 0,
                'patterns_discovered': meta['patterns_discovered'] or 0,
                'date_range': {
                    'from': meta['date_range_from'].strftime('%Y-%m-%d') if meta['date_range_from'] else None,
                    'to': meta['date_range_to'].strftime('%Y-%m-%d') if meta['date_range_to'] else None
                }
            }

        result = {
            'debet_patterns': {},  # Empty - using unified verb patterns
            'credit_patterns': {},  # Empty - using unified verb patterns
            'reference_patterns': reference_patterns,
            'total_transactions': metadata.get('total_transactions', 0),
            'patterns_discovered': len(reference_patterns),
            'analysis_date': metadata.get('analysis_date'),
            'date_range': metadata.get('date_range', {}),
            'statistics': calculate_statistics_from_db_patterns({}, {}, reference_patterns)
        }

        print(f"✅ Loaded {result['patterns_discovered']} patterns from database")
        return result

    except Exception as e:
        print(f"❌ Error loading patterns from database: {e}")
        # Fallback to empty patterns
        return {
            'debet_patterns': {},
            'credit_patterns': {},
            'reference_patterns': {},
            'total_transactions': 0,
            'patterns_discovered': 0,
            'statistics': {}
        }


def should_refresh_patterns(db: DatabaseManager, administration: str) -> bool:
    """
    Check if patterns should be refreshed based on last analysis date

    REQ-PAT-006: Implement incremental pattern updates
    """
    try:
        metadata = db.execute_query("""
            SELECT last_analysis_date FROM pattern_analysis_metadata 
            WHERE administration = %s
        """, (administration,))

        if not metadata:
            return True  # No previous analysis, need to analyze

        last_analysis = metadata[0]['last_analysis_date']
        if not last_analysis:
            return True

        # Refresh if last analysis was more than 24 hours ago
        return datetime.now() - last_analysis > timedelta(hours=24)

    except Exception as e:
        print(f"Warning: Could not check pattern refresh status: {e}")
        return True  # Default to refresh on error


def get_cache_performance_stats(
    db: DatabaseManager,
    administration: str,
    persistent_cache
) -> Dict[str, Any]:
    """
    Get comprehensive cache performance statistics

    REQ-PAT-006: Persistent Pattern Cache performance metrics
    """
    cache_stats = persistent_cache.get_cache_stats()
    storage_stats = get_pattern_storage_stats(db, administration)

    return {
        'persistent_cache': cache_stats,
        'pattern_storage': storage_stats,
        'cache_effectiveness': {
            'cache_hit_rate': cache_stats['performance']['hit_rate_percent'],
            'startup_performance': f"{cache_stats['performance']['startup_time_seconds']:.3f}s",
            'memory_efficiency': f"{cache_stats['memory_usage']['utilization_percent']:.1f}% utilized",
            'multi_level_caching': {
                'L1_memory': cache_stats['cache_levels']['memory_entries'],
                'L2_database': cache_stats['cache_levels']['database_active'],
                'L3_file': cache_stats['cache_levels']['file_cache_exists']
            }
        },
        'performance_benefits': {
            'cache_survives_restart': True,
            'shared_between_instances': True,
            'automatic_cache_warming': True,
            'multi_level_fallback': True
        }
    }


def get_incremental_update_stats(db: DatabaseManager, administration: str) -> Dict[str, Any]:
    """
    Get statistics about incremental pattern updates

    REQ-PAT-006: Performance improvement through incremental processing
    """
    try:
        metadata = db.execute_query("""
            SELECT last_analysis_date, transactions_analyzed, patterns_discovered,
                   date_range_from, date_range_to, created_at, updated_at
            FROM pattern_analysis_metadata 
            WHERE administration = %s
        """, (administration,))

        if not metadata:
            return {
                'administration': administration,
                'incremental_updates_available': False,
                'reason': 'No previous analysis found'
            }

        meta = metadata[0]
        last_analysis = meta['last_analysis_date']

        # Count pending transactions
        pending_transactions = db.execute_query("""
            SELECT COUNT(*) as count, MIN(TransactionDate) as earliest, MAX(TransactionDate) as latest
            FROM mutaties 
            WHERE administration = %s
            AND TransactionDate > %s
            AND (Debet IS NOT NULL OR Credit IS NOT NULL)
        """, (administration, last_analysis))

        pending_count = pending_transactions[0]['count'] if pending_transactions else 0
        earliest_pending = pending_transactions[0]['earliest'] if pending_transactions else None
        latest_pending = pending_transactions[0]['latest'] if pending_transactions else None

        # Get total transaction count for comparison
        total_transactions = db.execute_query(f"""
            SELECT COUNT(*) as count FROM mutaties 
            WHERE administration = %s 
            AND TransactionDate >= {dialect.date_subtract(dialect.current_date(), 2, 'YEAR')}
            AND (Debet IS NOT NULL OR Credit IS NOT NULL)
        """, (administration,))

        total_count = total_transactions[0]['count'] if total_transactions else 0

        if total_count > 0 and pending_count >= 0:
            efficiency_ratio = pending_count / total_count
            processing_reduction = (1 - efficiency_ratio) * 100
        else:
            efficiency_ratio = 0
            processing_reduction = 0

        return {
            'administration': administration,
            'incremental_updates_available': True,
            'last_analysis': {
                'date': last_analysis.isoformat() if last_analysis else None,
                'transactions_analyzed': meta['transactions_analyzed'],
                'patterns_discovered': meta['patterns_discovered'],
                'analysis_period': {
                    'from': meta['date_range_from'].strftime('%Y-%m-%d') if meta['date_range_from'] else None,
                    'to': meta['date_range_to'].strftime('%Y-%m-%d') if meta['date_range_to'] else None
                }
            },
            'pending_incremental_update': {
                'transactions_to_process': pending_count,
                'date_range': {
                    'from': earliest_pending.strftime('%Y-%m-%d') if earliest_pending else None,
                    'to': latest_pending.strftime('%Y-%m-%d') if latest_pending else None
                },
                'efficiency_gain': f"{processing_reduction:.1f}% reduction in processing",
                'processing_ratio': f"{pending_count}/{total_count} transactions"
            },
            'performance_benefits': {
                'database_io_reduction': f"{processing_reduction:.1f}%",
                'processing_time_reduction': f"~{processing_reduction:.1f}%",
                'memory_usage_reduction': f"~{processing_reduction:.1f}%",
                'incremental_processing_active': True
            },
            'recommendations': {
                'should_run_incremental': pending_count > 0,
                'should_run_full_analysis': should_refresh_patterns(db, administration),
                'next_action': 'incremental_update' if pending_count > 0 and not should_refresh_patterns(db, administration) else 'full_analysis'
            }
        }

    except Exception as e:
        return {
            'administration': administration,
            'incremental_updates_available': False,
            'error': f"Could not retrieve incremental update stats: {e}"
        }


def get_pattern_storage_stats(db: DatabaseManager, administration: str) -> Dict[str, Any]:
    """
    Get statistics about pattern storage performance using unified pattern_verb_patterns table

    REQ-PAT-006: Performance improvement through database storage
    """
    try:
        # Get pattern counts from unified verb patterns table
        verb_pattern_count = db.execute_query("""
            SELECT COUNT(*) as count FROM pattern_verb_patterns 
            WHERE administration = %s
        """, (administration,))

        # Get metadata
        metadata = db.execute_query("""
            SELECT last_analysis_date, transactions_analyzed, patterns_discovered
            FROM pattern_analysis_metadata 
            WHERE administration = %s
        """, (administration,))

        # Get transaction count for comparison
        transaction_count = db.execute_query(f"""
            SELECT COUNT(*) as count FROM mutaties 
            WHERE administration = %s 
            AND TransactionDate >= {dialect.date_subtract(dialect.current_date(), 2, 'YEAR')}
        """, (administration,))

        total_patterns = verb_pattern_count[0]['count'] if verb_pattern_count else 0
        total_transactions = transaction_count[0]['count'] if transaction_count else 0

        # Calculate performance improvement
        if total_transactions > 0:
            data_reduction_ratio = total_patterns / total_transactions
            performance_improvement = f"{(1 - data_reduction_ratio) * 100:.1f}% reduction in data processing"
        else:
            performance_improvement = "No data available"
            data_reduction_ratio = 0

        return {
            'administration': administration,
            'pattern_storage': {
                'unified_verb_patterns': total_patterns,
                'total_patterns': total_patterns
            },
            'transaction_comparison': {
                'total_transactions_2_years': total_transactions,
                'patterns_stored': total_patterns,
                'data_reduction_ratio': f"{data_reduction_ratio:.4f}" if total_transactions > 0 else "N/A",
                'performance_improvement': performance_improvement
            },
            'last_analysis': metadata[0]['last_analysis_date'] if metadata else None,
            'database_storage_active': True,
            'unified_table_approach': True
        }

    except Exception as e:
        return {
            'error': f"Could not retrieve storage stats: {e}",
            'database_storage_active': False
        }
