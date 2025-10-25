#!/usr/bin/env python3
"""
Analyze the base mutaties table for Goodwin administration
"""

import mysql.connector
import os
from dotenv import load_dotenv
import pandas as pd

load_dotenv('backend/.env')

def analyze_mutaties_table():
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )
    
    cursor = conn.cursor(dictionary=True)
    
    # Check table structure
    cursor.execute("DESCRIBE mutaties")
    columns = cursor.fetchall()
    
    print("=== MUTATIES TABLE STRUCTURE ===")
    for col in columns:
        print(f"{col['Field']} - {col['Type']}")
    
    # Query Goodwin data from base table
    query = "SELECT * FROM mutaties WHERE Administration LIKE 'Goodwin%' LIMIT 10"
    cursor.execute(query)
    sample = cursor.fetchall()
    
    print("\n=== SAMPLE MUTATIES RECORDS ===")
    for i, row in enumerate(sample):
        print(f"Row {i+1}:")
        for key, value in row.items():
            print(f"  {key}: {value}")
        print("-" * 50)
    
    # Count records
    cursor.execute("SELECT COUNT(*) as count FROM mutaties WHERE Administration LIKE 'Goodwin%'")
    count = cursor.fetchone()['count']
    print(f"\n=== RECORD COUNT ===")
    print(f"Total mutaties records: {count}")
    
    # Compare with view count
    cursor.execute("SELECT COUNT(*) as count FROM vw_mutaties WHERE Administration LIKE 'Goodwin%'")
    view_count = cursor.fetchone()['count']
    print(f"Total vw_mutaties records: {view_count}")
    print(f"View multiplier: {view_count / count if count > 0 else 0:.1f}x")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    analyze_mutaties_table()