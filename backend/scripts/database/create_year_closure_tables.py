"""
Database migration script for Year-End Closure feature.

Creates:
1. year_closure_status table - Track year closure history
2. parameters column in rekeningschema - Store account role configuration

Usage:
    python scripts/database/create_year_closure_tables.py [--test-mode] [--dry-run]

Options:
    --test-mode: Use test database
    --dry-run: Preview changes without applying
"""

import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager


def create_year_closure_status_table(db, dry_run=False):
    """Create year_closure_status table"""
    
    create_table_sql = """
        CREATE TABLE IF NOT EXISTS year_closure_status (
            id INT AUTO_INCREMENT PRIMARY KEY,
            administration VARCHAR(50) NOT NULL,
            year INT NOT NULL,
            closed_date DATETIME NOT NULL,
            closed_by VARCHAR(255) NOT NULL,
            closure_transaction_id INT,
            opening_balance_transaction_id INT,
            notes TEXT,
            UNIQUE KEY unique_admin_year (administration, year),
            INDEX idx_administration (administration),
            INDEX idx_year (year),
            INDEX idx_closed_date (closed_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """
    
    print("\n📋 Creating year_closure_status table...")
    print(f"SQL: {create_table_sql}")
    
    if dry_run:
        print("✅ [DRY RUN] Would create year_closure_status table")
        return True
    
    try:
        db.execute_query(create_table_sql, fetch=False, commit=True)
        print("✅ year_closure_status table created successfully")
        return True
    except Exception as e:
        print(f"❌ Error creating year_closure_status table: {e}")
        return False


def add_parameters_column(db, dry_run=False):
    """Add parameters JSON column to rekeningschema table"""
    
    # First check if column already exists
    check_column_sql = """
        SELECT COUNT(*) as count
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'rekeningschema'
        AND COLUMN_NAME = 'parameters'
    """
    
    result = db.execute_query(check_column_sql)
    if result and result[0]['count'] > 0:
        print("\n✅ parameters column already exists in rekeningschema")
        return True
    
    add_column_sql = """
        ALTER TABLE rekeningschema
        ADD COLUMN parameters JSON
    """
    
    print("\n📋 Adding parameters column to rekeningschema...")
    print(f"SQL: {add_column_sql}")
    
    if dry_run:
        print("✅ [DRY RUN] Would add parameters column to rekeningschema")
        return True
    
    try:
        db.execute_query(add_column_sql, fetch=False, commit=True)
        print("✅ parameters column added successfully")
        return True
    except Exception as e:
        print(f"❌ Error adding parameters column: {e}")
        return False


def create_indexes(db, dry_run=False):
    """Create additional indexes for performance"""
    
    indexes = [
        {
            'name': 'idx_parameters_role',
            'table': 'rekeningschema',
            'sql': """
                CREATE INDEX idx_parameters_role 
                ON rekeningschema ((CAST(JSON_EXTRACT(parameters, '$.role') AS CHAR(50))))
            """
        }
    ]
    
    print("\n📋 Creating performance indexes...")
    
    for index in indexes:
        # Check if index exists
        check_index_sql = """
            SELECT COUNT(*) as count
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND INDEX_NAME = %s
        """
        
        result = db.execute_query(check_index_sql, (index['table'], index['name']))
        if result and result[0]['count'] > 0:
            print(f"✅ Index {index['name']} already exists")
            continue
        
        print(f"Creating index: {index['name']}")
        print(f"SQL: {index['sql']}")
        
        if dry_run:
            print(f"✅ [DRY RUN] Would create index {index['name']}")
            continue
        
        try:
            db.execute_query(index['sql'], fetch=False, commit=True)
            print(f"✅ Index {index['name']} created successfully")
        except Exception as e:
            # Index creation might fail on older MySQL versions, log but continue
            print(f"⚠️ Warning: Could not create index {index['name']}: {e}")
    
    return True


def verify_tables(db):
    """Verify tables were created correctly"""
    
    print("\n🔍 Verifying table structure...")
    
    # Check year_closure_status table
    check_table_sql = """
        SELECT COUNT(*) as count
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'year_closure_status'
    """
    
    result = db.execute_query(check_table_sql)
    if not result or result[0]['count'] == 0:
        print("❌ year_closure_status table not found")
        return False
    
    print("✅ year_closure_status table exists")
    
    # Check parameters column
    check_column_sql = """
        SELECT COUNT(*) as count
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'rekeningschema'
        AND COLUMN_NAME = 'parameters'
    """
    
    result = db.execute_query(check_column_sql)
    if not result or result[0]['count'] == 0:
        print("❌ parameters column not found in rekeningschema")
        return False
    
    print("✅ parameters column exists in rekeningschema")
    
    # Show table structure
    print("\n📊 year_closure_status table structure:")
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
    print("Year-End Closure Database Migration")
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
    
    # Run migrations
    success = True
    
    # Step 1: Create year_closure_status table
    if not create_year_closure_status_table(db, dry_run):
        success = False
    
    # Step 2: Add parameters column to rekeningschema
    if not add_parameters_column(db, dry_run):
        success = False
    
    # Step 3: Create indexes
    if not create_indexes(db, dry_run):
        success = False
    
    # Step 4: Verify (only if not dry run)
    if not dry_run and success:
        if not verify_tables(db):
            success = False
    
    # Summary
    print("\n" + "=" * 60)
    if dry_run:
        print("✅ DRY RUN COMPLETE - No changes made")
    elif success:
        print("✅ MIGRATION COMPLETE - All changes applied successfully")
    else:
        print("❌ MIGRATION FAILED - Some changes may not have been applied")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
