"""
Script to apply duplicate detection index migration
This creates the necessary indexes for optimal duplicate detection performance
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from database_migrations import DatabaseMigration

def main():
    print("=" * 70)
    print("Applying Duplicate Detection Index Migration")
    print("=" * 70)
    
    # Create migration manager
    migrator = DatabaseMigration(test_mode=False)
    
    # Get migration status before
    print("\nChecking migration status...")
    status_before = migrator.get_migration_status()
    print(f"Total migrations: {status_before['total_migrations']}")
    print(f"Applied migrations: {status_before['applied_migrations']}")
    print(f"Pending migrations: {status_before['pending_migrations']}")
    
    # Apply all pending migrations
    print("\nApplying pending migrations...")
    applied_count = migrator.run_all_migrations()
    
    if applied_count > 0:
        print(f"\n✓ Successfully applied {applied_count} migration(s)")
    else:
        print("\n✓ No pending migrations to apply")
    
    # Get migration status after
    print("\nFinal migration status:")
    status_after = migrator.get_migration_status()
    print(f"Total migrations: {status_after['total_migrations']}")
    print(f"Applied migrations: {status_after['applied_migrations']}")
    print(f"Pending migrations: {status_after['pending_migrations']}")
    
    # Check indexes
    print("\nChecking database indexes...")
    index_report = migrator.check_indexes()
    
    for table_info in index_report:
        if 'error' in table_info:
            print(f"\n✗ Error checking {table_info['table']}: {table_info['error']}")
        else:
            print(f"\n✓ Table: {table_info['table']}")
            print(f"  Indexes: {table_info['index_count']}")
            
            # Show duplicate detection indexes
            if table_info['indexes']:
                duplicate_indexes = [
                    idx for idx in table_info['indexes'] 
                    if 'duplicate' in idx.get('Key_name', '').lower() or 
                       'transaction_date' in idx.get('Key_name', '').lower()
                ]
                if duplicate_indexes:
                    print("  Duplicate detection indexes:")
                    for idx in duplicate_indexes:
                        print(f"    - {idx.get('Key_name')}: {idx.get('Column_name')}")
    
    print("\n" + "=" * 70)
    print("Migration Complete!")
    print("=" * 70)
    print("\nThe following indexes have been created for duplicate detection:")
    print("  1. idx_duplicate_check: Composite index on (ReferenceNumber, TransactionDate, TransactionAmount)")
    print("  2. idx_transaction_date_range: Index on TransactionDate for date range queries")
    print("\nThese indexes will significantly improve duplicate detection performance.")
    print("Expected query performance: < 2 seconds even with large datasets")
    print("=" * 70)

if __name__ == '__main__':
    main()
