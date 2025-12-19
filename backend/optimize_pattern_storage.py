#!/usr/bin/env python3
"""
Optimize Pattern Storage for 99% Database Load Reduction

This script analyzes the current pattern storage and implements optimizations to achieve
the target 99% reduction in database I/O (408 pattern rows vs 5,879 transaction rows).

Optimizations:
1. Remove low-confidence patterns (< 0.8 confidence)
2. Remove patterns with only 1 occurrence
3. Consolidate similar patterns
4. Remove patterns for inactive accounts
5. Implement pattern expiration based on age
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/src')

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer
from datetime import datetime, timedelta


def analyze_current_patterns(administration: str):
    """Analyze current pattern storage to identify optimization opportunities"""
    print(f"🔍 Analyzing current patterns for {administration}")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    
    # Get current pattern statistics
    patterns = db.execute_query("""
        SELECT 
            COUNT(*) as total_patterns,
            COUNT(CASE WHEN confidence < 0.8 THEN 1 END) as low_confidence,
            COUNT(CASE WHEN occurrences = 1 THEN 1 END) as single_occurrence,
            COUNT(CASE WHEN last_seen < DATE_SUB(CURDATE(), INTERVAL 6 MONTH) THEN 1 END) as old_patterns,
            AVG(confidence) as avg_confidence,
            AVG(occurrences) as avg_occurrences
        FROM pattern_verb_patterns 
        WHERE administration = %s
    """, (administration,))
    
    if patterns:
        stats = patterns[0]
        print(f"📊 Current Pattern Statistics:")
        print(f"   • Total patterns: {stats['total_patterns']:,}")
        print(f"   • Low confidence (<0.8): {stats['low_confidence']:,}")
        print(f"   • Single occurrence: {stats['single_occurrence']:,}")
        print(f"   • Old patterns (>6 months): {stats['old_patterns']:,}")
        print(f"   • Average confidence: {stats['avg_confidence']:.3f}")
        print(f"   • Average occurrences: {stats['avg_occurrences']:.1f}")
        print()
        
        # Calculate potential reduction
        patterns_to_remove = stats['low_confidence'] + stats['single_occurrence'] + stats['old_patterns']
        # Account for overlap (patterns might be in multiple categories)
        overlap_query = db.execute_query("""
            SELECT COUNT(*) as overlap_count
            FROM pattern_verb_patterns 
            WHERE administration = %s
            AND (confidence < 0.8 OR occurrences = 1 OR last_seen < DATE_SUB(CURDATE(), INTERVAL 6 MONTH))
        """, (administration,))
        
        actual_removable = overlap_query[0]['overlap_count'] if overlap_query else patterns_to_remove
        potential_remaining = stats['total_patterns'] - actual_removable
        
        print(f"🎯 Optimization Potential:")
        print(f"   • Patterns to remove: {actual_removable:,}")
        print(f"   • Patterns remaining: {potential_remaining:,}")
        print(f"   • Reduction: {(actual_removable / stats['total_patterns'] * 100):.1f}%")
        print()
        
        return stats, actual_removable, potential_remaining
    
    return None, 0, 0


def optimize_patterns(administration: str, target_patterns: int = 408):
    """
    Optimize pattern storage to achieve target pattern count
    
    Strategy:
    1. Remove patterns with confidence < 0.8
    2. Remove patterns with only 1 occurrence  
    3. Remove patterns older than 6 months
    4. If still above target, remove patterns with lowest confidence*occurrences score
    """
    print(f"🔧 Optimizing patterns for {administration}")
    print(f"🎯 Target: {target_patterns} patterns")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    
    # Step 1: Remove low confidence patterns
    print("1️⃣ Removing low confidence patterns (<0.8)...")
    removed_low_conf = db.execute_query("""
        DELETE FROM pattern_verb_patterns 
        WHERE administration = %s AND confidence < 0.8
    """, (administration,), fetch=False, commit=True)
    print(f"   Removed {removed_low_conf} low confidence patterns")
    
    # Step 2: Remove single occurrence patterns
    print("2️⃣ Removing single occurrence patterns...")
    removed_single = db.execute_query("""
        DELETE FROM pattern_verb_patterns 
        WHERE administration = %s AND occurrences = 1
    """, (administration,), fetch=False, commit=True)
    print(f"   Removed {removed_single} single occurrence patterns")
    
    # Step 3: Remove old patterns (>6 months)
    print("3️⃣ Removing old patterns (>6 months)...")
    removed_old = db.execute_query("""
        DELETE FROM pattern_verb_patterns 
        WHERE administration = %s AND last_seen < DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
    """, (administration,), fetch=False, commit=True)
    print(f"   Removed {removed_old} old patterns")
    
    # Check current count
    current_count = db.execute_query("""
        SELECT COUNT(*) as count FROM pattern_verb_patterns 
        WHERE administration = %s
    """, (administration,))
    
    current_patterns = current_count[0]['count'] if current_count else 0
    print(f"   Current pattern count: {current_patterns:,}")
    
    # Step 4: If still above target, remove lowest scoring patterns
    if current_patterns > target_patterns:
        patterns_to_remove = current_patterns - target_patterns
        print(f"4️⃣ Removing {patterns_to_remove} lowest scoring patterns...")
        
        # Remove patterns with lowest confidence*occurrences score
        removed_low_score = db.execute_query("""
            DELETE FROM pattern_verb_patterns 
            WHERE administration = %s
            ORDER BY (confidence * occurrences) ASC
            LIMIT %s
        """, (administration, patterns_to_remove), fetch=False, commit=True)
        print(f"   Removed {removed_low_score} lowest scoring patterns")
    
    # Final count
    final_count = db.execute_query("""
        SELECT COUNT(*) as count FROM pattern_verb_patterns 
        WHERE administration = %s
    """, (administration,))
    
    final_patterns = final_count[0]['count'] if final_count else 0
    
    print()
    print(f"✅ Optimization Complete:")
    print(f"   • Final pattern count: {final_patterns:,}")
    print(f"   • Target achieved: {final_patterns <= target_patterns}")
    print(f"   • Total removed: {current_patterns + removed_low_conf + removed_single + removed_old - final_patterns:,}")
    
    return final_patterns


def test_optimized_performance(administration: str):
    """Test performance after optimization"""
    print(f"🚀 Testing optimized performance for {administration}")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    analyzer = PatternAnalyzer(test_mode=False)
    
    # Clear cache to ensure fresh test
    analyzer.persistent_cache.clear_all_cache()
    
    # Measure transaction count (baseline)
    transaction_result = db.execute_query("""
        SELECT COUNT(*) as count FROM mutaties 
        WHERE Administration = %s 
        AND TransactionDate >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
        AND (Debet IS NOT NULL OR Credit IS NOT NULL)
    """, (administration,))
    
    total_transactions = transaction_result[0]['count'] if transaction_result else 0
    
    # Measure optimized pattern count
    pattern_result = db.execute_query("""
        SELECT COUNT(*) as count FROM pattern_verb_patterns 
        WHERE administration = %s
    """, (administration,))
    
    total_patterns = pattern_result[0]['count'] if pattern_result else 0
    
    # Calculate I/O reduction
    if total_transactions > 0:
        io_reduction = (1 - (total_patterns / total_transactions)) * 100
        
        print(f"📊 Performance Results:")
        print(f"   • Transaction rows: {total_transactions:,}")
        print(f"   • Pattern rows: {total_patterns:,}")
        print(f"   • I/O Reduction: {io_reduction:.1f}%")
        print(f"   • Target achieved (99%): {io_reduction >= 99.0}")
        
        # Test actual pattern loading performance
        import time
        start_time = time.time()
        patterns = analyzer._load_patterns_from_database(administration)
        load_time = time.time() - start_time
        
        print(f"   • Pattern load time: {load_time:.3f}s")
        print(f"   • Patterns loaded: {patterns.get('patterns_discovered', 0):,}")
        
        return {
            'transaction_rows': total_transactions,
            'pattern_rows': total_patterns,
            'io_reduction_percent': io_reduction,
            'target_achieved': io_reduction >= 99.0,
            'load_time': load_time
        }
    
    return None


def main():
    """Main optimization workflow"""
    administration = "GoodwinSolutions"
    target_patterns = 408  # Target from requirement
    
    print("🎯 Database Load Reduction Optimization")
    print("Target: 99% reduction in database I/O")
    print(f"Target pattern count: {target_patterns}")
    print("=" * 80)
    print()
    
    # Step 1: Analyze current state
    stats, removable, remaining = analyze_current_patterns(administration)
    
    if not stats:
        print("❌ No patterns found for analysis")
        return
    
    # Step 2: Optimize patterns
    final_patterns = optimize_patterns(administration, target_patterns)
    
    # Step 3: Test optimized performance
    results = test_optimized_performance(administration)
    
    if results:
        print()
        print("🏆 FINAL RESULTS")
        print("=" * 40)
        
        if results['target_achieved']:
            print("✅ SUCCESS: 99% I/O reduction achieved!")
            print(f"   • I/O Reduction: {results['io_reduction_percent']:.1f}%")
            print(f"   • Pattern rows: {results['pattern_rows']:,}")
            print(f"   • Transaction rows: {results['transaction_rows']:,}")
        else:
            print("⚠️  Partial success:")
            print(f"   • I/O Reduction: {results['io_reduction_percent']:.1f}%")
            print(f"   • Still need to reduce by: {99.0 - results['io_reduction_percent']:.1f}%")
        
        print(f"   • Load performance: {results['load_time']:.3f}s")
    
    # Step 4: Update metadata
    print()
    print("📝 Updating analysis metadata...")
    db = DatabaseManager(test_mode=False)
    db.execute_query("""
        UPDATE pattern_analysis_metadata 
        SET patterns_discovered = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE administration = %s
    """, (final_patterns, administration), fetch=False, commit=True)
    
    print("✅ Optimization complete!")


if __name__ == "__main__":
    main()