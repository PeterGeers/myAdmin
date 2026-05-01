#!/usr/bin/env python3
"""
Apply schema migration: Add parameters column to rekeningschema table.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database import DatabaseManager
from dialect_helpers import dialect


def check_column_exists(db_manager):
    """Check if parameters column already exists."""
    result = db_manager.execute_query("""
        SELECT COUNT(*) as count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'rekeningschema'
        AND COLUMN_NAME = 'parameters'
    """)

    return result and result[0]['count'] > 0


def apply_migration():
    """Apply the schema migration."""
    print("=" * 60)
    print("Schema Migration: Add parameters column")
    print("=" * 60)
    print(f"Database: {os.getenv('DB_NAME', 'myAdmin')}")
    print(f"Host: {os.getenv('DB_HOST', 'localhost')}")
    print()

    # Initialize database manager
    db_manager = DatabaseManager()

    # Check if already applied
    if check_column_exists(db_manager):
        print("✓ Migration already applied - parameters column exists")
        return 0

    print("Applying migration...")

    try:
        # Add parameters column
        print("  Adding parameters column...")
        db_manager.execute_query("""
            ALTER TABLE rekeningschema 
            ADD COLUMN parameters JSON DEFAULT NULL 
            COMMENT 'JSON configuration for account roles (e.g., {"roles": ["equity_result", "pl_closing"]})'
        """, fetch=False, commit=True)
        print("  ✓ Column added")

        # Add index using dialect helper for JSON_EXTRACT
        print("  Adding index on parameters...")
        je_roles = dialect.json_extract('parameters', '$.roles')
        db_manager.execute_query(f"""
            CREATE INDEX idx_parameters_roles ON rekeningschema 
            ((CAST({je_roles} AS CHAR(255) ARRAY)))
        """, fetch=False, commit=True)
        print("  ✓ Index added")

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
        return 1


def main():
    """Main entry point."""
    return apply_migration()


if __name__ == "__main__":
    sys.exit(main())
