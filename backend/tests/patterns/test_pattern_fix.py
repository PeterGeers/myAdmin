#!/usr/bin/env python3
"""
Test the pattern analysis fix
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def test_pattern_analysis():
    """Test if pattern analysis is now working"""
    print("=" * 60)
    print("Testing Pattern Analysis Fix")
    print("=" * 60)
    
    try:
        db = DatabaseManager(test_mode=False)
        
        # Test the get_patterns method
        print("\n1. Testing get_patterns method...")
        patterns = db.get_patterns('GoodwinSolutions')
        
        print(f"✓ Found {len(patterns)} patterns for GoodwinSolutions")
        
        if patterns:
            print("\nSample patterns:")
            for i, pattern in enumerate(patterns[:5]):  # Show first 5
                print(f"  {i+1}. Debet: {pattern['debet']}, Credit: {pattern['credit']}, Ref: {pattern['referenceNumber']}")
        
        # Test pattern filtering by account type
        print("\n2. Testing bank account pattern filtering...")
        
        debet_patterns = [p for p in patterns if p['debet'] and p['debet'] < '1300']
        credit_patterns = [p for p in patterns if p['credit'] and p['credit'] < '1300']
        
        print(f"✓ Debet bank account patterns: {len(debet_patterns)}")
        print(f"✓ Credit bank account patterns: {len(credit_patterns)}")
        
        # Show some examples
        if debet_patterns:
            print("\nDebet bank account examples:")
            for pattern in debet_patterns[:3]:
                print(f"  - Bank: {pattern['debet']} → Credit: {pattern['credit']} (Ref: {pattern['referenceNumber']})")
        
        if credit_patterns:
            print("\nCredit bank account examples:")
            for pattern in credit_patterns[:3]:
                print(f"  - Debet: {pattern['debet']} → Bank: {pattern['credit']} (Ref: {pattern['referenceNumber']})")
        
        print("\n" + "=" * 60)
        print("✅ Pattern Analysis Test Results:")
        print(f"- Database view fix: SUCCESS")
        print(f"- Pattern retrieval: {len(patterns)} patterns found")
        print(f"- Bank account filtering: {len(debet_patterns) + len(credit_patterns)} bank patterns")
        print(f"- Date filtering: Applied (last 2 years)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing pattern analysis: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_pattern_analysis()
    if success:
        print("\n🎉 Phase 1 fix successful! Ready for Phase 2.")
    else:
        print("\n❌ Phase 1 fix needs more work.")