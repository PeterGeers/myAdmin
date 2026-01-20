"""
Check if there are transactions between ID 60307 and 60333 that are NOT Revolut
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from src.database import DatabaseManager

def check_id_gap():
    """Check transactions in the ID gap"""
    print("\n=== CHECKING ID GAP 60307 to 60333 ===")
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get ALL transactions between these IDs
    cursor.execute("""
        SELECT 
            ID,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Debet,
            Credit,
            Ref1,
            Ref3
        FROM mutaties 
        WHERE ID BETWEEN 60307 AND 60333
        ORDER BY ID
    """)
    
    transactions = cursor.fetchall()
    
    print(f"\nFound {len(transactions)} transactions in ID range 60307-60333:")
    print(f"{'ID':<8} {'Date':<12} {'Description':<40} {'Amount':<10} {'D':<6} {'C':<6} {'IBAN':<25} {'Ref3':<10}")
    print("=" * 130)
    
    revolut_count = 0
    other_count = 0
    
    for tx in transactions:
        is_revolut = tx['Ref1'] == 'NL08REVO7549383472'
        if is_revolut:
            revolut_count += 1
            marker = " [REVOLUT]"
        else:
            other_count += 1
            marker = " [OTHER]"
        
        print(f"{tx['ID']:<8} {str(tx['TransactionDate']):<12} {tx['TransactionDescription'][:40]:<40} "
              f"{float(tx['TransactionAmount'] or 0):<10.2f} {tx['Debet']:<6} {tx['Credit']:<6} "
              f"{(tx['Ref1'] or '')[:25]:<25} {(tx['Ref3'] or ''):<10}{marker}")
    
    print(f"\nSummary:")
    print(f"  Revolut transactions: {revolut_count}")
    print(f"  Other transactions: {other_count}")
    print(f"  Total: {len(transactions)}")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    check_id_gap()
