#!/usr/bin/env python3
"""
Debug account names lookup
"""

import os
import sys
from pathlib import Path

# Add src to path
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir / 'src'))
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv(backend_dir / '.env')

from database import DatabaseManager
from db_exceptions import DatabaseError


def debug_account_names():
    db = DatabaseManager()

    # Check what's in vw_mutaties for account names
    results = db.execute_query(
        "SELECT DISTINCT Reknum, AccountName, Administration FROM vw_mutaties "
        "WHERE Administration LIKE 'Goodwin%' LIMIT 10",
        fetch=True
    )

    print("=== VW_MUTATIES ACCOUNT NAMES ===")
    for row in results:
        print(f"Reknum: {row['Reknum']}, AccountName: {row['AccountName']}, Admin: {row['Administration']}")

    # Check rekeningschema table if it exists
    try:
        schema_results = db.execute_query("SELECT * FROM rekeningschema LIMIT 5", fetch=True)
        print("\n=== REKENINGSCHEMA TABLE ===")
        for row in schema_results:
            print(row)
    except DatabaseError:
        print("\n=== REKENINGSCHEMA TABLE NOT FOUND ===")


if __name__ == "__main__":
    try:
        debug_account_names()
    except DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
