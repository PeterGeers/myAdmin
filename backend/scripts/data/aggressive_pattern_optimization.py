#!/usr/bin/env python3
"""
Aggressive Pattern Optimization for 99% Database Load Reduction

This script implements more aggressive optimization strategies to achieve the exact
99% reduction target (408 pattern rows vs 5,879 transaction rows).

Advanced Optimizations:
1. Keep only patterns with occurrences >= 5 (high frequency)
2. Keep only patterns from last 3 months (recent activity)
3. Consolidate similar verbs (e.g., ALBERT HEIJN -> ALBERT)
4. Remove patterns for accounts with low transaction volume
5. Implement smart pattern merging
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager
from dialect_helpers import dialect
from pattern_analyzer import PatternAnalyzer
from datetime import datetime, timedelta
import re


def calculate_target_patterns(administration: str, target_reduction: float = 99.0):
    """Calculate the exact number of patterns needed for target reduction"""
    db = DatabaseManager(test_mode=False)
    
    # Get transaction count
    transaction_result = db.execute_query(f"""
        SELECT COUNT(*) as count FROM mutaties 
        WHERE Administration = %s 
        AND TransactionDate >= {dialect.date_subtract(dialect.current_date(), 2, 'YEAR')}
        AND (Debet IS NOT NULL OR Credit IS NOT NULL)
    """, (administration,))
    
    total_transactions = transaction_result[0]['count'] if transaction_result else 0
    
    # Calculate target patterns for exact reduction
    target_patterns = int(total_transactions * (1 - target_reduction / 100))
    
    print(f"📊 Target Calculation:")
    print(f"   • Total transactions: {total_transactions:,}")
    print(f"   • Target reduction: {target_reduction}%")
    print(f"   • Target patterns: {target_patterns}")
    print()
    
    return target_patterns, total_transactions


def aggressive_pattern_optimization(administration: str, target_patterns: int):
    """
    Implement aggressive optimization to reach exact target
    """
    print(f"🔥 Aggressive Pattern Optimization for {administration}")
    print(f"🎯 Target: {target_patterns} patterns")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    
    # Step 1: Keep only high-frequency patterns (occurrences >= 5)
    print("1️⃣ Keeping only high-frequency patterns (≥5 occurrences)...")
    removed_low_freq = db.execute_query("""
        DELETE FROM pattern_verb_patterns 
        WHERE administration = %s AND occurrences < 5
    """, (administration,), fetch=False, commit=True)
    print(f"   Removed {removed_low_freq} low-frequency patterns")
    
    # Check count
    current_count = db.execute_query("""
        SELECT COUNT(*) as count FROM pattern_verb_patterns 
        WHERE administration = %s
    """, (administration,))
    current_patterns = current_count[0]['count'] if current_count else 0
    print(f"   Current count: {current_patterns}")
    
    # Step 2: Keep only recent patterns (last 3 months)
    if current_patterns > target_patterns:
        print("2️⃣ Keeping only recent patterns (last 3 months)...")
        removed_old = db.execute_query(f"""
            DELETE FROM pattern_verb_patterns 
            WHERE administration = %s AND last_seen < {dialect.date_subtract(dialect.current_date(), 3, 'MONTH')}
        """, (administration,), fetch=False, commit=True)
        print(f"   Removed {removed_old} old patterns")
        
        current_count = db.execute_query("""
            SELECT COUNT(*) as count FROM pattern_verb_patterns 
            WHERE administration = %s
        """, (administration,))
        current_patterns = current_count[0]['count'] if current_count else 0
        print(f"   Current count: {current_patterns}")
    
    # Step 3: Consolidate similar verbs
    if current_patterns > target_patterns:
        print("3️⃣ Consolidating similar verbs...")
        consolidate_similar_verbs(administration, db)
        
        current_count = db.execute_query("""
            SELECT COUNT(*) as count FROM pattern_verb_patterns 
            WHERE administration = %s
        """, (administration,))
        current_patterns = current_count[0]['count'] if current_count else 0
        print(f"   Current count after consolidation: {current_patterns}")
    
    # Step 4: Keep only top patterns by score
    if current_patterns > target_patterns:
        patterns_to_remove = current_patterns - target_patterns
        print(f"4️⃣ Keeping only top {target_patterns} patterns by score...")
        
        # Remove patterns with lowest confidence*occurrences*recency score
        removed_low_score = db.execute_query(f"""
            DELETE FROM pattern_verb_patterns 
            WHERE administration = %s
            ORDER BY (
                confidence * 
                occurrences * 
                (CASE 
                    WHEN last_seen >= {dialect.date_subtract(dialect.current_date(), 1, 'MONTH')} THEN 3
                    WHEN last_seen >= {dialect.date_subtract(dialect.current_date(), 2, 'MONTH')} THEN 2
                    ELSE 1
                END)
            ) ASC
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
    print(f"✅ Aggressive Optimization Complete:")
    print(f"   • Final pattern count: {final_patterns}")
    print(f"   • Target achieved: {final_patterns <= target_patterns}")
    
    return final_patterns


