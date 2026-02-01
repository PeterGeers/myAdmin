#!/usr/bin/env python3
"""
Create template_validation_log table
Part of Phase 2.6: Template Preview and Validation
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


def run_migration():
    """Execute the template_validation_log table creation"""
    
    print("=" * 60)
    print("Creating template_validation_log table")
    print("=" * 60)
    
    try:
        # Initialize database manager
        db = DatabaseManager()
        
        # Read SQL file
        sql_file = backend_dir / 'sql' / 'create_template_validation_log_table.sql'
        
        if not sql_file.exists():
            print(f"❌ SQL file not found: {sql_file}")
            return False
        
        print(f"\n📄 Reading SQL file: {sql_file}")
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Remove comments and split SQL statements
        lines = []
        for line in sql_content.split('\n'):
            # Skip comment lines
            if line.strip().startswith('--'):
                continue
            lines.append(line)
        
        clean_sql = '\n'.join(lines)
        
        # Split SQL statements by semicolon
        statements = [stmt.strip() for stmt in clean_sql.split(';') if stmt.strip()]
        
        print(f"\n🔧 Executing {len(statements)} SQL statements...")
        
        for i, statement in enumerate(statements, 1):
            # Skip empty statements
            if not statement:
                continue
            
            try:
                # Execute statement
                if statement.upper().startswith('SELECT'):
                    result = db.execute_query(statement, fetch=True)
                    if result:
                        print(f"\n✅ Statement {i}: {result[0] if result else 'Success'}")
                elif statement.upper().startswith('DESCRIBE'):
                    result = db.execute_query(statement, fetch=True)
                    print(f"\n✅ Statement {i}: Table structure:")
                    for row in result:
                        print(f"   {row}")
                else:
                    db.execute_query(statement, fetch=False, commit=True)
                    print(f"✅ Statement {i}: Executed successfully")
            
            except Exception as e:
                # Check if error is about table already existing
                if 'already exists' in str(e).lower():
                    print(f"⚠️  Statement {i}: Table already exists (skipping)")
                else:
                    print(f"❌ Statement {i} failed: {e}")
                    raise
        
        print("\n" + "=" * 60)
        print("✅ template_validation_log table created successfully!")
        print("=" * 60)
        
        return True
    
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
