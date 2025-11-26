import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import DatabaseManager

db = DatabaseManager(test_mode=False)
conn = db.get_connection()
cursor = conn.cursor()

cursor.execute("UPDATE bnbfuture SET channel = 'AirBnB' WHERE channel LIKE '%airbnb%'")
updated = cursor.rowcount
print(f"Updated {updated} rows to 'AirBnB'")

conn.commit()

cursor.execute("SELECT DISTINCT channel FROM bnbfuture ORDER BY channel")
print("\nFinal channel values:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")

cursor.close()
conn.close()
