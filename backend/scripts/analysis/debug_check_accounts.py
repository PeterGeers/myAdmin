#!/usr/bin/env python3
"""
Debug check banking accounts function
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


def debug_check_accounts():
    db = DatabaseManager()

    # Check lookupbankaccounts_r table
    accounts = db.execute_query("SELECT * FROM lookupbankaccounts_r LIMIT 5", fetch=True)
    print("=== LOOKUPBANKACCOUNTS_R ===")
    for acc in accounts:
        print(acc)

    if not accounts:
        print("No accounts found in lookupbankaccounts_r!")
        return

    # Get administrations and account patterns
    administrations = list(set([acc['Administration'] for acc in accounts]))
    account_codes = list(set([acc['Account'] for acc in accounts]))

    admin_pattern = '|'.join(administrations)
    account_pattern = '|'.join(account_codes)

    print(f"\nAdmin pattern: {admin_pattern}")
    print(f"Account pattern: {account_pattern}")

    # Test the main query
    balances = db.execute_query(
        """
        SELECT Reknum, Administration, 
               ROUND(SUM(Amount), 2) as calculated_balance,
               MAX(AccountName) as account_name
        FROM vw_mutaties 
        WHERE Administration REGEXP %s 
        AND Reknum REGEXP %s
        GROUP BY Reknum, Administration
        LIMIT 5
        """,
        (admin_pattern, account_pattern),
        fetch=True
    )

    print(f"\n=== CALCULATED BALANCES ===")
    for balance in balances:
        print(balance)


if __name__ == "__main__":
    try:
        debug_check_accounts()
    except DatabaseError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