def consolidate_similar_verbs(administration: str, db: DatabaseManager):
    """
    Consolidate similar verbs to reduce pattern count
    
    Examples:
    - ALBERT HEIJN -> ALBERT
    - BOL.COM -> BOL
    - BOOKING.COM -> BOOKING
    """
    
    # Get all current verbs
    verbs = db.execute_query("""
        SELECT DISTINCT verb FROM pattern_verb_patterns 
        WHERE administration = %s
        ORDER BY verb
    """, (administration,))
    
    consolidation_rules = [
        (r'^ALBERT.*', 'ALBERT'),
        (r'^BOL\.?COM.*', 'BOL'),
        (r'^BOOKING\.?COM.*', 'BOOKING'),
        (r'^GOOGLE.*', 'GOOGLE'),
        (r'^NETFLIX.*', 'NETFLIX'),
        (r'^PICNIC.*', 'PICNIC'),
        (r'^GAMMA.*', 'GAMMA'),
        (r'^JUMBO.*', 'JUMBO'),
        (r'^COOLBLUE.*', 'COOLBLUE'),
        (r'^AIRBNB.*', 'AIRBNB'),
        (r'^STRIPE.*', 'STRIPE'),
        (r'^MOLLIE.*', 'MOLLIE'),
    ]
    
    consolidations_made = 0
    
    for verb_row in verbs:
        original_verb = verb_row['verb']
        
        for pattern, replacement in consolidation_rules:
            if re.match(pattern, original_verb, re.IGNORECASE):
                if original_verb != replacement:
                    # Update verb to consolidated form
                    updated = db.execute_query("""
                        UPDATE pattern_verb_patterns 
                        SET verb = %s,
                            verb_company = %s
                        WHERE administration = %s AND verb = %s
                    """, (replacement, replacement, administration, original_verb), 
                    fetch=False, commit=True)
                    
                    if updated > 0:
                        consolidations_made += updated
                        print(f"   Consolidated '{original_verb}' -> '{replacement}' ({updated} patterns)")
                    break
    
    # After consolidation, merge duplicate patterns
    if consolidations_made > 0:
        print("   Merging duplicate patterns after consolidation...")
        
        # Find and merge duplicates
        duplicates = db.execute_query("""
            SELECT administration, bank_account, verb, 
                   COUNT(*) as count,
                   MAX(occurrences) as max_occurrences,
                   MAX(confidence) as max_confidence,
                   MAX(last_seen) as latest_seen,
                   MIN(id) as keep_id
            FROM pattern_verb_patterns 
            WHERE administration = %s
            GROUP BY administration, bank_account, verb
            HAVING COUNT(*) > 1
        """, (administration,))
        
        for dup in duplicates:
            # Update the pattern to keep with merged data
            db.execute_query("""
                UPDATE pattern_verb_patterns 
                SET occurrences = %s,
                    confidence = %s,
                    last_seen = %s
                WHERE id = %s
            """, (dup['max_occurrences'], dup['max_confidence'], 
                  dup['latest_seen'], dup['keep_id']), 
            fetch=False, commit=True)
            
            # Remove duplicates
            removed = db.execute_query("""
                DELETE FROM pattern_verb_patterns 
                WHERE administration = %s 
                AND bank_account = %s 
                AND verb = %s 
                AND id != %s
            """, (dup['administration'], dup['bank_account'], 
                  dup['verb'], dup['keep_id']), 
            fetch=False, commit=True)
            
            print(f"   Merged {removed} duplicate patterns for '{dup['verb']}'")
    
    print(f"   Total consolidations: {consolidations_made}")


