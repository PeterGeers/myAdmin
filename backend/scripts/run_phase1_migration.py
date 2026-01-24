#!/usr/bin/env python3
"""
Phase 1 Multi-Tenant Migration Script

This script executes the Phase 1 database schema migration for multi-tenant support.
It adds the 'administration' field to all required tables and creates the tenant_config table.

Usage:
    python backend/scripts/run_phase1_migration.py [--dry-run] [--backup]

Options:
    --dry-run    Show what would be executed without making changes
    --backup     Create a backup before running migration
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path to import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager
import mysql.connector

class Phase1Migration:
    def __init__(self, dry_run=False, backup=False):
        self.dry_run = dry_run
        self.backup = backup
        self.db = DatabaseManager()
        self.migration_file = os.path.join(
            os.path.dirname(__file__), 
            '..', 
            'sql', 
            'phase1_multitenant_schema.sql'
        )
        
    def create_backup(self):
        """Create a database backup before migration"""
        if not self.backup:
            return True
            
        print("📦 Creating database backup...")
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"backup_before_phase1_{timestamp}.sql"
            
            # Get database config
            config = self.db.config
            
            # Use mysqldump to create backup
            cmd = f"mysqldump -h {config['host']} -u {config['user']} "
            if config['password']:
                cmd += f"-p{config['password']} "
            cmd += f"{config['database']} > {backup_file}"
            
            os.system(cmd)
            print(f"✅ Backup created: {backup_file}")
            return True
            
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return False
    
    def check_prerequisites(self):
        """Check if database is ready for migration"""
        print("🔍 Checking prerequisites...")
        
        try:
            # Check if database connection works
            with self.db.get_cursor() as (cursor, conn):
                cursor.execute("SELECT 1")
                result = cursor.fetchall()  # Consume the result
                
            print("✅ Database connection successful")
            
            # Check if required tables exist
            required_tables = [
                'bnb', 'bnbfuture', 'bnblookup', 'bnbplanned',
                'listings', 'pricing_events', 'pricing_recommendations',
                'mutaties', 'rekeningschema'
            ]
            
            with self.db.get_cursor() as (cursor, conn):
                cursor.execute("""
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = DATABASE()
                """)
                existing_tables = [row['TABLE_NAME'] for row in cursor.fetchall()]
            
            missing_tables = [t for t in required_tables if t not in existing_tables]
            
            if missing_tables:
                print(f"⚠️  Warning: Some tables don't exist yet: {', '.join(missing_tables)}")
                print("   Migration will skip these tables.")
            else:
                print("✅ All required tables exist")
            
            return True
            
        except Exception as e:
            print(f"❌ Prerequisites check failed: {e}")
            return False
    
    def read_migration_file(self):
        """Read the SQL migration file"""
        try:
            with open(self.migration_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"❌ Failed to read migration file: {e}")
            return None
    
    def execute_migration(self):
        """Execute the migration SQL"""
        print("🚀 Starting Phase 1 migration...")
        
        if self.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        
        # Read migration file
        sql_content = self.read_migration_file()
        if not sql_content:
            return False
        
        # Split into individual statements
        statements = []
        current_statement = []
        in_delimiter_block = False
        
        for line in sql_content.split('\n'):
            stripped = line.strip()
            
            # Skip comments and empty lines
            if not stripped or stripped.startswith('--'):
                continue
            
            # Handle delimiter blocks (for stored procedures, etc.)
            if 'DELIMITER' in stripped.upper():
                in_delimiter_block = not in_delimiter_block
                continue
            
            current_statement.append(line)
            
            # Check for statement end
            if not in_delimiter_block and stripped.endswith(';'):
                stmt = '\n'.join(current_statement)
                if stmt.strip():
                    statements.append(stmt)
                current_statement = []
        
        # Add any remaining statement
        if current_statement:
            stmt = '\n'.join(current_statement)
            if stmt.strip():
                statements.append(stmt)
        
        print(f"📝 Found {len(statements)} SQL statements to execute")
        
        if self.dry_run:
            print("\n--- SQL STATEMENTS TO BE EXECUTED ---")
            for i, stmt in enumerate(statements[:5], 1):  # Show first 5
                print(f"\n{i}. {stmt[:200]}...")
            if len(statements) > 5:
                print(f"\n... and {len(statements) - 5} more statements")
            return True
        
        # Execute migration
        success_count = 0
        error_count = 0
        
        try:
            with self.db.get_cursor() as (cursor, conn):
                for i, statement in enumerate(statements, 1):
                    try:
                        # Execute statement
                        cursor.execute(statement)
                        
                        # Fetch results if any (for SELECT statements)
                        if cursor.description:
                            results = cursor.fetchall()
                            if results and len(results) > 0:
                                # Print informational messages
                                for row in results:
                                    if 'message' in row:
                                        print(f"   ℹ️  {row['message']}")
                                    elif 'status' in row:
                                        print(f"   ✅ {row['status']}")
                        
                        success_count += 1
                        
                        # Show progress every 10 statements
                        if i % 10 == 0:
                            print(f"   Progress: {i}/{len(statements)} statements executed")
                        
                    except mysql.connector.Error as e:
                        # Some errors are expected (like "column already exists")
                        if 'Duplicate column name' in str(e) or 'already exists' in str(e):
                            print(f"   ℹ️  Skipping: {str(e)[:100]}")
                            success_count += 1
                        else:
                            print(f"   ❌ Error in statement {i}: {e}")
                            error_count += 1
                
                # Commit all changes
                conn.commit()
                print(f"\n✅ Migration completed: {success_count} successful, {error_count} errors")
                
                return error_count == 0
                
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return False
    
    def verify_migration(self):
        """Verify that migration was successful"""
        print("\n🔍 Verifying migration...")
        
        try:
            # Check administration columns
            with self.db.get_cursor() as (cursor, conn):
                cursor.execute("""
                    SELECT 
                        TABLE_NAME,
                        COLUMN_NAME,
                        DATA_TYPE,
                        COLUMN_DEFAULT
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND COLUMN_NAME = 'administration'
                    ORDER BY TABLE_NAME
                """)
                
                admin_columns = cursor.fetchall()
                
                if admin_columns:
                    print(f"✅ Found 'administration' column in {len(admin_columns)} tables:")
                    for col in admin_columns:
                        print(f"   - {col['TABLE_NAME']}")
                else:
                    print("⚠️  No 'administration' columns found")
                    return False
            
            # Check tenant_config table
            with self.db.get_cursor() as (cursor, conn):
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'tenant_config'
                """)
                
                result = cursor.fetchone()
                if result and result['count'] > 0:
                    print("✅ tenant_config table created successfully")
                else:
                    print("⚠️  tenant_config table not found")
                    return False
            
            # Check indexes
            with self.db.get_cursor() as (cursor, conn):
                cursor.execute("""
                    SELECT 
                        TABLE_NAME,
                        INDEX_NAME
                    FROM INFORMATION_SCHEMA.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND INDEX_NAME = 'idx_administration'
                    ORDER BY TABLE_NAME
                """)
                
                indexes = cursor.fetchall()
                
                if indexes:
                    print(f"✅ Found indexes on {len(indexes)} tables:")
                    for idx in indexes:
                        print(f"   - {idx['TABLE_NAME']}")
                else:
                    print("⚠️  No indexes found on administration columns")
            
            print("\n✅ Migration verification complete!")
            return True
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False
    
    def run(self):
        """Run the complete migration process"""
        print("=" * 60)
        print("Phase 1: Multi-Tenant Database Schema Migration")
        print("=" * 60)
        print()
        
        # Check prerequisites
        if not self.check_prerequisites():
            print("\n❌ Prerequisites check failed. Aborting migration.")
            return False
        
        # Create backup if requested
        if self.backup and not self.dry_run:
            if not self.create_backup():
                print("\n❌ Backup failed. Aborting migration.")
                return False
        
        # Execute migration
        if not self.execute_migration():
            print("\n❌ Migration failed.")
            return False
        
        # Verify migration (skip in dry-run mode)
        if not self.dry_run:
            if not self.verify_migration():
                print("\n⚠️  Migration completed but verification found issues.")
                return False
        
        print("\n" + "=" * 60)
        print("✅ Phase 1 Migration Complete!")
        print("=" * 60)
        
        if not self.dry_run:
            print("\nNext steps:")
            print("1. Review the changes in your database")
            print("2. Test your application with the new schema")
            print("3. Proceed to Phase 2: Cognito Setup")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Execute Phase 1 Multi-Tenant Database Migration'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be executed without making changes'
    )
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Create a backup before running migration'
    )
    
    args = parser.parse_args()
    
    migration = Phase1Migration(dry_run=args.dry_run, backup=args.backup)
    success = migration.run()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
