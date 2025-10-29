#!/usr/bin/env python3
"""
Check column names in vw_mutaties view
"""

import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')

def check_columns():
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'finance')
    )
    
    cursor = conn.cursor()
    
    # Get column information
    cursor.execute("DESCRIBE vw_mutaties")
    columns = cursor.fetchall()
    
    print("=== VW_MUTATIES COLUMNS ===")
    for col in columns:
        print(f"{col[0]} - {col[1]}")
    
    # Get sample data
    cursor.execute("SELECT * FROM vw_mutaties WHERE Administration LIKE 'Goodwin%' LIMIT 3")
    sample = cursor.fetchall()
    
    print("\n=== SAMPLE DATA ===")
    col_names = [desc[0] for desc in cursor.description]
    print("Columns:", col_names)
    
    for i, row in enumerate(sample):
        print(f"Row {i+1}:", dict(zip(col_names, row)))
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_columns()