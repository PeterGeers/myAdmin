#!/usr/bin/env python3
"""
Quick schema verification script
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager()

print("Checking mutaties table...")
result = db.execute_query("SHOW COLUMNS FROM mutaties")
cols = [r['Field'] for r in result]
print(f"Columns: {', '.join(cols[:10])}...")
print(f"Has 'administration': {'administration' in cols}")
print(f"Has 'Administration': {'Administration' in cols}")

print("\nChecking rekeningschema table...")
result = db.execute_query("SHOW COLUMNS FROM rekeningschema")
cols = [r['Field'] for r in result]
print(f"Columns: {', '.join(cols[:10])}...")
print(f"Has 'administration': {'administration' in cols}")
print(f"Has 'Administration': {'Administration' in cols}")

print("\nChecking vw_mutaties view...")
try:
    result = db.execute_query("SELECT * FROM vw_mutaties LIMIT 1")
    if result:
        print(f"Columns: {', '.join(result[0].keys())}")
except Exception as e:
    print(f"Error: {e}")

print("\nChecking vw_rekeningschema view...")
try:
    result = db.execute_query("SELECT * FROM vw_rekeningschema LIMIT 1")
    if result:
        print(f"Columns: {', '.join(result[0].keys())}")
except Exception as e:
    print(f"Error: {e}")