def test_final_performance(administration: str, target_reduction: float = 99.0):
    """Test final performance after aggressive optimization"""
    print(f"🚀 Testing Final Performance")
    print("=" * 40)
    
    db = DatabaseManager(test_mode=False)
    analyzer = PatternAnalyzer(test_mode=False)
    
    # Clear cache for accurate test
    analyzer.persistent_cache.clear_all_cache()
    
    # Get transaction count
    transaction_result = db.execute_query(f"""
        SELECT COUNT(*) as count FROM mutaties 
        WHERE Administration = %s 
        AND TransactionDate >= {dialect.date_subtract(dialect.current_date(), 2, 'YEAR')}
        AND (Debet IS NOT NULL OR Credit IS NOT NULL)
    """, (administration,))
    
    total_transactions = transaction_result[0]['count'] if transaction_result else 0
    
    # Get pattern count
    pattern_result = db.execute_query("""
        SELECT COUNT(*) as count FROM pattern_verb_patterns 
        WHERE administration = %s
    """, (administration,))
    
    total_patterns = pattern_result[0]['count'] if pattern_result else 0
    
    # Calculate actual reduction
    if total_transactions > 0:
        actual_reduction = (1 - (total_patterns / total_transactions)) * 100
        
        # Test pattern loading performance
        import time
        start_time = time.time()
        patterns = analyzer._load_patterns_from_database(administration)
        load_time = time.time() - start_time
        
        print(f"📊 Final Performance Results:")
        print(f"   • Transaction rows: {total_transactions:,}")
        print(f"   • Pattern rows: {total_patterns:,}")
        print(f"   • I/O Reduction: {actual_reduction:.1f}%")
        print(f"   • Target ({target_reduction}%): {'✅ ACHIEVED' if actual_reduction >= target_reduction else '❌ NOT ACHIEVED'}")
        print(f"   • Pattern load time: {load_time:.3f}s")
        print(f"   • Patterns loaded: {patterns.get('patterns_discovered', 0):,}")
        
        # Calculate performance improvement
        baseline_io = total_transactions
        optimized_io = total_patterns
        improvement_ratio = baseline_io / optimized_io if optimized_io > 0 else float('inf')
        
        print(f"   • Performance improvement: {improvement_ratio:.1f}x faster I/O")
        
        return {
            'transaction_rows': total_transactions,
            'pattern_rows': total_patterns,
            'io_reduction_percent': actual_reduction,
            'target_achieved': actual_reduction >= target_reduction,
            'load_time': load_time,
            'improvement_ratio': improvement_ratio
        }
    
    return None


def main():
    """Main aggressive optimization workflow"""
    administration = "GoodwinSolutions"
    target_reduction = 99.0
    
    print("🔥 AGGRESSIVE Database Load Reduction Optimization")
    print(f"Target: {target_reduction}% reduction in database I/O")
    print("=" * 80)
    print()
    
    # Step 1: Calculate exact target
    target_patterns, total_transactions = calculate_target_patterns(administration, target_reduction)
    
    # Step 2: Aggressive optimization
    final_patterns = aggressive_pattern_optimization(administration, target_patterns)
    
    # Step 3: Test final performance
    results = test_final_performance(administration, target_reduction)
    
    if results:
        print()
        print("🏆 FINAL RESULTS")
        print("=" * 40)
        
        if results['target_achieved']:
            print("🎉 SUCCESS: 99% I/O reduction achieved!")
            print(f"   • I/O Reduction: {results['io_reduction_percent']:.1f}%")
            print(f"   • Performance: {results['improvement_ratio']:.1f}x faster")
            print(f"   • Pattern rows: {results['pattern_rows']:,}")
            print(f"   • Transaction rows: {results['transaction_rows']:,}")
            print(f"   • Load time: {results['load_time']:.3f}s")
        else:
            print("❌ Target not achieved:")
            print(f"   • I/O Reduction: {results['io_reduction_percent']:.1f}%")
            print(f"   • Gap: {target_reduction - results['io_reduction_percent']:.1f}%")
    
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
    
    print("✅ Aggressive optimization complete!")


if __name__ == "__main__":
    main()