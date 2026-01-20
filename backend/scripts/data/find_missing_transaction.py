"""
Find the missing transaction(s) that cause the gap
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from src.database import DatabaseManager

def find_gap():
    """Find where the gap starts"""
    print("\n=== FINDING THE GAP ===")
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get transactions before and including ID 60333
    cursor.execute("""
        SELECT 
            ID,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Debet,
            Credit,
            Ref2,
            Ref3
        FROM mutaties 
        WHERE Ref1 = 'NL08REVO7549383472'
        AND ID <= 60333
        AND TransactionDate >= '2025-05-01'
        ORDER BY ID DESC
        LIMIT 20
    """)
    
    transactions = cursor.fetchall()
    
    print(f"\nLast 20 transactions before/including the gap (ID 60333):")
    print(f"{'ID':<8} {'Date':<12} {'Description':<35} {'Amount':<10} {'D':<6} {'C':<6} {'Ref3':<10}")
    print("=" * 110)
    
    # Calculate balance manually
    calculated_balance = None
    for i, tx in enumerate(reversed(transactions)):
        amount = float(tx['TransactionAmount'] or 0)
        ref3 = float(tx['Ref3']) if tx['Ref3'] else None
        
        # For first transaction, use Ref3
        if calculated_balance is None:
            calculated_balance = ref3
            balance_change = 0
        else:
            # Calculate balance change
            if tx['Debet'] == '1022':
                balance_change = amount
            elif tx['Credit'] == '1022':
                balance_change = -amount
            else:
                balance_change = 0
            calculated_balance += balance_change
        
        discrepancy = ref3 - calculated_balance if ref3 is not None else None
        
        marker = " <-- GAP!" if abs(discrepancy or 0) > 0.01 else ""
        disc_str = f"{discrepancy:.2f}" if discrepancy is not None else "N/A"
        
        print(f"{tx['ID']:<8} {str(tx['TransactionDate']):<12} {tx['TransactionDescription'][:35]:<35} "
              f"{amount:<10.2f} {tx['Debet']:<6} {tx['Credit']:<6} {ref3:<10.2f} "
              f"Calc: {calculated_balance:.2f}, Disc: {disc_str}{marker}")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    find_gap()
