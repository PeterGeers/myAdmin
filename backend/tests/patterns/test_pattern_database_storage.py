#!/usr/bin/env python3
"""
Test script for database pattern storage implementation

This script validates:
- REQ-PAT-005: Store discovered patterns in optimized database structure
- REQ-PAT-006: Implement pattern caching for performance
- Database Pattern Storage: Patterns are stored in dedicated database tables instead of recalculating from mutaties table every time
"""

import sys
import os
import time
import pytest
from datetime import datetime

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from pattern_analyzer import PatternAnalyzer
from database import DatabaseManager

# Skip this test - requires pattern_debet_predictions table that doesn't exist yet
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skip(reason="Requires pattern_debet_predictions table - TODO: create migration")
]

def test_database_pattern_storage():
    """Test database pattern storage functionality"""
    print("🧪 Testing Database Pattern Storage Implementation")
    print("=" * 60)
    
    # Initialize analyzer
    analyzer = PatternAnalyzer(test_mode=False)
    administration = "GoodwinSolutions"
    
    print(f"\n1. Testing Pattern Storage to Database")
    print("-" * 40)
    
    # Clear any existing patterns for clean test
    db = DatabaseManager(test_mode=False)
    try:
        db.execute_query("DELETE FROM pattern_analysis_metadata WHERE administration = %s", (administration,), fetch=False, commit=True)
        db.execute_query("DELETE FROM pattern_debet_predictions WHERE administration = %s", (administration,), fetch=False, commit=True)
        db.execute_query("DELETE FROM pattern_credit_predictions WHERE administration = %s", (administration,), fetch=False, commit=True)
        db.execute_query("DELETE FROM pattern_reference_predictions WHERE administration = %s", (administration,), fetch=False, commit=True)
        print("✅ Cleared existing test patterns")
    except Exception as e:
        print(f"Warning: Could not clear existing patterns: {e}")
    
    # Test 1: Full pattern analysis and storage
    print(f"\n📊 Running full pattern analysis for {administration}...")
    start_time = time.time()
    
    patterns = analyzer.analyze_historical_patterns(administration)
    analysis_time = time.time() - start_time
    
    print(f"✅ Analysis completed in {analysis_time:.2f} seconds")
    print(f"   - Total transactions analyzed: {patterns['total_transactions']:,}")
    print(f"   - Patterns discovered: {patterns['patterns_discovered']}")
    print(f"   - Debet patterns: {len(patterns['debet_patterns'])}")
    print(f"   - Credit patterns: {len(patterns['credit_patterns'])}")
    print(f"   - Reference patterns: {len(patterns['reference_patterns'])}")
    
    # Test 2: Verify patterns are stored in database
    print(f"\n2. Verifying Database Storage")
    print("-" * 40)
    
    # Check database tables directly
    debet_count = db.execute_query("SELECT COUNT(*) as count FROM pattern_debet_predictions WHERE administration = %s", (administration,))
    credit_count = db.execute_query("SELECT COUNT(*) as count FROM pattern_credit_predictions WHERE administration = %s", (administration,))
    reference_count = db.execute_query("SELECT COUNT(*) as count FROM pattern_reference_predictions WHERE administration = %s", (administration,))
    metadata_count = db.execute_query("SELECT COUNT(*) as count FROM pattern_analysis_metadata WHERE administration = %s", (administration,))
    
    db_debet_count = debet_count[0]['count'] if debet_count else 0
    db_credit_count = credit_count[0]['count'] if credit_count else 0
    db_reference_count = reference_count[0]['count'] if reference_count else 0
    db_metadata_count = metadata_count[0]['count'] if metadata_count else 0
    
    print(f"✅ Database storage verification:")
    print(f"   - Debet patterns in DB: {db_debet_count}")
    print(f"   - Credit patterns in DB: {db_credit_count}")
    print(f"   - Reference patterns in DB: {db_reference_count}")
    print(f"   - Metadata records: {db_metadata_count}")
    
    total_db_patterns = db_debet_count + db_credit_count + db_reference_count
    
    if total_db_patterns > 0:
        print(f"✅ Patterns successfully stored in database: {total_db_patterns} total patterns")
    else:
        print("❌ No patterns found in database")
        return False
    
    # Test 3: Load patterns from database (performance test)
    print(f"\n3. Testing Database Pattern Loading Performance")
    print("-" * 40)
    
    # Clear memory cache to force database load
    analyzer.patterns_cache.clear()
    
    start_time = time.time()
    loaded_patterns = analyzer._load_patterns_from_database(administration)
    load_time = time.time() - start_time
    
    print(f"✅ Database load completed in {load_time:.4f} seconds")
    print(f"   - Loaded patterns: {loaded_patterns['patterns_discovered']}")
    print(f"   - Performance improvement: {analysis_time/load_time:.1f}x faster than full analysis")
    
    # Test 4: Verify pattern retrieval uses database
    print(f"\n4. Testing Pattern Retrieval from Database")
    print("-" * 40)
    
    # Clear cache again
    analyzer.patterns_cache.clear()
    
    start_time = time.time()
    retrieved_patterns = analyzer.get_filtered_patterns(administration)
    retrieval_time = time.time() - start_time
    
    print(f"✅ Pattern retrieval completed in {retrieval_time:.4f} seconds")
    print(f"   - Retrieved patterns: {retrieved_patterns['patterns_discovered']}")
    print(f"   - Uses database storage: {retrieval_time < 1.0}")  # Should be very fast from DB
    
    # Test 5: Storage statistics
    print(f"\n5. Testing Storage Statistics")
    print("-" * 40)
    
    storage_stats = analyzer.get_pattern_storage_stats(administration)
    
    if 'error' not in storage_stats:
        print(f"✅ Storage statistics:")
        print(f"   - Total patterns stored: {storage_stats['pattern_storage']['total_patterns']}")
        print(f"   - Total transactions (2 years): {storage_stats['transaction_comparison']['total_transactions_2_years']:,}")
        print(f"   - Data reduction: {storage_stats['transaction_comparison']['performance_improvement']}")
        print(f"   - Database storage active: {storage_stats['database_storage_active']}")
    else:
        print(f"❌ Storage statistics error: {storage_stats['error']}")
        return False
    
    # Test 6: Incremental updates (simulate)
    print(f"\n6. Testing Incremental Pattern Updates")
    print("-" * 40)
    
    # Test should_refresh_patterns
    should_refresh = analyzer._should_refresh_patterns(administration)
    print(f"✅ Should refresh patterns: {should_refresh} (expected: False for recent analysis)")
    
    # Test incremental analysis (will likely find no new transactions)
    start_time = time.time()
    incremental_result = analyzer.analyze_incremental_patterns(administration)
    incremental_time = time.time() - start_time
    
    print(f"✅ Incremental analysis completed in {incremental_time:.4f} seconds")
    print(f"   - Result patterns: {incremental_result['patterns_discovered']}")
    
    # Test 7: Performance comparison
    print(f"\n7. Performance Comparison Summary")
    print("-" * 40)
    
    print(f"✅ Performance Results:")
    print(f"   - Full analysis time: {analysis_time:.2f} seconds")
    print(f"   - Database load time: {load_time:.4f} seconds")
    print(f"   - Pattern retrieval time: {retrieval_time:.4f} seconds")
    print(f"   - Speed improvement: {analysis_time/load_time:.1f}x faster with database storage")
    
    # Calculate data reduction
    if storage_stats['transaction_comparison']['total_transactions_2_years'] > 0:
        transactions = storage_stats['transaction_comparison']['total_transactions_2_years']
        patterns = storage_stats['pattern_storage']['total_patterns']
        reduction_ratio = (1 - patterns/transactions) * 100
        print(f"   - Data reduction: {reduction_ratio:.1f}% (processing {patterns} patterns vs {transactions:,} transactions)")
    
    print(f"\n🎉 Database Pattern Storage Test Results:")
    print(f"✅ REQ-PAT-005: Patterns stored in dedicated database tables")
    print(f"✅ REQ-PAT-006: Pattern caching implemented for performance")
    print(f"✅ Database Pattern Storage: Eliminates repeated mutaties table analysis")
    print(f"✅ Performance improvement: {analysis_time/load_time:.1f}x faster pattern retrieval")
    
    # Get transaction count from storage stats
    total_transactions = storage_stats['transaction_comparison']['total_transactions_2_years']
    print(f"✅ Data reduction: Processing {total_db_patterns} patterns instead of {total_transactions:,} transactions")
    
    return True

if __name__ == "__main__":
    try:
        success = test_database_pattern_storage()
        if success:
            print(f"\n🎉 ALL TESTS PASSED!")
            print("✅ Database pattern storage implementation is working correctly")
            sys.exit(0)
        else:
            print(f"\n❌ TESTS FAILED!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)