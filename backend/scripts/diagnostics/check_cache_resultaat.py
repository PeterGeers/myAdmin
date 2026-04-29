"""Check resultaat using cache method."""

import os
import sys
from pathlib import Path

backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

from database import DatabaseManager
from mutaties_cache import get_cache

db = DatabaseManager(test_mode=False)
cache = get_cache()
cache.get_data(db)

year = 2025
administration = 'GoodwinSolutions'

# Use cache method
summary_data = cache.query_aangifte_ib(year, administration)

print(f"\nData from cache for {administration} year {year}:")
print("-" * 80)

total = 0.0
for row in summary_data:
    amount = float(row['Amount'])
    total += amount
    print(f"{row['Parent']:5s} | {row['Aangifte']:30s} | €{amount:15,.2f}")

print("-" * 80)
print(f"RESULTAAT (sum of all amounts): €{total:,.2f}")
print()
