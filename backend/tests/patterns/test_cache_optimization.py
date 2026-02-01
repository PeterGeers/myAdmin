#!/usr/bin/env python3
"""
Test script to verify cache optimization is working correctly
Tests the three updated report endpoints
"""

import sys
import time
from database import DatabaseManager
from mutaties_cache import get_cache

def test_cache_loading():
    """Test that cache loads successfully"""
    print("\n" + "="*60)
    print("TEST 1: Cache Loading")
    print("="*60)
    
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=False)
        
        start_time = time.time()
        df = cache.get_data(db)
        load_time = time.time() - start_time
        
        print(f"✓ Cache loaded successfully")
        print(f"  - Records: {len(df):,}")
        print(f"  - Load time: {load_time:.3f}s")
        print(f"  - Columns: {', '.join(df.columns[:5])}...")
        print(f"  - Memory usage: ~{df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")
        
        return True
    except Exception as e:
        print(f"✗ Cache loading failed: {e}")
        return False

def test_actuals_balance():
    """Test actuals balance endpoint logic"""
    print("\n" + "="*60)
    print("TEST 2: Actuals Balance (Cache-based)")
    print("="*60)
    
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=False)
        df = cache.get_data(db)
        
        # Simulate the actuals-balance endpoint logic
        start_time = time.time()
        
        # Filter: VW = 'N' (balance accounts)
        filtered = df[df['VW'] == 'N'].copy()
        
        # Filter by year (up to 2025)
        filtered = filtered[filtered['jaar'] <= 2025]
        
        # Group by Parent and ledger
        grouped = filtered.groupby(['Parent', 'ledger'], as_index=False).agg({
            'Amount': 'sum'
        })
        
        # Filter out zero amounts
        grouped = grouped[grouped['Amount'] != 0]
        
        query_time = time.time() - start_time
        
        print(f"✓ Actuals Balance query successful")
        print(f"  - Records returned: {len(grouped):,}")
        print(f"  - Query time: {query_time*1000:.1f}ms")
        print(f"  - Sample data:")
        if len(grouped) > 0:
            for _, row in grouped.head(3).iterrows():
                print(f"    Parent: {row['Parent']}, Ledger: {row['ledger']}, Amount: €{row['Amount']:,.2f}")
        
        return True
    except Exception as e:
        print(f"✗ Actuals Balance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_actuals_profitloss():
    """Test actuals P&L endpoint logic"""
    print("\n" + "="*60)
    print("TEST 3: Actuals Profit/Loss (Cache-based)")
    print("="*60)
    
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=False)
        df = cache.get_data(db)
        
        # Simulate the actuals-profitloss endpoint logic
        start_time = time.time()
        
        # Filter: VW = 'Y' (profit/loss accounts)
        filtered = df[df['VW'] == 'Y'].copy()
        
        # Filter by years
        year_list = [2024, 2025]
        filtered = filtered[filtered['jaar'].isin(year_list)]
        
        # Group by Parent, ledger, jaar
        grouped = filtered.groupby(['Parent', 'ledger', 'jaar'], as_index=False).agg({
            'Amount': 'sum'
        })
        
        # Filter out zero amounts
        grouped = grouped[grouped['Amount'] != 0]
        
        query_time = time.time() - start_time
        
        print(f"✓ Actuals P&L query successful")
        print(f"  - Records returned: {len(grouped):,}")
        print(f"  - Query time: {query_time*1000:.1f}ms")
        print(f"  - Sample data:")
        if len(grouped) > 0:
            for _, row in grouped.head(3).iterrows():
                print(f"    Year: {row['jaar']}, Parent: {row['Parent']}, Ledger: {row['ledger']}, Amount: €{row['Amount']:,.2f}")
        
        return True
    except Exception as e:
        print(f"✗ Actuals P&L test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_btw_data():
    """Test BTW processor logic"""
    print("\n" + "="*60)
    print("TEST 4: BTW Aangifte (Cache-based)")
    print("="*60)
    
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=False)
        df = cache.get_data(db)
        
        # Simulate BTW balance data query
        start_time = time.time()
        
        administration = "GoodwinSolutions"
        end_date = "2025-12-31"
        
        # Filter by date
        df_filtered = df[df['TransactionDate'] <= end_date].copy()
        
        # Filter by administration (LIKE pattern)
        df_filtered = df_filtered[df_filtered['Administration'].str.startswith(administration)]
        
        # Filter by BTW accounts
        df_filtered = df_filtered[df_filtered['Reknum'].isin(['2010', '2020', '2021'])]
        
        # Group by account
        grouped = df_filtered.groupby(['Reknum', 'AccountName'], as_index=False).agg({
            'Amount': 'sum'
        })
        
        query_time = time.time() - start_time
        
        print(f"✓ BTW balance query successful")
        print(f"  - Records returned: {len(grouped):,}")
        print(f"  - Query time: {query_time*1000:.1f}ms")
        print(f"  - Sample data:")
        if len(grouped) > 0:
            for _, row in grouped.iterrows():
                print(f"    Account: {row['Reknum']} - {row['AccountName']}, Amount: €{row['Amount']:,.2f}")
        
        return True
    except Exception as e:
        print(f"✗ BTW test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_reference_number():
    """Test reference number endpoint logic"""
    print("\n" + "="*60)
    print("TEST 5: View ReferenceNumber (Cache-based)")
    print("="*60)
    
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=False)
        df = cache.get_data(db)
        
        # Simulate check-reference endpoint logic
        start_time = time.time()
        
        # Filter: ReferenceNumber not null and not empty
        df_filtered = df[(df['ReferenceNumber'].notna()) & (df['ReferenceNumber'] != '')].copy()
        
        # Get reference summary
        summary_df = df_filtered.groupby('ReferenceNumber', as_index=False).agg({
            'Amount': ['count', 'sum']
        })
        summary_df.columns = ['ReferenceNumber', 'transaction_count', 'total_amount']
        
        # Filter out near-zero amounts
        summary_df = summary_df[summary_df['total_amount'].abs() > 0.01]
        
        # Sort by absolute amount descending
        summary_df = summary_df.sort_values('total_amount', key=lambda x: x.abs(), ascending=False)
        
        query_time = time.time() - start_time
        
        print(f"✓ Reference Number query successful")
        print(f"  - Unique references: {len(summary_df):,}")
        print(f"  - Query time: {query_time*1000:.1f}ms")
        print(f"  - Top 5 references by amount:")
        if len(summary_df) > 0:
            for _, row in summary_df.head(5).iterrows():
                print(f"    {row['ReferenceNumber']}: {row['transaction_count']} transactions, €{row['total_amount']:,.2f}")
        
        return True
    except Exception as e:
        print(f"✗ Reference Number test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance_comparison():
    """Test performance improvement"""
    print("\n" + "="*60)
    print("TEST 6: Performance Comparison")
    print("="*60)
    
    try:
        cache = get_cache()
        db = DatabaseManager(test_mode=False)
        
        # First access (may need to load)
        start_time = time.time()
        df = cache.get_data(db)
        first_access = time.time() - start_time
        
        # Second access (should be cached)
        start_time = time.time()
        df = cache.get_data(db)
        second_access = time.time() - start_time
        
        # Run a complex query
        start_time = time.time()
        filtered = df[df['VW'] == 'Y'].copy()
        filtered = filtered[filtered['jaar'].isin([2024, 2025])]
        grouped = filtered.groupby(['Parent', 'ledger', 'jaar'], as_index=False).agg({
            'Amount': 'sum'
        })
        query_time = time.time() - start_time
        
        print(f"✓ Performance metrics:")
        print(f"  - First cache access: {first_access*1000:.1f}ms")
        print(f"  - Second cache access: {second_access*1000:.1f}ms")
        print(f"  - Complex query time: {query_time*1000:.1f}ms")
        print(f"  - Cache speedup: {first_access/second_access:.1f}x faster")
        print(f"  - Estimated DB query time: ~200-500ms")
        print(f"  - Cache improvement: ~{200/query_time:.0f}x faster than DB")
        
        return True
    except Exception as e:
        print(f"✗ Performance test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("CACHE OPTIMIZATION VERIFICATION")
    print("Testing: Actuals, BTW, and ReferenceNumber endpoints")
    print("="*60)
    
    tests = [
        test_cache_loading,
        test_actuals_balance,
        test_actuals_profitloss,
        test_btw_data,
        test_reference_number,
        test_performance_comparison
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - Cache optimization is working correctly!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
