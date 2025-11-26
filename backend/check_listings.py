import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import DatabaseManager

db = DatabaseManager(test_mode=False)
conn = db.get_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT DISTINCT listing FROM bnbfuture ORDER BY listing")
print("Current listing values:")
for row in cursor.fetchall():
    print(f"  - {row['listing']}")

cursor.close()
conn.close()
