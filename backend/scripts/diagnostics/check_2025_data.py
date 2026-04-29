"""Quick script to check what data exists for 2025."""

import os
import sys
from pathlib import Path

backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

# Check what years we have data for
query = """
    SELECT 
        YEAR(TransactionDate) as Year,
        administration,
        COUNT(*) as RecordCount,
        SUM(Amount) as TotalAmount
    FROM vw_mutaties
    WHERE administration = 'GoodwinSolutions'
    GROUP BY YEAR(TransactionDate), administration
    ORDER BY Year DESC
"""

results = db.execute_query(query, fetch=True)

print("\nData by year for GoodwinSolutions:")
print("-" * 80)
for row in results:
    print(f"Year {row['Year']}: {row['RecordCount']:,} records, Total: €{row['TotalAmount']:,.2f}")

# Check specific parent totals for 2025
query2 = """
    SELECT 
        Parent,
        SUM(Amount) as Amount
    FROM vw_mutaties
    WHERE YEAR(TransactionDate) = 2025
    AND administration = 'GoodwinSolutions'
    AND Parent IS NOT NULL
    GROUP BY Parent
    ORDER BY Parent
"""

results2 = db.execute_query(query2, fetch=True)

print("\nParent totals for 2025:")
print("-" * 80)
for row in results2:
    print(f"Parent {row['Parent']}: €{row['Amount']:,.2f}")
