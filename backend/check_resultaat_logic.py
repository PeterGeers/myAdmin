"""Check resultaat calculation logic - P&L only vs all accounts."""

import os
import sys
from pathlib import Path

backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

year = 2025
administration = 'GoodwinSolutions'
year_end = f"{year}-12-31"

# Get all data with VW flag
query = """
    SELECT 
        Parent,
        Aangifte,
        Reknum,
        VW,
        SUM(Amount) as Amount
    FROM vw_mutaties
    WHERE (
        (VW = 'N' AND TransactionDate <= %s) OR
        (VW = 'Y' AND YEAR(TransactionDate) = %s)
    )
    AND administration = %s
    AND Parent IS NOT NULL
    AND Aangifte IS NOT NULL
    GROUP BY Parent, Aangifte, Reknum, VW
    ORDER BY Parent, Aangifte, Reknum
"""

results = db.execute_query(query, (year_end, year, administration), fetch=True)

print(f"\nDetailed data for {administration} year {year}:")
print("-" * 100)
print(f"{'Parent':<7} {'Aangifte':<30} {'Reknum':<7} {'VW':<3} {'Amount':>15}")
print("-" * 100)

total_all = 0.0
total_pl_only = 0.0
total_balance_only = 0.0

for row in results:
    amount = float(row['Amount'])
    vw = row['VW']
    total_all += amount
    
    if vw == 'Y':
        total_pl_only += amount
    elif vw == 'N':
        total_balance_only += amount
    
    print(f"{row['Parent']:<7} {row['Aangifte']:<30} {row['Reknum']:<7} {vw:<3} €{amount:>14,.2f}")

print("-" * 100)
print(f"\nTotals:")
print(f"  All accounts:           €{total_all:>14,.2f}")
print(f"  P&L only (VW='Y'):      €{total_pl_only:>14,.2f}")
print(f"  Balance only (VW='N'):  €{total_balance_only:>14,.2f}")
print()
print(f"Expected RESULTAAT:     €28,853.76")
print()

# Check if excluding account 8099 gives us the expected result
query2 = """
    SELECT 
        SUM(Amount) as Total
    FROM vw_mutaties
    WHERE (
        (VW = 'N' AND TransactionDate <= %s) OR
        (VW = 'Y' AND YEAR(TransactionDate) = %s)
    )
    AND administration = %s
    AND Parent IS NOT NULL
    AND Aangifte IS NOT NULL
    AND Reknum != '8099'
"""

result = db.execute_query(query2, (year_end, year, administration), fetch=True)
total_excluding_8099 = float(result[0]['Total']) if result else 0.0

print(f"Total excluding account 8099: €{total_excluding_8099:,.2f}")
