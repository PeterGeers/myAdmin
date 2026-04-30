#!/usr/bin/env python3
"""
Check column names in vw_mutaties view
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


def check_columns():
    db = DatabaseManager()

    # Get column information
    columns = db.execute_query("DESCRIBE vw_mutaties", fetch=True)

    print("=== VW_MUTATIES COLUMNS ===")
    for col in columns:
        print(f"{col['Field']} - {col['Type']}")

    # Get sample data
    sample = db.execute_query(
        "SELECT * FROM vw_mutaties WHERE Administration LIKE 'Goodwin%' LIMIT 3",
        fetch=True
    )

    print("\n=== SAMPLE DATA ===")
    if sample:
        col_names = list(sample[0].keys())
        print("Columns:", col_names)

        for i, row in enumerate(sample):
            print(f"Row {i+1}:", row)


if __name__ == "__main__":
    try:
        check_columns()
    except DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
