#!/usr/bin/env python3
"""
Debug account names lookup
"""

import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

def debug_account_names():
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )
    
    cursor = conn.cursor(dictionary=True)
    
    # Check what's in vw_mutaties for account names
    cursor.execute("SELECT DISTINCT Reknum, AccountName, Administration FROM vw_mutaties WHERE Administration LIKE 'Goodwin%' LIMIT 10")
    results = cursor.fetchall()
    
    print("=== VW_MUTATIES ACCOUNT NAMES ===")
    for row in results:
        print(f"Reknum: {row['Reknum']}, AccountName: {row['AccountName']}, Admin: {row['Administration']}")
    
    # Check rekeningschema table if it exists
    try:
        cursor.execute("SELECT * FROM rekeningschema LIMIT 5")
        schema_results = cursor.fetchall()
        print("\n=== REKENINGSCHEMA TABLE ===")
        for row in schema_results:
            print(row)
    except:
        print("\n=== REKENINGSCHEMA TABLE NOT FOUND ===")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    debug_account_names()