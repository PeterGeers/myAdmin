#!/usr/bin/env python3
"""
Create ai_usage_log table
Part of Phase 2.6: Template Preview and Validation - AI Template Assistant
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
    """Execute the ai_usage_log table creation"""
    
    print("=" * 60)
    print("Creating ai_usage_log table")
    print("=" * 60)
    
    try:
        db = DatabaseManager()
        
        # Read SQL file
        sql_file = backend_dir / 'sql' / 'create_ai_usage_log_table.sql'
        
        if not sql_file.exists():
            print(f"❌ SQL file not found: {sql_file}")
            return False
        
        print(f"\n📄 Reading SQL file: {sql_file.name}")
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Remove comment lines but keep the SQL statements
        lines = sql_content.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip pure comment lines
            if line.strip().startswith('--'):
                continue
            cleaned_lines.append(line)
        
        cleaned_content = '\n'.join(cleaned_lines)
        
        # Split into statements (simple split by semicolon)
        statements = [s.strip() for s in cleaned_content.split(';') if s.strip()]
        
        print(f"📝 Found {len(statements)} SQL statements to execute\n")
        
        # Execute each statement
        for i, statement in enumerate(statements, 1):
            
            print(f"Executing statement {i}...")
            
            try:
                # Check if it's a SELECT/SHOW/DESCRIBE statement
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
                    # CREATE TABLE or other DDL
                    db.execute_query(statement, fetch=False, commit=True)
                    print(f"✅ Statement {i}: Success")
            
            except Exception as e:
                print(f"❌ Statement {i} failed: {e}")
                return False
        
        print("\n" + "=" * 60)
        print("✅ ai_usage_log table created successfully!")
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
