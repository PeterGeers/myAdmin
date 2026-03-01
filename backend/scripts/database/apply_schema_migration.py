#!/usr/bin/env python3
"""
Apply schema migration: Add parameters column to rekeningschema table.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager
from src.config import Config


def check_column_exists(db_manager):
    """Check if parameters column already exists."""
    conn = db_manager.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'rekeningschema'
            AND COLUMN_NAME = 'parameters'
        """, (Config.DB_NAME,))
        
        result = cursor.fetchone()
        return result['count'] > 0
        
    finally:
        cursor.close()
        conn.close()


def apply_migration():
    """Apply the schema migration."""
    print("=" * 60)
    print("Schema Migration: Add parameters column")
    print("=" * 60)
    print(f"Database: {Config.DB_NAME}")
    print(f"Host: {Config.DB_HOST}")
    print()
    
    # Initialize database manager
    db_manager = DatabaseManager()
    
    # Check if already applied
    if check_column_exists(db_manager):
        print("✓ Migration already applied - parameters column exists")
        return 0
    
    print("Applying migration...")
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    try:
        # Add parameters column
        print("  Adding parameters column...")
        cursor.execute("""
            ALTER TABLE rekeningschema 
            ADD COLUMN parameters JSON DEFAULT NULL 
            COMMENT 'JSON configuration for account roles (e.g., {"roles": ["equity_result", "pl_closing"]})'
        """)
        print("  ✓ Column added")
        
        # Add index
        print("  Adding index on parameters...")
        cursor.execute("""
            CREATE INDEX idx_parameters_roles ON rekeningschema 
            ((CAST(JSON_EXTRACT(parameters, '$.roles') AS CHAR(255) ARRAY)))
        """)
        print("  ✓ Index added")
        
        conn.commit()
        
        print()
        print("=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Run test script: python scripts/database/test_parameters_column.py")
        print("2. Configure account roles in Chart of Accounts UI")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Error applying migration: {e}")
        conn.rollback()
        return 1
        
    finally:
        cursor.close()
        conn.close()


def main():
    """Main entry point."""
    return apply_migration()


if __name__ == "__main__":
    sys.exit(main())
