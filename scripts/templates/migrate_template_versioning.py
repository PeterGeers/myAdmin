#!/usr/bin/env python3
"""
Template Versioning Migration Script for Railway Migration
Adds versioning support to tenant_template_config table.

This script extends the tenant_template_config table with columns for:
- version tracking
- approval workflow (approved_by, approved_at, approval_notes)
- template history (previous_file_id)
- status management (draft, active, archived)

Usage:
    python scripts/templates/migrate_template_versioning.py [--dry-run] [--verify]

Options:
    --dry-run       Show what would be changed without actually changing
    --verify        Verify migration by checking table structure
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Add backend/src to path for imports
backend_src = Path(__file__).parent.parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TemplateVersioningMigrator:
    """Handles migration of tenant_template_config table to add versioning support"""
    
    # SQL file path
    SQL_FILE = 'backend/sql/alter_tenant_template_config_add_versioning.sql'
    
    # Expected new columns
    EXPECTED_COLUMNS = [
        'version',
        'approved_by',
        'approved_at',
        'approval_notes',
        'previous_file_id',
        'status'
    ]
    
    # Expected new indexes
    EXPECTED_INDEXES = [
        'idx_status',
        'idx_approved_by',
        'idx_admin_status'
    ]
    
    def __init__(self, dry_run=False):
        """
        Initialize the migrator.
        
        Args:
            dry_run: If True, only show what would be changed without actually changing
        """
        self.dry_run = dry_run
        self.db_manager = None
        
        # Always initialize database connection (needed to check current schema)
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize database manager"""
        try:
            self.db_manager = DatabaseManager()
            logger.info("✅ Database connection initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database connection: {e}")
            raise
    
    def _read_sql_file(self) -> str:
        """
        Read the SQL migration file.
        
        Returns:
            SQL file content as string
            
        Raises:
            FileNotFoundError: If SQL file doesn't exist
        """
        sql_path = Path(self.SQL_FILE)
        
        if not sql_path.exists():
            raise FileNotFoundError(f"SQL file not found: {self.SQL_FILE}")
        
        with open(sql_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _get_current_columns(self) -> list:
        """
        Get current columns in tenant_template_config table.
        
        Returns:
            List of column names
        """
        query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'tenant_template_config'
            ORDER BY ORDINAL_POSITION
        """
        
        results = self.db_manager.execute_query(query)
        return [row['COLUMN_NAME'] for row in results]
    
    def _get_current_indexes(self) -> list:
        """
        Get current indexes in tenant_template_config table.
        
        Returns:
            List of index names
        """
        query = """
            SELECT DISTINCT INDEX_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'tenant_template_config'
            ORDER BY INDEX_NAME
        """
        
        results = self.db_manager.execute_query(query)
        return [row['INDEX_NAME'] for row in results]
    
    def _check_if_migration_needed(self) -> dict:
        """
        Check if migration is needed by comparing current schema with expected schema.
        
        Returns:
            Dict with migration status:
            {
                'needed': bool,
                'missing_columns': list,
                'missing_indexes': list,
                'existing_columns': list,
                'existing_indexes': list
            }
        """
        current_columns = self._get_current_columns()
        current_indexes = self._get_current_indexes()
        
        missing_columns = [col for col in self.EXPECTED_COLUMNS if col not in current_columns]
        missing_indexes = [idx for idx in self.EXPECTED_INDEXES if idx not in current_indexes]
        
        return {
            'needed': len(missing_columns) > 0 or len(missing_indexes) > 0,
            'missing_columns': missing_columns,
            'missing_indexes': missing_indexes,
            'existing_columns': current_columns,
            'existing_indexes': current_indexes
        }
    
    def _execute_sql_statements(self, sql_content: str):
        """
        Execute SQL statements from the migration file.
        
        Args:
            sql_content: SQL file content
        """
        # Split SQL content into individual statements
        # Remove comments and empty lines
        statements = []
        current_statement = []
        
        for line in sql_content.split('\n'):
            # Skip comment lines
            if line.strip().startswith('--'):
                continue
            
            # Skip empty lines
            if not line.strip():
                continue
            
            current_statement.append(line)
            
            # Check if statement is complete (ends with semicolon)
            if line.strip().endswith(';'):
                statement = '\n'.join(current_statement)
                statements.append(statement)
                current_statement = []
        
        # Execute each statement
        for i, statement in enumerate(statements, 1):
            try:
                # Skip verification queries (SELECT, SHOW, DESCRIBE statements)
                statement_upper = statement.strip().upper()
                if (statement_upper.startswith('SELECT') or 
                    statement_upper.startswith('SHOW') or 
                    statement_upper.startswith('DESCRIBE')):
                    continue
                
                logger.info(f"📝 Executing statement {i}/{len(statements)}...")
                logger.debug(f"SQL: {statement[:100]}...")
                
                self.db_manager.execute_query(statement, fetch=False, commit=True)
                logger.info(f"✅ Statement {i} executed successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to execute statement {i}: {e}")
                logger.error(f"Statement: {statement}")
                raise
    
    def migrate(self, verify=False):
        """
        Execute the migration.
        
        Args:
            verify: If True, verify migration by checking table structure
            
        Returns:
            Dict with migration results
        """
        logger.info("=" * 60)
        logger.info("🚀 Starting Template Versioning Migration")
        logger.info("=" * 60)
        
        if self.dry_run:
            logger.info("⚠️  DRY RUN MODE - No changes will be made")
        
        logger.info("")
        
        try:
            # Check if migration is needed
            logger.info("🔍 Checking current table structure...")
            migration_status = self._check_if_migration_needed()
            
            logger.info(f"Current columns: {len(migration_status['existing_columns'])}")
            logger.info(f"Current indexes: {len(migration_status['existing_indexes'])}")
            
            if not migration_status['needed']:
                logger.info("✅ Migration not needed - table already has versioning columns")
                return {
                    'success': True,
                    'migration_needed': False,
                    'message': 'Table already has versioning support'
                }
            
            logger.info(f"\n⚠️  Migration needed:")
            if migration_status['missing_columns']:
                logger.info(f"  Missing columns: {', '.join(migration_status['missing_columns'])}")
            if migration_status['missing_indexes']:
                logger.info(f"  Missing indexes: {', '.join(migration_status['missing_indexes'])}")
            
            logger.info("")
            
            if self.dry_run:
                logger.info("[DRY RUN] Would execute SQL migration script")
                logger.info(f"[DRY RUN] SQL file: {self.SQL_FILE}")
                return {
                    'success': True,
                    'migration_needed': True,
                    'dry_run': True,
                    'missing_columns': migration_status['missing_columns'],
                    'missing_indexes': migration_status['missing_indexes']
                }
            
            # Read SQL file
            logger.info(f"📖 Reading SQL migration file: {self.SQL_FILE}")
            sql_content = self._read_sql_file()
            logger.info(f"✅ SQL file loaded ({len(sql_content)} bytes)")
            
            # Execute migration
            logger.info("\n🔧 Executing migration...")
            self._execute_sql_statements(sql_content)
            logger.info("✅ Migration executed successfully")
            
            # Verify if requested
            if verify:
                logger.info("\n🔍 Verifying migration...")
                verification_result = self._verify_migration()
                
                if verification_result['success']:
                    logger.info("✅ Verification successful")
                else:
                    logger.error("❌ Verification failed")
                    return verification_result
            
            return {
                'success': True,
                'migration_needed': True,
                'message': 'Migration completed successfully'
            }
        
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _verify_migration(self) -> dict:
        """
        Verify that migration was successful.
        
        Returns:
            Dict with verification results
        """
        try:
            # Check columns
            current_columns = self._get_current_columns()
            missing_columns = [col for col in self.EXPECTED_COLUMNS if col not in current_columns]
            
            # Check indexes
            current_indexes = self._get_current_indexes()
            missing_indexes = [idx for idx in self.EXPECTED_INDEXES if idx not in current_indexes]
            
            if missing_columns or missing_indexes:
                return {
                    'success': False,
                    'missing_columns': missing_columns,
                    'missing_indexes': missing_indexes,
                    'message': 'Migration incomplete - some columns or indexes are missing'
                }
            
            # Check column types
            logger.info("  Checking column types...")
            describe_query = "DESCRIBE tenant_template_config"
            columns_info = self.db_manager.execute_query(describe_query)
            
            # Verify specific column types
            column_types = {row['Field']: row['Type'] for row in columns_info}
            
            expected_types = {
                'version': 'int',
                'approved_by': 'varchar(255)',
                'approved_at': 'timestamp',
                'approval_notes': 'text',
                'previous_file_id': 'varchar(255)',
                'status': "enum('draft','active','archived')"
            }
            
            type_mismatches = []
            for col, expected_type in expected_types.items():
                actual_type = column_types.get(col, '').lower()
                if actual_type != expected_type:
                    type_mismatches.append(f"{col}: expected {expected_type}, got {actual_type}")
            
            if type_mismatches:
                logger.warning(f"  ⚠️  Column type mismatches: {', '.join(type_mismatches)}")
            
            logger.info(f"  ✅ All {len(self.EXPECTED_COLUMNS)} columns present")
            logger.info(f"  ✅ All {len(self.EXPECTED_INDEXES)} indexes present")
            
            return {
                'success': True,
                'columns': current_columns,
                'indexes': current_indexes,
                'message': 'Migration verified successfully'
            }
        
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def print_summary(self, result: dict):
        """Print migration summary"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 Migration Summary")
        logger.info("=" * 60)
        
        if result['success']:
            if result.get('migration_needed', True):
                logger.info("✅ Status: SUCCESS")
                logger.info(f"📝 Message: {result.get('message', 'Migration completed')}")
            else:
                logger.info("ℹ️  Status: SKIPPED (already migrated)")
        else:
            logger.info("❌ Status: FAILED")
            logger.info(f"⚠️  Error: {result.get('error', 'Unknown error')}")
        
        logger.info("=" * 60)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Add versioning support to tenant_template_config table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be changed
  python scripts/templates/migrate_template_versioning.py --dry-run
  
  # Execute migration
  python scripts/templates/migrate_template_versioning.py
  
  # Execute migration and verify
  python scripts/templates/migrate_template_versioning.py --verify
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without actually changing'
    )
    
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify migration by checking table structure'
    )
    
    args = parser.parse_args()
    
    try:
        migrator = TemplateVersioningMigrator(dry_run=args.dry_run)
        result = migrator.migrate(verify=args.verify)
        migrator.print_summary(result)
        
        # Exit with error code if migration failed
        if not result['success']:
            sys.exit(1)
        
        logger.info("✅ Migration completed successfully!")
        sys.exit(0)
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
