import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import DatabaseManager

db = DatabaseManager(test_mode=False)
conn = db.get_connection()
cursor = conn.cursor()

print("=== Fixing listing names ===\n")

# Update old listing names to standardized format
updates = [
    ("UPDATE bnbfuture SET listing = 'Child Friendly' WHERE listing LIKE '%child.friendly%'", "Child Friendly"),
    ("UPDATE bnbfuture SET listing = 'Green Studio' WHERE listing LIKE '%green.studio%'", "Green Studio"),
    ("UPDATE bnbfuture SET listing = 'Red Studio' WHERE listing LIKE '%Red.Studio%'", "Red Studio")
]

total_updated = 0
for query, name in updates:
    cursor.execute(query)
    count = cursor.rowcount
    total_updated += count
    print(f"Updated {count} rows to '{name}'")

conn.commit()

# Show final state
cursor.execute("SELECT DISTINCT listing FROM bnbfuture ORDER BY listing")
print("\nFinal listing values:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")

print(f"\nTotal updated: {total_updated} rows")

cursor.close()
conn.close()
print("\nDone!")
