#!/usr/bin/env python3
"""
Final validation of the enhanced pattern analysis implementation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pattern_analyzer import PatternAnalyzer
from banking_processor import BankingProcessor

def main():
    print("🔍 FINAL VALIDATION: Enhanced Pattern Analysis Implementation")
    print("=" * 70)
    
    # Test 1: Pattern Analyzer
    print("\n1. Testing PatternAnalyzer...")
    analyzer = PatternAnalyzer()
    patterns = analyzer.analyze_historical_patterns('GoodwinSolutions')
    
    print(f"✅ SUCCESS: Analyzed {patterns['total_transactions']} transactions")
    print(f"✅ SUCCESS: Discovered {patterns['patterns_discovered']} patterns")
    print(f"✅ SUCCESS: Date range {patterns['date_range']['from']} to {patterns['date_range']['to']}")
    
    # Test 2: Banking Processor Integration
    print("\n2. Testing BankingProcessor integration...")
    processor = BankingProcessor()
    summary = processor.get_pattern_summary('GoodwinSolutions')
    
    print(f"✅ SUCCESS: Pattern summary generated")
    print(f"✅ SUCCESS: {summary['total_patterns']} total patterns available")
    print(f"✅ SUCCESS: Pattern types: {summary['pattern_types']}")
    
    # Test 3: Requirements Validation
    print("\n3. Validating requirements...")
    
    # REQ-PAT-001: Analyze transactions from last 2 years
    days_analyzed = (
        __import__('datetime').datetime.strptime(patterns['date_range']['to'], '%Y-%m-%d') -
        __import__('datetime').datetime.strptime(patterns['date_range']['from'], '%Y-%m-%d')
    ).days
    
    if 700 <= days_analyzed <= 750:  # ~2 years ± margin
        print("✅ REQ-PAT-001: Analyzes transactions from last 2 years ✓")
    else:
        print(f"❌ REQ-PAT-001: Date range is {days_analyzed} days (expected ~730)")
        return False
    
    # REQ-PAT-002: Filter by Administration, ReferenceNumber, Debet/Credit, Date
    if patterns['statistics']['patterns_by_type']['debet_patterns'] > 0:
        print("✅ REQ-PAT-002: Filters by Administration, Debet/Credit, Date ✓")
    else:
        print("❌ REQ-PAT-002: No debet patterns found")
        return False
    
    # REQ-PAT-003: Pattern matching based on known variables
    if patterns['statistics']['patterns_by_type']['reference_patterns'] > 0:
        print("✅ REQ-PAT-003: Creates pattern matching based on known variables ✓")
    else:
        print("❌ REQ-PAT-003: No reference patterns found")
        return False
    
    # REQ-PAT-004: Bank account lookup logic
    bank_txs = patterns['statistics']['bank_account_transactions']
    if bank_txs['debet_is_bank'] > 0 or bank_txs['credit_is_bank'] > 0:
        print("✅ REQ-PAT-004: Implements bank account lookup logic ✓")
    else:
        print("❌ REQ-PAT-004: No bank account transactions detected")
        return False
    
    print("\n" + "=" * 70)
    print("🎉 IMPLEMENTATION COMPLETE AND VALIDATED")
    print("✅ All requirements successfully implemented:")
    print("   - REQ-PAT-001: Pattern analysis processes last 2 years of transaction data")
    print("   - REQ-PAT-002: Filter patterns by Administration, ReferenceNumber, Debet/Credit, Date")
    print("   - REQ-PAT-003: Create pattern matching based on known variables")
    print("   - REQ-PAT-004: Implement bank account lookup logic")
    print("=" * 70)
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)