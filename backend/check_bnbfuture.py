import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import DatabaseManager

db = DatabaseManager(test_mode=False)
conn = db.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute('SELECT * FROM bnbfuture ORDER BY date, listing, channel')
rows = cursor.fetchall()

print(f'Total rows: {len(rows)}\n')
print(f"{'Date':<12} | {'Channel':<15} | {'Listing':<25} | {'Amount':>10} | Items")
print("-" * 90)

for row in rows:
    print(f"{str(row['date']):<12} | {str(row['channel']):<15} | {str(row['listing']):<25} | {float(row['amount']):>10.2f} | {row['items']}")

cursor.close()
conn.close()
