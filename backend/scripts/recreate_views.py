#!/usr/bin/env python3
"""
Recreate views with lowercase administration column
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("Recreating Views with Lowercase Administration")
print("=" * 60)

# Recreate vw_mutaties view
print("\n1. Recreating vw_mutaties view...")
try:
    db.execute_query("DROP VIEW IF EXISTS vw_mutaties", fetch=False, commit=True)
    
    # Recreate view with lowercase administration
    db.execute_query("""
        CREATE VIEW vw_mutaties AS
        SELECT 
            r.Belastingaangifte AS Aangifte,
            m.TransactionNumber,
            m.TransactionDate,
            m.TransactionDescription,
            m.TransactionAmount AS Amount,
            m.Debet AS Reknum,
            r.AccountName,
            r.Parent,
            r.VW,
            YEAR(m.TransactionDate) AS jaar,
            QUARTER(m.TransactionDate) AS kwartaal,
            MONTH(m.TransactionDate) AS maand,
            WEEK(m.TransactionDate) AS week,
            m.ReferenceNumber,
            m.administration,
            m.Ref3,
            m.Ref4,
            m.ID
        FROM mutaties m
        LEFT JOIN rekeningschema r ON m.Debet = r.Account
            AND m.administration = r.administration
    """, fetch=False, commit=True)
    
    print("   ✅ vw_mutaties view recreated")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Recreate vw_rekeningschema view
print("\n2. Recreating vw_rekeningschema view...")
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
            administration
        FROM rekeningschema
    """, fetch=False, commit=True)
    
    print("   ✅ vw_rekeningschema view recreated")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Verify views
print("\n" + "=" * 60)
print("Verification")
print("=" * 60)

print("\nChecking vw_mutaties view...")
try:
    result = db.execute_query("SELECT * FROM vw_mutaties LIMIT 1")
    if result and len(result) > 0:
        cols = list(result[0].keys())
        print(f"   Columns: {', '.join(cols)}")
        if 'administration' in result[0] and 'ID' in result[0]:
            print("   ✅ Has 'administration' and 'ID' columns")
        else:
            print("   ❌ Missing required columns")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\nChecking vw_rekeningschema view...")
try:
    result = db.execute_query("SELECT * FROM vw_rekeningschema LIMIT 1")
    if result and len(result) > 0:
        cols = list(result[0].keys())
        print(f"   Columns: {', '.join(cols)}")
        if 'administration' in result[0]:
            print("   ✅ Has 'administration' column")
        else:
            print("   ❌ Missing 'administration' column")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("✅ Views Recreated!")
print("=" * 60)
