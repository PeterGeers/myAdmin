"""
Delete June 2025 Revolut transactions (with confirmation)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from src.database import DatabaseManager

def delete_june_transactions():
    """Delete June Revolut transactions with confirmation"""
    print("\n=== DELETE JUNE 2025 REVOLUT TRANSACTIONS ===")
    print("⚠️  WARNING: This will permanently delete transactions!")
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # First, count transactions
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND TransactionDate >= '2025-06-01'
        AND TransactionDate < '2025-07-01'
    """)
    
    result = cursor.fetchone()
    count = result['count']
    
    if count == 0:
        print("No June transactions found to delete!")
        cursor.close()
        conn.close()
        return
    
    print(f"\nFound {count} June 2025 Revolut transactions to delete")
    
    # Show sample
    cursor.execute("""
        SELECT 
            ID,
            TransactionDate,
            TransactionDescription,
            TransactionAmount
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND TransactionDate >= '2025-06-01'
        AND TransactionDate < '2025-07-01'
        ORDER BY ID
        LIMIT 5
    """)
    
    sample = cursor.fetchall()
    print(f"\nSample transactions (first 5):")
    for tx in sample:
        print(f"  ID {tx['ID']}: {tx['TransactionDate']} - {tx['TransactionDescription'][:40]} - €{tx['TransactionAmount']}")
    
    # Confirmation
    print(f"\n{'='*80}")
    print(f"⚠️  YOU ARE ABOUT TO DELETE {count} TRANSACTIONS!")
    print(f"{'='*80}")
    
    confirmation = input("\nType 'DELETE' to confirm (or anything else to cancel): ")
    
    if confirmation != 'DELETE':
        print("\n❌ Deletion cancelled")
        cursor.close()
        conn.close()
        return
    
    # Double confirmation
    confirmation2 = input(f"\nAre you ABSOLUTELY SURE? Type 'YES' to proceed: ")
    
    if confirmation2 != 'YES':
        print("\n❌ Deletion cancelled")
        cursor.close()
        conn.close()
        return
    
    # Perform deletion
    print(f"\n🗑️  Deleting {count} transactions...")
    
    cursor.execute("""
        DELETE FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND TransactionDate >= '2025-06-01'
        AND TransactionDate < '2025-07-01'
    """)
    
    conn.commit()
    
    print(f"✓ Successfully deleted {cursor.rowcount} transactions")
    
    # Verify deletion
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND TransactionDate >= '2025-06-01'
        AND TransactionDate < '2025-07-01'
    """)
    
    result = cursor.fetchone()
    remaining = result['count']
    
    if remaining == 0:
        print("✓ Verification: No June transactions remaining")
    else:
        print(f"⚠️  Warning: {remaining} transactions still remain!")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    delete_june_transactions()
