#!/usr/bin/env python3
"""
Show duplicate transactions in Goodwin administration data
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


def show_duplicates():
    db = DatabaseManager()

    # Query Goodwin administration data
    results = db.execute_query(
        "SELECT * FROM mutaties WHERE Administration LIKE 'Goodwin%'",
        fetch=True
    )

    df = pd.DataFrame(results)

    # Find duplicates based on date, description, amount, debet, and credit
    duplicate_mask = df.duplicated(
        subset=['TransactionDate', 'TransactionDescription', 'TransactionAmount',
                'Debet', 'Credit', 'ReferenceNumber'],
        keep=False
    )
    duplicates = df[duplicate_mask].sort_values(
        ['TransactionDate', 'TransactionDescription', 'TransactionAmount',
         'Debet', 'Credit', 'ReferenceNumber']
    )

    print(f"=== DUPLICATE TRANSACTIONS ({len(duplicates)} records) ===\n")

    # Group duplicates for better display
    grouped = duplicates.groupby(
        ['TransactionDate', 'TransactionDescription', 'TransactionAmount',
         'Debet', 'Credit', 'ReferenceNumber']
    )

    for (date, desc, amount, debet, credit, ref), group in grouped:
        print(f"Date: {date}")
        print(f"Description: {desc}")
        print(f"Amount: ${amount}")
        print(f"Debet: {debet} | Credit: {credit}")
        print(f"Duplicate Count: {len(group)}")
        print("Records:")
        for _, row in group.iterrows():
            print(f"  - ID: {row['ID']}")
            print(f"    Ref: {row['ReferenceNumber']}")
            print(f"    Transaction#: {row['TransactionNumber']}")
        print("-" * 80)


if __name__ == "__main__":
    try:
        show_duplicates()
    except DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
