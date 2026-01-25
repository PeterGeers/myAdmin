#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("Fixing vw_mutaties with CORRECT accounting signs:")
print("  - Debet (money IN) = POSITIVE")
print("  - Credit (money OUT) = NEGATIVE")
print()

# Drop the existing view
print("Dropping existing view...")
db.execute_query("DROP VIEW IF EXISTS vw_mutaties", fetch=False, commit=True)

# Recreate with CORRECT signs for asset accounts
sql = """
CREATE VIEW vw_mutaties AS
SELECT 
    r.Belastingaangifte AS Aangifte,
    d.TransactionNumber,
    d.TransactionDate,
    d.TransactionDescription,
    d.TransactionAmount AS Amount,
    d.Reknum,
    d.AccountName,
    d.Parent,
    d.VW,
    d.jaar,
    d.kwartaal,
    d.maand,
    d.week,
    d.ReferenceNumber,
    d.administration,
    d.Ref3,
    d.Ref4
FROM vw_debetmutaties d
LEFT JOIN rekeningschema r ON d.Reknum = r.Account 
    AND d.administration = r.administration

UNION ALL

SELECT 
    r.Belastingaangifte AS Aangifte,
    c.TransactionNumber,
    c.TransactionDate,
    c.TransactionDescription,
    -c.TransactionAmount AS Amount,
    c.Reknum,
    c.AccountName,
    c.Parent,
    c.VW,
    c.jaar,
    c.kwartaal,
    c.maand,
    c.week,
    c.ReferenceNumber,
    c.administration,
    c.Ref3,
    c.Ref4
FROM vw_creditmutaties c
LEFT JOIN rekeningschema r ON c.Reknum = r.Account 
    AND c.administration = r.administration
"""

db.execute_query(sql, fetch=False, commit=True)
print("✅ View recreated with CORRECT signs")

# Test it
result = db.execute_query("SELECT COUNT(*) as count FROM vw_mutaties")
print(f"✅ View has {result[0]['count']} rows")

# Test balance for account 1002 (should be POSITIVE now)
result = db.execute_query("""
    SELECT Reknum, administration, ROUND(SUM(Amount), 2) as balance 
    FROM vw_mutaties 
    WHERE administration = 'GoodwinSolutions' AND Reknum = '1002'
    GROUP BY Reknum, administration
""")
if result:
    balance = result[0]['balance']
    print(f"✅ Balance for account 1002 (GoodwinSolutions): {balance}")
    if balance > 0:
        print("   ✅ POSITIVE balance - CORRECT!")
    else:
        print("   ❌ NEGATIVE balance - still wrong!")

# Verify the calculation manually
debet = db.execute_query("""
    SELECT SUM(TransactionAmount) as total
    FROM mutaties
    WHERE Debet = '1002' AND administration = 'GoodwinSolutions'
""")
credit = db.execute_query("""
    SELECT SUM(TransactionAmount) as total
    FROM mutaties
    WHERE Credit = '1002' AND administration = 'GoodwinSolutions'
""")

print(f"\nManual verification:")
print(f"  Debet total (money IN): {debet[0]['total']:.2f}")
print(f"  Credit total (money OUT): {credit[0]['total']:.2f}")
print(f"  Expected balance (Debet - Credit): {debet[0]['total'] - credit[0]['total']:.2f}")
