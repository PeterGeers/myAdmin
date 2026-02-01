#!/usr/bin/env python3
"""
Test Runner for Pattern Analyzer Fixes

This script runs the pattern analysis with the FIXED code (pattern_analyzer_test.py)
and compares results with the backup data.

Usage:
    cd backend/src/validate_pattern
    python run_test.py
"""

import sys
import os

# Add parent directory to path so we can import from backend/src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pattern_analyzer_test import PatternAnalyzer
from datetime import datetime

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80 + "\n")

def print_section(text):
    """Print a formatted section"""
    print("\n" + "-"*80)
    print(f"  {text}")
    print("-"*80 + "\n")

def main():
    print_header("Pattern Analyzer Test - With 4 Fixes Applied")
    
    print("📋 Test Configuration:")
    print("   - Using: pattern_analyzer_test.py (with fixes)")
    print("   - Original: backend/src/pattern_analyzer.py (untouched)")
    print("   - Backup: pattern_verb_patterns_backup_20260127 (3,258 records)")
    print(f"   - Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize test analyzer
    print_section("Initializing Pattern Analyzer (Test Version)")
    analyzer = PatternAnalyzer(test_mode=False)
    print("✅ Pattern Analyzer initialized")
    
    # Analyze PeterPrive
    print_section("Analyzing PeterPrive Administration")
    try:
        result_peter = analyzer.analyze_historical_patterns("PeterPrive")
        print(f"✅ PeterPrive Analysis Complete:")
        print(f"   - Total Transactions: {result_peter['total_transactions']}")
        print(f"   - Patterns Discovered: {result_peter['patterns_discovered']}")
        print(f"   - Date Range: {result_peter['date_range']['from']} to {result_peter['date_range']['to']}")
    except Exception as e:
        print(f"❌ Error analyzing PeterPrive: {e}")
        return 1
    
    # Analyze GoodwinSolutions
    print_section("Analyzing GoodwinSolutions Administration")
    try:
        result_goodwin = analyzer.analyze_historical_patterns("GoodwinSolutions")
        print(f"✅ GoodwinSolutions Analysis Complete:")
        print(f"   - Total Transactions: {result_goodwin['total_transactions']}")
        print(f"   - Patterns Discovered: {result_goodwin['patterns_discovered']}")
        print(f"   - Date Range: {result_goodwin['date_range']['from']} to {result_goodwin['date_range']['to']}")
    except Exception as e:
        print(f"❌ Error analyzing GoodwinSolutions: {e}")
        return 1
    
    # Summary
    print_section("Test Summary")
    total_patterns = result_peter['patterns_discovered'] + result_goodwin['patterns_discovered']
    print(f"✅ Total Patterns Created: {total_patterns}")
    print(f"   - PeterPrive: {result_peter['patterns_discovered']}")
    print(f"   - GoodwinSolutions: {result_goodwin['patterns_discovered']}")
    
    print_header("Next Steps")
    print("1. Run SQL comparison query to compare NEW vs BACKUP patterns")
    print("2. Check specific test cases (Sociale Verzekeringsbank, 2Theloo)")
    print("3. Calculate success rate")
    print("4. If >= 95%, replace original with test version")
    print("5. If < 95%, rollback to backup")
    
    print("\n📊 SQL Comparison Query:")
    print("""
    SELECT 
        'NEW' as source,
        administration,
        COUNT(*) as pattern_count,
        COUNT(DISTINCT verb_company) as unique_companies,
        COUNT(DISTINCT reference_number) as unique_references,
        AVG(occurrences) as avg_occurrences
    FROM pattern_verb_patterns
    GROUP BY administration
    
    UNION ALL
    
    SELECT 
        'BACKUP' as source,
        administration,
        COUNT(*) as pattern_count,
        COUNT(DISTINCT verb_company) as unique_companies,
        COUNT(DISTINCT reference_number) as unique_references,
        AVG(occurrences) as avg_occurrences
    FROM pattern_verb_patterns_backup_20260127
    GROUP BY administration
    ORDER BY administration, source;
    """)
    
    print("\n✅ Test completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
