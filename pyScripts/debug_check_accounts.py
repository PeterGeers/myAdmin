#!/usr/bin/env python3
"""
Debug check banking accounts function
"""

import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

def debug_check_accounts():
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )
    
    cursor = conn.cursor(dictionary=True)
    
    # Check lookupbankaccounts_r table
    cursor.execute("SELECT * FROM lookupbankaccounts_r LIMIT 5")
    accounts = cursor.fetchall()
    print("=== LOOKUPBANKACCOUNTS_R ===")
    for acc in accounts:
        print(acc)
    
    if not accounts:
        print("No accounts found in lookupbankaccounts_r!")
        cursor.close()
        conn.close()
        return
    
    # Get administrations and account patterns
    administrations = list(set([acc['Administration'] for acc in accounts]))
    account_codes = list(set([acc['Account'] for acc in accounts]))
    
    admin_pattern = '|'.join(administrations)
    account_pattern = '|'.join(account_codes)
    
    print(f"\nAdmin pattern: {admin_pattern}")
    print(f"Account pattern: {account_pattern}")
    
    # Test the main query
    cursor.execute("""
        SELECT Reknum, Administration, 
               ROUND(SUM(Amount), 2) as calculated_balance,
               MAX(AccountName) as account_name
        FROM vw_mutaties 
        WHERE Administration REGEXP %s 
        AND Reknum REGEXP %s
        GROUP BY Reknum, Administration
        LIMIT 5
    """, (admin_pattern, account_pattern))
    
    balances = cursor.fetchall()
    print(f"\n=== CALCULATED BALANCES ===")
    for balance in balances:
        print(balance)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    debug_check_accounts()