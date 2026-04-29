"""Check resultaat calculation."""

import os
import sys
from pathlib import Path

backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

# Fetch the same data as the test
query = """
    SELECT 
        Parent,
        Aangifte,
        SUM(Amount) as Amount
    FROM vw_mutaties
    WHERE (
        (VW = 'N' AND TransactionDate <= %s) OR
        (VW = 'Y' AND YEAR(TransactionDate) = %s)
    )
    AND administration = %s
    AND Parent IS NOT NULL
    AND Aangifte IS NOT NULL
    GROUP BY Parent, Aangifte
    ORDER BY Parent, Aangifte
"""

year = 2025
administration = 'GoodwinSolutions'
year_end = f"{year}-12-31"

results = db.execute_query(query, (year_end, year, administration), fetch=True)

print(f"\nData for {administration} year {year}:")
print("-" * 80)

total = 0.0
for row in results:
    amount = float(row['Amount'])
    total += amount
    print(f"{row['Parent']:5s} | {row['Aangifte']:30s} | €{amount:15,.2f}")

print("-" * 80)
print(f"RESULTAAT (sum of all amounts): €{total:,.2f}")
print()

# The resultaat should be the sum of all parent-aangifte amounts
# This represents the profit/loss for the year
