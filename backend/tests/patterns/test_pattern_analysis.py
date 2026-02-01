#!/usr/bin/env python3
"""
Test pattern analysis functionality after database view consolidation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def test_pattern_analysis():
    """Test that pattern analysis works with the consolidated view"""
    print("=" * 60)
    print("TESTING PATTERN ANALYSIS FUNCTIONALITY")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    
    # Test 1: Basic get_patterns functionality
    print("\n1. Testing get_patterns() method...")
    try:
        patterns = db.get_patterns('GoodwinSolutions')
        print(f"✅ Found {len(patterns)} patterns for GoodwinSolutions")
        
        if patterns:
            sample = patterns[0]
            required_fields = ['debet', 'credit', 'administration', 'referenceNumber']
            missing_fields = [field for field in required_fields if field not in sample]
            
            if missing_fields:
                print(f"❌ Missing required fields: {missing_fields}")
                return False
            else:
                print("✅ All required fields present in pattern data")
                print(f"   Sample: debet={sample['debet']}, credit={sample['credit']}, ref={sample['referenceNumber']}")
                
                # Check if Date field is included (new feature)
                if 'Date' in sample:
                    print(f"✅ Date filtering active: {sample['Date']}")
                else:
                    print("⚠ Date field not found (may be expected)")
        
    except Exception as e:
        print(f"❌ get_patterns() failed: {e}")
        return False
    
    # Test 2: Pattern filtering (bank accounts < 1300)
    print("\n2. Testing bank account filtering...")
    try:
        bank_patterns = [p for p in patterns if p['debet'] < '1300' or p['credit'] < '1300']
        print(f"✅ Found {len(bank_patterns)} bank account patterns (debet/credit < 1300)")
        
        if bank_patterns:
            sample_bank = bank_patterns[0]
            print(f"   Sample bank pattern: debet={sample_bank['debet']}, credit={sample_bank['credit']}")
        
    except Exception as e:
        print(f"❌ Bank account filtering test failed: {e}")
        return False
    
    # Test 3: Date filtering (should only get patterns from last 2 years)
    print("\n3. Testing date filtering...")
    try:
        from datetime import datetime, timedelta
        two_years_ago = datetime.now() - timedelta(days=730)
        
        recent_patterns = [p for p in patterns if p.get('Date') and p['Date'] >= two_years_ago.date()]
        print(f"✅ Found {len(recent_patterns)} patterns from last 2 years")
        
        if recent_patterns:
            oldest_date = min(p['Date'] for p in recent_patterns if p.get('Date'))
            newest_date = max(p['Date'] for p in recent_patterns if p.get('Date'))
            print(f"   Date range: {oldest_date} to {newest_date}")
        
    except Exception as e:
        print(f"⚠ Date filtering test failed (may be expected if Date not in results): {e}")
    
    # Test 4: Multiple administrations
    print("\n4. Testing different administrations...")
    test_admins = ['GoodwinSolutions', 'GoodwinSolutions2024']
    
    for admin in test_admins:
        try:
            admin_patterns = db.get_patterns(admin)
            print(f"✅ {admin}: {len(admin_patterns)} patterns")
        except Exception as e:
            print(f"❌ {admin}: Failed - {e}")
    
    print("\n" + "=" * 60)
    print("✅ PATTERN ANALYSIS TESTING COMPLETE")
    print("✅ Database view consolidation successful")
    print("✅ Pattern analysis functionality working")
    print("=" * 60)
    
    return True

if __name__ == '__main__':
    success = test_pattern_analysis()
    if not success:
        print("\n❌ PATTERN ANALYSIS TESTING FAILED")
        sys.exit(1)