#!/usr/bin/env python3
"""
Test the enhanced pattern analysis API endpoints
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from banking_processor import BankingProcessor
import json


def test_pattern_api():
    """Test the enhanced pattern analysis methods"""
    print("=" * 60)
    print("TESTING ENHANCED PATTERN ANALYSIS API")
    print("=" * 60)
    
    processor = BankingProcessor(test_mode=False)
    administration = 'GoodwinSolutions'
    
    # Test 1: Analyze patterns
    print("\n1. Testing analyze_patterns_for_administration...")
    try:
        patterns = processor.analyze_patterns_for_administration(administration)
        print(f"✅ Pattern analysis successful")
        print(f"   - Total transactions: {patterns['total_transactions']}")
        print(f"   - Patterns discovered: {patterns['patterns_discovered']}")
        print(f"   - Date range: {patterns['date_range']['from']} to {patterns['date_range']['to']}")
    except Exception as e:
        print(f"❌ Pattern analysis failed: {e}")
        return False
    
    # Test 2: Apply enhanced patterns
    print("\n2. Testing apply_enhanced_patterns...")
    try:
        sample_transactions = [
            {
                'TransactionDescription': 'GAMMA BOUWMARKT TEST',
                'TransactionAmount': 100.00,
                'Debet': '',
                'Credit': '1002',
                'Administration': administration,
                'TransactionDate': '2025-12-19'
            }
        ]
        
        updated_transactions, results = processor.apply_enhanced_patterns(
            sample_transactions, administration
        )
        
        print(f"✅ Enhanced pattern application successful")
        print(f"   - Transactions processed: {results['total_transactions']}")
        print(f"   - Predictions made: {sum(results['predictions_made'].values())}")
        print(f"   - Average confidence: {results['average_confidence']:.2f}")
        
    except Exception as e:
        print(f"❌ Enhanced pattern application failed: {e}")
        return False
    
    # Test 3: Get pattern summary
    print("\n3. Testing get_pattern_summary...")
    try:
        summary = processor.get_pattern_summary(administration)
        print(f"✅ Pattern summary successful")
        print(f"   - Administration: {summary['administration']}")
        print(f"   - Total patterns: {summary['total_patterns']}")
        print(f"   - Pattern types: {summary['pattern_types']}")
        
    except Exception as e:
        print(f"❌ Pattern summary failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ENHANCED PATTERN ANALYSIS API TESTING COMPLETE")
    print("✅ All API methods working correctly")
    print("=" * 60)
    
    return True


if __name__ == '__main__':
    success = test_pattern_api()
    if success:
        print("\n🎉 API TESTS PASSED - Enhanced Pattern Analysis API Ready!")
        sys.exit(0)
    else:
        print("\n❌ API TESTS FAILED")
        sys.exit(1)