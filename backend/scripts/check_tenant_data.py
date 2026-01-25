#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("Checking all administrations in vw_mutaties:")
result = db.execute_query("""
    SELECT administration, COUNT(*) as count
    FROM vw_mutaties
    GROUP BY administration
    ORDER BY administration
""")

total = 0
for row in result:
    print(f"  {row['administration']:30} : {row['count']:>6} records")
    total += row['count']

print(f"\n  {'TOTAL':30} : {total:>6} records")

print("\nChecking all administrations in mutaties table:")
result = db.execute_query("""
    SELECT administration, COUNT(*) as count
    FROM mutaties
    GROUP BY administration
    ORDER BY administration
""")

total = 0
for row in result:
    print(f"  {row['administration']:30} : {row['count']:>6} records")
    total += row['count']

print(f"\n  {'TOTAL':30} : {total:>6} records")
