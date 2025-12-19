#!/usr/bin/env python3
"""
Verify database view consolidation was successful
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def verify_consolidation():
    """Verify that only one reference view exists and it works correctly"""
    print("=" * 50)
    print("VERIFYING DATABASE VIEW CONSOLIDATION")
    print("=" * 50)
    
    db = DatabaseManager(test_mode=False)
    
    # Check for reference views
    print("\n1. Checking reference views in database...")
    views = db.execute_query("""
        SELECT TABLE_NAME, TABLE_TYPE 
        FROM information_schema.TABLES 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME LIKE '%reference%'
        ORDER BY TABLE_NAME
    """)
    
    print(f"Reference views found: {len(views)}")
    for view in views:
        print(f"  - {view['TABLE_NAME']} ({view['TABLE_TYPE']})")
    
    # Verify only one exists
    if len(views) == 1 and views[0]['TABLE_NAME'] == 'vw_readreferences':
        print("✅ SUCCESS: Only one reference view exists (vw_readreferences)")
    else:
        print("❌ ISSUE: Expected exactly one view named 'vw_readreferences'")
        return False
    
    # Test the updated get_patterns method
    print("\n2. Testing get_patterns() method...")
    try:
        patterns = db.get_patterns('GoodwinSolutions')
        print(f"✅ get_patterns() works: {len(patterns)} patterns found")
        
        if patterns:
            sample = patterns[0]
            print(f"Sample pattern: {dict(sample)}")
            
            # Check if Date column is included
            if 'Date' in sample:
                print("✅ Date column is included in results")
            else:
                print("❌ Date column missing from results")
                
    except Exception as e:
        print(f"❌ get_patterns() failed: {e}")
        return False
    
    # Test that old view is gone
    print("\n3. Verifying old view is removed...")
    try:
        db.execute_query("SELECT 1 FROM vw_ReadReferences LIMIT 1")
        print("❌ ERROR: vw_ReadReferences still exists!")
        return False
    except Exception:
        print("✅ Confirmed: vw_ReadReferences has been removed")
    
    print("\n" + "=" * 50)
    print("✅ CONSOLIDATION VERIFICATION COMPLETE")
    print("✅ Task 'Only one reference view exists in the database' - COMPLETED")
    print("=" * 50)
    
    return True

if __name__ == '__main__':
    success = verify_consolidation()
    if not success:
        print("\n❌ VERIFICATION FAILED")
        sys.exit(1)