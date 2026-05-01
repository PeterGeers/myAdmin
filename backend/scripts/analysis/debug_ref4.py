#!/usr/bin/env python3
"""
Debug Ref4 values in mutaties table
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


def debug_ref4():
    db = DatabaseManager()

    # Check Ref4 values in mutaties table
    results = db.execute_query(
        "SELECT Ref4, COUNT(*) as count FROM mutaties "
        "WHERE Administration LIKE 'Goodwin%' GROUP BY Ref4 ORDER BY count DESC LIMIT 10",
        fetch=True
    )

    print("=== REF4 VALUES IN MUTATIES ===")
    for row in results:
        print(f"Ref4: '{row['Ref4']}', Count: {row['count']}")

    # Check a specific account's last transactions
    last_transactions = db.execute_query(
        """
        SELECT TransactionDate, TransactionDescription, Ref2, Ref4
        FROM mutaties 
        WHERE Administration = 'GoodwinSolutions' 
        AND (Debet = '1002' OR Credit = '1002')
        ORDER BY TransactionDate DESC, Ref2 DESC
        LIMIT 5
        """,
        fetch=True
    )

    print("\n=== LAST 5 TRANSACTIONS FOR ACCOUNT 1002 ===")
    for tx in last_transactions:
        print(f"Date: {tx['TransactionDate']}, Ref2: {tx['Ref2']}, Ref4: '{tx['Ref4']}'")
        print(f"Description: {tx['TransactionDescription']}")
        print("-" * 50)


if __name__ == "__main__":
    try:
        debug_ref4()
    except DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
