#!/usr/bin/env python3
"""
Show duplicate transactions in Goodwin administration data
"""

import mysql.connector
import os
from dotenv import load_dotenv
import pandas as pd

load_dotenv('backend/.env')

def show_duplicates():
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )
    
    cursor = conn.cursor(dictionary=True)
    
    # Query Goodwin administration data
    query = "SELECT * FROM vw_mutaties WHERE Administration LIKE 'Goodwin%'"
    cursor.execute(query)
    results = cursor.fetchall()
    
    df = pd.DataFrame(results)
    
    # Find duplicates based on date, description, and amount
    duplicate_mask = df.duplicated(subset=['TransactionDate', 'TransactionDescription', 'Amount'], keep=False)
    duplicates = df[duplicate_mask].sort_values(['TransactionDate', 'TransactionDescription', 'Amount'])
    
    print(f"=== DUPLICATE TRANSACTIONS ({len(duplicates)} records) ===\n")
    
    # Group duplicates for better display
    grouped = duplicates.groupby(['TransactionDate', 'TransactionDescription', 'Amount'])
    
    for (date, desc, amount), group in grouped:
        print(f"Date: {date}")
        print(f"Description: {desc}")
        print(f"Amount: ${amount}")
        print(f"Duplicate Count: {len(group)}")
        print("Records:")
        for _, row in group.iterrows():
            print(f"  - Account: {row['Reknum']} ({row['AccountName']})")
            print(f"    Ref: {row['ReferenceNumber']}")
            print(f"    Transaction#: {row['TransactionNumber']}")
        print("-" * 80)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    show_duplicates()