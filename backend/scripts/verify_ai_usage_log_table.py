#!/usr/bin/env python3
"""
Verify ai_usage_log table structure
Part of Phase 2.6: Template Preview and Validation - AI Template Assistant
"""

import os
import sys
from pathlib import Path

# Add backend/src to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / 'src'))

from dotenv import load_dotenv
from database import DatabaseManager

# Load environment variables
load_dotenv(backend_dir / '.env')


def verify_table():
    """Verify the ai_usage_log table structure"""
    
    print("=" * 60)
    print("Verifying ai_usage_log table")
    print("=" * 60)
    
    try:
        db = DatabaseManager()
        
        # Check table exists
        print("\n1. Checking if table exists...")
        result = db.execute_query("""
            SELECT COUNT(*) as count 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'ai_usage_log'
        """)
        
        if result[0]['count'] == 0:
            print("❌ Table does not exist!")
            return False
        
        print("✅ Table exists")
        
        # Check columns
        print("\n2. Checking table structure...")
        columns = db.execute_query("DESCRIBE ai_usage_log")
        
        expected_columns = {
            'id': 'int',
            'administration': 'varchar(100)',
            'feature': 'varchar(100)',
            'tokens_used': 'int',
            'cost_estimate': 'decimal(10,6)',
            'created_at': 'timestamp'
        }
        
        print("\n   Column Structure:")
        for col in columns:
            col_name = col['Field']
            col_type = col['Type'].decode('utf-8') if isinstance(col['Type'], bytes) else col['Type']
            print(f"   - {col_name}: {col_type}")
            
            if col_name in expected_columns:
                # Normalize type comparison (handle unsigned, etc.)
                expected_type = expected_columns[col_name].lower()
                actual_type = col_type.lower()
                
                # Check if types match (allowing for variations like "int" vs "int unsigned")
                if expected_type in actual_type or actual_type.startswith(expected_type):
                    print(f"     ✅ Correct type")
                else:
                    print(f"     ⚠️  Expected: {expected_columns[col_name]}, Got: {col_type}")
        
        # Check indexes
        print("\n3. Checking indexes...")
        indexes = db.execute_query("""
            SELECT 
                INDEX_NAME,
                COLUMN_NAME,
                SEQ_IN_INDEX,
                NON_UNIQUE
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'ai_usage_log'
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """)
        
        print("\n   Indexes:")
        current_index = None
        for idx in indexes:
            if idx['INDEX_NAME'] != current_index:
                current_index = idx['INDEX_NAME']
                unique = "UNIQUE" if idx['NON_UNIQUE'] == 0 else "NON-UNIQUE"
                print(f"\n   - {current_index} ({unique}):")
            print(f"     Column {idx['SEQ_IN_INDEX']}: {idx['COLUMN_NAME']}")
        
        # Verify expected indexes
        expected_indexes = {
            'PRIMARY': ['id'],
            'idx_administration': ['administration'],
            'idx_created_at': ['created_at']
        }
        
        print("\n4. Verifying expected indexes...")
        index_dict = {}
        for idx in indexes:
            if idx['INDEX_NAME'] not in index_dict:
                index_dict[idx['INDEX_NAME']] = []
            index_dict[idx['INDEX_NAME']].append(idx['COLUMN_NAME'])
        
        all_good = True
        for idx_name, expected_cols in expected_indexes.items():
            if idx_name in index_dict:
                if index_dict[idx_name] == expected_cols:
                    print(f"   ✅ {idx_name}: {', '.join(expected_cols)}")
                else:
                    print(f"   ⚠️  {idx_name}: Expected {expected_cols}, Got {index_dict[idx_name]}")
                    all_good = False
            else:
                print(f"   ❌ {idx_name}: Missing!")
                all_good = False
        
        # Test basic operations
        print("\n5. Testing basic operations...")
        
        # Test INSERT
        print("   Testing INSERT...")
        db.execute_query("""
            INSERT INTO ai_usage_log 
            (administration, feature, tokens_used, cost_estimate) 
            VALUES ('test_tenant', 'template_validation', 1000, 0.002000)
        """, fetch=False, commit=True)
        print("   ✅ INSERT successful")
        
        # Test SELECT
        print("   Testing SELECT...")
        result = db.execute_query("""
            SELECT * FROM ai_usage_log 
            WHERE administration = 'test_tenant' 
            ORDER BY id DESC LIMIT 1
        """)
        if result and len(result) > 0:
            print(f"   ✅ SELECT successful - Found record: {result[0]}")
        else:
            print("   ❌ SELECT failed - No records found")
            all_good = False
        
        # Test DELETE (cleanup)
        print("   Cleaning up test data...")
        db.execute_query("""
            DELETE FROM ai_usage_log 
            WHERE administration = 'test_tenant'
        """, fetch=False, commit=True)
        print("   ✅ DELETE successful")
        
        print("\n" + "=" * 60)
        if all_good:
            print("✅ All verifications passed!")
        else:
            print("⚠️  Some issues found")
        print("=" * 60)
        
        return all_good
    
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = verify_table()
    sys.exit(0 if success else 1)
