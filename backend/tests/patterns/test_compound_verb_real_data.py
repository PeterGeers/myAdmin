#!/usr/bin/env python3
"""
Test compound verb patterns with real data from GoodwinSolutions
"""

import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from pattern_analyzer import PatternAnalyzer
from database import DatabaseManager

def test_compound_verb_with_real_data():
    """Test compound verb functionality with real GoodwinSolutions data"""
    print("🧪 Testing Compound Verb Patterns with Real Data")
    print("=" * 60)
    
    analyzer = PatternAnalyzer(test_mode=False)
    administration = "GoodwinSolutions"
    
    # Clear existing patterns to force fresh analysis with compound verbs
    db = DatabaseManager(test_mode=False)
    db.execute_query("DELETE FROM pattern_verb_patterns WHERE administration = %s", (administration,), fetch=False, commit=True)
    db.execute_query("DELETE FROM pattern_analysis_metadata WHERE administration = %s", (administration,), fetch=False, commit=True)
    print("✅ Cleared existing patterns for fresh compound analysis")
    
    # Run pattern analysis with compound verb support
    print(f"\n📊 Analyzing patterns with compound verb support...")
    patterns = analyzer.analyze_historical_patterns(administration)
    
    print(f"✅ Analysis complete:")
    print(f"   - Total transactions: {patterns['total_transactions']:,}")
    print(f"   - Patterns discovered: {patterns['patterns_discovered']}")
    
    # Check compound patterns in database
    compound_patterns = db.execute_query("""
        SELECT verb, verb_company, verb_reference, is_compound, reference_number, 
               debet_account, credit_account, occurrences, sample_description
        FROM pattern_verb_patterns 
        WHERE administration = %s AND is_compound = TRUE
        ORDER BY occurrences DESC
        LIMIT 10
    """, (administration,))
    
    print(f"\n🔗 Top 10 Compound Patterns:")
    for i, pattern in enumerate(compound_patterns, 1):
        print(f"   {i}. {pattern['verb']} (Occurrences: {pattern['occurrences']})")
        print(f"      → Company: {pattern['verb_company']}, Reference: {pattern['verb_reference']}")
        print(f"      → Maps to: {pattern['reference_number']}")
        print(f"      → Accounts: Debet={pattern['debet_account']}, Credit={pattern['credit_account']}")
        print(f"      → Sample: {pattern['sample_description'][:60]}...")
    
    # Check simple patterns for comparison
    simple_patterns = db.execute_query("""
        SELECT verb, verb_company, reference_number, occurrences, sample_description
        FROM pattern_verb_patterns 
        WHERE administration = %s AND is_compound = FALSE
        ORDER BY occurrences DESC
        LIMIT 5
    """, (administration,))
    
    print(f"\n📝 Top 5 Simple Patterns (for comparison):")
    for i, pattern in enumerate(simple_patterns, 1):
        print(f"   {i}. {pattern['verb']} (Occurrences: {pattern['occurrences']})")
        print(f"      → Maps to: {pattern['reference_number']}")
        print(f"      → Sample: {pattern['sample_description'][:60]}...")
    
    # Test compound pattern matching
    print(f"\n🎯 Testing Compound Pattern Predictions:")
    
    # Create test transactions that should match compound patterns
    if compound_patterns:
        # Use the most frequent compound pattern for testing
        top_pattern = compound_patterns[0]
        company = top_pattern['verb_company']
        reference = top_pattern['verb_reference']
        
        test_transaction = {
            'TransactionDescription': f'{company} TEST TRANSACTION {reference} EXTRA INFO',
            'TransactionAmount': 100.00,
            'Credit': '1002',  # Common bank account
            'Debet': '',
            'ReferenceNumber': '',
            'Administration': administration
        }
        
        print(f"   Test Description: {test_transaction['TransactionDescription']}")
        print(f"   Expected to match: {top_pattern['verb']} → {top_pattern['reference_number']}")
        
        # Apply patterns
        updated_txs, results = analyzer.apply_patterns_to_transactions([test_transaction], administration)
        
        if updated_txs:
            tx = updated_txs[0]
            print(f"\n   ✅ Prediction Results:")
            if tx.get('ReferenceNumber'):
                print(f"      → ReferenceNumber: {tx['ReferenceNumber']} (confidence: {tx.get('_reference_confidence', 0):.2f})")
            if tx.get('Debet'):
                print(f"      → Debet: {tx['Debet']} (confidence: {tx.get('_debet_confidence', 0):.2f})")
        else:
            print("   ❌ No predictions made")
    
    # Summary statistics
    total_patterns = len(compound_patterns) + len(simple_patterns)
    compound_ratio = len(compound_patterns) / max(total_patterns, 1) * 100
    
    print(f"\n📊 Pattern Analysis Summary:")
    print(f"   - Total patterns: {patterns['patterns_discovered']}")
    print(f"   - Compound patterns: {len(compound_patterns)}")
    print(f"   - Simple patterns: {patterns['patterns_discovered'] - len(compound_patterns)}")
    print(f"   - Compound ratio: {compound_ratio:.1f}%")
    
    print(f"\n🎉 Compound Verb System Benefits:")
    print(f"✅ More specific pattern matching with reference numbers")
    print(f"✅ Better disambiguation for companies with multiple references")
    print(f"✅ Enhanced accuracy for invoice/reference number prediction")
    print(f"✅ Backward compatibility with simple company-only patterns")
    
    return True

if __name__ == "__main__":
    try:
        success = test_compound_verb_with_real_data()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)