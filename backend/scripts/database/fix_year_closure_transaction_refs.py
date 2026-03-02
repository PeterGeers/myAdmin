"""
Fix year_closure_status table to use TransactionNumber instead of transaction IDs.

Problem: Opening balance transactions create MULTIPLE records (one per account),
all sharing the same TransactionNumber. We should reference the TransactionNumber,
not a single transaction ID.

Changes:
- closure_transaction_id INT -> closure_transaction_number VARCHAR(50)
- opening_balance_transaction_id INT -> opening_balance_transaction_number VARCHAR(50)

Usage:
    python scripts/database/fix_year_closure_transaction_refs.py [--test-mode] [--dry-run]
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager


def fix_transaction_references(db, dry_run=False):
    """Change transaction ID columns to TransactionNumber columns"""
    
    print("\n📋 Modifying year_closure_status table...")
    
    # Check if old columns exist
    check_columns_sql = """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'year_closure_status'
        AND COLUMN_NAME IN ('closure_transaction_id', 'opening_balance_transaction_id',
                            'closure_transaction_number', 'opening_balance_transaction_number')
    """
    
    existing_columns = db.execute_query(check_columns_sql)
    column_names = [col['COLUMN_NAME'] for col in existing_columns] if existing_columns else []
    
    print(f"Existing columns: {column_names}")
    
    # Check if we need to migrate
    has_old_columns = 'closure_transaction_id' in column_names or 'opening_balance_transaction_id' in column_names
    has_new_columns = 'closure_transaction_number' in column_names or 'opening_balance_transaction_number' in column_names
    
    if has_new_columns and not has_old_columns:
        print("✅ Table already has correct structure (TransactionNumber columns)")
        return True
    
    if not has_old_columns and not has_new_columns:
        print("❌ Table doesn't have expected columns")
        return False
    
    # Migration needed
    alter_sql = """
        ALTER TABLE year_closure_status
        DROP COLUMN closure_transaction_id,
        DROP COLUMN opening_balance_transaction_id,
        ADD COLUMN closure_transaction_number VARCHAR(50),
        ADD COLUMN opening_balance_transaction_number VARCHAR(50),
        ADD INDEX idx_closure_txn (closure_transaction_number),
        ADD INDEX idx_opening_txn (opening_balance_transaction_number)
    """
    
    print(f"\nSQL: {alter_sql}")
    
    if dry_run:
        print("✅ [DRY RUN] Would modify year_closure_status table")
        print("   - Drop: closure_transaction_id (INT)")
        print("   - Drop: opening_balance_transaction_id (INT)")
        print("   - Add: closure_transaction_number (VARCHAR(50))")
        print("   - Add: opening_balance_transaction_number (VARCHAR(50))")
        print("   - Add indexes on new columns")
        return True
    
    try:
        db.execute_query(alter_sql, fetch=False, commit=True)
        print("✅ year_closure_status table modified successfully")
        return True
    except Exception as e:
        print(f"❌ Error modifying table: {e}")
        return False


def verify_structure(db):
    """Verify table has correct structure"""
    
    print("\n🔍 Verifying table structure...")
    
    # Check new columns exist
    check_columns_sql = """
        SELECT COLUMN_NAME, COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'year_closure_status'
        AND COLUMN_NAME IN ('closure_transaction_number', 'opening_balance_transaction_number')
    """
    
    columns = db.execute_query(check_columns_sql)
    
    if not columns or len(columns) != 2:
        print("❌ New columns not found")
        return False
    
    for col in columns:
        print(f"✅ {col['COLUMN_NAME']}: {col['COLUMN_TYPE']}")
    
    # Check old columns are gone
    check_old_sql = """
        SELECT COUNT(*) as count
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'year_closure_status'
        AND COLUMN_NAME IN ('closure_transaction_id', 'opening_balance_transaction_id')
    """
    
    result = db.execute_query(check_old_sql)
    if result and result[0]['count'] > 0:
        print("⚠️ Warning: Old columns still exist")
        return False
    
    print("✅ Old columns removed")
    
    # Show full table structure
    print("\n📊 Full table structure:")
    describe_sql = "DESCRIBE year_closure_status"
    columns = db.execute_query(describe_sql)
    for col in columns:
        print(f"  - {col['Field']}: {col['Type']} {col['Null']} {col['Key']}")
    
    return True


def main():
    """Main migration function"""
    
    # Parse command line arguments
    test_mode = '--test-mode' in sys.argv
    dry_run = '--dry-run' in sys.argv
    
    print("=" * 60)
    print("Fix Year Closure Transaction References")
    print("=" * 60)
    print(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")
    print(f"Dry Run: {'YES' if dry_run else 'NO'}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    if not dry_run:
        confirm = input("\n⚠️  This will modify the database. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ Migration cancelled")
            return 1
    
    # Initialize database connection
    try:
        db = DatabaseManager(test_mode=test_mode)
        print(f"\n✅ Connected to database: {db.config['database']}")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return 1
    
    # Run migration
    success = fix_transaction_references(db, dry_run)
    
    # Verify (only if not dry run)
    if not dry_run and success:
        if not verify_structure(db):
            success = False
    
    # Summary
    print("\n" + "=" * 60)
    if dry_run:
        print("✅ DRY RUN COMPLETE - No changes made")
    elif success:
        print("✅ MIGRATION COMPLETE - Table structure fixed")
    else:
        print("❌ MIGRATION FAILED")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
