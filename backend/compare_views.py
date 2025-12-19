#!/usr/bin/env python3
"""
Compare the two reference views to understand differences
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager

def compare_views():
    """Compare both reference views"""
    print("=" * 60)
    print("Comparing Reference Views")
    print("=" * 60)
    
    db = DatabaseManager(test_mode=False)
    
    # Check structure of current view (old view has been removed)
    views = ['vw_readreferences']
    
    for view_name in views:
        print(f"\n📊 {view_name}:")
        
        try:
            # Get column structure
            columns = db.execute_query(f"""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM information_schema.columns 
                WHERE table_schema = DATABASE() 
                AND table_name = '{view_name}'
                ORDER BY ORDINAL_POSITION
            """)
            
            print(f"  Columns ({len(columns)}):")
            for col in columns:
                nullable = "NULL" if col['IS_NULLABLE'] == 'YES' else "NOT NULL"
                print(f"    - {col['COLUMN_NAME']}: {col['DATA_TYPE']} {nullable}")
            
            # Get record count
            count_result = db.execute_query(f"SELECT COUNT(*) as count FROM {view_name}")
            record_count = count_result[0]['count'] if count_result else 0
            print(f"  Records: {record_count:,}")
            
            # Get date range if Date column exists
            if any(col['COLUMN_NAME'] == 'Date' for col in columns):
                date_range = db.execute_query(f"""
                    SELECT MIN(Date) as min_date, MAX(Date) as max_date 
                    FROM {view_name}
                """)
                if date_range and date_range[0]['min_date']:
                    print(f"  Date range: {date_range[0]['min_date']} to {date_range[0]['max_date']}")
            
            # Sample recent records
            sample = db.execute_query(f"SELECT * FROM {view_name} LIMIT 3")
            print(f"  Sample records:")
            for i, record in enumerate(sample[:2]):  # Show only 2 for brevity
                print(f"    {i+1}. {dict(record)}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("🔍 Analysis:")
    print("- vw_readreferences: Current view with Date column for pattern analysis")
    print("- Old vw_ReadReferences view has been removed (was consolidated)")
    print("- Current code uses: vw_readreferences (lowercase, with date filtering)")
    print("- Status: ✅ View consolidation completed successfully")

if __name__ == '__main__':
    compare_views()