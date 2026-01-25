#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("Recreating vw_mutaties with correct signs...")

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
print("✅ View created successfully")

# Test it
result = db.execute_query("SELECT COUNT(*) as count FROM vw_mutaties")
print(f"✅ View has {result[0]['count']} rows")

# Test balance for account 1002
result = db.execute_query("""
    SELECT Reknum, administration, ROUND(SUM(Amount), 2) as balance 
    FROM vw_mutaties 
    WHERE administration = 'GoodwinSolutions' AND Reknum = '1002'
    GROUP BY Reknum, administration
""")
if result:
    print(f"✅ Balance for account 1002: {result[0]['balance']}")
