#!/usr/bin/env python3
"""
Phase 5 Migration: Tenant-Specific Module Access

Creates tenant_modules table and populates initial data.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import DatabaseManager

def run_migration():
    """Execute Phase 5 migration"""
    print("=" * 60)
    print("Phase 5: Tenant-Specific Module Access Migration")
    print("=" * 60)
    
    # Read SQL file
    sql_file = Path(__file__).parent.parent / 'sql' / 'phase5_tenant_modules.sql'
    
    if not sql_file.exists():
        print(f"❌ SQL file not found: {sql_file}")
        return False
    
    print(f"\n📄 Reading SQL from: {sql_file}")
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Connect to database
    print("\n🔌 Connecting to database...")
    db_manager = DatabaseManager()
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    try:
        # Execute the entire SQL content as one block
        # MySQL connector can handle multiple statements
        print(f"\n📝 Executing SQL migration...")
        
        # Split by semicolon but keep multi-line statements together
        statements = []
        current_statement = []
        
        for line in sql_content.split('\n'):
            line = line.strip()
            # Skip empty lines and comment-only lines
            if not line or line.startswith('--'):
                continue
            
            current_statement.append(line)
            
            # If line ends with semicolon, it's end of statement
            if line.endswith(';'):
                stmt = ' '.join(current_statement)
                if stmt and not stmt.startswith('--'):
                    statements.append(stmt)
                current_statement = []
        
        print(f"\n📝 Found {len(statements)} SQL statements to execute...")
        
        for i, statement in enumerate(statements, 1):
            # Show first 80 chars of statement
            preview = statement[:80].replace('\n', ' ')
            print(f"\n[{i}/{len(statements)}] {preview}...")
            
            cursor.execute(statement)
            
            # If it's a SELECT, show results
            if statement.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                if results:
                    print(f"   ✅ Found {len(results)} rows:")
                    for row in results:
                        print(f"      {row}")
                else:
                    print("   ✅ No rows returned")
            else:
                print(f"   ✅ Affected rows: {cursor.rowcount}")
        
        # Commit changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Verify tenant_modules table
        print("\n" + "=" * 60)
        print("Verification: tenant_modules table")
        print("=" * 60)
        
        cursor.execute("""
            SELECT administration, module_name, is_active, created_at
            FROM tenant_modules
            ORDER BY administration, module_name
        """)
        
        results = cursor.fetchall()
        print(f"\nTotal tenant-module mappings: {len(results)}")
        print("\nTenant Module Assignments:")
        print("-" * 60)
        
        for row in results:
            status = "✅ Active" if row[2] else "❌ Inactive"
            print(f"  {row[0]:20} | {row[1]:10} | {status}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()
        print("\n🔌 Database connection closed")

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
