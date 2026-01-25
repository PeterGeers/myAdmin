#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("Checking a few sample transactions to understand Debet/Credit meaning:")
print("\nSample where 1002 is in DEBET column (should be money IN):")
result = db.execute_query("""
    SELECT TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit
    FROM mutaties
    WHERE Debet = '1002' AND administration = 'GoodwinSolutions'
    ORDER BY TransactionDate DESC
    LIMIT 5
""")
for row in result:
    print(f"  {row['TransactionDate']} | {row['TransactionDescription'][:50]:50} | €{row['TransactionAmount']:>10.2f} | Debet: {row['Debet']} | Credit: {row['Credit']}")

print("\nSample where 1002 is in CREDIT column (should be money OUT):")
result = db.execute_query("""
    SELECT TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit
    FROM mutaties
    WHERE Credit = '1002' AND administration = 'GoodwinSolutions'
    ORDER BY TransactionDate DESC
    LIMIT 5
""")
for row in result:
    print(f"  {row['TransactionDate']} | {row['TransactionDescription'][:50]:50} | €{row['TransactionAmount']:>10.2f} | Debet: {row['Debet']} | Credit: {row['Credit']}")

print("\n" + "="*80)
print("ACCOUNTING RULE FOR ASSET ACCOUNTS (like bank accounts):")
print("  - Debet = INCREASE (money coming IN) = POSITIVE")
print("  - Credit = DECREASE (money going OUT) = NEGATIVE")
print("  - Balance = SUM(Debet amounts) - SUM(Credit amounts)")
print("="*80)
