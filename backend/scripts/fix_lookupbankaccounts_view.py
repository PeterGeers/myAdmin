#!/usr/bin/env python3
"""
Fix lookupbankaccounts_r view to use lowercase administration
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("Fixing lookupbankaccounts_r View")
print("=" * 60)

# Check current definition
print("\n1. Checking current view definition...")
try:
    result = db.execute_query("SHOW CREATE VIEW lookupbankaccounts_r")
    if result:
        create_view = result[0]['Create View']
        print(f"   Current definition length: {len(create_view)} chars")
        
        if 'Administration' in create_view and 'administration' not in create_view.replace('Administration', ''):
            print("   ⚠️  View uses uppercase 'Administration'")
        else:
            print("   ✅ View already uses lowercase 'administration'")
            
except Exception as e:
    print(f"   ❌ Error: {e}")

# Fix the view
print("\n2. Recreating view with lowercase administration...")
try:
    db.execute_query("DROP VIEW IF EXISTS lookupbankaccounts_r", fetch=False, commit=True)
    
    # Recreate with lowercase administration
    db.execute_query("""
        CREATE VIEW lookupbankaccounts_r AS
        SELECT 
            rekeningNummer,
            Account,
            administration
        FROM (
            SELECT 
                CONCAT('NL', Account) AS rekeningNummer,
                Account,
                administration
            FROM rekeningschema
            WHERE Account LIKE 'NL%'
            
            UNION ALL
            
            SELECT 
                Account AS rekeningNummer,
                Account,
                administration
            FROM rekeningschema
            WHERE Account REGEXP '^[0-9]'
        ) AS bank_accounts
    """, fetch=False, commit=True)
    
    print("   ✅ lookupbankaccounts_r recreated with lowercase administration")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Verify the fix
print("\n3. Verifying the fix...")
try:
    # Test the view
    result = db.execute_query("SELECT * FROM lookupbankaccounts_r LIMIT 5")
    print(f"   ✅ View works ({len(result)} rows)")
    
    # Check columns
    if result and len(result) > 0:
        cols = list(result[0].keys())
        print(f"   Columns: {', '.join(cols)}")
        
        if 'administration' in cols:
            print("   ✅ Has lowercase 'administration' column")
        elif 'Administration' in cols:
            print("   ⚠️  Still has uppercase 'Administration' column")
        else:
            print("   ❌ Missing administration column")
    
    # Show sample data
    print("\n   Sample data:")
    for row in result[:3]:
        print(f"      {row['rekeningNummer']} -> {row['Account']} ({row.get('administration', row.get('Administration', 'N/A'))})")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check the new definition
print("\n4. Checking new view definition...")
try:
    result = db.execute_query("SHOW CREATE VIEW lookupbankaccounts_r")
    if result:
        create_view = result[0]['Create View']
        
        if 'administration' in create_view.lower():
            admin_count = create_view.count('administration')
            Admin_count = create_view.count('Administration')
            print(f"   lowercase 'administration': {admin_count} occurrences")
            print(f"   uppercase 'Administration': {Admin_count} occurrences")
            
            if Admin_count == 0:
                print("   ✅ View definition uses only lowercase")
            else:
                print("   ⚠️  View definition still has uppercase references")
                
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("✅ Fix Complete!")
print("=" * 60)
print("\nRefresh MySQL Workbench:")
print("  Right-click schema → Refresh All")
