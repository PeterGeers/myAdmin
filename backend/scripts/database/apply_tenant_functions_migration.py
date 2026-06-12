"""
Migration: Create tenant_functions table for Tenant Optional Functions.

This table stores per-tenant function activation overrides.
Only rows where a tenant has explicitly toggled a function are stored;
absence of a row means the FUNCTION_REGISTRY default applies.

Requirements: 2.1, 2.2

Usage:
    python apply_tenant_functions_migration.py [--test]

Flags:
    --test  Run against the test database instead of production.
"""

import sys
import os

# Add backend/src to path so we can import DatabaseManager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager


DDL = """
CREATE TABLE IF NOT EXISTS tenant_functions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    function_name VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    INDEX idx_administration (administration),
    UNIQUE KEY uq_admin_function (administration, function_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def main():
    test_mode = '--test' in sys.argv
    mode_label = 'TEST' if test_mode else 'PRODUCTION'

    print("=" * 60)
    print("Tenant Functions Migration Script")
    print(f"Running against {mode_label} database...")
    print("=" * 60)
    print()

    db = DatabaseManager(test_mode=test_mode)

    # Check if table already exists
    try:
        result = db.execute_query("""
            SELECT COUNT(*) as count
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'tenant_functions'
        """)

        if result and result[0]['count'] > 0:
            print("✅ Table 'tenant_functions' already exists.")
            print()
            _verify_table(db)
            return
    except Exception as e:
        print(f"⚠️  Could not check existing tables: {e}")
        print("Proceeding with CREATE TABLE IF NOT EXISTS...")
        print()

    # Create the table
    try:
        db.execute_query(DDL, fetch=False, commit=True)
        print("✅ tenant_functions table created successfully.")
        print()
        _verify_table(db)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)


def _verify_table(db):
    """Verify the table structure and indexes."""
    print("Verifying table structure...")
    print()

    try:
        columns = db.execute_query("""
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'tenant_functions'
            ORDER BY ORDINAL_POSITION
        """)

        if columns:
            print(f"  Columns ({len(columns)}):")
            for col in columns:
                nullable = "NULL" if col['IS_NULLABLE'] == 'YES' else "NOT NULL"
                key = f" [{col['COLUMN_KEY']}]" if col['COLUMN_KEY'] else ""
                default = f" DEFAULT {col['COLUMN_DEFAULT']}" if col['COLUMN_DEFAULT'] else ""
                print(f"    - {col['COLUMN_NAME']}: {col['COLUMN_TYPE']} {nullable}{key}{default}")
            print()

        indexes = db.execute_query("""
            SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
            AND table_name = 'tenant_functions'
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """)

        if indexes:
            print(f"  Indexes ({len(indexes)}):")
            seen = set()
            for idx in indexes:
                key = f"{idx['INDEX_NAME']}({idx['COLUMN_NAME']})"
                if key not in seen:
                    seen.add(key)
                    unique = "UNIQUE" if not idx['NON_UNIQUE'] else "INDEX"
                    print(f"    - {idx['INDEX_NAME']}: {unique} on {idx['COLUMN_NAME']}")
            print()

        print("✅ Verification complete.")

    except Exception as e:
        print(f"⚠️  Verification failed: {e}")
        print("   The table may still have been created correctly.")


if __name__ == '__main__':
    main()
