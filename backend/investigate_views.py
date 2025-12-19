#!/usr/bin/env python3
"""
Database View Investigation Script
Part of Phase 1: Database Investigation & Cleanup
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def investigate_database_views():
    """Investigate database views for pattern analysis"""
    print("=" * 60)
    print("Database View Investigation")
    print("=" * 60)
    
    try:
        # Initialize database manager
        db = DatabaseManager(test_mode=False)
        
        print("\n1. Checking for reference-related views...")
        
        # Check for views with 'reference' in the name
        views_query = """
            SELECT TABLE_NAME, TABLE_TYPE 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME LIKE '%reference%'
            ORDER BY TABLE_NAME
        """
        
        reference_views = db.execute_query(views_query)
        
        if reference_views:
            print(f"Found {len(reference_views)} reference-related objects:")
            for view in reference_views:
                print(f"  - {view['TABLE_NAME']} ({view['TABLE_TYPE']})")
        else:
            print("No reference-related views found")
        
        print("\n2. Checking what the code expects vs what exists...")
        
        # Test the current code's query
        print("\nTesting current code query (vw_ReadReferences):")
        try:
            result = db.execute_query("""
                SELECT COUNT(*) as count FROM vw_ReadReferences LIMIT 1
            """)
            print(f"✓ vw_ReadReferences exists and has {result[0]['count']} records")
        except Exception as e:
            print(f"✗ vw_ReadReferences failed: {e}")
        
        # Test the lowercase version
        print("\nTesting lowercase version (vw_readreferences):")
        try:
            result = db.execute_query("""
                SELECT COUNT(*) as count FROM vw_readreferences LIMIT 1
            """)
            print(f"✓ vw_readreferences exists and has {result[0]['count']} records")
        except Exception as e:
            print(f"✗ vw_readreferences failed: {e}")
        
        print("\n3. Analyzing view structure...")
        
        # Get structure of existing view
        for view_name in ['vw_readreferences', 'vw_ReadReferences']:
            try:
                columns = db.execute_query(f"""
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = '{view_name}'
                    ORDER BY ORDINAL_POSITION
                """)
                
                if columns:
                    print(f"\nStructure of {view_name}:")
                    for col in columns:
                        nullable = "NULL" if col['IS_NULLABLE'] == 'YES' else "NOT NULL"
                        print(f"  - {col['COLUMN_NAME']}: {col['DATA_TYPE']} {nullable}")
                    
                    # Get sample data
                    sample = db.execute_query(f"SELECT * FROM {view_name} LIMIT 3")
                    if sample:
                        print(f"\nSample data from {view_name}:")
                        for i, row in enumerate(sample[:3]):
                            print(f"  Row {i+1}: {dict(row)}")
                
            except Exception as e:
                print(f"Could not analyze {view_name}: {e}")
        
        print("\n4. Checking for pattern analysis requirements...")
        
        # Check what fields are available for pattern analysis
        try:
            # Test the pattern query that's currently failing
            test_admin = 'GoodwinSolutions2024'  # Use a known administration
            
            for view_name in ['vw_readreferences', 'vw_ReadReferences']:
                try:
                    patterns = db.execute_query(f"""
                        SELECT debet, credit, administration, referenceNumber 
                        FROM {view_name} 
                        WHERE administration = %s AND (debet < '1300' OR credit < '1300')
                        LIMIT 5
                    """, (test_admin,))
                    
                    print(f"\n✓ Pattern query works on {view_name}")
                    print(f"  Found {len(patterns)} patterns for {test_admin}")
                    if patterns:
                        print("  Sample patterns:")
                        for pattern in patterns[:3]:
                            print(f"    - Debet: {pattern.get('debet')}, Credit: {pattern.get('credit')}, Ref: {pattern.get('referenceNumber')}")
                    
                except Exception as e:
                    print(f"✗ Pattern query failed on {view_name}: {e}")
        
        except Exception as e:
            print(f"Error testing pattern queries: {e}")
        
        print("\n" + "=" * 60)
        print("Investigation Complete")
        print("=" * 60)
        
    except Exception as e:
        print(f"Investigation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    investigate_database_views()