#!/usr/bin/env python3
"""
Diagnose MySQL Workbench issues with tables and views
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("MySQL Workbench Diagnostic")
print("=" * 60)

# Check all tables
print("\n1. Checking all tables...")
try:
    result = db.execute_query("""
        SELECT TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_TYPE, TABLE_NAME
    """)
    
    tables = [r for r in result if r['TABLE_TYPE'] == 'BASE TABLE']
    views = [r for r in result if r['TABLE_TYPE'] == 'VIEW']
    
    print(f"   Found {len(tables)} tables and {len(views)} views")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check for problematic views
print("\n2. Checking view definitions...")
try:
    result = db.execute_query("""
        SELECT TABLE_NAME, VIEW_DEFINITION
        FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = DATABASE()
    """)
    
    print(f"   Found {len(result)} view definitions")
    
    for view in result:
        view_name = view['TABLE_NAME']
        print(f"\n   Checking {view_name}...")
        
        # Try to select from the view
        try:
            test_result = db.execute_query(f"SELECT * FROM {view_name} LIMIT 1")
            print(f"      ✅ View works ({len(test_result)} rows)")
        except Exception as e:
            print(f"      ❌ View broken: {e}")
            print(f"      Definition: {view['VIEW_DEFINITION'][:200]}...")
            
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check for invalid view references
print("\n3. Checking for invalid column references...")
try:
    # Check vw_mutaties
    print("   Checking vw_mutaties...")
    result = db.execute_query("SHOW CREATE VIEW vw_mutaties")
    if result:
        create_stmt = result[0]['Create View']
        print(f"      Definition length: {len(create_stmt)} chars")
        
        # Check if it references non-existent columns
        if 'ledger' in create_stmt.lower():
            print("      ⚠️  References 'ledger' column (may not exist)")
        if 'AccountDescription' in create_stmt:
            print("      ⚠️  References 'AccountDescription' (should be 'AccountName')")
            
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check for definer issues
print("\n4. Checking view definers...")
try:
    result = db.execute_query("""
        SELECT TABLE_NAME, DEFINER, SECURITY_TYPE
        FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = DATABASE()
    """)
    
    for view in result:
        print(f"   {view['TABLE_NAME']}: Definer={view['DEFINER']}, Security={view['SECURITY_TYPE']}")
        
        # Check if definer exists
        definer_parts = view['DEFINER'].split('@')
        if len(definer_parts) == 2:
            user, host = definer_parts
            user = user.strip("'`")
            host = host.strip("'`")
            
            # Check if user exists
            try:
                user_check = db.execute_query(
                    "SELECT User, Host FROM mysql.user WHERE User = %s AND Host = %s",
                    (user, host)
                )
                if not user_check:
                    print(f"      ⚠️  Definer user '{user}'@'{host}' does not exist!")
            except:
                pass  # May not have permission to check mysql.user
                
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check for circular dependencies
print("\n5. Checking for circular view dependencies...")
try:
    result = db.execute_query("""
        SELECT TABLE_NAME, VIEW_DEFINITION
        FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = DATABASE()
    """)
    
    for view in result:
        view_name = view['TABLE_NAME']
        definition = view['VIEW_DEFINITION'].lower()
        
        # Check if view references itself
        if view_name.lower() in definition:
            print(f"   ⚠️  {view_name} may have circular reference")
            
except Exception as e:
    print(f"   ❌ Error: {e}")

# Suggest fixes
print("\n" + "=" * 60)
print("Recommendations")
print("=" * 60)

print("""
If MySQL Workbench shows "tables and views cannot be fetched":

1. **Refresh the schema**:
   - Right-click on the schema in MySQL Workbench
   - Select "Refresh All"

2. **Check view definitions**:
   - Run: SHOW CREATE VIEW vw_mutaties;
   - Look for invalid column references

3. **Recreate problematic views**:
   - Run: python backend/scripts/recreate_views.py

4. **Check permissions**:
   - Ensure your user has SELECT privilege on all tables/views
   - Run: SHOW GRANTS FOR CURRENT_USER();

5. **Restart MySQL Workbench**:
   - Close and reopen MySQL Workbench
   - Reconnect to the database

6. **Check MySQL error log**:
   - Look for errors in MySQL error log
   - Location varies by installation
""")

print("\n" + "=" * 60)
