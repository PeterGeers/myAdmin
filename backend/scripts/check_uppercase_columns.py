#!/usr/bin/env python3
"""
Check for uppercase column names that should be lowercase
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("Checking for Uppercase Column Names")
print("=" * 60)

# Get all tables
tables_result = db.execute_query("""
    SELECT TABLE_NAME 
    FROM INFORMATION_SCHEMA.TABLES 
    WHERE TABLE_SCHEMA = DATABASE() 
    AND TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_NAME
""")

tables = [r['TABLE_NAME'] for r in tables_result]

uppercase_columns = []

for table in tables:
    result = db.execute_query(f"SHOW COLUMNS FROM {table}")
    
    for col in result:
        col_name = col['Field']
        
        # Check if column has uppercase letters
        if col_name != col_name.lower():
            uppercase_columns.append({
                'table': table,
                'column': col_name,
                'type': col['Type'],
                'lowercase': col_name.lower()
            })

if uppercase_columns:
    print(f"\n⚠️  Found {len(uppercase_columns)} columns with uppercase letters:\n")
    
    # Group by table
    by_table = {}
    for col in uppercase_columns:
        table = col['table']
        if table not in by_table:
            by_table[table] = []
        by_table[table].append(col)
    
    for table, cols in sorted(by_table.items()):
        print(f"\n{table}:")
        for col in cols:
            print(f"   {col['column']} ({col['type']}) → {col['lowercase']}")
    
    print("\n" + "=" * 60)
    print("Recommendation")
    print("=" * 60)
    print("""
For PostgreSQL compatibility, all column names should be lowercase.

However, renaming columns is a BREAKING CHANGE that will affect:
- Application code that references these columns
- Existing queries and stored procedures
- Views that use these columns
- Reports and analytics

IMPORTANT DECISION NEEDED:
1. Keep uppercase columns (current MySQL standard)
2. Rename to lowercase (PostgreSQL compatible, but requires code changes)

For Phase 1, we focused on the 'administration' field only.
Renaming all columns should be a separate migration phase.
""")
    
else:
    print("\n✅ All columns are lowercase!")

print("\n" + "=" * 60)
