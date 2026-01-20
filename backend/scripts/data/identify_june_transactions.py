"""
Identify all June 2025 Revolut transaction IDs for deletion
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from src.database import DatabaseManager

def identify_june_transactions():
    """List all June Revolut transaction IDs"""
    print("\n=== IDENTIFYING JUNE 2025 REVOLUT TRANSACTIONS ===")
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all Revolut transactions from June 2025
    cursor.execute("""
        SELECT 
            ID,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Ref2,
            Ref3
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND TransactionDate >= '2025-06-01'
        AND TransactionDate < '2025-07-01'
        ORDER BY ID
    """)
    
    transactions = cursor.fetchall()
    
    if not transactions:
        print("No June transactions found!")
        cursor.close()
        conn.close()
        return
    
    print(f"\nFound {len(transactions)} June 2025 Revolut transactions")
    print(f"ID range: {transactions[0]['ID']} to {transactions[-1]['ID']}")
    print(f"Date range: {transactions[0]['TransactionDate']} to {transactions[-1]['TransactionDate']}")
    
    # Show first 5 and last 5
    print(f"\nFirst 5 transactions:")
    for tx in transactions[:5]:
        print(f"  ID {tx['ID']}: {tx['TransactionDate']} - {tx['TransactionDescription'][:40]} - €{tx['TransactionAmount']}")
    
    print(f"\nLast 5 transactions:")
    for tx in transactions[-5:]:
        print(f"  ID {tx['ID']}: {tx['TransactionDate']} - {tx['TransactionDescription'][:40]} - €{tx['TransactionAmount']}")
    
    # Generate DELETE statement
    id_list = [str(tx['ID']) for tx in transactions]
    
    print(f"\n{'='*80}")
    print("SQL DELETE STATEMENT:")
    print(f"{'='*80}")
    print(f"DELETE FROM mutaties WHERE ID IN ({', '.join(id_list)});")
    print(f"{'='*80}")
    
    print(f"\nOr use date-based delete:")
    print(f"DELETE FROM mutaties")
    print(f"WHERE Ref1 = 'NL08REVO7549383472'")
    print(f"AND TransactionDate >= '2025-06-01'")
    print(f"AND TransactionDate < '2025-07-01';")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    identify_june_transactions()
