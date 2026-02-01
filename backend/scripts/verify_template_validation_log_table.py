#!/usr/bin/env python3
"""
Verify template_validation_log table structure
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
    """Verify the template_validation_log table structure"""
    
    print("=" * 60)
    print("Verifying template_validation_log table")
    print("=" * 60)
    
    try:
        db = DatabaseManager()
        
        # Check table exists
        print("\n1. Checking if table exists...")
        result = db.execute_query("""
            SELECT COUNT(*) as count 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'template_validation_log'
        """)
        
        if result[0]['count'] == 0:
            print("❌ Table does not exist!")
            return False
        
        print("✅ Table exists")
        
        # Check columns
        print("\n2. Checking table structure...")
        columns = db.execute_query("DESCRIBE template_validation_log")
        
        expected_columns = {
            'id': 'int',
            'administration': 'varchar(100)',
            'template_type': 'varchar(50)',
            'validation_result': "enum('success','warning','error')",
            'errors': 'json',
            'warnings': 'json',
            'validated_by': 'varchar(255)',
            'validated_at': 'timestamp'
        }
        
        print("\n   Column Structure:")
        for col in columns:
            col_name = col['Field']
            col_type = col['Type'].decode('utf-8') if isinstance(col['Type'], bytes) else col['Type']
            print(f"   - {col_name}: {col_type}")
            
            if col_name in expected_columns:
                if col_type.lower() == expected_columns[col_name].lower():
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
            AND TABLE_NAME = 'template_validation_log'
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
            'idx_administration_template': ['administration', 'template_type'],
            'idx_validated_at': ['validated_at']
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
