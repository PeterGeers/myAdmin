"""
Script to apply the audit logging migration

This script creates the duplicate_decision_log table for audit logging.
Run this script to set up the audit logging system.

Requirements: 3.2, 6.4, 6.5
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database_migrations import DatabaseMigration
from database import DatabaseManager


def apply_audit_migration():
    """Apply the audit logging migration"""
    print("=" * 60)
    print("Audit Logging Migration Script")
    print("=" * 60)
    print()
    
    try:
        # Initialize migration manager
        print("Initializing database migration manager...")
        migrator = DatabaseMigration(test_mode=False)
        
        # Get migration status
        print("\nChecking migration status...")
        status = migrator.get_migration_status()
        
        print(f"Total migrations: {status['total_migrations']}")
        print(f"Applied migrations: {status['applied_migrations']}")
        print(f"Pending migrations: {status['pending_migrations']}")
        print()
        
        # Find the audit log migration
        audit_migration = None
        for migration in status['migrations']:
            if 'audit' in migration['name'].lower():
                audit_migration = migration
                break
        
        if not audit_migration:
            print("ERROR: Audit logging migration not found!")
            print("Expected migration file: 20251217130000_duplicate_decision_audit_log.json")
            return False
        
        # Check if already applied
        if audit_migration['applied']:
            print(f"✓ Audit logging migration '{audit_migration['name']}' is already applied")
            print()
            
            # Verify table exists
            print("Verifying audit log table...")
            db = DatabaseManager(test_mode=False)
            try:
                result = db.execute_query("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE() 
                    AND table_name = 'duplicate_decision_log'
                """)
                
                if result and result[0]['count'] > 0:
                    print("✓ Audit log table 'duplicate_decision_log' exists")
                    
                    # Get table info
                    columns = db.execute_query("""
                        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE()
                        AND table_name = 'duplicate_decision_log'
                        ORDER BY ORDINAL_POSITION
                    """)
                    
                    print(f"\nTable structure ({len(columns)} columns):")
                    for col in columns:
                        key_info = f" [{col['COLUMN_KEY']}]" if col['COLUMN_KEY'] else ""
                        nullable = "NULL" if col['IS_NULLABLE'] == 'YES' else "NOT NULL"
                        print(f"  - {col['COLUMN_NAME']}: {col['DATA_TYPE']} {nullable}{key_info}")
                    
                    # Get indexes
                    indexes = db.execute_query("""
                        SHOW INDEXES FROM duplicate_decision_log
                    """)
                    
                    if indexes:
                        print(f"\nIndexes ({len(indexes)}):")
                        index_names = set()
                        for idx in indexes:
                            if idx['Key_name'] not in index_names:
                                index_names.add(idx['Key_name'])
                                print(f"  - {idx['Key_name']} on {idx['Column_name']}")
                    
                    # Get row count
                    count_result = db.execute_query("SELECT COUNT(*) as count FROM duplicate_decision_log")
                    row_count = count_result[0]['count'] if count_result else 0
                    print(f"\nCurrent audit log entries: {row_count}")
                    
                else:
                    print("✗ Audit log table does not exist despite migration being marked as applied")
                    print("  You may need to run the migration again")
                    
            except Exception as e:
                print(f"✗ Error verifying table: {e}")
            
            return True
        
        # Apply the migration
        print(f"Applying migration: {audit_migration['name']}")
        print(f"Description: {audit_migration['description']}")
        print()
        
        migration_file = os.path.join(
            os.path.dirname(__file__),
            'src',
            'migrations',
            audit_migration['filename']
        )
        
        if not os.path.exists(migration_file):
            print(f"ERROR: Migration file not found: {migration_file}")
            return False
        
        print(f"Migration file: {migration_file}")
        print()
        
        # Confirm before applying
        response = input("Apply this migration? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Migration cancelled by user")
            return False
        
        print("\nApplying migration...")
        success = migrator.apply_migration(migration_file)
        
        if success:
            print("✓ Migration applied successfully!")
            print()
            
            # Verify table was created
            print("Verifying table creation...")
            db = DatabaseManager(test_mode=False)
            result = db.execute_query("""
                SELECT COUNT(*) as count 
                FROM information_schema.tables 
                WHERE table_schema = DATABASE() 
                AND table_name = 'duplicate_decision_log'
            """)
            
            if result and result[0]['count'] > 0:
                print("✓ Audit log table 'duplicate_decision_log' created successfully")
                
                # Show table structure
                columns = db.execute_query("""
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                    AND table_name = 'duplicate_decision_log'
                    ORDER BY ORDINAL_POSITION
                """)
                
                print(f"\nTable structure ({len(columns)} columns):")
                for col in columns:
                    key_info = f" [{col['COLUMN_KEY']}]" if col['COLUMN_KEY'] else ""
                    nullable = "NULL" if col['IS_NULLABLE'] == 'YES' else "NOT NULL"
                    print(f"  - {col['COLUMN_NAME']}: {col['DATA_TYPE']} {nullable}{key_info}")
                
            else:
                print("✗ Table was not created")
                return False
            
            return True
        else:
            print("✗ Migration failed")
            return False
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    print()
    success = apply_audit_migration()
    print()
    
    if success:
        print("=" * 60)
        print("Audit logging system is ready!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. The audit log table is now available")
        print("2. Duplicate decisions will be automatically logged")
        print("3. Use the audit API endpoints to query logs and generate reports")
        print("4. Run tests: pytest backend/test/test_audit_logger.py")
        print()
        return 0
    else:
        print("=" * 60)
        print("Migration failed - please check errors above")
        print("=" * 60)
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
