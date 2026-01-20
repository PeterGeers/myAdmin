"""
Investigate the gap that appears at transaction ID 60333
"""
import requests
import json

BASE_URL = "http://localhost:5000"

def get_transactions_around_gap():
    """Get transactions before and after the first gap appears"""
    print("\n=== INVESTIGATING GAP AT ID 60333 ===")
    
    # We need to query the database directly to see transactions around ID 60333
    # Let's get transactions from ID 60320 to 60340
    
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from src.database import DatabaseManager
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
            ID,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Debet,
            Credit,
            Ref1,
            Ref2,
            Ref3
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND ID BETWEEN 60320 AND 60340
        ORDER BY ID
    """)
    
    transactions = cursor.fetchall()
    
    print(f"\nFound {len(transactions)} transactions around the gap:")
    print(f"{'ID':<8} {'Date':<12} {'Description':<30} {'Amount':<10} {'Debet':<6} {'Credit':<6} {'Ref3':<10}")
    print("=" * 100)
    
    for tx in transactions:
        print(f"{tx['ID']:<8} {str(tx['TransactionDate']):<12} {tx['TransactionDescription'][:30]:<30} "
              f"{tx['TransactionAmount']:<10.2f} {tx['Debet']:<6} {tx['Credit']:<6} {tx['Ref3']:<10}")
    
    cursor.close()
    conn.close()
    
    # Now let's manually calculate the balance for these transactions
    print("\n\n=== MANUAL BALANCE CALCULATION ===")
    
    # Get the last good balance (before the gap)
    cursor = db.get_connection().cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            ID,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Debet,
            Credit,
            Ref3
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND ID < 60333
        ORDER BY ID DESC
        LIMIT 5
    """)
    
    before_gap = cursor.fetchall()
    print("\nLast 5 transactions BEFORE the gap:")
    for tx in before_gap:
        print(f"  ID: {tx['ID']}, Date: {tx['TransactionDate']}, "
              f"Desc: {tx['TransactionDescription'][:30]}, "
              f"Amount: {tx['TransactionAmount']}, Ref3: {tx['Ref3']}")
    
    cursor.close()

if __name__ == '__main__':
    get_transactions_around_gap()
