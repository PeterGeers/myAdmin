#!/usr/bin/env python3
"""
Test script to investigate database view issues
Part of Phase 1: Database Investigation & Cleanup
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def test_database_views():
    """Test database views and identify the case sensitivity issue"""
    print("=" * 60)
    print("Database View Investigation - Phase 1")
    print("=" * 60)
    
    try:
        db = DatabaseManager(test_mode=False)
        
        # Test 1: Check what views exist
        print("\n1. Checking existing views...")
        views = db.execute_query("""
            SELECT TABLE_NAME, TABLE_TYPE 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND TABLE_NAME LIKE '%reference%'
            ORDER BY TABLE_NAME
        """)
        
        print(f"Found {len(views)} view(s) with 'reference' in name:")
        for view in views:
            print(f"  - {view['TABLE_NAME']} ({view['TABLE_TYPE']})")
        
        # Test 2: Try the current code's query (should fail)
        print("\n2. Testing current code query (vw_ReadReferences)...")
        try:
            result = db.execute_query("""
                SELECT COUNT(*) as count FROM vw_ReadReferences LIMIT 1
            """)
            print(f"✓ vw_ReadReferences works: {result[0]['count']} records")
        except Exception as e:
            print(f"✗ vw_ReadReferences failed: {e}")
        
        # Test 3: Try the lowercase version
        print("\n3. Testing lowercase version (vw_readreferences)...")
        try:
            result = db.execute_query("""
                SELECT COUNT(*) as count FROM vw_readreferences LIMIT 1
            """)
            print(f"✓ vw_readreferences works: {result[0]['count']} records")
        except Exception as e:
            print(f"✗ vw_readreferences failed: {e}")
        
        # Test 4: Check view structure
        print("\n4. Checking view structure...")
        try:
            columns = db.execute_query("""
                SELECT COLUMN_NAME, DATA_TYPE 
                FROM information_schema.columns 
                WHERE table_schema = DATABASE() 
                AND table_name = 'vw_readreferences'
                ORDER BY ORDINAL_POSITION
            """)
            
            print("vw_readreferences columns:")
            for col in columns:
                print(f"  - {col['COLUMN_NAME']}: {col['DATA_TYPE']}")
                
        except Exception as e:
            print(f"Error checking structure: {e}")
        
        # Test 5: Sample data
        print("\n5. Sample data from vw_readreferences...")
        try:
            sample = db.execute_query("""
                SELECT * FROM vw_readreferences LIMIT 3
            """)
            
            if sample:
                print(f"Sample records ({len(sample)}):")
                for i, record in enumerate(sample):
                    print(f"  Record {i+1}: {dict(record)}")
            else:
                print("No sample data found")
                
        except Exception as e:
            print(f"Error getting sample data: {e}")
            
    except Exception as e:
        print(f"Database connection error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("Investigation complete!")
    return True

if __name__ == '__main__':
    test_database_views()