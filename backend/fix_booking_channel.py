import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from database import DatabaseManager

db = DatabaseManager(test_mode=False)
conn = db.get_connection()
cursor = conn.cursor(dictionary=True)

print("=== Fixing Booking.com channel names ===\n")

# Check current state
cursor.execute("SELECT DISTINCT channel FROM bnbfuture ORDER BY channel")
print("Current channel values:")
for row in cursor.fetchall():
    print(f"  - {row['channel']}")

# Update any channel containing 'ooking' to 'Booking.com'
cursor.execute("UPDATE bnbfuture SET channel = 'Booking.com' WHERE channel LIKE '%ooking%'")
updated = cursor.rowcount
print(f"\nUpdated {updated} rows where channel contains 'ooking'")

conn.commit()

# Show final state
cursor.execute("SELECT DISTINCT channel FROM bnbfuture ORDER BY channel")
print("\nFinal channel values:")
for row in cursor.fetchall():
    print(f"  - {row['channel']}")

cursor.close()
conn.close()

print("\nDone!")
