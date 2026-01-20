"""
Export all June 2025 Revolut transactions to CSV for backup before re-import
"""
import sys
import os
import csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from src.database import DatabaseManager

def export_june_revolut():
    """Export June Revolut transactions to CSV"""
    print("\n=== EXPORTING JUNE 2025 REVOLUT TRANSACTIONS ===")
    
    db = DatabaseManager(test_mode=False)
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all Revolut transactions from June 2025
    cursor.execute("""
        SELECT 
            ID,
            TransactionNumber,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Debet,
            Credit,
            ReferenceNumber,
            Ref1,
            Ref2,
            Ref3,
            Ref4,
            Administration
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
    
    # Export to CSV
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'june_revolut_backup_{timestamp}.csv'
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['ID', 'TransactionNumber', 'TransactionDate', 'TransactionDescription', 
                     'TransactionAmount', 'Debet', 'Credit', 'ReferenceNumber', 
                     'Ref1', 'Ref2', 'Ref3', 'Ref4', 'Administration']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for tx in transactions:
            writer.writerow(tx)
    
    print(f"\n✓ Exported {len(transactions)} transactions to {filename}")
    print(f"\nFirst transaction: ID {transactions[0]['ID']}, Date: {transactions[0]['TransactionDate']}")
    print(f"Last transaction: ID {transactions[-1]['ID']}, Date: {transactions[-1]['TransactionDate']}")
    
    # Show summary by date
    from collections import defaultdict
    by_date = defaultdict(int)
    for tx in transactions:
        by_date[str(tx['TransactionDate'])] += 1
    
    print(f"\nTransactions by date:")
    for date in sorted(by_date.keys()):
        print(f"  {date}: {by_date[date]} transactions")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    export_june_revolut()
