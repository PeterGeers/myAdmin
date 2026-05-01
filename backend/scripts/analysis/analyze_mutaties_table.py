#!/usr/bin/env python3
"""
Analyze the base mutaties table for Goodwin administration
"""

import os
import sys
from pathlib import Path

import pandas as pd

# Add src to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir / 'src'))
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / '.env')

from database import DatabaseManager
from db_exceptions import DatabaseError


def analyze_mutaties_table():
    db = DatabaseManager()

    # Check table structure
    columns = db.execute_query("DESCRIBE mutaties", fetch=True)

    print("=== MUTATIES TABLE STRUCTURE ===")
    for col in columns:
        print(f"{col['Field']} - {col['Type']}")

    # Query Goodwin data from base table
    query = "SELECT * FROM mutaties WHERE Administration LIKE 'Goodwin%' LIMIT 10"
    sample = db.execute_query(query, fetch=True)

    print("\n=== SAMPLE MUTATIES RECORDS ===")
    for i, row in enumerate(sample):
        print(f"Row {i+1}:")
        for key, value in row.items():
            print(f"  {key}: {value}")
        print("-" * 50)

    # Count records
    result = db.execute_query(
        "SELECT COUNT(*) as count FROM mutaties WHERE Administration LIKE 'Goodwin%'",
        fetch=True
    )
    count = result[0]['count']
    print(f"\n=== RECORD COUNT ===")
    print(f"Total mutaties records: {count}")

    # Compare with view count
    view_result = db.execute_query(
        "SELECT COUNT(*) as count FROM vw_mutaties WHERE Administration LIKE 'Goodwin%'",
        fetch=True
    )
    view_count = view_result[0]['count']
    print(f"Total vw_mutaties records: {view_count}")
    print(f"View multiplier: {view_count / count if count > 0 else 0:.1f}x")


if __name__ == "__main__":
    try:
        analyze_mutaties_table()
    except DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
