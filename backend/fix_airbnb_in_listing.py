import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import DatabaseManager

db = DatabaseManager(test_mode=False)
conn = db.get_connection()
cursor = conn.cursor()

cursor.execute("UPDATE bnbfuture SET listing = REPLACE(REPLACE(listing, 'AirBnB', ''), 'airbnb', '')")
updated = cursor.rowcount
print(f"Updated {updated} rows - removed AirBnB/airbnb from listing names")

cursor.execute("UPDATE bnbfuture SET listing = TRIM(listing)")
trimmed = cursor.rowcount
print(f"Trimmed {trimmed} rows")

conn.commit()

cursor.execute("SELECT DISTINCT listing FROM bnbfuture ORDER BY listing")
print("\nFinal listing values:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")

cursor.close()
conn.close()
