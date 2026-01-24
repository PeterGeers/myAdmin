#!/usr/bin/env python3
"""
Fix uppercase Administration columns

This script renames uppercase 'Administration' to lowercase 'administration'
in mutaties and rekeningschema tables, and updates the views.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("Fixing Uppercase Administration Columns")
print("=" * 60)

# Fix mutaties table
print("\n1. Renaming mutaties.Administration to administration...")
try:
    db.execute_query(
        "ALTER TABLE mutaties CHANGE Administration administration VARCHAR(50)",
        fetch=False,
        commit=True
    )
    print("   ✅ mutaties.Administration renamed to administration")
except Exception as e:
    if "doesn't exist" in str(e).lower() or "unknown column" in str(e).lower():
        print("   ℹ️  Column already renamed or doesn't exist")
    else:
        print(f"   ❌ Error: {e}")

# Fix rekeningschema table
print("\n2. Renaming rekeningschema.Administration to administration...")
try:
    db.execute_query(
        "ALTER TABLE rekeningschema CHANGE Administration administration VARCHAR(50)",
        fetch=False,
        commit=True
    )
    print("   ✅ rekeningschema.Administration renamed to administration")
except Exception as e:
    if "doesn't exist" in str(e).lower() or "unknown column" in str(e).lower():
        print("   ℹ️  Column already renamed or doesn't exist")
    else:
        print(f"   ❌ Error: {e}")

# Update vw_mutaties view
print("\n3. Updating vw_mutaties view...")
try:
    db.execute_query("DROP VIEW IF EXISTS vw_mutaties", fetch=False, commit=True)
    
    # Recreate view with lowercase administration
    db.execute_query("""
        CREATE VIEW vw_mutaties AS
        SELECT 
            Belastingaangifte AS Aangifte,
            TransactionNumber,
            TransactionDate,
            TransactionDescription,
            TransactionAmount AS Amount,
            Debet AS Reknum,
            AccountName,
            ledger,
            Parent,
            VW,
            YEAR(TransactionDate) AS jaar,
            QUARTER(TransactionDate) AS kwartaal,
            MONTH(TransactionDate) AS maand,
            WEEK(TransactionDate) AS week,
            ReferenceNumber,
            administration,
            Ref3,
            Ref4
        FROM mutaties
        LEFT JOIN rekeningschema ON mutaties.Debet = rekeningschema.Account
            AND mutaties.administration = rekeningschema.administration
    """, fetch=False, commit=True)
    
    print("   ✅ vw_mutaties view updated")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Update vw_rekeningschema view
print("\n4. Updating vw_rekeningschema view...")
try:
    db.execute_query("DROP VIEW IF EXISTS vw_rekeningschema", fetch=False, commit=True)
    
    # Recreate view with lowercase administration
    db.execute_query("""
        CREATE VIEW vw_rekeningschema AS
        SELECT 
            Account,
            AccountName,
            Parent,
            VW,
            Belastingaangifte,
            ledger,
            administration
        FROM rekeningschema
    """, fetch=False, commit=True)
    
    print("   ✅ vw_rekeningschema view updated")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Verify changes
print("\n" + "=" * 60)
print("Verification")
print("=" * 60)

print("\nChecking mutaties table...")
result = db.execute_query("SHOW COLUMNS FROM mutaties LIKE '%administration%'")
for col in result:
    print(f"   Column: {col['Field']} ({col['Type']})")

print("\nChecking rekeningschema table...")
result = db.execute_query("SHOW COLUMNS FROM rekeningschema LIKE '%administration%'")
for col in result:
    print(f"   Column: {col['Field']} ({col['Type']})")

print("\nChecking vw_mutaties view...")
result = db.execute_query("SELECT * FROM vw_mutaties LIMIT 1")
if result and len(result) > 0:
    if 'administration' in result[0]:
        print("   ✅ Has 'administration' column")
    else:
        print("   ❌ Missing 'administration' column")

print("\nChecking vw_rekeningschema view...")
result = db.execute_query("SELECT * FROM vw_rekeningschema LIMIT 1")
if result and len(result) > 0:
    if 'administration' in result[0]:
        print("   ✅ Has 'administration' column")
    else:
        print("   ❌ Missing 'administration' column")

print("\n" + "=" * 60)
print("✅ Fix Complete!")
print("=" * 60)
