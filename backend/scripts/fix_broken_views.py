#!/usr/bin/env python3
"""
Fix broken views that reference old column names
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("=" * 60)
print("Fixing Broken Views")
print("=" * 60)

# Fix vw_beginbalans
print("\n1. Fixing vw_beginbalans...")
try:
    db.execute_query("DROP VIEW IF EXISTS vw_beginbalans", fetch=False, commit=True)
    
    # Recreate without ledger column and with lowercase administration
    db.execute_query("""
        CREATE VIEW vw_beginbalans AS
        SELECT 
            administration,
            VW,
            Parent,
            AccountName,
            SUM(Amount) AS beginbalans,
            jaar
        FROM vw_mutaties
        WHERE VW = 'N'
        GROUP BY administration, VW, Parent, AccountName, jaar
    """, fetch=False, commit=True)
    
    print("   ✅ vw_beginbalans fixed")
    
    # Test it
    result = db.execute_query("SELECT * FROM vw_beginbalans LIMIT 1")
    print(f"   ✅ View works ({len(result)} rows)")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Fix vw_creditmutaties
print("\n2. Fixing vw_creditmutaties...")
try:
    db.execute_query("DROP VIEW IF EXISTS vw_creditmutaties", fetch=False, commit=True)
    
    # Recreate with lowercase administration
    db.execute_query("""
        CREATE VIEW vw_creditmutaties AS
        SELECT 
            m.TransactionNumber,
            m.TransactionDate,
            m.TransactionDescription,
            m.TransactionAmount,
            m.Credit AS Reknum,
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
            m.Ref4
        FROM mutaties m
        LEFT JOIN rekeningschema r ON m.Credit = r.Account
            AND m.administration = r.administration
    """, fetch=False, commit=True)
    
    print("   ✅ vw_creditmutaties fixed")
    
    # Test it
    result = db.execute_query("SELECT * FROM vw_creditmutaties LIMIT 1")
    print(f"   ✅ View works ({len(result)} rows)")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Fix vw_debetmutaties
print("\n3. Fixing vw_debetmutaties...")
try:
    db.execute_query("DROP VIEW IF EXISTS vw_debetmutaties", fetch=False, commit=True)
    
    # Recreate with lowercase administration
    db.execute_query("""
        CREATE VIEW vw_debetmutaties AS
        SELECT 
            m.TransactionNumber,
            m.TransactionDate,
            m.TransactionDescription,
            m.TransactionAmount,
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
            m.Ref4
        FROM mutaties m
        LEFT JOIN rekeningschema r ON m.Debet = r.Account
            AND m.administration = r.administration
    """, fetch=False, commit=True)
    
    print("   ✅ vw_debetmutaties fixed")
    
    # Test it
    result = db.execute_query("SELECT * FROM vw_debetmutaties LIMIT 1")
    print(f"   ✅ View works ({len(result)} rows)")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Verify all views
print("\n" + "=" * 60)
print("Verification")
print("=" * 60)

print("\nTesting all views...")
views = [
    'lookupbankaccounts_r',
    'vw_beginbalans',
    'vw_bnb_total',
    'vw_creditmutaties',
    'vw_debetmutaties',
    'vw_mutaties',
    'vw_readreferences',
    'vw_rekeningnummers',
    'vw_rekeningschema',
    'vw_reservationcode'
]

passed = 0
failed = 0

for view in views:
    try:
        result = db.execute_query(f"SELECT * FROM {view} LIMIT 1")
        print(f"   ✅ {view} works")
        passed += 1
    except Exception as e:
        print(f"   ❌ {view} broken: {str(e)[:100]}")
        failed += 1

print(f"\n✅ {passed}/{len(views)} views working")

if failed == 0:
    print("\n" + "=" * 60)
    print("✅ All Views Fixed!")
    print("=" * 60)
    print("\nMySQL Workbench should now work correctly.")
    print("Try: Right-click schema → Refresh All")
else:
    print(f"\n⚠️  {failed} views still broken")

