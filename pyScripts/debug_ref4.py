#!/usr/bin/env python3
"""
Debug Ref4 values in mutaties table
"""

import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

def debug_ref4():
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )
    
    cursor = conn.cursor(dictionary=True)
    
    # Check Ref4 values in mutaties table
    cursor.execute("SELECT Ref4, COUNT(*) as count FROM mutaties WHERE Administration LIKE 'Goodwin%' GROUP BY Ref4 ORDER BY count DESC LIMIT 10")
    results = cursor.fetchall()
    
    print("=== REF4 VALUES IN MUTATIES ===")
    for row in results:
        print(f"Ref4: '{row['Ref4']}', Count: {row['count']}")
    
    # Check a specific account's last transactions
    cursor.execute("""
        SELECT TransactionDate, TransactionDescription, Ref2, Ref4
        FROM mutaties 
        WHERE Administration = 'GoodwinSolutions' 
        AND (Debet = '1002' OR Credit = '1002')
        ORDER BY TransactionDate DESC, Ref2 DESC
        LIMIT 5
    """)
    
    last_transactions = cursor.fetchall()
    print("\n=== LAST 5 TRANSACTIONS FOR ACCOUNT 1002 ===")
    for tx in last_transactions:
        print(f"Date: {tx['TransactionDate']}, Ref2: {tx['Ref2']}, Ref4: '{tx['Ref4']}'")
        print(f"Description: {tx['TransactionDescription']}")
        print("-" * 50)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    debug_ref4()