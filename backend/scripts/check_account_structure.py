#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("Bank accounts for GoodwinSolutions:")
result = db.execute_query("""
    SELECT * 
    FROM vw_rekeningnummers 
    WHERE administration='GoodwinSolutions'
    LIMIT 1
""")
if result:
    print(f"Columns: {list(result[0].keys())}")

result = db.execute_query("""
    SELECT Account, rekeningNummer, administration
    FROM vw_rekeningnummers 
    WHERE administration='GoodwinSolutions'
""")
for row in result:
    print(f"  {row['Account']:6} | {row['rekeningNummer']}")

print("\nChecking debet vs credit for account 1002:")
debet = db.execute_query("""
    SELECT COUNT(*) as count, SUM(TransactionAmount) as total
    FROM mutaties
    WHERE Debet = '1002' AND administration = 'GoodwinSolutions'
""")
credit = db.execute_query("""
    SELECT COUNT(*) as count, SUM(TransactionAmount) as total
    FROM mutaties
    WHERE Credit = '1002' AND administration = 'GoodwinSolutions'
""")

print(f"  Debet (money OUT): {debet[0]['count']} transactions, total: {debet[0]['total']:.2f}")
print(f"  Credit (money IN): {credit[0]['count']} transactions, total: {credit[0]['total']:.2f}")
print(f"  Net balance (Credit - Debet): {credit[0]['total'] - debet[0]['total']:.2f}")
