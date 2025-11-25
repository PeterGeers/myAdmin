#!/usr/bin/env python3
"""
Debug script to test reference analysis functionality
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from database import DatabaseManager
import re

def test_reference_analysis():
    """Test the reference analysis functionality"""
    
    # Initialize database
    db = DatabaseManager(test_mode=False)
    connection = db.get_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Test 1: Check if we have any reference numbers at all
        print("=== Test 1: Check reference numbers ===")
        cursor.execute("""
            SELECT COUNT(*) as total_count,
                   COUNT(DISTINCT ReferenceNumber) as unique_refs
            FROM vw_mutaties 
            WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != ''
        """)
        result = cursor.fetchone()
        print(f"Total transactions with references: {result['total_count']}")
        print(f"Unique reference numbers: {result['unique_refs']}")
        
        # Test 2: Show sample reference numbers
        print("\n=== Test 2: Sample reference numbers ===")
        cursor.execute("""
            SELECT DISTINCT ReferenceNumber 
            FROM vw_mutaties 
            WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != ''
            ORDER BY ReferenceNumber
            LIMIT 10
        """)
        refs = cursor.fetchall()
        for ref in refs:
            print(f"- {ref['ReferenceNumber']}")
        
        # Test 3: Test regex functionality
        print("\n=== Test 3: Test regex patterns ===")
        test_patterns = ['AMZN', '.*Amazon.*', 'BOOKING', '.*']
        
        for pattern in test_patterns:
            try:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM vw_mutaties 
                    WHERE ReferenceNumber REGEXP %s
                """, [pattern])
                result = cursor.fetchone()
                print(f"Pattern '{pattern}': {result['count']} matches")
            except Exception as e:
                print(f"Pattern '{pattern}': ERROR - {e}")
        
        # Test 4: Check available years
        print("\n=== Test 4: Available years ===")
        cursor.execute("""
            SELECT DISTINCT jaar 
            FROM vw_mutaties 
            WHERE jaar IS NOT NULL 
            ORDER BY jaar DESC
        """)
        years = cursor.fetchall()
        print(f"Available years: {[y['jaar'] for y in years]}")
        
        # Test 5: Check available accounts
        print("\n=== Test 5: Available accounts ===")
        cursor.execute("""
            SELECT DISTINCT Reknum, AccountName 
            FROM vw_mutaties 
            WHERE Reknum IS NOT NULL AND Reknum != ''
                  AND AccountName IS NOT NULL AND AccountName != ''
            ORDER BY Reknum
            LIMIT 10
        """)
        accounts = cursor.fetchall()
        for acc in accounts:
            print(f"- {acc['Reknum']}: {acc['AccountName']}")
        
        # Test 6: Test a specific reference analysis query
        print("\n=== Test 6: Test reference analysis query ===")
        cursor.execute("""
            SELECT TransactionDate, TransactionDescription, Amount, Reknum,
                   AccountName, ReferenceNumber, Administration
            FROM vw_mutaties
            WHERE jaar IN (2024, 2025) 
                  AND ReferenceNumber IS NOT NULL 
                  AND ReferenceNumber != ''
            ORDER BY TransactionDate DESC
            LIMIT 5
        """)
        transactions = cursor.fetchall()
        print(f"Sample transactions: {len(transactions)}")
        for tx in transactions:
            print(f"- {tx['TransactionDate']}: {tx['ReferenceNumber']} - €{tx['Amount']}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    test_reference_analysis()